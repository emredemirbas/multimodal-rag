"""Published provenance is version-pinned; retirement is not physical deletion."""
from uuid import UUID, uuid4

import pytest
from psycopg.types.json import Jsonb

from app.chat.contracts import ConversationCreate, MessageRequest
from app.chat.repository import ChatRepository
from app.jobs.dispatch import cleanup_once
from app.models import AuthenticatedPrincipal, ProjectCreate, TranscriptIngestRequest
from app.sources.media import retire_unusable_audio
from app.sources.transcript import TranscriptRepository
from app.store import ProjectNotFoundError
from test_checkpoints_integration import make_due
from test_ingestion_integration import ingestion, register, run
from test_media_integration import cleanup_all, media, process, register_audio
from test_postgres_integration import isolated_postgres_url

pytestmark = pytest.mark.integration


def ready_audio(ingestion, media):
    result = register_audio(ingestion, media, frames=16_000)
    repo, _, principal, project, _ = ingestion
    assert process(repo, result)
    source = repo.get_source(principal.tenant_id, project.id, result.source.id)
    assert run(repo, result.model_copy(update={'job': source.job}))
    return result


def test_unfinished_audio_has_no_published_asr_origin_or_evidence(ingestion, media):
    repo, _, principal, project, actor = ingestion
    result = register_audio(ingestion, media)  # Two windows.
    source = repo.get_source(principal.tenant_id, project.id, result.source.id)
    assert source.asr_origin is None and source.audio_retention.status == 'temporary'
    assert source.audio_retention.cleanup_id is None and source.audio_retention.deleted_at is None
    assert not process(repo, result)
    partial = repo.get_source(principal.tenant_id, project.id, result.source.id)
    assert partial.asr_origin is None and partial.audio_retention == source.audio_retention
    page = TranscriptRepository(repo.store).read(principal.tenant_id, project.id, actor, source.id)
    assert page.asr_origin is None and page.generation is None and not page.items
    make_due(repo, result)
    assert process(repo, result)
    adopted = repo.get_source(principal.tenant_id, project.id, source.id)
    assert adopted.asr_origin.job_id == result.job.id and adopted.audio_retention.status == 'cleanup_pending'
    assert adopted.active_generation is None  # ASR completion is not index publication.
    page = TranscriptRepository(repo.store).read(principal.tenant_id, project.id, actor, source.id)
    assert page.asr_origin is None and not page.items


def test_origin_survives_reindex_metadata_drift_history_and_raw_deletion_without_io(ingestion, media):
    repo, service, principal, project, actor = ingestion
    result = ready_audio(ingestion, media)
    chat = ChatRepository(repo.store)
    browse = TranscriptRepository(repo.store)
    source = repo.get_source(principal.tenant_id, project.id, result.source.id)
    origin = source.asr_origin
    assert origin.machine_generated and origin.job_id == result.job.id and origin.generation == 1
    assert origin.provider == 'faster-whisper-local' and origin.model == 'whisper-base'
    assert origin.requested_language == 'en' and origin.completed_at is not None
    page = browse.read(principal.tenant_id, project.id, actor, source.id)
    assert page.asr_origin == origin and all(item.asr_origin == origin for item in page.items)
    body = MessageRequest(question='What is GET /health?', source_ids=[source.id], idempotency_key='asr-inspection-question')
    response, retrieval = service.prepare_answer(principal, project.id, body.question, body.source_ids)
    assert response.citations and all(item.asr_origin == origin for item in response.citations)
    conversation = chat.create(principal.tenant_id, project.id, actor, ConversationCreate(idempotency_key='asr-inspection-chat'))
    turn = chat.record(principal.tenant_id, project.id, actor, conversation.id, body, response, retrieval)
    assert turn.response.citations[0].asr_origin == origin
    citation = turn.response.citations[0]
    reindex = repo.command(principal.tenant_id, project.id, source.id, actor, 'reprocess', 'asr-inspection-reindex')
    assert run(repo, reindex) and len(media[1].calls) == 1
    with repo.store._connect() as connection:
        connection.execute('UPDATE sources SET metadata=%s WHERE tenant_id=%s AND project_id=%s AND id=%s',
                           (Jsonb({'machine_generated': False, 'asr_job_id': str(uuid4()), 'asr_profile': 'not-the-real-profile'}),
                            principal.tenant_id, project.id, source.id))
    cleanup_all(repo)
    # These reads must not call either the model or storage, even after raw removal.
    repo.artifacts.fail_get = True
    media[1].after_call = lambda: pytest.fail('Inspection must not transcribe again')
    current = repo.get_source(principal.tenant_id, project.id, source.id)
    assert current.asr_origin == origin and current.active_generation == 2
    assert current.audio_retention.status == 'deleted' and current.audio_retention.deleted_at is not None
    assert repo.list_sources(principal.tenant_id, project.id).items == [current]
    assert browse.read(principal.tenant_id, project.id, actor, source.id, generation=1).items == page.items
    newest = browse.read(principal.tenant_id, project.id, actor, source.id)
    assert newest.generation == 2 and newest.asr_origin == origin  # ASR generation is still 1.
    assert chat.evidence(principal.tenant_id, project.id, actor, citation.segment_id).asr_origin == origin
    assert chat.history(principal.tenant_id, project.id, actor, conversation.id).turns == [turn]
    assert chat.replay(principal.tenant_id, project.id, actor, conversation.id, body) == turn
    assert len(media[1].calls) == 1
    public = current.model_dump_json()
    for forbidden in ['input_sha256', 'input_frames', 'object_key', 'result_sha256', 'network_policy', '/audio/', 'not-the-real-profile']:
        # metadata is a legacy untrusted field; only typed provenance is authoritative.
        if forbidden == 'not-the-real-profile':
            assert forbidden not in origin.model_dump_json()
        else:
            assert forbidden not in public


def test_uploaded_and_legacy_subtitles_do_not_inherit_forged_machine_origin(ingestion, media):
    repo, service, principal, project, actor = ingestion
    audio = ready_audio(ingestion, media)
    ordinary = register(ingestion)
    assert run(repo, ordinary)
    legacy = service.ingest_transcript(principal, project.id, TranscriptIngestRequest(
        filename='legacy.vtt', content='WEBVTT\n\n00:01.000 --> 00:05.000\nGET /health example.',
        authorization_mode='owner_upload', idempotency_key='legacy-inspection')).source
    chat = ChatRepository(repo.store)
    for source in [ordinary.source, legacy]:
        with repo.store._connect() as connection:
            connection.execute('UPDATE sources SET metadata=%s WHERE tenant_id=%s AND project_id=%s AND id=%s',
                               (Jsonb({'machine_generated': True, 'asr_job_id': str(audio.job.id)}), principal.tenant_id, project.id, source.id))
        managed = repo.get_source(principal.tenant_id, project.id, source.id)
        assert managed.asr_origin is None and managed.audio_retention is None
        page = TranscriptRepository(repo.store).read(principal.tenant_id, project.id, actor, source.id)
        assert page.asr_origin is None and all(item.asr_origin is None for item in page.items)
        assert chat.evidence(principal.tenant_id, project.id, actor, page.items[0].segment_id).asr_origin is None
        assert all(item.asr_origin is None for item in service.ask(principal, project.id, 'GET /health', [source.id]).citations)


def test_retention_expiry_failure_and_confirmation_are_separate_observable_states(ingestion, media):
    repo, _, principal, project, actor = ingestion
    result = register_audio(ingestion, media, frames=16_000)
    read = lambda: repo.get_source(principal.tenant_id, project.id, result.source.id).audio_retention
    with repo.store._connect() as connection:
        connection.execute("UPDATE audio_inputs SET expires_at=now()-interval '1 second' WHERE tenant_id=%s AND project_id=%s AND job_id=%s",
                           (principal.tenant_id, project.id, result.job.id))
    assert read().status == 'expired' and read().cleanup_id is None and repo.artifacts.objects
    assert retire_unusable_audio(repo) == 1
    assert read().status == 'cleanup_pending' and read().deleted_at is None
    cleanup = read().cleanup_id
    with repo.store._connect() as connection:
        connection.execute('UPDATE artifact_cleanup SET attempt_count=5 WHERE tenant_id=%s AND project_id=%s AND id=%s',
                           (principal.tenant_id, project.id, cleanup))
    repo.artifacts.fail_delete = True
    assert cleanup_once(repo) == 0
    assert read().status == 'cleanup_failed' and read().deleted_at is None and repo.artifacts.objects
    assert repo.get_cleanup(principal.tenant_id, project.id, cleanup, actor).status == 'failed'
    with repo.store._connect() as connection:
        connection.execute("UPDATE artifact_cleanup SET status='pending',attempt_count=0,available_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s",
                           (principal.tenant_id, project.id, cleanup))
    assert read().status == 'cleanup_pending'
    repo.artifacts.fail_delete = False
    assert cleanup_once(repo) == 1
    assert read().status == 'deleted' and read().deleted_at is not None and not repo.artifacts.objects


def test_machine_evidence_inspection_scope_archive_revocation_and_deletion(ingestion, media):
    repo, service, principal, project, actor = ingestion
    result = ready_audio(ingestion, media)
    browse = TranscriptRepository(repo.store)
    chat = ChatRepository(repo.store)
    original = browse.read(principal.tenant_id, project.id, actor, result.source.id)
    segment = original.items[0].segment_id
    other_project = service.create_project(principal, ProjectCreate(title='Not this audio'))
    foreign = AuthenticatedPrincipal(provider='test', subject='media-reader', tenant_id='media-other')
    foreign_actor = repo.store.bootstrap_principal(foreign)
    for tenant, scope, user in [(principal.tenant_id, other_project.id, actor), (foreign.tenant_id, project.id, foreign_actor)]:
        for read in [lambda: repo.get_source(tenant, scope, result.source.id),
                     lambda: browse.read(tenant, scope, user, result.source.id),
                     lambda: chat.evidence(tenant, scope, user, segment)]:
            with pytest.raises(ProjectNotFoundError): read()
    service.archive_project(principal, project.id)
    assert browse.read(principal.tenant_id, project.id, actor, result.source.id) == original
    with repo.store._connect() as connection:
        connection.execute('DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s', (principal.tenant_id, actor))
    with pytest.raises(ProjectNotFoundError): browse.read(principal.tenant_id, project.id, actor, result.source.id)
    with pytest.raises(ProjectNotFoundError): chat.evidence(principal.tenant_id, project.id, actor, segment)
    repo.store.bootstrap_principal(principal)
    repo.delete_source(principal.tenant_id, project.id, result.source.id, actor)
    with pytest.raises(ProjectNotFoundError): browse.read(principal.tenant_id, project.id, actor, result.source.id)
    with pytest.raises(ProjectNotFoundError): chat.evidence(principal.tenant_id, project.id, actor, segment)
    assert not repo.list_sources(principal.tenant_id, project.id).items
    service.delete_project(principal, project.id)
    with pytest.raises(ProjectNotFoundError): repo.get_source(principal.tenant_id, project.id, result.source.id)


@pytest.mark.anyio
async def test_http_machine_origin_and_existing_authorized_cleanup_retry(ingestion, media):
    from httpx import ASGITransport, AsyncClient
    from app.config import Settings
    from app.main import create_app
    from app.sources.media import MediaRepository
    from app.models import AuthorizationMode
    from conftest import MappingAuthenticator, TEST_TOKENS, auth_headers
    from test_wav import wav_bytes
    repo, service, _, _, _ = ingestion
    principal = TEST_TOKENS['tenant-a-token-long-enough']
    project = service.create_project(principal, ProjectCreate(title='HTTP media inspection'))
    actor = repo.store.bootstrap_principal(principal)
    result = MediaRepository(repo).register(principal.tenant_id, project.id, actor, filename='owned.wav', content=wav_bytes(16_000),
        rights=AuthorizationMode.OWNER_UPLOAD, language='en', idempotency_key='http-private-media')
    assert process(repo, result)
    source = repo.get_source(principal.tenant_id, project.id, result.source.id)
    assert run(repo, result.model_copy(update={'job': source.job}))
    segment = service.ask(principal, project.id, 'GET /health').citations[0].segment_id
    cleanup = source.audio_retention.cleanup_id
    with repo.store._connect() as connection:
        connection.execute("UPDATE artifact_cleanup SET status='failed',attempt_count=6 WHERE tenant_id=%s AND project_id=%s AND id=%s",
                           (principal.tenant_id, project.id, cleanup))
    app = create_app(settings=Settings(environment='test', development_auth_token='test-token-long-enough', auto_migrate=False),
                     store=repo.store, authenticator=MappingAuthenticator(), artifacts=repo.artifacts)
    async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as client:
        base = f'/api/v1/projects/{project.id}'
        paths = [f'/sources/{source.id}', '/sources', f'/sources/{source.id}/transcript', f'/evidence/{segment}']
        for path in paths:
            assert (await client.get(base + path)).status_code == 401
            assert (await client.get(base + path, headers=auth_headers('tenant-b'))).status_code == 404
            response = await client.get(base + path, headers=auth_headers())
            assert response.status_code == 200
            payload = response.json()['items'][0] if path == '/sources' else response.json()
            assert payload['asr_origin']['job_id'] == str(result.job.id)
            assert payload['asr_origin']['machine_generated'] is True
            assert 'input_sha256' not in response.text and 'object_key' not in response.text
        assert (await client.get(base + paths[0], headers=auth_headers())).json()['audio_retention']['status'] == 'cleanup_failed'
        retry = base + f'/cleanup/{cleanup}/retry'
        assert (await client.post(retry)).status_code == 401
        assert (await client.post(retry, headers=auth_headers('tenant-b'))).status_code == 404
        # Knowing the ticket does not grant another member its actor-owned command.
        other = AuthenticatedPrincipal(provider='test', subject='other-member', tenant_id=principal.tenant_id)
        other_actor = repo.store.bootstrap_principal(other)
        with pytest.raises(ProjectNotFoundError): repo.get_cleanup(principal.tenant_id, project.id, cleanup, other_actor)
        assert (await client.post(retry, headers=auth_headers())).json()['status'] == 'pending'
        assert (await client.get(base + paths[0], headers=auth_headers())).json()['audio_retention']['status'] == 'cleanup_pending'
        cleanup_all(repo)
        final = (await client.get(base + paths[0], headers=auth_headers())).json()['audio_retention']
        assert final['status'] == 'deleted' and final['deleted_at'] is not None
        assert UUID(final['cleanup_id']) == cleanup
