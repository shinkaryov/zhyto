"""Unit tests for portfolio draft tool behavior."""

from datetime import date, timedelta

from src.rag.portfolio_draft_tool import execute_draft_portfolio_transaction


def test_draft_tool_returns_pending_draft_with_required_fields():
    result = execute_draft_portfolio_transaction(
        {
            "asset_type": "Акції (ETF)",
            "amount": 3,
            "currency": "USD",
            "purchase_price": 200,
            "ticker": "aapl",
        }
    )

    assert result["ok"] is True
    assert result["type"] == "pending_transaction_draft"
    draft = result["pending_transaction_draft"]
    assert isinstance(draft, dict)
    assert draft["asset_type"] == "Акції (ETF)"
    assert draft["amount"] == 3.0
    assert draft["currency"] == "USD"
    assert draft["purchase_price"] == 200.0
    assert draft["ticker"] == "AAPL"
    assert "purchase_date" in draft


def test_draft_tool_drops_synthetic_english_notes():
    result = execute_draft_portfolio_transaction(
        {
            "asset_type": "Акції (ETF)",
            "amount": 3,
            "currency": "USD",
            "notes": "User bought 3 Apple shares for 600 USD",
        }
    )

    assert result["ok"] is True
    draft = result["pending_transaction_draft"]
    assert isinstance(draft, dict)
    assert "notes" not in draft


def test_draft_tool_keeps_user_note_when_not_synthetic():
    result = execute_draft_portfolio_transaction(
        {
            "asset_type": "Депозит",
            "amount": 1000,
            "currency": "EUR",
            "notes": "Довгострокова частина заощаджень",
        }
    )

    assert result["ok"] is True
    draft = result["pending_transaction_draft"]
    assert isinstance(draft, dict)
    assert draft.get("notes") == "Довгострокова частина заощаджень"


def test_draft_tool_derives_unit_price_from_total_value():
    result = execute_draft_portfolio_transaction(
        {
            "asset_type": "Акції (ETF)",
            "amount": 20,
            "currency": "USD",
            "ticker": "TSLA",
            "total_value": 4000,
        }
    )

    assert result["ok"] is True
    draft = result["pending_transaction_draft"]
    assert isinstance(draft, dict)
    assert draft["purchase_price"] == 200.0
    assert draft["total_value"] == 4000.0


def test_draft_tool_resolves_yesterday_date_keyword():
    result = execute_draft_portfolio_transaction(
        {
            "asset_type": "Готівка",
            "amount": 1000,
            "currency": "EUR",
            "purchase_date": "вчора",
        }
    )

    assert result["ok"] is True
    draft = result["pending_transaction_draft"]
    assert isinstance(draft, dict)
    assert draft["purchase_date"] == (date.today() - timedelta(days=1)).isoformat()
