from __future__ import annotations

import math
from threading import RLock
from typing import Protocol
from uuid import UUID

from .models import EvidenceSegment, Project, RetrievalHit, RetrievalRun, Source


class ProjectNotFoundError(LookupError):
    pass


class Store(Protocol):
    def healthcheck(self) -> None: ...
    def create_project(self, project: Project) -> Project: ...
    def get_project(self, tenant_id: str, project_id: UUID) -> Project: ...
    def get_source_by_idempotency_key(
        self, tenant_id: str, project_id: UUID, idempotency_key: str
    ) -> Source | None: ...
    def save_source(
        self, source: Source, segments: list[EvidenceSegment], idempotency_key: str
    ) -> Source: ...
    def get_source(self, tenant_id: str, project_id: UUID, source_id: UUID) -> Source: ...
    def search(
        self,
        tenant_id: str,
        project_id: UUID,
        query_text: str,
        query_embedding: list[float],
        limit: int,
    ) -> list[RetrievalHit]: ...
    def save_retrieval_run(self, run: RetrievalRun) -> None: ...


def cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


class InMemoryStore:
    """Test/demo store with the same tenant/project constraints as PostgreSQL."""

    def __init__(self) -> None:
        self._projects: dict[tuple[str, UUID], Project] = {}
        self._sources: dict[tuple[str, UUID, UUID], Source] = {}
        self._segments: list[EvidenceSegment] = []
        self._idempotency: dict[tuple[str, UUID, str], UUID] = {}
        self._runs: list[RetrievalRun] = []
        self._lock = RLock()

    def healthcheck(self) -> None:
        return None

    def create_project(self, project: Project) -> Project:
        with self._lock:
            self._projects[(project.tenant_id, project.id)] = project
        return project

    def get_project(self, tenant_id: str, project_id: UUID) -> Project:
        try:
            return self._projects[(tenant_id, project_id)]
        except KeyError as exc:
            raise ProjectNotFoundError("project not found") from exc

    def get_source_by_idempotency_key(
        self, tenant_id: str, project_id: UUID, idempotency_key: str
    ) -> Source | None:
        self.get_project(tenant_id, project_id)
        source_id = self._idempotency.get((tenant_id, project_id, idempotency_key))
        if source_id is None:
            return None
        return self._sources[(tenant_id, project_id, source_id)]

    def save_source(
        self, source: Source, segments: list[EvidenceSegment], idempotency_key: str
    ) -> Source:
        self.get_project(source.tenant_id, source.project_id)
        with self._lock:
            key = (source.tenant_id, source.project_id, idempotency_key)
            existing_id = self._idempotency.get(key)
            if existing_id is not None:
                return self._sources[(source.tenant_id, source.project_id, existing_id)]
            saved = source.model_copy(update={"segment_count": len(segments)})
            self._sources[(saved.tenant_id, saved.project_id, saved.id)] = saved
            self._segments.extend(segments)
            self._idempotency[key] = saved.id
        return saved

    def get_source(self, tenant_id: str, project_id: UUID, source_id: UUID) -> Source:
        self.get_project(tenant_id, project_id)
        try:
            return self._sources[(tenant_id, project_id, source_id)]
        except KeyError as exc:
            raise ProjectNotFoundError("source not found") from exc

    def search(
        self,
        tenant_id: str,
        project_id: UUID,
        query_text: str,
        query_embedding: list[float],
        limit: int,
    ) -> list[RetrievalHit]:
        self.get_project(tenant_id, project_id)
        matches: list[RetrievalHit] = []
        for segment in self._segments:
            if segment.tenant_id != tenant_id or segment.project_id != project_id:
                continue
            source = self._sources[(tenant_id, project_id, segment.source_id)]
            score = cosine_similarity(query_embedding, segment.embedding)
            matches.append(
                RetrievalHit(segment=segment, source_filename=source.filename, score=score)
            )
        return sorted(matches, key=lambda hit: hit.score, reverse=True)[:limit]

    def save_retrieval_run(self, run: RetrievalRun) -> None:
        self.get_project(run.tenant_id, run.project_id)
        with self._lock:
            self._runs.append(run)
