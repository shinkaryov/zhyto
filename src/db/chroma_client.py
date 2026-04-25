"""
ChromaDB client wrapper for vector database operations.
"""

from typing import Optional

from src.utils.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ChromaDBClient:
    """Wrapper for ChromaDB operations."""

    def __init__(self):
        """Initialize ChromaDB client."""
        self.client = None
        self.collection = None
        self._initialize()

    def _initialize(self) -> None:
        """Initialize ChromaDB client and collection."""
        try:
            import chromadb

            self.client = chromadb.PersistentClient(path=settings.chroma_db_path)
            self.collection = self.client.get_or_create_collection(
                name=settings.chroma_collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                f"ChromaDB initialized with collection '{settings.chroma_collection_name}'"
            )
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")

    def is_ready(self) -> bool:
        """Check if ChromaDB is ready for operations."""
        return self.collection is not None

    def get_collection_stats(self) -> dict:
        """Get statistics about the collection."""
        try:
            if not self.is_ready():
                return {"error": "ChromaDB not initialized"}

            count = self.collection.count()
            return {
                "name": settings.chroma_collection_name,
                "document_count": count,
                "status": "ready",
            }
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {"error": str(e), "status": "error"}


# Global ChromaDB client instance
_chroma_client: Optional[ChromaDBClient] = None


def get_chroma_client() -> ChromaDBClient:
    """Get or create global ChromaDB client instance."""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = ChromaDBClient()
    return _chroma_client
