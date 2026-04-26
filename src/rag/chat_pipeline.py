"""Analytical chat pipeline for multi-stage retrieval and grounded generation."""

from __future__ import annotations

import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Any, Optional

from src.rag.chat_evidence import EvidenceSynthesizer, source_key as _source_key
from src.rag.chat_intent import (
    QueryIntentDetector,
    detect_language as _detect_language,
    normalize_text as _normalize_text,
)
from src.rag.chat_reranker import DeterministicReranker, safe_float as _safe_float
from src.rag.chat_types import (
    EvidencePack,
    HypothesisCandidate,
    PipelineResult,
    QueryIntent,
    ROUTING_INTENT_ANALYTICAL_RAG,
    ROUTING_INTENT_ANALYTICAL_WITH_LIVE_PRICE,
    ROUTING_INTENT_FACTUAL_RAG,
    ROUTING_INTENT_PORTFOLIO_TRANSACTION,
    ROUTING_INTENT_PURE_LIVE_PRICE,
    ScoredChunk,
)
from src.rag.guardrails import (
    build_scope_refusal,
    detect_scope_violation,
    validate_response_output,
)
from src.rag.model_router import ChatModelRouter, ModelRoutingDecision
from src.rag.prompt_loader import render_prompt
from src.services.portfolio_context_formatter import build_enriched_portfolio_context
from src.utils.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)
TOOL_CATEGORY_LIVE_MARKET = "live_market_tools"
TOOL_CATEGORY_PORTFOLIO_ACTION = "portfolio_action_tools"

_HYPOTHESIS_CACHE: dict[str, tuple[float, list[HypothesisCandidate]]] = {}
_COMPRESSION_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_PIPELINE_CACHE_LOCK = Lock()


def _extract_json_block(text: str) -> Optional[str]:
    """Extract probable JSON payload from plain text or fenced blocks."""
    if not text:
        return None

    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    fenced = re.search(
        r"```(?:json)?\s*({[\s\S]*})\s*```", stripped, flags=re.IGNORECASE
    )
    if fenced:
        return fenced.group(1).strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1].strip()
    return None


def _safe_json_loads(text: str) -> Optional[dict[str, Any]]:
    """Safely parse JSON object from model output."""
    json_block = _extract_json_block(text)
    if not json_block:
        return None
    try:
        parsed = json.loads(json_block)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return None
    return None


class AnalyticalChatPipeline:
    """End-to-end chat pipeline: retrieval -> synthesis -> analyst -> advisor."""

    HYPOTHESIS_COUNT_MIN = 2
    HYPOTHESIS_COUNT_MAX = 4
    HYPOTHESIS_RETRIEVAL_TOP_K = 12
    HYPOTHESIS_SNIPPETS_PER_HYPOTHESIS = 8
    TOKENS_HYPOTHESIS = 220
    TOKENS_COMPRESSION = 450
    TOKENS_ANALYST_FACTUAL = 350
    TOKENS_ANALYST_COMPRESSED = 350
    TOKENS_ADVISOR_FACTUAL = 700
    TOKENS_ADVISOR_COMPRESSED = 1400
    TOKENS_LIVE_PRICE = 280
    TOKENS_PORTFOLIO_DRAFT = 420

    def __init__(self, retriever: Any, generator: Any):
        self.retriever = retriever
        self.generator = generator
        self.intent_detector = QueryIntentDetector()
        self.model_router = ChatModelRouter()
        self.reranker = DeterministicReranker()
        self.synthesizer = EvidenceSynthesizer()
        self._last_model_call_metadata: Optional[dict[str, Any]] = None

    @staticmethod
    def _build_hypothesis_cache_key(
        *,
        question: str,
        user_context: str,
        routing_intent: str,
    ) -> str:
        payload = (
            f"q={_normalize_text(question)}|"
            f"intent={routing_intent}|"
            f"ctx={_normalize_text(user_context)[:2500]}"
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _build_compression_cache_key(
        *,
        question: str,
        hypothesis_payload_json: str,
        source_registry_json: str,
    ) -> str:
        payload = (
            f"q={_normalize_text(question)}|"
            f"h={hypothesis_payload_json}|"
            f"s={source_registry_json}"
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _cache_get_hypotheses(cache_key: str) -> Optional[list[HypothesisCandidate]]:
        ttl_seconds = max(int(settings.chat_hypothesis_cache_ttl_seconds), 0)
        if ttl_seconds <= 0:
            return None
        now = time.monotonic()
        with _PIPELINE_CACHE_LOCK:
            cached = _HYPOTHESIS_CACHE.get(cache_key)
            if not cached:
                return None
            created_at, payload = cached
            if now - created_at > ttl_seconds:
                _HYPOTHESIS_CACHE.pop(cache_key, None)
                return None
            return [
                HypothesisCandidate(
                    hypothesis_id=item.hypothesis_id,
                    short_title=item.short_title,
                    description=item.description,
                    evidence_query=item.evidence_query,
                )
                for item in payload
            ]

    @staticmethod
    def _cache_set_hypotheses(
        cache_key: str, hypotheses: list[HypothesisCandidate]
    ) -> None:
        ttl_seconds = max(int(settings.chat_hypothesis_cache_ttl_seconds), 0)
        if ttl_seconds <= 0:
            return
        max_entries = max(int(settings.chat_hypothesis_cache_max_entries), 1)
        with _PIPELINE_CACHE_LOCK:
            _HYPOTHESIS_CACHE[cache_key] = (
                time.monotonic(),
                [
                    HypothesisCandidate(
                        hypothesis_id=item.hypothesis_id,
                        short_title=item.short_title,
                        description=item.description,
                        evidence_query=item.evidence_query,
                    )
                    for item in hypotheses
                ],
            )
            if len(_HYPOTHESIS_CACHE) > max_entries:
                oldest_key = min(
                    _HYPOTHESIS_CACHE, key=lambda key: _HYPOTHESIS_CACHE[key][0]
                )
                _HYPOTHESIS_CACHE.pop(oldest_key, None)

    @staticmethod
    def _cache_get_compression(cache_key: str) -> Optional[dict[str, Any]]:
        ttl_seconds = max(int(settings.chat_compression_cache_ttl_seconds), 0)
        if ttl_seconds <= 0:
            return None
        now = time.monotonic()
        with _PIPELINE_CACHE_LOCK:
            cached = _COMPRESSION_CACHE.get(cache_key)
            if not cached:
                return None
            created_at, payload = cached
            if now - created_at > ttl_seconds:
                _COMPRESSION_CACHE.pop(cache_key, None)
                return None
            return json.loads(json.dumps(payload))

    @staticmethod
    def _cache_set_compression(cache_key: str, compression: dict[str, Any]) -> None:
        ttl_seconds = max(int(settings.chat_compression_cache_ttl_seconds), 0)
        if ttl_seconds <= 0:
            return
        max_entries = max(int(settings.chat_compression_cache_max_entries), 1)
        with _PIPELINE_CACHE_LOCK:
            _COMPRESSION_CACHE[cache_key] = (
                time.monotonic(),
                json.loads(json.dumps(compression)),
            )
            if len(_COMPRESSION_CACHE) > max_entries:
                oldest_key = min(
                    _COMPRESSION_CACHE, key=lambda key: _COMPRESSION_CACHE[key][0]
                )
                _COMPRESSION_CACHE.pop(oldest_key, None)

    def _resolve_stage_deployments(
        self,
        *,
        routing_intent: str,
        selected_deployment: str,
    ) -> dict[str, str]:
        default_deployment = (
            self.model_router.default_deployment or selected_deployment
        ).strip()
        advanced_deployment = (
            self.model_router.advanced_deployment or selected_deployment
        ).strip()

        stage_deployments = {
            "hypothesis": selected_deployment,
            "compression": selected_deployment,
            "analyst": selected_deployment,
            "advisor": selected_deployment,
        }

        if (
            routing_intent
            in {
                ROUTING_INTENT_ANALYTICAL_RAG,
                ROUTING_INTENT_ANALYTICAL_WITH_LIVE_PRICE,
            }
            and selected_deployment == advanced_deployment
            and default_deployment
            and default_deployment != advanced_deployment
        ):
            stage_deployments["hypothesis"] = default_deployment
            stage_deployments["compression"] = default_deployment
            stage_deployments["analyst"] = default_deployment
            stage_deployments["advisor"] = advanced_deployment

        return stage_deployments

    @staticmethod
    def _format_user_context(
        user_notes: list[dict],
        user_portfolio: list[dict],
        portfolio_totals: Optional[dict[str, Any]] = None,
    ) -> str:
        context_parts: list[str] = []

        if user_portfolio:
            context_parts.append(
                build_enriched_portfolio_context(
                    user_portfolio,
                    marker="Portfolio",
                    empty_message="No user portfolio or notes context provided.",
                )
            )

        if user_notes:
            note_lines = [
                f"- {note.get('content', '')}"
                for note in user_notes[:20]
                if note.get("content")
            ]
            if note_lines:
                context_parts.append("User Notes:\n" + "\n".join(note_lines))

        return (
            "\n\n".join(context_parts)
            if context_parts
            else "No user portfolio or notes context provided."
        )

    @staticmethod
    def _extract_citation_indices(text: str, max_index: int) -> list[int]:
        found: set[int] = set()

        for block in re.findall(r"\[([^\]]+)]", text or ""):
            for token in re.split(r"[,;\s]+", block.strip()):
                if token.isdigit():
                    idx = int(token)
                    if 1 <= idx <= max_index:
                        found.add(idx)

        return sorted(found)

    @staticmethod
    def _source_payload_by_indices(
        sources: list[dict[str, Any]], indices: list[int]
    ) -> list[dict[str, Any]]:
        index_set = set(indices)
        return [source for source in sources if source.get("index") in index_set]

    @staticmethod
    def _insufficient_message(language: str) -> str:
        if language == "uk":
            return (
                "У наявній базі знань недостатньо підтвердженої інформації, щоб надійно відповісти на це питання. "
                "Спробуйте уточнити тему, період або конкретний актив."
            )
        return (
            "The available knowledge base does not contain enough grounded evidence to answer this reliably. "
            "Please narrow the topic, timeframe, or specific asset."
        )

    def _resolve_model_routing(
        self,
        *,
        question: str,
        intent: QueryIntent,
        user_context: str,
    ) -> ModelRoutingDecision:
        return self.model_router.route(
            question=question,
            routing_intent=intent.routing_intent,
            has_portfolio_context="Portfolio:\n" in user_context,
            requires_live_price_tool=intent.requires_live_price_tool,
        )

    @staticmethod
    def _apply_guardrails_to_output(
        *,
        message: str,
        routing_intent: str,
        language: str,
    ) -> tuple[str, list[str], bool]:
        result = validate_response_output(
            message=message,
            routing_intent=routing_intent,
            language=language,
        )
        return result.message.strip(), result.triggered_rules, result.clear_sources

    @staticmethod
    def _tool_categories_for_intent(
        routing_intent: str,
        *,
        include_portfolio_actions: bool = False,
    ) -> list[str]:
        categories: list[str] = []
        if routing_intent in {
            ROUTING_INTENT_PURE_LIVE_PRICE,
            ROUTING_INTENT_ANALYTICAL_WITH_LIVE_PRICE,
        }:
            categories.append(TOOL_CATEGORY_LIVE_MARKET)
        if (
            include_portfolio_actions
            or routing_intent == ROUTING_INTENT_PORTFOLIO_TRANSACTION
        ):
            categories.append(TOOL_CATEGORY_PORTFOLIO_ACTION)
        return categories

    @staticmethod
    def _is_portfolio_add_request(question: str) -> bool:
        normalized = _normalize_text(question)
        explicit_analysis_hints = (
            "що думаєш",
            "як думаєш",
            "what do you think",
            "оціни",
            "analyze",
            "проаналіз",
            "ризик",
            "risk",
            "чи варто",
            "should i",
            "should we",
            "поясни",
            "why",
            "чому",
        )
        if any(hint in normalized for hint in explicit_analysis_hints):
            return False

        transaction_verbs = (
            "купив",
            "купила",
            "купили",
            "продав",
            "продала",
            "продали",
            "взяв",
            "взяла",
            "взяли",
            "додав",
            "додала",
            "додали",
            "добавив",
            "добавила",
            "bought",
            "sold",
            "acquired",
            "added",
            "purchased",
            "took",
            "buy",
            "sell",
        )
        has_transaction_verb = any(
            re.search(rf"\b{re.escape(verb)}\b", normalized)
            for verb in transaction_verbs
        )
        if not has_transaction_verb:
            return False

        ticker_candidates = re.findall(r"\b[A-Z]{2,10}\b", question or "")
        non_market_tokens = {"OVDP", "GDP", "IRS", "FED", "ECB"}
        has_ticker = any(token not in non_market_tokens for token in ticker_candidates)
        asset_hints = (
            "акці",
            "etf",
            "stock",
            "крипт",
            "crypto",
            "btc",
            "eth",
            "ovdp",
            "овдп",
            "облігац",
            "депозит",
            "готів",
            "cash",
            "asset",
            "актив",
        )
        has_asset_reference = has_ticker or any(
            hint in normalized for hint in asset_hints
        )
        if not has_asset_reference:
            return False

        numeric_tokens = re.findall(r"\d+(?:[.,]\d+)?", question or "")
        number_count = len(numeric_tokens)
        price_hints = (
            " за ",
            " for ",
            " по ",
            "usd",
            "uah",
            "eur",
            "бакс",
            "дол",
            "грн",
            "$",
            "€",
            "₴",
        )
        has_price_signal = number_count >= 2 or (
            number_count >= 1 and any(hint in normalized for hint in price_hints)
        )

        return has_price_signal

    @staticmethod
    def _get_last_assistant_message(history: list[dict[str, Any]]) -> str:
        for item in reversed(history):
            if str(item.get("role") or "").strip().lower() != "assistant":
                continue
            content = item.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
        return ""

    @classmethod
    def _is_portfolio_add_followup(
        cls, question: str, history: list[dict[str, Any]]
    ) -> bool:
        if not history:
            return False

        last_assistant = cls._get_last_assistant_message(history)
        if not last_assistant:
            return False

        assistant_normalized = _normalize_text(last_assistant)
        asks_total_vs_unit = (
            (
                any(
                    token in assistant_normalized
                    for token in ("total", "загальн", "сума")
                )
                and any(
                    token in assistant_normalized
                    for token in (
                        "unit",
                        "per share",
                        "за одиниц",
                        "ціна за одиниц",
                        "ціна за акцію",
                    )
                )
            )
            or "is 600 usd the total transaction amount or the price per share"
            in assistant_normalized
        )
        if not asks_total_vs_unit:
            return False

        normalized = _normalize_text(question)
        if not normalized:
            return False

        direct_answers = {
            "total",
            "total amount",
            "загальна сума",
            "загальна",
            "за одиницю",
            "ціна за одиницю",
            "unit",
            "unit price",
            "per unit",
            "per share",
        }
        if normalized in direct_answers:
            return True

        short_followup = len(normalized.split()) <= 8
        has_disambiguation_keyword = any(
            token in normalized
            for token in (
                "total",
                "загальн",
                "сума",
                "unit",
                "за одиниц",
                "ціна за одиниц",
                "per unit",
                "per share",
            )
        )
        return short_followup and has_disambiguation_keyword

    def _generate_with_optional_metadata(
        self, **kwargs: Any
    ) -> tuple[str, Optional[dict[str, Any]]]:
        self._last_model_call_metadata = None
        generate_structured = getattr(self.generator, "generate_structured", None)
        if callable(generate_structured):
            result = generate_structured(**kwargs)
            if isinstance(result, dict):
                message = str(result.get("message") or "").strip()
                pending = result.get("pending_transaction_draft")
                model_call_metadata = result.get("model_call_metadata")
                if isinstance(model_call_metadata, dict):
                    self._last_model_call_metadata = {
                        "requested_deployment": str(
                            model_call_metadata.get("requested_deployment") or ""
                        ).strip()
                        or None,
                        "final_deployment": str(
                            model_call_metadata.get("final_deployment") or ""
                        ).strip()
                        or None,
                        "fallback_used": bool(model_call_metadata.get("fallback_used")),
                    }
                return message, pending if isinstance(pending, dict) else None
        message = self.generator.generate(**kwargs)
        return str(message or "").strip(), None

    def _final_answer_model_info(self, *, selected_deployment: str) -> tuple[str, bool]:
        final_answer_model = (selected_deployment or "").strip()
        fallback_used = False
        metadata = self._last_model_call_metadata
        if isinstance(metadata, dict):
            candidate = str(metadata.get("final_deployment") or "").strip()
            if candidate:
                final_answer_model = candidate
            fallback_used = bool(metadata.get("fallback_used"))
        if (
            final_answer_model
            and selected_deployment
            and final_answer_model != selected_deployment
        ):
            fallback_used = True
        return final_answer_model or selected_deployment, fallback_used

    def _generate_hypotheses(
        self,
        question: str,
        user_context: str,
        routing_intent: str,
        deployment: Optional[str],
    ) -> list[HypothesisCandidate]:
        """Generate 2-4 plausible hypotheses for analytical questions."""
        cache_key = self._build_hypothesis_cache_key(
            question=question,
            user_context=user_context,
            routing_intent=routing_intent,
        )
        cached = self._cache_get_hypotheses(cache_key)
        if cached is not None:
            logger.info("Hypothesis cache hit for route=%s", routing_intent)
            return cached

        system_prompt = render_prompt("chat_pipeline/hypothesis_system.txt")

        route_hint = (
            "Route=analytical_with_live_price. Include at least one hypothesis for interpretation of the current move."
            if routing_intent == ROUTING_INTENT_ANALYTICAL_WITH_LIVE_PRICE
            else "Route=analytical_rag."
        )

        prompt = render_prompt(
            "chat_pipeline/hypothesis_user.txt",
            question=question,
            user_context=user_context,
            route_hint=route_hint,
        )

        try:
            raw = self.generator.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=self.TOKENS_HYPOTHESIS,
                temperature=0.25,
                deployment=deployment,
                chat_intent=routing_intent,
            )
            parsed = _safe_json_loads(raw or "")
            if parsed:
                parsed_hypotheses = self._parse_hypothesis_payload(parsed)
                if parsed_hypotheses:
                    self._cache_set_hypotheses(cache_key, parsed_hypotheses)
                    return parsed_hypotheses
        except Exception:
            logger.warning(
                "Hypothesis generation failed, using deterministic fallback",
                exc_info=True,
            )

        fallback = self._fallback_hypotheses(question, routing_intent)
        self._cache_set_hypotheses(cache_key, fallback)
        return fallback

    @classmethod
    def _parse_hypothesis_payload(
        cls, payload: dict[str, Any]
    ) -> list[HypothesisCandidate]:
        raw_items = payload.get("hypotheses")
        if not isinstance(raw_items, list):
            return []

        hypotheses: list[HypothesisCandidate] = []
        for index, item in enumerate(raw_items[: cls.HYPOTHESIS_COUNT_MAX], start=1):
            if not isinstance(item, dict):
                continue
            hypothesis_id = (
                str(item.get("hypothesis_id") or f"H{index}").strip() or f"H{index}"
            )
            short_title = str(item.get("short_title") or "").strip()
            description = str(item.get("description") or "").strip()
            evidence_query = str(item.get("evidence_query") or "").strip()

            if not short_title or not evidence_query:
                continue

            if not description:
                description = short_title

            hypotheses.append(
                HypothesisCandidate(
                    hypothesis_id=hypothesis_id,
                    short_title=short_title[:120],
                    description=description[:500],
                    evidence_query=evidence_query[:200],
                )
            )

        if len(hypotheses) < cls.HYPOTHESIS_COUNT_MIN:
            return []
        return hypotheses

    @classmethod
    def _fallback_hypotheses(
        cls,
        question: str,
        routing_intent: str,
    ) -> list[HypothesisCandidate]:
        normalized = _normalize_text(question)
        has_ovdp = (
            "овдп" in normalized or "ovdp" in normalized or "облігац" in normalized
        )
        has_crypto = any(
            token in normalized
            for token in ("bitcoin", "btc", "ethereum", "eth", "крипт")
        )

        if has_ovdp:
            return [
                HypothesisCandidate(
                    hypothesis_id="H1",
                    short_title="Ризик рефінансування",
                    description="Поточний фон може відображати побоювання щодо обсягу майбутніх погашень та попиту.",
                    evidence_query="ОВДП ризики рефінансування попит аукціони погашення",
                ),
                HypothesisCandidate(
                    hypothesis_id="H2",
                    short_title="Макро-ставки та інфляція",
                    description="Динаміка очікувань щодо ставок та інфляції може тиснути на оцінку дохідності ОВДП.",
                    evidence_query="ОВДП інфляція ставки НБУ дохідність ризики",
                ),
                HypothesisCandidate(
                    hypothesis_id="H3",
                    short_title="Політика та ліквідність",
                    description="Коментарі щодо бюджетного фінансування та ліквідності банків можуть пояснювати дисбаланс.",
                    evidence_query="ОВДП ліквідність банки бюджет розміщення Мінфін",
                ),
            ]

        base_asset = "Bitcoin" if has_crypto else "акції"
        base_ticker = "BTC" if has_crypto else "AAPL"
        fallback = [
            HypothesisCandidate(
                hypothesis_id="H1",
                short_title="Специфічний фактор активу",
                description="Рух міг бути спричинений новиною або подією, що стосується саме активу.",
                evidence_query=f"{base_ticker} company specific news earnings guidance sentiment",
            ),
            HypothesisCandidate(
                hypothesis_id="H2",
                short_title="Ринковий/макро фактор",
                description="Рух міг бути частиною ширшого ринкового або макро тренду ризик-апетиту.",
                evidence_query=f"{base_asset} market macro risk appetite rates dollar flows",
            ),
            HypothesisCandidate(
                hypothesis_id="H3",
                short_title="Короткостроковий шум",
                description="Рух може бути переважно технічним або короткостроковим без зміни фундаменталу.",
                evidence_query=f"{base_ticker} technical move positioning short term volatility",
            ),
        ]

        if routing_intent == ROUTING_INTENT_ANALYTICAL_WITH_LIVE_PRICE:
            fallback.append(
                HypothesisCandidate(
                    hypothesis_id="H4",
                    short_title="Матеріальність для портфеля",
                    description="Навіть при волатильності вплив на портфель може бути обмеженим через розмір позиції.",
                    evidence_query="portfolio concentration position sizing drawdown exposure impact",
                )
            )
        return fallback[: cls.HYPOTHESIS_COUNT_MAX]

    def _retrieve_evidence_for_hypotheses(
        self,
        hypotheses: list[HypothesisCandidate],
        intent: QueryIntent,
    ) -> dict[str, list[ScoredChunk]]:
        """Retrieve and rerank evidence for each hypothesis query."""
        evidence_by_hypothesis: dict[str, list[ScoredChunk]] = {}
        if not hypotheses:
            return evidence_by_hypothesis

        workers = min(
            max(int(settings.chat_parallel_hypothesis_workers), 1),
            len(hypotheses),
        )
        if workers <= 1:
            for hypothesis in hypotheses:
                evidence_by_hypothesis[hypothesis.hypothesis_id] = (
                    self._retrieve_single_hypothesis_evidence(
                        hypothesis=hypothesis,
                        intent=intent,
                    )
                )
            return evidence_by_hypothesis

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(
                    self._retrieve_single_hypothesis_evidence,
                    hypothesis=hypothesis,
                    intent=intent,
                ): hypothesis.hypothesis_id
                for hypothesis in hypotheses
            }
            for future in as_completed(future_map):
                hypothesis_id = future_map[future]
                try:
                    evidence_by_hypothesis[hypothesis_id] = future.result()
                except Exception:
                    logger.warning(
                        "Parallel hypothesis retrieval failed for %s",
                        hypothesis_id,
                        exc_info=True,
                    )
                    evidence_by_hypothesis[hypothesis_id] = []

        # Keep deterministic ordering by hypothesis list order.
        return {
            hypothesis.hypothesis_id: evidence_by_hypothesis.get(
                hypothesis.hypothesis_id, []
            )
            for hypothesis in hypotheses
        }

    def _retrieve_single_hypothesis_evidence(
        self,
        *,
        hypothesis: HypothesisCandidate,
        intent: QueryIntent,
    ) -> list[ScoredChunk]:
        try:
            raw = self.retriever.search(
                hypothesis.evidence_query,
                top_k=self.HYPOTHESIS_RETRIEVAL_TOP_K,
            )
        except Exception:
            logger.warning(
                "Hypothesis retrieval failed for %s (%s)",
                hypothesis.hypothesis_id,
                hypothesis.evidence_query,
                exc_info=True,
            )
            raw = []
        ranked = self.reranker.rerank(raw, intent)
        return ranked[: self.HYPOTHESIS_RETRIEVAL_TOP_K]

    def _build_source_registry_from_hypothesis_evidence(
        self,
        evidence_by_hypothesis: dict[str, list[ScoredChunk]],
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """Create a unified deduplicated source map across all hypotheses."""
        flattened: list[ScoredChunk] = []
        for candidates in evidence_by_hypothesis.values():
            flattened.extend(candidates)

        deduped = self.synthesizer.deduplicate_candidates(flattened)
        deduped.sort(
            key=lambda item: (
                str(item.metadata.get("date") or ""),
                str(item.metadata.get("url") or ""),
                str(item.metadata.get("source_id") or ""),
            )
        )
        return self.synthesizer._build_source_registry(deduped)

    def _compress_evidence_pack(
        self,
        question: str,
        hypotheses: list[HypothesisCandidate],
        evidence_by_hypothesis: dict[str, list[ScoredChunk]],
        source_lookup: dict[str, int],
        sources: list[dict[str, Any]],
        deployment: Optional[str],
        routing_intent: Optional[str] = None,
    ) -> dict[str, Any]:
        """Compress per-hypothesis evidence into compact structured pack."""
        snippets_by_hypothesis: dict[str, list[dict[str, Any]]] = {}
        for hypothesis in hypotheses:
            candidates = evidence_by_hypothesis.get(hypothesis.hypothesis_id, [])
            snippets: list[dict[str, Any]] = []
            for candidate in candidates[: self.HYPOTHESIS_SNIPPETS_PER_HYPOTHESIS]:
                key = _source_key(candidate.metadata, candidate.content)
                source_idx = source_lookup.get(key)
                if not source_idx:
                    continue
                snippets.append(
                    {
                        "source_index": source_idx,
                        "channel": candidate.metadata.get("channel", "Unknown"),
                        "date": candidate.metadata.get("date", "N/A"),
                        "domain": candidate.metadata.get("domain", "N/A"),
                        "trust_weight": _safe_float(
                            candidate.metadata.get("trust_weight"), 0.5
                        ),
                        "score": round(candidate.rerank_score, 4),
                        "excerpt": candidate.content[:420],
                    }
                )
            snippets_by_hypothesis[hypothesis.hypothesis_id] = snippets

        system_prompt = render_prompt("chat_pipeline/evidence_compression_system.txt")

        hypothesis_payload = [
            {
                "hypothesis_id": hypothesis.hypothesis_id,
                "short_title": hypothesis.short_title,
                "description": hypothesis.description,
                "evidence_query": hypothesis.evidence_query,
                "evidence_snippets": snippets_by_hypothesis.get(
                    hypothesis.hypothesis_id, []
                ),
            }
            for hypothesis in hypotheses
        ]
        hypothesis_payload_json = json.dumps(hypothesis_payload, ensure_ascii=False)
        source_registry_json = json.dumps(sources, ensure_ascii=False)
        cache_key = self._build_compression_cache_key(
            question=question,
            hypothesis_payload_json=hypothesis_payload_json,
            source_registry_json=source_registry_json,
        )
        cached_pack = self._cache_get_compression(cache_key)
        if cached_pack is not None:
            logger.info("Evidence compression cache hit for question signature")
            return cached_pack

        prompt = render_prompt(
            "chat_pipeline/evidence_compression_user.txt",
            question=question,
            hypothesis_payload_json=hypothesis_payload_json,
            source_registry_json=source_registry_json,
        )

        try:
            raw = self.generator.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=self.TOKENS_COMPRESSION,
                temperature=0.2,
                deployment=deployment,
                chat_intent=routing_intent,
            )
            parsed = _safe_json_loads(raw or "")
            if parsed:
                normalized = self._parse_compressed_evidence_payload(
                    parsed, hypotheses, sources
                )
                if normalized:
                    self._cache_set_compression(cache_key, normalized)
                    return normalized
        except Exception:
            logger.warning(
                "Evidence compression failed, using deterministic fallback",
                exc_info=True,
            )

        fallback = self._fallback_compressed_evidence_pack(
            hypotheses, snippets_by_hypothesis, sources
        )
        self._cache_set_compression(cache_key, fallback)
        return fallback

    @staticmethod
    def _parse_compressed_evidence_payload(
        payload: dict[str, Any],
        hypotheses: list[HypothesisCandidate],
        sources: list[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        raw_hypotheses = payload.get("hypotheses")
        if not isinstance(raw_hypotheses, list):
            return None

        source_indices = {
            int(source.get("index"))
            for source in sources
            if str(source.get("index", "")).isdigit()
        }
        normalized_hypotheses: list[dict[str, Any]] = []

        for hypothesis in raw_hypotheses:
            if not isinstance(hypothesis, dict):
                continue

            hypothesis_id = str(hypothesis.get("hypothesis_id") or "").strip()
            title = str(hypothesis.get("title") or "").strip()
            confidence = str(hypothesis.get("confidence") or "").strip().lower()
            if confidence not in {"low", "medium", "high"}:
                confidence = "medium"

            supporting = [
                int(item)
                for item in hypothesis.get("supporting_evidence", [])
                if isinstance(item, int) and item in source_indices
            ]
            contradicting = [
                int(item)
                for item in hypothesis.get("contradicting_evidence", [])
                if isinstance(item, int) and item in source_indices
            ]
            source_notes_raw = hypothesis.get("source_notes", [])
            source_notes = (
                [str(note).strip() for note in source_notes_raw if str(note).strip()]
                if isinstance(source_notes_raw, list)
                else []
            )

            if not hypothesis_id:
                continue

            normalized_hypotheses.append(
                {
                    "hypothesis_id": hypothesis_id,
                    "title": title or hypothesis_id,
                    "supporting_evidence": sorted(set(supporting)),
                    "contradicting_evidence": sorted(set(contradicting)),
                    "source_notes": source_notes[:4],
                    "confidence": confidence,
                }
            )

        if not normalized_hypotheses:
            return None

        known_ids = {hypothesis.hypothesis_id for hypothesis in hypotheses}
        normalized_hypotheses = [
            item for item in normalized_hypotheses if item["hypothesis_id"] in known_ids
        ]
        if not normalized_hypotheses:
            return None

        consensus = str(payload.get("cross_source_consensus") or "").strip()
        uncertainties_raw = payload.get("major_uncertainties", [])
        uncertainties = (
            [str(item).strip() for item in uncertainties_raw if str(item).strip()]
            if isinstance(uncertainties_raw, list)
            else []
        )
        sources_used_raw = payload.get("sources_used", [])
        sources_used = [
            int(item)
            for item in sources_used_raw
            if isinstance(item, int) and item in source_indices
        ]

        if not sources_used:
            sources_used = sorted(
                {
                    idx
                    for item in normalized_hypotheses
                    for idx in item["supporting_evidence"]
                    + item["contradicting_evidence"]
                }
            )

        return {
            "hypotheses": normalized_hypotheses,
            "cross_source_consensus": consensus,
            "major_uncertainties": uncertainties[:6],
            "sources_used": sorted(set(sources_used)),
            "sources": sources,
        }

    @staticmethod
    def _fallback_compressed_evidence_pack(
        hypotheses: list[HypothesisCandidate],
        snippets_by_hypothesis: dict[str, list[dict[str, Any]]],
        sources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        fallback_hypotheses: list[dict[str, Any]] = []
        all_used_sources: set[int] = set()

        for hypothesis in hypotheses:
            snippets = snippets_by_hypothesis.get(hypothesis.hypothesis_id, [])
            supporting = [
                int(item["source_index"])
                for item in snippets[:3]
                if isinstance(item.get("source_index"), int)
            ]
            all_used_sources.update(supporting)

            confidence = "low"
            if len(supporting) >= 3:
                confidence = "medium"
            if len(supporting) >= 4:
                confidence = "high"

            source_notes = []
            for snippet in snippets[:3]:
                excerpt = str(snippet.get("excerpt") or "").strip()
                if excerpt:
                    source_notes.append(excerpt[:160])

            fallback_hypotheses.append(
                {
                    "hypothesis_id": hypothesis.hypothesis_id,
                    "title": hypothesis.short_title,
                    "supporting_evidence": supporting,
                    "contradicting_evidence": [],
                    "source_notes": source_notes,
                    "confidence": confidence,
                }
            )

        consensus = "Evidence is mixed with partial overlap across sources."
        uncertainties = ["Some hypotheses rely on limited or single-source evidence."]

        return {
            "hypotheses": fallback_hypotheses,
            "cross_source_consensus": consensus,
            "major_uncertainties": uncertainties,
            "sources_used": sorted(all_used_sources),
            "sources": sources,
        }

    @staticmethod
    def _compressed_pack_to_prompt_text(compressed_pack: dict[str, Any]) -> str:
        """Render compressed evidence pack as compact text for downstream prompts."""
        source_map: list[str] = []
        for source in compressed_pack.get("sources", []):
            source_map.append(
                f"[{source.get('index')}] channel={source.get('channel')}; domain={source.get('domain')}; "
                f"date={source.get('date')}; trust={source.get('trust_weight')}; url={source.get('url')}"
            )

        hypotheses_lines: list[str] = []
        for hypothesis in compressed_pack.get("hypotheses", []):
            sup = (
                " ".join(
                    f"[{idx}]" for idx in hypothesis.get("supporting_evidence", [])
                )
                or "N/A"
            )
            con = (
                " ".join(
                    f"[{idx}]" for idx in hypothesis.get("contradicting_evidence", [])
                )
                or "N/A"
            )
            notes = (
                " | ".join(hypothesis.get("source_notes", [])[:3])
                if hypothesis.get("source_notes")
                else "N/A"
            )
            hypotheses_lines.append(
                f"{hypothesis.get('hypothesis_id')}: {hypothesis.get('title')}\n"
                f"Confidence: {hypothesis.get('confidence')}\n"
                f"Supporting: {sup}\n"
                f"Contradicting: {con}\n"
                f"Notes: {notes}"
            )

        consensus = compressed_pack.get("cross_source_consensus") or "N/A"
        uncertainties = compressed_pack.get("major_uncertainties") or []
        uncertainty_block = (
            "\n".join(f"- {item}" for item in uncertainties)
            if uncertainties
            else "- N/A"
        )
        sources_used = (
            " ".join(f"[{idx}]" for idx in compressed_pack.get("sources_used", []))
            or "N/A"
        )

        return (
            "COMPRESSED SOURCE MAP:\n"
            + ("\n".join(source_map) if source_map else "No sources.\n")
            + "\n\nHYPOTHESIS SUMMARY:\n"
            + (
                "\n\n".join(hypotheses_lines)
                if hypotheses_lines
                else "No hypotheses.\n"
            )
            + f"\n\nCROSS-SOURCE CONSENSUS:\n{consensus}\n\n"
            + f"MAJOR UNCERTAINTIES:\n{uncertainty_block}\n\n"
            + f"SOURCES USED:\n{sources_used}"
        )

    def _analyst_step(
        self,
        question: str,
        evidence_pack: EvidencePack,
        user_context: str,
        deployment: Optional[str],
    ) -> str:
        """Existing factual-RAG analyst step (no hypothesis layer)."""
        system_prompt = render_prompt("chat_pipeline/analyst_factual_system.txt")
        prompt = render_prompt(
            "chat_pipeline/analyst_factual_user.txt",
            question=question,
            user_context=user_context,
            evidence_pack=evidence_pack.to_prompt_text(),
        )

        return self.generator.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=self.TOKENS_ANALYST_FACTUAL,
            temperature=0.2,
            deployment=deployment,
            chat_intent=ROUTING_INTENT_FACTUAL_RAG,
        )

    def _analyst_step_from_compressed(
        self,
        question: str,
        user_context: str,
        compressed_pack: dict[str, Any],
        routing_intent: str,
        deployment: Optional[str],
    ) -> str:
        """Analyst reasoning over hypothesis-compressed evidence."""
        system_prompt = render_prompt("chat_pipeline/analyst_compressed_system.txt")
        prompt = render_prompt(
            "chat_pipeline/analyst_compressed_user.txt",
            question=question,
            user_context=user_context,
            compressed_evidence_pack=self._compressed_pack_to_prompt_text(
                compressed_pack
            ),
        )

        return self.generator.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=self.TOKENS_ANALYST_COMPRESSED,
            temperature=0.2,
            deployment=deployment,
            chat_intent=routing_intent,
        )

    def _advisor_step(
        self,
        question: str,
        history: list[dict[str, Any]],
        evidence_pack: EvidencePack,
        analyst_artifact: str,
        user_context: str,
        routing_intent: str,
        deployment: Optional[str],
    ) -> str:
        """Final advisor for factual RAG path."""
        style_rules = render_prompt("chat_pipeline/advisor_style_rules.txt")
        route_instruction = render_prompt("chat_pipeline/advisor_factual_route.txt")
        system_prompt = f"{style_rules}\n\n{route_instruction}"
        prompt = render_prompt(
            "chat_pipeline/advisor_factual_user.txt",
            question=question,
            user_context=user_context,
            analyst_artifact=analyst_artifact,
            evidence_pack=evidence_pack.to_prompt_text(),
        )

        message, _ = self._generate_with_optional_metadata(
            prompt=prompt,
            system_prompt=system_prompt,
            history=history,
            max_tokens=self.TOKENS_ADVISOR_FACTUAL,
            temperature=0.4,
            enable_market_price_tool=False,
            deployment=deployment,
            chat_intent=routing_intent,
        )
        return message

    def _advisor_step_from_compressed(
        self,
        question: str,
        history: list[dict[str, Any]],
        user_context: str,
        analyst_artifact: str,
        compressed_pack: dict[str, Any],
        routing_intent: str,
        deployment: Optional[str],
    ) -> str:
        """Final advisor for analytical routes."""
        route_instruction = render_prompt("chat_pipeline/advisor_analytical_route.txt")
        tool_enabled = False
        if routing_intent == ROUTING_INTENT_ANALYTICAL_WITH_LIVE_PRICE:
            route_instruction = render_prompt(
                "chat_pipeline/advisor_analytical_live_route.txt"
            )
            tool_enabled = True

        style_rules = render_prompt("chat_pipeline/advisor_style_rules.txt")
        style_rules += "\nDo NOT cite live tool data as [n]."
        system_prompt = f"{style_rules}\n\n{route_instruction}"
        prompt = render_prompt(
            "chat_pipeline/advisor_compressed_user.txt",
            question=question,
            user_context=user_context,
            analyst_artifact=analyst_artifact,
            compressed_evidence_pack=self._compressed_pack_to_prompt_text(
                compressed_pack
            ),
        )

        message, _ = self._generate_with_optional_metadata(
            prompt=prompt,
            system_prompt=system_prompt,
            history=history,
            max_tokens=self.TOKENS_ADVISOR_COMPRESSED,
            temperature=0.45,
            enable_market_price_tool=False,
            tool_categories=(
                self._tool_categories_for_intent(routing_intent)
                if tool_enabled
                else None
            ),
            deployment=deployment,
            chat_intent=routing_intent,
        )
        return message

    def _live_price_only_step(
        self,
        question: str,
        history: list[dict[str, Any]],
        user_context: str,
        deployment: Optional[str],
    ) -> str:
        system_prompt = render_prompt("chat_pipeline/live_price_only_system.txt")
        prompt = render_prompt(
            "chat_pipeline/live_price_only_user.txt",
            question=question,
            user_context=user_context,
        )

        message, _ = self._generate_with_optional_metadata(
            prompt=prompt,
            system_prompt=system_prompt,
            history=history,
            max_tokens=self.TOKENS_LIVE_PRICE,
            temperature=0.2,
            enable_market_price_tool=False,
            tool_categories=self._tool_categories_for_intent(
                ROUTING_INTENT_PURE_LIVE_PRICE
            ),
            deployment=deployment,
            chat_intent=ROUTING_INTENT_PURE_LIVE_PRICE,
        )
        return message

    def _draft_portfolio_transaction_step(
        self,
        *,
        question: str,
        history: list[dict[str, Any]],
        user_context: str,
        deployment: Optional[str],
        routing_intent: Optional[str] = None,
    ) -> tuple[str, Optional[dict[str, Any]]]:
        system_prompt = render_prompt("chat_pipeline/portfolio_draft_system.txt")
        prompt = render_prompt(
            "chat_pipeline/portfolio_draft_user.txt",
            question=question,
            user_context=user_context,
        )
        return self._generate_with_optional_metadata(
            prompt=prompt,
            system_prompt=system_prompt,
            history=history,
            max_tokens=self.TOKENS_PORTFOLIO_DRAFT,
            temperature=0.2,
            enable_market_price_tool=False,
            tool_categories=self._tool_categories_for_intent(
                ROUTING_INTENT_PORTFOLIO_TRANSACTION,
                include_portfolio_actions=True,
            ),
            deployment=deployment,
            chat_intent=routing_intent or ROUTING_INTENT_PORTFOLIO_TRANSACTION,
        )

    def run(
        self,
        question: str,
        history: Optional[list[dict[str, Any]]] = None,
        user_notes: Optional[list[dict[str, Any]]] = None,
        user_portfolio: Optional[list[dict[str, Any]]] = None,
        portfolio_totals: Optional[dict[str, Any]] = None,
        debug: bool = False,
    ) -> PipelineResult:
        pipeline_started_at = time.perf_counter()
        stage_timings_ms: dict[str, float] = {}
        history = history or []
        user_notes = user_notes or []
        user_portfolio = user_portfolio or []
        intent = self.intent_detector.detect(
            question,
            user_portfolio=user_portfolio,
            history=history,
        )
        routing_intent = intent.routing_intent
        language = _detect_language(question)
        user_context = self._format_user_context(
            user_notes, user_portfolio, portfolio_totals
        )

        scope_violation = detect_scope_violation(question)
        if scope_violation:
            refusal = build_scope_refusal(language, scope_violation)
            debug_payload = None
            if debug:
                debug_payload = {
                    "routing_intent": routing_intent,
                    "scope_violation": scope_violation,
                    "model_routing": None,
                    "hypotheses": [],
                    "evidence_by_hypothesis": {},
                    "compressed_evidence_pack": None,
                    "analyst_output": "",
                    "guardrail_hits": ["scope_control_refusal"],
                }
            return PipelineResult(message=refusal, sources=[], debug=debug_payload)

        model_routing = self._resolve_model_routing(
            question=question,
            intent=intent,
            user_context=user_context,
        )
        selected_deployment = model_routing.selected_deployment
        stage_deployments = self._resolve_stage_deployments(
            routing_intent=routing_intent,
            selected_deployment=selected_deployment,
        )
        logger.info(
            "Chat routing decision: intent=%s complexity=%s deployment=%s requires_live_tool=%s reason=%s",
            routing_intent,
            model_routing.complexity_label,
            selected_deployment,
            intent.requires_live_price_tool,
            model_routing.reason,
        )
        logger.info(
            "Chat stage deployments: hypothesis=%s compression=%s analyst=%s advisor=%s",
            stage_deployments["hypothesis"],
            stage_deployments["compression"],
            stage_deployments["analyst"],
            stage_deployments["advisor"],
        )

        if (
            routing_intent == ROUTING_INTENT_PORTFOLIO_TRANSACTION
            or self._is_portfolio_add_request(question)
            or self._is_portfolio_add_followup(question, history)
        ):
            draft_started_at = time.perf_counter()
            raw_answer, pending_transaction_draft = (
                self._draft_portfolio_transaction_step(
                    question=question,
                    history=history,
                    user_context=user_context,
                    deployment=selected_deployment,
                    routing_intent=routing_intent,
                )
            )
            stage_timings_ms["draft_ms"] = round(
                (time.perf_counter() - draft_started_at) * 1000, 2
            )
            if not raw_answer:
                raw_answer = (
                    "Не вдалося підготувати чернетку транзакції. Уточніть, будь ласка, тип активу, кількість і валюту."
                    if language == "uk"
                    else "I couldn't prepare a transaction draft. Please provide asset type, amount, and currency."
                )
            final_answer, guardrail_hits, _ = self._apply_guardrails_to_output(
                message=raw_answer,
                routing_intent=ROUTING_INTENT_PORTFOLIO_TRANSACTION,
                language=language,
            )
            final_answer_model, fallback_used = self._final_answer_model_info(
                selected_deployment=selected_deployment
            )
            stage_timings_ms["total_ms"] = round(
                (time.perf_counter() - pipeline_started_at) * 1000, 2
            )
            debug_payload = None
            if debug:
                debug_payload = {
                    "routing_intent": ROUTING_INTENT_PORTFOLIO_TRANSACTION,
                    "detected_routing_intent": routing_intent,
                    "model_routing": model_routing.to_debug_dict(),
                    "hypotheses": [],
                    "evidence_by_hypothesis": {},
                    "compressed_evidence_pack": None,
                    "analyst_output": "",
                    "guardrail_hits": guardrail_hits,
                    "pending_transaction_draft": pending_transaction_draft,
                    "final_answer_model": final_answer_model,
                    "fallback_used": fallback_used,
                    "stage_deployments": stage_deployments,
                    "stage_timings_ms": stage_timings_ms,
                }
            logger.info(
                "Analytical chat pipeline route=%s selected_model=%s final_answer_model=%s fallback_used=%s "
                "draft_ms=%.2f total_ms=%.2f guardrail_hits=%d",
                ROUTING_INTENT_PORTFOLIO_TRANSACTION,
                selected_deployment,
                final_answer_model,
                fallback_used,
                stage_timings_ms.get("draft_ms", 0.0),
                stage_timings_ms.get("total_ms", 0.0),
                len(guardrail_hits),
            )
            return PipelineResult(
                message=final_answer,
                sources=[],
                pending_transaction_draft=pending_transaction_draft,
                debug=debug_payload,
            )

        if routing_intent == ROUTING_INTENT_PURE_LIVE_PRICE:
            live_started_at = time.perf_counter()
            raw_answer = self._live_price_only_step(
                question=question,
                history=history,
                user_context=user_context,
                deployment=selected_deployment,
            ).strip()
            stage_timings_ms["live_price_ms"] = round(
                (time.perf_counter() - live_started_at) * 1000, 2
            )
            final_answer, guardrail_hits, _ = self._apply_guardrails_to_output(
                message=raw_answer,
                routing_intent=routing_intent,
                language=language,
            )
            final_answer_model, fallback_used = self._final_answer_model_info(
                selected_deployment=selected_deployment
            )
            stage_timings_ms["total_ms"] = round(
                (time.perf_counter() - pipeline_started_at) * 1000, 2
            )
            debug_payload = None
            if debug:
                debug_payload = {
                    "routing_intent": routing_intent,
                    "model_routing": model_routing.to_debug_dict(),
                    "hypotheses": [],
                    "evidence_by_hypothesis": {},
                    "compressed_evidence_pack": None,
                    "analyst_output": "",
                    "guardrail_hits": guardrail_hits,
                    "final_answer_model": final_answer_model,
                    "fallback_used": fallback_used,
                    "stage_deployments": stage_deployments,
                    "stage_timings_ms": stage_timings_ms,
                }
            logger.info(
                "Analytical chat pipeline route=%s selected_model=%s final_answer_model=%s fallback_used=%s "
                "live_ms=%.2f total_ms=%.2f cited_sources=%d guardrail_hits=%d",
                routing_intent,
                selected_deployment,
                final_answer_model,
                fallback_used,
                stage_timings_ms.get("live_price_ms", 0.0),
                stage_timings_ms.get("total_ms", 0.0),
                0,
                len(guardrail_hits),
            )
            return PipelineResult(message=final_answer, sources=[], debug=debug_payload)

        if routing_intent == ROUTING_INTENT_FACTUAL_RAG:
            stage1_k = max(
                settings.chat_retrieval_initial_top_k, settings.chat_rerank_top_k
            )
            retrieve_started_at = time.perf_counter()
            stage1_raw = self.retriever.search(question, top_k=stage1_k)
            reranked = self.reranker.rerank(stage1_raw, intent)
            narrowed = reranked[: settings.chat_rerank_top_k]
            evidence_pack = self.synthesizer.synthesize(narrowed)
            stage_timings_ms["retrieve_ms"] = round(
                (time.perf_counter() - retrieve_started_at) * 1000, 2
            )

            if not evidence_pack.sources:
                stage_timings_ms["total_ms"] = round(
                    (time.perf_counter() - pipeline_started_at) * 1000, 2
                )
                return PipelineResult(
                    message=self._insufficient_message(language),
                    sources=[],
                    stage1_candidates=reranked,
                    reranked_candidates=narrowed,
                    evidence_pack=evidence_pack,
                    debug=(
                        {
                            "routing_intent": routing_intent,
                            "model_routing": model_routing.to_debug_dict(),
                            "hypotheses": [],
                            "evidence_by_hypothesis": {},
                            "compressed_evidence_pack": None,
                            "analyst_output": "",
                            "guardrail_hits": [],
                            "stage_deployments": stage_deployments,
                            "stage_timings_ms": stage_timings_ms,
                        }
                        if debug
                        else None
                    ),
                )

            analyst_started_at = time.perf_counter()
            analyst_artifact = self._analyst_step(
                question=question,
                evidence_pack=evidence_pack,
                user_context=user_context,
                deployment=stage_deployments["analyst"],
            )
            stage_timings_ms["analyst_ms"] = round(
                (time.perf_counter() - analyst_started_at) * 1000, 2
            )
            advisor_started_at = time.perf_counter()
            raw_answer = self._advisor_step(
                question=question,
                history=history,
                evidence_pack=evidence_pack,
                analyst_artifact=analyst_artifact,
                user_context=user_context,
                routing_intent=routing_intent,
                deployment=stage_deployments["advisor"],
            ).strip()
            stage_timings_ms["advisor_ms"] = round(
                (time.perf_counter() - advisor_started_at) * 1000, 2
            )
            final_answer, guardrail_hits, clear_sources = (
                self._apply_guardrails_to_output(
                    message=raw_answer,
                    routing_intent=routing_intent,
                    language=language,
                )
            )
            final_answer_model, fallback_used = self._final_answer_model_info(
                selected_deployment=selected_deployment
            )
            stage_timings_ms["total_ms"] = round(
                (time.perf_counter() - pipeline_started_at) * 1000, 2
            )

            cited_indices: list[int] = []
            if not clear_sources:
                cited_indices = self._extract_citation_indices(
                    final_answer, max_index=len(evidence_pack.sources)
                )
            if evidence_pack.sources and not cited_indices and not clear_sources:
                fallback_indices = [
                    source["index"]
                    for source in evidence_pack.sources[
                        : min(3, len(evidence_pack.sources))
                    ]
                ]
                citation_line = " ".join(f"[{idx}]" for idx in fallback_indices)
                label = "Джерела" if language == "uk" else "Sources"
                final_answer = f"{final_answer}\n\n{label}: {citation_line}"
                cited_indices = fallback_indices

            used_sources: list[dict[str, Any]] = []
            if not clear_sources:
                used_sources = self._source_payload_by_indices(
                    evidence_pack.sources, cited_indices
                )
            debug_payload = None
            if debug:
                debug_payload = {
                    "routing_intent": routing_intent,
                    "model_routing": model_routing.to_debug_dict(),
                    "hypotheses": [],
                    "evidence_by_hypothesis": {},
                    "compressed_evidence_pack": None,
                    "analyst_output": analyst_artifact,
                    "guardrail_hits": guardrail_hits,
                    "final_answer_model": final_answer_model,
                    "fallback_used": fallback_used,
                    "stage_deployments": stage_deployments,
                    "stage_timings_ms": stage_timings_ms,
                }
            logger.info(
                "Analytical chat pipeline route=%s selected_model=%s final_answer_model=%s fallback_used=%s "
                "stage1=%d reranked=%d clusters=%d cited_sources=%d "
                "retrieve_ms=%.2f analyst_ms=%.2f advisor_ms=%.2f total_ms=%.2f guardrail_hits=%d",
                routing_intent,
                selected_deployment,
                final_answer_model,
                fallback_used,
                len(stage1_raw),
                len(narrowed),
                len(evidence_pack.clusters),
                len(used_sources),
                stage_timings_ms.get("retrieve_ms", 0.0),
                stage_timings_ms.get("analyst_ms", 0.0),
                stage_timings_ms.get("advisor_ms", 0.0),
                stage_timings_ms.get("total_ms", 0.0),
                len(guardrail_hits),
            )
            return PipelineResult(
                message=final_answer,
                sources=used_sources,
                stage1_candidates=reranked,
                reranked_candidates=narrowed,
                evidence_pack=evidence_pack,
                analyst_artifact=analyst_artifact,
                debug=debug_payload,
            )

        hypothesis_started_at = time.perf_counter()
        hypotheses = self._generate_hypotheses(
            question=question,
            user_context=user_context,
            routing_intent=routing_intent,
            deployment=stage_deployments["hypothesis"],
        )
        stage_timings_ms["hypotheses_ms"] = round(
            (time.perf_counter() - hypothesis_started_at) * 1000, 2
        )
        retrieve_started_at = time.perf_counter()
        evidence_by_hypothesis = self._retrieve_evidence_for_hypotheses(
            hypotheses, intent
        )
        stage_timings_ms["retrieve_ms"] = round(
            (time.perf_counter() - retrieve_started_at) * 1000, 2
        )
        sources, source_lookup = self._build_source_registry_from_hypothesis_evidence(
            evidence_by_hypothesis
        )

        if routing_intent == ROUTING_INTENT_ANALYTICAL_RAG and not sources:
            stage_timings_ms["total_ms"] = round(
                (time.perf_counter() - pipeline_started_at) * 1000, 2
            )
            return PipelineResult(
                message=self._insufficient_message(language),
                sources=[],
                debug=(
                    {
                        "routing_intent": routing_intent,
                        "model_routing": model_routing.to_debug_dict(),
                        "hypotheses": (
                            [hypothesis.__dict__ for hypothesis in hypotheses]
                            if debug
                            else []
                        ),
                        "evidence_by_hypothesis": {},
                        "compressed_evidence_pack": None,
                        "analyst_output": "",
                        "guardrail_hits": [],
                        "stage_deployments": stage_deployments,
                        "stage_timings_ms": stage_timings_ms,
                    }
                    if debug
                    else None
                ),
            )

        compression_started_at = time.perf_counter()
        compressed_pack = self._compress_evidence_pack(
            question=question,
            hypotheses=hypotheses,
            evidence_by_hypothesis=evidence_by_hypothesis,
            source_lookup=source_lookup,
            sources=sources,
            deployment=stage_deployments["compression"],
            routing_intent=routing_intent,
        )
        stage_timings_ms["compression_ms"] = round(
            (time.perf_counter() - compression_started_at) * 1000, 2
        )

        analyst_started_at = time.perf_counter()
        analyst_artifact = self._analyst_step_from_compressed(
            question=question,
            user_context=user_context,
            compressed_pack=compressed_pack,
            routing_intent=routing_intent,
            deployment=stage_deployments["analyst"],
        )
        stage_timings_ms["analyst_ms"] = round(
            (time.perf_counter() - analyst_started_at) * 1000, 2
        )

        advisor_started_at = time.perf_counter()
        raw_answer = self._advisor_step_from_compressed(
            question=question,
            history=history,
            user_context=user_context,
            analyst_artifact=analyst_artifact,
            compressed_pack=compressed_pack,
            routing_intent=routing_intent,
            deployment=stage_deployments["advisor"],
        ).strip()
        stage_timings_ms["advisor_ms"] = round(
            (time.perf_counter() - advisor_started_at) * 1000, 2
        )
        final_answer, guardrail_hits, clear_sources = self._apply_guardrails_to_output(
            message=raw_answer,
            routing_intent=routing_intent,
            language=language,
        )
        final_answer_model, fallback_used = self._final_answer_model_info(
            selected_deployment=selected_deployment
        )
        stage_timings_ms["total_ms"] = round(
            (time.perf_counter() - pipeline_started_at) * 1000, 2
        )

        cited_indices: list[int] = []
        if not clear_sources:
            cited_indices = self._extract_citation_indices(
                final_answer, max_index=len(sources)
            )
        if (
            routing_intent == ROUTING_INTENT_ANALYTICAL_RAG
            and sources
            and not cited_indices
            and not clear_sources
        ):
            fallback_indices = [
                source["index"] for source in sources[: min(3, len(sources))]
            ]
            label = "Джерела" if language == "uk" else "Sources"
            final_answer = f"{final_answer}\n\n{label}: {' '.join(f'[{idx}]' for idx in fallback_indices)}"
            cited_indices = fallback_indices
        used_sources = (
            self._source_payload_by_indices(sources, cited_indices)
            if (sources and not clear_sources)
            else []
        )

        debug_payload = None
        if debug:
            debug_payload = {
                "routing_intent": routing_intent,
                "model_routing": model_routing.to_debug_dict(),
                "hypotheses": [hypothesis.__dict__ for hypothesis in hypotheses],
                "evidence_by_hypothesis": {
                    hypothesis_id: [
                        {
                            "source_index": source_lookup.get(
                                _source_key(item.metadata, item.content)
                            ),
                            "score": round(item.rerank_score, 4),
                            "channel": item.metadata.get("channel", "Unknown"),
                            "date": item.metadata.get("date", "N/A"),
                        }
                        for item in candidates[
                            : self.HYPOTHESIS_SNIPPETS_PER_HYPOTHESIS
                        ]
                    ]
                    for hypothesis_id, candidates in evidence_by_hypothesis.items()
                },
                "compressed_evidence_pack": compressed_pack,
                "analyst_output": analyst_artifact,
                "guardrail_hits": guardrail_hits,
                "final_answer_model": final_answer_model,
                "fallback_used": fallback_used,
                "stage_deployments": stage_deployments,
                "stage_timings_ms": stage_timings_ms,
            }

        logger.info(
            "Analytical chat pipeline route=%s selected_model=%s final_answer_model=%s fallback_used=%s "
            "hypotheses=%d sources=%d cited_sources=%d "
            "hypotheses_ms=%.2f retrieve_ms=%.2f compression_ms=%.2f analyst_ms=%.2f advisor_ms=%.2f total_ms=%.2f "
            "guardrail_hits=%d",
            routing_intent,
            selected_deployment,
            final_answer_model,
            fallback_used,
            len(hypotheses),
            len(sources),
            len(used_sources),
            stage_timings_ms.get("hypotheses_ms", 0.0),
            stage_timings_ms.get("retrieve_ms", 0.0),
            stage_timings_ms.get("compression_ms", 0.0),
            stage_timings_ms.get("analyst_ms", 0.0),
            stage_timings_ms.get("advisor_ms", 0.0),
            stage_timings_ms.get("total_ms", 0.0),
            len(guardrail_hits),
        )

        return PipelineResult(
            message=final_answer,
            sources=used_sources,
            analyst_artifact=analyst_artifact,
            debug=debug_payload,
        )
