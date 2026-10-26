"""Actual private HTTP/native boundary with authored cards, never user data."""
import json
import subprocess
import sys
import tempfile
from time import monotonic, sleep

from .client import LocalVisualClient, VisualError


def main():
    from importlib.util import find_spec
    if any(find_spec(name) is not None for name in ('app.vision.checkpoints', 'psycopg', 'boto3', 'celery', 'fastapi')):
        raise ValueError("Native image contains application coordination dependencies")
    environment = {"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1",
                   "LANG": "C.UTF-8"}
    fixture = subprocess.run([sys.executable, "-m", "app.vision.http_selftest", "--fixture"],
        env=environment, capture_output=True, timeout=20, check=True).stdout
    if not 24 <= len(fixture) <= 2_000_000:
        raise ValueError("Authored fixture bound exceeded")
    # Parent remains able to connect to the child listener over loopback inside
    # a --network none disposable container. Only the service/native children
    # install the inherited syscall filter; no host port is published.
    with tempfile.TemporaryFile() as log:
        child = subprocess.Popen([sys.executable, "-m", "app.vision.server"], env=environment,
                                 stdout=log, stderr=log, start_new_session=True)
        try:
            remote = LocalVisualClient("http://127.0.0.1:8091")
            deadline = monotonic() + 10
            while True:
                if child.poll() is not None:
                    raise ValueError("Private service failed startup")
                try:
                    pinned = remote.ready("tr")
                    break
                except VisualError:
                    if monotonic() >= deadline:
                        raise ValueError("Private service readiness deadline") from None
                    sleep(.05)
            result = remote.extract(fixture, expected_identity=pinned)
            if result.candidates != 4 or [f.timestamp_ms for f in result.frames] != [0, 10000]:
                raise ValueError("HTTP evidence timeline mismatch")
            text = result.frames[1].text.replace("I", "ı").replace("İ", "i").casefold()
            if "sağlık kontrolü" not in text:
                raise ValueError("Authored explicit-language diagnostic failed")
            if any(not f.image.startswith(b"\x89PNG\r\n\x1a\n") for f in result.frames):
                raise ValueError("HTTP frame payload mismatch")
            bad = pinned.model_dump()
            # A different but internally valid identity must not be auto-adopted.
            import hashlib
            bad["engines"]["ffmpeg"] = "0.0.0"
            bad["profile"] = "local-visual-v1:" + hashlib.sha256(json.dumps(
                {k: v for k, v in bad.items() if k != "profile"}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            from .contracts import VisualIdentity
            try:
                remote.extract(fixture, expected_identity=VisualIdentity.model_validate(bad))
            except VisualError as failure:
                if failure.code != "visual_profile_changed":
                    raise ValueError("Wrong identity drift error") from None
            else:
                raise ValueError("Changed profile was adopted")
            log.seek(0)
            lines = log.read(65_537)
            if len(lines) > 65_536 or b"SA\xc4\x9eLIK" in lines or b"HEALTH CHECK" in lines:
                raise ValueError("Service logging bound/privacy failure")
            if lines.count(b'"event": "visual_extraction_complete"') != 1:
                raise ValueError("Unrequested native retry")
            print(json.dumps({"outcome": "private-http-component-complete", "quality_approval": "not_established",
                "frames": len(result.frames), "candidates": result.candidates,
                "timestamps_ms": [f.timestamp_ms for f in result.frames],
                "profile_pinning": True, "literal_png_ocr_transport": True,
                "service_kernel_and_child_denial": True, "application_records_created": 0}, sort_keys=True))
        finally:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--fixture"]:
            from ..asr.isolation import block_outbound_sockets
            from .selftest import authored_video
            block_outbound_sockets()
            sys.stdout.buffer.write(authored_video())
        elif not sys.argv[1:]:
            main()
        else:
            raise ValueError("Unsupported diagnostic arguments")
    except Exception:
        raise SystemExit("FAIL: private visual HTTP self-test; no media, OCR, paths or raw errors logged.") from None
