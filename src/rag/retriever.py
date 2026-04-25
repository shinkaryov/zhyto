from typing import Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)

class Retriever:
    def __init__(self, use_mock: Optional[bool] = None):
        self.use_mock = use_mock if use_mock is not None else False
        self.chroma_client = None
        self.embedder = None

        if not self.use_mock:
            self._initialize()

    def _initialize(self) -> None:
        try:
            from src.db.chroma_client import get_chroma_client
            from src.rag.embedder import get_embedder

            self.chroma_client = get_chroma_client()
            self.embedder = get_embedder()
            
            if not self.chroma_client.is_ready():
                raise Exception("ChromaDB collection is not ready")
                
            logger.info("Retriever initialized with real ChromaDB")
        except Exception as e:
            logger.error(f"Failed to initialize Retriever: {e}")
            self.use_mock = True

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if self.use_mock:
            return self._mock_search(query, top_k)

        try:
            query_embedding = self.embedder.embed_text(query)
            
            results = self.chroma_client.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k
            )
            
            formatted_results = []
            if results["documents"] and len(results["documents"]) > 0:
                for i in range(len(results["documents"][0])):
                    formatted_results.append({
                        "content": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "distance": results["distances"][0][i] if "distances" in results else 0.0
                    })
            return formatted_results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return self._mock_search(query, top_k)

    @staticmethod
    def _mock_search(query: str, top_k: int) -> list[dict]:
        return [
            {
                "content": "Моковий результат: ОВДП дають 16% річних.",
                "metadata": {
                    "channel": "Mock",
                    "url": "N/A",
                    "date": "2026-01-01T00:00:00",
                    "domain": "fixed_income",
                    "source_type": "mock",
                    "trust_weight": 1.0,
                },
                "distance": 0.1
            }
        ]

_retriever: Optional[Retriever] = None

def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever
