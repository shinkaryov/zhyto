"""
Data ingestion module for RAG system.

Handles reading investment data from JSON files, chunking text,
generating embeddings with Azure OpenAI, and storing in ChromaDB.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import AzureOpenAIEmbeddings

from src.db.chroma_client import ChromaDBClient
from src.utils.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class DataIngestionError(Exception):
    """Custom exception for data ingestion errors."""

    pass


class DataLoader:
    """Load investment data from JSON files."""

    DATA_DIR = Path(__file__).parent.parent / "invest_app_data"

    REQUIRED_FIELDS = {"id", "text", "date", "channel"}

    @classmethod
    def load_json(cls, filename: str) -> list[dict]:
        """
        Load data from JSON file.

        Args:
            filename: Name of JSON file in invest_app_data directory

        Returns:
            List of document dictionaries

        Raises:
            DataIngestionError: If file not found or invalid JSON
        """
        filepath = cls.DATA_DIR / filename

        if not filepath.exists():
            logger.warning(f"File not found: {filepath}")
            return []

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Ensure data is a list
            if not isinstance(data, list):
                data = [data]

            logger.info(f"Loaded {len(data)} documents from {filename}")
            return data

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {filename}: {e}")
            raise DataIngestionError(f"Failed to parse {filename}: {e}")
        except Exception as e:
            logger.error(f"Error loading {filename}: {e}")
            raise DataIngestionError(f"Failed to load {filename}: {e}")

    @classmethod
    def validate_documents(cls, documents: list[dict], filename: str) -> list[dict]:
        """
        Validate documents have required fields.

        Args:
            documents: List of documents to validate
            filename: Source filename for logging

        Returns:
            List of valid documents
        """
        valid_docs = []
        invalid_count = 0

        for i, doc in enumerate(documents):
            if not isinstance(doc, dict):
                invalid_count += 1
                continue

            # Check for required fields
            if not cls.REQUIRED_FIELDS.issubset(doc.keys()):
                missing = cls.REQUIRED_FIELDS - set(doc.keys())
                logger.debug(f"Document {i} in {filename} missing fields: {missing}")
                invalid_count += 1
                continue

            valid_docs.append(doc)

        if invalid_count > 0:
            logger.warning(f"{invalid_count} invalid documents skipped from {filename}")

        return valid_docs

    @classmethod
    def load_all_data(cls) -> dict[str, list[dict]]:
        """
        Load all investment data files.

        Returns:
            Dictionary with data by source type
        """
        data = {
            "macro_news": cls.load_json("global_and_local_macro_news.json"),
            "telegram": cls.load_json("telegram.json"),
            "youtube": cls.load_json("youtube_transcripts_database.json"),
            "user_notes": cls.load_json("synthetic_notes.json"),
        }

        # Validate each dataset
        for source, documents in data.items():
            data[source] = cls.validate_documents(documents, source)

        return data


class TextChunker:
    """Split documents into chunks for embedding."""

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ):
        """
        Initialize text chunker.

        Args:
            chunk_size: Target size of chunks
            chunk_overlap: Overlap between chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )

    def chunk_text(self, text: str, max_chunks: Optional[int] = None) -> list[str]:
        """
        Split text into chunks.

        Args:
            text: Text to chunk
            max_chunks: Maximum number of chunks to return

        Returns:
            List of text chunks
        """
        if not text or not isinstance(text, str):
            return []

        chunks = self.splitter.split_text(text)

        if max_chunks and len(chunks) > max_chunks:
            logger.warning(
                f"Text produced {len(chunks)} chunks, " f"truncating to {max_chunks}"
            )
            chunks = chunks[:max_chunks]

        return chunks


class EmbeddingGenerator:
    """Generate embeddings using Azure OpenAI."""

    def __init__(self):
        """Initialize Azure OpenAI embeddings."""
        if not settings.azure_openai_api_key:
            raise DataIngestionError(
                "Azure OpenAI API key not configured. "
                "Set AZURE_OPENAI_API_KEY environment variable."
            )

        if not settings.azure_openai_endpoint:
            raise DataIngestionError(
                "Azure OpenAI endpoint not configured. "
                "Set AZURE_OPENAI_ENDPOINT environment variable."
            )

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
            logger.info("Azure OpenAI embeddings initialized")
        except Exception as e:
            logger.error(f"Failed to initialize embeddings: {e}")
            raise DataIngestionError(f"Failed to initialize embeddings: {e}")

    def generate(self, text: str) -> list[float]:
        """
        Generate embedding for text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        try:
            embedding = self.embeddings.embed_query(text)
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise DataIngestionError(f"Embedding generation failed: {e}")


class DataIngestion:
    """Main data ingestion orchestrator."""

    def __init__(
        self,
        chroma_client: Optional[ChromaDBClient] = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ):
        """
        Initialize data ingestion.

        Args:
            chroma_client: ChromaDB client instance
            chunk_size: Size of text chunks
            chunk_overlap: Overlap between chunks
        """
        self.chroma_client = chroma_client or ChromaDBClient()
        self.chunker = TextChunker(chunk_size, chunk_overlap)

        # Initialize embeddings
        try:
            self.embeddings = EmbeddingGenerator()
        except DataIngestionError as e:
            logger.error(f"Failed to initialize embeddings: {e}")
            raise

        self.total_documents = 0
        self.total_chunks = 0
        self.failed_chunks = 0

    def prepare_chunk_data(
        self,
        chunk_text: str,
        original_doc: dict,
        chunk_index: int,
    ) -> tuple[str, dict, str]:
        """
        Prepare chunk data for storage.

        Args:
            chunk_text: The chunk text content
            original_doc: Original document dictionary
            chunk_index: Index of chunk within document

        Returns:
            Tuple of (chunk_id, metadata, chunk_text)
        """
        # Create unique ID combining document ID and chunk index
        doc_id = str(original_doc.get("id", "unknown"))
        chunk_id = f"{doc_id}_chunk_{chunk_index}"

        # Prepare metadata
        metadata = {
            "source_id": doc_id,
            "chunk_index": chunk_index,
            "date": str(original_doc.get("date", "")),
            "channel": str(original_doc.get("channel", "")),
            "url": str(original_doc.get("url", "")),
            "domain": str(original_doc.get("domain", "")),
            "source_type": str(original_doc.get("source_type", "")),
            "trust_weight": float(original_doc.get("trust_weight", 0.5)),
            "ingested_at": datetime.utcnow().isoformat(),
        }

        return chunk_id, metadata, chunk_text

    def ingest_documents(
        self,
        source_type: str,
        documents: list[dict],
        skip_errors: bool = True,
    ) -> dict[str, int]:
        """
        Ingest documents from a source.

        Args:
            source_type: Type of source (macro_news, telegram, youtube, user_notes)
            documents: List of documents to ingest
            skip_errors: Whether to skip individual document errors

        Returns:
            Dictionary with ingestion statistics
        """
        logger.info(
            f"Starting ingestion of {len(documents)} documents from {source_type}"
        )

        stats = {
            "source_type": source_type,
            "documents_processed": 0,
            "chunks_created": 0,
            "chunks_stored": 0,
            "chunks_failed": 0,
        }

        for doc_index, doc in enumerate(documents, 1):
            try:
                # Extract text
                text = doc.get("text") or doc.get("content") or ""
                if not text:
                    logger.debug(f"Document {doc_index} has no text, skipping")
                    continue

                # Chunk the text
                chunks = self.chunker.chunk_text(text)
                if not chunks:
                    logger.debug(f"Document {doc_index} produced no chunks")
                    continue

                stats["chunks_created"] += len(chunks)

                # Store each chunk
                for chunk_index, chunk_text in enumerate(chunks):
                    try:
                        chunk_id, metadata, prepared_text = self.prepare_chunk_data(
                            chunk_text, doc, chunk_index
                        )

                        # Generate embedding
                        embedding = self.embeddings.generate(prepared_text)

                        # Store in ChromaDB
                        self.chroma_client.collection.add(
                            ids=[chunk_id],
                            documents=[prepared_text],
                            metadatas=[metadata],
                            embeddings=[embedding],
                        )

                        stats["chunks_stored"] += 1

                    except Exception as e:
                        stats["chunks_failed"] += 1
                        logger.error(
                            f"Failed to store chunk {chunk_index} "
                            f"from document {doc_index}: {e}"
                        )
                        if not skip_errors:
                            raise

                stats["documents_processed"] += 1

                # Log progress
                if doc_index % 10 == 0:
                    logger.info(
                        f"Processed {doc_index}/{len(documents)} documents "
                        f"from {source_type}"
                    )

            except Exception as e:
                logger.error(f"Error processing document {doc_index}: {e}")
                if not skip_errors:
                    raise

        logger.info(
            f"Ingestion complete for {source_type}: "
            f"{stats['documents_processed']} documents, "
            f"{stats['chunks_stored']} chunks stored, "
            f"{stats['chunks_failed']} chunks failed"
        )

        return stats

    def ingest_all_data(self, skip_errors: bool = True) -> dict[str, Any]:
        """
        Load and ingest all investment data.

        Args:
            skip_errors: Whether to skip individual errors

        Returns:
            Dictionary with overall ingestion statistics
        """
        logger.info("Starting full data ingestion pipeline")

        # Load all data
        all_data = DataLoader.load_all_data()

        # Ingest by source type
        results = {
            "start_time": datetime.utcnow().isoformat(),
            "sources": {},
            "total_documents": 0,
            "total_chunks": 0,
            "total_stored": 0,
            "total_failed": 0,
        }

        for source_type, documents in all_data.items():
            if not documents:
                logger.info(f"No documents found for source: {source_type}")
                results["sources"][source_type] = {
                    "documents": 0,
                    "chunks": 0,
                    "status": "skipped",
                }
                continue

            try:
                stats = self.ingest_documents(source_type, documents, skip_errors)
                results["sources"][source_type] = {
                    "documents": stats["documents_processed"],
                    "chunks": stats["chunks_stored"],
                    "failed": stats["chunks_failed"],
                    "status": "completed",
                }

                results["total_documents"] += stats["documents_processed"]
                results["total_chunks"] += stats["chunks_stored"]
                results["total_stored"] += stats["chunks_stored"]
                results["total_failed"] += stats["chunks_failed"]

            except Exception as e:
                logger.error(f"Failed to ingest {source_type}: {e}")
                results["sources"][source_type] = {
                    "status": "failed",
                    "error": str(e),
                }

        results["end_time"] = datetime.utcnow().isoformat()

        logger.info(
            f"Data ingestion completed: {results['total_documents']} documents, "
            f"{results['total_stored']} chunks stored"
        )

        return results


def ingest_investment_data(
    skip_errors: bool = True,
) -> dict[str, Any]:
    """
    Convenience function to ingest all investment data.

    Args:
        skip_errors: Whether to skip individual errors

    Returns:
        Dictionary with ingestion results
    """
    ingestion = DataIngestion()
    return ingestion.ingest_all_data(skip_errors=skip_errors)


if __name__ == "__main__":
    # Example usage
    try:
        results = ingest_investment_data()

        print("\n" + "=" * 60)
        print("DATA INGESTION RESULTS")
        print("=" * 60)
        print(f"Start time: {results['start_time']}")
        print(f"End time: {results['end_time']}")
        print(f"\nTotal documents processed: {results['total_documents']}")
        print(f"Total chunks created: {results['total_chunks']}")
        print(f"Total chunks stored: {results['total_stored']}")
        print(f"Total chunks failed: {results['total_failed']}")

        print("\nDetailed results by source:")
        for source, stats in results["sources"].items():
            print(f"\n  {source}:")
            for key, value in stats.items():
                print(f"    {key}: {value}")

        print("\n" + "=" * 60)

    except Exception as e:
        logger.error(f"Data ingestion failed: {e}")
        print(f"ERROR: {e}")
