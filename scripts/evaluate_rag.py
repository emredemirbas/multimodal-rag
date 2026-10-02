"""Synthetic regression measurements, not an independent model-quality assessment."""
import argparse
import json
import math
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from app.models import AuthenticatedPrincipal, ProjectCreate, TranscriptIngestRequest
from app.providers import DeterministicHashEmbeddingProvider, EvidenceExtractiveAnswerProvider
from app.service import TutorialService
from app.store import InMemoryStore


def evaluate(store):
    dataset = json.loads((Path(__file__).resolve().parents[1] / "backend/tests/fixtures/rag-evaluation.json").read_text())
    embedding = DeterministicHashEmbeddingProvider()
    service = TutorialService(store, embedding, EvidenceExtractiveAnswerProvider())
    principal = AuthenticatedPrincipal(provider="evaluation", subject="eval-"+uuid4().hex, tenant_id="eval-"+uuid4().hex[:16])
    project = service.create_project(principal, ProjectCreate(title="Synthetic RAG evaluation"))
    recalled = cited = supported = correct_abstentions = unsupported = owned = total_citations = 0
    durations = []
    try:
        for source in dataset["sources"]:
            service.ingest_transcript(principal, project.id, TranscriptIngestRequest(**source, authorization_mode="owner_upload", idempotency_key="eval-"+uuid4().hex))
        for example in dataset["questions"]:
            started = perf_counter()
            hits = store.search(principal.tenant_id, project.id, example["question"], embedding.embed(example["question"]), 4)
            response = service.ask(principal, project.id, example["question"])
            durations.append((perf_counter()-started)*1000)
            total_citations += len(response.citations)
            owned += sum(any(hit.segment.id == citation.segment_id and hit.segment.project_id == project.id for hit in hits) for citation in response.citations)
            if example.get("abstain"):
                unsupported += 1
                correct_abstentions += int(response.abstained and not response.citations)
            else:
                supported += 1
                recalled += int(any(hit.source_filename == example["filename"] and hit.segment.start_ms == example["start_ms"] for hit in hits))
                cited += int(any(citation.source_filename == example["filename"] and citation.start_ms == example["start_ms"] for citation in response.citations))
        durations.sort()
        return {"dataset": dataset["version"], "label_status": dataset["label_status"], "supported": supported,
                "unsupported": unsupported, "recall_at_4": round(recalled/max(1,supported),4),
                "expected_evidence_cited": round(cited/max(1,supported),4),
                "citation_ownership_precision": round(owned/max(1,total_citations),4),
                "unsupported_abstention": round(correct_abstentions/max(1,unsupported),4),
                "p95_retrieval_and_answer_ms": round(durations[math.ceil(len(durations)*.95)-1],2),
                "provider": service.answer_provider.name, "model": service.answer_provider.model}
    finally:
        service.delete_project(principal, project.id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--postgres", action="store_true", help="Use local PostgreSQL with environment credentials")
    arguments = parser.parse_args()
    try:
        store = InMemoryStore()
        if arguments.postgres:
            from app.postgres import PostgresStore
            from psycopg.conninfo import make_conninfo
            connection = os.getenv("TEST_DATABASE_URL") or make_conninfo(
                host=os.getenv("TEST_POSTGRES_HOST", "127.0.0.1"), port=os.getenv("POSTGRES_PORT", "5433"),
                dbname=os.getenv("POSTGRES_DB", "tutorial"), user=os.getenv("POSTGRES_USER", "tutorial"), password=os.environ["POSTGRES_PASSWORD"])
            store = PostgresStore(connection)
            store.run_migrations()
        print(json.dumps(evaluate(store), indent=2))
    except Exception as error:
        raise SystemExit(f"Evaluation failed ({type(error).__name__}); no credentials or provider payloads are printed.") from None
