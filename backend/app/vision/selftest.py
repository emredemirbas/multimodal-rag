"""Authored high-contrast cards only; not a representative OCR quality benchmark."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from ..asr.isolation import block_outbound_sockets
from .local import LocalVisualProvider, NativeRunner


def authored_video() -> bytes:
    with tempfile.TemporaryDirectory(prefix="visual-selftest-", dir="/tmp") as directory:
        path = Path(directory) / "authored.mp4"
        NativeRunner().run(["/usr/bin/ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
            "color=c=white:s=960x540:r=2:d=20,"
            "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:text='HEALTH CHECK':fontsize=56:fontcolor=black:x=80:y=200:enable='lt(t,10)',"
            "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:text='SAĞLIK KONTROLÜ':fontsize=56:fontcolor=black:x=80:y=200:enable='gte(t,10)'",
            "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p", "-crf", "0",
            "-preset", "ultrafast", "-g", "1", "-t", "20", "-f", "mp4", str(path)])
        with path.open("rb") as stream:
            content = stream.read(2_000_001)
        if len(content) > 2_000_000:
            raise ValueError("Authored fixture exceeded its own bound")
        return content


def main():
    block_outbound_sockets()
    child = subprocess.run([sys.executable, "-c", "import socket; socket.socket()"],
        env={"PATH": "/usr/local/bin:/usr/bin:/bin"}, capture_output=True, timeout=5)
    if not child.returncode or b"Operation not permitted" not in child.stderr:
        raise RuntimeError("Child kernel isolation was not inherited")
    content = authored_video()
    results = {language: LocalVisualProvider().extract(content, language)
               for language in ("en", "tr", "en+tr")}
    validate_results(content, results)


def validate_results(content, results):
    for result in results.values():
        if result.candidates != 4 or len(result.frames) != 2 or [f.timestamp_ms for f in result.frames] != [0, 10000]:
            raise ValueError("Actual PTS or exact-pixel deduplication failed")
    english = results["en"].frames[0].text.casefold()
    turkish = results["tr"].frames[1].text.replace("I", "ı").replace("İ", "i").casefold()
    if not re.search(r"\bhealth\s+check\b", english) or not re.search(r"\bsağlık\s+kontrolü\b", turkish):
        raise ValueError("Authored card OCR diagnostic failed")
    mixed = results["en+tr"].frames[1].text.replace("I", "ı").replace("İ", "i").casefold()
    environment = {"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
    command = [sys.executable, "-m", "app.vision.smoke", "--authorized-input", "--language", "en"]
    delivered = subprocess.run([*command, "--synthetic-card-check"], input=content,
        env=environment, capture_output=True, timeout=30)
    if delivered.returncode or delivered.stderr:
        raise ValueError("Operator stdin command failed")
    receipt = json.loads(delivered.stdout)
    if receipt["frames"] != 2 or not receipt["synthetic_check"] or b"HEALTH CHECK" in delivered.stdout:
        raise ValueError("Operator summary leaked text or lost evidence")
    rejected = subprocess.run(command, input=b"PRIVATE_INVALID_VIDEO",
        env=environment, capture_output=True, timeout=5)
    if rejected.returncode != 1 or rejected.stdout or b"PRIVATE_INVALID_VIDEO" in rejected.stderr:
        raise ValueError("Malformed input did not fail safely")
    # Retain the observed combined-language failure as a separate diagnostic,
    # never reinterpret explicit-language success as universal recognition.
    print(json.dumps({"results": {language: result.summary() for language, result in results.items()},
        "authored_card_checks": "passed-explicit-languages",
        "combined_language_turkish_exact": bool(re.search(r"\bsağlık\s+kontrolü\b", mixed)),
        "inherited_network_denial": True, "operator_cli_and_safe_rejection": True,
        "fixture_bytes": len(content)}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("FAIL: authored visual self-test; no frames, OCR, paths or raw exception was logged.") from None
