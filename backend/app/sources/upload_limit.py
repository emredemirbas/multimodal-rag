import json

import anyio
from starlette.datastructures import Headers

from ..auth import AuthenticationError
from ..asr.wav import MAX_WAV_BYTES


class UploadLimitMiddleware:
    """Bound the wire body before multipart parsing/spooling, including chunked uploads."""

    def __init__(self, app, limit: int, *, audio_upload_enabled: bool = False, authenticator=None, audio_timeout: float = 30):
        self.app, self.limit = app, limit
        self.audio_upload_enabled, self.authenticator, self.audio_timeout = audio_upload_enabled, authenticator, audio_timeout

    @staticmethod
    async def error(send, status, code, detail):
        headers = [(b'content-type', b'application/json'), (b'cache-control', b'no-store')]
        if status == 401:
            headers.append((b'www-authenticate', b'Bearer'))
        await send({'type': 'http.response.start', 'status': status, 'headers': headers})
        await send({'type': 'http.response.body', 'body': json.dumps({'code': code, 'detail': detail}).encode()})

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '').rstrip('/')
        is_upload = scope['type'] == 'http' and path.endswith('/sources/uploads')
        is_audio = scope['type'] == 'http' and path.endswith('/sources/audio')
        is_chat = scope['type'] == 'http' and '/conversations' in scope['path']
        if scope['type'] != 'http' or scope['method'] != 'POST' or not (is_upload or is_audio or is_chat):
            return await self.app(scope, receive, send)
        if is_audio:
            try:
                if self.authenticator is None:
                    raise AuthenticationError()
                self.authenticator.authenticate(Headers(scope=scope))
            except AuthenticationError as error:
                return await self.error(send, 401, error.code, error.detail)
            if not self.audio_upload_enabled:
                return await self.error(send, 503, 'audio_upload_disabled', 'Local audio upload is not enabled. Use an authorized SRT/VTT transcript.')
        limit = MAX_WAV_BYTES + 16_384 if is_audio else self.limit if is_upload else 16_384
        code = 'audio_too_large' if is_audio else 'upload_too_large' if is_upload else 'message_too_large'
        detail = ('Upload a WAV file of at most 20 MB.' if is_audio else
                  'Upload a transcript of at most 2 MB.' if is_upload else 'Send a question of at most 2000 characters.')
        content = bytearray()

        async def read():
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return False
                chunk = message.get('body', b'')
                if len(content) + len(chunk) > limit:
                    await self.error(send, 413, code, detail)
                    return False
                content.extend(chunk)
                if not message.get('more_body', False):
                    return True

        try:
            with anyio.fail_after(self.audio_timeout if is_audio else None):
                if not await read():
                    return
        except TimeoutError:
            return await self.error(send, 408, 'audio_upload_timeout', 'Audio upload timed out; resend the same request key to recover safely.')
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(content), 'more_body': False}
            return await receive()

        await self.app(scope, replay, send)
