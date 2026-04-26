"""Unit tests for analytical chat pipeline components."""

from datetime import datetime, timezone

from src.rag.chat_pipeline import (
    AnalyticalChatPipeline,
    DeterministicReranker,
    EvidenceSynthesizer,
    QueryIntentDetector,
    ROUTING_INTENT_ANALYTICAL_RAG,
    ROUTING_INTENT_ANALYTICAL_WITH_LIVE_PRICE,
    ROUTING_INTENT_FACTUAL_RAG,
    ROUTING_INTENT_PORTFOLIO_TRANSACTION,
    ROUTING_INTENT_PURE_LIVE_PRICE,
    ScoredChunk,
)
from src.rag.model_router import ChatModelRouter


class DummyRetriever:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def search(self, query: str, top_k: int = 5):
        self.calls.append((query, top_k))
        return self.results[:top_k]


class DummyGenerator:
    def __init__(self):
        self.calls = []

    def generate(self, prompt: str, system_prompt: str | None = None, **kwargs):
        self.calls.append(
            {"prompt": prompt, "system_prompt": system_prompt, "kwargs": kwargs}
        )
        normalized_system = (system_prompt or "").lower()

        if "senior financial research analyst" in normalized_system:
            return (
                "Key Facts: OVDP yields are under pressure [1].\n"
                "Signals: refinancing concerns are elevated [2]."
            )
        if "routing mode: pure_live_price" in normalized_system:
            return "Apple (AAPL) зараз коштує $273.43 за акцію."
        if "routing mode: analytical_with_live_price" in normalized_system:
            return "Apple (AAPL) зараз коштує $273.43. Рух пов'язаний із короткостроковою волатильністю [1]."

        return "Main risk for OVDP holders is refinancing pressure [2]."


class UnsafeAdvisorGenerator(DummyGenerator):
    def generate(self, prompt: str, system_prompt: str | None = None, **kwargs):
        self.calls.append(
            {"prompt": prompt, "system_prompt": system_prompt, "kwargs": kwargs}
        )
        normalized_system = (system_prompt or "").lower()
        if "senior financial research analyst" in normalized_system:
            return "Key Facts: OVDP market context [1]."
        if "routing mode: factual_rag" in normalized_system:
            return "Купуй AAPL на всі гроші — гарантовано виросте."
        return super().generate(prompt, system_prompt=system_prompt, **kwargs)


class TestModelRouter:
    def test_routes_pure_live_price_to_default_deployment(self):
        router = ChatModelRouter(
            enabled=True,
            default_deployment="mini-deploy",
            advanced_deployment="pro-deploy",
        )
        decision = router.route(
            question="Скільки коштує AAPL зараз?",
            routing_intent=ROUTING_INTENT_PURE_LIVE_PRICE,
            requires_live_price_tool=True,
        )

        assert decision.selected_deployment == "mini-deploy"
        assert decision.complexity_label == "simple"

    def test_routes_analytical_queries_to_advanced_deployment(self):
        router = ChatModelRouter(
            enabled=True,
            default_deployment="mini-deploy",
            advanced_deployment="pro-deploy",
        )
        decision = router.route(
            question="Проаналізуй мій портфель і ризики",
            routing_intent=ROUTING_INTENT_ANALYTICAL_RAG,
        )

        assert decision.selected_deployment == "pro-deploy"
        assert decision.complexity_label == "complex"

    def test_routes_portfolio_transaction_to_default_deployment(self):
        router = ChatModelRouter(
            enabled=True,
            default_deployment="mini-deploy",
            advanced_deployment="pro-deploy",
        )
        decision = router.route(
            question="Вчора купив 20 акцій TSLA за 4000 доларів",
            routing_intent=ROUTING_INTENT_PORTFOLIO_TRANSACTION,
        )
        assert decision.selected_deployment == "mini-deploy"
        assert decision.complexity_label == "simple"

    def test_factual_rag_broad_query_stays_on_default_deployment(self):
        router = ChatModelRouter(
            enabled=True,
            default_deployment="mini-deploy",
            advanced_deployment="pro-deploy",
        )
        decision = router.route(
            question=(
                "Explain tax nuances for a Ukrainian investor across OVDP, ETFs, "
                "stocks, crypto, real estate, deposits, and bonds, and include "
                "differences for short-term and long-term holding periods."
            ),
            routing_intent=ROUTING_INTENT_FACTUAL_RAG,
        )
        assert decision.selected_deployment == "mini-deploy"
        assert decision.complexity_label == "moderate"
        assert "latency and stability" in decision.reason.lower()

    def test_factual_rag_high_stakes_stays_on_default_deployment(self):
        router = ChatModelRouter(
            enabled=True,
            default_deployment="mini-deploy",
            advanced_deployment="pro-deploy",
        )
        decision = router.route(
            question="Should I put all money into OVDP right now?",
            routing_intent=ROUTING_INTENT_FACTUAL_RAG,
        )
        assert decision.selected_deployment == "mini-deploy"
        assert decision.complexity_label == "complex"
        assert "latency and stability" in decision.reason.lower()


class TestIntentDetector:
    def test_detects_domain_channel_and_analysis_intent(self):
        detector = QueryIntentDetector()
        intent = detector.detect(
            "What narrative is forming across Telegram and YouTube on OVDP risks now?"
        )

        assert intent.is_analytical is True
        assert intent.is_time_sensitive is True
        assert "telegram" in intent.matched_channels
        assert "youtube" in intent.matched_channels
        assert any(
            "bond" in domain or "ovdp" in domain for domain in intent.matched_domains
        )

    def test_detects_chat_routing_modes(self):
        detector = QueryIntentDetector()

        pure_live = detector.detect("Скільки коштують акції AAPL зараз?")
        assert pure_live.routing_intent == ROUTING_INTENT_PURE_LIVE_PRICE
        assert pure_live.requires_live_price_tool is True

        live_plus_analysis = detector.detect("Що сьогодні з AAPL і чому він падає?")
        assert (
            live_plus_analysis.routing_intent
            == ROUTING_INTENT_ANALYTICAL_WITH_LIVE_PRICE
        )
        assert live_plus_analysis.requires_live_price_tool is True

        my_btc_live = detector.detect(
            "Що там сьогодні з моїм Bitcoin?",
            user_portfolio=[{"asset_type": "Криптовалюта", "ticker": "BTC"}],
        )
        assert my_btc_live.routing_intent == ROUTING_INTENT_PURE_LIVE_PRICE
        assert my_btc_live.requires_live_price_tool is True

        rag_only = detector.detect("Які зараз податки на ОВДП?")
        assert rag_only.routing_intent == ROUTING_INTENT_FACTUAL_RAG
        assert rag_only.requires_live_price_tool is False

        analytical_rag = detector.detect("Які головні ризики для ОВДП зараз?")
        assert analytical_rag.routing_intent == ROUTING_INTENT_ANALYTICAL_RAG
        assert analytical_rag.requires_live_price_tool is False

    def test_transaction_statement_does_not_route_to_analytical_by_default(self):
        detector = QueryIntentDetector()
        intent = detector.detect("вчора взяв 4 акції MSFT за 1600 баксів")
        assert intent.routing_intent == ROUTING_INTENT_PORTFOLIO_TRANSACTION
        assert intent.requires_live_price_tool is False

    def test_transaction_clarification_followup_stays_in_transaction_intent(self):
        detector = QueryIntentDetector()
        history = [
            {"role": "user", "content": "Вчора купив 20 акцій TSLA за 4000 доларів"},
            {
                "role": "assistant",
                "content": "4000 доларів — це загальна сума угоди чи ціна за 1 акцію?",
            },
        ]
        intent = detector.detect("Загальна", history=history)
        assert intent.routing_intent == ROUTING_INTENT_PORTFOLIO_TRANSACTION
        assert intent.requires_live_price_tool is False

    def test_transaction_clarification_followup_total_alias_stays_in_transaction_intent(
        self,
    ):
        detector = QueryIntentDetector()
        history = [
            {"role": "user", "content": "Вчора купив 20 акцій TSLA за 4000 доларів"},
            {
                "role": "assistant",
                "content": "4000 доларів — це загальна сума угоди чи ціна за 1 акцію?",
            },
        ]
        intent = detector.detect("тотал", history=history)
        assert intent.routing_intent == ROUTING_INTENT_PORTFOLIO_TRANSACTION
        assert intent.requires_live_price_tool is False

    def test_transaction_analysis_question_routes_to_analytical(self):
        detector = QueryIntentDetector()
        intent = detector.detect("Що думаєш про мою покупку TSLA?")
        assert intent.routing_intent in {
            ROUTING_INTENT_ANALYTICAL_RAG,
            ROUTING_INTENT_ANALYTICAL_WITH_LIVE_PRICE,
        }


class TestDeterministicReranker:
    def test_boosts_recent_trusted_domain_match(self):
        fixed_now = datetime(2026, 4, 23, tzinfo=timezone.utc)

        reranker = DeterministicReranker(
            similarity_weight=0.4,
            trust_weight=0.2,
            freshness_weight=0.3,
            domain_weight=0.1,
            freshness_half_life_days=10,
            now_provider=lambda: fixed_now,
        )

        intent = QueryIntentDetector().detect(
            "What changed in tax discussion recently?"
        )

        results = [
            {
                "content": "Older broad note",
                "metadata": {
                    "domain": "macro_global",
                    "channel": "GeneralNews",
                    "date": "2024-01-10",
                    "trust_weight": 0.45,
                },
                "distance": 0.02,
            },
            {
                "content": "Recent trusted tax update",
                "metadata": {
                    "domain": "tax_policy",
                    "channel": "TaxDesk",
                    "date": "2026-04-22T12:00:00+00:00",
                    "trust_weight": 0.95,
                },
                "distance": 0.2,
            },
        ]

        ranked = reranker.rerank(results, intent)

        assert ranked[0].content == "Recent trusted tax update"
        assert (
            ranked[0].score_breakdown["freshness"]
            > ranked[1].score_breakdown["freshness"]
        )
        assert ranked[0].score_breakdown["trust"] > ranked[1].score_breakdown["trust"]


class TestEvidenceSynthesizer:
    def test_deduplicates_near_duplicate_chunks(self):
        synthesizer = EvidenceSynthesizer(max_clusters=5, max_sources=5)

        candidates = [
            ScoredChunk(
                content="OVDP yields moved to 17% after the latest primary auction and demand stayed strong.",
                metadata={
                    "source_id": "doc-1",
                    "channel": "SourceA",
                    "url": "https://a",
                    "date": "2026-04-22",
                },
                distance=0.1,
                retrieval_score=0.8,
                rerank_score=0.9,
            ),
            ScoredChunk(
                content="OVDP yields moved to 17% after the latest primary auction and demand stayed strong.",
                metadata={
                    "source_id": "doc-1",
                    "channel": "SourceA",
                    "url": "https://a",
                    "date": "2026-04-22",
                },
                distance=0.11,
                retrieval_score=0.79,
                rerank_score=0.88,
            ),
            ScoredChunk(
                content="Analysts now flag refinancing risk for the 2027 maturity bucket as a key downside.",
                metadata={
                    "source_id": "doc-2",
                    "channel": "SourceB",
                    "url": "https://b",
                    "date": "2026-04-21",
                },
                distance=0.2,
                retrieval_score=0.7,
                rerank_score=0.84,
            ),
        ]

        deduped = synthesizer.deduplicate_candidates(candidates)

        assert len(deduped) == 2


class TestAnalyticalChatPipeline:
    def test_transaction_override_routes_to_draft_flow(self):
        retriever = DummyRetriever([])
        generator = DummyGenerator()
        pipeline = AnalyticalChatPipeline(
            retriever=retriever,
            generator=generator,
        )
        pipeline.model_router = ChatModelRouter(
            enabled=True,
            default_deployment="mini-deploy",
            advanced_deployment="pro-deploy",
        )

        result = pipeline.run(question="вчора взяв 4 акції MSFT за 1600 баксів")

        assert result.sources == []
        assert retriever.calls == []
        assert len(generator.calls) == 1
        assert (
            "portfolio transaction drafting assistant"
            in (generator.calls[0]["system_prompt"] or "").lower()
        )
        assert generator.calls[0]["kwargs"].get("tool_categories") == [
            "portfolio_action_tools"
        ]
        assert generator.calls[0]["kwargs"].get("deployment") == "mini-deploy"

    def test_transaction_clarification_followup_routes_back_to_draft_flow(self):
        retriever = DummyRetriever([])
        generator = DummyGenerator()
        pipeline = AnalyticalChatPipeline(
            retriever=retriever,
            generator=generator,
        )

        history = [
            {"role": "user", "content": "вчора взяв 4 акції MSFT за 1600 баксів"},
            {
                "role": "assistant",
                "content": "Уточніть, будь ласка: 1600 USD — це загальна сума угоди чи ціна за одиницю?",
            },
        ]

        result = pipeline.run(
            question="Total",
            history=history,
        )

        assert result.sources == []
        assert retriever.calls == []
        assert len(generator.calls) == 1
        assert (
            "portfolio transaction drafting assistant"
            in (generator.calls[0]["system_prompt"] or "").lower()
        )
        assert generator.calls[0]["kwargs"].get("tool_categories") == [
            "portfolio_action_tools"
        ]

    def test_scope_control_refuses_unrelated_requests(self):
        retriever = DummyRetriever([])
        generator = DummyGenerator()
        pipeline = AnalyticalChatPipeline(
            retriever=retriever,
            generator=generator,
        )

        result = pipeline.run(question="Write me code for a Python scraper")

        assert (
            "інвестиці" in result.message.lower() or "invest" in result.message.lower()
        )
        assert result.sources == []
        assert retriever.calls == []
        assert generator.calls == []

    def test_pure_live_price_bypasses_retrieval_and_sources(self):
        raw_results = [
            {
                "content": "Irrelevant macro summary that should not be used.",
                "metadata": {
                    "source_id": "s1",
                    "channel": "Noise",
                    "url": "https://noise",
                    "date": "2026-04-23",
                    "domain": "macro_global",
                    "trust_weight": 0.4,
                },
                "distance": 0.15,
            }
        ]

        retriever = DummyRetriever(raw_results)
        generator = DummyGenerator()
        pipeline = AnalyticalChatPipeline(
            retriever=retriever,
            generator=generator,
        )
        pipeline.model_router = ChatModelRouter(
            enabled=True,
            default_deployment="mini-deploy",
            advanced_deployment="pro-deploy",
        )

        result = pipeline.run(
            question="Яка зараз ціна DUOL?",
            user_portfolio=[{"asset_type": "Акції (ETF)", "ticker": "DUOL"}],
        )

        assert result.message == "Apple (AAPL) зараз коштує $273.43 за акцію."
        assert result.sources == []
        assert retriever.calls == []
        assert len(generator.calls) == 1
        assert generator.calls[0]["kwargs"].get("enable_market_price_tool") is False
        assert generator.calls[0]["kwargs"].get("tool_categories") == [
            "live_market_tools"
        ]
        assert generator.calls[0]["kwargs"].get("deployment") == "mini-deploy"
        assert (
            generator.calls[0]["kwargs"].get("max_tokens") == pipeline.TOKENS_LIVE_PRICE
        )
        assert generator.calls[0]["kwargs"].get("max_tokens") <= 300

    def test_analytical_rag_stage_split_uses_advanced_only_for_advisor(self):
        retriever = DummyRetriever(
            [
                {
                    "content": "OVDP demand remains stable according to primary market updates.",
                    "metadata": {
                        "source_id": "s1",
                        "channel": "NewsA",
                        "url": "https://source-a",
                        "date": "2026-04-22",
                        "domain": "fixed_income",
                        "trust_weight": 0.9,
                    },
                    "distance": 0.1,
                }
            ]
        )
        generator = DummyGenerator()
        pipeline = AnalyticalChatPipeline(
            retriever=retriever,
            generator=generator,
        )
        pipeline.model_router = ChatModelRouter(
            enabled=True,
            default_deployment="mini-deploy",
            advanced_deployment="pro-deploy",
        )

        result = pipeline.run(
            question="Проаналізуй ризики мого портфеля на 2 роки",
            debug=True,
        )

        assert result.debug is not None
        assert result.debug["stage_deployments"] == {
            "hypothesis": "mini-deploy",
            "compression": "mini-deploy",
            "analyst": "mini-deploy",
            "advisor": "pro-deploy",
        }
        advisor_call = next(
            (
                item
                for item in generator.calls
                if item["kwargs"].get("deployment") == "pro-deploy"
                and item["kwargs"].get("chat_intent") == ROUTING_INTENT_ANALYTICAL_RAG
            ),
            None,
        )
        assert advisor_call is not None
        assert advisor_call["kwargs"].get("max_tokens") >= 1400

    def test_returns_only_cited_sources(self):
        raw_results = [
            {
                "content": "OVDP demand remains stable according to primary market updates.",
                "metadata": {
                    "source_id": "s1",
                    "channel": "NewsA",
                    "url": "https://source-a",
                    "date": "2026-04-22",
                    "domain": "fixed_income",
                    "trust_weight": 0.9,
                },
                "distance": 0.1,
            },
            {
                "content": "Refinancing pressure for 2027 maturities is rising in dealer commentary.",
                "metadata": {
                    "source_id": "s2",
                    "channel": "NewsB",
                    "url": "https://source-b",
                    "date": "2026-04-23",
                    "domain": "fixed_income",
                    "trust_weight": 0.92,
                },
                "distance": 0.12,
            },
        ]

        pipeline = AnalyticalChatPipeline(
            retriever=DummyRetriever(raw_results),
            generator=DummyGenerator(),
        )

        result = pipeline.run(question="What are the main OVDP risks right now?")

        assert "[2]" in result.message
        assert len(result.sources) == 1
        assert result.sources[0]["index"] == 2
        assert result.sources[0]["url"] == "https://source-b"

    def test_advisor_prompt_contains_strict_style_rules(self):
        raw_results = [
            {
                "content": "Macro signal one.",
                "metadata": {
                    "source_id": "s1",
                    "channel": "NewsA",
                    "url": "https://source-a",
                    "date": "2026-04-22",
                    "domain": "macro_global",
                    "trust_weight": 0.9,
                },
                "distance": 0.1,
            },
            {
                "content": "Macro signal two.",
                "metadata": {
                    "source_id": "s2",
                    "channel": "NewsB",
                    "url": "https://source-b",
                    "date": "2026-04-23",
                    "domain": "macro_global",
                    "trust_weight": 0.92,
                },
                "distance": 0.12,
            },
        ]

        generator = DummyGenerator()
        pipeline = AnalyticalChatPipeline(
            retriever=DummyRetriever(raw_results),
            generator=generator,
        )

        _ = pipeline.run(question="Як макро новини впливають на портфель?")

        advisor_call = generator.calls[-1]
        advisor_system_prompt = advisor_call["system_prompt"]

        assert (
            "You MUST answer in the EXACT SAME LANGUAGE the user used in their prompt."
            in advisor_system_prompt
        )
        assert "ROUTING MODE: ANALYTICAL_RAG." in advisor_system_prompt
        assert "THE PERSONA:" in advisor_system_prompt
        assert "MELT THE STRUCTURE (CRITICAL):" in advisor_system_prompt
        assert (
            "NEVER use bullet points (-) or numbered lists (1., 2.)."
            in advisor_system_prompt
        )
        assert "Never offer further assistance." in advisor_system_prompt
        assert (
            "Format your response as 2 to 4 short, punchy paragraphs"
            in advisor_system_prompt
        )
        assert "Do NOT cite live tool data as [n]." in advisor_system_prompt
        assert (
            "Use [n] citations only for KB-backed factual claims."
            in advisor_system_prompt
        )

    def test_guardrail_patches_unsafe_all_in_advice(self):
        raw_results = [
            {
                "content": "OVDP tax context for resident investors.",
                "metadata": {
                    "source_id": "s1",
                    "channel": "TaxDesk",
                    "url": "https://source-tax",
                    "date": "2026-04-22",
                    "domain": "tax_policy",
                    "trust_weight": 0.95,
                },
                "distance": 0.1,
            }
        ]

        pipeline = AnalyticalChatPipeline(
            retriever=DummyRetriever(raw_results),
            generator=UnsafeAdvisorGenerator(),
        )

        result = pipeline.run(question="Який податок на ОВДП?")

        assert "не можу давати гарантії" in result.message.lower()
        assert result.sources == []
