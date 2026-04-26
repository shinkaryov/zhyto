"""
Azure Cosmos DB client wrapper for user data operations with Local Mock support.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.utils.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CosmosDBClient:
    """Wrapper for Azure Cosmos DB operations."""

    def __init__(self, use_mock: Optional[bool] = None):
        """
        Initialize Cosmos DB client.

        Args:
            use_mock: Whether to use mock database. Defaults to settings.use_mock_cosmos.
        """
        self.use_mock = use_mock if use_mock is not None else settings.use_mock_cosmos
        configured_mock_path = os.getenv(
            "LOCAL_COSMOS_MOCK_FILE", "local_cosmos_db.json"
        )
        self.mock_file = self._resolve_mock_file_path(configured_mock_path)

        self.client = None
        self.database = None
        self.users_container = None
        self.notes_container = None
        self.portfolio_container = None
        self.chat_container = None

        if self.use_mock:
            self._init_local_db()
            logger.info("Using Local JSON Mock for Cosmos DB")
        else:
            self._initialize()

    def _init_local_db(self) -> None:
        """Initialize the local JSON file for mocking the database."""
        mock_path = Path(self.mock_file)
        mock_path.parent.mkdir(parents=True, exist_ok=True)
        if not mock_path.exists():
            initial_data = {
                "users": [],
                "notes": [],
                "portfolio": [],
                "chat_history": [],
            }
            with open(mock_path, "w", encoding="utf-8") as f:
                json.dump(initial_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Initialized local Cosmos mock DB at '{mock_path}'")

    @staticmethod
    def _resolve_mock_file_path(raw_path: str) -> str:
        """Resolve a safe JSON file path even when the configured path is a directory."""
        path = Path(raw_path)
        if path.exists() and path.is_dir():
            return str(path / "mock_cosmos_db.json")
        if path.suffix.lower() != ".json":
            return str(path / "mock_cosmos_db.json")
        return str(path)

    def _read_local_db(self) -> dict:
        """Read data from the local JSON file."""
        try:
            with open(self.mock_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read local DB: {e}")
            return {"users": [], "notes": [], "portfolio": [], "chat_history": []}

    def _write_local_db(self, data: dict) -> None:
        """Write data to the local JSON file."""
        try:
            with open(self.mock_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to write local DB: {e}")

    def _initialize(self) -> None:
        """Initialize Azure Cosmos DB client and containers."""
        try:
            from azure.cosmos import CosmosClient

            self.client = CosmosClient.from_connection_string(
                settings.cosmos_db_connection_string
            )

            self.database = self.client.get_database_client("ukraine_invest_db")
            self.users_container = self.database.get_container_client("users")
            self.notes_container = self.database.get_container_client("user_notes")
            self.portfolio_container = self.database.get_container_client(
                "portfolio_assets"
            )
            self.chat_container = self.database.get_container_client("chat_history")

            logger.info("Cosmos DB initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Cosmos DB: {e}")
            if settings.allow_mock_fallback():
                logger.warning("Falling back to mock database")
                self.use_mock = True
                self._init_local_db()
                return
            logger.critical(
                "Cosmos DB unavailable in production and mock fallback is disabled."
            )
            raise RuntimeError(
                "Cosmos DB initialization failed and mock fallback is disabled."
            ) from e

    def is_ready(self) -> bool:
        """Check if Cosmos DB is ready for operations."""
        if self.use_mock:
            return True
        return self.database is not None

    def create_user(self, user_data: dict) -> dict:
        if self.use_mock:
            db = self._read_local_db()
            if "id" not in user_data:
                user_data["id"] = str(uuid.uuid4())
            db["users"].append(user_data)
            self._write_local_db(db)
            return user_data

        try:
            return self.users_container.create_item(body=user_data)
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            raise

    def get_user(self, user_id: str) -> Optional[dict]:
        if self.use_mock:
            db = self._read_local_db()
            for user in db.get("users", []):
                if user.get("id") == user_id:
                    return user
            return None

        try:
            return self.users_container.read_item(item=user_id, partition_key=user_id)
        except Exception as e:
            logger.warning(f"User not found: {e}")
            return None

    def upsert_user(self, user_data: dict) -> dict:
        """Create or update a user profile record."""
        if self.use_mock:
            db = self._read_local_db()
            if "id" not in user_data:
                user_data["id"] = str(uuid.uuid4())

            replaced = False
            users = db.get("users", [])
            for index, existing in enumerate(users):
                if existing.get("id") == user_data.get("id"):
                    users[index] = user_data
                    replaced = True
                    break
            if not replaced:
                users.append(user_data)

            db["users"] = users
            self._write_local_db(db)
            return user_data

        try:
            return self.users_container.upsert_item(body=user_data)
        except Exception as e:
            logger.error(f"Failed to upsert user: {e}")
            raise

    def add_note(self, note_data: dict) -> dict:
        if self.use_mock:
            db = self._read_local_db()
            note_data["id"] = str(uuid.uuid4())
            note_data["created_at"] = datetime.utcnow().isoformat()
            db["notes"].append(note_data)
            self._write_local_db(db)
            return note_data

        try:
            return self.notes_container.create_item(body=note_data)
        except Exception as e:
            logger.error(f"Failed to add note: {e}")
            raise

    def get_user_notes(self, user_id: str, limit: int = 10) -> list[dict]:
        if self.use_mock:
            db = self._read_local_db()
            user_notes = [n for n in db.get("notes", []) if n.get("user_id") == user_id]
            user_notes.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            return user_notes[:limit]

        try:
            query = (
                "SELECT * FROM c WHERE c.user_id = @user_id ORDER BY c.created_at DESC"
            )
            return list(
                self.notes_container.query_items(
                    query=query,
                    parameters=[{"name": "@user_id", "value": user_id}],
                    max_item_count=limit,
                )
            )
        except Exception as e:
            logger.error(f"Failed to get user notes: {e}")
            return []

    def add_portfolio_asset(self, asset_data: dict) -> dict:
        if self.use_mock:
            db = self._read_local_db()
            asset_data["id"] = str(uuid.uuid4())
            asset_data["created_at"] = datetime.utcnow().isoformat()
            db["portfolio"].append(asset_data)
            self._write_local_db(db)
            return asset_data

        try:
            return self.portfolio_container.create_item(body=asset_data)
        except Exception as e:
            logger.error(f"Failed to add portfolio asset: {e}")
            raise

    def get_user_portfolio(self, user_id: str) -> list[dict]:
        if self.use_mock:
            db = self._read_local_db()
            assets = [a for a in db.get("portfolio", []) if a.get("user_id") == user_id]
            assets.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            return assets

        try:
            query = "SELECT * FROM c WHERE c.user_id = @user_id"
            return list(
                self.portfolio_container.query_items(
                    query=query,
                    parameters=[{"name": "@user_id", "value": user_id}],
                )
            )
        except Exception as e:
            logger.error(f"Failed to get user portfolio: {e}")
            return []

    def delete_note(self, note_id: str, user_id: str) -> bool:
        """Delete a note by ID for a specific user."""
        if self.use_mock:
            db = self._read_local_db()
            original_count = len(db.get("notes", []))
            db["notes"] = [
                n
                for n in db.get("notes", [])
                if not (n.get("id") == note_id and n.get("user_id") == user_id)
            ]
            if len(db["notes"]) < original_count:
                self._write_local_db(db)
                logger.info(f"Note {note_id} deleted successfully")
                return True
            logger.warning(f"Note {note_id} not found")
            return False

        try:
            self.notes_container.delete_item(item=note_id, partition_key=user_id)
            logger.info(f"Note {note_id} deleted successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to delete note: {e}")
            return False

    def delete_portfolio_asset(self, asset_id: str, user_id: str) -> bool:
        """Delete a portfolio asset by ID for a specific user."""
        if self.use_mock:
            db = self._read_local_db()
            original_count = len(db.get("portfolio", []))
            db["portfolio"] = [
                a
                for a in db.get("portfolio", [])
                if not (a.get("id") == asset_id and a.get("user_id") == user_id)
            ]
            if len(db["portfolio"]) < original_count:
                self._write_local_db(db)
                logger.info(f"Portfolio asset {asset_id} deleted successfully")
                return True
            logger.warning(f"Portfolio asset {asset_id} not found")
            return False

        try:
            self.portfolio_container.delete_item(item=asset_id, partition_key=user_id)
            logger.info(f"Portfolio asset {asset_id} deleted successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to delete portfolio asset: {e}")
            return False

    def update_portfolio_manual_price(
        self,
        asset_id: str,
        user_id: str,
        manual_current_price: Optional[float],
    ) -> Optional[dict]:
        """Set or clear manual current price for a portfolio asset."""
        if self.use_mock:
            db = self._read_local_db()
            for asset in db.get("portfolio", []):
                if asset.get("id") == asset_id and asset.get("user_id") == user_id:
                    if manual_current_price is None:
                        asset.pop("manual_current_price", None)
                    else:
                        asset["manual_current_price"] = manual_current_price
                    asset["updated_at"] = datetime.utcnow().isoformat()
                    self._write_local_db(db)
                    return asset
            logger.warning(
                f"Portfolio asset {asset_id} not found for manual price update"
            )
            return None

        try:
            asset = self.portfolio_container.read_item(
                item=asset_id, partition_key=user_id
            )
        except Exception as e:
            logger.warning(
                f"Portfolio asset {asset_id} not found for user {user_id}: {e}"
            )
            return None

        try:
            if str(asset.get("user_id")) != str(user_id):
                logger.warning(
                    "Partitioned asset user mismatch for asset '%s': expected '%s', got '%s'",
                    asset_id,
                    user_id,
                    asset.get("user_id"),
                )
                return None

            if manual_current_price is None:
                asset.pop("manual_current_price", None)
            else:
                asset["manual_current_price"] = manual_current_price
            asset["updated_at"] = datetime.utcnow().isoformat()

            return self.portfolio_container.replace_item(item=asset_id, body=asset)
        except Exception as e:
            logger.error(
                f"Failed to update manual current price for asset {asset_id}: {e}"
            )
            return None


# Global Cosmos DB client instance
_cosmos_client: Optional[CosmosDBClient] = None


def get_cosmos_client() -> CosmosDBClient:
    """Get or create global Cosmos DB client instance."""
    global _cosmos_client
    if _cosmos_client is None:
        _cosmos_client = CosmosDBClient()
    return _cosmos_client
