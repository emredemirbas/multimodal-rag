from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
from uuid import uuid4

import pytest

from app.config import Settings
from app.jobs.dispatch import cleanup_once, dispatch_once
from app.jobs.processing import process_transcript
from app.models import AuthenticatedPrincipal, AuthorizationMode, ProjectCreate
from app.postgres import PostgresStore
from app.providers import DeterministicHashEmbeddingProvider, EvidenceExtractiveAnswerProvider
from app.service import TutorialService
from app.sources.contracts import SourceError
from app.sources.repository import SourceRepository
from app.store import ProjectNotFoundError
from test_postgres_integration import isolated_postgres_url

TRANSCRIPT = b'WEBVTT\n\n00:00.000 --> 00:05.000\nFastAPI uses create_app() and GET /health.\n'


class MemoryArtifacts:
    def __init__(self):
        self.objects = {}
        self.fail_put = False
        self.fail_get = False
        self.fail_delete = False
        self.after_put = None

    def put(self, key, content):
        if self.fail_put:
            raise SourceError('storage_unavailable', 'Storage temporarily unavailable.', 503, transient=True)
        self.objects[key] = content
        if self.after_put:
            self.after_put()

    def get(self, key, limit):
        if self.fail_get:
            raise SourceError('storage_unavailable', 'Storage temporarily unavailable.', 503, transient=True)
        return self.objects[key]

    def delete_prefix(self, prefix):
        if self.fail_delete:
            raise SourceError('storage_unavailable', 'Storage temporarily unavailable.', 503, transient=True)
        self.objects = {key: value for key, value in self.objects.items() if not key.startswith(prefix)}


@pytest.fixture
def ingestion(isolated_postgres_url):
    store = PostgresStore(isolated_postgres_url)
    store.run_migrations()
    principal = AuthenticatedPrincipal(provider='test', subject='test-user', tenant_id='ingestion-test')
    service = TutorialService(store, DeterministicHashEmbeddingProvider(), EvidenceExtractiveAnswerProvider())
    project = service.create_project(principal, ProjectCreate(title='Ingestion'))
    actor = store.bootstrap_principal(principal)
    artifacts = MemoryArtifacts()
    settings = Settings(environment='test', development_auth_token='test-development-token', auto_migrate=False)
    repository = SourceRepository(store, artifacts, settings)
    return repository, service, principal, project, actor


def register(ingestion, *, key='upload-key-1', content=TRANSCRIPT):
    repository, _, principal, project, actor = ingestion
    return repository.register(principal.tenant_id, project.id, actor, filename='tutorial.vtt', content=content,
                               rights=AuthorizationMode.OWNER_UPLOAD, idempotency_key=key)


def run(repository, result):
    return process_transcript(repository, result.source.tenant_id, result.source.project_id, result.source.id, result.job.id, result.job.generation)


@pytest.mark.integration
def test_registration_concurrency_outbox_broker_outage_and_duplicate_processing(ingestion):
    repository, service, principal, project, actor = ingestion
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: register(ingestion), range(2)))
    result = results[0]
    assert results[0].source.id == results[1].source.id
    assert results[0].job.id == results[1].job.id
    assert sorted(item.deduplicated for item in results) == [False, True]
    assert len(repository.artifacts.objects) == 1
    with pytest.raises(SourceError, match='different input'):
        register(ingestion, content=TRANSCRIPT + b'\nextra')
    assert dispatch_once(repository, lambda _: (_ for _ in ()).throw(ConnectionError('secret-broker-password'))) == 0
    with repository.store._connect() as connection:
        row = connection.execute('SELECT sent_at,publish_attempts FROM outbox_events WHERE tenant_id=%s AND project_id=%s', (principal.tenant_id, project.id)).fetchone()
        assert row['sent_at'] is None and row['publish_attempts'] == 1
    assert run(repository, result)
    assert not run(repository, result)
    assert repository.get_job(principal.tenant_id, project.id, result.job.id).status == 'succeeded'
    answer = service.ask(principal, project.id, 'What is GET /health?')
    assert not answer.abstained and answer.citations[0].source_id == result.source.id
    with repository.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS count FROM content_segments WHERE tenant_id=%s AND project_id=%s', (principal.tenant_id, project.id)).fetchone()['count'] == 1
        assert connection.execute('SELECT count(*) AS count FROM usage_events WHERE tenant_id=%s AND project_id=%s', (principal.tenant_id, project.id)).fetchone()['count'] == 1


@pytest.mark.integration
def test_rollback_after_object_put_is_cleaned_by_durable_reservation(ingestion):
    repository, _, principal, project, _ = ingestion
    def fail_after_put():
        raise SourceError('registration_unavailable', 'Registration interrupted.', 503)
    repository.artifacts.after_put = fail_after_put
    with pytest.raises(SourceError):
        register(ingestion)
    assert len(repository.artifacts.objects) == 1
    assert not repository.list_sources(principal.tenant_id, project.id).items
    assert cleanup_once(repository) == 1
    assert not repository.artifacts.objects


@pytest.mark.integration
def test_cancel_retry_reprocess_keeps_prior_provenance_and_fences_stale_worker(ingestion):
    repository, service, principal, project, actor = ingestion
    result = register(ingestion)
    tenant, source, job = principal.tenant_id, result.source.id, result.job.id
    claim = repository.claim_job(tenant, project.id, source, job, 1)
    cancelled = repository.command(tenant, project.id, source, actor, 'cancel', 'cancel-key-1')
    assert cancelled.job.status == 'cancelled'
    assert not repository.stage(claim, 'indexing', 90)
    retry = repository.command(tenant, project.id, source, actor, 'retry', 'retry-key-1')
    assert repository.command(tenant, project.id, source, actor, 'retry', 'retry-key-1').deduplicated
    assert run(repository, retry)
    old_citation = service.ask(principal, project.id, 'What is GET /health?').citations[0].segment_id
    reprocess = repository.command(tenant, project.id, source, actor, 'reprocess', 'reprocess-key-1')
    assert reprocess.job.generation == 2
    assert repository.command(tenant, project.id, source, actor, 'reprocess', 'reprocess-key-1').job.id == reprocess.job.id
    repository.artifacts.fail_get = True
    assert not run(repository, reprocess)
    assert service.ask(principal, project.id, 'What is GET /health?').citations[0].segment_id == old_citation
    repository.artifacts.fail_get = False
    with repository.store._connect() as connection:
        connection.execute('UPDATE processing_jobs SET available_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s', (tenant, project.id, reprocess.job.id))
    assert run(repository, reprocess)
    assert service.ask(principal, project.id, 'What is GET /health?').citations[0].segment_id != old_citation
    with repository.store._connect() as connection:
        assert connection.execute('SELECT id FROM content_segments WHERE tenant_id=%s AND project_id=%s AND id=%s', (tenant, project.id, old_citation)).fetchone()


@pytest.mark.integration
def test_expired_lease_bounded_recovery_and_deletion_race(ingestion):
    repository, service, principal, project, actor = ingestion
    result = register(ingestion)
    tenant = principal.tenant_id
    claim = repository.claim_job(tenant, project.id, result.source.id, result.job.id, 1)
    with repository.store._connect() as connection:
        connection.execute("UPDATE processing_jobs SET lease_expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND id=%s", (tenant, project.id, result.job.id))
    assert repository.recover_leases() == 1
    assert not repository.stage(claim, 'indexing', 90)
    with repository.store._connect() as connection:
        connection.execute('UPDATE processing_jobs SET available_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s', (tenant, project.id, result.job.id))
    second_claim = repository.claim_job(tenant, project.id, result.source.id, result.job.id, 1)
    ticket = repository.delete_source(tenant, project.id, result.source.id, actor)
    assert not repository.stage(second_claim, 'indexing', 90)
    assert not run(repository, result)
    repository.artifacts.fail_delete = True
    assert cleanup_once(repository) == 0
    assert repository.get_cleanup(tenant, project.id, ticket.id, actor).failure_code == 'storage_cleanup_unavailable'
    repository.artifacts.fail_delete = False
    with repository.store._connect() as connection:
        connection.execute('UPDATE artifact_cleanup SET available_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s', (tenant, project.id, ticket.id))
    assert cleanup_once(repository) == 1
    assert not repository.artifacts.objects
    project_ticket = service.delete_project(principal, project.id)
    assert repository.get_cleanup(tenant, project.id, project_ticket, actor).status == 'pending'
    assert cleanup_once(repository) == 1
    assert repository.get_cleanup(tenant, project.id, project_ticket, actor).status == 'completed'


@pytest.mark.integration
def test_source_job_artifacts_commands_and_cleanup_are_project_and_tenant_scoped(ingestion):
    repository, service, principal, project, actor = ingestion
    result = register(ingestion)
    other_project = service.create_project(principal, ProjectCreate(title='Other project'))
    foreign = AuthenticatedPrincipal(provider='test', subject='foreign-user', tenant_id='foreign-tenant')
    foreign_actor = repository.store.bootstrap_principal(foreign)
    for tenant, project_id, user in [(principal.tenant_id, other_project.id, actor), (foreign.tenant_id, project.id, foreign_actor)]:
        with pytest.raises(ProjectNotFoundError):
            repository.get_source(tenant, project_id, result.source.id)
        with pytest.raises(ProjectNotFoundError):
            repository.get_job(tenant, project_id, result.job.id)
        with pytest.raises(ProjectNotFoundError):
            repository.command(tenant, project_id, result.source.id, user, 'cancel', 'cross-scope-command')
        with pytest.raises(ProjectNotFoundError):
            repository.delete_source(tenant, project_id, result.source.id, user)
        assert repository.claim_job(tenant, project_id, result.source.id, result.job.id, 1) is None
    ticket = repository.delete_source(principal.tenant_id, project.id, result.source.id, actor)
    with pytest.raises(ProjectNotFoundError):
        repository.get_cleanup(foreign.tenant_id, project.id, ticket.id, foreign_actor)


@pytest.mark.integration
@pytest.mark.anyio
async def test_upload_api_bounds_validation_isolation_and_safe_errors(ingestion):
    from httpx import ASGITransport, AsyncClient
    from app.auth import TrustedProxyAuthenticator
    from app.main import create_app
    repository, _, principal, project, _ = ingestion
    app = create_app(settings=repository.settings, store=repository.store, artifacts=repository.artifacts,
                     authenticator=TrustedProxyAuthenticator(shared_secret='integration-proxy-secret'))
    headers = {'X-Trusted-Proxy-Secret': 'integration-proxy-secret', 'X-Authenticated-Subject': principal.subject,
               'X-Authenticated-Tenant': principal.tenant_id}
    path = f'/api/v1/projects/{project.id}/sources/uploads'
    data = {'authorization_mode': 'owner_upload', 'idempotency_key': 'http-upload-1'}
    async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.post(path, data=data, files={'file': ('tutorial.vtt', TRANSCRIPT, 'text/vtt')})).status_code == 401
        assert (await client.post(path, headers=headers, data={'idempotency_key': 'http-upload-1'}, files={'file': ('tutorial.vtt', TRANSCRIPT, 'text/vtt')})).status_code == 422
        assert (await client.post(path, headers=headers, data=data, files={'file': ('tutorial.vtt', b'\xff', 'text/vtt')})).json()['code'] == 'invalid_encoding'
        assert (await client.post(path, headers=headers, data=data, files={'file': ('tutorial.vtt', b'x' * 2_020_000, 'text/vtt')})).status_code == 413
        # Private ASR staging must not silently enable product binary uploads.
        from test_wav import wav_bytes
        for content_type in ['audio/wav', 'application/octet-stream']:
            response = await client.post(path, headers=headers, data=data, files={'file': ('owned.wav', wav_bytes(), content_type)})
            assert response.status_code == 422
        with repository.store._connect() as connection:
            assert connection.execute('SELECT count(*) AS n FROM asr_runs').fetchone()['n'] == 0
        foreign = {**headers, 'X-Authenticated-Tenant': 'http-foreign'}
        assert (await client.post(path, headers=foreign, data=data, files={'file': ('tutorial.vtt', TRANSCRIPT, 'text/vtt')})).status_code == 404
        response = await client.post(path, headers=headers, data=data, files={'file': ('tutorial.vtt', TRANSCRIPT, 'text/vtt')})
        assert response.status_code == 202
        source_id = response.json()['source']['id']
        assert len((await client.get(f'/api/v1/projects/{project.id}/sources', headers=headers)).json()['items']) == 1
        assert (await client.get(f'/api/v1/projects/{project.id}/sources/{source_id}', headers=foreign)).status_code == 404


@pytest.mark.integration
def test_deterministic_failure_revoked_worker_and_exhausted_retry(ingestion):
    repository, _, principal, project, actor = ingestion
    invalid = register(ingestion, content=b'UTF-8 text but no subtitle cues')
    assert not run(repository, invalid)
    assert repository.get_job(principal.tenant_id, project.id, invalid.job.id).failure_code == 'invalid_transcript'
    result = register(ingestion, key='transient-input')
    repository.artifacts.fail_get = True
    for _ in range(3):
        assert not run(repository, result)
        with repository.store._connect() as connection:
            connection.execute('UPDATE processing_jobs SET available_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s', (principal.tenant_id, project.id, result.job.id))
    final = repository.get_job(principal.tenant_id, project.id, result.job.id)
    assert final.status == 'failed' and final.attempt_count == final.max_attempts == 3
    revoked = register(ingestion, key='revoked-input')
    with repository.store._connect() as connection:
        connection.execute('DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s', (principal.tenant_id, actor))
    assert not run(repository, revoked)
    assert repository.get_job(principal.tenant_id, project.id, revoked.job.id).failure_code == 'authorization_revoked'


@pytest.mark.integration
def test_metadata_registration_processing_and_no_transcript_index(ingestion, monkeypatch):
    from app.sources.adapters import YouTubeMetadataProvider
    repository, service, principal, project, actor = ingestion
    with pytest.raises(SourceError) as error:
        repository.register_metadata(principal.tenant_id, project.id, actor, url='https://youtu.be/abcdefghijk', rights=AuthorizationMode.OWNER_UPLOAD, idempotency_key='metadata-input')
    assert error.value.code == 'provider_not_configured'
    repository.settings = replace(repository.settings, youtube_api_key='fixture-only')
    result = repository.register_metadata(principal.tenant_id, project.id, actor, url='https://youtu.be/abcdefghijk', rights=AuthorizationMode.OWNER_UPLOAD, idempotency_key='metadata-input')
    monkeypatch.setattr(YouTubeMetadataProvider, '_fetch', lambda *_: {'items': [{'id': 'abcdefghijk', 'snippet': {'title': 'Synthetic metadata'}}]})
    assert run(repository, result)
    source = repository.get_source(principal.tenant_id, project.id, result.source.id)
    assert source.status == 'metadata_ready' and source.active_generation is None and source.segment_count == 0
    assert source.metadata['needs_authorized_transcript']
    assert service.ask(principal, project.id, 'What is GET /health?').abstained


@pytest.mark.integration
def test_real_minio_put_integrity_and_complete_deletion(ingestion):
    import os
    from app.artifacts.storage import S3ArtifactStore
    password = os.getenv('MINIO_ROOT_PASSWORD')
    if not password:
        pytest.skip('MINIO_ROOT_PASSWORD is not configured')
    repository, service, principal, project, actor = ingestion
    settings = replace(repository.settings, s3_endpoint=f"http://127.0.0.1:{os.getenv('MINIO_API_PORT', '9000')}",
                       s3_access_key=os.getenv('MINIO_ROOT_USER', 'tutorial'), s3_secret_key=password)
    artifacts = S3ArtifactStore(settings)
    repository.artifacts = artifacts
    try:
        result = register(ingestion)
        assert run(repository, result)
        with repository.store._connect() as connection:
            key = connection.execute('SELECT object_key FROM source_artifacts WHERE tenant_id=%s AND project_id=%s AND source_id=%s', (principal.tenant_id, project.id, result.source.id)).fetchone()['object_key']
        assert hashlib.sha256(artifacts.get(key, 2_000_000)).hexdigest() == hashlib.sha256(TRANSCRIPT).hexdigest()
        ticket = service.delete_project(principal, project.id)
        for _ in range(5):
            cleanup_once(repository)
        assert repository.get_cleanup(principal.tenant_id, project.id, ticket, actor).status == 'completed'
        assert not artifacts.client.list_objects_v2(Bucket=artifacts.bucket, Prefix=f'{principal.tenant_id}/{project.id}/').get('Contents')
    finally:
        artifacts.delete_prefix(f'{principal.tenant_id}/{project.id}/')
