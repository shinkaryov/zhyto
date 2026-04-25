"""
Tests for database components.
"""

from src.db.cosmos_client import CosmosDBClient
from src.db.models import PortfolioAsset, UserNote, UserProfile


class TestCosmosDBClient:
    """Test Cosmos DB client."""

    def test_cosmos_mock_initialization(self):
        """Test Cosmos DB client with mock mode."""
        client = CosmosDBClient(use_mock=True)
        assert client.use_mock is True

    def test_cosmos_is_ready(self):
        """Test Cosmos DB readiness."""
        client = CosmosDBClient(use_mock=True)
        assert client.is_ready() is True

    def test_create_user(self):
        """Test creating a user."""
        client = CosmosDBClient(use_mock=True)
        user_data = {"id": "user_123", "email": "test@example.com", "name": "Test User"}
        result = client.create_user(user_data)
        assert result["id"] == "user_123"

    def test_get_user(self):
        """Test getting a user."""
        client = CosmosDBClient(use_mock=True)
        user = client.get_user("user_123")
        assert user is not None
        assert user["id"] == "user_123"

    def test_add_note(self):
        """Test adding a note."""
        client = CosmosDBClient(use_mock=True)
        note_data = {"user_id": "user_123", "content": "Test note"}
        result = client.add_note(note_data)
        assert result["user_id"] == "user_123"

    def test_get_user_notes(self):
        """Test getting user notes."""
        client = CosmosDBClient(use_mock=True)
        notes = client.get_user_notes("user_123", limit=10)
        assert isinstance(notes, list)

    def test_update_portfolio_manual_price(self):
        """Test setting and clearing manual current price for a portfolio asset."""
        client = CosmosDBClient(use_mock=True)
        added = client.add_portfolio_asset(
            {
                "user_id": "user_test_manual_price",
                "asset_type": "Акції (ETF)",
                "amount": 2,
                "currency": "USD",
                "purchase_price": 100,
                "purchase_date": "2026-01-01",
                "ticker": "DUOL",
            }
        )

        updated = client.update_portfolio_manual_price(
            asset_id=added["id"],
            user_id="user_test_manual_price",
            manual_current_price=125.5,
        )
        assert updated is not None
        assert updated["manual_current_price"] == 125.5

        cleared = client.update_portfolio_manual_price(
            asset_id=added["id"],
            user_id="user_test_manual_price",
            manual_current_price=None,
        )
        assert cleared is not None
        assert "manual_current_price" not in cleared


class TestDatabaseModels:
    """Test database models."""

    def test_user_note_model(self):
        """Test UserNote model."""
        note = UserNote(
            user_id="user_123", content="Test note", tags=["finance", "planning"]
        )
        assert note.user_id == "user_123"
        assert note.content == "Test note"
        assert len(note.tags) == 2

    def test_portfolio_asset_model(self):
        """Test PortfolioAsset model."""
        from datetime import datetime
        from src.core.constants import AssetType, Currency

        asset = PortfolioAsset(
            user_id="user_123",
            asset_type=AssetType.BONDS,
            amount=5000.0,
            currency=Currency.UAH,
            purchase_date=datetime.now(),
        )
        assert asset.user_id == "user_123"
        assert asset.asset_type == AssetType.BONDS
        assert asset.amount == 5000.0

    def test_user_profile_model(self):
        """Test UserProfile model."""
        from src.core.constants import RiskLevel

        profile = UserProfile(
            id="user_123",
            email="test@example.com",
            name="Test User",
            risk_level=RiskLevel.MODERATE,
            investment_experience="intermediate",
        )
        assert profile.id == "user_123"
        assert profile.email == "test@example.com"
