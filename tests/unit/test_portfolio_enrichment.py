"""Unit tests for portfolio market-data enrichment."""

import pytest

from src.api.routes import portfolio


class StubMarketDataService:
    """Minimal fake market data service used in route-level tests."""

    def __init__(
        self,
        returned_prices: dict[tuple[str, str | None], float | None],
        historical_rates: dict[str, dict[str, float]] | None = None,
    ):
        self.returned_prices = returned_prices
        self.historical_rates = historical_rates or {}

    def get_current_price(self, asset_type: str, ticker: str | None, purchase_price: float | None):
        return self.returned_prices.get((asset_type, ticker), purchase_price)

    @staticmethod
    def get_usd_uah_rate() -> float:
        return 40.0

    @staticmethod
    def get_eur_uah_rate() -> float:
        return 44.0

    def get_usd_uah_rate_for_date(self, date_value: str) -> float:
        date_rates = self.historical_rates.get(date_value, {})
        return float(date_rates.get("usd", 40.0))

    def get_eur_uah_rate_for_date(self, date_value: str) -> float:
        date_rates = self.historical_rates.get(date_value, {})
        return float(date_rates.get("eur", 44.0))

    @staticmethod
    def is_market_traded_asset(asset_type: str) -> bool:
        return asset_type in {"Акції (ETF)", "Криптовалюта"}


def test_enrich_stock_asset_computes_current_value_and_pnl(monkeypatch):
    stub_service = StubMarketDataService({("Акції (ETF)", "AAPL"): 125.0})
    monkeypatch.setattr(portfolio, "get_market_data_service", lambda: stub_service)

    assets = [
        {
            "id": "a1",
            "asset_type": "Акції (ETF)",
            "ticker": "AAPL",
            "amount": 2.0,
            "currency": "USD",
            "purchase_price": 100.0,
            "purchase_date": "2024-01-01",
        }
    ]

    enriched, totals, usd_uah_rate, eur_uah_rate = portfolio._enrich_portfolio_assets(assets)
    item = enriched[0]

    assert item["current_price"] == 125.0
    assert item["purchase_price_usd"] == pytest.approx(100.0)
    assert item["current_price_usd"] == pytest.approx(125.0)
    assert item["invested_value_usd"] == pytest.approx(200.0)
    assert item["current_value"] == 250.0
    assert item["current_value_usd"] == 250.0
    assert item["current_value_uah"] == 10000.0
    assert item["current_value_eur"] == pytest.approx(227.2727272727)
    assert item["pnl_value_usd"] == pytest.approx(50.0)
    assert item["pnl_percent_usd"] == pytest.approx(25.0)
    assert item["pnl_percent"] == pytest.approx(25.0)
    assert totals["usd"] == pytest.approx(250.0)
    assert totals["uah"] == pytest.approx(10000.0)
    assert totals["eur"] == pytest.approx(227.2727272727)
    assert usd_uah_rate == pytest.approx(40.0)
    assert eur_uah_rate == pytest.approx(44.0)


def test_enrich_static_asset_uses_purchase_price_for_mvp(monkeypatch):
    stub_service = StubMarketDataService({})
    monkeypatch.setattr(portfolio, "get_market_data_service", lambda: stub_service)

    assets = [
        {
            "id": "s1",
            "asset_type": "Депозит",
            "amount": 10.0,
            "currency": "UAH",
            "purchase_price": 100.0,
            "purchase_date": "2024-01-01",
        }
    ]

    enriched, totals, _, _ = portfolio._enrich_portfolio_assets(assets)
    item = enriched[0]

    assert item["current_price"] == 100.0
    assert item["current_value"] == 1000.0
    assert item["current_value_uah"] == 1000.0
    assert item["current_value_usd"] == pytest.approx(25.0)
    assert item["current_value_eur"] == pytest.approx(22.7272727272)
    assert item["pnl_percent"] == pytest.approx(0.0)
    assert totals["uah"] == pytest.approx(1000.0)
    assert totals["usd"] == pytest.approx(25.0)
    assert totals["eur"] == pytest.approx(22.7272727272)


def test_enrich_crypto_asset_with_unavailable_price_is_safe(monkeypatch):
    stub_service = StubMarketDataService({("Криптовалюта", "BTC"): None})
    monkeypatch.setattr(portfolio, "get_market_data_service", lambda: stub_service)

    assets = [
        {
            "id": "c1",
            "asset_type": "Криптовалюта",
            "ticker": "BTC",
            "amount": 0.5,
            "currency": "USD",
            "purchase_price": 60000.0,
            "purchase_date": "2024-01-01",
        }
    ]

    enriched, totals, _, _ = portfolio._enrich_portfolio_assets(assets)
    item = enriched[0]

    assert item["current_price"] is None
    assert item["current_value"] is None
    assert item["current_value_uah"] is None
    assert item["current_value_usd"] is None
    assert item["current_value_eur"] is None
    assert item["pnl_value_uah"] is None
    assert item["pnl_value_usd"] is None
    assert item["pnl_value_eur"] is None
    assert item["pnl_percent_uah"] is None
    assert item["pnl_percent_usd"] is None
    assert item["pnl_percent_eur"] is None
    assert item["pnl_percent"] is None
    assert totals["uah"] is None
    assert totals["usd"] is None
    assert totals["eur"] is None


def test_manual_current_price_takes_precedence(monkeypatch):
    stub_service = StubMarketDataService({("Акції (ETF)", "DUOL"): 150.0})
    monkeypatch.setattr(portfolio, "get_market_data_service", lambda: stub_service)

    assets = [
        {
            "id": "m1",
            "asset_type": "Акції (ETF)",
            "ticker": "DUOL",
            "amount": 2.0,
            "currency": "USD",
            "purchase_price": 100.0,
            "purchase_date": "2024-01-01",
            "manual_current_price": 130.0,
        }
    ]

    enriched, totals, _, _ = portfolio._enrich_portfolio_assets(assets)
    item = enriched[0]

    assert item["current_price"] == 130.0
    assert item["current_value"] == 260.0
    assert item["current_value_uah"] == pytest.approx(10400.0)
    assert item["current_value_usd"] == pytest.approx(260.0)
    assert item["current_value_eur"] == pytest.approx(236.3636363636)
    assert item["pnl_value_usd"] == pytest.approx(60.0)
    assert item["pnl_percent_usd"] == pytest.approx(30.0)
    assert item["pnl_percent"] == pytest.approx(30.0)
    assert totals["uah"] == pytest.approx(10400.0)
    assert totals["usd"] == pytest.approx(260.0)
    assert totals["eur"] == pytest.approx(236.3636363636)


def test_totals_are_currency_aware_and_not_raw_mixed_sum(monkeypatch):
    stub_service = StubMarketDataService({("Акції (ETF)", "AAPL"): 25.0})
    monkeypatch.setattr(portfolio, "get_market_data_service", lambda: stub_service)

    assets = [
        {
            "id": "u1",
            "asset_type": "Депозит",
            "amount": 4000.0,
            "currency": "UAH",
            "purchase_price": 1.0,
            "purchase_date": "2024-01-01",
        },
        {
            "id": "u2",
            "asset_type": "Акції (ETF)",
            "ticker": "AAPL",
            "amount": 2.0,
            "currency": "USD",
            "purchase_price": 20.0,
            "purchase_date": "2024-01-01",
        },
    ]

    enriched, totals, _, _ = portfolio._enrich_portfolio_assets(assets)

    assert len(enriched) == 2
    assert totals["uah"] == pytest.approx(6000.0)  # 4000 UAH + (50 USD * 40)
    assert totals["usd"] == pytest.approx(150.0)  # (4000 UAH / 40) + 50 USD
    assert totals["eur"] == pytest.approx(136.3636363636)  # 6000 UAH / 44


def test_enrich_eur_asset_computes_uah_and_usd_values(monkeypatch):
    stub_service = StubMarketDataService({})
    monkeypatch.setattr(portfolio, "get_market_data_service", lambda: stub_service)

    assets = [
        {
            "id": "e1",
            "asset_type": "Готівка",
            "amount": 1000.0,
            "currency": "EUR",
            "purchase_price": 1.0,
            "purchase_date": "2024-01-01",
        }
    ]

    enriched, totals, _, _ = portfolio._enrich_portfolio_assets(assets)
    item = enriched[0]

    assert item["current_price"] == 1.0
    assert item["current_value"] == pytest.approx(1000.0)
    assert item["current_value_eur"] == pytest.approx(1000.0)
    assert item["current_value_uah"] == pytest.approx(44000.0)
    assert item["current_value_usd"] == pytest.approx(1100.0)
    assert totals["eur"] == pytest.approx(1000.0)
    assert totals["uah"] == pytest.approx(44000.0)
    assert totals["usd"] == pytest.approx(1100.0)


def test_global_pnl_uses_historical_purchase_fx_and_live_current_fx(monkeypatch):
    stub_service = StubMarketDataService(
        returned_prices={("Акції (ETF)", "SAP"): 100.0},
        historical_rates={
            "2024-01-01": {"usd": 39.0, "eur": 40.0},
        },
    )
    monkeypatch.setattr(portfolio, "get_market_data_service", lambda: stub_service)

    assets = [
        {
            "id": "fx1",
            "asset_type": "Акції (ETF)",
            "ticker": "SAP",
            "amount": 1.0,
            "currency": "EUR",
            "purchase_price": 100.0,
            "purchase_date": "2024-01-01",
        }
    ]

    enriched, totals, _, _ = portfolio._enrich_portfolio_assets(assets)
    item = enriched[0]

    # Native prices unchanged, but global PnL should still reflect FX changes:
    # invested_usd = 100 EUR * 40 UAH / 39 = 102.564...
    # current_usd = 100 EUR * 44 UAH / 40 = 110
    assert item["invested_value_usd"] == pytest.approx(102.5641025641)
    assert item["current_value_usd"] == pytest.approx(110.0)
    assert item["pnl_value_usd"] == pytest.approx(7.4358974359)
    assert item["pnl_percent_usd"] == pytest.approx(7.25)
    assert totals["usd"] == pytest.approx(110.0)


def test_calculate_pnl_percent_handles_zero_purchase_price():
    assert portfolio._calculate_pnl_percent(0, 100) is None


def test_cash_asset_bought_today_uses_live_fx_for_purchase_valuation(monkeypatch):
    today = portfolio.date.today().isoformat()
    stub_service = StubMarketDataService(
        returned_prices={},
        historical_rates={
            today: {"usd": 39.0, "eur": 43.0},
        },
    )
    monkeypatch.setattr(portfolio, "get_market_data_service", lambda: stub_service)

    assets = [
        {
            "id": "cash-today-1",
            "asset_type": "Готівка",
            "amount": 1000.0,
            "currency": "EUR",
            "purchase_price": 1.0,
            "purchase_date": today,
        }
    ]

    enriched, _, _, _ = portfolio._enrich_portfolio_assets(assets)
    item = enriched[0]

    # For day-zero cash, purchase FX is aligned to live FX (USD=40, EUR=44).
    assert item["invested_value_uah"] == pytest.approx(44000.0)
    assert item["current_value_uah"] == pytest.approx(44000.0)
    assert item["invested_value_usd"] == pytest.approx(1100.0)
    assert item["current_value_usd"] == pytest.approx(1100.0)
    assert item["pnl_value_usd"] == pytest.approx(0.0)
    assert item["pnl_percent_usd"] == pytest.approx(0.0)
