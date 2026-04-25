"""Shared types and constants for chat pipeline modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

ROUTING_INTENT_PURE_LIVE_PRICE = "pure_live_price"
ROUTING_INTENT_FACTUAL_RAG = "factual_rag"
ROUTING_INTENT_ANALYTICAL_RAG = "analytical_rag"
ROUTING_INTENT_ANALYTICAL_WITH_LIVE_PRICE = "analytical_with_live_price"
ROUTING_INTENT_PORTFOLIO_TRANSACTION = "portfolio_transaction"


@dataclass
class QueryIntent:
    """Parsed intent signals from user query."""

    matched_domains: list[str] = field(default_factory=list)
    matched_channels: list[str] = field(default_factory=list)
    is_analytical: bool = False
    is_time_sensitive: bool = False
    routing_intent: str = ROUTING_INTENT_FACTUAL_RAG
    requires_live_price_tool: bool = False


@dataclass
class ScoredChunk:
    """Retrieved chunk with deterministic reranking metadata."""

    content: str
    metadata: dict[str, Any]
    distance: float
    retrieval_score: float
    rerank_score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)


@dataclass
class EvidenceCluster:
    """Synthesized evidence group for prompt assembly."""

    cluster_id: int
    topic: str
    summary: str
    source_indices: list[int]
    confidence_note: str
    score: float


@dataclass
class EvidencePack:
    """Compact evidence package used by generation layers."""

    sources: list[dict[str, Any]]
    clusters: list[EvidenceCluster]

    def to_prompt_text(self) -> str:
        if not self.sources:
            return "No evidence sources available."

        source_lines = []
        for source in self.sources:
            source_lines.append(
                f"[{source['index']}] channel={source.get('channel', 'Unknown')}; "
                f"domain={source.get('domain', 'N/A')}; "
                f"date={source.get('date', 'N/A')}; "
                f"trust_weight={source.get('trust_weight', 'N/A')}; "
                f"url={source.get('url', 'N/A')}"
            )

        cluster_lines = []
        for cluster in self.clusters:
            src_refs = " ".join(f"[{idx}]" for idx in cluster.source_indices) or "N/A"
            cluster_lines.append(
                f"Cluster {cluster.cluster_id}:\n"
                f"Theme: {cluster.topic}\n"
                f"Evidence Summary: {cluster.summary}\n"
                f"Supporting Sources: {src_refs}\n"
                f"Confidence: {cluster.confidence_note}"
            )

        return (
            "SOURCE MAP:\n"
            + "\n".join(source_lines)
            + "\n\nEVIDENCE CLUSTERS:\n"
            + "\n\n".join(cluster_lines)
        )


@dataclass
class PipelineResult:
    """Final result returned by analytical chat pipeline."""

    message: str
    sources: list[dict[str, Any]]
    stage1_candidates: list[ScoredChunk] = field(default_factory=list)
    reranked_candidates: list[ScoredChunk] = field(default_factory=list)
    evidence_pack: Optional[EvidencePack] = None
    analyst_artifact: str = ""
    pending_transaction_draft: Optional[dict[str, Any]] = None
    debug: Optional[dict[str, Any]] = None


@dataclass
class HypothesisCandidate:
    """Internal hypothesis candidate for analytical routing."""

    hypothesis_id: str
    short_title: str
    description: str
    evidence_query: str
