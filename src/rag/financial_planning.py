"""Deterministic helpers for personal financial planning responses."""

from __future__ import annotations

import math
from typing import Any


def annual_income_target(monthly_income: float) -> float:
    """Convert monthly income target to annual target income."""
    normalized = max(float(monthly_income or 0.0), 0.0)
    return normalized * 12.0


def required_capital(annual_income: float, yield_rate: float) -> float:
    """
    Estimate required capital for a target annual income at a planning yield rate.

    This is a scenario-planning utility only and does not imply guaranteed returns.
    """
    normalized_income = max(float(annual_income or 0.0), 0.0)
    normalized_rate = float(yield_rate or 0.0)
    if normalized_rate <= 0:
        return math.inf
    return normalized_income / normalized_rate


def future_value_lump_sum(
    current_value: float, annual_return: float, years: float
) -> float:
    """Future value of an existing lump sum."""
    principal = max(float(current_value or 0.0), 0.0)
    rate = float(annual_return or 0.0)
    horizon_years = max(float(years or 0.0), 0.0)
    if horizon_years == 0:
        return principal
    return principal * math.pow(1.0 + rate, horizon_years)


def future_value_monthly_contributions(
    monthly_contribution: float,
    annual_return: float,
    years: float,
) -> float:
    """Future value of monthly contributions (end-of-period contributions)."""
    contribution = max(float(monthly_contribution or 0.0), 0.0)
    rate_annual = float(annual_return or 0.0)
    horizon_years = max(float(years or 0.0), 0.0)
    periods = int(round(horizon_years * 12))
    if periods <= 0:
        return 0.0
    monthly_rate = rate_annual / 12.0
    if abs(monthly_rate) < 1e-12:
        return contribution * periods
    growth_factor = math.pow(1.0 + monthly_rate, periods)
    return contribution * ((growth_factor - 1.0) / monthly_rate)


def _safe_float(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(parsed) or math.isinf(parsed):
        return 0.0
    return parsed


def _classify_asset_class(asset: dict[str, Any]) -> str:
    blob = " ".join(
        [
            str(asset.get("asset_type") or ""),
            str(asset.get("ticker") or ""),
            str(asset.get("isin") or ""),
            str(asset.get("notes") or ""),
        ]
    ).lower()

    if any(token in blob for token in ("bitcoin", "btc", "eth", "crypto", "крипт")):
        return "high_risk"
    if any(
        token in blob
        for token in ("reit", "real estate", "нерухом", "земл", "land", "property")
    ):
        return "real_assets"
    if any(
        token in blob
        for token in ("cash", "готів", "money market", "mmf", "короткостроков")
    ):
        return "liquidity_cash"
    if any(
        token in blob
        for token in (
            "ovdp",
            "облігац",
            "bond",
            "депозит",
            "t-bill",
            "treasury",
            "bill",
        )
    ):
        return "defensive_income"
    if any(
        token in blob
        for token in (
            "etf",
            "stock",
            "акці",
            "equity",
            "s&p",
            "nasdaq",
            "spy",
            "vwce",
            "vt",
            "qqq",
            "msci",
        )
    ):
        return "growth_core"
    return "other"


def _pick_value_field(portfolio: list[dict[str, Any]]) -> tuple[str, float]:
    candidates = (
        "current_value_usd",
        "current_value_uah",
        "current_value_eur",
        "current_value",
    )
    best_field = "current_value"
    best_sum = 0.0
    for field in candidates:
        total = 0.0
        for asset in portfolio:
            total += max(_safe_float(asset.get(field)), 0.0)
        if total > best_sum:
            best_sum = total
            best_field = field
    return best_field, best_sum


def portfolio_allocation_by_asset_class(
    portfolio: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Build an allocation snapshot from a portfolio list.

    Returns a normalized structure with value and percentage weight by class.
    """
    base = {
        "growth_core": 0.0,
        "defensive_income": 0.0,
        "real_assets": 0.0,
        "liquidity_cash": 0.0,
        "high_risk": 0.0,
        "other": 0.0,
    }
    if not portfolio:
        return {
            "value_field": "current_value",
            "total_value": 0.0,
            "allocation": {
                key: {"value": 0.0, "weight_percent": 0.0} for key in base.keys()
            },
        }

    value_field, total_value = _pick_value_field(portfolio)
    for asset in portfolio:
        category = _classify_asset_class(asset)
        value = max(_safe_float(asset.get(value_field)), 0.0)
        base[category] = base.get(category, 0.0) + value

    allocation = {}
    for key, value in base.items():
        weight = (value / total_value * 100.0) if total_value > 0 else 0.0
        allocation[key] = {
            "value": round(value, 2),
            "weight_percent": round(weight, 2),
        }

    return {
        "value_field": value_field,
        "total_value": round(total_value, 2),
        "allocation": allocation,
    }
