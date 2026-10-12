"""Bounded, deterministic rank fusion/reranking behind the provider boundary."""
from collections import Counter
from uuid import UUID

from .models import RetrievalHit
from .providers import content_tokens

RETRIEVAL_VERSION = "hybrid-rrf-v1"
RERANKER_VERSION = "identifier-overlap-v1"
PROMPT_VERSION = "quoted-evidence-v1"
CANDIDATES_PER_CHANNEL = 24
CONTEXT_CHARACTERS = 4_800


def fuse_and_rerank(query: str, channels: list[list[RetrievalHit]], limit: int, *, semantic_mode: bool = False) -> list[RetrievalHit]:
    """RRF k=60, then lexical coverage; not a learned relevance model."""
    scores: Counter[UUID] = Counter()
    candidates: dict[UUID, RetrievalHit] = {}
    for channel in channels:
        seen: set[UUID] = set()
        for rank, hit in enumerate(channel, 1):
            if hit.segment.id in seen:
                continue
            seen.add(hit.segment.id)
            candidates[hit.segment.id] = hit
            scores[hit.segment.id] += 1 / (60 + rank)
    terms = content_tokens(query)
    ranked = sorted(candidates.values(), key=lambda hit: (
        -(hit.semantic_similarity or 0) - .05 * len(terms & content_tokens(hit.segment.text)) / max(1, len(terms)) if semantic_mode else
        -len(terms & content_tokens(hit.segment.text)) / max(1, len(terms)),
        -scores[hit.segment.id], hit.segment.start_ms, str(hit.segment.id),
    ))
    result: list[RetrievalHit] = []
    source_counts: Counter[UUID] = Counter()
    characters = 0
    for hit in ranked:
        if len(result) >= min(limit, 4):
            break
        if source_counts[hit.segment.source_id] >= 2 or characters + len(hit.segment.text) > CONTEXT_CHARACTERS:
            continue
        source_counts[hit.segment.source_id] += 1
        characters += len(hit.segment.text)
        result.append(hit.model_copy(update={"score": scores[hit.segment.id]}))
    return result
