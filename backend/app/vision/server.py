"""Private credential-free native parser service, never a product upload API."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import logging
import socket
import subprocess
import sys
from threading import BoundedSemaphore, Timer
from time import monotonic

from ..asr.isolation import block_outbound_sockets
from .contracts import VisualIdentity, WireResult, encode_wire
from .local import LocalVisualProvider, NativeRunner, require_isolation, runtime_identity
from .media import MAX_VIDEO_BYTES, validate_mp4

LOGGER = logging.getLogger("tutorial_workspace.visual")
READ_SECONDS = 10


def verify_child_isolation():
    probe = subprocess.run([sys.executable, "-c",
        "from app.vision.local import require_isolation; require_isolation()"],
        env={"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    if probe.returncode:
        raise RuntimeError("Visual child isolation is unavailable")


def end_connection(connection):
    try:
        connection.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


class VisualServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 4

    def __init__(self, address, *, runner=None):
        self.runner = runner or LocalVisualProvider().extract
        self.identities: dict[str, VisualIdentity] = {}
        self.network_ready = False
        self.capacity = BoundedSemaphore(1)
        self.connections = BoundedSemaphore(4)
        super().__init__(address, VisualHandler)

    def process_request(self, request, client_address):
        if not self.connections.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.connections.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.connections.release()

    def handle_error(self, request, client_address):
        LOGGER.warning('{"event":"visual_request_failed","code":"request_unavailable"}')


class VisualHandler(BaseHTTPRequestHandler):
    server: VisualServer
    server_version = "LocalVisual"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(READ_SECONDS)
        # Absolute deadline covers headers as well as a trickling body. Idle
        # socket timeouts alone would let one slow peer retain capacity forever.
        self.read_timer = Timer(READ_SECONDS, end_connection, (self.connection,))
        self.read_timer.daemon = True
        self.read_timer.start()

    def finish(self):
        self.read_timer.cancel()
        super().finish()

    def log_message(self, *_):
        pass  # Base messages interpolate untrusted paths/header errors.

    def send_error(self, code, message=None, explain=None):
        self.reply(code, {"code": "invalid_visual_request"})

    def reply(self, status, value):
        data = encode_wire(value)
        self.read_timer.cancel()
        self.connection.settimeout(5)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        self.wfile.write(data)
        path = getattr(self, "path", "").partition("?")[0]
        route = path if path in {"/health/ready", "/extract"} else "unmatched"
        LOGGER.info(json.dumps({"event": "visual_request_complete", "route": route, "status": status}))

    def requested_language(self, route):
        path, separator, query = self.path.partition("?")
        if path != route:
            self.reply(404, {"code": "not_found"})
            return None
        language = "en" if not separator else query.removeprefix("language=")
        if (separator and not query.startswith("language=")) or language not in {"en", "tr", "en+tr"}:
            self.reply(422, {"code": "invalid_visual_request"})
            return None
        allowed = {"host", "accept", "connection", "content-type", "content-length",
                   "accept-encoding", "x-visual-profile", "x-input-sha256"}
        if any(name.lower() not in allowed for name in self.headers):
            self.reply(422, {"code": "invalid_visual_request"})
            return None
        return language

    def do_GET(self):
        language = self.requested_language("/health/ready")
        if language is None:
            return
        if not self.server.network_ready or language not in self.server.identities:
            return self.reply(503, {"code": "local_visual_unavailable"})
        self.reply(200, self.server.identities[language])

    def do_POST(self):
        language = self.requested_language("/extract")
        if language is None:
            return
        lengths = self.headers.get_all("Content-Length", [])
        types = self.headers.get_all("Content-Type", [])
        profiles = self.headers.get_all("X-Visual-Profile", [])
        digests = self.headers.get_all("X-Input-SHA256", [])
        if (len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit()
                or len(lengths[0]) > 9 or types != ["application/octet-stream"]
                or len(profiles) != 1 or len(digests) != 1
                or len(digests[0]) != 64 or any(c not in "0123456789abcdef" for c in digests[0])):
            return self.reply(422, {"code": "invalid_visual_request"})
        size = int(lengths[0])
        if not 24 <= size <= MAX_VIDEO_BYTES:
            return self.reply(413, {"code": "invalid_visual_request"})
        identity = self.server.identities.get(language)
        if not self.server.network_ready or identity is None:
            return self.reply(503, {"code": "local_visual_unavailable"})
        if profiles[0] != identity.profile:
            return self.reply(409, {"code": "visual_profile_changed"})
        if not self.server.capacity.acquire(blocking=False):
            return self.reply(503, {"code": "local_visual_busy"})
        started = monotonic()
        try:
            try:
                content = bytearray()
                while len(content) < size:
                    block = self.rfile.read1(min(65_536, size - len(content)))
                    if not block:
                        raise ValueError("Incomplete input")
                    content.extend(block)
                self.read_timer.cancel()
                content = bytes(content)
                if hashlib.sha256(content).hexdigest() != digests[0]:
                    raise ValueError("Input digest mismatch")
                validate_mp4(content)
            except (ValueError, OSError):
                return self.reply(422, {"code": "invalid_visual_request"})
            result = WireResult.from_result(self.server.runner(content, language))
            if result.input_sha256 != digests[0] or result.identity != identity:
                raise ValueError("Visual processing identity changed")
            LOGGER.info(json.dumps({"event": "visual_extraction_complete", "frames": len(result.frames),
                "candidates": result.candidates, "duration_ms": result.video.duration_ms,
                "elapsed_ms": int((monotonic() - started) * 1000)}))
            self.reply(200, result)
        except Exception:
            self.reply(503, {"code": "local_visual_unavailable"})
        finally:
            self.server.capacity.release()


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    server = VisualServer(("0.0.0.0", 8091))
    try:
        block_outbound_sockets()  # Listener exists; native children inherit deny.
        require_isolation()
        verify_child_isolation()
        server.identities = {language: VisualIdentity.model_validate(runtime_identity(NativeRunner(), language))
                             for language in ("en", "tr", "en+tr")}
        server.network_ready = True
        LOGGER.info('{"event":"visual_ready","protocol":"local-visual-http-v1"}')
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Local visual service unavailable; verify its isolated image and Linux kernel support.") from None
