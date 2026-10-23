import json

import anyio
import pytest

from app.config import Settings
from app.sources.upload_limit import UploadLimitMiddleware
from conftest import MappingAuthenticator


@pytest.mark.anyio
@pytest.mark.parametrize('authenticated,enabled,status', [(False, False, 401), (False, True, 401), (True, False, 503)])
async def test_audio_is_authenticated_and_gated_before_reading_body(authenticated, enabled, status):
    sent = []
    async def forbidden(*_): pytest.fail('Disabled/unauthenticated audio must not be read or parsed')
    async def send(message): sent.append(message)
    headers = [(b'authorization', b'Bearer tenant-a-token-long-enough')] if authenticated else []
    middleware = UploadLimitMiddleware(forbidden, 16, audio_upload_enabled=enabled, authenticator=MappingAuthenticator())
    await middleware({'type': 'http', 'method': 'POST', 'path': '/api/v1/projects/x/sources/audio', 'headers': headers}, forbidden, send)
    assert sent[0]['status'] == status
    assert b'no-store' in dict(sent[0]['headers']).values()


@pytest.mark.anyio
async def test_audio_chunked_wire_bound_and_timeout_precede_multipart_parser(monkeypatch):
    monkeypatch.setattr('app.sources.upload_limit.MAX_WAV_BYTES', 10)
    scope = {'type': 'http', 'method': 'POST', 'path': '/api/v1/projects/x/sources/audio',
             'headers': [(b'authorization', b'Bearer tenant-a-token-long-enough'), (b'content-length', b'1')]}
    sent = []
    async def forbidden(*_): pytest.fail('Oversized/timed-out body must not reach the multipart parser')
    async def send(message): sent.append(message)
    chunks = iter([{'type': 'http.request', 'body': b'x' * 10_000, 'more_body': True},
                   {'type': 'http.request', 'body': b'x' * 6_395, 'more_body': False}])
    async def receive(): return next(chunks)
    middleware = UploadLimitMiddleware(forbidden, 16, audio_upload_enabled=True, authenticator=MappingAuthenticator(), audio_timeout=.01)
    await middleware(scope, receive, send)
    assert sent[0]['status'] == 413 and json.loads(sent[1]['body'])['code'] == 'audio_too_large'
    sent.clear()
    async def slow(): await anyio.sleep(1)
    await middleware(scope, slow, send)
    assert sent[0]['status'] == 408 and json.loads(sent[1]['body'])['code'] == 'audio_upload_timeout'


@pytest.mark.anyio
async def test_audio_does_not_raise_subtitle_or_chat_limits():
    for path, length in [('/sources/uploads', 17), ('/conversations', 16_385)]:
        sent = []
        async def forbidden(*_): pytest.fail('Existing limit was bypassed')
        async def receive(): return {'type': 'http.request', 'body': b'x' * length}
        async def send(message): sent.append(message)
        await UploadLimitMiddleware(forbidden, 16, audio_upload_enabled=True)(
            {'type': 'http', 'method': 'POST', 'path': path, 'headers': []}, receive, send)
        assert sent[0]['status'] == 413


def test_audio_opt_in_is_explicit_and_strict(monkeypatch):
    monkeypatch.delenv('AUDIO_UPLOAD_ENABLED', raising=False)
    assert Settings.from_env().audio_upload_enabled is False
    monkeypatch.setenv('AUDIO_UPLOAD_ENABLED', 'true')
    assert Settings.from_env().audio_upload_enabled is True
    monkeypatch.setenv('AUDIO_UPLOAD_ENABLED', 'perhaps')
    with pytest.raises(ValueError): Settings.from_env()
    with pytest.raises(ValueError): Settings(development_auth_token='test-development-token', audio_upload_enabled='true')
