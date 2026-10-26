"""Worker-side transport only: no native parsing, proxy, redirect or fallback."""
import hashlib
from http.client import HTTPConnection, HTTPException
import socket
from threading import BoundedSemaphore, Timer
from urllib.parse import urlsplit

from .contracts import MAX_RESPONSE_BYTES, VisualIdentity, WireResult, decode_wire
from .media import validate_mp4

REQUEST_SECONDS = 145
READY_SECONDS = 3


class VisualError(Exception):
    def __init__(self, code: str, *, transient: bool = False):
        super().__init__(code)
        self.code = code
        self.transient = transient


def checked_visual_url(value: str) -> str:
    try:
        url = urlsplit(value)
        if (url.scheme != "http" or url.hostname not in {"visual", "localhost", "127.0.0.1", "::1"}
                or url.username is not None or url.password is not None or url.query or url.fragment
                or url.path not in {"", "/"} or not url.port or not 1024 <= url.port <= 65535
                or (url.hostname == "visual" and url.port != 8091)
                or any(char.isspace() for char in value) or "\\" in value):
            raise ValueError()
    except (AttributeError, TypeError, ValueError):
        raise ValueError("Use private visual:8091 or an explicit loopback HTTP test endpoint") from None
    return value.rstrip("/")


def expire_connection(connection):
    # A socket reference, not HTTPConnection.close(): getresponse may detach a
    # Connection:close socket while a trickling response is still being read.
    try:
        connection.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


class LocalVisualClient:
    def __init__(self, base_url="http://visual:8091"):
        self.base_url = checked_visual_url(base_url)
        self.capacity = BoundedSemaphore(1)

    def _request(self, path, *, content=None, identity=None):
        url = urlsplit(self.base_url)
        connection = HTTPConnection(url.hostname, url.port, timeout=2)
        timer = None
        try:
            connection.connect()
            timer = Timer(REQUEST_SECONDS if content is not None else READY_SECONDS, expire_connection, (connection.sock,))
            timer.daemon = True
            timer.start()
            headers = {"Accept": "application/json", "Connection": "close"}
            if content is not None:
                headers.update({"Content-Type": "application/octet-stream", "X-Visual-Profile": identity.profile,
                                "X-Input-SHA256": hashlib.sha256(content).hexdigest()})
            connection.sock.settimeout(10 if content is not None else 2)
            connection.request("POST" if content is not None else "GET", path, body=content, headers=headers)
            connection.sock.settimeout(130 if content is not None else 2)
            with connection.getresponse() as response:
                lengths = response.headers.get_all("Content-Length", [])
                if (response.headers.get_all("Content-Type", []) != ["application/json"]
                        or response.headers.get("Transfer-Encoding") is not None
                        or response.headers.get("Content-Encoding") is not None or len(lengths) != 1
                        or not lengths[0].isascii() or not lengths[0].isdigit() or len(lengths[0]) > 8):
                    raise ValueError()
                size = int(lengths[0])
                limit = MAX_RESPONSE_BYTES if content is not None and response.status == 200 else 4096
                if not 0 < size <= limit:
                    raise ValueError()
                data = response.read(size + 1)
                if len(data) != size:
                    raise ValueError()
                document = decode_wire(data)
                if response.status != 200:
                    code = document.get("code") if isinstance(document, dict) else None
                    if response.status == 503 and code == "local_visual_busy":
                        raise VisualError("local_visual_busy", transient=True)
                    if response.status == 409 and code == "visual_profile_changed":
                        raise VisualError("visual_profile_changed")
                    if response.status in {413, 422} and code == "invalid_visual_request":
                        raise VisualError("invalid_visual_request")
                    raise VisualError("local_visual_unavailable", transient=True)
                return document
        except (HTTPException, OSError):
            raise VisualError("local_visual_unavailable", transient=True) from None
        except (ValueError, RecursionError):
            raise VisualError("invalid_visual_response") from None
        finally:
            if timer is not None:
                timer.cancel()
            connection.close()

    def ready(self, language="en") -> VisualIdentity:
        if language not in {"en", "tr", "en+tr"}:
            raise VisualError("invalid_visual_request")
        try:
            identity = VisualIdentity.model_validate(self._request("/health/ready?language=" + language))
            if identity.language != language:
                raise ValueError()
            return identity
        except (ValueError, RecursionError):
            raise VisualError("invalid_visual_response") from None

    def extract(self, content: bytes, *, expected_identity: VisualIdentity):
        try:
            validate_mp4(content)
            identity = VisualIdentity.model_validate(expected_identity)
        except ValueError:
            raise VisualError("invalid_visual_request") from None
        if not self.capacity.acquire(blocking=False):
            raise VisualError("local_visual_busy", transient=True)
        try:
            if self.ready(identity.language) != identity:
                raise VisualError("visual_profile_changed")
            document = self._request("/extract?language=" + identity.language, content=content, identity=identity)
            try:
                result = WireResult.model_validate(document)
                if result.identity != identity or result.input_sha256 != hashlib.sha256(content).hexdigest():
                    raise ValueError()
                return result.result()
            except (ValueError, RecursionError):
                raise VisualError("invalid_visual_response") from None
        finally:
            self.capacity.release()
