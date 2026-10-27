from __future__ import annotations

import hashlib
from time import perf_counter
from uuid import UUID, NAMESPACE_URL, uuid5

from .models import (
    AuthenticatedPrincipal,
    Citation,
    EvidenceSegment,
    Project,
    ProjectCreate,
    ProjectList,
    ProjectListStatus,
    ProjectUpdate,
    QuestionResponse,
    RetrievalRun,
    Source,
    SourceIngested,
    TranscriptIngestRequest,
)
from .providers import AnswerProvider, AnswerResult, EmbeddingProvider
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

    def _actor_user_id(self, principal: AuthenticatedPrincipal) -> UUID:
        return self.store.bootstrap_principal(principal)

    def create_project(
        self, principal: AuthenticatedPrincipal, request: ProjectCreate
    ) -> Project:
        actor_user_id = self._actor_user_id(principal)
        return self.store.create_project(
            Project(tenant_id=principal.tenant_id, title=request.title),
            actor_user_id,
        )

    def list_projects(
        self,
        principal: AuthenticatedPrincipal,
        status: ProjectListStatus,
    ) -> ProjectList:
        self._actor_user_id(principal)
        return ProjectList(items=self.store.list_projects(principal.tenant_id, status))

    def get_project(
        self, principal: AuthenticatedPrincipal, project_id: UUID
    ) -> Project:
        self._actor_user_id(principal)
        return self.store.get_project(principal.tenant_id, project_id)

    def update_project(
        self,
        principal: AuthenticatedPrincipal,
        project_id: UUID,
        request: ProjectUpdate,
    ) -> Project:
        actor_user_id = self._actor_user_id(principal)
        return self.store.update_project_title(
            principal.tenant_id,
            project_id,
            request.title,
            actor_user_id,
        )

    def archive_project(
        self, principal: AuthenticatedPrincipal, project_id: UUID
    ) -> Project:
        actor_user_id = self._actor_user_id(principal)
        return self.store.archive_project(
            principal.tenant_id, project_id, actor_user_id
        )

    def restore_project(
        self, principal: AuthenticatedPrincipal, project_id: UUID
    ) -> Project:
        actor_user_id = self._actor_user_id(principal)
        return self.store.restore_project(
            principal.tenant_id, project_id, actor_user_id
        )

    def delete_project(
        self, principal: AuthenticatedPrincipal, project_id: UUID
    ) -> UUID | None:
        actor_user_id = self._actor_user_id(principal)
        return self.store.delete_project(principal.tenant_id, project_id, actor_user_id)

    def ingest_transcript(
        self,
        principal: AuthenticatedPrincipal,
        project_id: UUID,
        request: TranscriptIngestRequest,
    ) -> SourceIngested:
        from .embedding_profiles import HASH_SPACE
        from .sources.contracts import SourceError
        if self.embedding_provider.space_id != HASH_SPACE:
            raise SourceError('validation_endpoint_unavailable', 'Use asynchronous uploads for local semantic indexing.', 503)
        self._actor_user_id(principal)
        tenant_id = principal.tenant_id
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
        principal: AuthenticatedPrincipal,
        project_id: UUID,
        question: str,
        source_ids: list[UUID] | None = None,
    ) -> QuestionResponse:
        response, run = self.prepare_answer(principal, project_id, question, source_ids)
        self.store.save_retrieval_run(run)
        return response

    def prepare_answer(
        self, principal: AuthenticatedPrincipal, project_id: UUID, question: str,
        source_ids: list[UUID] | None = None,
    ) -> tuple[QuestionResponse, RetrievalRun]:
        from .sources.contracts import SourceError
        self._actor_user_id(principal)
        tenant_id = principal.tenant_id
        project = self.store.get_project(tenant_id, project_id)
        if project.status.value != 'active':
            raise SourceError('project_archived', 'Restore the project before asking new questions.', 409)
        for source_id in source_ids or []:
            self.store.get_source(tenant_id, project_id, source_id)
        started = perf_counter()
        query_batch = self.embedding_provider.embed_query(question)
        embedding = query_batch.vectors[0]
        hits = self.store.search(
            tenant_id,
            project_id,
            question,
            embedding,
            self.retrieval_limit,
            source_ids,
            embedding_space=self.embedding_provider.space_id,
        )
        retrieved = {hit.segment.id: hit.model_copy(deep=True) for hit in hits}
        provider_input = [hit.model_copy(deep=True) for hit in hits]
        budgeted_answer = getattr(self.answer_provider, 'answer_with_budget', None)
        generated = (budgeted_answer(question, provider_input, started + 28) if budgeted_answer is not None
                     else self.answer_provider.answer(question, provider_input))
        result = generated if isinstance(generated, AnswerResult) else AnswerResult(*generated)
        answer, abstained, cited_hits = result.answer, result.abstained, result.cited_hits
        if (len(answer) > 12_000 or not answer.strip() or (abstained and cited_hits) or (not abstained and not cited_hits)
                or len(cited_hits) > 4 or len({hit.segment.id for hit in cited_hits}) != len(cited_hits)):
            raise SourceError("invalid_model_answer", "The answer could not be validated.", 503)
        for hit in cited_hits:
            if (hit.segment.tenant_id != tenant_id or hit.segment.project_id != project_id or
                    hit.segment.id not in retrieved or retrieved[hit.segment.id] != hit):
                raise SourceError("invalid_citation", "The answer evidence could not be validated.", 503)

        latency_ms = round((perf_counter() - started) * 1_000)
        run = RetrievalRun(
            tenant_id=tenant_id,
            project_id=project_id,
            embedding_provider=self.embedding_provider.name,
            embedding_model=self.embedding_provider.model,
            embedding_space=self.embedding_provider.space_id,
            embedding_dimensions=self.embedding_provider.dimensions,
            embedding_model_digest=self.embedding_provider.model_digest,
            embedding_input_tokens=query_batch.input_tokens,
            answer_provider=result.provider or self.answer_provider.name,
            answer_model=result.model or self.answer_provider.model,
            query_sha256=hashlib.sha256(question.encode("utf-8")).hexdigest(),
            retrieved_segment_ids=[hit.segment.id for hit in hits],
            cited_segment_ids=[hit.segment.id for hit in cited_hits],
            candidate_count=len(hits),
            latency_ms=latency_ms,
            prompt_version=result.prompt_version or getattr(self.answer_provider, 'prompt_version', 'quoted-evidence-v1'),
            input_tokens=result.input_tokens, output_tokens=result.output_tokens, answer_model_digest=result.model_digest,
            retrieval_version='semantic-hybrid-rrf-v2' if self.embedding_provider.space_id != 'signed-hash-v1:64' else 'hybrid-rrf-v1',
            reranker_version='cosine-identifier-v1' if self.embedding_provider.space_id != 'signed-hash-v1:64' else 'identifier-overlap-v1',
        )
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
                processing_version=hit.segment.processing_version,
                generation=hit.segment.generation,
                asr_origin=hit.asr_origin,
                visual_origin=hit.visual_origin,
            )
            for hit in cited_hits
        ]
        return QuestionResponse(
            answer=answer,
            abstained=abstained,
            citations=citations,
            retrieval_run_id=run.id,
            provider=run.answer_provider,
            model=run.answer_model,
            processing_version=run.retrieval_version,
            latency_ms=latency_ms,
        ), run

    def get_source(
        self,
        principal: AuthenticatedPrincipal,
        project_id: UUID,
        source_id: UUID,
    ) -> Source:
        self._actor_user_id(principal)
        return self.store.get_source(principal.tenant_id, project_id, source_id)
