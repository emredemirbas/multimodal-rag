from __future__ import annotations

import hashlib
from time import perf_counter
from uuid import UUID, NAMESPACE_URL, uuid5

from .models import (
    Citation,
    EvidenceSegment,
    Project,
    ProjectCreate,
    QuestionResponse,
    RetrievalRun,
    Source,
    SourceIngested,
    TranscriptIngestRequest,
)
from .providers import AnswerProvider, EmbeddingProvider
from .store import Store
from .transcripts import parse_transcript, select_novel_frames


class TutorialService:
    def __init__(
        self,
        store: Store,
        embedding_provider: EmbeddingProvider,
        answer_provider: AnswerProvider,
        *,
        retrieval_limit: int = 4,
    ) -> None:
        self.store = store
        self.embedding_provider = embedding_provider
        self.answer_provider = answer_provider
        self.retrieval_limit = retrieval_limit

    def create_project(self, tenant_id: str, request: ProjectCreate) -> Project:
        return self.store.create_project(Project(tenant_id=tenant_id, title=request.title))

    def ingest_transcript(
        self,
        tenant_id: str,
        project_id: UUID,
        request: TranscriptIngestRequest,
    ) -> SourceIngested:
        self.store.get_project(tenant_id, project_id)
        existing = self.store.get_source_by_idempotency_key(
            tenant_id, project_id, request.idempotency_key
        )
        if existing is not None:
            return SourceIngested(source=existing, deduplicated=True)

        cues = parse_transcript(request.content)
        frames = select_novel_frames(request.frame_candidates)
        source = Source(
            tenant_id=tenant_id,
            project_id=project_id,
            filename=request.filename,
            authorization_mode=request.authorization_mode,
            frame_count=len(frames),
        )
        segments: list[EvidenceSegment] = []
        for cue in cues:
            segment_id = uuid5(
                NAMESPACE_URL,
                f"{source.id}:transcript:{cue.start_ms}:{cue.end_ms}:{cue.text}",
            )
            segments.append(
                EvidenceSegment(
                    id=segment_id,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    source_id=source.id,
                    modality="transcript",
                    start_ms=cue.start_ms,
                    end_ms=cue.end_ms,
                    text=cue.text,
                    embedding=self.embedding_provider.embed(cue.text),
                )
            )
        for frame in frames:
            timestamp_ms = round(frame.timestamp_seconds * 1_000)
            text = " ".join(
                part.strip() for part in (frame.ocr_text, frame.description) if part.strip()
            )
            frame_id = uuid5(
                NAMESPACE_URL,
                f"{source.id}:frame:{timestamp_ms}:{text}",
            )
            segments.append(
                EvidenceSegment(
                    id=uuid5(NAMESPACE_URL, f"{frame_id}:segment"),
                    tenant_id=tenant_id,
                    project_id=project_id,
                    source_id=source.id,
                    modality="frame",
                    start_ms=timestamp_ms,
                    end_ms=timestamp_ms + 1_000,
                    text=text,
                    embedding=self.embedding_provider.embed(text),
                    frame_id=frame_id,
                )
            )

        saved = self.store.save_source(source, segments, request.idempotency_key)
        return SourceIngested(source=saved, deduplicated=False)

    def ask(
        self,
        tenant_id: str,
        project_id: UUID,
        question: str,
    ) -> QuestionResponse:
        started = perf_counter()
        embedding = self.embedding_provider.embed(question)
        hits = self.store.search(
            tenant_id,
            project_id,
            question,
            embedding,
            self.retrieval_limit,
        )
        answer, abstained, cited_hits = self.answer_provider.answer(question, hits)

        for hit in cited_hits:
            if hit.segment.tenant_id != tenant_id or hit.segment.project_id != project_id:
                raise RuntimeError("citation failed project ownership validation")

        latency_ms = round((perf_counter() - started) * 1_000)
        run = RetrievalRun(
            tenant_id=tenant_id,
            project_id=project_id,
            embedding_provider=self.embedding_provider.name,
            embedding_model=self.embedding_provider.model,
            answer_provider=self.answer_provider.name,
            answer_model=self.answer_provider.model,
            query_sha256=hashlib.sha256(question.encode("utf-8")).hexdigest(),
            retrieved_segment_ids=[hit.segment.id for hit in hits],
            cited_segment_ids=[hit.segment.id for hit in cited_hits],
            candidate_count=len(hits),
            latency_ms=latency_ms,
        )
        self.store.save_retrieval_run(run)
        citations = [
            Citation(
                segment_id=hit.segment.id,
                source_id=hit.segment.source_id,
                source_filename=hit.source_filename,
                start_ms=hit.segment.start_ms,
                end_ms=hit.segment.end_ms,
                modality=hit.segment.modality,
                frame_id=hit.segment.frame_id,
                score=round(hit.score, 6),
            )
            for hit in cited_hits
        ]
        return QuestionResponse(
            answer=answer,
            abstained=abstained,
            citations=citations,
            retrieval_run_id=run.id,
            provider=self.answer_provider.name,
            model=self.answer_provider.model,
            processing_version="sprint0-v1",
            latency_ms=latency_ms,
        )
