"""Unit tests for chat market price tool executor."""

from src.rag import market_price_tool


class StubMarketDataService:
    def is_market_traded_asset(self, asset_type: str) -> bool:
        return asset_type in {"Акції (ETF)", "Криптовалюта"}

    def get_current_price(self, asset_type: str, ticker=None, purchase_price=None):
        if asset_type == "Акції (ETF)" and ticker == "DUOL":
            return 151.25
        if asset_type == "Криптовалюта" and ticker == "BTC":
            return 69000.0
        if asset_type == "Депозит":
            return purchase_price
        return None


def test_tool_requires_asset_type():
    result = market_price_tool.execute_get_current_market_price({})
    assert result["ok"] is False
    assert result["error_code"] == "missing_asset_type"


def test_tool_requires_ticker_for_market_assets(monkeypatch):
    monkeypatch.setattr(market_price_tool, "get_market_data_service", lambda: StubMarketDataService())
    result = market_price_tool.execute_get_current_market_price({"asset_type": "Акції (ETF)"})
    assert result["ok"] is False
    assert result["error_code"] == "missing_ticker"


def test_tool_returns_structured_stock_price(monkeypatch):
    monkeypatch.setattr(market_price_tool, "get_market_data_service", lambda: StubMarketDataService())
    result = market_price_tool.execute_get_current_market_price(
        {"asset_type": "Акції (ETF)", "ticker": "duol"}
    )
    assert result["ok"] is True
    assert result["ticker"] == "DUOL"
    assert result["current_price"] == 151.25
    assert result["source"] == "yfinance"


def test_tool_returns_static_fallback_without_fabrication(monkeypatch):
    monkeypatch.setattr(market_price_tool, "get_market_data_service", lambda: StubMarketDataService())
    result = market_price_tool.execute_get_current_market_price(
        {"asset_type": "Депозит", "purchase_price": 1000.0, "currency": "UAH"}
    )
    assert result["ok"] is True
    assert result["current_price"] == 1000.0
    assert result["source"] == "static_fallback"
    assert result["currency"] == "UAH"
