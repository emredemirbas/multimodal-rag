from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread

import pytest

from app.asr.client import LocalAsrProvider, checked_asr_url
from app.asr.contracts import TranscriptionSlice
from app.asr.profile import MAX_RESPONSE_BYTES, identity
from app.asr.server import AsrServer
from app.asr.wav import MAX_PCM_BYTES
from app.sources.contracts import SourceError


def result(pcm=b"\x00\x00" * 16000, language="en"):
    return {**identity(), "input_frames": len(pcm) // 2, "requested_language": language,
        "language": "en", "language_probability": .95, "duration_ms": 12,
        "segments": [{"start_ms": 0, "end_ms": 900, "text": "GET /health is the health endpoint."}]}


@pytest.fixture
def asr_http():
    state = {"calls": [], "ready": identity(), "result": result()}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def reply(self, payload):
            self.send_response(state.get("status", 200))
            self.send_header("Content-Type", state.get("content_type", "application/json"))
            if state.get("redirect"):
                self.send_header("Location", "https://remote.invalid/transcribe")
            self.end_headers()
            self.wfile.write(state.get("raw", json.dumps(payload).encode()))
        def do_GET(self):
            state["calls"].append(self.path)
            self.reply(state["ready"])
        def do_POST(self):
            state["calls"].append(self.path)
            state["pcm"] = self.rfile.read(int(self.headers["Content-Length"]))
            state["headers"] = dict(self.headers)
            self.reply(state["result"])
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
    thread.start()
    try:
        yield LocalAsrProvider(f"http://127.0.0.1:{server.server_port}"), state
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_local_adapter_sends_pcm_only_and_never_credentials_or_proxy(asr_http, monkeypatch):
    provider, state = asr_http
    monkeypatch.setenv("HTTP_PROXY", "http://unreachable.invalid:1234")
    pcm = b"\x00\x00" * 16000
    output = provider.transcribe(pcm, "en")
    assert output.segments[0].start_ms == 0 and output.input_frames == 16000
    assert state["calls"] == ["/health/ready", "/transcribe?language=en"] and state["pcm"] == pcm
    assert "Authorization" not in state["headers"] and "X-Tenant-ID" not in state["headers"]
    assert not any(path.startswith("/api/pull") for path in state["calls"])


@pytest.mark.parametrize("patch", [{"input_frames": True}, {"input_frames": 1}, {"requested_language": "tr"},
    {"profile": "changed"}, {"revision": "a" * 40}, {"engine": "changed"}, {"provider": "paid"},
    {"duration_ms": -1}, {"language_probability": float("nan")}, {"language_probability": True},
    {"segments": [{"start_ms": 0, "end_ms": 1001, "text": "out of input"}]},
    {"segments": [{"start_ms": 0, "end_ms": 100, "text": "x"}, {"start_ms": 99, "end_ms": 200, "text": "overlap"}]},
    {"segments": [{"start_ms": 1, "end_ms": 1, "text": "empty span"}]},
    {"segments": [{"start_ms": 0, "end_ms": 100, "text": "x" * 2001}]}, {"tools": []}])
def test_unvalidated_model_text_never_crosses_provider_boundary(asr_http, patch):
    provider, state = asr_http
    state["result"].update(patch)
    with pytest.raises(SourceError) as error:
        provider.transcribe(b"\x00\x00" * 16000, "en")
    assert error.value.code == "invalid_asr_response"
    assert provider.capacity.acquire(blocking=False)
    provider.capacity.release()


def test_identity_busy_oversized_redirect_timeout_and_capacity(asr_http, monkeypatch):
    provider, state = asr_http
    state["ready"] = {**identity(), "model": "different"}
    with pytest.raises(SourceError) as error: provider.transcribe(b"\x00\x00" * 16000)
    assert error.value.code == "asr_model_changed" and state["calls"] == ["/health/ready"]
    state["ready"] = identity()
    for patch, code in [({"status": 503, "raw": b'{"code":"local_asr_busy"}'}, "local_asr_busy"),
                        ({"status": 302, "redirect": True}, "local_asr_unavailable"),
                        ({"raw": b"x" * (MAX_RESPONSE_BYTES + 1)}, "invalid_asr_response"),
                        ({"content_type": "text/html"}, "invalid_asr_response"), ({"raw": b"{"}, "invalid_asr_response")]:
        state.update(patch)
        with pytest.raises(SourceError) as error: provider.ready()
        assert error.value.code == code
        for key in patch: state.pop(key)
    state["calls"].clear()
    for pcm, language in [(b"", "en"), (b"x", "en"), (b"x" * (MAX_PCM_BYTES + 2), "en"), (b"xx", "invalid")]:
        with pytest.raises(SourceError): provider.transcribe(pcm, language)
    provider.capacity.acquire()
    with pytest.raises(SourceError) as error: provider.transcribe(b"xx")
    assert error.value.code == "local_asr_busy" and not state["calls"]
    provider.capacity.release()
    def timeout(*_, **__): raise TimeoutError("private audio and secret URL")
    monkeypatch.setattr(provider.opener, "open", timeout)
    with pytest.raises(SourceError) as error: provider.ready()
    assert error.value.code == "local_asr_unavailable" and error.value.transient
    assert "private" not in str(error.value) and error.value.__cause__ is None


def test_strict_local_url_and_silent_output_contract():
    for value in ["https://api.example.com", "http://minio:9000", "http://169.254.169.254:8090", "http://asr:1234", "http://asr:8090/path",
                  "http://user:secret@asr:8090", "http://asr:8090?key=secret", "http://asr:8090#fragment", "file:///tmp/audio", "http://localhost:80"]:
        with pytest.raises(ValueError): checked_asr_url(value)
    assert checked_asr_url("http://asr:8090/") == "http://asr:8090"
    assert TranscriptionSlice.model_validate({**result(), "segments": []}).segments == []


def test_actual_service_protocol_bounds_busy_and_private_errors(caplog):
    caplog.set_level("INFO", logger="tutorial_workspace.asr")
    def runner(pcm, language): return result(pcm, language)
    server = AsrServer(("127.0.0.1", 0), runner)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
    thread.start()
    provider = LocalAsrProvider(f"http://127.0.0.1:{server.server_port}")
    try:
        with pytest.raises(SourceError): provider.ready()
        # Test-only fixture: production sets this only after the real kernel filter.
        server.network_ready = True
        assert provider.transcribe(b"\x00\x00" * 16000, "en").segments
        server.inference_capacity.acquire()
        with pytest.raises(SourceError) as error: provider.transcribe(b"\x00\x00" * 16000)
        assert error.value.code == "local_asr_busy"
        server.inference_capacity.release()
        import http.client
        for path, data, headers, status in [("/transcribe?language=en&language=tr", b"xx", {"Content-Type": "application/octet-stream"}, 422),
            ("/transcribe?file=http://metadata.invalid", b"xx", {"Content-Type": "application/octet-stream"}, 422),
            ("/transcribe", b"x", {"Content-Type": "application/octet-stream"}, 413),
            ("/transcribe", b"xx", {"Content-Type": "audio/wav"}, 422)]:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            connection.request("POST", path, data, headers)
            response = connection.getresponse()
            assert response.status == status and response.getheader("Cache-Control") == "no-store"
            assert set(json.loads(response.read())) == {"code"}
            connection.close()
        def broken(*_): raise ValueError("private recognized text and credentials")
        server.runner = broken
        with pytest.raises(SourceError) as error: provider.transcribe(b"\x00\x00" * 16000)
        assert error.value.code == "local_asr_unavailable" and "private" not in str(error.value)
        logged = "\n".join(record.message for record in caplog.records)
        assert '"event": "asr_inference_complete"' in logged
        assert '"route": "/transcribe"' in logged
        assert "health endpoint" not in logged and "private recognized" not in logged and "metadata.invalid" not in logged
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
