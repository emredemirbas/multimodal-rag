from __future__ import annotations

import math
from datetime import datetime, timezone
from threading import RLock
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from .models import (
    AuthenticatedPrincipal,
    EvidenceSegment,
    Project,
    ProjectListStatus,
    ProjectStatus,
    RetrievalHit,
    RetrievalRun,
    Source,
)


class ProjectNotFoundError(LookupError):
    pass


class Store(Protocol):
    def healthcheck(self) -> None: ...
    def bootstrap_principal(self, principal: AuthenticatedPrincipal) -> UUID: ...
    def create_project(self, project: Project, actor_user_id: UUID) -> Project: ...
    def list_projects(
        self, tenant_id: str, status: ProjectListStatus
    ) -> list[Project]: ...
    def get_project(self, tenant_id: str, project_id: UUID) -> Project: ...
    def update_project_title(
        self,
        tenant_id: str,
        project_id: UUID,
        title: str,
        actor_user_id: UUID,
    ) -> Project: ...
    def archive_project(
        self, tenant_id: str, project_id: UUID, actor_user_id: UUID
    ) -> Project: ...
    def restore_project(
        self, tenant_id: str, project_id: UUID, actor_user_id: UUID
    ) -> Project: ...
    def delete_project(
        self, tenant_id: str, project_id: UUID, actor_user_id: UUID
    ) -> None: ...
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
        source_ids: list[UUID] | None = None,
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
        self._identity_users: dict[tuple[str, str], UUID] = {}
        self._memberships: set[tuple[str, UUID]] = set()
        self._audit_events: list[dict[str, object]] = []
        self._lock = RLock()

    def healthcheck(self) -> None:
        return None

    def bootstrap_principal(self, principal: AuthenticatedPrincipal) -> UUID:
        identity_key = (principal.provider, principal.subject)
        with self._lock:
            user_id = self._identity_users.setdefault(
                identity_key,
                uuid5(NAMESPACE_URL, f"identity:{principal.provider}:{principal.subject}"),
            )
            self._memberships.add((principal.tenant_id, user_id))
        return user_id

    def _audit(
        self,
        *,
        tenant_id: str,
        project_id: UUID,
        actor_user_id: UUID,
        action: str,
    ) -> None:
        self._audit_events.append(
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "actor_user_id": actor_user_id,
                "action": action,
                "created_at": datetime.now(timezone.utc),
            }
        )

    def _require_membership(self, tenant_id: str, actor_user_id: UUID) -> None:
        if (tenant_id, actor_user_id) not in self._memberships:
            raise ProjectNotFoundError("project not found")

    def create_project(self, project: Project, actor_user_id: UUID) -> Project:
        self._require_membership(project.tenant_id, actor_user_id)
        with self._lock:
            self._projects[(project.tenant_id, project.id)] = project
            self._audit(
                tenant_id=project.tenant_id,
                project_id=project.id,
                actor_user_id=actor_user_id,
                action="project.created",
            )
        return project

    def list_projects(
        self, tenant_id: str, status: ProjectListStatus
    ) -> list[Project]:
        projects = [
            project
            for (project_tenant, _), project in self._projects.items()
            if project_tenant == tenant_id
            and (status == ProjectListStatus.ALL or project.status.value == status.value)
        ]
        return sorted(projects, key=lambda project: (project.updated_at, project.id), reverse=True)

    def get_project(self, tenant_id: str, project_id: UUID) -> Project:
        try:
            return self._projects[(tenant_id, project_id)]
        except KeyError as exc:
            raise ProjectNotFoundError("project not found") from exc

    def update_project_title(
        self,
        tenant_id: str,
        project_id: UUID,
        title: str,
        actor_user_id: UUID,
    ) -> Project:
        self._require_membership(tenant_id, actor_user_id)
        existing = self.get_project(tenant_id, project_id)
        updated = existing.model_copy(
            update={"title": title, "updated_at": datetime.now(timezone.utc)}
        )
        with self._lock:
            self._projects[(tenant_id, project_id)] = updated
            self._audit(
                tenant_id=tenant_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                action="project.renamed",
            )
        return updated

    def archive_project(
        self, tenant_id: str, project_id: UUID, actor_user_id: UUID
    ) -> Project:
        self._require_membership(tenant_id, actor_user_id)
        existing = self.get_project(tenant_id, project_id)
        if existing.status == ProjectStatus.ARCHIVED:
            return existing
        now = datetime.now(timezone.utc)
        archived = existing.model_copy(
            update={
                "status": ProjectStatus.ARCHIVED,
                "archived_at": now,
                "updated_at": now,
            }
        )
        with self._lock:
            self._projects[(tenant_id, project_id)] = archived
            self._audit(
                tenant_id=tenant_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                action="project.archived",
            )
        return archived

    def restore_project(
        self, tenant_id: str, project_id: UUID, actor_user_id: UUID
    ) -> Project:
        self._require_membership(tenant_id, actor_user_id)
        existing = self.get_project(tenant_id, project_id)
        if existing.status == ProjectStatus.ACTIVE:
            return existing
        restored = existing.model_copy(
            update={
                "status": ProjectStatus.ACTIVE,
                "archived_at": None,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        with self._lock:
            self._projects[(tenant_id, project_id)] = restored
            self._audit(
                tenant_id=tenant_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                action="project.restored",
            )
        return restored

    def delete_project(
        self, tenant_id: str, project_id: UUID, actor_user_id: UUID
    ) -> None:
        self._require_membership(tenant_id, actor_user_id)
        self.get_project(tenant_id, project_id)
        with self._lock:
            self._projects.pop((tenant_id, project_id))
            source_keys = [
                key
                for key in self._sources
                if key[0] == tenant_id and key[1] == project_id
            ]
            for key in source_keys:
                self._sources.pop(key)
            self._segments = [
                segment
                for segment in self._segments
                if segment.tenant_id != tenant_id or segment.project_id != project_id
            ]
            self._idempotency = {
                key: value
                for key, value in self._idempotency.items()
                if key[0] != tenant_id or key[1] != project_id
            }
            self._runs = [
                run
                for run in self._runs
                if run.tenant_id != tenant_id or run.project_id != project_id
            ]
            self._audit(
                tenant_id=tenant_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                action="project.deleted",
            )

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
        source_ids: list[UUID] | None = None,
    ) -> list[RetrievalHit]:
        from .providers import content_tokens
        from .retrieval import CANDIDATES_PER_CHANNEL, fuse_and_rerank
        self.get_project(tenant_id, project_id)
        for source_id in source_ids or []:
            self.get_source(tenant_id, project_id, source_id)
        matches: list[RetrievalHit] = []
        for segment in self._segments:
            if segment.tenant_id != tenant_id or segment.project_id != project_id:
                continue
            if source_ids and segment.source_id not in source_ids:
                continue
            source = self._sources[(tenant_id, project_id, segment.source_id)]
            if source.status != "ready":
                continue
            score = cosine_similarity(query_embedding, segment.embedding)
            matches.append(
                RetrievalHit(segment=segment, source_filename=source.filename, score=score)
            )
        terms = content_tokens(query_text)
        lexical = sorted(
            [hit for hit in matches if terms & content_tokens(hit.segment.text)],
            key=lambda hit: (-len(terms & content_tokens(hit.segment.text)), str(hit.segment.id)),
        )[:CANDIDATES_PER_CHANNEL]
        semantic = sorted(matches, key=lambda hit: (-hit.score, str(hit.segment.id)))[:CANDIDATES_PER_CHANNEL]
        return fuse_and_rerank(query_text, [lexical, semantic], limit)

    def save_retrieval_run(self, run: RetrievalRun) -> None:
        self.get_project(run.tenant_id, run.project_id)
        with self._lock:
            self._runs.append(run)
