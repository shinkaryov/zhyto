"""Evidence synthesis helpers for chat pipeline."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from src.rag.chat_intent import normalize_text
from src.rag.chat_reranker import parse_datetime, safe_float
from src.rag.chat_types import EvidenceCluster, EvidencePack, ScoredChunk
from src.utils.config import settings


def extract_headline(content: str) -> str:
    for line in (content or "").splitlines():
        cleaned = line.strip(" -\t")
        if len(cleaned) >= 12:
            return cleaned[:140]
    return (content or "")[:140].strip() or "Untitled signal"


def split_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[\.!?])\s+", (text or "").strip())
    return [chunk.strip() for chunk in chunks if chunk and chunk.strip()]


def source_key(metadata: dict[str, Any], content: str) -> str:
    url = str(metadata.get("url") or "").strip()
    source_id = str(metadata.get("source_id") or "").strip()
    channel = str(metadata.get("channel") or "").strip()
    date = str(metadata.get("date") or "").strip()

    if url:
        return f"url:{url}"
    if source_id:
        return f"source:{source_id}"

    signature = normalize_text(content)[:160]
    return f"fallback:{channel}:{date}:{signature}"


class EvidenceSynthesizer:
    """Deduplicate, group, and condense retrieved evidence chunks."""

    def __init__(
        self,
        max_clusters: int = settings.chat_synthesis_max_clusters,
        max_sources: int = settings.chat_context_max_sources,
    ):
        self.max_clusters = max(1, max_clusters)
        self.max_sources = max(1, max_sources)

    def deduplicate_candidates(self, candidates: list[ScoredChunk]) -> list[ScoredChunk]:
        unique: list[ScoredChunk] = []
        signatures: list[str] = []

        for candidate in candidates:
            normalized = normalize_text(candidate.content)
            if not normalized:
                continue

            snippet = normalized[:350]
            source_id = str(candidate.metadata.get("source_id") or "")
            skip_candidate = False

            for idx, prev in enumerate(unique):
                prev_snippet = signatures[idx]
                same_source = source_id and source_id == str(prev.metadata.get("source_id") or "")
                ratio = SequenceMatcher(None, snippet, prev_snippet).ratio()
                if ratio >= 0.93 or (same_source and ratio >= 0.84):
                    skip_candidate = True
                    break

            if skip_candidate:
                continue

            unique.append(candidate)
            signatures.append(snippet)

        return unique

    @staticmethod
    def _group_candidates(candidates: list[ScoredChunk]) -> dict[str, list[ScoredChunk]]:
        groups: dict[str, list[ScoredChunk]] = {}

        for candidate in candidates:
            metadata = candidate.metadata
            source_id = str(metadata.get("source_id") or "").strip()
            url = str(metadata.get("url") or "").strip()
            domain = str(metadata.get("domain") or "unknown").strip().lower()
            channel = str(metadata.get("channel") or "unknown").strip().lower()

            if source_id:
                key = f"source:{source_id}"
            elif url:
                key = f"url:{url}"
            else:
                topic_signature = normalize_text(extract_headline(candidate.content))[:80]
                key = f"topic:{domain}:{channel}:{topic_signature}"

            groups.setdefault(key, []).append(candidate)

        return groups

    @staticmethod
    def _build_cluster_summary(group: list[ScoredChunk]) -> str:
        selected_fragments: list[str] = []

        for candidate in sorted(group, key=lambda item: item.rerank_score, reverse=True):
            for sentence in split_sentences(candidate.content):
                clean_sentence = sentence.strip()
                if len(clean_sentence) < 35:
                    continue

                if any(
                    SequenceMatcher(None, normalize_text(clean_sentence), normalize_text(existing)).ratio() > 0.85
                    for existing in selected_fragments
                ):
                    continue

                selected_fragments.append(clean_sentence)
                if len(selected_fragments) >= 2:
                    break

            if len(selected_fragments) >= 2:
                break

        if not selected_fragments:
            top_content = group[0].content[:280]
            return top_content.strip()

        return " ".join(fragment[:260] for fragment in selected_fragments)

    @staticmethod
    def _cluster_confidence(group: list[ScoredChunk], source_count: int) -> str:
        avg_trust = sum(safe_float(item.metadata.get("trust_weight"), 0.5) for item in group) / max(1, len(group))
        has_date = any(parse_datetime(item.metadata.get("date")) for item in group)

        if avg_trust >= 0.9 and source_count >= 2 and has_date:
            return "high (multiple high-trust sources)"
        if avg_trust >= 0.7 and has_date:
            return "medium (moderate corroboration)"
        if source_count <= 1:
            return "medium-low (single-source evidence)"
        return "low (limited or weakly corroborated evidence)"

    def _build_source_registry(self, candidates: list[ScoredChunk]) -> tuple[list[dict[str, Any]], dict[str, int]]:
        sources: list[dict[str, Any]] = []
        source_index: dict[str, int] = {}

        for candidate in candidates:
            key = source_key(candidate.metadata, candidate.content)
            if key in source_index:
                continue
            if len(sources) >= self.max_sources:
                break

            metadata = candidate.metadata
            idx = len(sources) + 1
            source_index[key] = idx
            sources.append(
                {
                    "index": idx,
                    "channel": metadata.get("channel", "Unknown"),
                    "url": metadata.get("url", "N/A") or "N/A",
                    "date": metadata.get("date", "N/A") or "N/A",
                    "domain": metadata.get("domain", "N/A") or "N/A",
                    "source_type": metadata.get("source_type", "N/A") or "N/A",
                    "trust_weight": safe_float(metadata.get("trust_weight"), 0.5),
                }
            )

        return sources, source_index

    def synthesize(self, candidates: list[ScoredChunk]) -> EvidencePack:
        deduped = self.deduplicate_candidates(candidates)
        sources, source_lookup = self._build_source_registry(deduped)
        grouped = self._group_candidates(deduped)

        clusters: list[EvidenceCluster] = []
        ordered_groups = sorted(
            grouped.values(),
            key=lambda group: max(item.rerank_score for item in group),
            reverse=True,
        )

        for group in ordered_groups:
            group_sources: list[int] = []
            for candidate in group:
                key = source_key(candidate.metadata, candidate.content)
                src_idx = source_lookup.get(key)
                if src_idx and src_idx not in group_sources:
                    group_sources.append(src_idx)

            if not group_sources:
                continue

            topic = extract_headline(group[0].content)
            summary = self._build_cluster_summary(group)
            confidence_note = self._cluster_confidence(group, len(group_sources))
            score = max(item.rerank_score for item in group)

            clusters.append(
                EvidenceCluster(
                    cluster_id=len(clusters) + 1,
                    topic=topic,
                    summary=summary,
                    source_indices=sorted(group_sources),
                    confidence_note=confidence_note,
                    score=score,
                )
            )

            if len(clusters) >= self.max_clusters:
                break

        return EvidencePack(sources=sources, clusters=clusters)
