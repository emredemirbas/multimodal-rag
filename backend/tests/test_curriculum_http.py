import json

import pytest

from app.curriculum.http import CurriculumHttpMiddleware, MAX_CONTEXT_REQUEST_BYTES, MAX_DRAFT_REQUEST_BYTES
from conftest import MappingAuthenticator


def scope(method="POST", *, authenticated=True):
    return {
        "type": "http", "method": method,
        "path": "/api/v1/projects/00000000-0000-0000-0000-000000000001/curriculum/contexts",
        "headers": [(b"authorization", b"Bearer tenant-a-token-long-enough")]
        if authenticated else [],
    }


def assert_private(message):
    headers = dict(message["headers"])
    assert headers[b"cache-control"] == b"private, no-store"
    assert headers[b"x-content-type-options"] == b"nosniff"
    assert headers[b"cross-origin-resource-policy"] == b"same-origin"


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH"])
async def test_authentication_precedes_curriculum_body_reads(method):
    sent = []

    async def forbidden(*_):
        pytest.fail("Unauthenticated content must not be read or parsed")

    async def send(message):
        sent.append(message)

    middleware = CurriculumHttpMiddleware(forbidden, authenticator=MappingAuthenticator())
    await middleware(scope(method, authenticated=False), forbidden, send)
    assert sent[0]["status"] == 401
    assert_private(sent[0])
    assert dict(sent[0]["headers"])[b"www-authenticate"] == b"Bearer"


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH"])
async def test_wire_limit_counts_chunks_despite_false_content_length(method):
    sent, reads = [], []
    chunks = iter([
        {"type": "http.request", "body": b"x" * MAX_CONTEXT_REQUEST_BYTES, "more_body": True},
        {"type": "http.request", "body": b"x", "more_body": True},
    ])

    async def receive():
        reads.append(True)
        return next(chunks)

    async def forbidden(*_):
        pytest.fail("Oversized content must not reach the API")

    async def send(message):
        sent.append(message)

    current_scope = scope(method)
    current_scope["headers"].append((b"content-length", b"1"))
    await CurriculumHttpMiddleware(forbidden, authenticator=MappingAuthenticator())(current_scope, receive, send)
    assert len(reads) == 2
    assert sent[0]["status"] == 413
    assert json.loads(sent[1]["body"])["code"] == "curriculum_request_too_large"
    assert_private(sent[0])


@pytest.mark.anyio
@pytest.mark.parametrize("payload", [
    b'{"secret":"PRIVATE SOURCE","secret":"another"}',
    b'{"learner":{"allow_extensions":false,"allow_extensions":true}}',
    b'{"learner":{"available_minutes":NaN}}',
    b'{"learner":{"available_minutes":Infinity}}',
    b'{"incomplete":',
    b'"\xff"',
    b"[" * 2000 + b"]" * 2000,
], ids=["duplicate-root", "duplicate-nested", "nan", "infinity", "incomplete", "encoding", "nested-array"])
async def test_ambiguous_or_invalid_json_never_reaches_api_or_error_text(payload):
    sent = []

    async def receive():
        return {"type": "http.request", "body": payload}

    async def forbidden(*_):
        pytest.fail("Invalid JSON must not reach the API")

    async def send(message):
        sent.append(message)

    await CurriculumHttpMiddleware(forbidden, authenticator=MappingAuthenticator())(scope(), receive, send)
    assert sent[0]["status"] == 422
    assert json.loads(sent[1]["body"]) == {"code": "validation_error", "detail": "Request validation failed."}
    assert b"PRIVATE" not in sent[1]["body"]
    assert_private(sent[0])


@pytest.mark.anyio
async def test_valid_body_is_replayed_unchanged_at_exact_wire_limit():
    payload = b'{"value":"' + b"x" * (MAX_CONTEXT_REQUEST_BYTES - 12) + b'"}'
    assert len(payload) == MAX_CONTEXT_REQUEST_BYTES
    chunks = iter([
        {"type": "http.request", "body": payload[:5], "more_body": True},
        {"type": "http.request", "body": payload[5:]},
        {"type": "http.disconnect"},
    ])
    sent = []

    async def receive():
        return next(chunks)

    async def app(_, read, send):
        assert await read() == {"type": "http.request", "body": payload, "more_body": False}
        assert await read() == {"type": "http.disconnect"}
        await send({"type": "http.response.start", "status": 201,
                    "headers": [(b"Cache-Control", b"public"), (b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b"{}"})

    async def send(message):
        sent.append(message)

    await CurriculumHttpMiddleware(app, authenticator=MappingAuthenticator())(scope(), receive, send)
    assert_private(sent[0])
    assert len([key for key, _ in sent[0]["headers"] if key.lower() == b"cache-control"]) == 1


@pytest.mark.anyio
async def test_disconnected_body_is_not_persisted():
    sent = []
    chunks = iter([
        {"type": "http.request", "body": b'{"partial":', "more_body": True},
        {"type": "http.disconnect"},
    ])

    async def receive():
        return next(chunks)

    async def forbidden(*_):
        pytest.fail("Disconnected partial content must not reach the API")

    async def send(message):
        sent.append(message)

    await CurriculumHttpMiddleware(forbidden, authenticator=MappingAuthenticator())(scope(), receive, send)
    assert not sent


@pytest.mark.anyio
@pytest.mark.parametrize("method,status", [("GET", 404), ("DELETE", 204), ("OPTIONS", 405)])
async def test_non_body_routes_are_private_without_reading_body(method, status):
    sent = []

    async def forbidden():
        pytest.fail("A read/delete response does not need to buffer JSON")

    async def app(_, __, send):
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def send(message):
        sent.append(message)

    await CurriculumHttpMiddleware(app, authenticator=MappingAuthenticator())(scope(method), forbidden, send)
    assert sent[0]["status"] == status
    assert_private(sent[0])


def draft_scope(method, kind):
    current = scope(method)
    project = "/api/v1/projects/00000000-0000-0000-0000-000000000001/curriculum"
    current["path"] = (project + "/contexts/00000000-0000-0000-0000-000000000002/drafts"
                       if kind == "create" else project + "/drafts/00000000-0000-0000-0000-000000000003")
    return current


@pytest.mark.anyio
@pytest.mark.parametrize("method,kind", [("POST", "create"), ("PUT", "replace")])
async def test_draft_wire_limit_replays_exact_bytes_above_context_limit(method, kind):
    payload = b'{"value":"' + b"x" * (MAX_DRAFT_REQUEST_BYTES - 12) + b'"}'
    assert MAX_CONTEXT_REQUEST_BYTES < len(payload) == MAX_DRAFT_REQUEST_BYTES
    sent = []
    chunks = iter([
        {"type": "http.request", "body": payload[:16000], "more_body": True},
        {"type": "http.request", "body": payload[16000:]},
    ])

    async def receive():
        return next(chunks)

    async def app(_, read, send):
        assert await read() == {"type": "http.request", "body": payload, "more_body": False}
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    async def send(message):
        sent.append(message)

    await CurriculumHttpMiddleware(app, authenticator=MappingAuthenticator())(draft_scope(method, kind), receive, send)
    assert_private(sent[0])


@pytest.mark.anyio
@pytest.mark.parametrize("method,kind", [("POST", "create"), ("PUT", "replace")])
async def test_draft_wire_limit_rejects_overflow_before_parser(method, kind):
    sent = []
    chunks = iter([
        {"type": "http.request", "body": b"x" * MAX_DRAFT_REQUEST_BYTES, "more_body": True},
        {"type": "http.request", "body": b"x", "more_body": True},
    ])

    async def receive():
        return next(chunks)

    async def forbidden(*_):
        pytest.fail("Over-limit draft must not reach the API")

    async def send(message):
        sent.append(message)

    current = draft_scope(method, kind)
    current["headers"].append((b"content-length", b"1"))
    await CurriculumHttpMiddleware(forbidden, authenticator=MappingAuthenticator())(current, receive, send)
    assert sent[0]["status"] == 413
    assert json.loads(sent[1]["body"])["code"] == "curriculum_request_too_large"
    assert_private(sent[0])


@pytest.mark.anyio
async def test_draft_authentication_precedes_even_large_body_reads():
    sent = []

    async def forbidden(*_):
        pytest.fail("Unauthenticated draft body must not be read")

    async def send(message):
        sent.append(message)

    current = draft_scope("PUT", "replace")
    current["headers"] = []
    await CurriculumHttpMiddleware(forbidden, authenticator=MappingAuthenticator())(current, forbidden, send)
    assert sent[0]["status"] == 401
    assert_private(sent[0])
