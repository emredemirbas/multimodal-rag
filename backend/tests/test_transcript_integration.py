from contextlib import contextmanager
from uuid import uuid4

import pytest

from app.chat.repository import ChatRepository
from app.models import AuthenticatedPrincipal, ProjectCreate, TranscriptIngestRequest
from app.sources.contracts import SourceError
from app.sources.transcript import TranscriptRepository
from app.store import ProjectNotFoundError
from test_checkpoints_integration import finish, long_transcript, use_semantic
from test_ingestion_integration import ingestion, register, run
from test_postgres_integration import isolated_postgres_url

pytestmark = pytest.mark.integration


def reader(fixture):
    repo, _, principal, project, actor = fixture
    browse = TranscriptRepository(repo.store)
    return lambda source, **query: browse.read(principal.tenant_id, project.id, actor, source, **query)


def test_bounded_stable_pagination_ordering_legacy_and_no_provider_io(ingestion):
    repo, service, principal, project, actor = ingestion
    # The compatibility path has no processing_versions row; it is still published
    # evidence. Tied times require the stable ID as the final sort key.
    content = "WEBVTT\n\n" + "\n\n".join(
        f"00:01.000 --> 00:05.000\nLegacy segment {i}. GET /health."
        for i in range(103))
    legacy = service.ingest_transcript(principal, project.id, TranscriptIngestRequest(
        filename="legacy.vtt", authorization_mode="owner_upload", idempotency_key="legacy-timeline",
        content=content, frame_candidates=[{"timestamp_seconds": 2, "ocr_text": "unrelated frame only", "description": "slide evidence"}],
    )).source
    assert legacy.frame_count == 1
    repo.artifacts.fail_get = True
    read = reader(ingestion)
    pages = [read(legacy.id, generation=1, page=page) for page in range(1, 4)]
    assert [len(page.items) for page in pages] == [50, 50, 3]
    assert all(page.total_segments == 103 and page.total_pages == 3 for page in pages)
    ids = [segment.segment_id for page in pages for segment in page.items]
    assert len(set(ids)) == 103 and ids == sorted(ids)
    assert read(legacy.id).items == pages[0].items
    assert ChatRepository(repo.store).evidence(principal.tenant_id, project.id, actor, ids[0]) == pages[0].items[0]
    with pytest.raises(SourceError) as missing:
        read(legacy.id, page=2)
    assert missing.value.code == "transcript_generation_required"
    for query in [{"page": 0}, {"page": 2001}, {"generation": 0}, {"generation": 2_147_483_648}]:
        with pytest.raises(SourceError):
            read(legacy.id, **query)
    for query in [{"generation": 1, "page": 4}, {"generation": 2}]:
        with pytest.raises(ProjectNotFoundError):
            read(legacy.id, **query)
    with repo.store._connect() as connection:
        assert not connection.execute("SELECT 1 FROM retrieval_runs WHERE tenant_id=%s AND project_id=%s", (principal.tenant_id, project.id)).fetchone()
        index = connection.execute("SELECT indexdef FROM pg_indexes WHERE schemaname=current_schema() AND indexname='content_segments_transcript_timeline_idx'").fetchone()["indexdef"]
        assert "generation, start_ms, end_ms, id" in index and "modality = 'transcript'" in index
        # Older one-segment/cue validation data may exceed the durable upload's
        # chunk cap. Browsing must not silently truncate its final pages.
        connection.execute("""INSERT INTO content_segments (id,tenant_id,project_id,source_id,modality,start_ms,end_ms,text,embedding,processing_version)
            SELECT gen_random_uuid(),cs.tenant_id,cs.project_id,cs.source_id,'transcript',10000+i*2,10001+i*2,
                   'Legacy block ' || i,cs.embedding,cs.processing_version
            FROM content_segments cs CROSS JOIN generate_series(1,9898) AS i
            WHERE cs.tenant_id=%s AND cs.project_id=%s AND cs.source_id=%s AND cs.id=%s""",
            (principal.tenant_id, project.id, legacy.id, ids[0]))
    last_legacy = read(legacy.id, generation=1, page=201)
    assert last_legacy.total_segments == 10_001 and last_legacy.total_pages == 201 and len(last_legacy.items) == 1


def test_unpublished_staging_hidden_and_reprocess_preserves_old_pages_across_spaces(ingestion, monkeypatch):
    repo, _, principal, project, actor = ingestion
    read = reader(ingestion)
    use_semantic(repo, monkeypatch)
    source = register(ingestion, content=long_transcript(17))
    assert not run(repo, source)  # One accepted private batch, no active generation.
    page = read(source.source.id)
    assert page.generation is None and page.total_segments == 0 and not page.items
    with pytest.raises(ProjectNotFoundError):
        read(source.source.id, generation=1)
    finish(repo, source)
    original = read(source.source.id, generation=1)
    assert original.total_segments == 17
    replacement = repo.command(principal.tenant_id, project.id, source.source.id, actor, "reprocess", "timeline-reprocess")
    assert not run(repo, replacement)
    assert read(source.source.id).items == original.items
    with pytest.raises(ProjectNotFoundError):
        read(source.source.id, generation=2)
    repo.command(principal.tenant_id, project.id, source.source.id, actor, "cancel", "timeline-cancel")
    assert read(source.source.id, generation=1).items == original.items
    repo.command(principal.tenant_id, project.id, source.source.id, actor, "retry", "timeline-retry")
    finish(repo, replacement)
    newest = read(source.source.id)
    assert newest.generation == newest.active_generation == 2 and newest.total_segments == 17
    retained = read(source.source.id, generation=1)
    assert retained.items == original.items and retained.active_generation == 2
    assert {item.segment_id for item in retained.items}.isdisjoint(item.segment_id for item in newest.items)
    # Browse is not constrained by the currently configured search space.
    from dataclasses import replace
    from app.providers import DeterministicHashEmbeddingProvider
    repo.settings = replace(repo.settings, embedding_provider="hash")
    assert read(source.source.id).items == newest.items
    monkeypatch.setattr("app.jobs.processing.build_embedding_provider", lambda _: DeterministicHashEmbeddingProvider())
    hash_generation = repo.command(principal.tenant_id, project.id, source.source.id, actor, "reprocess", "timeline-hash-space")
    assert run(repo, hash_generation)
    assert read(source.source.id).generation == 3
    assert read(source.source.id, generation=1).items == original.items


def test_metadata_has_no_transcript_and_archive_is_readable(ingestion):
    repo, service, principal, project, actor = ingestion
    result = register(ingestion)
    assert run(repo, result)
    transcript = reader(ingestion)(result.source.id)
    service.archive_project(principal, project.id)
    assert reader(ingestion)(result.source.id) == transcript
    with repo.store._connect() as connection:
        connection.execute("UPDATE sources SET kind='youtube_video',provider='youtube',status='metadata_ready',active_generation=NULL WHERE tenant_id=%s AND project_id=%s AND id=%s", (principal.tenant_id, project.id, result.source.id))
    metadata = reader(ingestion)(result.source.id)
    assert metadata.source_kind == "youtube_video" and metadata.generation is None and not metadata.items


def test_all_reads_scoped_revoked_and_deleted(ingestion):
    repo, service, principal, project, actor = ingestion
    result = register(ingestion)
    assert run(repo, result)
    browse = TranscriptRepository(repo.store)
    other_project = service.create_project(principal, ProjectCreate(title="Other scope"))
    other = AuthenticatedPrincipal(provider="test", subject="other-reader", tenant_id="other-tenant")
    other_actor = repo.store.bootstrap_principal(other)
    for tenant, scope, user, source in [(other.tenant_id, project.id, other_actor, result.source.id),
                                      (principal.tenant_id, other_project.id, actor, result.source.id),
                                      (principal.tenant_id, project.id, actor, uuid4())]:
        with pytest.raises(ProjectNotFoundError):
            browse.read(tenant, scope, user, source)
    with repo.store._connect() as connection:
        connection.execute("DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s", (principal.tenant_id, actor))
    with pytest.raises(ProjectNotFoundError):
        reader(ingestion)(result.source.id)
    repo.store.bootstrap_principal(principal)
    repo.delete_source(principal.tenant_id, project.id, result.source.id, actor)
    with pytest.raises(ProjectNotFoundError):
        reader(ingestion)(result.source.id, generation=1)
    service.delete_project(principal, project.id)
    with pytest.raises(ProjectNotFoundError):
        reader(ingestion)(result.source.id)


def test_one_read_has_consistent_snapshot_during_source_deletion(ingestion, monkeypatch):
    repo, _, principal, project, _ = ingestion
    source = register(ingestion)
    assert run(repo, source)
    original_connect = repo.store._connect
    deleted = False

    class InterleavedConnection:
        def __init__(self, connection): self.connection = connection
        def execute(self, query, parameters=None):
            nonlocal deleted
            result = self.connection.execute(query, parameters)
            if "SELECT count(*) AS total" in query and not deleted:
                # Delete between count and row read, on a distinct committed DB connection.
                with original_connect() as concurrent:
                    concurrent.execute("DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s", (principal.tenant_id, project.id, source.source.id))
                deleted = True
            return result

    @contextmanager
    def interleaved_connect():
        with original_connect() as connection:
            yield InterleavedConnection(connection)

    monkeypatch.setattr(repo.store, "_connect", interleaved_connect)
    page = reader(ingestion)(source.source.id)
    assert deleted and page.total_segments == len(page.items) == 1
    with pytest.raises(ProjectNotFoundError):
        reader(ingestion)(source.source.id)


@pytest.mark.anyio
async def test_http_auth_scope_bounds_and_safe_errors(ingestion):
    from httpx import ASGITransport, AsyncClient
    from app.config import Settings
    from app.main import create_app
    from conftest import MappingAuthenticator, auth_headers
    repo, _, _, _, _ = ingestion
    app = create_app(settings=Settings(environment="test", development_auth_token="test-token-long-enough", auto_migrate=False),
                     store=repo.store, authenticator=MappingAuthenticator(), artifacts=repo.artifacts)
    async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        project = (await client.post("/api/v1/projects", headers=auth_headers(), json={"title": "HTTP transcript"})).json()
        base = "/api/v1/projects/" + project["id"]
        uploaded = await client.post(base + "/sources/uploads", headers=auth_headers(), data={"authorization_mode": "owner_upload", "idempotency_key": "http-transcript-key"},
                                     files={"file": ("tutorial.vtt", long_transcript(3), "text/vtt")})
        source = uploaded.json()["source"]["id"]
        path = base + "/sources/" + source + "/transcript"
        assert (await client.get(path)).status_code == 401
        assert (await client.get(path, headers=auth_headers("tenant-b"))).status_code == 404
        pending = await client.get(path, headers=auth_headers())
        assert pending.status_code == 200 and pending.json()["items"] == []
        assert pending.headers["cache-control"] == "no-store"
        for query in ["?page=0", "?page=2001", "?page=2", "?generation=0", "?generation=2147483648", "?generation=no"]:
            error = await client.get(path + query, headers=auth_headers())
            assert error.status_code == 422 and "tutorial.vtt" not in error.text
        assert (await client.get(path + "?generation=1", headers=auth_headers())).status_code == 404
