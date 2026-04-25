"""Adaptive model routing for chat requests."""

from __future__ import annotations

from dataclasses import dataclass

from src.utils.config import settings

ROUTING_INTENT_PURE_LIVE_PRICE = "pure_live_price"
ROUTING_INTENT_FACTUAL_RAG = "factual_rag"
ROUTING_INTENT_ANALYTICAL_RAG = "analytical_rag"
ROUTING_INTENT_ANALYTICAL_WITH_LIVE_PRICE = "analytical_with_live_price"
ROUTING_INTENT_PORTFOLIO_TRANSACTION = "portfolio_transaction"


@dataclass
class ModelRoutingDecision:
    """Model/deployment choice with rationale."""

    selected_deployment: str
    reason: str
    complexity_label: str

    def to_debug_dict(self) -> dict[str, str]:
        return {
            "selected_model": self.selected_deployment,
            "reason": self.reason,
            "complexity_label": self.complexity_label,
        }


class ChatModelRouter:
    """Lightweight rule-based model router for MVP."""

    COMPLEX_HINTS = [
        "проаналіз",
        "analy",
        "аналіз",
        "порівня",
        "compare",
        "стратег",
        "strategy",
        "ризик",
        "risk",
        "що робити",
        "what should i do",
        "portfolio",
        "портфель",
        "allocation",
        "диверсиф",
        "на 2 рок",
        "2 year",
    ]
    BROAD_OR_HIGH_STAKES_HINTS = [
        "all money",
        "всі гроші",
        "all in",
        "all-in",
        "на все",
        "entire portfolio",
        "весь портфель",
        "max return",
        "максимальн",
        "best strategy",
        "найкраща стратег",
    ]

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        default_deployment: str | None = None,
        advanced_deployment: str | None = None,
    ) -> None:
        self.enabled = (
            settings.enable_adaptive_model_routing if enabled is None else bool(enabled)
        )
        self.default_deployment = (
            default_deployment
            or settings.azure_openai_default_deployment
            or settings.azure_openai_deployment_name
            or "gpt-5.4-mini"
        ).strip()
        self.advanced_deployment = (
            advanced_deployment
            or settings.azure_openai_advanced_deployment
            or self.default_deployment
        ).strip()

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join((text or "").strip().lower().split())

    def route(
        self,
        *,
        question: str,
        routing_intent: str,
        has_portfolio_context: bool = False,
        requires_live_price_tool: bool = False,
    ) -> ModelRoutingDecision:
        if not self.enabled:
            return ModelRoutingDecision(
                selected_deployment=self.default_deployment,
                reason="Adaptive model routing is disabled by configuration.",
                complexity_label="simple",
            )

        if routing_intent == ROUTING_INTENT_PURE_LIVE_PRICE or (
            requires_live_price_tool
            and routing_intent != ROUTING_INTENT_ANALYTICAL_WITH_LIVE_PRICE
        ):
            return ModelRoutingDecision(
                selected_deployment=self.default_deployment,
                reason="Pure live-price/tool-first request should stay on the default lightweight deployment.",
                complexity_label="simple",
            )

        if routing_intent == ROUTING_INTENT_PORTFOLIO_TRANSACTION:
            return ModelRoutingDecision(
                selected_deployment=self.default_deployment,
                reason="Portfolio transaction capture is extraction + confirmation and should use the default lightweight deployment.",
                complexity_label="simple",
            )

        if routing_intent in {
            ROUTING_INTENT_ANALYTICAL_RAG,
            ROUTING_INTENT_ANALYTICAL_WITH_LIVE_PRICE,
        }:
            return ModelRoutingDecision(
                selected_deployment=self.advanced_deployment,
                reason="Analytical routing requires hypothesis/evidence synthesis and should use the advanced deployment.",
                complexity_label="complex",
            )

        normalized = self._normalize(question)
        has_complex_language = any(hint in normalized for hint in self.COMPLEX_HINTS)
        high_stakes = any(
            hint in normalized for hint in self.BROAD_OR_HIGH_STAKES_HINTS
        )
        broad_query = (
            normalized.count(" і ") >= 2
            or normalized.count(" and ") >= 2
            or len(normalized.split()) >= 22
        )
        portfolio_decision_support = has_portfolio_context and (
            "портфель" in normalized
            or "portfolio" in normalized
            or "що робити" in normalized
            or "what should" in normalized
        )

        if high_stakes:
            return ModelRoutingDecision(
                selected_deployment=self.advanced_deployment,
                reason="High-stakes decision-support phrasing detected.",
                complexity_label="complex",
            )

        if has_complex_language or broad_query or portfolio_decision_support:
            return ModelRoutingDecision(
                selected_deployment=self.advanced_deployment,
                reason="Broad/analytical factual query detected; routing to advanced deployment for better reasoning.",
                complexity_label="moderate",
            )

        return ModelRoutingDecision(
            selected_deployment=self.default_deployment,
            reason="Simple factual/tool query can be answered on the default lightweight deployment.",
            complexity_label="simple",
        )
