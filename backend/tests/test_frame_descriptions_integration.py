"""Real scoped PostgreSQL publication with explicit image-model fixtures, not quality evidence."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.chat.contracts import ConversationCreate,MessageRequest
from app.chat.repository import ChatRepository
from app.jobs.descriptions import describe_frames
from app.jobs.dispatch import cleanup_once
from app.jobs.visual_indexing import index_visual
from app.main import create_app
from app.models import AuthenticatedPrincipal,ProjectCreate
from app.sources.contracts import SourceError
from app.store import ProjectNotFoundError
from app.vision.descriptions import DescriptionRepository
from app.vision.descriptions_client import DescriptionResult
from test_checkpoints_integration import make_due
from test_frame_descriptions import description,identity
from test_ingestion_integration import ingestion
from test_postgres_integration import isolated_postgres_url
from test_visual_gallery_integration import complete
from test_visual_index_integration import long_gallery,queue_index,run as run_index

pytestmark=pytest.mark.integration


def queue(ingestion,publication=None,key='describe-fixture'):
    repo,_,principal,project,actor=ingestion
    if publication is None: _,publication=complete(ingestion)
    repo.settings=replace(repo.settings,frame_descriptions_enabled=True,vision_model_digest='a'*64)
    return DescriptionRepository(repo).enqueue(principal.tenant_id,project.id,publication.source.id,actor,key)


def run(repo,item):
    return describe_frames(repo,item.source.tenant_id,item.source.project_id,item.source.id,item.job.id,item.job.generation)


def active(repo,item):
    return repo.claim_job(item.source.tenant_id,item.source.project_id,item.source.id,item.job.id,item.job.generation,job_types=('visual_describe',))


def fixture_result(frame):
    return DescriptionResult(identity(),description(),12,30,5,frame['image_sha256'])


@pytest.fixture
def model(monkeypatch):
    calls=[]
    class Provider:
        def __init__(self,url,digest): assert digest=='a'*64
        def ready(self): return identity()
        def describe(self,image,width,height,pinned):
            assert pinned==identity() and width==height==16
            calls.append(hashlib.sha256(image).hexdigest())
            return DescriptionResult(pinned,description(),12,30,5,calls[-1])
    monkeypatch.setattr('app.jobs.descriptions.LocalDescriptionProvider',Provider)
    return calls


def test_private_checkpoints_atomic_index_citations_history_usage_and_full_deletion(ingestion,model):
    repo,service,principal,project,actor=ingestion
    _,publication=complete(ingestion)
    old=queue_index(ingestion,publication); assert run_index(repo,old)
    old_citation=service.ask(principal,project.id,'user_id').citations[0]
    before=ChatRepository(repo.store).evidence(principal.tenant_id,project.id,actor,old_citation.segment_id)
    item=queue(ingestion,publication)
    descriptions=DescriptionRepository(repo)
    assert not run(repo,item) and len(model)==1
    view=descriptions.read(principal.tenant_id,project.id,item.source.id,actor)
    assert view.items==[] and view.origin is None and view.latest_job.processed_segments==1
    assert repo.get_source(principal.tenant_id,project.id,item.source.id).active_generation==old.job.generation
    make_due(repo,item); assert run(repo,item) and not run(repo,item) and len(model)==2
    view=descriptions.read(principal.tenant_id,project.id,item.source.id,actor)
    assert len(view.items)==2 and view.origin.model_digest=='a'*64
    assert view.origin.generation==item.job.generation and view.gallery_generation==publication.job.generation
    assert view.index_generation==item.job.generation+1 and view.index_job.status=='pending'
    assert index_visual(repo,principal.tenant_id,project.id,item.source.id,view.index_job.id,view.index_generation)
    response,attribution=service.prepare_answer(principal,project.id,'boxes', [item.source.id])
    assert not response.abstained and response.citations
    citation=response.citations[0]
    assert citation.visual_origin.description==view.origin and citation.processing_version==f'visual-evidence-chunks-v2:g{view.index_generation}'
    assert 'Unreviewed visual evidence' in response.answer
    chat=ChatRepository(repo.store)
    evidence=chat.evidence(principal.tenant_id,project.id,actor,citation.segment_id)
    assert evidence.text.startswith('Unreviewed image-model description:') and evidence.frame_id==citation.frame_id
    conversation=chat.create(principal.tenant_id,project.id,actor,ConversationCreate(idempotency_key='described-conversation'))
    chat.record(principal.tenant_id,project.id,actor,conversation.id,MessageRequest(question='boxes',idempotency_key='described-message'),response,attribution)
    assert chat.history(principal.tenant_id,project.id,actor,conversation.id).turns[0].response.citations[0].visual_origin.description==view.origin
    assert chat.evidence(principal.tenant_id,project.id,actor,old_citation.segment_id)==before
    with repo.store._connect() as connection:
        usage=connection.execute('SELECT * FROM usage_events WHERE job_id=%s',(item.job.id,)).fetchall()
        assert len(usage)==1 and usage[0]['input_image_count']==2 and usage[0]['input_image_bytes']>0
        assert (usage[0]['input_tokens'],usage[0]['output_tokens'],usage[0]['billed_usd'])==(24,60,0)
        assert usage[0]['model_digest']=='a'*64 and usage[0]['prompt_version']==view.origin.prompt_version
        assert connection.execute('SELECT count(*) AS n FROM visual_descriptions').fetchone()['n']==2
        assert connection.execute('SELECT count(*) AS n FROM content_segments WHERE generation=%s',(view.index_generation,)).fetchone()['n']==4
    ticket=repo.delete_source(principal.tenant_id,project.id,item.source.id,actor)
    while cleanup_once(repo): pass
    assert repo.get_cleanup(principal.tenant_id,project.id,ticket.id,actor).status=='completed' and not repo.artifacts.objects
    with repo.store._connect() as connection:
        for table in ('visual_description_runs','visual_descriptions','visual_index_runs','processing_versions','usage_events','content_segments'):
            assert connection.execute(f'SELECT count(*) AS n FROM {table}').fetchone()['n']==0


def test_concurrent_receipt_replay_pinned_inputs_and_default_closed(ingestion,model):
    repo,_,principal,project,actor=ingestion; _,publication=complete(ingestion)
    with pytest.raises(SourceError) as error: DescriptionRepository(repo).enqueue(principal.tenant_id,project.id,publication.source.id,actor,'disabled-fixture')
    assert error.value.code=='frame_descriptions_disabled'
    with ThreadPoolExecutor(max_workers=2) as pool: items=list(pool.map(lambda _:queue(ingestion,publication),range(2)))
    assert items[0].job.id==items[1].job.id and sorted(i.deduplicated for i in items)==[False,True]
    item=items[0]
    assert repo.claim_job(principal.tenant_id,project.id,item.source.id,item.job.id,item.job.generation) is None
    repo.settings=replace(repo.settings,vision_model_digest='b'*64)
    assert not run(repo,item); make_due(repo,item); assert run(repo,item)
    assert len(model)==2  # Digest was pinned at acceptance, not taken from changed settings.
    replay=queue(ingestion,publication)
    assert replay.job.id==item.job.id and replay.deduplicated


@pytest.mark.parametrize('boundary',['tenant','project','source','generation','token','actor','revoked','cancelled','lease','source_delete','project_delete'])
def test_scoped_live_fences_reject_late_model_results(ingestion,boundary):
    repo,service,principal,project,actor=ingestion; item=queue(ingestion); claim=active(repo,item)
    store=DescriptionRepository(repo); _,frames,_=store.next(claim,identity())
    if boundary in {'tenant','project','source','generation','token','actor'}:
        key={'tenant':'tenant_id','project':'project_id','source':'source_id','generation':'generation','token':'lease_token','actor':'actor_user_id'}[boundary]
        claim={**claim,key:'foreign' if boundary=='tenant' else 999 if boundary=='generation' else uuid4()}
    elif boundary=='revoked':
        with repo.store._connect() as connection: connection.execute('DELETE FROM memberships WHERE tenant_id=%s AND user_id=%s',(principal.tenant_id,actor))
    elif boundary=='cancelled': repo.command(principal.tenant_id,project.id,item.source.id,actor,'cancel','cancel-description')
    elif boundary=='lease':
        with repo.store._connect() as connection: connection.execute("UPDATE processing_jobs SET lease_expires_at=now()-interval '1 second' WHERE id=%s",(item.job.id,))
    elif boundary=='source_delete': repo.delete_source(principal.tenant_id,project.id,item.source.id,actor)
    else: service.delete_project(principal,project.id)
    assert store.next(claim) is None and not store.save(claim,0,fixture_result(frames[0])) and not store.advance(claim)
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM visual_descriptions').fetchone()['n']==0


@pytest.mark.parametrize('corruption',['content','hash','image','identity','missing'])
def test_corrupt_checkpoints_cannot_activate(ingestion,corruption):
    repo=ingestion[0];item=queue(ingestion);claim=active(repo,item);store=DescriptionRepository(repo)
    _,frames,_=store.next(claim,identity()); assert store.save(claim,0,fixture_result(frames[0]))
    with repo.store._connect() as connection:
        if corruption=='content': connection.execute("UPDATE visual_descriptions SET description=jsonb_set(description,'{summary}','\"changed\"')")
        if corruption=='hash': connection.execute("UPDATE visual_descriptions SET description_sha256=repeat('b',64)")
        if corruption=='image': connection.execute("UPDATE visual_descriptions SET image_sha256=repeat('b',64)")
        if corruption=='identity': connection.execute("UPDATE visual_description_runs SET identity=jsonb_set(identity,'{engine}','\"0.40.4\"')")
        if corruption=='missing': connection.execute('DELETE FROM visual_descriptions')
    with pytest.raises(SourceError): store.advance(claim)
    with repo.store._connect() as connection:
        assert connection.execute('SELECT count(*) AS n FROM usage_events WHERE job_id=%s',(item.job.id,)).fetchone()['n']==0
        assert connection.execute('SELECT count(*) AS n FROM visual_index_runs').fetchone()['n']==0


def test_last_saved_checkpoint_recovers_without_constructing_provider(ingestion,monkeypatch):
    repo,_,principal,project,actor=ingestion
    _,publication=long_gallery(ingestion,text='user_id',count=1)
    item=queue(ingestion,publication);claim=active(repo,item);store=DescriptionRepository(repo)
    _,frames,_=store.next(claim,identity());assert store.save(claim,0,fixture_result(frames[0]))
    with repo.store._connect() as connection: connection.execute("UPDATE processing_jobs SET lease_expires_at=now()-interval '1 second' WHERE id=%s",(item.job.id,))
    assert repo.recover_leases()==1;make_due(repo,item)
    def forbidden(*_): raise AssertionError('Already committed last frame must not invoke a provider')
    monkeypatch.setattr('app.jobs.descriptions.LocalDescriptionProvider',forbidden)
    assert run(repo,item)
    assert store.read(principal.tenant_id,project.id,item.source.id,actor).origin


def test_cancel_retry_during_model_io_has_no_database_lock_and_preserves_old_evidence(ingestion,monkeypatch,model):
    repo,service,principal,project,actor=ingestion
    _,publication=complete(ingestion);old=queue_index(ingestion,publication);assert run_index(repo,old)
    item=queue(ingestion,publication)
    from app.jobs import descriptions as worker
    original=worker.LocalDescriptionProvider.describe
    def cancel(self,*args):
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(repo.command,principal.tenant_id,project.id,item.source.id,actor,'cancel','cancel-during-inference').result(timeout=3)
        return original(self,*args)
    monkeypatch.setattr(worker.LocalDescriptionProvider,'describe',cancel)
    assert not run(repo,item)
    assert DescriptionRepository(repo).read(principal.tenant_id,project.id,item.source.id,actor).items==[]
    assert not service.ask(principal,project.id,'user_id').abstained
    repo.command(principal.tenant_id,project.id,item.source.id,actor,'retry','retry-description')
    monkeypatch.setattr(worker.LocalDescriptionProvider,'describe',original)
    assert not run(repo,item);make_due(repo,item);assert run(repo,item)


def test_http_auth_scope_no_store_disabled_and_no_private_projection(ingestion,model):
    repo,service,principal,project,actor=ingestion; item=queue(ingestion)
    class Auth:
        def authenticate(self,headers):
            if headers.get('authorization')!='Bearer fixture-token':
                from app.auth import AuthenticationError
                raise AuthenticationError('Authentication required')
            return principal
    app=create_app(settings=repo.settings,store=repo.store,authenticator=Auth(),artifacts=repo.artifacts)
    path=f'/api/v1/projects/{project.id}/sources/{item.source.id}/descriptions'
    headers={'Authorization':'Bearer fixture-token'}
    with TestClient(app) as client:
        assert client.get(path).status_code==401
        assert client.get(path,headers=headers).status_code==200
        foreign=service.create_project(principal,ProjectCreate(title='Foreign'))
        assert client.get(path.replace(str(project.id),str(foreign.id)),headers=headers).status_code==404
        assert client.post(path.replace(str(project.id),str(foreign.id)),headers=headers,json={'idempotency_key':'forbidden-key'}).status_code==404
        assert client.post(path,headers=headers,json={'idempotency_key':'describe-fixture'}).status_code==202
        assert not run(repo,item);make_due(repo,item);assert run(repo,item)
        response=client.get(path,headers=headers)
        assert response.status_code==200 and 'no-store' in response.headers['cache-control']
        assert response.headers['x-content-type-options']=='nosniff'
        assert not any(key in response.text for key in ('object_key','image_sha256','identity_sha256','lease_token','actor_user_id'))
        assert response.json()['origin']['model_digest']=='a'*64


def test_command_actor_scope_archived_and_wrong_image_binding(ingestion):
    repo,service,principal,project,actor=ingestion; _,publication=complete(ingestion)
    repo.settings=replace(repo.settings,frame_descriptions_enabled=True,vision_model_digest='a'*64)
    other=repo.store.bootstrap_principal(AuthenticatedPrincipal(provider='test',subject='other-describer',tenant_id=principal.tenant_id))
    for tenant,pid,sid,user in [('foreign',project.id,publication.source.id,actor),(principal.tenant_id,uuid4(),publication.source.id,actor),
            (principal.tenant_id,project.id,uuid4(),actor),(principal.tenant_id,project.id,publication.source.id,other)]:
        with pytest.raises((SourceError,ProjectNotFoundError)): DescriptionRepository(repo).enqueue(tenant,pid,sid,user,'scope-fixture')
    item=queue(ingestion,publication);claim=active(repo,item);store=DescriptionRepository(repo)
    _,frames,_=store.next(claim,identity())
    with pytest.raises(SourceError): store.save(claim,0,replace(fixture_result(frames[0]),input_sha256='b'*64))
    repo.command(principal.tenant_id,project.id,item.source.id,actor,'cancel','stop-description')
    service.archive_project(principal,project.id)
    with pytest.raises(SourceError): queue(ingestion,publication,'archived-description')


def test_abstention_has_no_description_segment_and_new_failure_preserves_snapshot(ingestion,monkeypatch,model):
    from app.vision.descriptions_client import FrameDescription
    from app.jobs import descriptions as worker
    repo,service,principal,project,actor=ingestion
    _,publication=long_gallery(ingestion,text='user_id',count=1)
    original=worker.LocalDescriptionProvider.describe
    def abstain(self,*args):
        return replace(original(self,*args),description=FrameDescription(kind='unclear',summary='',details=[],uncertainties=['Cannot infer purpose.'],abstained=True))
    monkeypatch.setattr(worker.LocalDescriptionProvider,'describe',abstain)
    item=queue(ingestion,publication);assert run(repo,item)
    view=DescriptionRepository(repo).read(principal.tenant_id,project.id,item.source.id,actor)
    assert view.items[0].description.abstained
    assert index_visual(repo,principal.tenant_id,project.id,item.source.id,view.index_job.id,view.index_generation)
    with repo.store._connect() as connection:
        rows=connection.execute('SELECT text FROM content_segments WHERE generation=%s',(view.index_generation,)).fetchall()
        assert [r['text'] for r in rows]==['Unreviewed OCR text:\nuser_id']
    newer=queue(ingestion,publication,'new-description-fails')
    def unavailable(*_): raise SourceError('local_vision_unavailable','Fixture unavailable.',503,transient=True)
    monkeypatch.setattr(worker.LocalDescriptionProvider,'describe',unavailable)
    assert not run(repo,newer)
    preserved=DescriptionRepository(repo).read(principal.tenant_id,project.id,item.source.id,actor)
    assert preserved.items==view.items and preserved.origin==view.origin and preserved.latest_job.id==newer.job.id
    assert repo.get_source(principal.tenant_id,project.id,item.source.id).active_generation==view.index_generation
    assert not service.ask(principal,project.id,'user_id').abstained


def test_image_only_evidence_can_index_without_inventing_ocr_or_speech(ingestion,model):
    repo,service,principal,project,actor=ingestion
    _,publication=long_gallery(ingestion,text='',count=1)
    item=queue(ingestion,publication);assert run(repo,item)
    view=DescriptionRepository(repo).read(principal.tenant_id,project.id,item.source.id,actor)
    assert index_visual(repo,principal.tenant_id,project.id,item.source.id,view.index_job.id,view.index_generation)
    response=service.ask(principal,project.id,'boxes')
    assert not response.abstained and response.citations[0].modality=='frame'
    evidence=ChatRepository(repo.store).evidence(principal.tenant_id,project.id,actor,response.citations[0].segment_id)
    assert evidence.text.startswith('Unreviewed image-model description:') and 'OCR' not in evidence.text
