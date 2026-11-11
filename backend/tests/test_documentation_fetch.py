"""Authored HTML, mocked DNS/TLS and local HTTP; no external documentation fetch."""

from dataclasses import asdict, replace
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import socket
import ssl
import subprocess
import sys
from threading import Thread
from time import sleep

from pydantic import ValidationError
import pytest

from app.curriculum import documentation_fetch as fetch


CATALOG_ID = "fastapi-first-steps-en"
HTML = (b'<!doctype html><html><head><title>Not evidence</title></head><body>'
        b'<nav>PRIVATE unrelated navigation</nav><article class="md-content__inner md-typeset">'
        b'<h1>First steps</h1><p>Create an <strong>API</strong> &amp; inspect it.</p>'
        b'<pre><code>from fastapi import FastAPI\n\napp = FastAPI()\n'
        b'    # preserve indentation\n</code></pre>'
        b'<script>PRIVATE malicious instructions</script><style>PRIVATE CSS</style>'
        b'<button>PRIVATE clipboard</button><template>PRIVATE template</template>'
        b'<iframe src="https://PRIVATE.invalid/">PRIVATE frame</iframe>'
        b'<div hidden>PRIVATE hidden</div><p aria-hidden="true">PRIVATE aria</p>'
        b'<aside>PRIVATE sidebar</aside><p>Then inspect <code>/docs</code>.</p>'
        b'</article><footer>PRIVATE footer</footer></body></html>')


def captured(**changes):
    text = "Synthetic official documentation text."
    values = dict(catalog_id=CATALOG_ID, parser_version=fetch.get_document(CATALOG_ID).parser_version,
                  text=text, content_sha256=sha256(text.encode()).hexdigest(), raw_sha256="a" * 64,
                  raw_bytes=100, detected_version=None)
    values.update(changes)
    return fetch.FetchedDocument(**values)


@pytest.fixture
def document_server(monkeypatch):
    state = {"requests": [], "headers": [("Content-Type", "text/html; charset=utf-8")],
             "body": HTML, "status": 200, "tls": []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            state["requests"].append((self.path, dict(self.headers)))
            try:
                if state.get("slow_headers"):
                    response = (b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nX-Synthetic-Padding: "
                                + b"x" * 1024 + b"\r\n\r\n" + HTML)
                    for byte in response:
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                        sleep(.01)
                    return
                if state.get("raw") is not None:
                    self.wfile.write(state["raw"])
                    return
                self.send_response(state["status"])
                for name, value in state["headers"]:
                    self.send_header(name, value)
                self.end_headers()
                if state.get("slow_body"):
                    for byte in state["body"]:
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                        sleep(.01)
                else:
                    self.wfile.write(state["body"])
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
    thread.start()
    state["port"] = server.server_port

    class FixtureTLS:
        def wrap_socket(self, stream, *, server_hostname):
            state["tls"].append(server_hostname)
            return stream

    # These are test-only patches, never a runtime constructor or environment escape.
    monkeypatch.setattr(fetch, "_public_addresses", lambda host: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", server.server_port))])
    monkeypatch.setattr(fetch.ssl, "create_default_context", lambda: FixtureTLS())
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_catalog_exact_policy_fingerprint_and_full_license():
    documents = fetch.catalog_documents()
    assert len(documents) == 1 and isinstance(documents, tuple)
    document = fetch.get_document(CATALOG_ID)
    assert document is documents[0]
    assert document.url == "https://fastapi.tiangolo.com/tutorial/first-steps/"
    assert document.license_name == "MIT" and "Copyright (c) 2018 Sebastián Ramírez" in document.license_text
    assert document.license_text.endswith("THE SOFTWARE.\n")
    assert "Permission is hereby granted" in document.license_text and "AS IS" in document.license_text
    assert document.license_url == "https://github.com/fastapi/fastapi/blob/master/LICENSE"
    raw = json.dumps(asdict(document), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert document.fingerprint == sha256(raw).hexdigest()
    assert replace(document, parser_version="changed-v2").fingerprint != document.fingerprint
    with pytest.raises((AttributeError, TypeError)):
        document.url = "https://PRIVATE.invalid/"


@pytest.mark.parametrize("identifier", [None, True, 1, [], "", "FASTAPI-FIRST-STEPS-EN", "../fastapi-first-steps-en",
                                       CATALOG_ID + "?fetch=1", "https://fastapi.tiangolo.com/tutorial/first-steps/",
                                       "https://user:PRIVATE@fastapi.tiangolo.com/tutorial/first-steps/",
                                       "http://127.0.0.1", "https://169.254.169.254/latest/meta-data/"])
def test_unapproved_identifier_never_starts_child(monkeypatch, identifier):
    monkeypatch.setattr(fetch.subprocess, "run", lambda *a, **k: pytest.fail("No child for unsupported ID"))
    with pytest.raises(fetch.DocumentationFetchError) as error:
        fetch.OfficialDocumentationFetcher().fetch(identifier)
    assert error.value.code == "documentation_fetch_not_allowed" and not error.value.retryable
    assert "PRIVATE" not in str(error.value)


def test_inert_main_text_pre_whitespace_and_utf8_hashes(document_server, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://PRIVATE.invalid:9")
    monkeypatch.setenv("ALL_PROXY", "http://PRIVATE.invalid:9")
    # Numeric socket connection must not perform a second name lookup.
    monkeypatch.setattr(fetch.socket, "getaddrinfo", lambda *a, **k: pytest.fail("DNS must stay pinned"))
    result = fetch._capture(CATALOG_ID)
    assert result.text == ("First steps\n\nCreate an API & inspect it.\n\n"
                           "from fastapi import FastAPI\n\napp = FastAPI()\n    # preserve indentation\n"
                           "\n\nThen inspect /docs.")
    assert "PRIVATE" not in result.text and "PRIVATE" not in repr(result)
    assert result.raw_sha256 == sha256(HTML).hexdigest() and result.raw_bytes == len(HTML)
    assert result.content_sha256 == sha256(result.text.encode()).hexdigest()
    assert result.detected_version is None
    assert document_server["tls"] == ["fastapi.tiangolo.com"]
    assert len(document_server["requests"]) == 1
    path, headers = document_server["requests"][0]
    assert path == "/tutorial/first-steps/" and headers["Host"] == "fastapi.tiangolo.com"
    assert headers["Accept-Encoding"] == "identity" and headers["Connection"] == "close"
    assert not {"Authorization", "Cookie", "Proxy-Authorization"} & headers.keys()


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.2.3", "172.16.0.2", "192.168.1.2",
                                    "169.254.169.254", "100.64.0.1", "192.0.0.8", "192.0.2.1", "0.0.0.0",
                                    "224.0.0.1", "240.0.0.1", "::1", "::", "fe80::1", "fc00::1",
                                    "ff02::1", "2001:db8::1", "::ffff:127.0.0.1", "::ffff:93.184.216.34",
                                    "2002:7f00:1::", "64:ff9b::7f00:1", "fe80::1%eth0"])
def test_all_nonpublic_and_transition_dns_answers_rejected(monkeypatch, address):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    record = (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))
    monkeypatch.setattr(fetch.socket, "getaddrinfo", lambda *a: [record])
    with pytest.raises(fetch.DocumentationFetchError) as error:
        fetch._public_addresses("fastapi.tiangolo.com")
    assert error.value.code == "documentation_fetch_not_allowed"


def test_mixed_public_private_dns_rejected_before_socket(monkeypatch):
    good = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))
    bad = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443))
    monkeypatch.setattr(fetch.socket, "getaddrinfo", lambda *a: [good, bad])
    monkeypatch.setattr(fetch.socket, "socket", lambda *a: pytest.fail("No connection to mixed DNS"))
    with pytest.raises(fetch.DocumentationFetchError):
        fetch._capture(CATALOG_ID)


def test_public_dns_resolved_once_and_tls_defaults_verify(monkeypatch):
    answers = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443)),
               (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("2606:4700::1111", 443))]
    calls = []
    def resolve(*args):
        calls.append(args)
        return answers
    monkeypatch.setattr(fetch.socket, "getaddrinfo", resolve)
    assert fetch._public_addresses("fastapi.tiangolo.com") == answers
    assert calls == [("fastapi.tiangolo.com", 443, socket.AF_UNSPEC, socket.SOCK_STREAM, socket.IPPROTO_TCP)]
    connection = fetch._PinnedConnection("fastapi.tiangolo.com", answers[0])
    assert connection._context.check_hostname and connection._context.verify_mode == ssl.CERT_REQUIRED


@pytest.mark.parametrize("records", [[], [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 80))],
                                    [(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP, "", ("93.184.216.34", 443))]])
def test_empty_or_non_tcp_dns_rejected(monkeypatch, records):
    monkeypatch.setattr(fetch.socket, "getaddrinfo", lambda *a: records)
    with pytest.raises(fetch.DocumentationFetchError):
        fetch._public_addresses("fastapi.tiangolo.com")


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirects_never_followed_even_same_host(document_server, status):
    document_server.update(status=status, headers=[("Location", "https://fastapi.tiangolo.com/other/")])
    with pytest.raises(fetch.DocumentationFetchError) as error:
        fetch._capture(CATALOG_ID)
    assert error.value.code == "documentation_fetch_not_allowed" and not error.value.retryable
    assert len(document_server["requests"]) == 1


@pytest.mark.parametrize("headers", [[], [("Content-Type", "application/json")],
    [("Content-Type", "text/html"), ("Content-Type", "text/html")],
    [("Content-Type", "text/html; charset=latin1")], [("Content-Type", "text/html; charset=utf-8; charset=utf-8")],
    [("Content-Encoding", "gzip")], [("Content-Encoding", "identity"), ("Content-Encoding", "identity")],
    [("Content-Length", "1"), ("Content-Length", "1")], [("Content-Length", "1, 1")],
    [("Content-Length", "-1")], [("Content-Length", "+1")], [("Content-Length", "0")],
    [("Content-Length", "9999999999999999999999999")], [("Content-Length", "512001")],
    [("Content-Length", "2"), ("Transfer-Encoding", "chunked")],
    [("Transfer-Encoding", "gzip")], [("Transfer-Encoding", "chunked"), ("Transfer-Encoding", "chunked")]])
def test_response_type_encoding_and_framing_rejected(document_server, headers):
    if not any(name.lower() == "content-type" for name, _ in headers) and headers:
        headers = [("Content-Type", "text/html; charset=utf-8")] + headers
    document_server["headers"] = headers
    with pytest.raises(fetch.DocumentationFetchError) as error:
        fetch._capture(CATALOG_ID)
    assert error.value.code == "documentation_fetch_invalid"


@pytest.mark.parametrize("status,retryable", [(204, False), (206, False), (400, False), (401, False),
                                           (404, False), (408, True), (429, True), (500, True), (503, True)])
def test_http_failure_has_safe_bounded_error(document_server, status, retryable):
    document_server["status"] = status
    with pytest.raises(fetch.DocumentationFetchError) as error:
        fetch._capture(CATALOG_ID)
    assert error.value.code == "documentation_fetch_unavailable" and error.value.retryable is retryable
    assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("case", ["large-body", "truncated", "large-header", "many-headers", "chunked-bad", "chunked-trailer"])
def test_wire_resource_bounds(document_server, case):
    if case == "large-body":
        document_server["body"] = b"x" * (fetch.MAX_RAW_BYTES + 1)
    if case == "truncated":
        document_server["headers"].append(("Content-Length", str(len(HTML) + 1)))
    if case == "large-header":
        document_server["headers"].append(("X-Padding", "x" * 8193))
    if case == "many-headers":
        document_server["headers"].extend((f"X-Padding-{n}", "x" * 1000) for n in range(40))
    if case.startswith("chunked"):
        document_server["headers"].append(("Transfer-Encoding", "chunked"))
        document_server["body"] = (b"PRIVATE-not-a-chunk\r\n" if case == "chunked-bad" else
                                   f"{len(HTML):x}\r\n".encode() + HTML + b"\r\n0\r\nX-Padding: " + b"x" * 8193 + b"\r\n\r\n")
    with pytest.raises((fetch.DocumentationFetchError, fetch.HTTPException)):
        fetch._capture(CATALOG_ID)


def test_chunked_body_and_bom_are_hashed_as_received(document_server):
    body = b"\xef\xbb\xbf" + HTML
    document_server["headers"].append(("Transfer-Encoding", "chunked"))
    document_server["body"] = f"{len(body):x}\r\n".encode() + body + b"\r\n0\r\n\r\n"
    result = fetch._capture(CATALOG_ID)
    assert result.raw_sha256 == sha256(body).hexdigest() and result.raw_bytes == len(body)
    assert "First steps" in result.text and "PRIVATE" not in result.text


@pytest.mark.parametrize("case", ["delimiter", "missing-terminator", "lf-only", "signed", "extension", "trailer"])
def test_chunk_framing_is_strict(document_server, case):
    size = f"{len(HTML):x}".encode()
    body = size + b"\r\n" + HTML + b"\r\n0\r\n\r\n"
    if case == "delimiter": body = size + b"\r\n" + HTML + b"ZZ0\r\n\r\n"
    if case == "missing-terminator": body = size + b"\r\n" + HTML + b"\r\n0\r\n"
    if case == "lf-only": body = size + b"\n" + HTML + b"\n0\n\n"
    if case == "signed": body = b"+" + body
    if case == "extension": body = size + b";PRIVATE=value\r\n" + HTML + b"\r\n0\r\n\r\n"
    if case == "trailer": body = size + b"\r\n" + HTML + b"\r\n0\r\nContent-Type: text/plain\r\n\r\n"
    document_server["headers"].append(("Transfer-Encoding", "chunked"))
    document_server["body"] = body
    with pytest.raises(fetch.DocumentationFetchError):
        fetch._capture(CATALOG_ID)


@pytest.mark.parametrize("body", [b"<p>No article</p>", b'<article class="md-content__inner"></article>',
    b'<article class="md-content__inner"><p>Never closed</p>',
    b'<article class="md-content__inner">One</article><article class="md-content__inner">Two</article>',
    b'<article class="md-content__inner"><p>Mismatched</div></article>',
    b'<article class="md-content__inner">\xff</article>',
    b'<article class="md-content__inner">\x00</article>',
    b'<article class="md-content__inner">' + b"x" * (fetch.MAX_TEXT_BYTES + 1) + b'</article>',
    b'<article class="md-content__inner">' + "ş".encode() * (fetch.MAX_TEXT_BYTES // 2 + 1) + b'</article>'])
def test_missing_ambiguous_malformed_or_large_content_rejected(body):
    with pytest.raises(fetch.DocumentationFetchError) as error:
        fetch._extract(body)
    assert error.value.code == "documentation_fetch_invalid"


@pytest.mark.parametrize("changes", [dict(text="  "), dict(text="PRIVATE\x00text"), dict(text="\ud800"),
                                      dict(content_sha256="b" * 64), dict(raw_bytes=0), dict(raw_bytes=True),
                                      dict(raw_bytes=fetch.MAX_RAW_BYTES + 1), dict(detected_version="0.123.0"),
                                      dict(unexpected="PRIVATE")])
def test_result_contract_is_strict_bounded_and_version_unknown(changes):
    with pytest.raises(ValidationError):
        captured(**changes)


def test_busy_is_process_wide_and_slot_released_on_failure(monkeypatch):
    fetch._FETCH_CAPACITY.acquire()
    try:
        with pytest.raises(fetch.DocumentationFetchError) as error:
            fetch.OfficialDocumentationFetcher().fetch(CATALOG_ID)
        assert error.value.code == "documentation_fetch_busy" and error.value.retryable
    finally:
        fetch._FETCH_CAPACITY.release()
    monkeypatch.setattr(fetch.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("PRIVATE")))
    with pytest.raises(fetch.DocumentationFetchError) as error:
        fetch.OfficialDocumentationFetcher().fetch(CATALOG_ID)
    assert error.value.code == "documentation_fetch_unavailable" and "PRIVATE" not in str(error.value)
    assert fetch._FETCH_CAPACITY.acquire(blocking=False)
    fetch._FETCH_CAPACITY.release()


def test_parent_strips_environment_and_uses_bounded_private_process(monkeypatch):
    monkeypatch.setenv("PRIVATE_OWNER_SECRET", "PRIVATE")
    calls = []
    result = captured()
    def run(command, **kwargs):
        calls.append((command, kwargs))
        kwargs["stdout"].write(result.model_dump_json().encode())
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(fetch.subprocess, "run", run)
    assert fetch.OfficialDocumentationFetcher().fetch(CATALOG_ID) == result
    command, kwargs = calls[0]
    assert command == [sys.executable, "-s", "-B", "-m", "app.curriculum.documentation_fetch", "--capture", CATALOG_ID]
    assert set(kwargs["env"]) == {"PYTHONPATH", "PYTHONIOENCODING", "PYTHONUTF8", "PYTHONDONTWRITEBYTECODE"}
    assert "PRIVATE_OWNER_SECRET" not in kwargs["env"]
    assert kwargs["timeout"] == 12 and kwargs["close_fds"] is True
    assert kwargs["stdin"] == kwargs["stderr"] == subprocess.DEVNULL


@pytest.mark.parametrize("case", ["oversized", "mismatch", "parser", "duplicate", "array", "nonzero", "garbage"])
def test_child_results_cannot_expand_or_mutate_capture(monkeypatch, case):
    result = captured().model_dump()
    if case == "mismatch": result["catalog_id"] = "different"
    if case == "parser": result["parser_version"] = "different-v2"
    raw = json.dumps(result).encode()
    if case == "oversized": raw = b"x" * (fetch.MAX_RESULT_BYTES + 1)
    if case == "duplicate": raw = b'{"error":"documentation_fetch_timeout","error":"PRIVATE","retryable":true}'
    if case == "array": raw = b"[]"
    if case == "garbage": raw = b"PRIVATE traceback"
    def run(command, **kwargs):
        kwargs["stdout"].write(raw)
        return subprocess.CompletedProcess(command, 2 if case == "nonzero" else 0)
    monkeypatch.setattr(fetch.subprocess, "run", run)
    with pytest.raises(fetch.DocumentationFetchError) as error:
        fetch.OfficialDocumentationFetcher().fetch(CATALOG_ID)
    assert "PRIVATE" not in str(error.value)


def test_real_child_timeout_is_killed_reaped_and_releases_slot(monkeypatch, tmp_path):
    pid_path = tmp_path / "synthetic-child.pid"
    command = [sys.executable, "-c", "import os,time,pathlib; pathlib.Path(" + repr(str(pid_path)) +
               ").write_text(str(os.getpid())); time.sleep(30)"]
    monkeypatch.setattr(fetch, "_command", lambda _: command)
    monkeypatch.setattr(fetch, "CAPTURE_SECONDS", .3)
    with pytest.raises(fetch.DocumentationFetchError) as error:
        fetch.OfficialDocumentationFetcher().fetch(CATALOG_ID)
    assert error.value.code == "documentation_fetch_timeout" and error.value.retryable
    pid = int(pid_path.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert fetch._FETCH_CAPACITY.acquire(blocking=False)
    fetch._FETCH_CAPACITY.release()


def test_actual_child_boundary_accepts_synthetic_result_without_network(monkeypatch):
    payload = captured().model_dump_json()
    monkeypatch.setattr(fetch, "_command", lambda _: [sys.executable, "-c", "print(" + repr(payload) + ")"])
    assert fetch.OfficialDocumentationFetcher().fetch(CATALOG_ID) == captured()


@pytest.mark.parametrize("phase", ["dns", "tls", "headers", "body"])
def test_actual_child_deadline_covers_dns_tls_slow_headers_and_body(document_server, monkeypatch, tmp_path, phase):
    # The child imports production code, but all targets are patched to this
    # authored fixture before capture. There is no production loopback override.
    marker = tmp_path / (phase + ".pid")
    script = ("import socket,time,pathlib,os,types\n"
              "from app.curriculum import documentation_fetch as f\n"
              "original_resolver=f._public_addresses\n"
              "f._public_addresses=lambda host:[(socket.AF_INET,socket.SOCK_STREAM,socket.IPPROTO_TCP,'',"
              + repr(("127.0.0.1", document_server["port"])) + ")]\n"
              "f.ssl.create_default_context=lambda:types.SimpleNamespace("
              "wrap_socket=lambda stream,server_hostname:stream)\n")
    if phase == "dns":
        script += "f._public_addresses=original_resolver\nf.socket.getaddrinfo=lambda *args:time.sleep(30)\n"
    if phase == "tls":
        script += ("f.ssl.create_default_context=lambda:types.SimpleNamespace("
                   "wrap_socket=lambda stream,server_hostname:time.sleep(30))\n")
    if phase == "headers": document_server["slow_headers"] = True
    if phase == "body": document_server["slow_body"] = True
    script += "pathlib.Path(" + repr(str(marker)) + ").write_text(str(os.getpid()))\n"
    script += "f._child_main(" + repr(CATALOG_ID) + ")\n"
    monkeypatch.setattr(fetch, "_command", lambda _: [sys.executable, "-c", script])
    monkeypatch.setattr(fetch, "CAPTURE_SECONDS", 2)
    with pytest.raises(fetch.DocumentationFetchError) as error:
        fetch.OfficialDocumentationFetcher().fetch(CATALOG_ID)
    assert error.value.code == "documentation_fetch_timeout"
    with pytest.raises(ProcessLookupError):
        os.kill(int(marker.read_text()), 0)
    if phase in {"headers", "body"}:
        assert len(document_server["requests"]) == 1


def test_child_resource_limits_are_explicit(monkeypatch):
    import resource
    calls = {}
    monkeypatch.setattr(resource, "setrlimit", lambda key, value: calls.update({key: value}))
    fetch._limits()
    assert calls[resource.RLIMIT_CORE] == (0, 0)
    assert calls[resource.RLIMIT_CPU] == (5, 5)
    assert calls[resource.RLIMIT_AS] == (256 * 1024 * 1024, 256 * 1024 * 1024)
    assert calls[resource.RLIMIT_FSIZE] == (fetch.MAX_RESULT_BYTES, fetch.MAX_RESULT_BYTES)
    assert calls[resource.RLIMIT_NOFILE] == (32, 32)


def test_child_own_alarm_terminates_blocked_dns_before_parent_deadline(monkeypatch, tmp_path):
    marker = tmp_path / "child-wall-deadline.pid"
    script = ("import socket,time,pathlib,os\n"
              "from app.curriculum import documentation_fetch as f\n"
              "f.socket.getaddrinfo=lambda *args:time.sleep(30)\n"
              "f.CAPTURE_SECONDS=.25\n"
              "pathlib.Path(" + repr(str(marker)) + ").write_text(str(os.getpid()))\n"
              "f._child_main(" + repr(CATALOG_ID) + ")\n")
    monkeypatch.setattr(fetch, "_command", lambda _: [sys.executable, "-c", script])
    monkeypatch.setattr(fetch, "CAPTURE_SECONDS", 5)
    run = subprocess.run
    codes = []
    def record(*args, **kwargs):
        result = run(*args, **kwargs)
        codes.append(result.returncode)
        return result
    monkeypatch.setattr(fetch.subprocess, "run", record)
    with pytest.raises(fetch.DocumentationFetchError) as error:
        fetch.OfficialDocumentationFetcher().fetch(CATALOG_ID)
    assert error.value.code == "documentation_fetch_timeout" and error.value.retryable
    assert codes == [-signal.SIGALRM]
    with pytest.raises(ProcessLookupError):
        os.kill(int(marker.read_text()), 0)


def test_direct_child_entry_clears_timer_and_restores_handler(monkeypatch):
    previous = signal.getsignal(signal.SIGALRM)
    calls = []
    monkeypatch.setattr(fetch, "_write_child_result", lambda identifier: calls.append(identifier))
    fetch._child_main(CATALOG_ID)
    assert calls == [CATALOG_ID]
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
    assert signal.getsignal(signal.SIGALRM) == previous
