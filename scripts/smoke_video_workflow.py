"""Opt-in development smoke: authored MP4 on stdin; only its new project is removed.

Requires running native visual/ordinary workers, API, scheduler, MinIO and frontend,
backend dependencies and explicit test credentials/ports in the environment.
Does not load .env, run migrations, download models or enable a product upload API.
"""
from dataclasses import replace
import json
import os
import sys
import struct
import time
import traceback
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from app.artifacts.storage import S3ArtifactStore
from app.config import Settings
from app.embedding_profiles import HASH_SPACE
from app.models import AuthenticatedPrincipal, AuthorizationMode
from app.postgres import PostgresStore
from app.sources.repository import SourceRepository
from app.sources.video import VideoRepository
from app.sources.contracts import Registration
from app.vision.media import validate_mp4


def main():
    if os.getenv('VIDEO_WORKFLOW_SMOKE') != '1':
        raise ValueError('Explicitly opt into the owned-data development smoke')
    settings = Settings.from_env()
    if settings.auth_mode != 'development' or settings.embedding_provider != 'hash' or settings.answer_provider != 'extractive':
        raise ValueError('This smoke requires development auth and hash/extractive mode')
    fixture = sys.stdin.buffer.read(100_000_001)
    validate_mp4(fixture)
    api = f"http://127.0.0.1:{os.getenv('API_PORT', '8000')}"
    web = f"http://127.0.0.1:{os.getenv('FRONTEND_PORT', '3000')}"
    # Host-side private registration uses the same configured Compose credentials.
    # No automatic migration or application-scoped environment file is read.
    user, password, db = (quote(os.getenv('POSTGRES_USER', 'tutorial'), safe=''),
                          quote(os.environ['POSTGRES_PASSWORD'], safe=''),
                          quote(os.getenv('POSTGRES_DB', 'tutorial'), safe=''))
    settings = replace(settings, auto_migrate=False,
        database_url=f"postgresql://{user}:{password}@127.0.0.1:{os.getenv('POSTGRES_PORT', '5433')}/{db}",
        s3_endpoint=f"http://127.0.0.1:{os.getenv('MINIO_API_PORT', '9000')}",
        s3_bucket='tutorial-artifacts', s3_access_key=os.getenv('MINIO_ROOT_USER', 'tutorial'),
        s3_secret_key=os.environ['MINIO_ROOT_PASSWORD'])
    store = PostgresStore(settings.database_url)
    repo = SourceRepository(store, S3ArtifactStore(settings), settings)

    public_upload = os.getenv('VIDEO_UPLOAD_SMOKE') == '1'
    change_selection = os.getenv('VIDEO_CHANGE_SMOKE') == '1'
    language = 'en' if change_selection else 'tr'
    def request(path, body=None, method='GET', expected=200, *, frontend=False, content_type='application/json'):
        headers = {'Content-Type': content_type}
        if not frontend: headers['Authorization'] = 'Bearer ' + settings.development_auth_token
        else: headers['Origin'] = web
        data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
        try:
            with urlopen(Request((web if frontend else api) + path, data=data, headers=headers, method=method), timeout=45) as response:
                status, payload, receipt = response.status, response.read(3_000_000), response.headers
        except HTTPError as error:
            status, payload, receipt = error.code, error.read(100_000), error.headers
        assert status == expected, f'Expected HTTP {expected}; received {status}'
        return payload, receipt

    def wait(check, timeout=120):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = check()
            if value: return value
            time.sleep(.25)
        raise AssertionError('Owned video workflow smoke exceeded its deadline')

    created = json.loads(request('/api/v1/projects', {'title': 'Video workflow smoke ' + uuid4().hex[:12]}, 'POST', 201)[0])
    project = UUID(created['id'])  # Deletion target comes only from this creation response.
    path = f'/api/v1/projects/{project}'
    deleted = False
    try:
        actor = store.bootstrap_principal(AuthenticatedPrincipal(provider='development',
            subject=settings.development_auth_subject, tenant_id=settings.development_auth_tenant))
        tenant = settings.development_auth_tenant
        args = dict(filename='authored-cards.mp4', content=fixture, rights=AuthorizationMode.OWNER_UPLOAD,
                    language=language, idempotency_key='smoke-video-' + uuid4().hex, auto_process=True)
        def public_register(data, key, filename='authored-cards.mp4'):
            boundary='video-smoke-'+uuid4().hex
            body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: video/mp4\r\n\r\n'.encode()+data+b'\r\n')
            fields=dict(authorization_mode='owner_upload',language=language,idempotency_key=key,retention_acknowledged='accepted')
            body+=(''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n' for name,value in fields.items())+f'--{boundary}--\r\n').encode()
            payload,headers=request(f'/api/projects/{project}/sources/video',body,'POST',202,frontend=True,content_type='multipart/form-data; boundary='+boundary)
            receipt=json.loads(payload)
            assert set(receipt)=={'project_id','source_id','job_id','deduplicated'} and receipt['project_id']==str(project)
            assert 'no-store' in headers['Cache-Control']
            return Registration(source=repo.get_source(tenant,project,UUID(receipt['source_id'])),
                job=repo.get_job(tenant,project,UUID(receipt['job_id'])),deduplicated=receipt['deduplicated'])
        if public_upload:
            capability=json.loads(request('/api/v1/ingestion/video-capabilities')[0])
            assert capability['enabled'] and capability['max_bytes']==100_000_000
            workspace=request(f'/projects/{project}',frontend=True)[0].decode()
            assert 'Upload authorized MP4' in workspace and 'selected-frame/OCR retention' in workspace
            original=public_register(fixture,args['idempotency_key'])
        else: original = VideoRepository(repo).register(tenant, project, actor, **args)
        def ready():
            current = repo.get_source(tenant, project, original.source.id)
            assert current.status not in {'failed', 'cancelled'}, 'Owned video processing failed'
            return current if current.status == 'ready' else None
        current = wait(ready)
        assert current.generation == current.active_generation == 3 and current.active_embedding_space == HASH_SPACE
        assert current.job.job_type == 'visual_index' and current.job.status == 'succeeded'
        replay = public_register(fixture,args['idempotency_key']) if public_upload else VideoRepository(repo).register(tenant, project, actor, **args)
        assert replay.deduplicated and replay.job.id == original.job.id and replay.source.generation == 3
        gallery = json.loads(request(f'{path}/sources/{original.source.id}/frames')[0])
        assert gallery['searchable'] and gallery['active_index_generation'] == 3
        assert gallery['origin']['job_id'] == str(original.job.id)
        if change_selection:
            expected_pts = [0, 3000, 4000, 7000, 13000, 19000]
            expected_citation_pts, question = 3000, 'BRIEF VIEW'
            assert gallery['origin']['profile'].startswith('local-visual-v2:')
            assert gallery['origin']['checkpoint_version'] == 'visual-checkpoint-v2'
            assert 'BRIEF VIEW' in gallery['items'][1]['ocr_text']
        else:
            expected_pts, expected_citation_pts, question = [0, 10000], 0, 'HEALTH CHECK'
            assert 'sağlık kontrolü' in gallery['items'][1]['ocr_text'].replace('I', 'ı').replace('İ', 'i').casefold()
        assert [f['timestamp_ms'] for f in gallery['items']] == expected_pts
        answer = json.loads(request(path + '/questions', {'question': question, 'source_ids': [str(original.source.id)]}, 'POST')[0])
        assert not answer['abstained']
        citation = answer['citations'][0]
        assert citation['modality'] == 'frame' and citation['start_ms'] == citation['end_ms'] == expected_citation_pts
        expected_frame = gallery['items'][expected_pts.index(expected_citation_pts)]
        assert citation['frame_id'] == expected_frame['id'] and citation['visual_origin'] == gallery['origin']
        rendered = request(f'/projects/{project}/evidence/{citation["segment_id"]}', frontend=True)[0].decode()
        assert 'Automatic frame OCR' in rendered and 'not human-reviewed' in rendered
        if change_selection: assert 'Experimental change-aware selection' in rendered
        assert f'#frame-{citation["frame_id"]}' in rendered and 'No original-video player' in rendered
        png, headers = request(f'/api/projects/{project}/frames/{citation["frame_id"]}/image', frontend=True)
        assert png.startswith(b'\x89PNG\r\n\x1a\n') and 'no-store' in headers['Cache-Control']
        with store._connect() as connection:
            workflow = connection.execute('SELECT * FROM video_workflows WHERE tenant_id=%s AND project_id=%s AND source_id=%s',
                                          (tenant, project, original.source.id)).fetchone()
            assert workflow['publication_generation'] == 2 and workflow['index_job_id'] == current.job.id
            jobs = connection.execute('SELECT status,actor_user_id FROM processing_jobs WHERE tenant_id=%s AND project_id=%s AND source_id=%s',
                                      (tenant, project, original.source.id)).fetchall()
            assert len(jobs) == 3 and all(j['status'] == 'succeeded' and j['actor_user_id'] == actor for j in jobs)
            usage = connection.execute('SELECT billed_usd FROM usage_events WHERE tenant_id=%s AND project_id=%s AND source_id=%s',
                                       (tenant, project, original.source.id)).fetchall()
            assert len(usage) == 2 and all(u['billed_usd'] == 0 for u in usage)
        def raw_deleted():
            with store._connect() as connection:
                return connection.execute('SELECT deleted_at FROM video_inputs WHERE tenant_id=%s AND project_id=%s AND source_id=%s',
                                          (tenant, project, original.source.id)).fetchone()['deleted_at'] is not None
        wait(raw_deleted, 60)
        if public_upload:
            workspace=request(f'/projects/{project}',frontend=True)[0].decode()
            assert 'Original video deletion confirmed.' in workspace and 'View selected frames' in workspace
        objects = repo.artifacts.client.list_objects_v2(Bucket=repo.artifacts.bucket, Prefix=f'{tenant}/{project}/').get('Contents', [])
        assert len(objects) == len(expected_pts) and all(o['Key'].endswith('/frame.png') for o in objects)
        if change_selection:
            with store._connect() as connection:
                manifest = connection.execute('SELECT selection_manifest FROM visual_runs WHERE tenant_id=%s AND project_id=%s AND job_id=%s',
                    (tenant, project, original.job.id)).fetchone()['selection_manifest']
                assert manifest['selected_timestamps_ms'] == expected_pts and len(manifest['samples']) == 20
        # An independently authored transcript of this known test recording. The
        # product still labels the association user-asserted, never verified.
        transcript = ('WEBVTT\n\n00:00.000 --> 00:01.000\n'
            'Alignment introduction &lt;script&gt;not executable&lt;/script&gt;.\n\n'
            '00:10.000 --> 00:11.000\nAlignment closing view.\n')
        boundary = 'align-smoke-' + uuid4().hex
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="authorization_mode"\r\n\r\nowner_upload\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="idempotency_key"\r\n\r\nalign-{uuid4().hex}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="owned-alignment.vtt"\r\nContent-Type: text/vtt\r\n\r\n'
            f'{transcript}\r\n--{boundary}--\r\n').encode()
        subtitle = json.loads(request(path + '/sources/uploads', body, 'POST', 202,
            content_type='multipart/form-data; boundary=' + boundary)[0])
        text_source = subtitle['source']['id']
        def transcript_ready():
            job = json.loads(request(path + '/jobs/' + subtitle['job']['id'])[0])
            assert job['status'] not in {'failed', 'cancelled'}
            return job['status'] == 'succeeded'
        wait(transcript_ready)
        alignment_path = f'{path}/sources/{original.source.id}/alignment'
        parameters = dict(transcript_source_id=text_source, assert_same_recording='true', offset_ms=0,
            visual_generation=2, transcript_generation=1)
        paired, headers = request(alignment_path + '?' + urlencode(parameters))
        paired = json.loads(paired)
        assert 'no-store' in headers['Cache-Control'] and paired['semantics_verified'] is False
        assert paired['relationship'] == 'user_asserted' and paired['gallery']['origin'] == gallery['origin']
        assert paired['matched_frames'] == (1 if change_selection else 2)
        assert paired['items'][0]['matches'][0]['excerpt'] == 'Alignment introduction <script>not executable</script>.'
        chooser = f'/projects/{project}/sources/{original.source.id}/frames/align'
        selection = request(chooser, frontend=True)[0].decode()
        assert 'I assert that this transcript describes the same recording' in selection and 'owned-alignment.vtt' in selection
        # With a loading boundary Next can stream a meta/RSC redirect in HTTP
        # 200; urllib follows HTTP redirects, not browser-rendered redirects.
        # Validate the pinned destination, then read that exact local view.
        unpinned = {key: value for key, value in parameters.items() if key not in {'visual_generation', 'transcript_generation'}}
        paired_html = request(chooser + '?' + urlencode(unpinned), frontend=True)[0].decode()
        if 'not verified audiovisual identity' not in paired_html:
            assert 'NEXT_REDIRECT' in paired_html or 'http-equiv="refresh"' in paired_html
            assert chooser in paired_html and 'visual_generation=2' in paired_html and 'transcript_generation=1' in paired_html
            paired_html = request(chooser + '?' + urlencode(parameters), frontend=True)[0].decode()
        assert 'Frame and transcript timeline' in paired_html and 'not verified audiovisual identity' in paired_html
        assert '&lt;script&gt;not executable&lt;/script&gt;' in paired_html and '<script>not executable</script>' not in paired_html
        first_span = paired['items'][0]['matches'][0]['segment_id']
        assert f'/evidence/{first_span}' in paired_html
        if change_selection: assert 'No transcript span contains this timestamp' in paired_html
        shifted = json.loads(request(alignment_path + '?' + urlencode({**parameters, 'offset_ms': -600000}))[0])
        assert shifted['matched_frames'] == 0 and all(not item['matches'] for item in shifted['items'])
        reprocessed = json.loads(request(f'{path}/sources/{text_source}/reprocess',
            {'idempotency_key': 'align-reprocess-' + uuid4().hex}, 'POST', 202)[0])
        def reindex_ready():
            job = json.loads(request(path + '/jobs/' + reprocessed['job']['id'])[0])
            assert job['status'] not in {'failed', 'cancelled'}
            return job['status'] == 'succeeded'
        wait(reindex_ready)
        old = json.loads(request(alignment_path + '?' + urlencode(parameters))[0])
        assert old['items'] == paired['items'] and old['transcript']['active_generation'] == 2
        old_html = request(chooser + '?' + urlencode(parameters), frontend=True)[0].decode()
        assert 'older published generation' in old_html
        print('PASS: actual subtitle worker -> user-asserted temporal alignment API/production SSR, pinned generations, escaped text, gaps/offsets and stable evidence after reprocessing.')
        if public_upload and os.getenv('VIDEO_UPLOAD_LARGE_SMOKE')=='1':
            padding=100_000_000-len(fixture)
            assert padding>=8
            large=fixture+struct.pack('>I4s',padding,b'free')+bytes(padding-8)
            validate_mp4(large)
            big=public_register(large,'large-video-'+uuid4().hex,'large-authored.mp4')
            assert big.source.video_retention is not None
            request(f'{path}/sources/{big.source.id}/cancel',{'idempotency_key':'cancel-large-'+uuid4().hex},'POST',202)
            with store._connect() as connection:
                actual=connection.execute('SELECT byte_count FROM video_inputs WHERE tenant_id=%s AND project_id=%s AND source_id=%s',
                    (tenant,project,big.source.id)).fetchone()['byte_count']
                assert actual==100_000_000
            print('PASS: actual 100,000,000-byte MP4 through production BFF/API/spooling and scoped cancellation; no raised subtitle/WAV/chat limits.')
            del large
        _, receipt = request(path, method='DELETE', expected=204)
        deleted = True
        wait(lambda: json.loads(request(f'{path}/cleanup/{receipt["X-Cleanup-ID"]}')[0])['status'] == 'completed', 60)
        assert not repo.artifacts.client.list_objects_v2(Bucket=repo.artifacts.bucket, Prefix=f'{tenant}/{project}/').get('Contents')
        with store._connect() as connection:
            for table in ('video_workflows', 'visual_runs', 'visual_checkpoint_frames', 'retained_visual_frames', 'content_segments'):
                assert not connection.execute(f'SELECT 1 FROM {table} WHERE tenant_id=%s AND project_id=%s', (tenant, project)).fetchone()
        request(f'{path}/evidence/{citation["segment_id"]}', expected=404)
        request(alignment_path + '?' + urlencode(parameters), expected=404)
        print('PASS: '+('public BFF/MP4/retention UI -> ' if public_upload else '')+'actual native MP4 -> automatic gallery/outbox -> OCR index -> frame citation/API/SSR/PNG -> confirmed raw and owned-project cleanup. Fixture OCR quality only.')
        if change_selection: print('PASS: explicit change selection, six exact-PTS frames including a temporal return, persisted full scan and cited transient OCR at 3000 ms.')
    finally:
        if not deleted:
            _, receipt = request(path, method='DELETE', expected=204)
            wait(lambda: json.loads(request(f'{path}/cleanup/{receipt["X-Cleanup-ID"]}')[0])['status'] == 'completed', 60)


if __name__ == '__main__':
    try: main()
    except Exception as error:
        line = traceback.extract_tb(error.__traceback__)[-1].lineno
        raise SystemExit(f'FAIL: video workflow smoke ({type(error).__name__}, check line {line}); no raw payload or exception logged.') from None
