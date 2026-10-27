"""Opt-in development smoke: authored MP4 on stdin; only its new project is removed.

Requires running native visual/ordinary workers, API, scheduler, MinIO and frontend,
backend dependencies and explicit test credentials/ports in the environment.
Does not load .env, run migrations, download models or enable a product upload API.
"""
from dataclasses import replace
import json
import os
import sys
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from app.artifacts.storage import S3ArtifactStore
from app.config import Settings
from app.embedding_profiles import HASH_SPACE
from app.models import AuthenticatedPrincipal, AuthorizationMode
from app.postgres import PostgresStore
from app.sources.repository import SourceRepository
from app.sources.video import VideoRepository
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

    def request(path, body=None, method='GET', expected=200, *, frontend=False):
        headers = {'Content-Type': 'application/json'}
        if not frontend: headers['Authorization'] = 'Bearer ' + settings.development_auth_token
        data = json.dumps(body).encode() if body is not None else None
        try:
            with urlopen(Request((web if frontend else api) + path, data=data, headers=headers, method=method), timeout=15) as response:
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
                    language='tr', idempotency_key='smoke-video-' + uuid4().hex, auto_process=True)
        original = VideoRepository(repo).register(tenant, project, actor, **args)
        def ready():
            current = repo.get_source(tenant, project, original.source.id)
            assert current.status not in {'failed', 'cancelled'}, 'Owned video processing failed'
            return current if current.status == 'ready' else None
        current = wait(ready)
        assert current.generation == current.active_generation == 3 and current.active_embedding_space == HASH_SPACE
        assert current.job.job_type == 'visual_index' and current.job.status == 'succeeded'
        replay = VideoRepository(repo).register(tenant, project, actor, **args)
        assert replay.deduplicated and replay.job.id == original.job.id and replay.source.generation == 3
        gallery = json.loads(request(f'{path}/sources/{original.source.id}/frames')[0])
        assert gallery['searchable'] and gallery['active_index_generation'] == 3
        assert gallery['origin']['job_id'] == str(original.job.id)
        assert [f['timestamp_ms'] for f in gallery['items']] == [0, 10000]
        assert 'sağlık kontrolü' in gallery['items'][1]['ocr_text'].replace('I', 'ı').replace('İ', 'i').casefold()
        answer = json.loads(request(path + '/questions', {'question': 'HEALTH CHECK', 'source_ids': [str(original.source.id)]}, 'POST')[0])
        assert not answer['abstained']
        citation = answer['citations'][0]
        assert citation['modality'] == 'frame' and citation['start_ms'] == citation['end_ms'] == 0
        assert citation['frame_id'] == gallery['items'][0]['id'] and citation['visual_origin'] == gallery['origin']
        rendered = request(f'/projects/{project}/evidence/{citation["segment_id"]}', frontend=True)[0].decode()
        assert 'Automatic frame OCR' in rendered and 'not human-reviewed' in rendered
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
        objects = repo.artifacts.client.list_objects_v2(Bucket=repo.artifacts.bucket, Prefix=f'{tenant}/{project}/').get('Contents', [])
        assert len(objects) == 2 and all(o['Key'].endswith('/frame.png') for o in objects)
        _, receipt = request(path, method='DELETE', expected=204)
        deleted = True
        wait(lambda: json.loads(request(f'{path}/cleanup/{receipt["X-Cleanup-ID"]}')[0])['status'] == 'completed', 60)
        assert not repo.artifacts.client.list_objects_v2(Bucket=repo.artifacts.bucket, Prefix=f'{tenant}/{project}/').get('Contents')
        with store._connect() as connection:
            assert not connection.execute('SELECT 1 FROM video_workflows WHERE tenant_id=%s AND project_id=%s', (tenant, project)).fetchone()
        request(f'{path}/evidence/{citation["segment_id"]}', expected=404)
        print('PASS: actual native MP4 -> automatic gallery/outbox -> OCR index -> frame citation/API/SSR/PNG -> confirmed raw and owned-project cleanup. Fixture OCR quality only.')
    finally:
        if not deleted:
            _, receipt = request(path, method='DELETE', expected=204)
            wait(lambda: json.loads(request(f'{path}/cleanup/{receipt["X-Cleanup-ID"]}')[0])['status'] == 'completed', 60)


if __name__ == '__main__':
    try: main()
    except Exception as error:
        raise SystemExit(f'FAIL: video workflow smoke ({type(error).__name__}); inspect safe service status.') from None
