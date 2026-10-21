"""Private credential-free model service, not an application upload endpoint."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
import resource
import subprocess
import sys
import tempfile
from threading import BoundedSemaphore
from urllib.parse import parse_qs, urlsplit

from .contracts import TranscriptionSlice
from .isolation import block_outbound_sockets
from .profile import INFERENCE_SECONDS, MAX_RESPONSE_BYTES, encode_result, identity, verify_model
from .wav import MAX_PCM_BYTES

LOGGER = logging.getLogger("tutorial_workspace.asr")


def infer(pcm: bytes, language: str) -> dict:
    # The child inherits seccomp, receives no caller-selected paths/environment,
    # and dies after one window. Anonymous tmpfs output has a child RLIMIT_FSIZE;
    # stdin is a bounded pipe, so original audio never touches the filesystem.
    environment = {"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONPATH": "/app", "PYTHONDONTWRITEBYTECODE": "1",
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
        "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "1", "TOKENIZERS_PARALLELISM": "false"}
    with tempfile.TemporaryFile() as output:
        with subprocess.Popen([sys.executable, "-m", "app.asr.infer_window", language], stdin=subprocess.PIPE,
                              stdout=output, stderr=subprocess.DEVNULL, env=environment, start_new_session=True) as child:
            try:
                child.communicate(pcm, timeout=INFERENCE_SECONDS)
            except subprocess.TimeoutExpired:
                # Only this explicitly created child process group is terminated.
                import signal
                os.killpg(child.pid, signal.SIGKILL)
                child.communicate()
                raise RuntimeError("Local ASR deadline exceeded") from None
            if child.returncode != 0:
                raise RuntimeError("Local ASR inference unavailable")
        output.seek(0)
        data = output.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("Local ASR output limit exceeded")
    result = TranscriptionSlice.model_validate_json(data)
    if result.input_frames != len(pcm) // 2 or result.requested_language != language:
        raise ValueError("Local ASR input identity mismatch")
    return result.model_dump()


class AsrServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 4

    def __init__(self, address, runner=infer):
        self.runner = runner
        self.inference_capacity = BoundedSemaphore(1)
        self.connections = BoundedSemaphore(4)
        self.network_ready = False
        super().__init__(address, AsrHandler)

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
        LOGGER.warning(json.dumps({"event": "asr_request_failed", "code": "request_unavailable"}))


class AsrHandler(BaseHTTPRequestHandler):
    server: AsrServer
    server_version = "LocalASR"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_):
        pass  # Default messages interpolate the caller's path; never log it.

    def reply(self, status: int, result: dict):
        data = encode_result(result)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True
        route = "/health/ready" if self.path == "/health/ready" else "/transcribe" if self.path.split("?", 1)[0] == "/transcribe" else "unmatched"
        LOGGER.info(json.dumps({"event": "asr_request_complete", "method": self.command, "route": route, "status": status}))

    def do_GET(self):
        if self.path != "/health/ready":
            return self.reply(404, {"code": "not_found"})
        if not self.server.network_ready:
            return self.reply(503, {"code": "local_asr_unavailable"})
        self.reply(200, identity())

    def do_POST(self):
        url = urlsplit(self.path)
        parameters = parse_qs(url.query, keep_blank_values=True)
        language = parameters.get("language", ["auto"])
        if url.path != "/transcribe":
            return self.reply(404, {"code": "not_found"})
        if parameters.keys() - {"language"} or len(language) != 1 or language[0] not in {"auto", "en", "tr"}:
            return self.reply(422, {"code": "invalid_audio_slice"})
        lengths = self.headers.get_all("Content-Length", [])
        if (self.headers.get("Transfer-Encoding") is not None or len(lengths) != 1
                or not lengths[0].isascii() or not lengths[0].isdigit() or len(lengths[0]) > 7
                or self.headers.get("Content-Type", "").lower() != "application/octet-stream"):
            return self.reply(422, {"code": "invalid_audio_slice"})
        size = int(lengths[0])
        if not 0 < size <= MAX_PCM_BYTES or size % 2:
            return self.reply(413, {"code": "invalid_audio_slice"})
        if not self.server.network_ready:
            return self.reply(503, {"code": "local_asr_unavailable"})
        if not self.server.inference_capacity.acquire(blocking=False):
            return self.reply(503, {"code": "local_asr_busy"})
        try:
            pcm = self.rfile.read(size)
            if len(pcm) != size:
                return self.reply(422, {"code": "invalid_audio_slice"})
            result = TranscriptionSlice.model_validate(self.server.runner(pcm, language[0]))
            if result.input_frames != size // 2 or result.requested_language != language[0]:
                raise ValueError("Local ASR input mismatch")
            LOGGER.info(json.dumps({"event": "asr_inference_complete", "input_frames": result.input_frames,
                "segment_count": len(result.segments), "duration_ms": result.duration_ms, "profile": result.profile}))
            self.reply(200, result.model_dump())
        except Exception:
            self.reply(503, {"code": "local_asr_unavailable"})
        finally:
            self.server.inference_capacity.release()


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    server = AsrServer(("0.0.0.0", 8090))  # Bind before denying new sockets/connect.
    try:
        block_outbound_sockets()
        verify_model()
        server.network_ready = True
        LOGGER.info(json.dumps({"event": "asr_ready", "model": identity()["model"], "profile": identity()["profile"]}))
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Local ASR unavailable: install the approved model and verify Linux isolation support.") from None
