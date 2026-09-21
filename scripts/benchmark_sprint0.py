#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from time import perf_counter

from app.models import ProjectCreate, TranscriptIngestRequest
from app.providers import DeterministicHashEmbeddingProvider, EvidenceExtractiveAnswerProvider
from app.service import TutorialService
from app.store import InMemoryStore


def percentile(values: list[float], proportion: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * proportion))
    return ordered[index]


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    transcript = (root / "examples" / "fastapi-intro.vtt").read_text(encoding="utf-8")
    frames = json.loads(
        (root / "examples" / "fastapi-intro.frames.json").read_text(encoding="utf-8")
    )
    store = InMemoryStore()
    service = TutorialService(
        store,
        DeterministicHashEmbeddingProvider(),
        EvidenceExtractiveAnswerProvider(),
    )
    project = service.create_project("benchmark", ProjectCreate(title="Benchmark"))
    service.ingest_transcript(
        "benchmark",
        project.id,
        TranscriptIngestRequest(
            filename="fastapi-intro.vtt",
            content=transcript,
            authorization_mode="owner_upload",
            idempotency_key="benchmark-fastapi-intro-v1",
            frame_candidates=frames,
        ),
    )

    samples_ms: list[float] = []
    for _ in range(500):
        started = perf_counter()
        response = service.ask(
            "benchmark",
            project.id,
            "Which endpoint checks service health?",
        )
        assert response.citations
        samples_ms.append((perf_counter() - started) * 1_000)

    print(
        json.dumps(
            {
                "provider": "local-deterministic",
                "iterations": len(samples_ms),
                "p50_ms": round(median(samples_ms), 4),
                "p95_ms": round(percentile(samples_ms, 0.95), 4),
                "max_ms": round(max(samples_ms), 4),
                "scope": "in-process retrieval and answer generation; excludes HTTP and PostgreSQL",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
