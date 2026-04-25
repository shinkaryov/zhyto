"""Shared portfolio enrichment logic for API and chat context."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

CASH_ASSET_TYPES = {"Готівка"}


def _parse_iso_date(value: str, field_name: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format") from exc


def to_float(value: Any) -> Optional[float]:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def calculate_pnl_percent(purchase_price: Optional[float], current_price: Optional[float]) -> Optional[float]:
    if current_price is None or purchase_price is None or purchase_price == 0:
        return None
    return ((current_price - purchase_price) / purchase_price) * 100


def calculate_pnl_value(invested_value: Optional[float], current_value: Optional[float]) -> Optional[float]:
    if invested_value is None or current_value is None:
        return None
    return current_value - invested_value


def calculate_pnl_percent_from_values(
    invested_value: Optional[float],
    current_value: Optional[float],
) -> Optional[float]:
    if invested_value is None or current_value is None or invested_value == 0:
        return None
    return ((current_value - invested_value) / invested_value) * 100


def convert_current_value(
    amount: Optional[float],
    currency: str,
    usd_uah_rate: Optional[float],
    eur_uah_rate: Optional[float],
    *,
    logger: Any,
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    if amount is None:
        return None, None, None

    normalized_currency = (currency or "").upper().strip()
    usd_rate = to_float(usd_uah_rate)
    eur_rate = to_float(eur_uah_rate)
    if usd_rate is not None and usd_rate <= 0:
        usd_rate = None
    if eur_rate is not None and eur_rate <= 0:
        eur_rate = None

    if normalized_currency == "UAH":
        value_uah = amount
        value_usd = value_uah / usd_rate if usd_rate else None
        value_eur = value_uah / eur_rate if eur_rate else None
        return value_uah, value_usd, value_eur

    if normalized_currency == "USD":
        value_usd = amount
        value_uah = value_usd * usd_rate if usd_rate else None
        value_eur = value_uah / eur_rate if value_uah is not None and eur_rate else None
        return value_uah, value_usd, value_eur

    if normalized_currency == "EUR":
        value_eur = amount
        value_uah = value_eur * eur_rate if eur_rate else None
        value_usd = value_uah / usd_rate if value_uah is not None and usd_rate else None
        return value_uah, value_usd, value_eur

    logger.warning(
        "Currency '%s' is not convertible in current MVP portfolio totals",
        normalized_currency or "UNKNOWN",
    )
    return None, None, None


def resolve_purchase_fx_rates_by_date(
    assets: list[dict[str, Any]],
    market_data_service,
    *,
    logger: Any,
) -> tuple[dict[str, Optional[float]], dict[str, Optional[float]]]:
    unique_dates: set[str] = set()
    for asset in assets:
        purchase_date = str(asset.get("purchase_date") or "").strip()
        if not purchase_date:
            continue
        try:
            _parse_iso_date(purchase_date, "Purchase date")
            unique_dates.add(purchase_date)
        except ValueError:
            logger.warning(
                "Skipping historical FX lookup due to invalid purchase_date='%s' for asset id='%s'",
                purchase_date,
                asset.get("id"),
            )

    usd_uah_by_date: dict[str, Optional[float]] = {}
    eur_uah_by_date: dict[str, Optional[float]] = {}
    for purchase_date in unique_dates:
        usd_uah_by_date[purchase_date] = market_data_service.get_usd_uah_rate_for_date(purchase_date)
        eur_uah_by_date[purchase_date] = market_data_service.get_eur_uah_rate_for_date(purchase_date)
    return usd_uah_by_date, eur_uah_by_date


def enrich_portfolio_asset(
    asset: dict[str, Any],
    market_data_service,
    usd_uah_rate: Optional[float],
    eur_uah_rate: Optional[float],
    purchase_usd_uah_by_date: dict[str, Optional[float]],
    purchase_eur_uah_by_date: dict[str, Optional[float]],
    *,
    logger: Any,
) -> dict[str, Any]:
    enriched_asset = dict(asset)
    asset_type = str(asset.get("asset_type") or "")
    ticker = asset.get("ticker")
    currency = str(asset.get("currency") or "")
    amount = to_float(asset.get("amount"))
    purchase_price = to_float(asset.get("purchase_price"))
    purchase_date = str(asset.get("purchase_date") or "").strip()
    manual_current_price = to_float(asset.get("manual_current_price"))

    purchase_usd_uah_rate = purchase_usd_uah_by_date.get(purchase_date)
    purchase_eur_uah_rate = purchase_eur_uah_by_date.get(purchase_date)

    if (
        asset_type in CASH_ASSET_TYPES
        and manual_current_price is None
        and purchase_date
    ):
        try:
            parsed_purchase_date = _parse_iso_date(purchase_date, "Purchase date")
            if parsed_purchase_date == date.today():
                purchase_usd_uah_rate = usd_uah_rate
                purchase_eur_uah_rate = eur_uah_rate
        except ValueError:
            logger.warning(
                "Skipping day-zero FX alignment due to invalid purchase_date='%s' for asset id='%s'",
                purchase_date,
                asset.get("id"),
            )

    if manual_current_price is not None:
        current_price = manual_current_price
    else:
        current_price = market_data_service.get_current_price(
            asset_type=asset_type,
            ticker=ticker,
            purchase_price=purchase_price,
        )
        if current_price is None and market_data_service.is_market_traded_asset(asset_type):
            logger.warning(
                "Current price unavailable for traded asset type='%s', ticker='%s', id='%s'",
                asset_type,
                ticker,
                asset.get("id"),
            )

    if purchase_date and (purchase_usd_uah_rate is None or purchase_eur_uah_rate is None):
        logger.warning(
            "Historical FX rates unavailable for purchase_date='%s', asset id='%s'",
            purchase_date,
            asset.get("id"),
        )

    purchase_price_uah, purchase_price_usd, purchase_price_eur = convert_current_value(
        amount=purchase_price,
        currency=currency,
        usd_uah_rate=purchase_usd_uah_rate,
        eur_uah_rate=purchase_eur_uah_rate,
        logger=logger,
    )
    current_price_uah, current_price_usd, current_price_eur = convert_current_value(
        amount=current_price,
        currency=currency,
        usd_uah_rate=usd_uah_rate,
        eur_uah_rate=eur_uah_rate,
        logger=logger,
    )

    invested_value_original = amount * purchase_price if amount is not None and purchase_price is not None else None
    current_value_original = amount * current_price if amount is not None and current_price is not None else None

    invested_value_uah, invested_value_usd, invested_value_eur = convert_current_value(
        amount=invested_value_original,
        currency=currency,
        usd_uah_rate=purchase_usd_uah_rate,
        eur_uah_rate=purchase_eur_uah_rate,
        logger=logger,
    )
    current_value_uah, current_value_usd, current_value_eur = convert_current_value(
        amount=current_value_original,
        currency=currency,
        usd_uah_rate=usd_uah_rate,
        eur_uah_rate=eur_uah_rate,
        logger=logger,
    )
    pnl_percent_native = calculate_pnl_percent(purchase_price=purchase_price, current_price=current_price)

    pnl_value_uah = calculate_pnl_value(invested_value_uah, current_value_uah)
    pnl_value_usd = calculate_pnl_value(invested_value_usd, current_value_usd)
    pnl_value_eur = calculate_pnl_value(invested_value_eur, current_value_eur)
    pnl_percent_uah = calculate_pnl_percent_from_values(invested_value_uah, current_value_uah)
    pnl_percent_usd = calculate_pnl_percent_from_values(invested_value_usd, current_value_usd)
    pnl_percent_eur = calculate_pnl_percent_from_values(invested_value_eur, current_value_eur)

    enriched_asset["current_price"] = current_price
    enriched_asset["purchase_price_uah"] = purchase_price_uah
    enriched_asset["purchase_price_usd"] = purchase_price_usd
    enriched_asset["purchase_price_eur"] = purchase_price_eur
    enriched_asset["current_price_uah"] = current_price_uah
    enriched_asset["current_price_usd"] = current_price_usd
    enriched_asset["current_price_eur"] = current_price_eur
    enriched_asset["invested_value_original_currency"] = invested_value_original
    enriched_asset["invested_value_uah"] = invested_value_uah
    enriched_asset["invested_value_usd"] = invested_value_usd
    enriched_asset["invested_value_eur"] = invested_value_eur
    enriched_asset["current_value_original_currency"] = current_value_original
    enriched_asset["current_value"] = current_value_original
    enriched_asset["current_value_uah"] = current_value_uah
    enriched_asset["current_value_usd"] = current_value_usd
    enriched_asset["current_value_eur"] = current_value_eur
    enriched_asset["pnl_value_uah"] = pnl_value_uah
    enriched_asset["pnl_value_usd"] = pnl_value_usd
    enriched_asset["pnl_value_eur"] = pnl_value_eur
    enriched_asset["pnl_percent"] = pnl_percent_native
    enriched_asset["pnl_percent_uah"] = pnl_percent_uah
    enriched_asset["pnl_percent_usd"] = pnl_percent_usd
    enriched_asset["pnl_percent_eur"] = pnl_percent_eur
    return enriched_asset


def calculate_portfolio_totals(enriched_assets: list[dict[str, Any]]) -> dict[str, Optional[float]]:
    total_uah = 0.0
    total_usd = 0.0
    total_eur = 0.0
    has_uah_value = False
    has_usd_value = False
    has_eur_value = False

    for asset in enriched_assets:
        value_uah = to_float(asset.get("current_value_uah"))
        value_usd = to_float(asset.get("current_value_usd"))
        value_eur = to_float(asset.get("current_value_eur"))
        if value_uah is not None:
            total_uah += value_uah
            has_uah_value = True
        if value_usd is not None:
            total_usd += value_usd
            has_usd_value = True
        if value_eur is not None:
            total_eur += value_eur
            has_eur_value = True

    return {
        "uah": total_uah if has_uah_value else None,
        "usd": total_usd if has_usd_value else None,
        "eur": total_eur if has_eur_value else None,
    }


def enrich_portfolio_assets(
    assets: list[dict[str, Any]],
    market_data_service,
    *,
    logger: Any,
) -> tuple[list[dict[str, Any]], dict[str, Optional[float]], Optional[float], Optional[float]]:
    usd_uah_rate = market_data_service.get_usd_uah_rate()
    eur_uah_rate = market_data_service.get_eur_uah_rate()
    purchase_usd_uah_by_date, purchase_eur_uah_by_date = resolve_purchase_fx_rates_by_date(
        assets,
        market_data_service,
        logger=logger,
    )
    enriched_assets: list[dict[str, Any]] = []

    for asset in assets:
        try:
            enriched_assets.append(
                enrich_portfolio_asset(
                    asset,
                    market_data_service,
                    usd_uah_rate,
                    eur_uah_rate,
                    purchase_usd_uah_by_date,
                    purchase_eur_uah_by_date,
                    logger=logger,
                )
            )
        except Exception as exc:
            logger.error(
                "Failed to enrich portfolio asset id='%s': %s",
                asset.get("id"),
                exc,
                exc_info=True,
            )
            fallback_asset = dict(asset)
            fallback_asset["current_price"] = None
            fallback_asset["purchase_price_uah"] = None
            fallback_asset["purchase_price_usd"] = None
            fallback_asset["purchase_price_eur"] = None
            fallback_asset["current_price_uah"] = None
            fallback_asset["current_price_usd"] = None
            fallback_asset["current_price_eur"] = None
            fallback_asset["invested_value_original_currency"] = None
            fallback_asset["invested_value_uah"] = None
            fallback_asset["invested_value_usd"] = None
            fallback_asset["invested_value_eur"] = None
            fallback_asset["current_value_original_currency"] = None
            fallback_asset["current_value"] = None
            fallback_asset["current_value_uah"] = None
            fallback_asset["current_value_usd"] = None
            fallback_asset["current_value_eur"] = None
            fallback_asset["pnl_value_uah"] = None
            fallback_asset["pnl_value_usd"] = None
            fallback_asset["pnl_value_eur"] = None
            fallback_asset["pnl_percent"] = None
            fallback_asset["pnl_percent_uah"] = None
            fallback_asset["pnl_percent_usd"] = None
            fallback_asset["pnl_percent_eur"] = None
            enriched_assets.append(fallback_asset)

    totals = calculate_portfolio_totals(enriched_assets)
    return enriched_assets, totals, usd_uah_rate, eur_uah_rate
