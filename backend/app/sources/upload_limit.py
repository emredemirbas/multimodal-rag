import json


class UploadLimitMiddleware:
    """Bound the wire body before multipart parsing/spooling, including chunked uploads."""

    def __init__(self, app, limit: int):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST' or not scope['path'].endswith('/sources/uploads'):
            return await self.app(scope, receive, send)
        content = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            if len(content) + len(chunk) > self.limit:
                body = json.dumps({'code': 'upload_too_large', 'detail': 'Upload a transcript of at most 2 MB.'}).encode()
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
