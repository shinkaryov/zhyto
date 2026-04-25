"""Prompt builders for chat route orchestration."""

from __future__ import annotations

from typing import Optional

from src.rag.chat_pipeline import (
    ROUTING_INTENT_ANALYTICAL_RAG,
    ROUTING_INTENT_ANALYTICAL_WITH_LIVE_PRICE,
    ROUTING_INTENT_FACTUAL_RAG,
    ROUTING_INTENT_PORTFOLIO_TRANSACTION,
    ROUTING_INTENT_PURE_LIVE_PRICE,
)
from src.rag.generator import get_generator
from src.rag.prompt_loader import render_prompt
from src.services.portfolio_context_formatter import build_enriched_portfolio_context
from src.utils.logger import get_logger

logger = get_logger(__name__)


def build_system_prompt(
    search_results,
    user_notes,
    user_portfolio,
    portfolio_totals=None,
    routing_intent: str = ROUTING_INTENT_FACTUAL_RAG,
):
    """Build route-aware system prompt from context."""
    system_prompt = render_prompt("chat_route/system_base.txt")

    if routing_intent == ROUTING_INTENT_PURE_LIVE_PRICE:
        system_prompt += "\n\n" + render_prompt("chat_route/mode_pure_live.txt")
    elif routing_intent == ROUTING_INTENT_ANALYTICAL_WITH_LIVE_PRICE:
        system_prompt += "\n\n" + render_prompt("chat_route/mode_analytical_live.txt")
    elif routing_intent == ROUTING_INTENT_PORTFOLIO_TRANSACTION:
        system_prompt += "\n\n" + render_prompt("chat_route/mode_generic.txt", mode_label="PORTFOLIO_TRANSACTION")
    else:
        mode_label = "ANALYTICAL_RAG" if routing_intent == ROUTING_INTENT_ANALYTICAL_RAG else "FACTUAL_RAG"
        system_prompt += "\n\n" + render_prompt("chat_route/mode_generic.txt", mode_label=mode_label)

    if user_portfolio or user_notes:
        system_prompt += "\n\n--- ПЕРСОНАЛЬНИЙ КОНТЕКСТ КОРИСТУВАЧА ---\n"
        if user_portfolio:
            system_prompt += (
                build_enriched_portfolio_context(
                    user_portfolio,
                    marker="Поточний портфель активів",
                    empty_message="Портфель не заповнений.",
                )
                + "\n"
            )
        if user_notes:
            system_prompt += "\nНотатки (цілі, преференції, стратегія):\n"
            for note in user_notes:
                system_prompt += f"- {note.get('content')}\n"
        system_prompt += "\nІнструкція: Використовуй ці дані як базову точку відліку при відповідях.\n"

    if search_results:
        system_prompt += "\n--- БАЗА ЗНАНЬ (РИНКОВИЙ КОНТЕКСТ) ---\n"
        for i, result in enumerate(search_results, 1):
            content = result.get("content", "")
            metadata = result.get("metadata", {})
            channel = metadata.get("channel", "Unknown")
            content_preview = content[:1500] + "..." if len(content) > 1500 else content
            system_prompt += f"[Джерело {i} - {channel}]:\n{content_preview}\n\n"

    if routing_intent == ROUTING_INTENT_PURE_LIVE_PRICE:
        system_prompt += render_prompt("chat_route/rules_pure_live.txt")
    elif routing_intent == ROUTING_INTENT_ANALYTICAL_WITH_LIVE_PRICE:
        system_prompt += render_prompt("chat_route/rules_analytical_live.txt")
    elif routing_intent == ROUTING_INTENT_PORTFOLIO_TRANSACTION:
        system_prompt += render_prompt("chat_route/rules_factual_rag.txt")
    else:
        if routing_intent == ROUTING_INTENT_ANALYTICAL_RAG:
            system_prompt += render_prompt("chat_route/rules_analytical_rag.txt")
        else:
            system_prompt += render_prompt("chat_route/rules_factual_rag.txt")

    return system_prompt


def build_user_only_summary(user_messages: list[str], language: str) -> str:
    """Create summary using only user messages, never assistant messages."""
    compact_messages = [msg.strip() for msg in user_messages if msg and msg.strip()]
    if not compact_messages:
        raise ValueError("No user messages to summarize")

    clipped = compact_messages[-12:]
    prompt_payload = "\n".join(f"{idx + 1}. {message}" for idx, message in enumerate(clipped))
    summary_language = "English" if language == "en" else "Ukrainian"
    system_prompt = render_prompt("chat_route/summary_system.txt", summary_language=summary_language)

    try:
        generator = get_generator()
        summary = generator.generate(
            prompt=f"User messages:\n{prompt_payload}",
            system_prompt=system_prompt,
            max_tokens=260,
            temperature=0.2,
        )
        cleaned = summary.strip()
        if cleaned:
            return cleaned
    except Exception:
        logger.warning("Summary generation fallback activated", exc_info=True)

    joined = " ".join(clipped)
    fallback = joined[:900].strip()
    return fallback if fallback else clipped[-1]
