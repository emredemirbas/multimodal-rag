from dataclasses import replace
from pathlib import Path
import hashlib
from uuid import uuid4

import pytest

from app.chat.contracts import ConversationCreate, MessageRequest
from app.chat.repository import ChatRepository
from app.embedding_profiles import HASH_SPACE, QWEN_SPACE, QWEN_DIGEST
from app.jobs.dispatch import cleanup_once
from app.models import AuthenticatedPrincipal, ProjectCreate, TranscriptIngestRequest
from app.postgres import PostgresStore
from app.providers import EmbeddingBatch, EvidenceExtractiveAnswerProvider, DeterministicHashEmbeddingProvider
from app.service import TutorialService
from app.sources.contracts import SourceError
from app.store import ProjectNotFoundError
from test_postgres_integration import isolated_postgres_url
from test_ingestion_integration import ingestion, register, run

pytestmark = pytest.mark.integration


class FixtureSemanticProvider:
    name, model, space_id, model_digest, dimensions = 'ollama-local', 'qwen3-embedding:0.6b', QWEN_SPACE, QWEN_DIGEST, 1024
    def embed_documents(self, texts): return EmbeddingBatch([[1.] + [0.] * 1023 for _ in texts], len(texts)*12)
    def embed_query(self, text): return self.embed_documents([text])


def test_reindex_spaces_failed_activation_provenance_usage_isolation_and_deletion(ingestion, monkeypatch):
    repo, service, principal, project, actor = ingestion
    old = register(ingestion); assert run(repo, old)
    old_segment = service.ask(principal, project.id, 'GET /health').citations[0].segment_id
    chat = ChatRepository(repo.store)
    convo = chat.create(principal.tenant_id, project.id, actor, ConversationCreate(idempotency_key='semantic-conversation'))
    body = MessageRequest(question='GET /health', idempotency_key='old-hash-turn')
    response, attribution = service.prepare_answer(principal, project.id, body.question)
    chat.record(principal.tenant_id, project.id, actor, convo.id, body, response, attribution)
    second_hash = register(ingestion, key='second-hash-source'); assert run(repo, second_hash)
    repo.settings = replace(repo.settings, embedding_provider='ollama')
    assert repo.get_source(principal.tenant_id, project.id, old.source.id).reindex_required
    service.embedding_provider = FixtureSemanticProvider()
    # Active hash evidence is excluded even from lexical candidates in semantic mode.
    assert service.ask(principal, project.id, 'GET /health').abstained
    replacement = repo.command(principal.tenant_id, project.id, old.source.id, actor, 'reprocess', 'semantic-reindex-1')
    class Failed(FixtureSemanticProvider):
        def embed_documents(self, texts): raise SourceError('invalid_embeddings', 'Invalid response.')
    monkeypatch.setattr('app.jobs.processing.build_embedding_provider', lambda _: Failed())
    assert not run(repo, replacement)
    assert repo.get_source(principal.tenant_id, project.id, old.source.id).active_generation == 1
    assert chat.evidence(principal.tenant_id, project.id, actor, old_segment).generation == 1
    replacement = repo.command(principal.tenant_id, project.id, old.source.id, actor, 'retry', 'semantic-retry-1')
    monkeypatch.setattr('app.jobs.processing.build_embedding_provider', lambda _: FixtureSemanticProvider())
    assert run(repo, replacement) and not run(repo, replacement)
    indexed = repo.get_source(principal.tenant_id, project.id, old.source.id)
    assert indexed.active_generation == 2 and indexed.active_embedding_space == QWEN_SPACE and not indexed.reindex_required
    response, attribution = service.prepare_answer(principal, project.id, 'Which route shows the application is alive?')
    assert not response.abstained and response.citations[0].generation == 2
    body = MessageRequest(question='Which route shows the application is alive?', idempotency_key='semantic-turn')
    chat.record(principal.tenant_id, project.id, actor, convo.id, body, response, attribution)
    assert chat.evidence(principal.tenant_id, project.id, actor, old_segment).generation == 1
    assert len(chat.history(principal.tenant_id, project.id, actor, convo.id).turns) == 2
    # Switching back cannot accidentally retrieve new active 1024-D evidence.
    assert not repo.store.search(principal.tenant_id, project.id, 'GET /health', [1.]+[0.]*63, 4, [old.source.id])
    # Two active sources with different dimensions must not cause a cosine error
    # or leak hash evidence through the lexical channel.
    mixed = repo.store.search(principal.tenant_id, project.id, 'GET /health', [1.]+[0.]*1023, 4, embedding_space=QWEN_SPACE)
    assert mixed and all(hit.segment.source_id == old.source.id for hit in mixed)
    other = service.create_project(principal, ProjectCreate(title='Other'))
    assert not repo.store.search(principal.tenant_id, other.id, 'GET /health', [1.]+[0.]*1023, 4, embedding_space=QWEN_SPACE)
    for tenant, scoped_project in [('foreign', project.id), (principal.tenant_id, other.id)]:
        with pytest.raises(ProjectNotFoundError): repo.store.search(tenant, scoped_project, 'health', [1.]+[0.]*1023, 4, [old.source.id], embedding_space=QWEN_SPACE)
    with repo.store._connect() as connection:
        version = connection.execute('SELECT * FROM processing_versions WHERE tenant_id=%s AND project_id=%s AND source_id=%s AND generation=2', (principal.tenant_id,project.id,old.source.id)).fetchone()
        assert version['embedding_dimensions'] == 1024 and version['embedding_space'] == QWEN_SPACE and version['embedding_model_digest'] == QWEN_DIGEST
        usage = connection.execute('SELECT * FROM usage_events WHERE tenant_id=%s AND project_id=%s AND generation=2', (principal.tenant_id,project.id)).fetchone()
        assert usage['input_tokens'] == 12 and usage['model_digest'] == QWEN_DIGEST and usage['billed_usd'] == 0
        record = connection.execute('SELECT * FROM retrieval_runs WHERE tenant_id=%s AND project_id=%s AND id=%s', (principal.tenant_id,project.id,attribution.id)).fetchone()
        assert record['embedding_input_tokens'] == 12 and record['embedding_dimensions'] == 1024 and record['embedding_space'] == QWEN_SPACE
    repo.delete_source(principal.tenant_id, project.id, old.source.id, actor)
    repo.delete_source(principal.tenant_id, project.id, second_hash.source.id, actor)
    assert cleanup_once(repo) == 1 and cleanup_once(repo) == 1 and not repo.artifacts.objects
    assert not chat.history(principal.tenant_id, project.id, actor, convo.id).turns
    with pytest.raises(ProjectNotFoundError): chat.evidence(principal.tenant_id, project.id, actor, old_segment)
    with repo.store._connect() as connection:
        for table in ['content_segments','processing_versions','usage_events']:
            assert connection.execute(f'SELECT count(*) AS n FROM {table} WHERE tenant_id=%s AND project_id=%s', (principal.tenant_id,project.id)).fetchone()['n'] == 0


def test_semantic_long_transcript_continues_without_consuming_retries_and_cancellation(ingestion, monkeypatch):
    repo, _, principal, project, actor = ingestion
    repo.settings = replace(repo.settings, embedding_provider='ollama')
    monkeypatch.setattr('app.jobs.processing.build_embedding_provider', lambda _: FixtureSemanticProvider())
    # Gaps force separate chunks without overflowing the normal byte/cue caps.
    cues = '\n\n'.join(f'{i*10//60:02d}:{i*10%60:02d}.000 --> {i*10//60:02d}:{i*10%60+1:02d}.000\nChunk {i}.' for i in range(129))
    too_large = register(ingestion, content=('WEBVTT\n\n'+cues).encode())
    assert not run(repo, too_large)
    pending = repo.get_job(principal.tenant_id,project.id,too_large.job.id)
    assert pending.stage == 'waiting_continuation' and pending.processed_segments == 64 and pending.total_segments == 129
    with repo.store._connect() as connection:
        connection.execute('UPDATE processing_jobs SET available_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s', (principal.tenant_id,project.id,too_large.job.id))
    assert not run(repo, too_large)
    with repo.store._connect() as connection:
        connection.execute('UPDATE processing_jobs SET available_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s', (principal.tenant_id,project.id,too_large.job.id))
    assert run(repo, too_large)
    done = repo.get_job(principal.tenant_id,project.id,too_large.job.id)
    assert done.attempt_count == 1 and done.delivery_count == 3 and done.processed_segments == 129
    cancelled = register(ingestion, key='cancel-semantic')
    repo.command(principal.tenant_id,project.id,cancelled.source.id,actor,'cancel','cancel-semantic-command')
    assert not run(repo, cancelled)


def test_migration_preserves_existing_hash_segments_and_citations(isolated_postgres_url):
    store = PostgresStore(isolated_postgres_url)
    migrations = sorted((Path(__file__).parents[1]/'app/migrations').glob('*.sql'))
    with store._connect() as connection:
        connection.execute('CREATE TABLE schema_migrations(version text PRIMARY KEY,sha256 text,applied_at timestamptz DEFAULT now())')
        for migration in migrations[:6]:
            script = migration.read_text()
            connection.execute(script)
            connection.execute('INSERT INTO schema_migrations(version,sha256) VALUES(%s,%s)', (migration.name,hashlib.sha256(script.encode()).hexdigest()))
        connection.execute("INSERT INTO tenants(id) VALUES ('legacy')")
        project, source, segment = uuid4(),uuid4(),uuid4()
        connection.execute("INSERT INTO projects(tenant_id,id,title) VALUES('legacy',%s,'Legacy')", (project,))
        connection.execute("INSERT INTO sources(tenant_id,project_id,id,filename,authorization_mode,status,active_generation,processing_version,idempotency_key) VALUES('legacy',%s,%s,'legacy.vtt','owner_upload','ready',1,'legacy-version','legacy-key')", (project,source))
        connection.execute("INSERT INTO content_segments(tenant_id,project_id,source_id,id,modality,start_ms,end_ms,text,embedding,processing_version) VALUES('legacy',%s,%s,%s,'transcript',0,1000,'GET /health',%s::vector,'legacy-version')", (project,source,segment,store._vector_literal([1.]+[0.]*63)))
    store.run_migrations(); store.run_migrations()
    found = store.search('legacy',project,'GET /health',[1.]+[0.]*63,4)
    assert found[0].segment.id == segment and found[0].segment.processing_version == 'legacy-version'
    assert found[0].segment.embedding_space == HASH_SPACE and len(found[0].segment.embedding) == 64
    assert not store.search('legacy',project,'GET /health',[1.]+[0.]*1023,4,embedding_space=QWEN_SPACE)
