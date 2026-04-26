"""Unit tests for deterministic financial planning helpers."""

from src.rag.financial_planning import (
    annual_income_target,
    future_value_lump_sum,
    future_value_monthly_contributions,
    portfolio_allocation_by_asset_class,
    required_capital,
)


def test_required_capital_scenarios_for_passive_income_target():
    annual_target = annual_income_target(5000)
    assert annual_target == 60000
    assert required_capital(annual_target, 0.03) == 2000000
    assert required_capital(annual_target, 0.04) == 1500000
    assert required_capital(annual_target, 0.05) == 1200000
    assert required_capital(annual_target, 0.06) == 1000000


def test_future_value_helpers_with_monthly_contributions():
    lump_sum = future_value_lump_sum(200000, 0.06, 10)
    contribution_leg = future_value_monthly_contributions(1000, 0.06, 10)
    total = lump_sum + contribution_leg

    assert round(lump_sum, 0) == 358170
    assert round(contribution_leg, 0) == 163879
    assert round(total, 0) == 522049


def test_portfolio_allocation_by_asset_class_maps_core_buckets():
    portfolio = [
        {"asset_type": "Акції (ETF)", "ticker": "SPY", "current_value_usd": 70000},
        {"asset_type": "ОВДП", "ticker": "UA-OVDP", "current_value_usd": 20000},
        {"asset_type": "REIT ETF", "ticker": "VNQ", "current_value_usd": 7000},
        {"asset_type": "Cash", "ticker": "USD", "current_value_usd": 2000},
        {"asset_type": "Криптовалюта", "ticker": "BTC", "current_value_usd": 1000},
    ]
    snapshot = portfolio_allocation_by_asset_class(portfolio)
    allocation = snapshot["allocation"]

    assert snapshot["value_field"] == "current_value_usd"
    assert snapshot["total_value"] == 100000.0
    assert allocation["growth_core"]["weight_percent"] == 70.0
    assert allocation["defensive_income"]["weight_percent"] == 20.0
    assert allocation["real_assets"]["weight_percent"] == 7.0
    assert allocation["liquidity_cash"]["weight_percent"] == 2.0
    assert allocation["high_risk"]["weight_percent"] == 1.0
