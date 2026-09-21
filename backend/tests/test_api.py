from __future__ import annotations

from httpx import AsyncClient
import pytest


pytestmark = pytest.mark.anyio


TRANSCRIPT = """WEBVTT

00:00:01.000 --> 00:00:05.000
Create the FastAPI application and define its routes.

00:00:05.000 --> 00:00:09.000
The GET health endpoint at slash health checks whether the service is running.

00:00:09.000 --> 00:00:13.000
Run the application with the Uvicorn server.
"""


async def create_project(client: AsyncClient, tenant: str = "tenant-a") -> str:
    response = await client.post(
        "/api/v1/projects",
        headers={"X-Tenant-ID": tenant},
        json={"title": "FastAPI course"},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def ingest(client: AsyncClient, project_id: str, tenant: str = "tenant-a") -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/sources/transcripts",
        headers={"X-Tenant-ID": tenant},
        json={
            "filename": "tutorial.vtt",
            "content": TRANSCRIPT,
            "authorization_mode": "owner_upload",
            "idempotency_key": "tutorial-upload-0001",
            "frame_candidates": [
                {
                    "timestamp_seconds": 6,
                    "ocr_text": "GET /health 200 OK",
                    "description": "OpenAPI documentation showing the health route",
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_end_to_end_cited_answer(client: AsyncClient) -> None:
    project_id = await create_project(client)
    source = await ingest(client, project_id)
    assert source["source"]["segment_count"] == 4
    assert source["source"]["frame_count"] == 1

    response = await client.post(
        f"/api/v1/projects/{project_id}/questions",
        headers={"X-Tenant-ID": "tenant-a"},
        json={"question": "Which endpoint checks service health?"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["abstained"] is False
    assert body["citations"]
    assert all(citation["source_id"] == source["source"]["id"] for citation in body["citations"])
    assert all(citation["start_ms"] >= 0 for citation in body["citations"])


async def test_unsupported_question_abstains(client: AsyncClient) -> None:
    project_id = await create_project(client)
    await ingest(client, project_id)
    response = await client.post(
        f"/api/v1/projects/{project_id}/questions",
        headers={"X-Tenant-ID": "tenant-a"},
        json={"question": "How do Kubernetes ingress controllers manage TLS certificates?"},
    )
    assert response.status_code == 200
    assert response.json()["abstained"] is True
    assert response.json()["citations"] == []


async def test_idempotent_ingestion_returns_same_source(client: AsyncClient) -> None:
    project_id = await create_project(client)
    first = await ingest(client, project_id)
    second = await ingest(client, project_id)
    assert second["deduplicated"] is True
    assert second["source"]["id"] == first["source"]["id"]


async def test_tenant_cannot_access_another_tenants_project(client: AsyncClient) -> None:
    project_id = await create_project(client, "tenant-a")
    source = await ingest(client, project_id, "tenant-a")

    query = await client.post(
        f"/api/v1/projects/{project_id}/questions",
        headers={"X-Tenant-ID": "tenant-b"},
        json={"question": "Which endpoint checks health?"},
    )
    direct = await client.get(
        f"/api/v1/projects/{project_id}/sources/{source['source']['id']}",
        headers={"X-Tenant-ID": "tenant-b"},
    )
    assert query.status_code == 404
    assert direct.status_code == 404


async def test_rejects_unsupported_source_and_invalid_transcript(client: AsyncClient) -> None:
    project_id = await create_project(client)
    unsupported = await client.post(
        f"/api/v1/projects/{project_id}/sources/transcripts",
        headers={"X-Tenant-ID": "tenant-a"},
        json={
            "filename": "video.mp4",
            "content": "binary",
            "authorization_mode": "owner_upload",
            "idempotency_key": "unsupported-0001",
        },
    )
    invalid = await client.post(
        f"/api/v1/projects/{project_id}/sources/transcripts",
        headers={"X-Tenant-ID": "tenant-a"},
        json={
            "filename": "bad.vtt",
            "content": "WEBVTT without cues",
            "authorization_mode": "owner_upload",
            "idempotency_key": "invalid-transcript-0001",
        },
    )
    assert unsupported.status_code == 422
    assert invalid.status_code == 422


async def test_rejects_blank_project_title_and_question(client: AsyncClient) -> None:
    project = await client.post(
        "/api/v1/projects",
        headers={"X-Tenant-ID": "tenant-a"},
        json={"title": "   "},
    )
    assert project.status_code == 422

    project_id = await create_project(client)
    question = await client.post(
        f"/api/v1/projects/{project_id}/questions",
        headers={"X-Tenant-ID": "tenant-a"},
        json={"question": "  "},
    )
    assert question.status_code == 422


async def test_metrics_use_route_templates_not_project_ids(client: AsyncClient) -> None:
    project_id = await create_project(client)
    await ingest(client, project_id)
    metrics = await client.get("/metrics")
    assert metrics.status_code == 200
    assert project_id not in metrics.text
    assert "/api/v1/projects/{project_id}/sources/transcripts" in metrics.text
