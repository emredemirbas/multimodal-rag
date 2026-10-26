from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zlib

import pytest

from app.vision import local, media
from app.vision import native


def box(kind, payload):
    return struct.pack(">I4s", len(payload) + 8, kind) + payload


def mp4():
    return box(b"ftyp", b"isom\x00\x00\x02\x00isomavc1") + box(b"moov", b"fixture") + box(b"mdat", b"fixture")


def probe(**changes):
    data = {"format": {"duration": "10.000000", "start_time": "0.000000"}, "streams": [{
        "codec_type": "video", "codec_name": "h264", "codec_tag_string": "avc1",
        "pix_fmt": "yuv420p", "width": 1920, "height": 1080, "start_time": "0.000000",
        "duration": "10.000000", "avg_frame_rate": "25/1", "r_frame_rate": "25/1", **changes,
    }]}
    return data


def pgm(pixel=0):
    return b"P5\n16 16\n255\n" + bytes([pixel]) * 256


def test_top_level_container_guards_and_extended_box():
    media.validate_mp4(mp4())
    content = box(b"ftyp", b"mp42\0\0\0\0") + box(b"moov", b"fixture")
    media.validate_mp4(content + struct.pack(">I4sQ", 1, b"mdat", 20) + b"data")


@pytest.mark.parametrize("content", [
    b"", b"http://127.0.0.1/private.mp4", b"#EXTM3U\nfile:///private",
    b"\0" * 24, mp4()[:-1], mp4() + b"truncated", mp4() + box(b"moof", b"no"),
    mp4() + box(b"moov", b"duplicate"), mp4() + box(b"ftyp", b"isom\0\0\0\0"),
    box(b"ftyp", b"evil\0\0\0\0") + box(b"moov", b"x") + box(b"mdat", b"x"),
    box(b"ftyp", b"isom\0\0\0\0") + box(b"mdat", b"data"),
    box(b"ftyp", b"isom\0\0\0\0") + box(b"moov", b"x") + box(b"mdat", b""),
    mp4() + struct.pack(">I4sQ", 1, b"mdat", 2**63),
    mp4() + struct.pack(">I4s", 0, b"free"),
    mp4() + box(b"free", b"x") * 64,
])
def test_malformed_unsupported_container_rejected_before_native(content, monkeypatch):
    monkeypatch.setattr(local, "require_isolation", lambda: pytest.fail("invalid input reached runtime"))
    with pytest.raises(ValueError):
        local.LocalVisualProvider().extract(content)


def test_actual_byte_limit_and_input_type(monkeypatch):
    monkeypatch.setattr(media, "MAX_VIDEO_BYTES", len(mp4()) - 1)
    for value in [mp4(), bytearray(mp4()), "not binary"]:
        with pytest.raises(ValueError):
            media.validate_mp4(value)


def test_metadata_limits_fractional_rounding_and_ignored_aac():
    data = probe(avg_frame_rate="30000/1001", r_frame_rate="30000/1001", duration="9.9991")
    data["streams"].append({"codec_type": "audio", "codec_name": "aac"})
    info = media.parse_probe(json.dumps(data).encode())
    assert info.duration_ms == 10000 and info.fps_numerator == 30000 and info.fps_denominator == 1001
    assert info.width == 1920 and info.height == 1080


@pytest.mark.parametrize("changes", [
    {"codec_name": "hevc"}, {"codec_tag_string": "encv"}, {"pix_fmt": "yuv420p10le"},
    {"width": 4096}, {"height": 2160}, {"width": True}, {"width": "1920"},
    {"side_data_list": [{"rotation": 90}]}, {"avg_frame_rate": "0/0"},
    {"avg_frame_rate": "1/0"}, {"avg_frame_rate": "NaN"}, {"r_frame_rate": "30/1"},
    {"avg_frame_rate": "120/1", "r_frame_rate": "120/1"},
    {"start_time": "0.001"}, {"start_time": "-0.001"},
    {"duration": "601"}, {"duration": "0"}, {"duration": "Infinity"},
    {"duration": "NaN"}, {"duration": True}, {"avg_frame_rate": "9" * 65},
])
def test_unsupported_metadata(changes):
    with pytest.raises((ValueError, ArithmeticError)):
        media.parse_probe(json.dumps(probe(**changes)).encode())


def test_metadata_shape_and_format_and_duplicate_keys():
    cases = []
    for streams in [[], probe()["streams"] * 2, probe()["streams"] + [{"codec_type": "subtitle"}],
                    probe()["streams"] + [{"codec_type": "audio", "codec_name": "opus"}]]:
        cases.append({**probe(), "streams": streams})
    for field, value in [("start_time", "1"), ("duration", "9"), ("duration", "601")]:
        cases.append({**probe(), "format": {**probe()["format"], field: value}})
    for value in cases:
        with pytest.raises(ValueError):
            media.parse_probe(json.dumps(value).encode())
    for value in [b'{"streams":[],"streams":[]}', b'{"value":NaN}', b" " * 32769]:
        with pytest.raises(ValueError):
            media.parse_probe(value)


def test_sampling_is_bounded_ordered_and_in_clip():
    assert media.sample_times(1) == media.sample_times(5000) == [0]
    assert media.sample_times(10000) == [0, 5000]
    assert media.sample_times(600000) == list(range(0, 600000, 30000))
    for value in [True, 0, -1, 600001]:
        with pytest.raises(ValueError):
            media.sample_times(value)


def test_png_is_deterministic_bounded_and_lossless_with_verified_crc():
    width, height, pixels = media.parse_pgm(pgm(123))
    png = media.encode_png(width, height, pixels)
    assert png == media.encode_png(width, height, pixels) and png.startswith(b"\x89PNG\r\n\x1a\n")
    offset, chunks = 8, {}
    while offset < len(png):
        size = struct.unpack_from(">I", png, offset)[0]
        kind, data = png[offset + 4:offset + 8], png[offset + 8:offset + 8 + size]
        assert zlib.crc32(kind + data) == struct.unpack_from(">I", png, offset + 8 + size)[0]
        chunks[kind] = data
        offset += 12 + size
    assert struct.unpack(">IIBBBBB", chunks[b"IHDR"]) == (16, 16, 8, 0, 0, 0, 0)
    assert zlib.decompress(chunks[b"IDAT"]) == (b"\x00" + bytes([123]) * 16) * 16
    assert not chunks[b"IEND"] and offset == len(png)
    for data in [pgm()[:-1], pgm() + b"extra", b"P6\n16 16\n255\n" + b"x" * 768,
                 b"P5\n9999 9999\n255\n", b"P5\n0 0\n255\n"]:
        with pytest.raises(ValueError):
            media.parse_pgm(data)
    with pytest.raises(ValueError):
        media.encode_png(9999, 1, b"x")


class Runner:
    timestamps = [0, 5000]
    images = [pgm(), pgm(255)]
    text = b"PRIVATE_OCR <script>alert(1)</script>\nuser_id\x0c"
    calls = []

    def run(self, arguments, **kwargs):
        self.calls.append((arguments, kwargs))
        if arguments[0].endswith("ffprobe"):
            return json.dumps(probe()).encode()
        if arguments[0].endswith("ffmpeg"):
            ordinal = sum(args[0][0].endswith("ffmpeg") for args in self.calls) - 1
            Path(arguments[-1].replace("%d", str(self.timestamps[ordinal]))).write_bytes(self.images[ordinal])
            return b""
        if arguments[0].endswith("tesseract"):
            return self.text
        raise AssertionError("Unknown fixed tool")


@pytest.fixture
def runner(monkeypatch):
    fake = Runner()
    fake.calls = []
    monkeypatch.setattr(local, "require_isolation", lambda: None)
    monkeypatch.setattr(local, "NativeRunner", lambda: fake)
    monkeypatch.setattr(local, "runtime_identity", lambda *args: {"profile": "fixture-identity"})
    return fake


def test_extraction_literal_ocr_actual_pts_safe_projection_and_temp_cleanup(runner):
    result = local.LocalVisualProvider().extract(mp4(), "tr")
    assert result.input_sha256 == hashlib.sha256(mp4()).hexdigest()
    assert [frame.timestamp_ms for frame in result.frames] == [0, 5000]
    assert result.frames[0].text == 'PRIVATE_OCR <script>alert(1)</script>\nuser_id'
    assert "PRIVATE_OCR" not in repr(result.frames[0])
    assert "PRIVATE_OCR" not in json.dumps(result.summary())
    assert "image" not in result.frames[0].model_dump()
    assert "text" not in result.frames[0].model_dump()
    assert result.summary()["frames_with_text"] == 2
    for arguments, kwargs in runner.calls:
        if arguments[0].endswith(("ffprobe", "ffmpeg")):
            assert "-enable_drefs" in arguments and "-use_absolute_path" in arguments
            assert arguments[arguments.index("-protocol_whitelist") + 1] == "file,pipe"
        if arguments[0].endswith("ffprobe"):
            assert not Path(arguments[-1]).parent.exists()
        if arguments[0].endswith("tesseract"):
            assert arguments[arguments.index("-l") + 1] == "tur" and kwargs["content"].startswith(b"P5")


def test_exact_pixels_deduplicate_but_small_code_pixel_changes_are_kept(runner):
    runner.images = [pgm(), pgm()]
    result = local.LocalVisualProvider().extract(mp4())
    assert result.summary()["exact_duplicates_removed"] == 1
    assert sum(args[0].endswith("tesseract") for args, _ in runner.calls) == 1
    runner.calls = []
    runner.images = [pgm(), pgm()[:-1] + b"\x01"]
    assert len(local.LocalVisualProvider().extract(mp4()).frames) == 2


@pytest.mark.parametrize("timestamp", [1, 4999, 6001, 10000, -1])
def test_invalid_decoded_pts_is_rejected_even_if_pixels_duplicate(runner, timestamp):
    runner.timestamps = [0, timestamp]
    runner.images = [pgm(), pgm()]
    with pytest.raises(ValueError):
        local.LocalVisualProvider().extract(mp4())


@pytest.mark.parametrize("text", [b"\xff", b"private\x00secret", b"x" * 16001])
def test_invalid_or_oversized_ocr_fails(runner, text):
    runner.text = text
    with pytest.raises(ValueError):
        local.LocalVisualProvider().extract(mp4())


def test_missing_isolation_and_language_fail_before_decoding(monkeypatch):
    monkeypatch.setattr(local, "NativeRunner", lambda: pytest.fail("must not decode"))
    with pytest.raises(ValueError):
        local.LocalVisualProvider().extract(mp4(), "de")
    # Ordinary Linux Docker/sandbox networking may be disabled, but new socket
    # creation itself must be denied; this is a stronger fail-closed requirement.
    class Socket:
        def close(self): pass
    monkeypatch.setattr(local.socket, "socket", lambda: Socket())
    with pytest.raises(RuntimeError):
        local.LocalVisualProvider().extract(mp4())


def test_native_runner_filters_credentials_enforces_bounds_and_kills_only_owned_group(monkeypatch):
    observed = {}
    class Child:
        pid = 999_999_999
        returncode = 0
        def __init__(self, args, **kwargs):
            observed.update(args=args, **kwargs)
            kwargs["stdout"].write(b"fixture-output")
            self.fail = observed.get("timeout_once", False)
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def communicate(self, content=None, timeout=None):
            observed["timeout"] = timeout
            if self.fail:
                self.fail = False
                raise subprocess.TimeoutExpired("owned", timeout)
    monkeypatch.setenv("DEVELOPMENT_AUTH_TOKEN", "private")
    monkeypatch.setenv("DATABASE_URL", "private")
    monkeypatch.setenv("HTTP_PROXY", "private")
    monkeypatch.setattr(local.subprocess, "Popen", Child)
    runner = local.NativeRunner()
    assert runner.run(["/usr/bin/ffprobe"]) == b"fixture-output"
    assert not {"DEVELOPMENT_AUTH_TOKEN", "DATABASE_URL", "HTTP_PROXY"} & observed["env"].keys()
    assert observed["stderr"] == subprocess.DEVNULL and observed["start_new_session"]
    assert 0 < observed["timeout"] <= 15
    with pytest.raises(ValueError):
        runner.run(["/usr/bin/ffprobe"], limit=1)
    observed["timeout_once"] = True
    killed = []
    monkeypatch.setattr(local.os, "killpg", lambda pid, signal: killed.append(pid))
    with pytest.raises(RuntimeError, match="deadline"):
        runner.run(["/usr/bin/ffprobe"])
    assert killed == [Child.pid]
    runner.deadline = 0
    with pytest.raises(RuntimeError, match="deadline"):
        runner.run(["/usr/bin/ffprobe"])


def test_runtime_identity_covers_language_weights_versions_policy_and_drift(tmp_path, monkeypatch):
    monkeypatch.setattr(local, "TESSDATA", tmp_path)
    for name in ("eng", "tur"):
        (tmp_path / (name + ".traineddata")).write_bytes(name.encode())
    class Versions:
        def run(self, args, **kwargs):
            return b"ffmpeg version 5.1.9-deb12 Copyright fixture" if "ffmpeg" in args[0] else b"tesseract 5.3.0\n"
    first = local.runtime_identity(Versions(), "en+tr")
    assert first == local.runtime_identity(Versions(), "en+tr")
    (tmp_path / "tur.traineddata").write_bytes(b"new-language-data")
    assert first["profile"] != local.runtime_identity(Versions(), "en+tr")["profile"]
    (tmp_path / "tur.traineddata").unlink()
    with pytest.raises(ValueError):
        local.runtime_identity(Versions(), "en+tr")


def test_native_exec_wrapper_resource_limits_and_allowlisted_environment(monkeypatch):
    import sys
    limits, executed = {}, []
    monkeypatch.setattr(sys, "argv", ["native", "/usr/bin/ffmpeg", "-version"])
    monkeypatch.setattr(native.resource, "setrlimit", lambda key, value: limits.update({key: value}))
    monkeypatch.setattr(native.os, "execve", lambda *args: executed.append(args))
    monkeypatch.setenv("S3_SECRET_KEY", "not-in-child")
    native.main()
    assert limits[native.resource.RLIMIT_CPU] == (10, 11)
    assert limits[native.resource.RLIMIT_AS] == (1024**3, 1024**3)
    assert limits[native.resource.RLIMIT_FSIZE] == (2_000_000, 2_000_000)
    assert limits[native.resource.RLIMIT_NOFILE] == (32, 32)
    assert limits[native.resource.RLIMIT_CORE] == (0, 0)
    assert executed[0][0] == "/usr/bin/ffmpeg"
    assert "S3_SECRET_KEY" not in executed[0][2]
    executed.clear()
    monkeypatch.setattr(sys, "argv", ["native", "/bin/sh", "-c", "not-allowed"])
    with pytest.raises(ValueError):
        native.main()
    assert not executed


def test_probe_requires_rights_acknowledgement_before_reading_input(monkeypatch):
    import sys
    from app.vision import smoke
    monkeypatch.setattr(sys, "argv", ["visual-probe"])
    monkeypatch.setattr(sys, "stdin", None)
    monkeypatch.setattr(smoke, "block_outbound_sockets", lambda: pytest.fail("must not alter the process"))
    with pytest.raises(SystemExit) as result:
        smoke.main()
    assert result.value.code == 2
