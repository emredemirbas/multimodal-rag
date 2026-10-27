"""Real DB evidence publication; embeddings/native input are explicit fixtures."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth import DevelopmentAuthenticator
from app.chat.contracts import ConversationCreate, MessageRequest
from app.chat.repository import ChatRepository
from app.embedding_profiles import HASH_SPACE, QWEN_SPACE
from app.jobs.dispatch import cleanup_once
from app.jobs.visual_indexing import index_visual
from app.main import create_app
from app.models import AuthenticatedPrincipal, ProjectCreate
from app.providers import DeterministicHashEmbeddingProvider, EmbeddingBatch
from app.sources.contracts import SourceError
from app.store import ProjectNotFoundError
from app.vision.gallery import VisualGalleryRepository
from app.vision.index import VisualIndexRepository
from app.vision.local import VisualResult
from app.vision.media import FrameEvidence, VideoInfo, encode_png
from test_checkpoints_integration import make_due
from test_embedding_spaces_integration import FixtureSemanticProvider
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url
from test_visual_gallery_integration import complete, prepared, deliver
from test_visual_service import result

pytestmark = pytest.mark.integration


def queue_index(ingestion, publication=None, key='index-ocr-fixture'):
    repo, _, principal, project, actor = ingestion
    if publication is None: _, publication = complete(ingestion)
    return VisualIndexRepository(repo).enqueue(principal.tenant_id, project.id, publication.source.id, publication.job.id, actor, key)


def run(repo, item):
    return index_visual(repo, item.source.tenant_id, item.source.project_id, item.source.id, item.job.id, item.job.generation)


def long_gallery(ingestion, text=None, count=6):
    baseline = result()
    frames = tuple(FrameEvidence(sample_target_ms=i*5000, timestamp_ms=i*5000, width=16, height=16,
        image=encode_png(16,16,bytes([i])*256), text=(f'GET /health frame {i}. '+('x'*(15979-len(str(i))))) if text is None else text)
        for i in range(count))
    assert all(len(frame.text) <= 16000 for frame in frames)
    snapshot = VisualResult(baseline.input_sha256,
        VideoInfo(duration_ms=count*5000,width=1920,height=1080,fps_numerator=25,fps_denominator=1),baseline.identity,count,frames)
    original = prepared(ingestion, snapshot)
    repo, _, principal, project, actor = ingestion
    publication = VisualGalleryRepository(repo).enqueue(principal.tenant_id,project.id,original.source.id,original.job.id,actor,'retain-index-fixture')
    for _ in range(count):
        make_due(repo,publication); deliver(repo,publication)
    assert repo.get_job(principal.tenant_id,project.id,publication.job.id).status == 'succeeded'
    return original, publication


def active_claim(repo, item):
    return repo.claim_job(item.source.tenant_id,item.source.project_id,item.source.id,item.job.id,item.job.generation,job_types=('visual_index',))


def test_hash_index_retrieval_citations_history_old_generations_and_complete_deletion(ingestion):
    repo, service, principal, project, actor = ingestion
    original, publication = complete(ingestion)
    item = queue_index(ingestion, publication)
    assert item.job.generation == 3
    with repo.store._connect() as connection:
        assert connection.execute('SELECT target_embedding_space FROM processing_jobs WHERE id=%s',(item.job.id,)).fetchone()['target_embedding_space'] == HASH_SPACE
    assert not VisualGalleryRepository(repo).gallery(principal.tenant_id,project.id,item.source.id,actor).searchable
    assert run(repo,item) and not run(repo,item)
    response, attribution = service.prepare_answer(principal,project.id,'user_id', [item.source.id])
    assert not response.abstained and 'Unreviewed frame OCR' in response.answer
    citation = response.citations[0]
    assert citation.modality == 'frame' and citation.start_ms == citation.end_ms
    assert citation.visual_origin.job_id == original.job.id and citation.visual_origin.generation == 1
    assert citation.asr_origin is None and citation.frame_id
    chat = ChatRepository(repo.store)
    evidence = chat.evidence(principal.tenant_id,project.id,actor,citation.segment_id)
    assert evidence.visual_origin == citation.visual_origin and evidence.frame_id == citation.frame_id
    assert evidence.text == result().frames[0 if evidence.start_ms == 0 else 1].text
    convo = chat.create(principal.tenant_id,project.id,actor,ConversationCreate(idempotency_key='visual-conversation'))
    body = MessageRequest(question='user_id',idempotency_key='visual-message')
    turn = chat.record(principal.tenant_id,project.id,actor,convo.id,body,response,attribution)
    before = chat.history(principal.tenant_id,project.id,actor,convo.id)
    with repo.store._connect() as connection:
        connection.execute("UPDATE sources SET metadata='{}'::jsonb WHERE tenant_id=%s AND project_id=%s AND id=%s",(principal.tenant_id,project.id,item.source.id))
        assert connection.execute('SELECT count(*) AS n FROM visual_index_chunks').fetchone()['n'] == 0
        usage = connection.execute('SELECT * FROM usage_events WHERE job_id=%s',(item.job.id,)).fetchone()
        assert usage['segment_count'] == 2 and usage['input_tokens'] == 0 and usage['billed_usd'] == 0
    again = queue_index(ingestion,publication,'second-index-generation')
    assert run(repo,again) and again.job.generation == 4
    assert chat.evidence(principal.tenant_id,project.id,actor,citation.segment_id) == evidence
    assert chat.history(principal.tenant_id,project.id,actor,convo.id) == before
    assert chat.replay(principal.tenant_id,project.id,actor,convo.id,body) == turn
    view = VisualGalleryRepository(repo).gallery(principal.tenant_id,project.id,item.source.id,actor)
    assert view.searchable and view.active_index_generation == 4 and view.active_embedding_space == HASH_SPACE
    assert service.ask(principal,project.id,'Kubernetes TLS clusters').abstained
    ticket = repo.delete_source(principal.tenant_id,project.id,item.source.id,actor)
    assert cleanup_once(repo) == 1 and not repo.artifacts.objects
    assert repo.get_cleanup(principal.tenant_id,project.id,ticket.id,actor).status == 'completed'
    assert chat.history(principal.tenant_id,project.id,actor,convo.id).turns == []
    with pytest.raises(ProjectNotFoundError): chat.evidence(principal.tenant_id,project.id,actor,citation.segment_id)
    with repo.store._connect() as connection:
        for table in ('visual_index_runs','visual_index_chunks','content_segments','processing_versions'):
            assert connection.execute(f'SELECT count(*) AS n FROM {table}').fetchone()['n'] == 0


def test_concurrent_command_replay_conflict_and_no_wrong_worker_claim(ingestion):
    _, publication = complete(ingestion)
    repo = ingestion[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        items = list(pool.map(lambda _: queue_index(ingestion,publication),range(2)))
    assert items[0].job.id == items[1].job.id and sum(i.deduplicated for i in items) == 1
    with pytest.raises(SourceError): queue_index(ingestion,publication,'different-key-busy')
    with pytest.raises(SourceError): VisualIndexRepository(repo).enqueue(items[0].source.tenant_id,items[0].source.project_id,items[0].source.id,uuid4(),ingestion[4],'index-ocr-fixture')
    item = items[0]
    assert repo.claim_job(item.source.tenant_id,item.source.project_id,item.source.id,item.job.id,item.job.generation) is None
    assert run(repo,item)


def test_semantic_bounded_continuations_retry_reuse_and_atomic_switch(ingestion, monkeypatch):
    repo, service, principal, project, actor = ingestion
    _, publication = long_gallery(ingestion)
    old = queue_index(ingestion,publication)
    assert not run(repo,old); make_due(repo,old); assert run(repo,old)
    old_citation = service.ask(principal,project.id,'health').citations[0]
    repo.settings = replace(repo.settings,embedding_provider='ollama')
    calls = []
    class Provider(FixtureSemanticProvider):
        fail_once = False
        def embed_documents(self,texts):
            calls.extend(texts)
            if self.fail_once:
                self.fail_once=False
                raise SourceError('local_embeddings_unavailable','Fixture outage.',transient=True)
            return super().embed_documents(texts)
    provider = Provider()
    monkeypatch.setattr('app.jobs.visual_indexing.build_embedding_provider',lambda _: provider)
    item = queue_index(ingestion,publication,'semantic-ocr-generation')
    assert not run(repo,item)
    state = repo.get_job(principal.tenant_id,project.id,item.job.id)
    assert (state.processed_segments,state.total_segments,state.stage,state.attempt_count) == (64,84,'waiting_continuation',1)
    assert not repo.store.search(principal.tenant_id,project.id,'health',[1.]+[0.]*1023,4,embedding_space=QWEN_SPACE)
    assert repo.get_source(principal.tenant_id,project.id,item.source.id).active_generation == old.job.generation
    assert 'tutorial_embedding_checkpoint_segments 64\n' in repo.render_metrics()
    repo.command(principal.tenant_id,project.id,item.source.id,actor,'cancel','cancel-ocr-fixture')
    assert not run(repo,item) and len(calls) == 64
    repo.command(principal.tenant_id,project.id,item.source.id,actor,'retry','retry-ocr-fixture')
    provider.fail_once=True
    assert not run(repo,item)
    make_due(repo,item); assert run(repo,item)
    done = repo.get_job(principal.tenant_id,project.id,item.job.id)
    assert done.processed_segments == 84 and done.delivery_count == 3 and done.attempt_count == 3
    assert sum(text.startswith('GET /health frame 0.') for text in calls) == 1
    assert len(calls) == 92  # 64 committed, one failed batch of eight, then 20 remaining.
    assert ChatRepository(repo.store).evidence(principal.tenant_id,project.id,actor,old_citation.segment_id).generation == old.job.generation
    service.embedding_provider=provider
    assert not service.ask(principal,project.id,'health').abstained
    with repo.store._connect() as connection:
        usage=connection.execute('SELECT * FROM usage_events WHERE job_id=%s',(item.job.id,)).fetchone()
        assert usage['input_tokens'] == 84*12 and usage['segment_count'] == 84 and usage['model_digest'] == provider.model_digest
        assert connection.execute('SELECT count(*) AS n FROM visual_index_chunks').fetchone()['n'] == 0


@pytest.mark.parametrize('boundary',['tenant','project','source','generation','token','actor','revoked','cancelled','lease','source_delete','project_delete'])
def test_scoped_live_fences_reject_stale_private_index_and_no_publication(ingestion,boundary):
    repo, service, principal, project, actor = ingestion
    item = queue_index(ingestion)
    active = active_claim(repo,item)
    index = VisualIndexRepository(repo)
    provider = DeterministicHashEmbeddingProvider()
    assert index.begin(active,provider)[0] == 0
    if boundary in {'tenant','project','source','generation','token','actor'}:
        key={'tenant':'tenant_id','project':'project_id','source':'source_id','generation':'generation','token':'lease_token','actor':'actor_user_id'}[boundary]
        active={**active,key: 'foreign' if boundary=='tenant' else 999 if boundary=='generation' else uuid4()}
    elif boundary=='revoked':
        with repo.store._connect() as connection: connection.execute('DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s',(principal.tenant_id,actor))
    elif boundary=='cancelled': repo.command(principal.tenant_id,project.id,item.source.id,actor,'cancel','cancel-index-fence')
    elif boundary=='lease':
        with repo.store._connect() as connection: connection.execute("UPDATE processing_jobs SET lease_expires_at=now()-interval '1 second' WHERE id=%s",(item.job.id,))
    elif boundary=='source_delete': repo.delete_source(principal.tenant_id,project.id,item.source.id,actor)
    else: service.delete_project(principal,project.id)
    assert index.begin(active,provider) is None
    assert not index.save(active,0,provider.embed_documents(['user_id','user_id']))
    assert not index.finish(active,provider)
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM content_segments').fetchone()['n'] == 0


@pytest.mark.parametrize('corruption',['text','frame','vector','profile','manifest','parser','missing'])
def test_corrupt_committed_batches_or_gallery_cannot_activate(ingestion,corruption):
    repo = ingestion[0]; item=queue_index(ingestion); active=active_claim(repo,item)
    index=VisualIndexRepository(repo); provider=DeterministicHashEmbeddingProvider()
    _, expected=index.begin(active,provider)
    assert index.save(active,0,provider.embed_documents([x['text'] for x in expected]))
    with repo.store._connect() as connection:
        if corruption=='text': connection.execute("UPDATE visual_index_chunks SET text='altered'")
        elif corruption=='frame': connection.execute('UPDATE visual_index_chunks SET frame_id=(SELECT id FROM retained_visual_frames ORDER BY ordinal DESC LIMIT 1) WHERE ordinal=0')
        elif corruption=='vector': connection.execute('UPDATE visual_index_chunks SET embedding=%s::vector',('[1,'+','.join(['0']*63)+']',))
        elif corruption=='profile': connection.execute("UPDATE visual_runs SET profile='local-visual-v1:'||repeat('f',64)")
        elif corruption=='manifest': connection.execute("UPDATE processing_jobs SET chunk_manifest_sha256=repeat('a',64) WHERE id=%s",(item.job.id,))
        elif corruption=='parser': connection.execute("UPDATE processing_jobs SET total_segments=3 WHERE id=%s",(item.job.id,))
        else: connection.execute('DELETE FROM visual_index_chunks WHERE ordinal=0')
    with pytest.raises(SourceError): index.finish(active,provider)
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM processing_versions').fetchone()['n'] == 0


def test_blank_ocr_and_configuration_drift_fail_without_fabricating_evidence(ingestion,monkeypatch):
    repo = ingestion[0]; _, publication = long_gallery(ingestion,text=' \n\t',count=1)
    item=queue_index(ingestion,publication)
    assert not run(repo,item)
    assert repo.get_job(item.source.tenant_id,item.source.project_id,item.job.id).failure_code=='visual_ocr_empty'
    assert not VisualGalleryRepository(repo).gallery(item.source.tenant_id,item.source.project_id,item.source.id,ingestion[4]).searchable
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM processing_versions').fetchone()['n']==0


def test_evidence_http_safe_projection_archive_and_foreign_scopes(ingestion):
    repo,service,principal,project,actor=ingestion; item=queue_index(ingestion); assert run(repo,item)
    citation=service.ask(principal,project.id,'user_id').citations[0]
    settings=replace(repo.settings,development_auth_subject=principal.subject,development_auth_tenant=principal.tenant_id)
    auth=DevelopmentAuthenticator(token='test-development-token',subject=principal.subject,tenant_id=principal.tenant_id)
    class FixtureAuth:
        def authenticate(self,headers):
            auth.authenticate(headers)
            return principal
    app=create_app(settings=settings,store=repo.store,authenticator=FixtureAuth(),artifacts=repo.artifacts)
    path=f'/api/v1/projects/{project.id}/evidence/{citation.segment_id}'
    with TestClient(app) as client:
        assert client.get(path).status_code==401
        response=client.get(path,headers={'Authorization':'Bearer test-development-token'})
        assert response.status_code==200 and response.json()['frame_id']==str(citation.frame_id)
        assert response.json()['visual_origin']['human_reviewed'] is False
        assert 'no-store' in response.headers['cache-control']
        assert not any(word in response.text for word in ('object_key','input_sha256','language_data','identity'))
        foreign=service.create_project(principal,ProjectCreate(title='Foreign'))
        assert client.get(path.replace(str(project.id),str(foreign.id)),headers={'Authorization':'Bearer test-development-token'}).status_code==404
    service.archive_project(principal,project.id)
    assert ChatRepository(repo.store).evidence(principal.tenant_id,project.id,actor,citation.segment_id).visual_origin


def test_internal_command_scope_origin_and_archived_rejection(ingestion):
    repo,service,principal,project,actor=ingestion
    original,publication=complete(ingestion)
    index=VisualIndexRepository(repo)
    foreign=service.create_project(principal,ProjectCreate(title='Other'))
    other_actor=repo.store.bootstrap_principal(AuthenticatedPrincipal(provider='test',subject='other-member',tenant_id=principal.tenant_id))
    for tenant,pid,sid,initiator in [('foreign',project.id,publication.source.id,actor),
        (principal.tenant_id,foreign.id,publication.source.id,actor),
        (principal.tenant_id,project.id,uuid4(),actor),
        (principal.tenant_id,project.id,publication.source.id,other_actor)]:
        with pytest.raises((SourceError,ProjectNotFoundError)):
            index.enqueue(tenant,pid,sid,publication.job.id,initiator,'forbidden-index-fixture')
    with pytest.raises(SourceError): index.enqueue(principal.tenant_id,project.id,publication.source.id,original.job.id,actor,'unpublished-index-fixture')
    service.archive_project(principal,project.id)
    with pytest.raises(SourceError): queue_index(ingestion,publication)


def test_configuration_drift_does_not_call_provider_or_publish_and_retry_restores_pin(ingestion,monkeypatch):
    repo,_,principal,project,actor=ingestion; item=queue_index(ingestion)
    class Unused(FixtureSemanticProvider):
        def embed_documents(self,texts): raise AssertionError('Changed configuration must not infer')
    monkeypatch.setattr('app.jobs.visual_indexing.build_embedding_provider',lambda _: Unused())
    assert not run(repo,item)
    assert repo.get_job(principal.tenant_id,project.id,item.job.id).failure_code=='processing_configuration_changed'
    monkeypatch.setattr('app.jobs.visual_indexing.build_embedding_provider',lambda _: DeterministicHashEmbeddingProvider())
    repo.command(principal.tenant_id,project.id,item.source.id,actor,'retry','restored-index-fixture')
    assert run(repo,item)


@pytest.mark.parametrize('boundary',['save','finish'])
def test_actual_wall_clock_expiry_rolls_back_batch_or_whole_promotion(ingestion,monkeypatch,boundary):
    repo=ingestion[0]; item=queue_index(ingestion); active=active_claim(repo,item)
    index=VisualIndexRepository(repo); provider=DeterministicHashEmbeddingProvider()
    _,expected=index.begin(active,provider)
    batch=provider.embed_documents([x['text'] for x in expected])
    if boundary=='finish':
        assert index.save(active,0,batch)
        activate=repo._activate
        def slow(*args,**kwargs):
            activate(*args,**kwargs)
            args[0].execute('SELECT pg_sleep(1)')
        monkeypatch.setattr(repo,'_activate',slow)
    with repo.store._connect() as connection:
        if boundary=='save':
            connection.execute("CREATE FUNCTION slow_ocr_insert() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep(1); RETURN NEW; END $$")
            connection.execute('CREATE TRIGGER slow_ocr BEFORE INSERT ON visual_index_chunks FOR EACH ROW EXECUTE FUNCTION slow_ocr_insert()')
        connection.execute("UPDATE processing_jobs SET lease_expires_at=clock_timestamp()+interval '700 milliseconds' WHERE id=%s",(item.job.id,))
    assert not (index.save(active,0,batch) if boundary=='save' else index.finish(active,provider))
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM content_segments').fetchone()['n']==0
        assert connection.execute('SELECT count(*) AS n FROM processing_versions').fetchone()['n']==0
        assert connection.execute('SELECT count(*) AS n FROM visual_index_chunks').fetchone()['n']==(0 if boundary=='save' else 2)
        assert connection.execute('SELECT count(*) AS n FROM usage_events').fetchone()['n']==1


def test_scoped_foreign_keys_reject_different_existing_gallery_or_frame(ingestion):
    import psycopg
    repo,_,principal,project,_=ingestion
    _,publication=complete(ingestion); item=queue_index(ingestion,publication)
    other_project=ingestion[1].create_project(principal,ProjectCreate(title='Other gallery'))
    # Another existing source in the same project, not just a nonexistent UUID.
    from test_ingestion_integration import register,run as run_transcript
    other=register(ingestion,key='other-existing-source'); assert run_transcript(repo,other)
    with pytest.raises(psycopg.IntegrityError):
        with repo.store._connect() as connection:
            connection.execute('UPDATE visual_index_runs SET source_id=%s WHERE job_id=%s',(other.source.id,item.job.id))
    with pytest.raises(psycopg.IntegrityError):
        with repo.store._connect() as connection:
            connection.execute('UPDATE visual_index_runs SET project_id=%s WHERE job_id=%s',(other_project.id,item.job.id))


@pytest.mark.parametrize('boundary',['search','evidence','history'])
def test_missing_managed_origin_never_downgrades_ocr_to_unlabeled_evidence(ingestion,boundary):
    repo,service,principal,project,actor=ingestion
    item=queue_index(ingestion); assert run(repo,item)
    response,attribution=service.prepare_answer(principal,project.id,'user_id')
    chat=ChatRepository(repo.store)
    convo=chat.create(principal.tenant_id,project.id,actor,ConversationCreate(idempotency_key='origin-integrity-conversation'))
    body=MessageRequest(question='user_id',idempotency_key='origin-integrity-message')
    chat.record(principal.tenant_id,project.id,actor,convo.id,body,response,attribution)
    with repo.store._connect() as connection:
        connection.execute('UPDATE visual_publications SET published_at=NULL')
    with pytest.raises(SourceError):
        if boundary=='search': service.ask(principal,project.id,'user_id')
        elif boundary=='evidence': chat.evidence(principal.tenant_id,project.id,actor,response.citations[0].segment_id)
        else: chat.history(principal.tenant_id,project.id,actor,convo.id)
