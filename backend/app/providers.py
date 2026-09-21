from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re
from typing import Protocol, Sequence

from .models import RetrievalHit


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "how", "in", "is", "it", "of", "on", "or", "that", "the", "this",
    "to", "was", "what", "when", "where", "which", "with",
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

    def embed(self, text: str) -> list[float]: ...


class AnswerProvider(Protocol):
    name: str
    model: str

    def answer(self, question: str, hits: Sequence[RetrievalHit]) -> tuple[str, bool, list[RetrievalHit]]: ...


@dataclass(frozen=True)
class DeterministicHashEmbeddingProvider:
    """Offline baseline used for reproducible validation, not production quality."""

    dimensions: int = 64
    name: str = "local-deterministic"
    model: str = "signed-hash-embedding-v1"

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
    model: str = "evidence-extractive-v1"

    def answer(
        self,
        question: str,
        hits: Sequence[RetrievalHit],
    ) -> tuple[str, bool, list[RetrievalHit]]:
        question_terms = content_tokens(question)
        grounded = [
            hit for hit in hits if question_terms & content_tokens(hit.segment.text)
        ]
        if not grounded:
            return (
                "I could not find support for that question in this project's tutorial evidence.",
                True,
                [],
            )

        cited = grounded[:2]
        evidence = " ".join(hit.segment.text for hit in cited)
        return f"The tutorial evidence says: {evidence}", False, cited
