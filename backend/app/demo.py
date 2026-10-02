from __future__ import annotations

import json
from pathlib import Path

from .models import AuthenticatedPrincipal, ProjectCreate, TranscriptIngestRequest
from .providers import DeterministicHashEmbeddingProvider, EvidenceExtractiveAnswerProvider
from .service import TutorialService
from .store import InMemoryStore


def main() -> None:
    root = Path(__file__).resolve().parents[2]
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
    principal = AuthenticatedPrincipal(
        provider="development",
        subject="demo-user",
        tenant_id="demo",
    )
    project = service.create_project(principal, ProjectCreate(title="FastAPI tutorial"))
    source = service.ingest_transcript(
        principal,
        project.id,
        TranscriptIngestRequest(
            filename="fastapi-intro.vtt",
            content=transcript,
            authorization_mode="owner_upload",
            idempotency_key="demo-fastapi-intro-v1",
            frame_candidates=frames,
        ),
    )
    answer = service.ask(principal, project.id, "Which endpoint checks service health?")
    print(
        json.dumps(
            {
                "project_id": str(project.id),
                "source": source.model_dump(mode="json"),
                "answer": answer.model_dump(mode="json"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
