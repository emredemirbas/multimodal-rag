from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest

from app.chat.contracts import ConversationCreate, MessageRequest
from app.chat.delivery import deliver
from app.chat.repository import ChatRepository
from app.models import AuthenticatedPrincipal, ProjectCreate, TranscriptIngestRequest
from app.metrics import Metrics
from app.postgres import PostgresStore
from app.providers import DeterministicHashEmbeddingProvider, EvidenceExtractiveAnswerProvider
from app.service import TutorialService
from app.sources.contracts import SourceError
from test_postgres_integration import isolated_postgres_url

pytestmark = pytest.mark.integration


@pytest.fixture
def chat_fixture(isolated_postgres_url):
    store = PostgresStore(isolated_postgres_url)
    store.run_migrations()
    service = TutorialService(store, DeterministicHashEmbeddingProvider(), EvidenceExtractiveAnswerProvider())
    principal = AuthenticatedPrincipal(provider="test", subject="chat-user", tenant_id="chat-tenant")
    project = service.create_project(principal, ProjectCreate(title="Chat tests"))
    actor = store.bootstrap_principal(principal)
    source = service.ingest_transcript(principal, project.id, TranscriptIngestRequest(filename="tutorial.vtt", authorization_mode="owner_upload",
                idempotency_key="chat-source-0001", content="WEBVTT\n\n00:01.000 --> 00:05.000\ncreate_app() exposes GET /health for service availability.\n")).source
    repository = ChatRepository(store, Metrics())
    conversation = repository.create(principal.tenant_id, project.id, actor, ConversationCreate(idempotency_key="chat-create-0001"))
    return repository, service, principal, project, actor, source, conversation


def prepare(fixture, key="chat-message-0001", question="What is GET /health?"):
    repository, service, principal, project, actor, source, conversation = fixture
    body = MessageRequest(question=question, idempotency_key=key, source_ids=[source.id])
    response, run = service.prepare_answer(principal, project.id, body.question, body.source_ids)
    return body, response, run


def record(fixture, prepared=None):
    repository, _, principal, project, actor, _, conversation = fixture
    body, response, run = prepared or prepare(fixture)
    return repository.record(principal.tenant_id, project.id, actor, conversation.id, body, response, run)


def test_atomic_history_idempotency_conflict_and_attribution(chat_fixture):
    repo, _, principal, project, actor, source, conversation = chat_fixture
    turn = record(chat_fixture)
    replay = repo.replay(principal.tenant_id, project.id, actor, conversation.id, prepare(chat_fixture)[0])
    assert replay == turn and not turn.response.abstained
    assert len(repo.history(principal.tenant_id, project.id, actor, conversation.id).turns) == 1
    evidence = repo.evidence(principal.tenant_id, project.id, actor, turn.response.citations[0].segment_id)
    assert evidence.start_ms == 1000 and evidence.generation == 1 and "GET /health" in evidence.text
    with pytest.raises(SourceError) as error:
        repo.replay(principal.tenant_id, project.id, actor, conversation.id, MessageRequest(question="different question", idempotency_key="chat-message-0001"))
    assert error.value.status == 409
    with repo.store._connect() as connection:
        assert connection.execute("SELECT count(*) AS count FROM retrieval_runs WHERE tenant_id=%s AND project_id=%s", (principal.tenant_id, project.id)).fetchone()["count"] == 1
        row = connection.execute("SELECT * FROM chat_turns WHERE tenant_id=%s AND project_id=%s AND id=%s", (principal.tenant_id, project.id, turn.id)).fetchone()
        assert row["prompt_version"] and row["reranker_version"] and row["billed_usd"] == 0 and row["input_tokens"] is None


def test_concurrent_same_key_commits_one_turn_and_one_run(chat_fixture):
    prepared = [prepare(chat_fixture), prepare(chat_fixture)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda item: record(chat_fixture, item), prepared))
    assert results[0].id == results[1].id
    repo, _, principal, project, actor, _, conversation = chat_fixture
    assert len(repo.history(principal.tenant_id, project.id, actor, conversation.id).turns) == 1
    assert 'tutorial_chat_turns_total{outcome="answered"} 1' in repo.metrics.render()
    with repo.store._connect() as connection:
        assert connection.execute("SELECT count(*) AS count FROM retrieval_runs WHERE tenant_id=%s AND project_id=%s", (principal.tenant_id, project.id)).fetchone()["count"] == 1


def test_filters_and_all_read_write_boundaries_are_scoped(chat_fixture):
    repo, service, principal, project, actor, source, conversation = chat_fixture
    turn = record(chat_fixture)
    other_project = service.create_project(principal, ProjectCreate(title="Other project"))
    other = AuthenticatedPrincipal(provider="test", subject="other-user", tenant_id="other-tenant")
    other_actor = repo.store.bootstrap_principal(other)
    for tenant, scoped_project, scoped_actor in [(other.tenant_id, project.id, other_actor), (principal.tenant_id, other_project.id, actor)]:
        for operation in [lambda: repo.history(tenant, scoped_project, scoped_actor, conversation.id),
                          lambda: repo.evidence(tenant, scoped_project, scoped_actor, turn.response.citations[0].segment_id),
                          lambda: repo.replay(tenant, scoped_project, scoped_actor, conversation.id, prepare(chat_fixture)[0])]:
            with pytest.raises(LookupError):
                operation()
        assert not repo.readable(tenant, scoped_project, scoped_actor, conversation.id, turn.id)
    with pytest.raises(LookupError):
        service.ask(principal, other_project.id, "health", [source.id])
    assert service.ask(principal, other_project.id, "health").abstained


def test_source_delete_removes_derived_chat_and_project_cascades(chat_fixture):
    repo, service, principal, project, actor, source, conversation = chat_fixture
    turn = record(chat_fixture)
    prepared = prepare(chat_fixture, "message-deletion-race")
    with repo.store._connect() as connection:
        connection.execute("DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s", (principal.tenant_id, project.id, source.id))
    assert not repo.history(principal.tenant_id, project.id, actor, conversation.id).turns
    assert not repo.readable(principal.tenant_id, project.id, actor, conversation.id, turn.id)
    with pytest.raises(SourceError, match="evidence changed"):
        record(chat_fixture, prepared)
    service.delete_project(principal, project.id)
    with repo.store._connect() as connection:
        for table in ["conversations", "chat_turns", "message_citations", "retrieval_runs"]:
            assert connection.execute(f"SELECT count(*) AS count FROM {table} WHERE tenant_id=%s AND project_id=%s", (principal.tenant_id, project.id)).fetchone()["count"] == 0


@pytest.mark.anyio
async def test_stream_stops_after_source_delete_and_replay_survives_disconnect(chat_fixture):
    repo, _, principal, project, actor, source, conversation = chat_fixture
    turn = record(chat_fixture)
    generator = deliver(repo, principal.tenant_id, project.id, actor, conversation.id, turn)
    assert (await anext(generator)).startswith("event: start")
    await generator.aclose()
    assert repo.replay(principal.tenant_id, project.id, actor, conversation.id, prepare(chat_fixture)[0]).id == turn.id
    generator = deliver(repo, principal.tenant_id, project.id, actor, conversation.id, turn)
    await anext(generator)
    with repo.store._connect() as connection:
        connection.execute("DELETE FROM sources WHERE tenant_id=%s AND project_id=%s AND id=%s", (principal.tenant_id, project.id, source.id))
    assert "evidence_unavailable" in await anext(generator)
    with pytest.raises(StopAsyncIteration):
        await anext(generator)


@pytest.mark.anyio
async def test_chat_http_stream_and_authorization(chat_fixture):
    import json
    from httpx import ASGITransport, AsyncClient
    from app.config import Settings
    from app.main import create_app
    from conftest import MappingAuthenticator, auth_headers
    repo, _, _, _, _, _, _ = chat_fixture
    app = create_app(settings=Settings(environment="test", development_auth_token="test-token-long-enough", auto_migrate=False),
                     store=repo.store, authenticator=MappingAuthenticator())
    async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        project = (await client.post("/api/v1/projects", headers=auth_headers(), json={"title":"HTTP chat"})).json()
        path = "/api/v1/projects/" + project["id"]
        created = await client.post(path+"/conversations", headers=auth_headers(), json={"idempotency_key":"http-conversation-key"})
        assert created.status_code == 201
        conversation = created.json()["id"]
        stream_path = path+"/conversations/"+conversation+"/messages"
        body = {"question":"Is Kubernetes covered?", "idempotency_key":"http-message-key"}
        assert (await client.post(stream_path, json=body)).status_code == 401
        assert (await client.post(stream_path, headers=auth_headers("tenant-b"), json=body)).status_code == 404
        response = await client.post(stream_path, headers=auth_headers(), json=body)
        assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
        complete = json.loads(response.text.split("event: complete\ndata: ")[1].split("\n\n")[0])
        assert complete["response"]["abstained"] and not complete["response"]["citations"]
        assert (await client.post(stream_path, headers=auth_headers(), json=body)).text == response.text
        oversized = await client.post(stream_path, headers=auth_headers(), content=b"x"*16_385)
        assert oversized.status_code == 413 and oversized.json()["code"] == "message_too_large"
