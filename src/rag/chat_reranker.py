"""Deterministic reranking logic for retrieved chat chunks."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from src.rag.chat_intent import normalize_text
from src.rag.chat_types import QueryIntent, ScoredChunk
from src.utils.config import settings


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    candidates = [
        raw,
        raw.replace("Z", "+00:00"),
        raw.split("+")[0],
    ]

    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return None


class DeterministicReranker:
    """Simple deterministic reranker combining relevance and metadata boosts."""

    def __init__(
        self,
        similarity_weight: float = settings.chat_rerank_similarity_weight,
        trust_weight: float = settings.chat_rerank_trust_weight,
        freshness_weight: float = settings.chat_rerank_freshness_weight,
        domain_weight: float = settings.chat_rerank_domain_weight,
        freshness_half_life_days: int = settings.chat_freshness_half_life_days,
        now_provider: Optional[Callable[[], datetime]] = None,
    ):
        self.similarity_weight = similarity_weight
        self.trust_weight = trust_weight
        self.freshness_weight = freshness_weight
        self.domain_weight = domain_weight
        self.freshness_half_life_days = max(1, freshness_half_life_days)
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _distance_to_similarity(distance: float) -> float:
        d = abs(safe_float(distance, default=1.0))
        if d <= 2:
            return clamp(1.0 - (d / 2.0))
        return clamp(1.0 / (1.0 + d))

    def _freshness_boost(self, date_value: Any, is_time_sensitive: bool) -> float:
        dt = parse_datetime(date_value)
        if not dt:
            return 0.0

        now = self.now_provider()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
        half_life = float(self.freshness_half_life_days)
        freshness = math.pow(0.5, age_days / half_life)

        if not is_time_sensitive:
            freshness *= 0.6

        return clamp(freshness)

    @staticmethod
    def _domain_channel_bonus(metadata: dict[str, Any], intent: QueryIntent) -> float:
        if not intent.matched_domains and not intent.matched_channels:
            return 0.0

        domain = normalize_text(str(metadata.get("domain") or ""))
        channel = normalize_text(str(metadata.get("channel") or ""))
        source_type = normalize_text(str(metadata.get("source_type") or ""))

        domain_hit = any(hint in domain for hint in intent.matched_domains)
        channel_hit = any(
            (hint in channel) or (hint in source_type)
            for hint in intent.matched_channels
        )

        if domain_hit and channel_hit:
            return 1.0
        if domain_hit:
            return 0.8
        if channel_hit:
            return 0.55
        return 0.0

    def rerank(self, raw_results: list[dict[str, Any]], intent: QueryIntent) -> list[ScoredChunk]:
        reranked: list[ScoredChunk] = []

        for result in raw_results:
            metadata = result.get("metadata") or {}
            distance = safe_float(result.get("distance"), default=1.0)
            retrieval_score = self._distance_to_similarity(distance)
            trust_score = clamp(safe_float(metadata.get("trust_weight"), default=0.5))
            freshness_score = self._freshness_boost(
                metadata.get("date"),
                is_time_sensitive=intent.is_time_sensitive,
            )
            domain_score = self._domain_channel_bonus(metadata, intent)

            final_score = (
                self.similarity_weight * retrieval_score
                + self.trust_weight * trust_score
                + self.freshness_weight * freshness_score
                + self.domain_weight * domain_score
            )

            reranked.append(
                ScoredChunk(
                    content=str(result.get("content") or ""),
                    metadata=metadata,
                    distance=distance,
                    retrieval_score=retrieval_score,
                    rerank_score=final_score,
                    score_breakdown={
                        "similarity": retrieval_score,
                        "trust": trust_score,
                        "freshness": freshness_score,
                        "domain": domain_score,
                        "final": final_score,
                    },
                )
            )

        reranked.sort(key=lambda item: item.rerank_score, reverse=True)
        return reranked
