from __future__ import annotations

from httpx import AsyncClient
import pytest
from uuid import UUID

from app.postgres import DatabaseUnavailableError
from app.store import InMemoryStore
from conftest import auth_headers


pytestmark = pytest.mark.anyio


TRANSCRIPT = """WEBVTT

00:00:01.000 --> 00:00:05.000
The health endpoint reports whether the service is ready.
"""


async def create_project(
    client: AsyncClient,
    *,
    tenant: str = "tenant-a",
    title: str = "FastAPI course",
) -> dict:
    response = await client.post(
        "/api/v1/projects",
        headers=auth_headers(tenant),
        json={"title": title},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_project_crud_and_lifecycle_filters(client: AsyncClient) -> None:
    empty = await client.get("/api/v1/projects", headers=auth_headers())
    assert empty.status_code == 200
    assert empty.json() == {"items": []}

    created = await create_project(client)
    project_id = created["id"]
    assert created["status"] == "active"
    assert created["created_at"]
    assert created["updated_at"]
    assert created["archived_at"] is None

    detail = await client.get(
        f"/api/v1/projects/{project_id}", headers=auth_headers()
    )
    assert detail.status_code == 200
    assert detail.json()["title"] == "FastAPI course"

    renamed = await client.patch(
        f"/api/v1/projects/{project_id}",
        headers=auth_headers(),
        json={"title": "  Renamed project  "},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Renamed project"

    archived = await client.post(
        f"/api/v1/projects/{project_id}/archive", headers=auth_headers()
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["archived_at"] is not None

    active_list = await client.get("/api/v1/projects", headers=auth_headers())
    archived_list = await client.get(
        "/api/v1/projects?status=archived", headers=auth_headers()
    )
    all_list = await client.get(
        "/api/v1/projects?status=all", headers=auth_headers()
    )
    assert active_list.json() == {"items": []}
    assert [item["id"] for item in archived_list.json()["items"]] == [project_id]
    assert [item["id"] for item in all_list.json()["items"]] == [project_id]

    restored = await client.post(
        f"/api/v1/projects/{project_id}/restore", headers=auth_headers()
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"
    assert restored.json()["archived_at"] is None

    deleted = await client.delete(
        f"/api/v1/projects/{project_id}", headers=auth_headers()
    )
    assert deleted.status_code == 204
    assert deleted.content == b""
    missing = await client.get(
        f"/api/v1/projects/{project_id}", headers=auth_headers()
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "not_found"


async def test_authentication_is_required_and_x_tenant_id_is_not_trusted(
    client: AsyncClient,
) -> None:
    missing = await client.get("/api/v1/projects")
    legacy_header = await client.get(
        "/api/v1/projects", headers={"X-Tenant-ID": "tenant-a"}
    )
    invalid = await client.get(
        "/api/v1/projects", headers={"Authorization": "Bearer invalid-token"}
    )

    assert missing.status_code == 401
    assert missing.json()["code"] == "authentication_required"
    assert legacy_header.status_code == 401
    assert invalid.status_code == 401
    assert invalid.json()["code"] == "invalid_authentication"


async def test_cross_tenant_project_access_is_not_found(client: AsyncClient) -> None:
    project = await create_project(client, tenant="tenant-a")
    project_id = project["id"]
    tenant_b = auth_headers("tenant-b")

    responses = [
        await client.get(f"/api/v1/projects/{project_id}", headers=tenant_b),
        await client.patch(
            f"/api/v1/projects/{project_id}",
            headers=tenant_b,
            json={"title": "Cross tenant"},
        ),
        await client.post(
            f"/api/v1/projects/{project_id}/archive", headers=tenant_b
        ),
        await client.post(
            f"/api/v1/projects/{project_id}/restore", headers=tenant_b
        ),
        await client.delete(f"/api/v1/projects/{project_id}", headers=tenant_b),
    ]
    assert all(response.status_code == 404 for response in responses)

    tenant_b_list = await client.get("/api/v1/projects?status=all", headers=tenant_b)
    assert tenant_b_list.json() == {"items": []}
    still_present = await client.get(
        f"/api/v1/projects/{project_id}", headers=auth_headers("tenant-a")
    )
    assert still_present.status_code == 200


async def test_delete_cascades_in_memory_project_data_and_retains_audit(
    client: AsyncClient,
    store: InMemoryStore,
) -> None:
    project = await create_project(client)
    project_id = project["id"]
    project_uuid = UUID(project_id)
    ingested = await client.post(
        f"/api/v1/projects/{project_id}/sources/transcripts",
        headers=auth_headers(),
        json={
            "filename": "delete-me.vtt",
            "content": TRANSCRIPT,
            "authorization_mode": "owner_upload",
            "idempotency_key": "delete-cascade-0001",
        },
    )
    assert ingested.status_code == 201
    asked = await client.post(
        f"/api/v1/projects/{project_id}/questions",
        headers=auth_headers(),
        json={"question": "Which endpoint reports health?"},
    )
    assert asked.status_code == 200

    deleted = await client.delete(
        f"/api/v1/projects/{project_id}", headers=auth_headers()
    )
    assert deleted.status_code == 204
    assert not any(key[1] == project_uuid for key in store._sources)
    assert not any(segment.project_id == project_uuid for segment in store._segments)
    assert not any(run.project_id == project_uuid for run in store._runs)
    assert any(
        event["project_id"] == project_uuid and event["action"] == "project.deleted"
        for event in store._audit_events
    )


async def test_project_status_filter_uses_stable_validation_error(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/v1/projects?status=deleted", headers=auth_headers()
    )
    assert response.status_code == 422
    assert response.json() == {
        "code": "validation_error",
        "detail": "Request validation failed.",
    }


async def test_liveness_is_dependency_free_and_readiness_checks_store(
    client: AsyncClient,
) -> None:
    live = await client.get("/health/live")
    ready = await client.get("/health/ready")
    compatibility = await client.get("/health")
    assert live.status_code == ready.status_code == compatibility.status_code == 200
    assert live.json()["version"] == "0.3.0"


async def test_readiness_returns_safe_service_unavailable_when_database_is_down(
    client: AsyncClient,
    store: InMemoryStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable() -> None:
        raise DatabaseUnavailableError("database connection failed")

    monkeypatch.setattr(store, "healthcheck", unavailable)
    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "code": "database_unavailable",
        "detail": "The database is temporarily unavailable.",
    }
