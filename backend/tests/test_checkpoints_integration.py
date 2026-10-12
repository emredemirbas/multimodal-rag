from dataclasses import replace
from uuid import uuid4

import pytest

from app.chat.repository import ChatRepository
from app.embedding_profiles import QWEN_SPACE
from app.jobs.checkpoints import TranscriptCheckpoints
from app.jobs.dispatch import cleanup_once, dispatch_once
from app.models import EvidenceSegment
from app.providers import EmbeddingBatch
from app.sources.chunking import PROCESSING_VERSION, chunk_transcript, segment_id
from app.sources.contracts import SourceError
from app.store import ProjectNotFoundError
from test_embedding_spaces_integration import FixtureSemanticProvider
from test_ingestion_integration import ingestion, register, run
from test_postgres_integration import isolated_postgres_url

pytestmark = pytest.mark.integration


def long_transcript(count):
    return ('WEBVTT\n\n'+'\n\n'.join(
        f'{i*10//60:02d}:{i*10%60:02d}.000 --> {i*10//60:02d}:{i*10%60+1:02d}.000\nChunk {i}. GET /health reports service availability.'
        for i in range(count))).encode()


def make_due(repo, registration):
    scope = (registration.source.tenant_id, registration.source.project_id, registration.job.id)
    with repo.store._connect() as connection:
        connection.execute('UPDATE processing_jobs SET available_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s', scope)
        connection.execute('UPDATE outbox_events SET available_at=now() WHERE tenant_id=%s AND project_id=%s AND job_id=%s', scope)


def finish(repo, registration):
    for _ in range(25):
        make_due(repo, registration)
        if run(repo, registration): return
        state = repo.get_job(registration.source.tenant_id,registration.source.project_id,registration.job.id)
        assert state.status in {'pending','retrying'}, state.failure_code
    raise AssertionError('Test-owned job did not finish bounded deliveries')


class CountingProvider(FixtureSemanticProvider):
    def __init__(self): self.calls, self.fail_once = [], False
    def embed_documents(self, texts):
        self.calls.extend(texts)
        if self.fail_once:
            self.fail_once = False
            raise SourceError('local_embeddings_unavailable', 'Fixture outage.', transient=True)
        return super().embed_documents(texts)
    def embed_query(self, text): return EmbeddingBatch([[1.]+[0.]*1023],12)


def use_semantic(repo, monkeypatch):
    repo.settings = replace(repo.settings, embedding_provider='ollama')
    provider = CountingProvider()
    monkeypatch.setattr('app.jobs.processing.build_embedding_provider', lambda _: provider)
    monkeypatch.setattr('app.jobs.processing.MAX_BATCHES_PER_DELIVERY', 1)
    return provider


def test_checkpoint_retry_atomic_promotion_usage_and_old_evidence(ingestion, monkeypatch):
    repo, service, principal, project, actor = ingestion
    old = register(ingestion, content=long_transcript(25)); assert run(repo, old)
    old_citation = service.ask(principal,project.id,'GET /health').citations[0]
    provider = use_semantic(repo, monkeypatch)
    service.embedding_provider = provider
    replacement = repo.command(principal.tenant_id,project.id,old.source.id,actor,'reprocess','checkpoint-reprocess')
    assert not run(repo,replacement)
    state = repo.get_job(principal.tenant_id,project.id,replacement.job.id)
    assert (state.stage,state.processed_segments,state.total_segments,state.attempt_count) == ('waiting_continuation',8,25,1)
    assert not repo.store.search(principal.tenant_id,project.id,'GET /health',[1.]+[0.]*1023,4,embedding_space=QWEN_SPACE)
    assert ChatRepository(repo.store).evidence(principal.tenant_id,project.id,actor,old_citation.segment_id).generation == 1
    provider.fail_once = True
    make_due(repo,replacement); assert not run(repo,replacement)
    assert repo.get_job(principal.tenant_id,project.id,replacement.job.id).processed_segments == 8
    finish(repo,replacement)
    done = repo.get_job(principal.tenant_id,project.id,replacement.job.id)
    assert done.attempt_count == 2 and done.delivery_count == 5 and done.processed_segments == 25
    assert all(provider.calls.count(text) == 1 for text in provider.calls[:8])
    assert provider.calls.count('Chunk 0. GET /health reports service availability.') == 1
    assert repo.get_source(principal.tenant_id,project.id,old.source.id).active_generation == 2
    assert ChatRepository(repo.store).evidence(principal.tenant_id,project.id,actor,old_citation.segment_id).generation == 1
    with repo.store._connect() as connection:
        scope = (principal.tenant_id,project.id,replacement.job.id)
        assert connection.execute('SELECT count(*) AS n FROM embedding_checkpoints WHERE tenant_id=%s AND project_id=%s AND job_id=%s',scope).fetchone()['n'] == 0
        usage = connection.execute('SELECT * FROM usage_events WHERE tenant_id=%s AND project_id=%s AND job_id=%s',scope).fetchone()
        assert usage['input_tokens'] == 25*12 and usage['segment_count'] == 25 and usage['billed_usd'] == 0
        duration = connection.execute('SELECT sum(duration_ms) AS n FROM processing_attempts WHERE tenant_id=%s AND project_id=%s AND job_id=%s',scope).fetchone()['n']
        assert usage['duration_ms'] == duration
    assert not run(repo,replacement)


def test_cancel_and_retry_resume_instead_of_recomputing(ingestion, monkeypatch):
    repo, _, principal, project, actor = ingestion
    provider = use_semantic(repo, monkeypatch)
    registered = register(ingestion, content=long_transcript(17)); assert not run(repo,registered)
    repo.command(principal.tenant_id,project.id,registered.source.id,actor,'cancel','checkpoint-cancel')
    assert not run(repo,registered) and len(provider.calls) == 8
    repo.command(principal.tenant_id,project.id,registered.source.id,actor,'retry','checkpoint-retry')
    finish(repo,registered)
    assert len(provider.calls) == 17 and len(set(provider.calls)) == 17


def test_mode_or_parser_drift_never_blends_checkpoints_and_reprocess_clears_only_staging(ingestion, monkeypatch):
    repo, _, principal, project, actor = ingestion
    provider = use_semantic(repo, monkeypatch)
    registered = register(ingestion, content=long_transcript(17)); assert not run(repo,registered)
    provider.model_digest = 'b'*64
    make_due(repo,registered); assert not run(repo,registered)
    assert repo.get_job(principal.tenant_id,project.id,registered.job.id).failure_code == 'processing_configuration_changed'
    provider.model_digest = FixtureSemanticProvider.model_digest
    repo.command(principal.tenant_id,project.id,registered.source.id,actor,'retry','restore-profile')
    original = chunk_transcript
    monkeypatch.setattr('app.jobs.processing.chunk_transcript', lambda content: [replace(chunk,text=chunk.text+' changed') for chunk in original(content)])
    assert not run(repo,registered)
    assert repo.get_job(principal.tenant_id,project.id,registered.job.id).failure_code == 'checkpoint_input_changed'
    assert len(provider.calls) == 8
    monkeypatch.setattr('app.jobs.processing.chunk_transcript', original)
    repo.settings = replace(repo.settings, embedding_provider='hash')
    from app.providers import DeterministicHashEmbeddingProvider
    monkeypatch.setattr('app.jobs.processing.build_embedding_provider', lambda _: DeterministicHashEmbeddingProvider())
    replacement = repo.command(principal.tenant_id,project.id,registered.source.id,actor,'reprocess','new-hash-generation')
    assert run(repo,replacement)
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM embedding_checkpoints WHERE tenant_id=%s AND project_id=%s', (principal.tenant_id,project.id)).fetchone()['n'] == 0
    assert repo.get_source(principal.tenant_id,project.id,registered.source.id).active_embedding_space != QWEN_SPACE


def test_checkpoint_fences_scope_lease_cancel_deletion_and_duplicate_batch(ingestion, monkeypatch):
    repo, _, principal, project, actor = ingestion
    use_semantic(repo,monkeypatch)
    registered = register(ingestion, content=long_transcript(17))
    claim = repo.claim_job(principal.tenant_id,project.id,registered.source.id,registered.job.id,1)
    chunks = chunk_transcript(long_transcript(17))
    store = TranscriptCheckpoints(repo)
    assert store.begin(claim,chunks) == 0
    segments = [EvidenceSegment(id=segment_id(registered.source.id,1,chunk,i),tenant_id=principal.tenant_id,project_id=project.id,
        source_id=registered.source.id,modality='transcript',start_ms=chunk.start_ms,end_ms=chunk.end_ms,text=chunk.text,
        embedding=[1.]+[0.]*1023,embedding_space=QWEN_SPACE,generation=1,processing_version=f'{PROCESSING_VERSION}:g1')
        for i,chunk in enumerate(chunks[:8])]
    provenance = [(chunk.cue_start,chunk.cue_end) for chunk in chunks[:8]]
    assert store.save(claim,0,segments,provenance,96)
    assert not store.save(claim,0,segments,provenance,96)
    assert store.begin({**claim,'tenant_id':'foreign'},chunks) is None
    assert store.begin({**claim,'project_id':uuid4()},chunks) is None
    with pytest.raises(SourceError): store.save(claim,8,[segments[0].model_copy(update={'source_id':uuid4()})],provenance[:1],12)
    with pytest.raises(SourceError): store.finish(claim)
    repo.command(principal.tenant_id,project.id,registered.source.id,actor,'cancel','fenced-cancel')
    assert not store.save(claim,8,segments,provenance,96) and not store.finish(claim)
    repo.command(principal.tenant_id,project.id,registered.source.id,actor,'retry','fenced-retry')
    new_claim = repo.claim_job(principal.tenant_id,project.id,registered.source.id,registered.job.id,1)
    assert new_claim['lease_token'] != claim['lease_token'] and store.begin(claim,chunks) is None
    assert store.begin(new_claim,chunks) == 8
    cleanup = repo.delete_source(principal.tenant_id,project.id,registered.source.id,actor)
    assert store.begin(new_claim,chunks) is None and not store.finish(new_claim)
    assert cleanup_once(repo) == 1 and repo.get_cleanup(principal.tenant_id,project.id,cleanup.id,actor).status == 'completed'
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM embedding_checkpoints WHERE tenant_id=%s AND project_id=%s',(principal.tenant_id,project.id)).fetchone()['n'] == 0


def test_continuation_outbox_fence_survives_racing_publish_ack(ingestion, monkeypatch):
    repo, _, principal, project, _ = ingestion
    use_semantic(repo,monkeypatch)
    registered = register(ingestion, content=long_transcript(17))
    # A publisher can race the worker's checkpoint continuation on the same outbox.
    assert dispatch_once(repo, lambda _: run(repo,registered)) == 1
    with repo.store._connect() as connection:
        row = connection.execute('SELECT * FROM outbox_events WHERE tenant_id=%s AND project_id=%s AND job_id=%s', (principal.tenant_id,project.id,registered.job.id)).fetchone()
        assert row['sent_at'] is None and row['lease_token'] is None
    make_due(repo,registered)
    assert dispatch_once(repo, lambda _: run(repo,registered)) == 1
    assert repo.get_job(principal.tenant_id,project.id,registered.job.id).attempt_count == 1


def test_project_deletion_cascades_checkpoint_vectors_and_fences_worker(ingestion, monkeypatch):
    repo, service, principal, project, actor = ingestion
    use_semantic(repo,monkeypatch)
    registered = register(ingestion,content=long_transcript(17)); assert not run(repo,registered)
    cleanup = service.delete_project(principal,project.id)
    assert not run(repo,registered) and cleanup_once(repo) == 1 and not repo.artifacts.objects
    assert repo.get_cleanup(principal.tenant_id,project.id,cleanup,actor).status == 'completed'
    with pytest.raises(ProjectNotFoundError): repo.get_job(principal.tenant_id,project.id,registered.job.id)
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM embedding_checkpoints WHERE tenant_id=%s AND project_id=%s',(principal.tenant_id,project.id)).fetchone()['n'] == 0
