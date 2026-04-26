"""Query intent detection logic for chat routing."""

from __future__ import annotations

import re
from typing import Any, Optional

from src.rag.chat_types import (
    QueryIntent,
    ROUTING_INTENT_ANALYTICAL_RAG,
    ROUTING_INTENT_ANALYTICAL_WITH_LIVE_PRICE,
    ROUTING_INTENT_FACTUAL_RAG,
    ROUTING_INTENT_PORTFOLIO_TRANSACTION,
    ROUTING_INTENT_PURE_LIVE_PRICE,
)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def detect_language(query: str) -> str:
    return "uk" if re.search(r"[іїєґІЇЄҐа-яА-Я]", query or "") else "en"


class QueryIntentDetector:
    """Rule-based detector for query domain and analysis intent."""

    DOMAIN_HINTS: dict[str, dict[str, list[str]]] = {
        "macro": {
            "keywords": [
                "macro",
                "інфляц",
                "ставк",
                "fed",
                "ecb",
                "центробанк",
                "глобаль",
                "рецес",
                "gdp",
                "геопол",
                "oil",
                "нафта",
            ],
            "domains": ["macro", "macro_global", "macro_local"],
        },
        "taxes": {
            "keywords": [
                "tax",
                "подат",
                "декларац",
                "пдфо",
                "military levy",
                "військов",
                "irs",
                "оподатку",
            ],
            "domains": ["tax", "personal_finance"],
        },
        "crypto": {
            "keywords": ["crypto", "крипт", "bitcoin", "btc", "eth", "solana"],
            "domains": ["crypto"],
        },
        "ovdp": {
            "keywords": ["ovdp", "овдп", "облігац", "bond", "isin", "мінфін", "ytm"],
            "domains": ["ovdp", "bonds", "fixed_income"],
        },
        "equities": {
            "keywords": [
                "equit",
                "stock",
                "акці",
                "etf",
                "s&p",
                "nasdaq",
                "dow",
                "valuation",
                "bull",
                "bear",
            ],
            "domains": ["equit", "stocks", "market", "personal_finance"],
        },
        "real_estate": {
            "keywords": [
                "reit",
                "real estate",
                "нерухом",
                "іпотек",
                "єоселя",
                "housing",
            ],
            "domains": ["real_estate", "property", "housing"],
        },
    }

    CHANNEL_HINTS: dict[str, list[str]] = {
        "telegram": ["telegram", "телеграм", "телеграмі", "канал"],
        "youtube": ["youtube", "ютуб", "відео"],
        "news": ["news", "новин", "новини", "rss", "media"],
    }

    ANALYTICAL_HINTS = [
        "що думаєш",
        "як думаєш",
        "what do you think",
        "оціни",
        "чому",
        "why",
        "ризик",
        "risk",
        "narrative",
        "сценар",
        "впли",
        "implication",
        "signal",
        "порівня",
        "consensus",
        "дискус",
        "аргумент",
        "main risks",
        "що змінил",
        "what changed",
        "що відбувається",
        "what is happening",
        "чи варто",
        "should i",
        "should we",
        "що це означає",
        "what does it mean",
        "варто хвилювати",
        "пасивн",
        "passive income",
        "фінансовий план",
        "financial plan",
        "allocation",
        "алокац",
        "ребаланс",
        "rebalanc",
        "що мені купити",
        "що купити",
        "what should i buy",
        "asset class",
        "класи активів",
        "диверсиф",
        "withdrawal",
        "safe withdrawal",
        "max drawdown",
        "просадк",
    ]

    TIME_SENSITIVE_HINTS = [
        "today",
        "сьогодні",
        "now",
        "зараз",
        "latest",
        "recent",
        "остан",
        "new",
        "новин",
        "цього тижня",
        "this week",
    ]

    LIVE_PRICE_QUERY_HINTS = [
        "price",
        "quote",
        "trading at",
        "how much",
        "скільки кошту",
        "яка ціна",
        "скільки зараз",
        "скільки сьогодні",
        "поточна ціна",
        "курс",
        "коштує",
        "зараз",
        "сьогодні",
        "today",
        "now",
        "на скільки виріс",
        "наскільки виріс",
        "на скільки впав",
        "наскільки впав",
    ]
    LIVE_ASSET_HINTS = [
        "aapl",
        "duol",
        "bitcoin",
        "btc",
        "ethereum",
        "eth",
        "crypto",
        "крипт",
        "акці",
        "stock",
        "etf",
        "ticker",
        "тикер",
    ]
    PORTFOLIO_REFERENCE_HINTS = [
        "мій",
        "моя",
        "моє",
        "мої",
        "my",
        "мій bitcoin",
        "my bitcoin",
        "мої акції",
        "my stocks",
        "мій портфель",
        "my portfolio",
    ]
    LIVE_ANALYSIS_HINTS = [
        "чому",
        "why",
        "що це означає",
        "what does it mean",
        "чи варто",
        "should i",
        "should we",
        "ризик",
        "risk",
        "поясн",
        "explain",
        "контекст",
        "context",
        "наслідк",
        "implication",
        "варто хвилювати",
        "should i worry",
    ]
    LIVE_TICKER_PATTERN = re.compile(r"\b[A-Z]{2,10}\b")
    NON_MARKET_TICKER_TOKENS = {
        "OVDP",
        "GDP",
        "IRS",
        "FED",
        "ECB",
    }
    TRANSACTION_VERB_HINTS = [
        "додай",
        "додати",
        "занеси",
        "занести",
        "зафіксуй",
        "зафіксувати",
        "record",
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
    ]
    EXPLICIT_ANALYSIS_ON_TRANSACTION_HINTS = [
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
    ]
    TRANSACTION_CONFIRM_WORDS = {
        "так",
        "yes",
        "ок",
        "ok",
        "додай",
        "додати",
        "підтверджую",
        "підтверджую.",
        "confirm",
    }
    TRANSACTION_CANCEL_WORDS = {
        "ні",
        "no",
        "скасувати",
        "cancel",
        "не додавай",
        "не додавати",
    }
    TRANSACTION_CLARIFICATION_DIRECT_ANSWERS = {
        "total",
        "total amount",
        "загальна сума",
        "загальна",
        "тотал",
        "це тотал",
        "за одиницю",
        "ціна за одиницю",
        "unit",
        "unit price",
        "per unit",
        "per share",
        "це загальна сума",
        "це ціна за одиницю",
        "це ціна за акцію",
    }

    @classmethod
    def _is_transaction_statement(cls, query: str, normalized_query: str) -> bool:
        has_transaction_verb = any(
            re.search(rf"\b{re.escape(verb)}\b", normalized_query)
            for verb in cls.TRANSACTION_VERB_HINTS
        )
        if not has_transaction_verb:
            return False

        ticker_candidates = cls.LIVE_TICKER_PATTERN.findall(query or "")
        has_ticker = any(
            token not in cls.NON_MARKET_TICKER_TOKENS for token in ticker_candidates
        )
        has_asset_hint = any(
            keyword in normalized_query for keyword in cls.LIVE_ASSET_HINTS
        )
        if not (has_ticker or has_asset_hint):
            return False

        numeric_tokens = re.findall(r"\d+(?:[.,]\d+)?", query or "")
        number_count = len(numeric_tokens)
        has_price_marker = any(
            marker in normalized_query
            for marker in (
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
        )
        return number_count >= 2 or (number_count >= 1 and has_price_marker)

    @classmethod
    def _is_portfolio_action_request(cls, query: str, normalized_query: str) -> bool:
        has_transaction_verb = any(
            re.search(rf"\b{re.escape(verb)}\b", normalized_query)
            for verb in cls.TRANSACTION_VERB_HINTS
        )
        if not has_transaction_verb:
            return False

        ticker_candidates = cls.LIVE_TICKER_PATTERN.findall(query or "")
        has_ticker = any(
            token not in cls.NON_MARKET_TICKER_TOKENS for token in ticker_candidates
        )
        has_asset_hint = any(
            keyword in normalized_query for keyword in cls.LIVE_ASSET_HINTS
        )
        has_portfolio_hint = any(
            token in normalized_query
            for token in ("портфель", "portfolio", "в портфель")
        )
        return has_ticker or has_asset_hint or has_portfolio_hint

    @classmethod
    def _is_explicit_analysis_request(cls, normalized_query: str) -> bool:
        return any(
            marker in normalized_query
            for marker in cls.EXPLICIT_ANALYSIS_ON_TRANSACTION_HINTS
        )

    @staticmethod
    def _last_assistant_message(history: Optional[list[dict[str, Any]]]) -> str:
        if not history:
            return ""
        for item in reversed(history):
            if str(item.get("role") or "").strip().lower() != "assistant":
                continue
            content = item.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
        return ""

    @classmethod
    def _is_transaction_clarification_followup(
        cls,
        *,
        normalized_query: str,
        history: Optional[list[dict[str, Any]]],
    ) -> bool:
        if not history or not normalized_query:
            return False

        last_assistant = normalize_text(cls._last_assistant_message(history))
        if not last_assistant:
            return False

        asks_total_vs_unit = (
            (
                any(token in last_assistant for token in ("total", "загальн", "сума"))
                and any(
                    token in last_assistant
                    for token in (
                        "unit",
                        "per share",
                        "за одиниц",
                        "ціна за одиниц",
                        "ціна за акцію",
                        "ціна за 1 акцію",
                        "за 1 акцію",
                    )
                )
            )
            or "total transaction amount" in last_assistant
            or "price per share" in last_assistant
        )
        if not asks_total_vs_unit:
            return False

        if normalized_query in cls.TRANSACTION_CLARIFICATION_DIRECT_ANSWERS:
            return True

        short_followup = len(normalized_query.split()) <= 8
        has_disambiguation_keyword = any(
            token in normalized_query
            for token in (
                "total",
                "загальн",
                "сума",
                "unit",
                "за одиниц",
                "ціна за одиниц",
                "ціна за акцію",
                "per unit",
                "per share",
            )
        )
        return short_followup and has_disambiguation_keyword

    @classmethod
    def _is_transaction_confirmation_followup(
        cls,
        *,
        normalized_query: str,
        history: Optional[list[dict[str, Any]]],
    ) -> bool:
        if not history or not normalized_query:
            return False

        last_assistant = normalize_text(cls._last_assistant_message(history))
        if not last_assistant:
            return False

        asks_for_confirmation = any(
            marker in last_assistant
            for marker in (
                "додати в портфель",
                "add to portfolio",
                "підготував запис",
                "draft is ready",
                "чернетка транзакції",
                "підтверд",
                "confirm",
            )
        )
        if not asks_for_confirmation:
            return False

        return (
            normalized_query in cls.TRANSACTION_CONFIRM_WORDS
            or normalized_query in cls.TRANSACTION_CANCEL_WORDS
        )

    @classmethod
    def _detect_chat_routing_intent(
        cls,
        *,
        query: str,
        normalized_query: str,
        user_portfolio: Optional[list[dict[str, Any]]] = None,
        history: Optional[list[dict[str, Any]]] = None,
    ) -> tuple[str, bool]:
        portfolio_items = user_portfolio or []
        if cls._is_transaction_clarification_followup(
            normalized_query=normalized_query,
            history=history,
        ) or cls._is_transaction_confirmation_followup(
            normalized_query=normalized_query,
            history=history,
        ):
            return ROUTING_INTENT_PORTFOLIO_TRANSACTION, False

        if cls._is_portfolio_action_request(
            query, normalized_query
        ) and not cls._is_explicit_analysis_request(normalized_query):
            return ROUTING_INTENT_PORTFOLIO_TRANSACTION, False

        if cls._is_transaction_statement(
            query, normalized_query
        ) and not cls._is_explicit_analysis_request(normalized_query):
            return ROUTING_INTENT_PORTFOLIO_TRANSACTION, False

        has_live_keyword = any(
            keyword in normalized_query for keyword in cls.LIVE_PRICE_QUERY_HINTS
        )
        ticker_candidates = cls.LIVE_TICKER_PATTERN.findall(query or "")
        has_ticker = any(
            token not in cls.NON_MARKET_TICKER_TOKENS for token in ticker_candidates
        )
        has_asset_hint = any(
            keyword in normalized_query for keyword in cls.LIVE_ASSET_HINTS
        )
        has_portfolio_reference = any(
            keyword in normalized_query for keyword in cls.PORTFOLIO_REFERENCE_HINTS
        )
        has_portfolio_ticker = any(
            str(asset.get("ticker") or "").strip() for asset in portfolio_items
        )

        has_asset_reference = (
            has_ticker
            or has_asset_hint
            or (has_portfolio_reference and has_portfolio_ticker)
        )
        requires_live_price = has_live_keyword and has_asset_reference
        asks_for_analysis = any(
            keyword in normalized_query for keyword in cls.LIVE_ANALYSIS_HINTS
        ) or any(keyword in normalized_query for keyword in cls.ANALYTICAL_HINTS)

        if requires_live_price and asks_for_analysis:
            return ROUTING_INTENT_ANALYTICAL_WITH_LIVE_PRICE, True
        if requires_live_price:
            return ROUTING_INTENT_PURE_LIVE_PRICE, True
        if asks_for_analysis:
            return ROUTING_INTENT_ANALYTICAL_RAG, False
        return ROUTING_INTENT_FACTUAL_RAG, False

    def detect(
        self,
        query: str,
        user_portfolio: Optional[list[dict[str, Any]]] = None,
        history: Optional[list[dict[str, Any]]] = None,
    ) -> QueryIntent:
        normalized = normalize_text(query)

        matched_domains: list[str] = []
        for domain_hint in self.DOMAIN_HINTS.values():
            if any(keyword in normalized for keyword in domain_hint["keywords"]):
                matched_domains.extend(domain_hint["domains"])

        matched_channels: list[str] = []
        for channel, keywords in self.CHANNEL_HINTS.items():
            if any(keyword in normalized for keyword in keywords):
                matched_channels.append(channel)

        is_analytical = any(keyword in normalized for keyword in self.ANALYTICAL_HINTS)
        is_time_sensitive = any(
            keyword in normalized for keyword in self.TIME_SENSITIVE_HINTS
        )
        routing_intent, requires_live_price_tool = self._detect_chat_routing_intent(
            query=query,
            normalized_query=normalized,
            user_portfolio=user_portfolio,
            history=history,
        )

        dedup_domains = list(dict.fromkeys(matched_domains))
        dedup_channels = list(dict.fromkeys(matched_channels))

        return QueryIntent(
            matched_domains=dedup_domains,
            matched_channels=dedup_channels,
            is_analytical=is_analytical,
            is_time_sensitive=is_time_sensitive,
            routing_intent=routing_intent,
            requires_live_price_tool=requires_live_price_tool,
        )
