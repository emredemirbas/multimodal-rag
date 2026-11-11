"""One approved official page, captured as inert text in a bounded child process.

The catalog is application policy, never model output or a user supplied URL.
Nothing in this module schedules capture or enables curriculum generation.
"""

from dataclasses import asdict, dataclass
from hashlib import sha256
from html.parser import HTMLParser
from http.client import HTTPException, HTTPResponse, HTTPSConnection
from ipaddress import ip_address
import json
from pathlib import Path
import re
import signal
import socket
import ssl
import subprocess
import sys
from tempfile import TemporaryFile
from threading import BoundedSemaphore
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from .contracts import Contract, Digest


MAX_RAW_BYTES = 512_000
MAX_TEXT_BYTES = 128_000
MAX_HEADER_BYTES = 32_768
MAX_RESULT_BYTES = MAX_TEXT_BYTES * 6 + 4096
CAPTURE_SECONDS = 12
SOCKET_SECONDS = 3
_FETCH_CAPACITY = BoundedSemaphore(1)
_ERROR_CODES = frozenset({"documentation_fetch_timeout", "documentation_fetch_unavailable",
                          "documentation_fetch_invalid", "documentation_fetch_not_allowed",
                          "documentation_fetch_busy"})

_FASTAPI_LICENSE = """The MIT License (MIT)

Copyright (c) 2018 Sebastián Ramírez

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""


@dataclass(frozen=True)
class CatalogDocument:
    id: str
    title: str
    url: str
    parser_version: str
    version_policy: str
    license_name: str
    license_url: str
    license_text: str
    attribution: str

    @property
    def fingerprint(self) -> str:
        value = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return sha256(value.encode("utf-8")).hexdigest()


_CATALOG = (CatalogDocument(
    id="fastapi-first-steps-en", title="FastAPI — First Steps (English)",
    url="https://fastapi.tiangolo.com/tutorial/first-steps/",
    parser_version="official-document-html-v1", version_policy="unversioned; detected_version=unknown",
    license_name="MIT", license_url="https://github.com/fastapi/fastapi/blob/master/LICENSE",
    license_text=_FASTAPI_LICENSE, attribution="FastAPI documentation. Copyright (c) 2018 Sebastián Ramírez.",
),)


class DocumentationFetchError(Exception):
    def __init__(self, code: str, *, retryable: bool):
        self.code = code if code in _ERROR_CODES else "documentation_fetch_invalid"
        self.retryable = retryable is True
        super().__init__("The approved documentation could not be captured.")


def _invalid():
    return DocumentationFetchError("documentation_fetch_invalid", retryable=False)


def catalog_documents() -> tuple[CatalogDocument, ...]:
    return _CATALOG


def get_document(catalog_id: str) -> CatalogDocument:
    if type(catalog_id) is str:
        for document in _CATALOG:
            if document.id == catalog_id:
                return document
    raise DocumentationFetchError("documentation_fetch_not_allowed", retryable=False)


class FetchedDocument(Contract):
    catalog_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9-]*$")
    parser_version: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9-]*$")
    text: str = Field(min_length=1, max_length=MAX_TEXT_BYTES, repr=False)
    content_sha256: Digest
    raw_sha256: Digest
    raw_bytes: int = Field(ge=1, le=MAX_RAW_BYTES)
    detected_version: str | None

    @model_validator(mode="after")
    def bounded_text(self):
        try:
            encoded = self.text.encode("utf-8")
        except UnicodeError:
            raise ValueError("Invalid captured documentation text") from None
        if (not self.text.strip() or "\x00" in self.text or len(encoded) > MAX_TEXT_BYTES
                or sha256(encoded).hexdigest() != self.content_sha256 or self.detected_version is not None):
            raise ValueError("Invalid captured documentation text")
        return self


class _ArticleParser(HTMLParser):
    """Capture the one Material content article; do not interpret active content."""

    _VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
                       "meta", "param", "source", "track", "wbr"})
    _EXCLUDE = frozenset({"script", "style", "nav", "header", "footer", "aside", "form", "button",
                          "template", "iframe", "object", "embed", "svg", "math", "noscript"})
    _BLOCK = frozenset({"p", "div", "section", "h1", "h2", "h3", "h4", "h5", "h6", "li",
                        "ul", "ol", "dl", "dt", "dd", "blockquote", "table", "tr", "td", "th"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.article_depth = self.pre_depth = None
        self.articles = self.tags = 0
        self.closed_article = False
        self.parts, self.buffer = [], []
        self.buffer_bytes = self.part_bytes = 0

    def _append(self, value):
        self.buffer_bytes += len(value.encode("utf-8"))
        if self.part_bytes + self.buffer_bytes > MAX_TEXT_BYTES:
            raise _invalid()
        self.buffer.append(value)

    def _flush(self, *, pre=False):
        value = "".join(self.buffer)
        if not pre:
            value = re.sub(r"\s+", " ", value).strip()
        if value:
            self.part_bytes += len(value.encode("utf-8")) + (2 if self.parts else 0)
            if self.part_bytes > MAX_TEXT_BYTES:
                raise _invalid()
            self.parts.append(value)
        self.buffer, self.buffer_bytes = [], 0

    def handle_starttag(self, tag, attrs):
        self.tags += 1
        if self.tags > 20_000 or len(self.stack) >= 128:
            raise _invalid()
        values = dict(attrs)
        target = tag == "article" and "md-content__inner" in (values.get("class") or "").split()
        if target:
            self.articles += 1
            if self.articles > 1 or len(values) != len(attrs):
                raise _invalid()
            self.article_depth = len(self.stack) + 1
        blocked = (bool(self.stack and self.stack[-1][1]) or tag in self._EXCLUDE
                   or "hidden" in values or (values.get("aria-hidden") or "").lower() == "true"
                   or (values.get("role") or "").lower() in {"navigation", "banner", "contentinfo", "search"}
                   or bool(re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)",
                                     values.get("style") or "", re.IGNORECASE)))
        if self.article_depth is not None and not blocked:
            if tag == "pre":
                if self.pre_depth is not None:
                    raise _invalid()
                self._flush()
                self.pre_depth = len(self.stack) + 1
            elif self.pre_depth is None and tag in self._BLOCK:
                self._flush()
            elif tag == "br":
                self._append("\n" if self.pre_depth is not None else " ")
        if tag not in self._VOID:
            self.stack.append((tag, blocked))

    def handle_endtag(self, tag):
        if tag in self._VOID:
            return
        if not self.stack or self.stack[-1][0] != tag:
            if self.article_depth is not None:
                raise _invalid()
            # Ignore malformed unrelated site chrome; it is never evidence.
            for index in range(len(self.stack) - 1, -1, -1):
                if self.stack[index][0] == tag:
                    del self.stack[index:]
                    break
            return
        blocked = self.stack[-1][1]
        if self.article_depth is not None:
            if self.pre_depth == len(self.stack):
                self._flush(pre=True)
                self.pre_depth = None
            elif self.pre_depth is None and tag in self._BLOCK and not blocked:
                self._flush()
            if self.article_depth == len(self.stack):
                self._flush()
                self.article_depth = None
                self.closed_article = True
        self.stack.pop()

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, value):
        if self.article_depth is not None and self.stack and not self.stack[-1][1]:
            self._append(value if self.pre_depth is not None else re.sub(r"\s+", " ", value))

    def text(self):
        if self.articles != 1 or not self.closed_article or self.article_depth is not None:
            raise _invalid()
        value = "\n\n".join(self.parts)
        if not value.strip() or "\x00" in value or len(value.encode("utf-8")) > MAX_TEXT_BYTES:
            raise _invalid()
        return value


def _extract(body: bytes) -> str:
    try:
        value = body.decode("utf-8-sig")
        if "\x00" in value:
            raise ValueError()
        parser = _ArticleParser()
        parser.feed(value)
        parser.close()
        return parser.text()
    except (UnicodeError, ValueError, RecursionError):
        raise _invalid() from None


def _public_addresses(host: str):
    answers = socket.getaddrinfo(host, 443, socket.AF_UNSPEC, socket.SOCK_STREAM, socket.IPPROTO_TCP)
    if not answers or len(answers) > 32:
        raise _invalid()
    for family, kind, protocol, _, address in answers:
        try:
            value = ip_address(address[0])
            if (family not in {socket.AF_INET, socket.AF_INET6} or kind != socket.SOCK_STREAM
                    or protocol != socket.IPPROTO_TCP or address[1] != 443 or not value.is_global
                    or value.is_reserved or value.is_private or value.is_loopback or value.is_link_local
                    or value.is_multicast or value.is_unspecified or "%" in address[0]
                    or getattr(value, "ipv4_mapped", None) is not None
                    or getattr(value, "sixtofour", None) is not None
                    or getattr(value, "teredo", None) is not None):
                raise ValueError()
        except (ValueError, TypeError, IndexError):
            raise DocumentationFetchError("documentation_fetch_not_allowed", retryable=False) from None
    return answers


class _WireReader:
    """Bound consumed headers, chunk framing and trailers as well as body bytes."""

    def __init__(self, stream):
        self.stream, self.count, self.limit = stream, 0, MAX_HEADER_BYTES

    def _read(self, method, size=-1):
        remaining = self.limit - self.count
        size = remaining + 1 if size < 0 else min(size, remaining + 1)
        if method == "readline":
            size = min(size, 8193)
        result = getattr(self.stream, method)(size)
        self.count += len(result)
        if self.count > self.limit or method == "readline" and len(result) > 8192:
            raise _invalid()
        return result

    def read(self, size=-1):
        return self._read("read", size)

    def read1(self, size=-1):
        return self._read("read1", size)

    def readline(self, size=-1):
        return self._read("readline", size)

    def __getattr__(self, name):
        return getattr(self.stream, name)


class _BoundedResponse(HTTPResponse):
    def begin(self):
        if not isinstance(self.fp, _WireReader):
            self.fp = _WireReader(self.fp)
        reader = self.fp
        super().begin()
        reader.limit = MAX_RAW_BYTES + 2 * MAX_HEADER_BYTES

    def _get_chunk_left(self):
        # The stdlib deliberately tolerates malformed chunk CRLF/trailers. This
        # narrow capture protocol requires strict framing, without extensions or
        # nonempty trailers; no response metadata may be supplied after the body.
        if not self.chunk_left:
            if self.chunk_left is not None and self._safe_read(2) != b"\r\n":
                raise _invalid()
            line = self.fp.readline(8193)
            if not re.fullmatch(rb"[0-9a-fA-F]{1,8}\r\n", line):
                raise _invalid()
            amount = int(line[:-2], 16)
            if amount > MAX_RAW_BYTES:
                raise _invalid()
            if amount == 0:
                if self.fp.readline(8193) != b"\r\n":
                    raise _invalid()
                self._close_conn()
                self.chunk_left = None
                return None
            self.chunk_left = amount
        return self.chunk_left


class _PinnedConnection(HTTPSConnection):
    response_class = _BoundedResponse

    def __init__(self, host, address):
        super().__init__(host, 443, timeout=SOCKET_SECONDS, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        family, kind, protocol, _, address = self.address
        stream = socket.socket(family, kind, protocol)
        try:
            stream.settimeout(SOCKET_SECONDS)
            stream.connect(address)
            self.sock = self._context.wrap_socket(stream, server_hostname=self.host)
        except BaseException:
            stream.close()
            raise


def _body(response) -> bytes:
    if response.status != 200:
        if 300 <= response.status < 400:
            raise DocumentationFetchError("documentation_fetch_not_allowed", retryable=False)
        raise DocumentationFetchError("documentation_fetch_unavailable",
                                      retryable=response.status in {408, 429, 500, 502, 503, 504})
    headers = response.headers
    if len(headers.get_all("Content-Type", [])) != 1 or headers.get_content_type() != "text/html":
        raise _invalid()
    charsets = [value for key, value in headers.get_params()[1:] if key.lower() == "charset"]
    if (len(charsets) > 1 or charsets and (type(charsets[0]) is not str
                                         or charsets[0].lower() not in {"utf-8", "utf8"})):
        raise _invalid()
    for name in ("Content-Encoding", "Content-Length", "Transfer-Encoding"):
        if len(headers.get_all(name, [])) > 1:
            raise _invalid()
    if headers.get("Content-Encoding", "identity").strip().lower() != "identity":
        raise _invalid()
    declared, transfer = headers.get("Content-Length"), headers.get("Transfer-Encoding")
    if (declared is not None and transfer is not None
            or transfer is not None and transfer.strip().lower() != "chunked"):
        raise _invalid()
    if declared is not None and (len(declared) > 6 or not declared.isascii() or not declared.isdecimal()
                                 or not 1 <= int(declared) <= MAX_RAW_BYTES):
        raise _invalid()
    content = bytearray()
    while True:
        chunk = response.read1(min(8192, MAX_RAW_BYTES + 1 - len(content)))
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > MAX_RAW_BYTES:
            raise _invalid()
    if not content or declared is not None and len(content) != int(declared):
        raise _invalid()
    return bytes(content)


def _capture(catalog_id: str) -> FetchedDocument:
    document = get_document(catalog_id)
    parsed = urlsplit(document.url)
    # No caller-selected URL reaches this boundary, including through the child CLI.
    if (parsed.scheme != "https" or parsed.netloc != "fastapi.tiangolo.com"
            or parsed.path != "/tutorial/first-steps/" or parsed.query or parsed.fragment):
        raise DocumentationFetchError("documentation_fetch_not_allowed", retryable=False)
    connection = _PinnedConnection(parsed.hostname, _public_addresses(parsed.hostname)[0])
    try:
        connection.request("GET", parsed.path, headers={
            "Host": parsed.hostname, "Accept": "text/html", "Accept-Encoding": "identity",
            "User-Agent": "multimodal-rag/official-document-capture-v1", "Connection": "close",
        })
        with connection.getresponse() as response:
            body = _body(response)
        text = _extract(body)
        return FetchedDocument(catalog_id=document.id, parser_version=document.parser_version, text=text,
                               content_sha256=sha256(text.encode("utf-8")).hexdigest(),
                               raw_sha256=sha256(body).hexdigest(), raw_bytes=len(body), detected_version=None)
    finally:
        connection.close()


def _limits():
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_RESULT_BYTES, MAX_RESULT_BYTES))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))


def _write_child_result(catalog_id: str):
    try:
        _limits()
        result = _capture(catalog_id).model_dump(mode="json")
    except DocumentationFetchError as error:
        result = {"error": error.code, "retryable": error.retryable}
    except (TimeoutError, socket.timeout):
        result = {"error": "documentation_fetch_timeout", "retryable": True}
    except ssl.SSLCertVerificationError:
        result = {"error": "documentation_fetch_unavailable", "retryable": False}
    except (HTTPException, UnicodeError, ValueError, TypeError, RecursionError):
        result = {"error": "documentation_fetch_invalid", "retryable": False}
    except Exception:
        result = {"error": "documentation_fetch_unavailable", "retryable": True}
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_RESULT_BYTES:
        encoded = b'{"error":"documentation_fetch_invalid","retryable":false}'
    sys.stdout.buffer.write(encoded)


def _child_main(catalog_id: str):
    # The default disposition terminates even inside a blocked C resolver. A
    # Python exception handler could wait for that resolver to return. This
    # independent wall bound also applies if the API parent disappears.
    previous_handler = signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.setitimer(signal.ITIMER_REAL, CAPTURE_SECONDS)
    try:
        _write_child_result(catalog_id)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _command(catalog_id):
    return [sys.executable, "-s", "-B", "-m", "app.curriculum.documentation_fetch", "--capture", catalog_id]


def _result(raw: bytes) -> FetchedDocument:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError()
            value[key] = item
        return value
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
        if type(parsed) is not dict:
            raise ValueError()
        if set(parsed) == {"error", "retryable"}:
            if parsed["error"] not in _ERROR_CODES or type(parsed["retryable"]) is not bool:
                raise ValueError()
            raise DocumentationFetchError(parsed["error"], retryable=parsed["retryable"])
        return FetchedDocument.model_validate(parsed, strict=True)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise _invalid() from None


class OfficialDocumentationFetcher:
    def fetch(self, catalog_id: str) -> FetchedDocument:
        document = get_document(catalog_id)
        if not _FETCH_CAPACITY.acquire(blocking=False):
            raise DocumentationFetchError("documentation_fetch_busy", retryable=True)
        try:
            root = Path(__file__).resolve().parents[2]
            environment = {"PYTHONPATH": str(root), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
                           "PYTHONDONTWRITEBYTECODE": "1"}
            with TemporaryFile() as output:
                completed = subprocess.run(_command(document.id), cwd=root, env=environment,
                                           stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.DEVNULL,
                                           timeout=CAPTURE_SECONDS, check=False, close_fds=True)
                if completed.returncode == -signal.SIGALRM:
                    raise DocumentationFetchError("documentation_fetch_timeout", retryable=True)
                if completed.returncode != 0:
                    raise DocumentationFetchError("documentation_fetch_unavailable", retryable=True)
                output.seek(0)
                raw = output.read(MAX_RESULT_BYTES + 1)
                if len(raw) > MAX_RESULT_BYTES:
                    raise _invalid()
            result = _result(raw)
            if result.catalog_id != document.id or result.parser_version != document.parser_version:
                raise _invalid()
            return result
        except subprocess.TimeoutExpired:
            # subprocess.run kills and reaps the direct child before raising.
            raise DocumentationFetchError("documentation_fetch_timeout", retryable=True) from None
        except OSError:
            raise DocumentationFetchError("documentation_fetch_unavailable", retryable=True) from None
        finally:
            _FETCH_CAPACITY.release()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--capture":
        _child_main(sys.argv[2])
    else:
        sys.exit(2)
