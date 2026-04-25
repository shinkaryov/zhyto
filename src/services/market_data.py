"""
Market data retrieval service for portfolio enrichment.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Optional
from urllib.parse import quote
from urllib.request import Request, urlopen

from src.utils import get_logger

logger = get_logger(__name__)

COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
COINGECKO_TIMEOUT_SECONDS = 8
DEFAULT_CACHE_TTL_SECONDS = 20 * 60  # 20 minutes
NBU_USD_UAH_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=USD&json"
NBU_EUR_UAH_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=EUR&json"
NBU_FX_URL_TEMPLATE = (
    "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?"
    "valcode={valcode}&date={yyyymmdd}&json"
)

STOCK_ASSET_TYPES = {"Акції", "Акції (ETF)", "ETF", "Stocks"}
CRYPTO_ASSET_TYPES = {"Криптовалюта", "Crypto"}
STATIC_ASSET_TYPES = {
    "ОВДП",
    "Корпоративні облігації",
    "Нерухомість",
    "Фонди нерухомості (Inzhur, REITs)",
    "Земля",
    "Готівка",
    "Депозит",
}

_CRYPTO_SYMBOL_TO_COINGECKO_ID = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDT": "tether",
    "USDC": "usd-coin",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "DOT": "polkadot",
    "TRX": "tron",
    "AVAX": "avalanche-2",
    "MATIC": "matic-network",
    "LTC": "litecoin",
    "LINK": "chainlink",
    "BCH": "bitcoin-cash",
    "XLM": "stellar",
    "ATOM": "cosmos",
    "ETC": "ethereum-classic",
    "FIL": "filecoin",
}


@dataclass
class _CacheEntry:
    value: float
    expires_at: datetime


class MarketDataService:
    """Market data service with simple in-memory TTL caching."""

    def __init__(self, cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS):
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, _CacheEntry] = {}
        self._last_successful_values: dict[str, float] = {}
        self._cache_lock = threading.Lock()
        self._crypto_symbol_to_id = dict(_CRYPTO_SYMBOL_TO_COINGECKO_ID)

    def is_market_traded_asset(self, asset_type: str) -> bool:
        """Check if asset type should be resolved from an external market API."""
        normalized_asset_type = (asset_type or "").strip()
        return normalized_asset_type in STOCK_ASSET_TYPES or normalized_asset_type in CRYPTO_ASSET_TYPES

    def get_stock_price(self, ticker: str) -> Optional[float]:
        """Return latest stock/ETF price from yfinance."""
        normalized_ticker = self._normalize_ticker(ticker)
        if not normalized_ticker:
            return None

        cache_key = self._build_cache_key("yfinance", normalized_ticker)
        cached_price = self._get_cached_price(cache_key)
        if cached_price is not None:
            return cached_price

        price = self._fetch_stock_price(normalized_ticker)
        if price is not None:
            self._set_cached_price(cache_key, price)
        return price

    def get_crypto_price(self, ticker: str) -> Optional[float]:
        """Return latest crypto spot price (USD) from CoinGecko."""
        normalized_symbol = self._normalize_crypto_symbol(ticker)
        if not normalized_symbol:
            return None

        cache_key = self._build_cache_key("coingecko", normalized_symbol)
        cached_price = self._get_cached_price(cache_key)
        if cached_price is not None:
            return cached_price

        coin_id = self._resolve_crypto_coin_id(normalized_symbol)
        if not coin_id:
            logger.warning("CoinGecko coin id could not be resolved for symbol '%s'", normalized_symbol)
            return None

        price = self._fetch_crypto_price_by_id(coin_id)
        if price is not None:
            self._set_cached_price(cache_key, price)
        return price

    def get_current_price(
        self,
        asset_type: str,
        ticker: Optional[str] = None,
        purchase_price: Optional[float] = None,
    ) -> Optional[float]:
        """
        Resolve current price based on asset type.

        Stocks/ETFs -> yfinance
        Crypto -> CoinGecko
        Static/non-market assets -> purchase_price fallback
        """
        normalized_asset_type = (asset_type or "").strip()
        purchase_price_value = self._to_float(purchase_price)

        if normalized_asset_type in STOCK_ASSET_TYPES:
            if not ticker:
                logger.warning("Ticker is missing for stock/ETF asset type '%s'", normalized_asset_type)
                return None
            return self.get_stock_price(ticker)

        if normalized_asset_type in CRYPTO_ASSET_TYPES:
            if not ticker:
                logger.warning("Ticker is missing for crypto asset type '%s'", normalized_asset_type)
                return None
            return self.get_crypto_price(ticker)

        if normalized_asset_type in STATIC_ASSET_TYPES:
            return purchase_price_value

        # Unknown asset types are treated as static for MVP safety.
        return purchase_price_value

    def get_usd_uah_rate(self) -> Optional[float]:
        """Return USD/UAH exchange rate with cache + stale fallback."""
        return self._get_nbu_fx_rate("USD", date_value=None)

    def get_eur_uah_rate(self) -> Optional[float]:
        """Return EUR/UAH exchange rate with cache + stale fallback."""
        return self._get_nbu_fx_rate("EUR", date_value=None)

    def get_usd_uah_rate_for_date(self, date_value: str) -> Optional[float]:
        """Return USD/UAH historical rate for provided YYYY-MM-DD date."""
        return self._get_nbu_fx_rate("USD", date_value=date_value)

    def get_eur_uah_rate_for_date(self, date_value: str) -> Optional[float]:
        """Return EUR/UAH historical rate for provided YYYY-MM-DD date."""
        return self._get_nbu_fx_rate("EUR", date_value=date_value)

    def _fetch_stock_price(self, ticker: str) -> Optional[float]:
        """Fetch stock price from yfinance with a pragmatic fallback chain."""
        try:
            import yfinance as yf
        except ImportError:
            logger.error("yfinance is not installed; cannot resolve stock price for '%s'", ticker)
            return None

        try:
            yf_ticker = yf.Ticker(ticker)

            fast_info = getattr(yf_ticker, "fast_info", {}) or {}
            for candidate in (
                fast_info.get("last_price"),
                fast_info.get("regularMarketPrice"),
                fast_info.get("previous_close"),
            ):
                price = self._to_positive_float(candidate)
                if price is not None:
                    return price

            info = getattr(yf_ticker, "info", {}) or {}
            for candidate in (
                info.get("regularMarketPrice"),
                info.get("currentPrice"),
                info.get("previousClose"),
            ):
                price = self._to_positive_float(candidate)
                if price is not None:
                    return price

            history = yf_ticker.history(period="1d")
            if history is not None and not history.empty:
                close_series = history.get("Close")
                if close_series is not None and not close_series.empty:
                    price = self._to_positive_float(close_series.iloc[-1])
                    if price is not None:
                        return price

            logger.warning("No stock market price returned by yfinance for ticker '%s'", ticker)
            return None
        except Exception as exc:
            logger.warning("Failed to fetch stock price for '%s': %s", ticker, exc, exc_info=True)
            return None

    def _resolve_crypto_coin_id(self, symbol: str) -> Optional[str]:
        """Resolve a CoinGecko coin id from a ticker symbol."""
        normalized_symbol = self._normalize_crypto_symbol(symbol)
        if not normalized_symbol:
            return None

        mapped_id = self._crypto_symbol_to_id.get(normalized_symbol)
        if mapped_id:
            return mapped_id

        try:
            payload = self._fetch_json(
                f"{COINGECKO_BASE_URL}/search?query={quote(normalized_symbol)}"
            )
            if not payload:
                return None

            coins = payload.get("coins", [])
            if not coins:
                return None

            # First try exact symbol match, then fallback to top search result.
            for coin in coins:
                coin_symbol = str(coin.get("symbol", "")).upper()
                if coin_symbol == normalized_symbol:
                    coin_id = coin.get("id")
                    if coin_id:
                        self._crypto_symbol_to_id[normalized_symbol] = coin_id
                        return coin_id

            fallback_coin_id = coins[0].get("id")
            if fallback_coin_id:
                self._crypto_symbol_to_id[normalized_symbol] = fallback_coin_id
                return fallback_coin_id

            return None
        except Exception as exc:
            logger.warning(
                "Failed to resolve CoinGecko id for symbol '%s': %s",
                normalized_symbol,
                exc,
                exc_info=True,
            )
            return None

    def _fetch_crypto_price_by_id(self, coin_id: str) -> Optional[float]:
        """Fetch crypto USD spot price by CoinGecko coin id."""
        payload = self._fetch_json(
            f"{COINGECKO_BASE_URL}/simple/price?ids={quote(coin_id)}&vs_currencies=usd"
        )
        if not payload:
            return None

        coin_payload = payload.get(coin_id, {})
        raw_price = coin_payload.get("usd")
        price = self._to_positive_float(raw_price)
        if price is None:
            logger.warning("No USD price in CoinGecko response for coin id '%s'", coin_id)
        return price

    def _fetch_json(self, url: str) -> Optional[dict[str, Any]]:
        """Fetch JSON safely from public APIs."""
        try:
            request = Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "zhyto-market-data-service/1.0",
                },
            )
            with urlopen(request, timeout=COINGECKO_TIMEOUT_SECONDS) as response:
                payload = response.read().decode("utf-8")
                parsed = json.loads(payload)
                if isinstance(parsed, dict):
                    return parsed
                return None
        except Exception as exc:
            logger.warning("HTTP market data request failed for '%s': %s", url, exc)
            return None

    def _fetch_usd_uah_rate_from_nbu(self) -> Optional[float]:
        """Fetch USD/UAH from NBU public API."""
        return self._fetch_nbu_fx_rate("USD", yyyymmdd=None)

    def _fetch_eur_uah_rate_from_nbu(self) -> Optional[float]:
        """Fetch EUR/UAH from NBU public API."""
        return self._fetch_nbu_fx_rate("EUR", yyyymmdd=None)

    def _fetch_nbu_fx_rate(self, valcode: str, yyyymmdd: Optional[str]) -> Optional[float]:
        """Fetch FX rate from NBU public API, with optional historical date."""
        normalized_valcode = (valcode or "").strip().upper()
        if normalized_valcode not in {"USD", "EUR"}:
            logger.warning("Unsupported NBU FX valcode '%s'", valcode)
            return None

        if yyyymmdd:
            url = NBU_FX_URL_TEMPLATE.format(valcode=normalized_valcode, yyyymmdd=yyyymmdd)
        elif normalized_valcode == "USD":
            url = NBU_USD_UAH_URL
        else:
            url = NBU_EUR_UAH_URL

        try:
            request = Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "zhyto-market-data-service/1.0",
                },
            )
            with urlopen(request, timeout=COINGECKO_TIMEOUT_SECONDS) as response:
                payload = response.read().decode("utf-8")
                parsed = json.loads(payload)
                if not isinstance(parsed, list) or not parsed:
                    return None

                first_item = parsed[0]
                if not isinstance(first_item, dict):
                    return None

                rate = self._to_positive_float(first_item.get("rate"))
                if rate is None:
                    logger.warning(
                        "%s/UAH rate missing in NBU response payload for date='%s'",
                        normalized_valcode,
                        yyyymmdd or "LIVE",
                    )
                return rate
        except Exception as exc:
            logger.warning(
                "Failed to fetch %s/UAH rate from NBU for date='%s': %s",
                normalized_valcode,
                yyyymmdd or "LIVE",
                exc,
            )
            return None

    def _get_nbu_fx_rate(self, valcode: str, date_value: Optional[str]) -> Optional[float]:
        """Get FX rate with TTL cache and stale fallback."""
        normalized_valcode = (valcode or "").strip().upper()
        yyyymmdd = self._normalize_rate_date(date_value)
        date_part = yyyymmdd or "LIVE"
        cache_key = self._build_cache_key("fx", f"{normalized_valcode}UAH:{date_part}")

        cached_rate = self._get_cached_price(cache_key)
        if cached_rate is not None:
            return cached_rate

        fetched_rate = self._fetch_nbu_fx_rate(normalized_valcode, yyyymmdd=yyyymmdd)
        if fetched_rate is not None:
            self._set_cached_price(cache_key, fetched_rate)
            return fetched_rate

        stale_rate = self._get_last_successful_value(cache_key)
        if stale_rate is not None:
            logger.warning(
                "Using last cached %s/UAH rate for date='%s' due to live fetch failure: %s",
                normalized_valcode,
                date_part,
                stale_rate,
            )
            return stale_rate

        logger.warning(
            "%s/UAH rate unavailable for date='%s' and no cached fallback exists",
            normalized_valcode,
            date_part,
        )
        return None

    def _build_cache_key(self, source: str, ticker: str) -> str:
        return f"{source}:{ticker.strip().upper()}"

    def _get_cached_price(self, key: str) -> Optional[float]:
        now = datetime.now(timezone.utc)
        with self._cache_lock:
            cache_entry = self._cache.get(key)
            if not cache_entry:
                return None
            if cache_entry.expires_at <= now:
                self._cache.pop(key, None)
                return None
            return cache_entry.value

    def _set_cached_price(self, key: str, value: float) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.cache_ttl_seconds)
        with self._cache_lock:
            self._cache[key] = _CacheEntry(value=value, expires_at=expires_at)
            self._last_successful_values[key] = value

    def _get_last_successful_value(self, key: str) -> Optional[float]:
        with self._cache_lock:
            return self._last_successful_values.get(key)

    @staticmethod
    def _normalize_ticker(ticker: Optional[str]) -> Optional[str]:
        if not ticker:
            return None
        normalized = ticker.strip().upper()
        return normalized or None

    @staticmethod
    def _normalize_crypto_symbol(symbol: Optional[str]) -> Optional[str]:
        if not symbol:
            return None
        normalized = symbol.strip().upper()
        if normalized.endswith("-USD"):
            normalized = normalized[:-4]
        return normalized or None

    @staticmethod
    def _normalize_rate_date(value: Optional[str]) -> Optional[str]:
        """Normalize YYYY-MM-DD or YYYYMMDD to YYYYMMDD for NBU API."""
        if value in (None, "", "None"):
            return None
        raw = str(value).strip()
        if not raw:
            return None
        try:
            if len(raw) == 10:
                parsed = datetime.strptime(raw, "%Y-%m-%d").date()
            elif len(raw) == 8:
                parsed = datetime.strptime(raw, "%Y%m%d").date()
            else:
                return None
            return parsed.strftime("%Y%m%d")
        except ValueError:
            return None

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value in (None, "", "None"):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_positive_float(value: Any) -> Optional[float]:
        parsed = MarketDataService._to_float(value)
        if parsed is None or parsed <= 0:
            return None
        return parsed


@lru_cache(maxsize=1)
def get_market_data_service() -> MarketDataService:
    """Return singleton market data service instance."""
    return MarketDataService()
