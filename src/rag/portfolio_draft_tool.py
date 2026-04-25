"""
Chat tool definition and executor for draft portfolio transaction extraction.

Draft-only by design: this module NEVER writes to storage.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from src.utils import get_logger

logger = get_logger(__name__)

DRAFT_PORTFOLIO_TRANSACTION_TOOL_NAME = "draft_portfolio_transaction"

_SUPPORTED_ASSET_TYPES = {
    "ОВДП",
    "Корпоративні облігації",
    "Акції (ETF)",
    "Криптовалюта",
    "Нерухомість",
    "Фонди нерухомості (Inzhur, REITs)",
    "Земля",
    "Готівка",
    "Депозит",
}
_SUPPORTED_CURRENCIES = {"UAH", "USD", "EUR"}

DRAFT_PORTFOLIO_TRANSACTION_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": DRAFT_PORTFOLIO_TRANSACTION_TOOL_NAME,
        "description": (
            "Extract a draft portfolio transaction from user instruction. "
            "Draft only, no database write. Use when user asks to add/buy asset into portfolio."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "asset_type": {
                    "type": "string",
                    "description": (
                        "Portfolio asset type (e.g. Акції (ETF), Криптовалюта, ОВДП, Депозит, Готівка)."
                    ),
                },
                "amount": {
                    "type": "number",
                    "description": "Asset amount/quantity. Must be > 0.",
                },
                "currency": {
                    "type": "string",
                    "description": "Asset currency (UAH, USD, EUR).",
                },
                "ticker": {
                    "type": "string",
                    "description": "Optional market ticker for stocks/ETF/crypto.",
                },
                "purchase_price": {
                    "type": "number",
                    "description": (
                        "Optional purchase price PER UNIT only. "
                        "If user gives total transaction amount, convert to per-unit before calling tool."
                    ),
                },
                "total_value": {
                    "type": "number",
                    "description": (
                        "Optional total transaction amount for the full position. "
                        "If present with amount and purchase_price is absent, purchase_price is derived."
                    ),
                },
                "purchase_date": {
                    "type": "string",
                    "description": "Optional purchase date in YYYY-MM-DD format. If omitted, defaults to today.",
                },
                "notes": {
                    "type": "string",
                    "description": (
                        "Optional note/comment explicitly provided by user. "
                        "Do not auto-generate synthetic summaries."
                    ),
                },
            },
            "required": ["asset_type", "amount", "currency"],
            "additionalProperties": False,
        },
    },
}


def get_portfolio_draft_tool_definitions() -> list[dict[str, Any]]:
    return [DRAFT_PORTFOLIO_TRANSACTION_TOOL_SCHEMA]


def execute_draft_portfolio_transaction(arguments: dict[str, Any]) -> dict[str, Any]:
    """
    Build pending transaction draft for chat confirmation card.

    This function is intentionally side-effect free.
    """
    asset_type_raw = arguments.get("asset_type")
    amount_raw = arguments.get("amount")
    currency_raw = arguments.get("currency")
    ticker_raw = arguments.get("ticker")
    purchase_price_raw = arguments.get("purchase_price")
    total_value_raw = arguments.get("total_value")
    purchase_date_raw = arguments.get("purchase_date")
    notes_raw = arguments.get("notes")

    asset_type = _normalize_asset_type(asset_type_raw)
    amount = _to_float(amount_raw)
    currency = _normalize_currency(currency_raw)
    ticker = str(ticker_raw).strip().upper() if ticker_raw else None
    purchase_price = _to_float(purchase_price_raw)
    total_value = _to_float(total_value_raw)
    purchase_date = _normalize_purchase_date(purchase_date_raw)
    notes = _normalize_notes(notes_raw)

    if asset_type is None:
        return _draft_failure("missing_asset_type", "asset_type is required")
    if amount is None or amount <= 0:
        return _draft_failure("invalid_amount", "amount must be a positive number")
    if currency is None:
        return _draft_failure("invalid_currency", "currency must be one of UAH, USD, EUR")

    if purchase_price is None and total_value is not None and amount > 0:
        purchase_price = total_value / amount

    draft: dict[str, Any] = {
        "asset_type": asset_type,
        "amount": amount,
        "currency": currency,
        "purchase_date": purchase_date,
    }
    if ticker:
        draft["ticker"] = ticker
    if purchase_price is not None:
        draft["purchase_price"] = purchase_price
    if total_value is not None:
        draft["total_value"] = total_value
    elif purchase_price is not None:
        draft["total_value"] = purchase_price * amount
    if notes:
        draft["notes"] = notes

    return {
        "ok": True,
        "type": "pending_transaction_draft",
        "pending_transaction_draft": draft,
        "error_code": None,
        "message": "Transaction draft prepared. Waiting for user confirmation.",
    }


def _draft_failure(error_code: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "type": "pending_transaction_draft",
        "pending_transaction_draft": None,
        "error_code": error_code,
        "message": message,
    }


def _to_float(value: Any) -> Optional[float]:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_purchase_date(value: Any) -> str:
    if not value:
        return date.today().isoformat()
    raw = str(value).strip()
    lowered = raw.lower()
    today = date.today()
    if lowered in {"today", "сьогодні"}:
        return today.isoformat()
    if lowered in {"yesterday", "вчора"}:
        return (today - timedelta(days=1)).isoformat()
    # Best-effort lightweight validation only.
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        return raw
    logger.warning("Invalid purchase_date format in draft tool '%s'; using today", raw)
    return date.today().isoformat()


def _normalize_currency(value: Any) -> Optional[str]:
    raw = str(value or "").strip().upper()
    if not raw:
        return None
    aliases = {
        "ГРН": "UAH",
        "UAH": "UAH",
        "USD": "USD",
        "$": "USD",
        "EUR": "EUR",
        "€": "EUR",
    }
    normalized = aliases.get(raw, raw)
    return normalized if normalized in _SUPPORTED_CURRENCIES else None


def _normalize_asset_type(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw in _SUPPORTED_ASSET_TYPES:
        return raw

    lowered = raw.lower()
    if any(token in lowered for token in ("акц", "etf", "stock", "stocks", "equity")):
        return "Акції (ETF)"
    if any(token in lowered for token in ("крипт", "crypto", "bitcoin", "btc", "eth", "ethereum")):
        return "Криптовалюта"
    if any(token in lowered for token in ("депозит", "deposit")):
        return "Депозит"
    if any(token in lowered for token in ("готів", "cash")):
        return "Готівка"
    if "ovdp" in lowered or "овдп" in lowered:
        return "ОВДП"
    if any(token in lowered for token in ("inzhur", "reit", "фонди нерухом")):
        return "Фонди нерухомості (Inzhur, REITs)"
    if any(token in lowered for token in ("нерухом", "real estate")):
        return "Нерухомість"
    if "земл" in lowered or "land" in lowered:
        return "Земля"
    if any(token in lowered for token in ("облігац", "bond", "bonds")):
        return "Корпоративні облігації"
    return raw if raw in _SUPPORTED_ASSET_TYPES else None


def _normalize_notes(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None

    notes = value.strip()
    if not notes:
        return None

    lowered = notes.lower()
    synthetic_english_prefixes = (
        "user bought",
        "user purchased",
        "user added",
        "bought ",
        "purchased ",
        "added ",
    )
    if any(lowered.startswith(prefix) for prefix in synthetic_english_prefixes):
        logger.info("Dropping synthetic draft note produced by model: '%s'", notes)
        return None

    return notes
