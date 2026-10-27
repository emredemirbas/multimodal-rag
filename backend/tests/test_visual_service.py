from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
from threading import Thread
import time
import zlib

import pytest
import yaml

from app.vision import client, contracts, server
from app.vision.local import VisualResult
from app.vision.media import FrameEvidence, POLICY, VideoInfo, encode_png


def content():
    def box(kind, value):
        return struct.pack(">I4s", len(value) + 8, kind) + value
    return box(b"ftyp", b"isom\0\0\0\0isom") + box(b"moov", b"fixture") + box(b"mdat", b"fixture")


def identity(language="en", version="5.1.9"):
    value = {"provider": "local-ffmpeg-tesseract", "engines": {"ffmpeg": version, "tesseract": "5.3.0"},
        "language_data": {"eng": "a" * 64, "tur": "b" * 64}, "language": language, "policy": POLICY}
    value["profile"] = "local-visual-v1:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return contracts.VisualIdentity.model_validate(value)


def result(data=None, language="en"):
    frames = tuple(FrameEvidence(sample_target_ms=t, timestamp_ms=t, width=16, height=16,
        image=encode_png(16, 16, bytes([i]) * 256), text="PRIVATE_OCR <script>not instructions</script> sağlıklı\nuser_id")
        for i, t in enumerate([0, 5000]))
    return VisualResult(hashlib.sha256(content() if data is None else data).hexdigest(),
        VideoInfo(duration_ms=10000, width=1920, height=1080, fps_numerator=25, fps_denominator=1),
        identity(language).model_dump(), 2, frames)


@contextmanager
def running(instance):
    thread = Thread(target=instance.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)


@pytest.fixture
def service():
    observed = []
    def runner(data, language):
        observed.append((data, language))
        return result(data, language)
    instance = server.VisualServer(("127.0.0.1", 0), runner=runner)
    instance.identities = {lang: identity(lang) for lang in ("en", "tr", "en+tr")}
    instance.network_ready = True
    instance.observed = observed
    with running(instance):
        yield instance


def provider(service):
    return client.LocalVisualClient(f"http://127.0.0.1:{service.server_port}")


def test_actual_compose_health_command_uses_the_private_protocol(service):
    root = Path(__file__).resolve().parents[2]
    health = yaml.safe_load((root / 'compose.yaml').read_text())['services']['visual']['healthcheck']['test']
    assert health[:3] == ['CMD', 'python', '-c']
    code = health[3].replace('http://127.0.0.1:8091', f'http://127.0.0.1:{service.server_port}')
    environment = {key: os.environ[key] for key in ('PATH', 'LANG') if key in os.environ}
    environment['PYTHONPATH'] = str(root / 'backend')
    completed = subprocess.run([sys.executable, '-c', code], env=environment, capture_output=True, timeout=8)
    assert completed.returncode == 0, 'The actual Compose health command violates the private protocol'
    assert not service.observed  # No native work or input involved in health.


def request(service, *, path="/extract?language=en", headers=None, body=None, method="POST"):
    data = content() if body is None else body
    base = {"Content-Type": "application/octet-stream", "X-Visual-Profile": identity().profile,
            "X-Input-SHA256": hashlib.sha256(data).hexdigest()}
    base.update(headers or {})
    connection = HTTPConnection("127.0.0.1", service.server_port, timeout=2)
    try:
        connection.request(method, path, body=data, headers=base)
        with connection.getresponse() as response:
            return response.status, json.loads(response.read())
    finally:
        connection.close()


@pytest.mark.parametrize("language", ["en", "tr", "en+tr"])
def test_real_http_roundtrip_literal_evidence_and_content_free_logs(service, language, caplog):
    caplog.set_level("INFO", logger="tutorial_workspace.visual")
    remote = provider(service)
    pinned = remote.ready(language)
    extracted = remote.extract(content(), expected_identity=pinned)
    assert extracted == result(language=language)
    assert service.observed == [(content(), language)]
    assert "PRIVATE_OCR" not in caplog.text and "user_id" not in caplog.text
    assert "PRIVATE_OCR" not in repr(extracted)
    assert "visual_extraction_complete" in caplog.text


def test_pinned_profile_and_input_drift_fail_without_adoption(service):
    remote = provider(service)
    with pytest.raises(client.VisualError) as failure:
        remote.extract(content(), expected_identity=identity(version="5.1.10"))
    assert failure.value.code == "visual_profile_changed" and not failure.value.transient
    assert not service.observed
    assert request(service, headers={"X-Visual-Profile": identity(version="5.1.10").profile})[0] == 409
    assert request(service, headers={"X-Input-SHA256": "c" * 64})[0] == 422
    assert not service.observed


def test_server_busy_and_failure_release_capacity_and_no_provider_retry(service, caplog):
    remote = provider(service)
    service.capacity.acquire()
    try:
        with pytest.raises(client.VisualError) as failure:
            remote.extract(content(), expected_identity=identity())
        assert failure.value.code == "local_visual_busy" and failure.value.transient
    finally:
        service.capacity.release()
    def broken(*_):
        service.observed.append("one failure")
        raise RuntimeError("PRIVATE_NATIVE_ERROR /private/path")
    original = service.runner
    service.runner = broken
    with pytest.raises(client.VisualError) as failure:
        remote.extract(content(), expected_identity=identity())
    assert failure.value.code == "local_visual_unavailable" and failure.value.transient
    assert service.observed == ["one failure"]
    assert "PRIVATE_NATIVE_ERROR" not in caplog.text
    service.runner = original
    assert remote.extract(content(), expected_identity=identity()).candidates == 2
    remote.capacity.acquire()
    try:
        with pytest.raises(client.VisualError, match="local_visual_busy"):
            remote.extract(content(), expected_identity=identity())
    finally:
        remote.capacity.release()


@pytest.mark.parametrize("headers,body,path,status", [
    ({"Content-Type": "text/plain"}, None, "/extract", 422),
    ({"Content-Encoding": "gzip"}, None, "/extract", 422),
    ({"Transfer-Encoding": "chunked"}, None, "/extract", 422),
    ({"Expect": "100-continue"}, None, "/extract", 422),
    ({"Authorization": "PRIVATE_CREDENTIAL"}, None, "/extract", 422),
    ({"X-Project-ID": "private-project"}, None, "/extract", 422),
    ({"Content-Length": "100000001"}, None, "/extract", 413),
    ({"Content-Length": "-1"}, None, "/extract", 422),
    ({"Content-Length": "0"}, None, "/extract", 413),
    ({"X-Input-SHA256": "X" * 64}, None, "/extract", 422),
    ({}, b"PRIVATE_INVALID_MEDIA" * 2, "/extract", 422),
    ({}, None, "/extract?language=en&language=tr", 422),
    ({}, None, "/extract?language=auto", 422),
    ({}, None, "/extract?language=en+tr&path=/private", 422),
    ({}, None, "/extract?language=", 422),
    ({}, None, "/extract?url=http://169.254.169.254", 422),
    ({}, None, "/private/PRIVATE_PATH", 404),
])
def test_http_rejects_before_native_and_no_content_echo(service, headers, body, path, status, caplog):
    received_status, document = request(service, headers=headers, body=body, path=path)
    assert received_status == status
    assert not service.observed
    assert "PRIVATE" not in json.dumps(document) + caplog.text


def test_duplicate_headers_and_missing_length_rejected(service):
    for field in ["Content-Length", "Content-Type", "X-Visual-Profile", "X-Input-SHA256", None]:
        headers = {"Content-Type": "application/octet-stream", "X-Visual-Profile": identity().profile,
            "X-Input-SHA256": hashlib.sha256(content()).hexdigest()}
        if field is not None:
            headers["Content-Length"] = str(len(content()))
        lines = ["POST /extract HTTP/1.1", "Host: localhost"] + [f"{k}: {v}" for k, v in headers.items()]
        if field is not None:
            lines.append(f"{field}: {headers[field]}")
        with socket.create_connection(("127.0.0.1", service.server_port), timeout=2) as sock:
            sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode() + content())
            assert b"422" in sock.recv(4096).split(b"\r\n", 1)[0]
    assert not service.observed


def test_unready_and_unknown_method_are_safe(service):
    service.network_ready = False
    remote = provider(service)
    with pytest.raises(client.VisualError, match="local_visual_unavailable"):
        remote.ready()
    assert request(service)[0] == 503
    assert request(service, method="DELETE", path="/PRIVATE_PATH")[0] == 501


@pytest.mark.parametrize("partial", [b"POST /extract HTTP/1.1\r\nX-Private: ", b"body"])
def test_absolute_read_deadline_frees_capacity_even_with_trickling_input(service, monkeypatch, partial):
    monkeypatch.setattr(server, "READ_SECONDS", .15)
    with socket.create_connection(("127.0.0.1", service.server_port), timeout=2) as sock:
        if partial == b"body":
            lines = ["POST /extract HTTP/1.1", "Host: localhost", "Content-Length: 1000",
                "Content-Type: application/octet-stream", f"X-Visual-Profile: {identity().profile}",
                "X-Input-SHA256: " + "a" * 64, "", ""]
            sock.sendall("\r\n".join(lines).encode())
        else:
            sock.sendall(partial)
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            try:
                sock.sendall(b"x")
            except OSError:
                break
            time.sleep(.03)
        assert sock.recv(4096) == b""
    assert not service.observed
    assert provider(service).extract(content(), expected_identity=identity()).candidates == 2


def test_wire_roundtrip_and_no_sensitive_repr():
    wire = contracts.WireResult.from_result(result())
    data = contracts.encode_wire(wire)
    assert "PRIVATE_OCR" not in repr(wire) + repr(wire.frames[0])
    assert contracts.WireResult.model_validate(contracts.decode_wire(data)).result() == result()


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(input_sha256="bad"),
    lambda d: d.update(candidates=1),
    lambda d: d.update(candidates=True),
    lambda d: d.update(frames=[]),
    lambda d: d.update(frames=d["frames"] * 11),
    lambda d: d.update(frames=list(reversed(d["frames"]))),
    lambda d: d["frames"][0].update(timestamp_ms=1001),
    lambda d: d["frames"][1].update(sample_target_ms=4999),
    lambda d: d["frames"][0].update(image_sha256="f" * 64),
    lambda d: d["frames"][0].update(width=17),
    lambda d: d["frames"][0].update(image_base64="\n"),
    lambda d: d["frames"][0].update(text="PRIVATE\0TEXT"),
    lambda d: d["frames"][0].update(text="x" * 16001),
    lambda d: d["frames"][0].update(text="\ud800"),
    lambda d: d["frames"][0].update(path="/private"),
    lambda d: d["video"].update(fps_numerator=61),
    lambda d: d["identity"]["engines"].update(ffmpeg="5.1.10"),
    lambda d: d["identity"].update(provider="cloud"),
    lambda d: d["identity"]["language_data"].update(eng="g" * 64),
    lambda d: d["identity"].update(language="auto"),
    lambda d: d.update(unexpected=True),
])
def test_malformed_wire_evidence_is_rejected(mutate):
    document = contracts.WireResult.from_result(result()).model_dump()
    mutate(document)
    with pytest.raises(ValueError):
        contracts.WireResult.model_validate(document)


def test_duplicate_decoded_pixels_rejected_even_if_png_encoding_differs():
    document = contracts.WireResult.from_result(result()).model_dump()
    original = encode_png(16, 16, b"\0" * 256)
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    png = original[:33] + chunk(b"IDAT", zlib.compress(b"\0" * 272, 0)) + chunk(b"IEND", b"")
    assert png != original and contracts.checked_png(png, 16, 16) == b"\0" * 256
    second = document["frames"][1]
    second.update(image_base64=base64.b64encode(png).decode(), image_sha256=hashlib.sha256(png).hexdigest())
    with pytest.raises(ValueError, match="Duplicate decoded frame"):
        contracts.WireResult.model_validate(document)


def test_png_rejects_crc_trailing_data_wrong_filter_and_bounded_decompression():
    png = encode_png(16, 16, b"\0" * 256)
    for changed in [png[:-1], png + b"private", png[:40] + bytes([png[40] ^ 1]) + png[41:]]:
        with pytest.raises(ValueError):
            contracts.checked_png(changed, 16, 16)
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    for data in [b"\1" + b"\0" * 271, b"x" * 2_000_000, b"\0" * 272 + b"extra"]:
        bad = png[:33] + chunk(b"IDAT", zlib.compress(data)) + chunk(b"IEND", b"")
        with pytest.raises(ValueError):
            contracts.checked_png(bad, 16, 16)
    malformed = png[:33] + chunk(b"IDAT", b"PRIVATE_INVALID_DEFLATE") + chunk(b"IEND", b"")
    with pytest.raises(ValueError, match="compressed frame"):
        contracts.checked_png(malformed, 16, 16)
    with pytest.raises(ValueError):
        contracts.decode_wire(b'{"frames": [], "frames": []}')
    with pytest.raises(ValueError):
        contracts.decode_wire(b'{"value":NaN}')


@pytest.mark.parametrize("url", ["https://visual:8091", "http://visual:80", "http://asr:8090", "http://evil.test:8091",
    "http://169.254.169.254:8091", "http://127.1:8091", "http://127.0.0.1", "http://user:secret@visual:8091",
    "http://visual:8091/extract", "http://visual:8091?url=x", "http://visual:8091#fragment", "http://visual:8091\n", None])
def test_client_url_allowlist(url):
    with pytest.raises(ValueError):
        client.LocalVisualClient(url)


def test_client_rejects_before_network_and_validates_identity_input_response_binding(monkeypatch):
    remote = client.LocalVisualClient()
    calls = []
    def fake(path, **kwargs):
        calls.append(path)
        return identity().model_dump() if path.startswith("/health") else contracts.WireResult.from_result(result(b"different bytes")).model_dump()
    monkeypatch.setattr(remote, "_request", fake)
    with pytest.raises(client.VisualError, match="invalid_visual_request"):
        remote.extract(b"bad", expected_identity=identity())
    with pytest.raises(client.VisualError, match="invalid_visual_request"):
        remote.ready("de")
    assert not calls
    with pytest.raises(client.VisualError, match="invalid_visual_response"):
        remote.extract(content(), expected_identity=identity())
    assert len(calls) == 2


@pytest.mark.parametrize("mode", ["redirect", "type", "oversize", "duplicate", "short", "encoding", "private_error"])
def test_actual_http_client_rejects_bad_responses_without_proxy_redirect_or_echo(monkeypatch, mode):
    hits = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            hits.append(self.path)
            data = contracts.encode_wire(identity())
            if mode == "duplicate":
                data = b'{"provider": "private", "provider": "private"}'
            elif mode == "private_error":
                data = b'{"code": "PRIVATE_ERROR", "private": "PRIVATE_OCR"}'
            self.send_response(302 if mode == "redirect" else 503 if mode == "private_error" else 200)
            self.send_header("Location", "http://169.254.169.254/private")
            self.send_header("Content-Type", "text/plain" if mode == "type" else "application/json")
            self.send_header("Content-Length", "18000001" if mode == "oversize" else str(len(data) + (1 if mode == "short" else 0)))
            if mode == "encoding":
                self.send_header("Content-Encoding", "gzip")
            self.end_headers()
            self.wfile.write(data)
    monkeypatch.setenv("HTTP_PROXY", "http://169.254.169.254/private")
    monkeypatch.setenv("ALL_PROXY", "http://169.254.169.254/private")
    with running(ThreadingHTTPServer(("127.0.0.1", 0), Handler)) as instance:
        with pytest.raises(client.VisualError) as failure:
            client.LocalVisualClient(f"http://127.0.0.1:{instance.server_port}").ready()
        assert len(hits) == 1 and "PRIVATE" not in str(failure.value)


def test_server_wrong_runner_identity_or_input_is_not_returned(service):
    for changed in [VisualResult("c" * 64, result().info, result().identity, 2, result().frames),
                    VisualResult(result().input_sha256, result().info, identity(version="5.1.10").model_dump(), 2, result().frames)]:
        service.runner = lambda *_, value=changed: value
        status, document = request(service)
        assert status == 503 and document == {"code": "local_visual_unavailable"}


@pytest.mark.parametrize("phase", ["headers", "body"])
def test_client_absolute_deadline_stops_trickling_response(monkeypatch, phase):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            data = contracts.encode_wire(identity())
            try:
                if phase == "headers":
                    for value in b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n":
                        self.connection.sendall(bytes([value]))
                        time.sleep(.02)
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    for value in data:
                        self.wfile.write(bytes([value]))
                        time.sleep(.02)
            except OSError:
                pass
    monkeypatch.setattr(client, "READY_SECONDS", .15)
    with running(ThreadingHTTPServer(("127.0.0.1", 0), Handler)) as instance:
        started = time.monotonic()
        with pytest.raises(client.VisualError) as failure:
            client.LocalVisualClient(f"http://127.0.0.1:{instance.server_port}").ready()
        assert time.monotonic() - started < 1.5
        assert failure.value.code in {"local_visual_unavailable", "invalid_visual_response"}


def test_startup_binds_then_verifies_inherited_denial_before_readiness(monkeypatch):
    events = []
    class Stub:
        network_ready = False
        def serve_forever(self): events.append(("serve", self.network_ready))
        def server_close(self): events.append("closed")
    instance = Stub()
    monkeypatch.setattr(server, "VisualServer", lambda address: events.append(("bind", address)) or instance)
    monkeypatch.setattr(server, "block_outbound_sockets", lambda: events.append("filter"))
    monkeypatch.setattr(server, "require_isolation", lambda: events.append("parent_probe"))
    monkeypatch.setattr(server, "verify_child_isolation", lambda: events.append("child_probe"))
    monkeypatch.setattr(server, "runtime_identity", lambda runner, language, selection='uniform': identity(language).model_dump())
    server.main()
    assert events == [("bind", ("0.0.0.0", 8091)), "filter", "parent_probe", "child_probe", ("serve", True), "closed"]


def test_fresh_child_probe_filters_environment_and_fails_closed(monkeypatch):
    observed = {}
    class Probe:
        returncode = 0
    def run(args, **kwargs):
        observed.update(args=args, **kwargs)
        return Probe()
    monkeypatch.setattr(server.subprocess, "run", run)
    monkeypatch.setenv("DATABASE_URL", "PRIVATE")
    server.verify_child_isolation()
    assert set(observed["env"]) == {"PATH", "PYTHONDONTWRITEBYTECODE"}
    assert observed["timeout"] == 5 and observed["stderr"] == subprocess.DEVNULL
    Probe.returncode = 1
    with pytest.raises(RuntimeError, match="isolation"):
        server.verify_child_isolation()


def test_connection_limit_rejects_fifth_socket_and_recovers(service):
    sockets = []
    try:
        for _ in range(4):
            sock = socket.create_connection(("127.0.0.1", service.server_port), timeout=2)
            sockets.append(sock)
            sock.sendall(b"GET /health/ready HTTP/1.1\r\nHost: ")
        deadline = time.monotonic() + 1
        while service.connections._value != 0 and time.monotonic() < deadline:
            time.sleep(.005)
        assert service.connections._value == 0
        with socket.create_connection(("127.0.0.1", service.server_port), timeout=2) as fifth:
            assert fifth.recv(1) == b""
    finally:
        for sock in sockets:
            sock.close()
    deadline = time.monotonic() + 1
    while service.connections._value != 4 and time.monotonic() < deadline:
        time.sleep(.005)
    assert service.connections._value == 4
    assert provider(service).ready() == identity()


def test_missing_kernel_filter_closes_listener_without_readiness(monkeypatch):
    class Stub:
        network_ready = False
        closed = False
        def server_close(self): self.closed = True
        def serve_forever(self): pytest.fail("must not become ready")
    instance = Stub()
    monkeypatch.setattr(server, "VisualServer", lambda address: instance)
    def unavailable():
        raise RuntimeError("kernel filter unavailable")
    monkeypatch.setattr(server, "block_outbound_sockets", unavailable)
    with pytest.raises(RuntimeError):
        server.main()
    assert instance.closed and not instance.network_ready
