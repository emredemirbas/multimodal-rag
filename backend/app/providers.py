from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re
from typing import Protocol, Sequence

from .models import RetrievalHit
from .embedding_profiles import HASH_SPACE, QWEN_SPACE, SEMANTIC_FLOOR


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "how", "in", "is", "it", "of", "on", "or", "that", "the", "this",
    "to", "was", "what", "when", "where", "which", "with",
    "do", "does", "did", "can", "could", "would", "should", "please", "explain",
    "tell", "me", "about", "tutorial", "use", "using",
}


def content_tokens(value: str) -> set[str]:
    return {
        token.lower()
        for token in TOKEN_RE.findall(value)
        if len(token) > 1 and token.lower() not in STOP_WORDS
    }


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimensions: int
    space_id: str
    model_digest: str | None

    def embed(self, text: str) -> list[float]: ...
    def embed_query(self, text: str) -> EmbeddingBatch: ...
    def embed_documents(self, texts: Sequence[str]) -> EmbeddingBatch: ...


@dataclass(frozen=True)
class EmbeddingBatch:
    vectors: list[list[float]]
    input_tokens: int | None = None


def grounded_hits(question: str, hits: Sequence[RetrievalHit]) -> list[RetrievalHit]:
    terms = content_tokens(question)
    return [hit for hit in hits if (
        hit.segment.embedding_space == QWEN_SPACE and hit.semantic_similarity is not None
        and hit.semantic_similarity >= SEMANTIC_FLOOR
    ) or (
        hit.segment.embedding_space == HASH_SPACE and terms
        and len(terms & content_tokens(hit.segment.text)) / len(terms) >= .5
    )]


class AnswerProvider(Protocol):
    name: str
    model: str

    def answer(self, question: str, hits: Sequence[RetrievalHit]) -> AnswerResult | tuple[str, bool, list[RetrievalHit]]: ...


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    abstained: bool
    cited_hits: list[RetrievalHit]
    input_tokens: int | None = None
    output_tokens: int | None = None
    model_digest: str | None = None
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None


@dataclass(frozen=True)
class DeterministicHashEmbeddingProvider:
    """Offline baseline used for reproducible validation, not production quality."""

    dimensions: int = 64
    name: str = "local-deterministic"
    model: str = "signed-hash-embedding-v1"
    space_id: str = HASH_SPACE
    model_digest: str | None = None

    def embed_query(self, text: str) -> EmbeddingBatch:
        return EmbeddingBatch([self.embed(text)], 0)

    def embed_documents(self, texts: Sequence[str]) -> EmbeddingBatch:
        return EmbeddingBatch([self.embed(text) for text in texts], 0)

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in TOKEN_RE.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            return [value / norm for value in vector]
        return vector


@dataclass(frozen=True)
class EvidenceExtractiveAnswerProvider:
    name: str = "local-deterministic"
    model: str = "evidence-extractive-v2"

    def answer(
        self,
        question: str,
        hits: Sequence[RetrievalHit],
    ) -> tuple[str, bool, list[RetrievalHit]]:
        grounded = grounded_hits(question, hits)
        if not grounded:
            return (
                "I could not find support for that question in this project's tutorial evidence.",
                True,
                [],
            )

        cited = grounded[:2]
        # Evidence is data, never an instruction or a tool request.
        evidence = "\n\n".join(f'[{index}] “{hit.segment.text}”' for index, hit in enumerate(cited, 1))
        return f"Quoted tutorial evidence (extractive baseline):\n\n{evidence}", False, cited
