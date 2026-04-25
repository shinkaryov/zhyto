"""Unit tests for portfolio transaction follow-up helpers."""

from datetime import date, timedelta

from src.rag.portfolio_transaction_followup import (
    bootstrap_pending_transaction_from_user_message,
    build_confirmation_message,
    complete_pending_draft_from_interpretation,
    detect_price_interpretation_answer,
    is_pending_draft_waiting_price_interpretation,
    is_price_clarification_prompt,
)


def test_bootstrap_pending_draft_from_user_message():
    draft = bootstrap_pending_transaction_from_user_message(
        "Вчора купив 20 акцій TSLA за 4000 доларів"
    )

    assert isinstance(draft, dict)
    assert draft["intent"] == "portfolio_transaction"
    assert draft["asset_type"] == "Акції (ETF)"
    assert draft["ticker"] == "TSLA"
    assert draft["amount"] == 20.0
    assert draft["currency"] == "USD"
    assert draft["ambiguous_price"] == 4000.0
    assert draft["price_interpretation"] == "unknown"
    assert draft["purchase_date"] == (date.today() - timedelta(days=1)).isoformat()


def test_detect_price_interpretation_supports_total_aliases():
    assert detect_price_interpretation_answer("тотал") == "total"
    assert detect_price_interpretation_answer("Загальна сума") == "total"
    assert detect_price_interpretation_answer("total") == "total"
    assert detect_price_interpretation_answer("за акцію") == "per_unit"


def test_complete_pending_draft_from_total_interpretation():
    base_draft = {
        "intent": "portfolio_transaction",
        "asset_type": "Акції (ETF)",
        "ticker": "TSLA",
        "amount": 20,
        "currency": "USD",
        "purchase_date": "2026-04-23",
        "ambiguous_price": 4000,
        "price_interpretation": "unknown",
    }

    assert is_pending_draft_waiting_price_interpretation(base_draft) is True
    completed = complete_pending_draft_from_interpretation(base_draft, "total")
    assert isinstance(completed, dict)
    assert completed["purchase_price"] == 200.0
    assert completed["total_value"] == 4000.0
    assert completed["price_interpretation"] == "total"


def test_build_confirmation_message_for_completed_draft():
    message = build_confirmation_message(
        {
            "asset_type": "Акції (ETF)",
            "ticker": "TSLA",
            "amount": 20,
            "currency": "USD",
            "purchase_price": 200,
            "total_value": 4000,
        },
        language="uk",
    )
    assert "20 TSLA" in message
    assert "$200" in message
    assert "$4000" in message
    assert "Додати в портфель?" in message


def test_recognizes_clarification_prompt():
    assert (
        is_price_clarification_prompt(
            "4000 доларів — це загальна сума угоди чи ціна за 1 акцію?"
        )
        is True
    )
