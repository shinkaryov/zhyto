"""
Portfolio endpoints.
"""

from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.auth.auth_service import AuthIdentity, get_current_identity
from src.utils import get_logger
from src.db.cosmos_client import get_cosmos_client
from src.services import get_market_data_service
from src.services.portfolio_enrichment import (
    enrich_portfolio_assets as shared_enrich_portfolio_assets,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/portfolio", tags=["portfolio"])
ASSET_TYPES = {
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
CURRENCIES = {"UAH", "USD", "EUR"}
ASSET_TYPES_WITH_YIELD = {
    "ОВДП",
    "Корпоративні облігації",
    "Депозит",
    "Земля",
    "Фонди нерухомості (Inzhur, REITs)",
}
ASSET_TYPES_WITH_TICKER = {
    "Акції (ETF)",
    "Криптовалюта",
    "Фонди нерухомості (Inzhur, REITs)",
}
ASSET_TYPES_WITH_ISIN = {"ОВДП", "Корпоративні облігації"}
ASSET_TYPES_WITH_OPTIONAL_PRICE = {"Готівка", "Депозит"}
CASH_ASSET_TYPES = {"Готівка"}


def _parse_iso_date(value: str, field_name: str) -> date:
    """Parse YYYY-MM-DD date and return date object."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format") from exc


class PortfolioAsset(BaseModel):
    """Portfolio asset model."""

    id: Optional[str] = None
    user_id: Optional[str] = None
    asset_type: str
    amount: float
    currency: str
    purchase_price: float = 1.0
    purchase_date: str
    notes: Optional[str] = None
    ticker: Optional[str] = None
    isin: Optional[str] = None
    maturity_date: Optional[str] = None
    yield_percent: Optional[float] = None
    manual_current_price: Optional[float] = None

    @field_validator("asset_type")
    @classmethod
    def validate_asset_type(cls, value: str) -> str:
        if value not in ASSET_TYPES:
            raise ValueError("Unsupported asset type")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        if value not in CURRENCIES:
            raise ValueError("Unsupported currency")
        return value

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Amount must be greater than 0")
        return value

    @field_validator("purchase_price")
    @classmethod
    def validate_purchase_price(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Purchase price cannot be negative")
        return value

    @field_validator("purchase_date")
    @classmethod
    def validate_purchase_date(cls, value: str) -> str:
        parsed_date = _parse_iso_date(value, "Purchase date")
        if parsed_date > date.today():
            raise ValueError("Purchase date cannot be in the future")
        return value

    @field_validator("maturity_date")
    @classmethod
    def validate_maturity_date(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return value
        _parse_iso_date(value, "Maturity date")
        return value

    @field_validator("yield_percent")
    @classmethod
    def validate_yield(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and value < 0:
            raise ValueError("Yield percent cannot be negative")
        return value

    @field_validator("manual_current_price")
    @classmethod
    def validate_manual_current_price(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and value < 0:
            raise ValueError("Manual current price cannot be negative")
        return value

    @model_validator(mode="after")
    def validate_conditional_fields(self):
        purchase_date = _parse_iso_date(self.purchase_date, "Purchase date")
        maturity_date = (
            _parse_iso_date(self.maturity_date, "Maturity date")
            if self.maturity_date
            else None
        )

        if (
            self.asset_type not in ASSET_TYPES_WITH_OPTIONAL_PRICE
            and self.purchase_price <= 0
        ):
            raise ValueError(
                "Purchase price must be greater than 0 for this asset type"
            )

        if self.asset_type in ASSET_TYPES_WITH_TICKER and not self.ticker:
            raise ValueError("Ticker is required for this asset type")

        if self.asset_type in ASSET_TYPES_WITH_ISIN and not self.isin:
            raise ValueError("ISIN is required for this asset type")

        if maturity_date and maturity_date < purchase_date:
            raise ValueError("Maturity date cannot be earlier than purchase date")

        if self.asset_type not in ASSET_TYPES_WITH_YIELD:
            self.yield_percent = None

        return self


class PortfolioAssetResponse(BaseModel):
    """Portfolio asset response model with live market enrichment fields."""

    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    user_id: Optional[str] = None
    asset_type: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    purchase_price: Optional[float] = None
    purchase_date: Optional[str] = None
    notes: Optional[str] = None
    ticker: Optional[str] = None
    isin: Optional[str] = None
    maturity_date: Optional[str] = None
    yield_percent: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    manual_current_price: Optional[float] = None
    current_price: Optional[float] = None
    purchase_price_uah: Optional[float] = None
    purchase_price_usd: Optional[float] = None
    purchase_price_eur: Optional[float] = None
    current_price_uah: Optional[float] = None
    current_price_usd: Optional[float] = None
    current_price_eur: Optional[float] = None
    invested_value_original_currency: Optional[float] = None
    invested_value_uah: Optional[float] = None
    invested_value_usd: Optional[float] = None
    invested_value_eur: Optional[float] = None
    current_value_original_currency: Optional[float] = None
    current_value: Optional[float] = None
    current_value_uah: Optional[float] = None
    current_value_usd: Optional[float] = None
    current_value_eur: Optional[float] = None
    pnl_percent: Optional[float] = None
    pnl_value_uah: Optional[float] = None
    pnl_value_usd: Optional[float] = None
    pnl_value_eur: Optional[float] = None
    pnl_percent_uah: Optional[float] = None
    pnl_percent_usd: Optional[float] = None
    pnl_percent_eur: Optional[float] = None


class PortfolioTotals(BaseModel):
    """Aggregated portfolio totals by reporting currency."""

    uah: Optional[float] = None
    usd: Optional[float] = None
    eur: Optional[float] = None


class PortfolioResponse(BaseModel):
    """Portfolio response payload."""

    assets: list[PortfolioAssetResponse]
    totals: Optional[PortfolioTotals] = None
    usd_uah_rate: Optional[float] = None
    eur_uah_rate: Optional[float] = None


class ManualCurrentPriceUpdateRequest(BaseModel):
    """Request payload for manual current price override."""

    manual_current_price: Optional[float] = None

    @field_validator("manual_current_price")
    @classmethod
    def validate_manual_current_price(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and value < 0:
            raise ValueError("manual_current_price must be non-negative")
        return value


def _to_float(value: Any) -> Optional[float]:
    """Convert value to float safely."""
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _calculate_pnl_percent(
    purchase_price: Optional[float], current_price: Optional[float]
) -> Optional[float]:
    """Calculate asset PnL percent safely."""
    if current_price is None or purchase_price is None or purchase_price == 0:
        return None
    return ((current_price - purchase_price) / purchase_price) * 100


def _calculate_pnl_value(
    invested_value: Optional[float], current_value: Optional[float]
) -> Optional[float]:
    """Calculate absolute PnL safely."""
    if invested_value is None or current_value is None:
        return None
    return current_value - invested_value


def _calculate_pnl_percent_from_values(
    invested_value: Optional[float],
    current_value: Optional[float],
) -> Optional[float]:
    """Calculate PnL percent from invested/current totals in same currency."""
    if invested_value is None or current_value is None or invested_value == 0:
        return None
    return ((current_value - invested_value) / invested_value) * 100


def _convert_current_value(
    amount: Optional[float],
    currency: str,
    usd_uah_rate: Optional[float],
    eur_uah_rate: Optional[float],
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Convert amount from source currency into UAH, USD, and EUR."""
    if amount is None:
        return None, None, None

    normalized_currency = (currency or "").upper().strip()
    usd_rate = _to_float(usd_uah_rate)
    eur_rate = _to_float(eur_uah_rate)
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


def _resolve_purchase_fx_rates_by_date(
    assets: list[dict[str, Any]],
    market_data_service,
) -> tuple[dict[str, Optional[float]], dict[str, Optional[float]]]:
    """Resolve historical USD/UAH and EUR/UAH rates for unique asset purchase dates."""
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
        usd_uah_by_date[purchase_date] = market_data_service.get_usd_uah_rate_for_date(
            purchase_date
        )
        eur_uah_by_date[purchase_date] = market_data_service.get_eur_uah_rate_for_date(
            purchase_date
        )

    return usd_uah_by_date, eur_uah_by_date


def _enrich_portfolio_asset(
    asset: dict[str, Any],
    market_data_service,
    usd_uah_rate: Optional[float],
    eur_uah_rate: Optional[float],
    purchase_usd_uah_by_date: dict[str, Optional[float]],
    purchase_eur_uah_by_date: dict[str, Optional[float]],
) -> dict[str, Any]:
    """Enrich a single portfolio asset with market data."""
    enriched_asset = dict(asset)
    asset_type = str(asset.get("asset_type") or "")
    ticker = asset.get("ticker")
    currency = str(asset.get("currency") or "")
    amount = _to_float(asset.get("amount"))
    purchase_price = _to_float(asset.get("purchase_price"))
    purchase_date = str(asset.get("purchase_date") or "").strip()
    manual_current_price = _to_float(asset.get("manual_current_price"))

    purchase_usd_uah_rate = purchase_usd_uah_by_date.get(purchase_date)
    purchase_eur_uah_rate = purchase_eur_uah_by_date.get(purchase_date)

    # Day-zero FX alignment for cash only:
    # if purchase date is today, historical and live rates may differ slightly
    # (close vs realtime), which creates artificial immediate P&L.
    # For cash assets bought today, force purchase FX to equal live FX.
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

        if current_price is None and market_data_service.is_market_traded_asset(
            asset_type
        ):
            logger.warning(
                "Current price unavailable for traded asset type='%s', ticker='%s', id='%s'",
                asset_type,
                ticker,
                asset.get("id"),
            )

    if purchase_date and (
        purchase_usd_uah_rate is None or purchase_eur_uah_rate is None
    ):
        logger.warning(
            "Historical FX rates unavailable for purchase_date='%s', asset id='%s'",
            purchase_date,
            asset.get("id"),
        )

    purchase_price_uah, purchase_price_usd, purchase_price_eur = _convert_current_value(
        amount=purchase_price,
        currency=currency,
        usd_uah_rate=purchase_usd_uah_rate,
        eur_uah_rate=purchase_eur_uah_rate,
    )
    current_price_uah, current_price_usd, current_price_eur = _convert_current_value(
        amount=current_price,
        currency=currency,
        usd_uah_rate=usd_uah_rate,
        eur_uah_rate=eur_uah_rate,
    )

    invested_value_original = (
        amount * purchase_price
        if amount is not None and purchase_price is not None
        else None
    )
    current_value_original = (
        amount * current_price
        if amount is not None and current_price is not None
        else None
    )

    invested_value_uah, invested_value_usd, invested_value_eur = _convert_current_value(
        amount=invested_value_original,
        currency=currency,
        usd_uah_rate=purchase_usd_uah_rate,
        eur_uah_rate=purchase_eur_uah_rate,
    )
    current_value_uah, current_value_usd, current_value_eur = _convert_current_value(
        amount=current_value_original,
        currency=currency,
        usd_uah_rate=usd_uah_rate,
        eur_uah_rate=eur_uah_rate,
    )
    pnl_percent_native = _calculate_pnl_percent(
        purchase_price=purchase_price, current_price=current_price
    )

    pnl_value_uah = _calculate_pnl_value(invested_value_uah, current_value_uah)
    pnl_value_usd = _calculate_pnl_value(invested_value_usd, current_value_usd)
    pnl_value_eur = _calculate_pnl_value(invested_value_eur, current_value_eur)
    pnl_percent_uah = _calculate_pnl_percent_from_values(
        invested_value_uah, current_value_uah
    )
    pnl_percent_usd = _calculate_pnl_percent_from_values(
        invested_value_usd, current_value_usd
    )
    pnl_percent_eur = _calculate_pnl_percent_from_values(
        invested_value_eur, current_value_eur
    )

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
    # Keep backward compatibility for clients currently reading current_value.
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


def _calculate_portfolio_totals(
    enriched_assets: list[dict[str, Any]],
) -> dict[str, Optional[float]]:
    """Calculate aggregate totals using converted per-asset values only."""
    total_uah = 0.0
    total_usd = 0.0
    total_eur = 0.0
    has_uah_value = False
    has_usd_value = False
    has_eur_value = False

    for asset in enriched_assets:
        value_uah = _to_float(asset.get("current_value_uah"))
        value_usd = _to_float(asset.get("current_value_usd"))
        value_eur = _to_float(asset.get("current_value_eur"))
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


def _enrich_portfolio_assets(
    assets: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]], dict[str, Optional[float]], Optional[float], Optional[float]
]:
    """Enrich all assets and isolate failures per asset."""
    market_data_service = get_market_data_service()
    return shared_enrich_portfolio_assets(
        assets,
        market_data_service,
        logger=logger,
    )


@router.get("", response_model=PortfolioResponse)
async def get_portfolio(current_user: AuthIdentity = Depends(get_current_identity)):
    """Get user's portfolio."""
    try:
        client = get_cosmos_client()
        assets = await run_in_threadpool(
            client.get_user_portfolio, current_user.user_id
        )
        enriched_assets, totals, usd_uah_rate, eur_uah_rate = await run_in_threadpool(
            _enrich_portfolio_assets, assets
        )
        return {
            "assets": enriched_assets,
            "totals": totals,
            "usd_uah_rate": usd_uah_rate,
            "eur_uah_rate": eur_uah_rate,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting portfolio: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def add_portfolio_asset(
    asset: PortfolioAsset,
    current_user: AuthIdentity = Depends(get_current_identity),
):
    """Add a new asset to portfolio."""
    try:
        client = get_cosmos_client()
        asset_data = asset.model_dump()
        asset_data["user_id"] = current_user.user_id
        added_asset = await run_in_threadpool(client.add_portfolio_asset, asset_data)
        return added_asset
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding portfolio asset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{asset_id}/manual-price", response_model=PortfolioAssetResponse)
async def update_portfolio_asset_manual_price(
    asset_id: str,
    payload: ManualCurrentPriceUpdateRequest,
    current_user: AuthIdentity = Depends(get_current_identity),
):
    """Set or clear manual current price override for a portfolio asset."""
    try:
        client = get_cosmos_client()
        updated_asset = await run_in_threadpool(
            client.update_portfolio_manual_price,
            asset_id,
            current_user.user_id,
            payload.manual_current_price,
        )
        if not updated_asset:
            raise HTTPException(status_code=404, detail="Asset not found")

        market_data_service = get_market_data_service()
        usd_uah_rate = await run_in_threadpool(market_data_service.get_usd_uah_rate)
        eur_uah_rate = await run_in_threadpool(market_data_service.get_eur_uah_rate)
        purchase_usd_uah_by_date, purchase_eur_uah_by_date = await run_in_threadpool(
            _resolve_purchase_fx_rates_by_date,
            [updated_asset],
            market_data_service,
        )
        enriched_asset = await run_in_threadpool(
            _enrich_portfolio_asset,
            updated_asset,
            market_data_service,
            usd_uah_rate,
            eur_uah_rate,
            purchase_usd_uah_by_date,
            purchase_eur_uah_by_date,
        )
        return enriched_asset
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating manual current price: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{asset_id}")
async def delete_portfolio_asset(
    asset_id: str,
    current_user: AuthIdentity = Depends(get_current_identity),
):
    """Delete an asset from portfolio."""
    try:
        client = get_cosmos_client()
        success = await run_in_threadpool(
            client.delete_portfolio_asset,
            asset_id,
            current_user.user_id,
        )
        if not success:
            raise HTTPException(status_code=404, detail="Asset not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting portfolio asset: {e}")
        raise HTTPException(status_code=500, detail=str(e))
