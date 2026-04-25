"""Lightweight chat guardrails for scope, safety, and response quality."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

ROUTING_INTENT_PURE_LIVE_PRICE = "pure_live_price"


@dataclass
class GuardrailValidationResult:
    """Post-generation guardrail output."""

    message: str
    triggered_rules: list[str] = field(default_factory=list)
    clear_sources: bool = False


SCOPE_PATTERNS: dict[str, list[str]] = {
    "medical": [
        "діагноз",
        "симптом",
        "лікуван",
        "medical diagnosis",
        "medicine dosage",
    ],
    "legal_representation": [
        "представляй мене в суді",
        "підготуй позов",
        "legal representation",
        "represent me in court",
        "write a lawsuit",
    ],
    "illegal_activity": [
        "відмиван",
        "insider trading plan",
        "how to evade tax",
        "ухилитись від подат",
        "підробити",
    ],
    "political_persuasion": [
        "переконай голосувати",
        "vote for",
        "політична агітація",
        "political campaign speech",
    ],
    "gambling": [
        "ставк",
        "casino",
        "казино",
        "betting odds",
        "ставки на спорт",
    ],
    "unrelated_coding_or_homework": [
        "solve my homework",
        "домашнє завдання",
        "напиши python скрипт",
        "write me code",
    ],
}


UNSAFE_ACTION_PATTERNS = [
    r"\b(buy|sell)\b.{0,35}\b(now|immediately|all|everything)\b",
    r"\b(купуй|продавай|продай|купи)\b.{0,35}\b(зараз|все|усе|всі|повністю)\b",
    r"\b(all[- ]?in|all money|всі гроші|весь капітал)\b",
]

GUARANTEE_PATTERNS = [
    r"\b(guaranteed|guarantee|definitely|certainly)\b.{0,35}\b(return|profit|rise|fall)\b",
    r"\b(гарантовано|точно|безризиково)\b.{0,35}\b(прибут|зрост|впаде|виросте)\b",
]

PURE_LIVE_NOISE_PATTERNS = [
    r"nothing found in sources",
    r"no relevant sources",
    r"не знайдено (?:у|в) джерел",
    r"джерела не знайден",
    r"nothing in the knowledge base",
    r"knowledge[- ]base.*(empty|not found)",
]


def detect_scope_violation(question: str) -> Optional[str]:
    normalized = " ".join((question or "").strip().lower().split())
    if not normalized:
        return None

    for category, patterns in SCOPE_PATTERNS.items():
        if any(pattern in normalized for pattern in patterns):
            return category
    return None


def build_scope_refusal(language: str, category: str) -> str:
    if language == "uk":
        return (
            "Я можу допомогти лише з інвестиціями, портфелем, ринком і податковим контекстом інвестицій. "
            "Сформулюйте, будь ласка, фінансове питання, і я відповім по суті."
        )
    return (
        "I can only help with investing, portfolio analysis, market context, and investment-related taxes. "
        "Please ask a finance-focused question and I will help directly."
    )


def _split_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [chunk.strip() for chunk in chunks if chunk and chunk.strip()]


def _strip_pure_live_noise(text: str) -> str:
    sentences = _split_sentences(text)
    if not sentences:
        return text.strip()

    kept: list[str] = []
    for sentence in sentences:
        normalized_sentence = sentence.lower()
        if any(re.search(pattern, normalized_sentence, flags=re.IGNORECASE) for pattern in PURE_LIVE_NOISE_PATTERNS):
            continue
        if re.match(r"^\s*(sources|джерела)\s*:\s*", sentence, flags=re.IGNORECASE):
            continue
        kept.append(sentence)

    cleaned = " ".join(kept).strip()
    return cleaned or text.strip()


def _is_unsafe_actionable_advice(text: str) -> bool:
    for pattern in UNSAFE_ACTION_PATTERNS + GUARANTEE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False


def _safe_actionable_response(language: str) -> str:
    if language == "uk":
        return (
            "Я не можу давати гарантії прибутку або команди на кшталт «купити/продати все». "
            "Можу допомогти зважити варіанти, ризики та сценарії для вашого портфеля."
        )
    return (
        "I can’t provide guaranteed-return promises or all-in buy/sell commands. "
        "I can help you weigh options, risks, and scenarios for your portfolio."
    )


def validate_response_output(
    *,
    message: str,
    routing_intent: str,
    language: str,
) -> GuardrailValidationResult:
    """Apply lightweight deterministic output checks and safe patching."""
    text = (message or "").strip()
    if not text:
        return GuardrailValidationResult(message=text)

    triggered: list[str] = []
    patched = text
    clear_sources = False

    if routing_intent == ROUTING_INTENT_PURE_LIVE_PRICE:
        without_noise = _strip_pure_live_noise(patched)
        if without_noise != patched:
            triggered.append("pure_live_removed_rag_noise")
            patched = without_noise
        # Never include KB citation blocks for tool-only direct price answers.
        citation_free = re.sub(r"\s*\[[0-9,\s;]+\]", "", patched).strip()
        if citation_free != patched:
            triggered.append("pure_live_removed_citations")
            patched = citation_free
            clear_sources = True

    if _is_unsafe_actionable_advice(patched):
        triggered.append("unsafe_financial_advice_blocked")
        patched = _safe_actionable_response(language)
        clear_sources = True

    return GuardrailValidationResult(
        message=patched,
        triggered_rules=triggered,
        clear_sources=clear_sources,
    )
