"""
Application constants and enumerations.
"""

from enum import Enum
from typing import Final

# ============================================================
# Application Constants
# ============================================================

APP_TITLE: Final[str] = "ЖИТО"
APP_SUBTITLE: Final[str] = "Фінансовий асистент для українських роздрібних інвесторів"

# ============================================================
# Asset Types
# ============================================================


class AssetType(str, Enum):
    """Enumeration of supported asset types."""

    BONDS = "ОВДП"  # Ukrainian Government Bonds
    STOCKS = "Акції"  # Stocks
    REAL_ESTATE = "Нерухомість"  # Real Estate
    CRYPTO = "Криптовалюта"  # Cryptocurrency
    CASH = "Готівка"  # Cash
    DEPOSITS = "Депозити"  # Bank Deposits


# ============================================================
# Currencies
# ============================================================


class Currency(str, Enum):
    """Enumeration of supported currencies."""

    UAH = "UAH"  # Ukrainian Hryvnia
    USD = "USD"  # US Dollar
    EUR = "EUR"  # Euro
    BTC = "BTC"  # Bitcoin
    ETH = "ETH"  # Ethereum


# ============================================================
# Risk Levels
# ============================================================


class RiskLevel(str, Enum):
    """Enumeration of investor risk profiles."""

    CONSERVATIVE = "Консервативний"  # Low risk
    MODERATE = "Помірний"  # Medium risk
    AGGRESSIVE = "Агресивний"  # High risk


# ============================================================
# Market Data Sources
# ============================================================

SUPPORTED_DATA_SOURCES: Final[list[str]] = [
    "Економічна Правда",
    "Ціна Держави (Telegram)",
    "Сімейний Бюджет (YouTube)",
    "Інші видання",
]

# ============================================================
# RAG Configuration
# ============================================================

CHROMA_COLLECTION_NAME: Final[str] = "ukraine_invest_market_context"
DEFAULT_EMBEDDING_MODEL: Final[str] = "text-embedding-3-small"
DEFAULT_LLM_MODEL: Final[str] = "gpt-4o-mini"

# ============================================================
# Pagination
# ============================================================

DEFAULT_PAGE_SIZE: Final[int] = 10
MAX_PAGE_SIZE: Final[int] = 100

# ============================================================
# Timeouts
# ============================================================

API_TIMEOUT_SECONDS: Final[int] = 30
LLM_TIMEOUT_SECONDS: Final[int] = 60
