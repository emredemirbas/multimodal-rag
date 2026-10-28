"""Keep the authored UI walkthrough honest about current chunk-level evidence."""

from pathlib import Path

import pytest

from app.models import AuthenticatedPrincipal, EvidenceSegment, ProjectCreate, Source
from app.providers import DeterministicHashEmbeddingProvider, EvidenceExtractiveAnswerProvider
from app.service import TutorialService
from app.sources.chunking import PROCESSING_VERSION, chunk_transcript, segment_id
from app.store import InMemoryStore


@pytest.mark.parametrize("question,supported", [
    ("Which endpoint checks service health?", True),
    ("What do Pydantic response models validate?", True),
    ("How does Kubernetes ingress handle TLS?", False),
])
def test_authored_demo_uses_published_chunk_spans_and_extracts_or_abstains(question, supported):
    content = (Path(__file__).resolve().parents[2] / "examples/fastapi-intro.vtt").read_bytes()
    chunks = chunk_transcript(content)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert (chunk.start_ms, chunk.end_ms, chunk.cue_start, chunk.cue_end) == (1000, 22000, 0, 3)

    store = InMemoryStore()
    embeddings = DeterministicHashEmbeddingProvider()
    service = TutorialService(store, embeddings, EvidenceExtractiveAnswerProvider())
    principal = AuthenticatedPrincipal(provider="test", subject="demo-reader", tenant_id="demo-reader")
    project = service.create_project(principal, ProjectCreate(title="Authored demo"))
    source = Source(tenant_id=principal.tenant_id, project_id=project.id,
                    filename="fastapi-intro.vtt", authorization_mode="licensed_content")
    # Mirror the queued worker's published segments, not the legacy per-cue demo.
    segment = EvidenceSegment(
        id=segment_id(source.id, 1, chunk, 0), tenant_id=principal.tenant_id,
        project_id=project.id, source_id=source.id, modality="transcript",
        start_ms=chunk.start_ms, end_ms=chunk.end_ms, text=chunk.text,
        embedding=embeddings.embed(chunk.text), embedding_space=embeddings.space_id,
        processing_version=f"{PROCESSING_VERSION}:g1", generation=1,
    )
    store.save_source(source, [segment], "authored-demo-upload")

    response = service.ask(principal, project.id, question, [source.id])

    assert response.abstained is not supported
    if not supported:
        assert response.citations == []
        return

    assert response.answer == f"Quoted tutorial evidence (extractive baseline):\n\n[1] “{chunk.text}”"
    assert len(response.citations) == 1
    citation = response.citations[0]
    assert citation.segment_id == segment.id and citation.source_id == source.id
    assert (citation.start_ms, citation.end_ms) == (1000, 22000)
    assert citation.processing_version == f"{PROCESSING_VERSION}:g1"
    assert citation.generation == 1 and citation.modality == "transcript"
