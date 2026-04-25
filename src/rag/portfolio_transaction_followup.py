"""Helpers for transaction draft follow-up handling in chat."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

TOTAL_INTERPRETATION_ANSWERS = {
    "total",
    "total amount",
    "загальна",
    "загальна сума",
    "це загальна сума",
    "тотал",
    "це тотал",
}

PER_UNIT_INTERPRETATION_ANSWERS = {
    "per share",
    "per unit",
    "unit",
    "unit price",
    "за акцію",
    "ціна за акцію",
    "ціна за 1",
    "ціна за 1 акцію",
    "за 1 акцію",
    "за одиницю",
    "ціна за одиницю",
}

_CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "UAH": "₴",
}


def normalize_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def detect_price_interpretation_answer(user_reply: str) -> Optional[str]:
    normalized = normalize_text(user_reply)
    if not normalized:
        return None

    if normalized in TOTAL_INTERPRETATION_ANSWERS:
        return "total"
    if normalized in PER_UNIT_INTERPRETATION_ANSWERS:
        return "per_unit"

    if any(token in normalized for token in ("тотал", "загальн", "сума", "total")):
        return "total"
    if any(
        token in normalized
        for token in (
            "per share",
            "per unit",
            "за акцію",
            "ціна за",
            "за 1",
            "за одиниц",
        )
    ):
        return "per_unit"
    return None


def is_price_clarification_prompt(message: str) -> bool:
    normalized = normalize_text(message)
    if not normalized:
        return False

    has_total_side = any(token in normalized for token in ("загальн", "сума", "total"))
    has_unit_side = any(
        token in normalized
        for token in (
            "за акцію",
            "ціна за",
            "per share",
            "per unit",
            "за одиниц",
            "за 1",
        )
    )
    return has_total_side and has_unit_side


def is_pending_draft_waiting_price_interpretation(draft: Optional[dict]) -> bool:
    if not isinstance(draft, dict):
        return False
    if draft.get("purchase_price") not in (None, ""):
        return False
    ambiguous_price = draft.get("ambiguous_price")
    if ambiguous_price in (None, ""):
        return False
    amount = _to_float(draft.get("amount"))
    if amount is None or amount <= 0:
        return False
    interpretation = str(draft.get("price_interpretation") or "").strip().lower()
    return interpretation in {"", "unknown"}


def complete_pending_draft_from_interpretation(
    draft: dict,
    interpretation: str,
) -> Optional[dict]:
    if not isinstance(draft, dict):
        return None

    amount = _to_float(draft.get("amount"))
    ambiguous_price = _to_float(draft.get("ambiguous_price"))
    if amount is None or amount <= 0 or ambiguous_price is None or ambiguous_price <= 0:
        return None

    interpretation_normalized = (interpretation or "").strip().lower()
    if interpretation_normalized == "total":
        total_value = ambiguous_price
        purchase_price = total_value / amount
    elif interpretation_normalized == "per_unit":
        purchase_price = ambiguous_price
        total_value = purchase_price * amount
    else:
        return None

    updated = dict(draft)
    updated["price_interpretation"] = interpretation_normalized
    updated["purchase_price"] = purchase_price
    updated["total_value"] = total_value
    return updated


def build_confirmation_message(draft: dict, language: str = "uk") -> str:
    amount = _format_number(draft.get("amount"))
    ticker = str(draft.get("ticker") or "").strip().upper()
    currency = str(draft.get("currency") or "").strip().upper()
    purchase_price = _format_money(draft.get("purchase_price"), currency)
    total_value = _format_money(draft.get("total_value"), currency)
    ticker_label = ticker if ticker else str(draft.get("asset_type") or "актив")

    if (language or "").strip().lower() == "en":
        return (
            f"Draft prepared: {amount} {ticker_label} at {purchase_price} per unit, "
            f"total amount {total_value}. Add to portfolio?"
        )
    return (
        f"Підготував запис: {amount} {ticker_label} по {purchase_price} за акцію, "
        f"загальна сума {total_value}. Додати в портфель?"
    )


def bootstrap_pending_transaction_from_user_message(
    user_message: str,
) -> Optional[dict]:
    text = user_message or ""
    normalized = normalize_text(text)
    if not normalized:
        return None

    amount = _extract_amount(text, normalized)
    ambiguous_price = _extract_ambiguous_price(text, normalized)
    ticker = _extract_ticker(text)
    currency = _extract_currency(normalized)
    asset_type = _extract_asset_type(normalized, ticker)
    purchase_date = _extract_purchase_date(normalized, text)

    if amount is None or amount <= 0 or ambiguous_price is None or ambiguous_price <= 0:
        return None
    if not asset_type:
        return None

    draft: dict[str, object] = {
        "intent": "portfolio_transaction",
        "asset_type": asset_type,
        "amount": amount,
        "purchase_date": purchase_date,
        "ambiguous_price": ambiguous_price,
        "price_interpretation": "unknown",
    }
    if ticker:
        draft["ticker"] = ticker
    if currency:
        draft["currency"] = currency
    return draft


def _extract_ticker(text: str) -> Optional[str]:
    candidates = re.findall(r"\b[A-Z]{2,10}\b", text or "")
    blocked = {"USD", "UAH", "EUR", "OVDP", "GDP", "FED", "ECB", "IRS"}
    for candidate in candidates:
        if candidate not in blocked:
            return candidate

    # Fallback for lowercase ticker mentions, e.g. "20 акцій tsla".
    contextual = re.search(
        r"(?:акц\w*|shares?|stock|stocks|etf)\s+([A-Za-z]{2,10})",
        text or "",
        flags=re.IGNORECASE,
    )
    if contextual:
        candidate = contextual.group(1).upper()
        if candidate not in blocked:
            return candidate
    return None


def _extract_currency(normalized: str) -> Optional[str]:
    if any(token in normalized for token in ("$", " usd", "usd ", "долар", "бакс")):
        return "USD"
    if any(token in normalized for token in ("€", " eur", "eur ", "євро", "евро")):
        return "EUR"
    if any(token in normalized for token in ("₴", " uah", "uah ", "грн")):
        return "UAH"
    return None


def _extract_asset_type(normalized: str, ticker: Optional[str]) -> Optional[str]:
    if any(
        token in normalized
        for token in ("крипт", "crypto", "bitcoin", "btc", "eth", "ethereum")
    ):
        return "Криптовалюта"
    if (
        any(token in normalized for token in ("акц", "stock", "shares", "etf"))
        or ticker
    ):
        return "Акції (ETF)"
    return None


def _extract_amount(text: str, normalized: str) -> Optional[float]:
    patterns = [
        r"(\d+(?:[.,]\d+)?)\s*(?:акц\w*|shares?|шт\b|одиниц\w*|coins?)",
        r"(?:купив|купила|продав|продала|взяв|взяла|додав|додала|bought|sold|added|purchased)\s*(\d+(?:[.,]\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            return _to_float(match.group(1))

    numbers = _extract_numbers(text)
    return numbers[0] if numbers else None


def _extract_ambiguous_price(text: str, normalized: str) -> Optional[float]:
    match = re.search(r"(?:\bза\b|\bпо\b|\bfor\b)\s*(\d+(?:[.,]\d+)?)", normalized)
    if match:
        return _to_float(match.group(1))

    numbers = _extract_numbers(text)
    if len(numbers) >= 2:
        return numbers[1]
    return None


def _extract_purchase_date(normalized: str, original_text: str) -> str:
    today = date.today()
    if "вчора" in normalized or "yesterday" in normalized:
        return (today - timedelta(days=1)).isoformat()
    if "сьогодні" in normalized or "today" in normalized:
        return today.isoformat()

    match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", original_text or "")
    if match:
        return match.group(1)
    return today.isoformat()


def _extract_numbers(text: str) -> list[float]:
    numbers: list[float] = []
    for token in re.findall(r"\d+(?:[.,]\d+)?", text or ""):
        numeric = _to_float(token)
        if numeric is not None:
            numbers.append(numeric)
    return numbers


def _format_number(value: object) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return "0"
    if abs(numeric - round(numeric)) < 1e-9:
        return str(int(round(numeric)))
    return f"{numeric:.2f}"


def _format_money(value: object, currency: str) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return "—"

    rendered = _format_number(numeric)
    symbol = _CURRENCY_SYMBOLS.get((currency or "").upper(), currency or "")
    if symbol in {"$", "€", "₴"}:
        return f"{symbol}{rendered}"
    if symbol:
        return f"{rendered} {symbol}"
    return rendered


def _to_float(value: object) -> Optional[float]:
    if value in (None, "", "None"):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
