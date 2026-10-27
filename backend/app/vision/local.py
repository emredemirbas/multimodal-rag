"""Explicit stateless native parser; never instantiate inside API/ordinary workers."""
from __future__ import annotations

from dataclasses import dataclass, field
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tempfile
from time import monotonic
from typing import Literal, Protocol
import unicodedata

from .media import (FrameEvidence, POLICY, VideoInfo, encode_png, parse_pgm,
                    parse_probe, sample_times, validate_mp4)
from .selection import CHANGE_POLICY

Language = Literal["en", "tr", "en+tr"]
TESSDATA = Path("/usr/share/tesseract-ocr/5/tessdata")
INPUT_OPTIONS = ["-f", "mov", "-protocol_whitelist", "file,pipe", "-enable_drefs", "0",
                 "-use_absolute_path", "0", "-probesize", "1000000", "-analyzeduration", "2000000"]


def require_isolation() -> None:
    try:
        probe = socket.socket()
    except OSError as error:
        if error.errno == errno.EPERM:
            return
    else:
        probe.close()
    raise RuntimeError("Start the explicit isolated visual tool")


class NativeRunner:
    def __init__(self):
        self.deadline = monotonic() + 120

    def run(self, arguments: list[str], *, content: bytes | None = None, limit: int = 32_768) -> bytes:
        remaining = self.deadline - monotonic()
        if remaining <= 0:
            raise RuntimeError("Visual processing deadline exceeded")
        environment = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
            "PYTHONPATH": str(Path(__file__).resolve().parents[2]), "PYTHONDONTWRITEBYTECODE": "1"}
        with tempfile.TemporaryFile(dir="/tmp") as output:
            with subprocess.Popen([sys.executable, "-m", "app.vision.native", *arguments],
                    stdin=subprocess.PIPE, stdout=output, stderr=subprocess.DEVNULL,
                    env=environment, start_new_session=True) as child:
                try:
                    child.communicate(content, timeout=min(15, remaining))
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    child.communicate()
                    raise RuntimeError("Visual child deadline exceeded") from None
                if child.returncode:
                    raise RuntimeError("Unsupported input or unavailable visual tool")
            output.seek(0)
            result = output.read(limit + 1)
        if len(result) > limit:
            raise ValueError("Visual output exceeds limit")
        return result


@dataclass(frozen=True)
class VisualResult:
    input_sha256: str
    info: VideoInfo
    identity: dict
    candidates: int
    frames: tuple[FrameEvidence, ...]
    selection: dict | None = field(default=None, repr=False)

    def summary(self) -> dict:
        return {"outcome": "component-complete", "quality_approval": "not_established",
            "input_sha256": self.input_sha256, "video": self.info.model_dump(), **self.identity,
            "candidates": self.candidates, "frames": len(self.frames),
            "exact_duplicates_removed": self.candidates - len(self.frames),
            "frames_with_text": sum(bool(frame.text) for frame in self.frames),
            "evidence": [{"sample_target_ms": frame.sample_target_ms, "timestamp_ms": frame.timestamp_ms,
                "width": frame.width, "height": frame.height, "image_sha256": frame.image_sha256,
                "text_characters": len(frame.text)} for frame in self.frames]}


class VisualProvider(Protocol):
    def extract(self, content: bytes, language: Language = "en") -> VisualResult: ...


def runtime_identity(runner: NativeRunner, language: Language, selection="uniform") -> dict:
    if language not in {'en', 'tr', 'en+tr'} or selection not in {'uniform', 'change'}:
        raise ValueError('Unsupported visual profile')
    versions = {}
    for name in ("ffmpeg", "tesseract"):
        output = runner.run(["/usr/bin/" + name, "-version" if name == "ffmpeg" else "--version"], limit=4096)
        pattern = rb"ffmpeg version ([0-9A-Za-z.+~:-]{1,64}) " if name == "ffmpeg" else rb"tesseract ([0-9A-Za-z.+~:-]{1,64})\n"
        match = re.match(pattern, output)
        if not match:
            raise ValueError("Unknown native tool identity")
        versions[name] = match[1].decode("ascii")
    models = {}
    for name in ("eng", "tur"):
        path = TESSDATA / (name + ".traineddata")
        if path.is_symlink() or not path.is_file() or not 1 <= path.stat().st_size <= 32_000_000:
            raise ValueError("Local OCR language data is unavailable")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        models[name] = digest.hexdigest()
    identity = {"provider": "local-ffmpeg-tesseract", "engines": versions,
                "language_data": models, "language": language, "policy": POLICY if selection == 'uniform' else CHANGE_POLICY}
    prefix = 'local-visual-v1:' if selection == 'uniform' else 'local-visual-v2:'
    return {**identity, "profile": prefix + hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


def recognize_text(runner: NativeRunner, pgm: bytes, language: Language) -> str:
    codes = {"en": "eng", "tr": "tur", "en+tr": "eng+tur"}[language]
    text = runner.run(["/usr/bin/tesseract", "stdin", "stdout", "--tessdata-dir",
        str(TESSDATA), "-l", codes, "--oem", "1", "--psm", "11", "txt"], content=pgm, limit=32_768).decode("utf-8").replace("\x0c", "").strip()
    if len(text) > 16_000 or any(unicodedata.category(char) in {"Cc", "Cs"} and char not in "\n\r\t" for char in text):
        raise ValueError("Invalid or oversized OCR text")
    return text


class LocalVisualProvider:
    def extract(self, content: bytes, language: Language = "en") -> VisualResult:
        validate_mp4(content)
        if language not in {"en", "tr", "en+tr"}:
            raise ValueError("Unsupported OCR language")
        require_isolation()  # Fail before native decoding outside the dedicated tool.
        runner = NativeRunner()
        identity = runtime_identity(runner, language)
        with tempfile.TemporaryDirectory(prefix="visual-", dir="/tmp") as directory:
            root = Path(directory)
            source = root / "input.mp4"
            source.write_bytes(content)
            metadata = runner.run(["/usr/bin/ffprobe", "-v", "error", *INPUT_OPTIONS,
                "-show_entries", "format=duration,start_time:stream=codec_type,codec_name,codec_tag_string,width,height,pix_fmt,start_time,duration,avg_frame_rate,r_frame_rate:stream_side_data=rotation",
                "-of", "json", str(source)])
            info = parse_probe(metadata)
            times = sample_times(info.duration_ms)
            frames, seen = [], set()
            for target in times:
                with tempfile.TemporaryDirectory(prefix="frame-", dir=root) as frame_dir:
                    destination = Path(frame_dir)
                    runner.run(["/usr/bin/ffmpeg", "-nostdin", "-v", "error", "-threads", "1", "-filter_threads", "1",
                        "-ss", f"{target / 1000:.3f}", "-copyts", *INPUT_OPTIONS, "-i", str(source),
                        "-map", "0:v:0", "-an", "-sn", "-dn", "-vf",
                        "scale=960:540:force_original_aspect_ratio=decrease:flags=bilinear,format=gray",
                        "-frames:v", "1", "-c:v", "pgm", "-threads", "1", "-vsync", "0",
                        "-enc_time_base", "1:1000", "-frame_pts", "1", "-f", "image2", str(destination / "%d.pgm")])
                    files = list(destination.iterdir())
                    if len(files) != 1 or files[0].is_symlink() or not re.fullmatch(r"[0-9]{1,6}\.pgm", files[0].name):
                        raise ValueError("Missing or invalid decoded frame PTS")
                    with files[0].open("rb") as image:
                        pgm = image.read(600_001)
                    width, height, pixels = parse_pgm(pgm)
                    timestamp = int(files[0].stem)
                    # Validate PTS even for a frame that will be deduplicated.
                    frame = FrameEvidence(sample_target_ms=target, timestamp_ms=timestamp,
                        width=width, height=height, image=encode_png(width, height, pixels), text="")
                    if timestamp >= info.duration_ms:
                        raise ValueError("Decoded frame lies outside the video")
                    fingerprint = hashlib.sha256(pgm).digest()
                    if fingerprint in seen:
                        continue
                    seen.add(fingerprint)
                    text = recognize_text(runner, pgm, language)
                    frames.append(FrameEvidence(sample_target_ms=target, timestamp_ms=timestamp,
                        width=width, height=height, image=frame.image, text=text))
        return VisualResult(hashlib.sha256(content).hexdigest(), info, identity, len(times), tuple(frames))
