"""Unit tests for enriched portfolio context formatting used by chat prompts."""

from src.services.portfolio_context_formatter import build_enriched_portfolio_context


def test_build_enriched_portfolio_context_includes_total_and_weights_in_reporting_currency():
    assets = [
        {
            "asset_type": "Криптовалюта",
            "ticker": "BTC",
            "amount": 0.01,
            "current_value_usd": 600.0,
            "current_value_uah": 24000.0,
            "current_value_eur": 550.0,
            "purchase_date": "2026-01-01",
            "maturity_date": None,
            "notes": "Core position",
            "yield_percent": None,
        },
        {
            "asset_type": "Акції/ETF",
            "ticker": "AAPL",
            "amount": 1.0,
            "current_value_usd": 400.0,
            "current_value_uah": 16000.0,
            "current_value_eur": 365.0,
            "purchase_date": "2026-02-01",
            "maturity_date": None,
            "notes": "Growth",
            "yield_percent": None,
        },
    ]

    context = build_enriched_portfolio_context(assets, marker="Portfolio")

    assert "Portfolio:" in context
    assert "Total Current Value: $1000 (USD)" in context
    assert "Asset: Криптовалюта (BTC)" in context
    assert "Current Value: $600 (Weight: 60%)." in context
    assert "Asset: Акції/ETF (AAPL)" in context
    assert "Current Value: $400 (Weight: 40%)." in context
    assert "Yield: N/A." in context


def test_build_enriched_portfolio_context_includes_explicit_yield_field_or_notes():
    assets = [
        {
            "asset_type": "ОВДП",
            "ticker": "UA400022",
            "amount": 10.0,
            "current_value_usd": 1000.0,
            "current_value_uah": 40000.0,
            "current_value_eur": 910.0,
            "purchase_date": "2026-01-01",
            "maturity_date": "2027-01-01",
            "notes": "Купон 29% річних",
            "yield_percent": 29.0,
        }
    ]

    context = build_enriched_portfolio_context(assets, marker="Portfolio")
    assert "Yield: 29%." in context
    assert "Notes: Купон 29% річних" in context


def test_build_enriched_portfolio_context_returns_empty_message_for_no_assets():
    context = build_enriched_portfolio_context([], empty_message="No portfolio")
    assert context == "No portfolio"
