import time
from collections import OrderedDict
from threading import Lock
from typing import Optional
from langchain_openai import AzureOpenAIEmbeddings
from src.utils.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class Embedder:
    def __init__(self, use_mock: Optional[bool] = None):
        self.use_mock = use_mock if use_mock is not None else settings.use_mock_openai
        self.embeddings = None
        self._cache_ttl_seconds = max(int(settings.chat_embedding_cache_ttl_seconds), 0)
        self._cache_max_entries = max(int(settings.chat_embedding_cache_max_entries), 1)
        self._embedding_cache: "OrderedDict[str, tuple[float, list[float]]]" = (
            OrderedDict()
        )
        self._cache_lock = Lock()

        if self.use_mock:
            logger.info("Using mock embedder for development")
        else:
            self._initialize_azure()

    def _initialize_azure(self):
        try:
            embedding_deployment = (
                settings.azure_openai_embedding_deployment_name
                or "text-embedding-3-small"
            ).strip()
            self.embeddings = AzureOpenAIEmbeddings(
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
                azure_endpoint=settings.azure_openai_endpoint,
                deployment=embedding_deployment,
                model=embedding_deployment,
            )
            logger.info("Azure OpenAI Embeddings initialized")
        except Exception as e:
            logger.error(f"Failed to init Azure Embeddings: {e}")
            self.use_mock = True

    def embed_text(self, text: str) -> list[float]:
        key = (text or "").strip()
        if not key:
            return self._mock_embed(text)

        cached = self._get_cached_embedding(key)
        if cached is not None:
            return cached

        if self.use_mock:
            vector = self._mock_embed(text)
            self._set_cached_embedding(key, vector)
            return vector
        try:
            vector = self.embeddings.embed_query(text)
            if isinstance(vector, list):
                self._set_cached_embedding(key, vector)
                return vector
            fallback = self._mock_embed(text)
            self._set_cached_embedding(key, fallback)
            return fallback
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            fallback = self._mock_embed(text)
            self._set_cached_embedding(key, fallback)
            return fallback

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Batch embedding helper kept for backward compatibility."""
        if self.use_mock:
            return [self._mock_embed(text) for text in texts]
        try:
            return self.embeddings.embed_documents(texts)
        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            return [self._mock_embed(text) for text in texts]

    def _mock_embed(self, text: str) -> list[float]:
        return [0.1] * 1536  # Проста заглушка на 1536 розмірностей

    def _get_cached_embedding(self, key: str) -> Optional[list[float]]:
        if self._cache_ttl_seconds <= 0:
            return None

        now = time.monotonic()
        with self._cache_lock:
            cached = self._embedding_cache.get(key)
            if not cached:
                return None
            created_at, vector = cached
            if now - created_at > self._cache_ttl_seconds:
                self._embedding_cache.pop(key, None)
                return None
            self._embedding_cache.move_to_end(key)
            return list(vector)

    def _set_cached_embedding(self, key: str, vector: list[float]) -> None:
        if self._cache_ttl_seconds <= 0:
            return

        with self._cache_lock:
            self._embedding_cache[key] = (time.monotonic(), list(vector))
            self._embedding_cache.move_to_end(key)
            while len(self._embedding_cache) > self._cache_max_entries:
                self._embedding_cache.popitem(last=False)


_embedder: Optional[Embedder] = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder
