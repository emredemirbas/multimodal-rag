import json
import anyio
import pytest
from app.config import Settings
from app.sources.upload_limit import UploadLimitMiddleware
from conftest import MappingAuthenticator


@pytest.mark.anyio
@pytest.mark.parametrize('authenticated,enabled,status', [(False, False, 401), (False, True, 401), (True, False, 503)])
async def test_video_auth_and_opt_in_precede_body_reads(authenticated, enabled, status):
    sent = []
    async def forbidden(*_): pytest.fail('Unavailable video must not be read')
    async def send(message): sent.append(message)
    headers = [(b'authorization', b'Bearer tenant-a-token-long-enough')] if authenticated else []
    middleware = UploadLimitMiddleware(forbidden, 16, video_upload_enabled=enabled, authenticator=MappingAuthenticator())
    await middleware({'type': 'http', 'method': 'POST', 'path': '/sources/video', 'headers': headers}, forbidden, send)
    assert sent[0]['status'] == status and b'no-store' in dict(sent[0]['headers']).values()


@pytest.mark.anyio
async def test_video_actual_bytes_timeout_disconnect_and_other_limits(monkeypatch):
    monkeypatch.setattr('app.sources.upload_limit.MAX_VIDEO_BYTES', 10)
    sent = []
    async def forbidden(*_): pytest.fail('Invalid body reached parser')
    async def send(message): sent.append(message)
    scope = {'type': 'http', 'method': 'POST', 'path': '/sources/video',
             'headers': [(b'authorization', b'Bearer tenant-a-token-long-enough'), (b'content-length', b'1')]}
    chunks = iter([{'type': 'http.request', 'body': b'x'*10000, 'more_body': True}, {'type': 'http.request', 'body': b'x'*6395}])
    async def receive(): return next(chunks)
    middleware = UploadLimitMiddleware(forbidden, 16, video_upload_enabled=True, authenticator=MappingAuthenticator(), audio_timeout=.01)
    await middleware(scope, receive, send)
    assert sent[0]['status'] == 413 and json.loads(sent[1]['body'])['code'] == 'video_too_large'
    assert not middleware.video_active
    sent.clear()
    async def slow(): await anyio.sleep(1)
    await middleware(scope, slow, send)
    assert sent[0]['status'] == 408 and not middleware.video_active
    sent.clear()
    async def disconnect(): return {'type': 'http.disconnect'}
    await middleware(scope, disconnect, send)
    assert not sent and not middleware.video_active
    for path, size in [('/sources/uploads', 17), ('/conversations', 16385), ('/sources/audio', 20_016_385)]:
        sent.clear()
        async def oversized(): return {'type': 'http.request', 'body': b'x'*size}
        other = UploadLimitMiddleware(forbidden, 16, video_upload_enabled=True, audio_upload_enabled=True, authenticator=MappingAuthenticator())
        await other({**scope, 'path': path}, oversized, send)
        assert sent[0]['status'] == 413


@pytest.mark.anyio
async def test_only_one_video_body_is_consumed_and_slot_releases_after_failure():
    entered, release = anyio.Event(), anyio.Event()
    async def app(*_):
        entered.set(); await release.wait(); raise RuntimeError('fixture failure')
    scope = {'type': 'http', 'method': 'POST', 'path': '/sources/video', 'headers': [(b'authorization', b'Bearer tenant-a-token-long-enough')]}
    middleware = UploadLimitMiddleware(app, 16, video_upload_enabled=True, authenticator=MappingAuthenticator())
    sent = []
    async def receive(): return {'type': 'http.request', 'body': b'x'}
    async def send(message): sent.append(message)
    async def first():
        with pytest.raises(RuntimeError): await middleware(scope, receive, send)
    async with anyio.create_task_group() as group:
        group.start_soon(first); await entered.wait()
        async def forbidden(): pytest.fail('Busy video body was read')
        await middleware(scope, forbidden, send)
        assert sent[0]['status'] == 429
        release.set()
    assert not middleware.video_active


def test_video_flag_is_explicit_strict_and_independent(monkeypatch):
    monkeypatch.delenv('VIDEO_UPLOAD_ENABLED', raising=False)
    assert Settings.from_env().video_upload_enabled is False
    monkeypatch.setenv('VIDEO_UPLOAD_ENABLED', 'true')
    assert Settings.from_env().video_upload_enabled is True
    monkeypatch.setenv('VIDEO_UPLOAD_ENABLED', 'perhaps')
    with pytest.raises(ValueError): Settings.from_env()
    with pytest.raises(ValueError): Settings(development_auth_token='test-development-token', video_upload_enabled='true')
