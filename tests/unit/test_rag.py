"""
Tests for RAG components.
"""

import pytest

from src.rag.embedder import Embedder
from src.rag.generator import Generator
from src.rag.retriever import Retriever


class TestEmbedder:
    """Test embedder module."""

    def test_embedder_mock_initialization(self):
        """Test embedder initialization with mock mode."""
        embedder = Embedder(use_mock=True)
        assert embedder.use_mock is True

    def test_embed_text(self):
        """Test text embedding."""
        embedder = Embedder(use_mock=True)
        embedding = embedder.embed_text("Test text")

        assert isinstance(embedding, list)
        assert len(embedding) == 1536  # OpenAI embedding size
        assert all(isinstance(x, float) for x in embedding)

    def test_embed_texts_batch(self):
        """Test batch text embedding."""
        embedder = Embedder(use_mock=True)
        texts = ["Text 1", "Text 2", "Text 3"]
        embeddings = embedder.embed_texts(texts)

        assert len(embeddings) == 3
        assert all(len(e) == 1536 for e in embeddings)


class TestRetriever:
    """Test retriever module."""

    def test_retriever_initialization(self):
        """Test retriever initialization."""
        retriever = Retriever(use_mock=True)
        assert retriever.use_mock is True

    def test_mock_search(self):
        """Test mock search."""
        retriever = Retriever(use_mock=True)
        results = retriever.search("Test query", top_k=3)

        assert isinstance(results, list)
        assert len(results) <= 3

    def test_search_result_structure(self):
        """Test search result structure."""
        retriever = Retriever(use_mock=True)
        results = retriever.search("Test query", top_k=1)

        if results:
            result = results[0]
            assert "content" in result
            assert "distance" in result
            assert "metadata" in result


class TestGenerator:
    """Test generator module."""

    def test_generator_mock_initialization(self):
        """Test generator initialization with mock mode."""
        generator = Generator(use_mock=True)
        assert generator.use_mock is True

    def test_generate_response(self):
        """Test response generation."""
        generator = Generator(use_mock=True)
        response = generator.generate("What about investments?")

        assert isinstance(response, str)
        assert len(response) > 0

    def test_generate_with_system_prompt(self):
        """Test generation with system prompt."""
        generator = Generator(use_mock=True)
        system_prompt = "You are a financial advisor"
        response = generator.generate(
            "Help me with portfolio",
            system_prompt=system_prompt
        )

        assert isinstance(response, str)
        assert len(response) > 0

