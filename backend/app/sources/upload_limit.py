import json


class UploadLimitMiddleware:
    """Bound the wire body before multipart parsing/spooling, including chunked uploads."""

    def __init__(self, app, limit: int):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        is_upload = scope['type'] == 'http' and scope['path'].endswith('/sources/uploads')
        is_chat = scope['type'] == 'http' and '/conversations' in scope['path']
        if scope['type'] != 'http' or scope['method'] != 'POST' or not (is_upload or is_chat):
            return await self.app(scope, receive, send)
        limit = self.limit if is_upload else 16_384
        content = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            if len(content) + len(chunk) > limit:
                body = json.dumps({'code': 'upload_too_large' if is_upload else 'message_too_large',
                                   'detail': 'Upload a transcript of at most 2 MB.' if is_upload else 'Send a question of at most 2000 characters.'}).encode()
                await send({'type': 'http.response.start', 'status': 413, 'headers': [(b'content-type', b'application/json')]})
                await send({'type': 'http.response.body', 'body': body})
                return
            content.extend(chunk)
            if not message.get('more_body', False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(content), 'more_body': False}
            return await receive()

        await self.app(scope, replay, send)
