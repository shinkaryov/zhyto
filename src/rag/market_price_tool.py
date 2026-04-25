"""
Chat tool definition and executor for live market price lookup.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from src.services import get_market_data_service
from src.services.market_data import CRYPTO_ASSET_TYPES, STOCK_ASSET_TYPES
from src.utils import get_logger

logger = get_logger(__name__)

MARKET_PRICE_TOOL_NAME = "get_current_market_price"

MARKET_PRICE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": MARKET_PRICE_TOOL_NAME,
        "description": (
            "Fetch a current market price for a user-requested asset. "
            "Use this for live/public market data such as stocks, ETFs, and crypto."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": (
                        "Public market ticker/symbol like AAPL, DUOL, BTC, ETH. "
                        "Required for market-traded assets (stocks/ETFs/crypto)."
                    ),
                },
                "asset_type": {
                    "type": "string",
                    "description": (
                        "Asset class label used by the portfolio domain "
                        "(e.g. 'Акції (ETF)', 'Криптовалюта', 'ОВДП', 'Депозит', 'Готівка')."
                    ),
                },
                "purchase_price": {
                    "type": "number",
                    "description": (
                        "Optional purchase price fallback for static/non-market assets where "
                        "external live pricing is not used."
                    ),
                },
                "currency": {
                    "type": "string",
                    "description": (
                        "Optional currency code from user/portfolio context (e.g. UAH, USD, EUR)."
                    ),
                },
            },
            "required": ["asset_type"],
            "additionalProperties": False,
        },
    },
}


def get_market_price_tool_definitions() -> list[dict[str, Any]]:
    """Return tool schema list compatible with LLM function/tool calling."""
    return [MARKET_PRICE_TOOL_SCHEMA]


def execute_get_current_market_price(arguments: dict[str, Any]) -> dict[str, Any]:
    """
    Execute live market price lookup via MarketDataService.

    Returns a structured payload and never fabricates prices.
    """
    market_data_service = get_market_data_service()
    asset_type = str(arguments.get("asset_type") or "").strip()
    raw_ticker = arguments.get("ticker")
    ticker = str(raw_ticker).strip().upper() if raw_ticker else None
    purchase_price = arguments.get("purchase_price")
    input_currency = str(arguments.get("currency") or "").strip().upper() or None
    fetched_at = datetime.now(timezone.utc).isoformat()

    if not asset_type:
        return _failure_response(
            ticker=ticker,
            asset_type=asset_type,
            source=None,
            currency=input_currency,
            fetched_at=fetched_at,
            error_code="missing_asset_type",
            message="asset_type is required",
        )

    if market_data_service.is_market_traded_asset(asset_type) and not ticker:
        return _failure_response(
            ticker=ticker,
            asset_type=asset_type,
            source=_infer_source(asset_type),
            currency=input_currency,
            fetched_at=fetched_at,
            error_code="missing_ticker",
            message="ticker is required for market-traded assets",
        )

    try:
        current_price = market_data_service.get_current_price(
            asset_type=asset_type,
            ticker=ticker,
            purchase_price=purchase_price,
        )
    except Exception as exc:
        logger.warning(
            "Market price tool failed for ticker='%s', asset_type='%s': %s",
            ticker,
            asset_type,
            exc,
            exc_info=True,
        )
        return _failure_response(
            ticker=ticker,
            asset_type=asset_type,
            source=_infer_source(asset_type),
            currency=input_currency,
            fetched_at=fetched_at,
            error_code="tool_execution_error",
            message="live market data is temporarily unavailable",
        )

    source = _infer_source(asset_type)
    resolved_currency = _infer_currency(asset_type, input_currency)

    if current_price is None:
        return _failure_response(
            ticker=ticker,
            asset_type=asset_type,
            source=source,
            currency=resolved_currency,
            fetched_at=fetched_at,
            error_code="price_unavailable",
            message="live market data is temporarily unavailable",
        )

    return {
        "ok": True,
        "ticker": ticker,
        "asset_type": asset_type,
        "current_price": current_price,
        "currency": resolved_currency,
        "source": source,
        "fetched_at": fetched_at,
        "error_code": None,
        "message": None,
    }


def _failure_response(
    *,
    ticker: Optional[str],
    asset_type: str,
    source: Optional[str],
    currency: Optional[str],
    fetched_at: str,
    error_code: str,
    message: str,
) -> dict[str, Any]:
    return {
        "ok": False,
        "ticker": ticker,
        "asset_type": asset_type,
        "current_price": None,
        "currency": currency,
        "source": source,
        "fetched_at": fetched_at,
        "error_code": error_code,
        "message": message,
    }


def _infer_source(asset_type: str) -> str:
    normalized_asset_type = (asset_type or "").strip()
    if normalized_asset_type in STOCK_ASSET_TYPES:
        return "yfinance"
    if normalized_asset_type in CRYPTO_ASSET_TYPES:
        return "coingecko"
    return "static_fallback"


def _infer_currency(asset_type: str, input_currency: Optional[str]) -> Optional[str]:
    normalized_asset_type = (asset_type or "").strip()
    if normalized_asset_type in CRYPTO_ASSET_TYPES:
        return "USD"
    return input_currency
