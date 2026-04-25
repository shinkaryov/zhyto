"""
Chat endpoints.
"""

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator

from src.auth.auth_service import AuthIdentity, get_current_identity
from src.utils import get_logger
from src.utils.config import settings
from src.db.cosmos_client import get_cosmos_client
from src.services import get_market_data_service
from src.services.portfolio_enrichment import enrich_portfolio_assets
from src.rag.retriever import get_retriever
from src.rag.generator import GeneratorError, LLMServiceUnavailableError, get_generator
from src.rag.guardrails import (
    build_scope_refusal,
    detect_scope_violation,
    validate_response_output,
)
from src.rag.model_router import ChatModelRouter
from src.rag.chat_pipeline import (
    AnalyticalChatPipeline,
    QueryIntentDetector,
    ROUTING_INTENT_PORTFOLIO_TRANSACTION,
    ROUTING_INTENT_PURE_LIVE_PRICE,
)
from src.rag.portfolio_transaction_followup import (
    bootstrap_pending_transaction_from_user_message,
    build_confirmation_message,
    complete_pending_draft_from_interpretation,
    detect_price_interpretation_answer,
    is_pending_draft_waiting_price_interpretation,
    is_price_clarification_prompt,
)
from src.api.routes.chat_prompt_builder import (
    build_system_prompt,
    build_user_only_summary,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessage(BaseModel):
    """Chat message model."""

    role: str
    content: str
    sources: Optional[list] = None
    pending_transaction_draft: Optional[dict] = None
    draft_status: Optional[str] = None


class ChatRequest(BaseModel):
    """Chat request model."""

    message: str
    user_id: Optional[str] = None
    history: Optional[list[ChatMessage]] = None
    debug: bool = False

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Message cannot be empty")
        return value.strip()


class ChatResponse(BaseModel):
    """Chat response model."""

    message: str
    sources: list
    pending_transaction_draft: Optional[dict] = None
    debug: Optional[dict] = None


class ChatFinalizeRequest(BaseModel):
    """Finalize chat request."""

    user_id: Optional[str] = None
    history: list[ChatMessage] = Field(default_factory=list)
    language: Optional[str] = "uk"


class ChatFinalizeResponse(BaseModel):
    """Finalize chat response."""

    summary: str
    note: dict


def _detect_message_language(text: str) -> str:
    """Detect message language (Ukrainian vs English) for error/fallback texts."""
    return "uk" if re.search(r"[іїєґІЇЄҐа-яА-Я]", text or "") else "en"


def _build_llm_unavailable_message(language: str, retry_attempts: int) -> str:
    """Build user-facing fallback when LLM API is temporarily unavailable."""
    if language == "uk":
        return "Зараз не можемо обробити ваш запит. Спробуйте пізніше."
    return "We cannot process your request now. Try again later."


def _build_generation_error_message(language: str) -> str:
    """Build user-facing fallback for non-transient generation failures."""
    if language == "uk":
        return (
            "Не вдалося згенерувати відповідь через технічну помилку на стороні AI-сервісу. "
            "Спробуйте, будь ласка, ще раз."
        )
    return (
        "I couldn’t generate a response because of a technical error on the AI service side. "
        "Please try again."
    )


def _detect_transaction_confirmation_action(message: str) -> Optional[str]:
    normalized = " ".join((message or "").strip().lower().split())
    if not normalized:
        return None

    confirm_phrases = {
        "так",
        "yes",
        "ок",
        "ok",
        "confirm",
        "підтверджую",
        "додай",
        "додати",
        "так додай",
        "так, додай",
    }
    cancel_phrases = {
        "ні",
        "no",
        "cancel",
        "скасувати",
        "не додавай",
    }

    if normalized in confirm_phrases:
        return "confirm"
    if normalized in cancel_phrases:
        return "cancel"
    return None


def _extract_latest_pending_transaction_draft(history: list[dict]) -> Optional[dict]:
    for item in reversed(history):
        if str(item.get("role") or "").strip().lower() != "assistant":
            continue
        draft = item.get("pending_transaction_draft")
        if not isinstance(draft, dict):
            continue
        status = str(item.get("draft_status") or "pending").strip().lower()
        if status in {"added", "cancelled"}:
            continue
        return draft
    return None


def _persist_pending_draft(db_client, *, user_id: str, draft: dict) -> dict:
    asset_type = str(draft.get("asset_type") or "").strip()
    amount = draft.get("amount")
    currency = str(draft.get("currency") or "").strip().upper()
    purchase_price = draft.get("purchase_price")
    purchase_date = str(draft.get("purchase_date") or "").strip()
    ticker = str(draft.get("ticker") or "").strip().upper() or None

    if not asset_type:
        raise ValueError("asset_type is required")
    if amount in (None, ""):
        raise ValueError("amount is required")
    if not currency:
        raise ValueError("currency is required")

    asset_types_with_ticker = {
        "Акції (ETF)",
        "Криптовалюта",
        "Фонди нерухомості (Inzhur, REITs)",
    }
    optional_price_asset_types = {"Готівка", "Депозит"}
    if asset_type in asset_types_with_ticker and not ticker:
        raise ValueError("ticker is required for this asset type")
    if asset_type not in optional_price_asset_types and purchase_price in (None, ""):
        raise ValueError("purchase_price is required for this asset type")
    if not purchase_date:
        raise ValueError("purchase_date is required")

    asset_data = {
        "user_id": user_id,
        "asset_type": asset_type,
        "amount": amount,
        "currency": currency,
        "purchase_price": purchase_price,
        "purchase_date": purchase_date,
        "ticker": ticker,
        "notes": draft.get("notes"),
    }
    return db_client.add_portfolio_asset(asset_data)


def _tool_categories_for_intent(routing_intent: str) -> Optional[list[str]]:
    if routing_intent == ROUTING_INTENT_PURE_LIVE_PRICE:
        return ["live_market_tools"]
    if routing_intent == ROUTING_INTENT_PORTFOLIO_TRANSACTION:
        return ["portfolio_action_tools"]
    if routing_intent == "analytical_with_live_price":
        return ["live_market_tools"]
    return None


@router.post("/send", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    current_user: AuthIdentity = Depends(get_current_identity),
):
    """Send a chat message and get a response."""
    try:
        return await run_in_threadpool(_send_message_sync, request, current_user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _send_message_sync(
    request: ChatRequest,
    current_user: AuthIdentity,
) -> ChatResponse:
    """Run blocking chat pipeline in a worker thread."""
    language = _detect_message_language(request.message)
    try:
        db_client = get_cosmos_client()
        user_notes = db_client.get_user_notes(current_user.user_id)
        user_portfolio_raw = db_client.get_user_portfolio(current_user.user_id)
        market_data_service = get_market_data_service()
        user_portfolio, portfolio_totals, _, _ = enrich_portfolio_assets(
            user_portfolio_raw,
            market_data_service,
            logger=logger,
        )

        retriever = get_retriever()
        generator = get_generator()
        history = (
            [msg.model_dump(exclude_none=True) for msg in request.history]
            if request.history
            else []
        )
        pending_draft = _extract_latest_pending_transaction_draft(history)

        draft_action = _detect_transaction_confirmation_action(request.message)
        if pending_draft and draft_action == "confirm":
            try:
                saved_asset = _persist_pending_draft(
                    db_client,
                    user_id=current_user.user_id,
                    draft=pending_draft,
                )
            except Exception as exc:
                logger.error(
                    "Failed to persist confirmed transaction draft: %s",
                    exc,
                    exc_info=True,
                )
                message = (
                    "Не вдалося додати актив з цієї чернетки. Перевірте дані та спробуйте ще раз."
                    if language == "uk"
                    else "Couldn't add this draft to portfolio. Please verify details and try again."
                )
                return ChatResponse(
                    message=message, sources=[], pending_transaction_draft=None
                )
            ticker_suffix = (
                f" ({saved_asset.get('ticker')})" if saved_asset.get("ticker") else ""
            )
            message = (
                f"Готово. Актив{ticker_suffix} додано в портфель."
                if language == "uk"
                else f"Done. Asset{ticker_suffix} was added to your portfolio."
            )
            return ChatResponse(
                message=message, sources=[], pending_transaction_draft=None
            )

        if pending_draft and draft_action == "cancel":
            message = (
                "Гаразд, чернетку транзакції скасовано."
                if language == "uk"
                else "Understood. The transaction draft has been cancelled."
            )
            return ChatResponse(
                message=message, sources=[], pending_transaction_draft=None
            )

        # Multi-turn transaction memory: resolve short clarification answers (e.g. "тотал", "за акцію")
        # before normal intent detection to avoid accidental fallback into factual/analytical routes.
        if pending_draft and is_pending_draft_waiting_price_interpretation(
            pending_draft
        ):
            interpretation = detect_price_interpretation_answer(request.message)
            if interpretation:
                completed_draft = complete_pending_draft_from_interpretation(
                    pending_draft,
                    interpretation,
                )
                if completed_draft:
                    confirmation = build_confirmation_message(
                        completed_draft, language=language
                    )
                    return ChatResponse(
                        message=confirmation,
                        sources=[],
                        pending_transaction_draft=completed_draft,
                    )

        intent_detector = QueryIntentDetector()
        intent = intent_detector.detect(
            request.message,
            user_portfolio=user_portfolio,
            history=history,
        )
        routing_intent = intent.routing_intent

        if settings.chat_analytical_pipeline_enabled:
            pipeline = AnalyticalChatPipeline(retriever=retriever, generator=generator)
            result = pipeline.run(
                question=request.message,
                history=history,
                user_notes=user_notes,
                user_portfolio=user_portfolio,
                portfolio_totals=portfolio_totals,
                debug=request.debug,
            )
            pending_from_result = result.pending_transaction_draft
            # If the assistant asked for total-vs-per-unit clarification without tool call,
            # persist a lightweight pending transaction draft in chat state.
            if (
                routing_intent == ROUTING_INTENT_PORTFOLIO_TRANSACTION
                and not isinstance(pending_from_result, dict)
                and is_price_clarification_prompt(result.message)
            ):
                pending_from_result = bootstrap_pending_transaction_from_user_message(
                    request.message
                )
            return ChatResponse(
                message=result.message,
                sources=result.sources,
                pending_transaction_draft=pending_from_result,
                debug=result.debug if request.debug else None,
            )

        scope_violation = detect_scope_violation(request.message)
        if scope_violation:
            refusal = build_scope_refusal(language, scope_violation)
            debug_payload = None
            if request.debug:
                debug_payload = {
                    "routing_intent": routing_intent,
                    "scope_violation": scope_violation,
                }
            return ChatResponse(message=refusal, sources=[], debug=debug_payload)

        model_router = ChatModelRouter()
        model_routing = model_router.route(
            question=request.message,
            routing_intent=routing_intent,
            has_portfolio_context=bool(user_portfolio),
            requires_live_price_tool=intent.requires_live_price_tool,
        )
        selected_tool_categories = _tool_categories_for_intent(routing_intent)

        # Search for relevant context only when route needs RAG.
        search_results = []
        if routing_intent not in {
            ROUTING_INTENT_PURE_LIVE_PRICE,
            ROUTING_INTENT_PORTFOLIO_TRANSACTION,
        }:
            search_results = retriever.search(request.message, top_k=5)

        # Build system prompt
        system_prompt = build_system_prompt(
            search_results,
            user_notes,
            user_portfolio,
            portfolio_totals=portfolio_totals,
            routing_intent=routing_intent,
        )

        # Generate response
        if hasattr(generator, "generate_structured"):
            generated = generator.generate_structured(
                prompt=request.message,
                system_prompt=system_prompt,
                history=history,
                max_tokens=2000,
                temperature=0.7,
                enable_market_price_tool=False,
                tool_categories=selected_tool_categories,
                deployment=model_routing.selected_deployment,
                chat_intent=routing_intent,
            )
            response = str(generated.get("message") or "")
            pending_transaction_draft = generated.get("pending_transaction_draft")
            if not isinstance(pending_transaction_draft, dict):
                pending_transaction_draft = None
        else:
            response = generator.generate(
                prompt=request.message,
                system_prompt=system_prompt,
                history=history,
                max_tokens=2000,
                temperature=0.7,
                enable_market_price_tool=False,
                tool_categories=selected_tool_categories,
                deployment=model_routing.selected_deployment,
                chat_intent=routing_intent,
            )
            pending_transaction_draft = None

        if (
            routing_intent == ROUTING_INTENT_PORTFOLIO_TRANSACTION
            and pending_transaction_draft is None
            and is_price_clarification_prompt(response)
        ):
            pending_transaction_draft = bootstrap_pending_transaction_from_user_message(
                request.message
            )
        validation = validate_response_output(
            message=response,
            routing_intent=routing_intent,
            language=language,
        )
        response = validation.message

        # Extract sources cited in response
        used_sources = []
        if (
            search_results
            and routing_intent
            not in {
                ROUTING_INTENT_PURE_LIVE_PRICE,
                ROUTING_INTENT_PORTFOLIO_TRANSACTION,
            }
            and not validation.clear_sources
        ):

            cited_indices_str = re.findall(r"\[(\d+)]", response)
            cited_indices = set(int(idx) for idx in cited_indices_str)

            for i, result in enumerate(search_results, 1):
                if i in cited_indices:
                    metadata = result.get("metadata", {})
                    used_sources.append(
                        {
                            "index": i,
                            "channel": metadata.get("channel", "Unknown"),
                            "url": metadata.get("url", "N/A"),
                            "date": metadata.get("date", "N/A"),
                        }
                    )

        debug_payload = None
        if request.debug:
            debug_payload = {
                "routing_intent": routing_intent,
                "model_routing": model_routing.to_debug_dict(),
                "guardrail_hits": validation.triggered_rules,
            }
        return ChatResponse(
            message=response,
            sources=used_sources,
            pending_transaction_draft=pending_transaction_draft,
            debug=debug_payload,
        )
    except LLMServiceUnavailableError as exc:
        logger.error("LLM service unavailable after retries: %s", exc, exc_info=True)
        debug_payload = None
        if request.debug:
            debug_payload = {
                "error_type": "llm_service_unavailable",
                "retry_attempts": exc.attempts,
                "operation": exc.operation,
                "deployment": exc.deployment,
                "last_error": str(exc.last_error),
            }
        return ChatResponse(
            message=_build_llm_unavailable_message(
                language, retry_attempts=exc.attempts
            ),
            sources=[],
            pending_transaction_draft=None,
            debug=debug_payload,
        )
    except GeneratorError as exc:
        logger.error("Chat generation failed: %s", exc, exc_info=True)
        debug_payload = None
        if request.debug:
            debug_payload = {
                "error_type": "generation_error",
                "error": str(exc),
            }
        return ChatResponse(
            message=_build_generation_error_message(language),
            sources=[],
            pending_transaction_draft=None,
            debug=debug_payload,
        )
    except Exception as e:
        logger.error(f"Chat pipeline failed: {e}", exc_info=True)
        raise


@router.post("/finalize", response_model=ChatFinalizeResponse)
async def finalize_chat(
    request: ChatFinalizeRequest,
    current_user: AuthIdentity = Depends(get_current_identity),
):
    """Finalize current chat and save a user-input-oriented summary as note."""
    try:
        return await run_in_threadpool(_finalize_chat_sync, request, current_user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Finalize chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _finalize_chat_sync(
    request: ChatFinalizeRequest,
    current_user: AuthIdentity,
) -> ChatFinalizeResponse:
    """Sync finalize pipeline for threadpool execution."""
    user_messages = [
        msg.content.strip()
        for msg in request.history
        if msg.role == "user" and msg.content and msg.content.strip()
    ]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user messages to summarize")

    lang = request.language if request.language in {"uk", "en"} else "uk"
    summary = build_user_only_summary(user_messages, lang)

    db_client = get_cosmos_client()
    note = db_client.add_note(
        {
            "user_id": current_user.user_id,
            "content": summary,
        }
    )

    return ChatFinalizeResponse(summary=summary, note=note)
