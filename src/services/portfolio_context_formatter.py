"""Formatting helpers for injecting enriched portfolio context into prompts."""

from __future__ import annotations

import re
from typing import Any, Optional


def _to_float(value: Any) -> Optional[float]:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_number(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _format_currency(value: Optional[float], currency: str) -> str:
    if value is None:
        return "N/A"
    symbols = {"USD": "$", "UAH": "₴", "EUR": "€"}
    symbol = symbols.get(currency.upper(), currency.upper())
    return f"{symbol}{_format_number(value)}"


def _extract_yield_from_notes(notes: str) -> Optional[str]:
    if not notes:
        return None

    normalized = notes.lower()
    if "%" not in normalized and not any(
        token in normalized for token in ("yield", "дохід", "дохідн", "купон", "ставк")
    ):
        return None

    match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", notes)
    if not match:
        return None
    numeric = match.group(1).replace(",", ".")
    try:
        return f"{float(numeric):.2f}".rstrip("0").rstrip(".") + "%"
    except ValueError:
        return match.group(1) + "%"


def _compute_totals(assets: list[dict[str, Any]]) -> dict[str, Optional[float]]:
    total_uah = 0.0
    total_usd = 0.0
    total_eur = 0.0
    has_uah = False
    has_usd = False
    has_eur = False
    for asset in assets:
        value_uah = _to_float(asset.get("current_value_uah"))
        value_usd = _to_float(asset.get("current_value_usd"))
        value_eur = _to_float(asset.get("current_value_eur"))
        if value_uah is not None:
            total_uah += value_uah
            has_uah = True
        if value_usd is not None:
            total_usd += value_usd
            has_usd = True
        if value_eur is not None:
            total_eur += value_eur
            has_eur = True
    return {
        "UAH": total_uah if has_uah else None,
        "USD": total_usd if has_usd else None,
        "EUR": total_eur if has_eur else None,
    }


def _pick_reporting_currency(totals: dict[str, Optional[float]]) -> str:
    for code in ("USD", "UAH", "EUR"):
        value = _to_float(totals.get(code))
        if value is not None and value > 0:
            return code
    return "USD"


def build_enriched_portfolio_context(
    assets: list[dict[str, Any]],
    *,
    marker: str = "Portfolio",
    empty_message: str = "No user portfolio or notes context provided.",
) -> str:
    if not assets:
        return empty_message

    totals = _compute_totals(assets)
    reporting_currency = _pick_reporting_currency(totals)
    total_global = _to_float(totals.get(reporting_currency))

    lines: list[str] = [
        f"{marker}:",
        (
            "Total Current Value: "
            f"{_format_currency(total_global, reporting_currency)} "
            f"({reporting_currency})"
        ),
    ]

    for asset in assets[:20]:
        asset_type = str(asset.get("asset_type") or "Unknown")
        ticker = str(asset.get("ticker") or asset.get("isin") or "—")
        amount = _to_float(asset.get("amount"))
        notes_raw = str(asset.get("notes") or "").strip()
        notes = notes_raw or "Немає"
        maturity_date = str(asset.get("maturity_date") or "").strip() or "N/A"
        purchase_date = str(asset.get("purchase_date") or "").strip() or "N/A"
        yield_percent = _to_float(asset.get("yield_percent"))
        yield_from_notes = _extract_yield_from_notes(notes_raw)
        if yield_percent is not None:
            yield_label = f"{_format_number(yield_percent)}%"
        elif yield_from_notes:
            yield_label = yield_from_notes
        else:
            yield_label = "N/A"

        current_value_global = _to_float(
            asset.get(f"current_value_{reporting_currency.lower()}")
        )
        weight_percent: Optional[float] = None
        if total_global and total_global > 0 and current_value_global is not None:
            weight_percent = (current_value_global / total_global) * 100

        lines.append(
            "- Asset: "
            f"{asset_type} ({ticker}), "
            f"Quantity: {_format_number(amount)}, "
            f"Current Value: {_format_currency(current_value_global, reporting_currency)} "
            f"(Weight: {_format_number(weight_percent)}%). "
            f"Yield: {yield_label}. "
            f"Purchase Date: {purchase_date}, Maturity Date: {maturity_date}. "
            f"Notes: {notes}"
        )

    return "\n".join(lines)
