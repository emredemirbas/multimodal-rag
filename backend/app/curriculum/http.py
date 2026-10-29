"""Bound curriculum JSON before parsing and keep every response private."""

import json
import re

from starlette.datastructures import Headers

from ..auth import AuthenticationError
from .contracts import MAX_DRAFT_BYTES


MAX_CONTEXT_REQUEST_BYTES = 16_384
MAX_DRAFT_REQUEST_BYTES = MAX_DRAFT_BYTES + 16_384
_PATH = re.compile(r"^/api/v1/projects/[^/]+/curriculum(?:/|$)")
_DRAFT_PATH = re.compile(r"^/api/v1/projects/[^/]+/curriculum/(?:contexts/[^/]+/drafts|drafts/[^/]+)/?$")
_PRIVATE_HEADERS = {
    b"cache-control": b"private, no-store",
    b"x-content-type-options": b"nosniff",
    b"cross-origin-resource-policy": b"same-origin",
}


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError()
        value[key] = item
    return value


def _invalid_constant(_):
    raise ValueError()


class CurriculumHttpMiddleware:
    def __init__(self, app, *, authenticator):
        self.app, self.authenticator = app, authenticator

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not _PATH.match(scope.get("path", "")):
            return await self.app(scope, receive, send)

        async def private_send(message):
            if message["type"] == "http.response.start":
                headers = [(key, value) for key, value in message.get("headers", [])
                           if key.lower() not in _PRIVATE_HEADERS]
                message = {**message, "headers": headers + list(_PRIVATE_HEADERS.items())}
            await send(message)

        async def error(status, code, detail):
            headers = [(b"content-type", b"application/json")]
            if status == 401:
                headers.append((b"www-authenticate", b"Bearer"))
            await private_send({"type": "http.response.start", "status": status, "headers": headers})
            await private_send({"type": "http.response.body",
                                "body": json.dumps({"code": code, "detail": detail}).encode()})

        if scope["method"] not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, private_send)
        try:
            self.authenticator.authenticate(Headers(scope=scope))
        except AuthenticationError as exc:
            return await error(401, exc.code, exc.detail)

        draft_request = _DRAFT_PATH.match(scope.get("path", "")) is not None
        limit = MAX_DRAFT_REQUEST_BYTES if draft_request else MAX_CONTEXT_REQUEST_BYTES
        content = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(content) + len(chunk) > limit:
                return await error(413, "curriculum_request_too_large",
                                   f"Send curriculum {'draft' if draft_request else 'context'} JSON of at most {limit} bytes.")
            content.extend(chunk)
            if not message.get("more_body", False):
                break
        try:
            value = json.loads(content, object_pairs_hook=_object, parse_constant=_invalid_constant)
            if not isinstance(value, dict):
                raise ValueError()
        except (ValueError, TypeError, RecursionError):
            return await error(422, "validation_error", "Request validation failed.")

        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(content), "more_body": False}
            return await receive()

        await self.app(scope, replay, private_send)
