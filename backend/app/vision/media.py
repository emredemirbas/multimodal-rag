"""Bounded container/metadata/pixel inspection without a native media decoder."""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
from fractions import Fraction
import hashlib
import json
import re
import struct
import zlib

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_VIDEO_BYTES = 100_000_000
MAX_DURATION_MS = 600_000
MAX_FRAMES = 20
MAX_PIXELS = 960 * 540
MAX_IMAGE_BYTES = 600_000
POLICY = "visual-uniform5s-cap20-gray960x540-exact-pixels-png-v1"


def validate_mp4(content: bytes) -> None:
    if not isinstance(content, bytes) or not 24 <= len(content) <= MAX_VIDEO_BYTES:
        raise ValueError("Use an authorized nonempty MP4 of at most 100 MB")
    offset, kinds = 0, []
    while offset < len(content):
        if len(kinds) >= 64 or offset + 8 > len(content):
            raise ValueError("Invalid MP4 box table")
        size, kind = struct.unpack_from(">I4s", content, offset)
        header = 8
        if size == 1:
            if offset + 16 > len(content):
                raise ValueError("Truncated extended box")
            size, header = struct.unpack_from(">Q", content, offset + 8)[0], 16
        if size < header or offset + size > len(content):
            raise ValueError("Invalid MP4 box extent")
        if kind not in {b"ftyp", b"moov", b"mdat", b"free", b"skip", b"wide"}:
            raise ValueError("Unsupported or fragmented MP4")
        if kind == b"ftyp":
            if offset != 0 or not header + 8 <= size <= 256 or (size - header) % 4:
                raise ValueError("Invalid MP4 brand table")
            if content[offset + header:offset + header + 4] not in {b"isom", b"iso2", b"mp41", b"mp42", b"avc1"}:
                raise ValueError("Unsupported MP4 brand")
        if kind in {b"moov", b"mdat"} and size <= header:
            raise ValueError("Empty MP4 data")
        kinds.append(kind)
        offset += size
    if kinds[0] != b"ftyp" or kinds.count(b"ftyp") != 1 or kinds.count(b"moov") != 1 or not 1 <= kinds.count(b"mdat") <= 8:
        raise ValueError("MP4 requires one header and complete media")


def unique_json(data: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate metadata field")
            result[key] = value
        return result
    def invalid(_):
        raise ValueError("Non-finite metadata")
    return json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid)


def milliseconds(value) -> int:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValueError("Missing time metadata")
    number = Decimal(value)
    if not number.is_finite() or not 0 <= number <= 600:
        raise ValueError("Invalid time metadata")
    return int((number * 1000).to_integral_value(rounding=ROUND_CEILING))


class VideoInfo(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    duration_ms: int = Field(gt=0, le=MAX_DURATION_MS)
    width: int = Field(ge=16, le=1920)
    height: int = Field(ge=16, le=1080)
    fps_numerator: int = Field(gt=0, le=1_000_000_000)
    fps_denominator: int = Field(gt=0, le=1_000_000_000)


def parse_probe(data: bytes) -> VideoInfo:
    if len(data) > 32_768:
        raise ValueError("Metadata exceeds limit")
    document = unique_json(data)
    streams = document["streams"]
    if not isinstance(streams, list) or not 1 <= len(streams) <= 2:
        raise ValueError("Use one video and optional AAC audio")
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(videos) != 1 or len(audio) > 1 or len(videos) + len(audio) != len(streams):
        raise ValueError("Unsupported streams")
    video = videos[0]
    if (video.get("codec_name") != "h264" or video.get("codec_tag_string") != "avc1"
            or video.get("pix_fmt") != "yuv420p" or video.get("side_data_list")
            or any(stream.get("codec_name") != "aac" for stream in audio)):
        raise ValueError("Use unrotated H.264/avc1 yuv420p and optional AAC")
    if milliseconds(document["format"]["start_time"]) or milliseconds(video["start_time"]):
        raise ValueError("Use a zero-based timeline")
    container_duration = milliseconds(document["format"]["duration"])
    duration = milliseconds(video["duration"])
    if not duration or container_duration < duration:
        raise ValueError("Invalid media duration")
    rates = [video.get(key) for key in ("avg_frame_rate", "r_frame_rate")]
    if any(not isinstance(value, str) or not 1 <= len(value) <= 64 for value in rates):
        raise ValueError("Missing frame rate")
    fps, nominal = (Fraction(value) for value in rates)
    if not 1 <= fps <= 60 or fps != nominal:
        raise ValueError("Use constant 1–60 fps input")
    return VideoInfo(duration_ms=duration, width=video["width"], height=video["height"],
                     fps_numerator=fps.numerator, fps_denominator=fps.denominator)


def sample_times(duration_ms: int) -> list[int]:
    if type(duration_ms) is not int or not 1 <= duration_ms <= MAX_DURATION_MS:
        raise ValueError("Invalid video duration")
    count = min(MAX_FRAMES, (duration_ms + 4999) // 5000)
    return [index * duration_ms // count for index in range(count)]


def parse_pgm(data: bytes) -> tuple[int, int, bytes]:
    # FFmpeg's fixed P5 output, never a generic/unbounded image decoder.
    match = re.match(rb"P5\n([1-9][0-9]{0,3}) ([1-9][0-9]{0,3})\n255\n", data)
    if not match:
        raise ValueError("Invalid grayscale image")
    width, height = (int(value) for value in match.groups())
    if width > 960 or height > 540 or len(data) != match.end() + width * height:
        raise ValueError("Image geometry/byte bound exceeded")
    return width, height, data[match.end():]


def encode_png(width: int, height: int, pixels: bytes) -> bytes:
    if type(width) is not int or type(height) is not int or not 1 <= width <= 960 or not 1 <= height <= 540 or len(pixels) != width * height:
        raise ValueError("Invalid PNG input")
    def chunk(kind, value):
        return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value))
    rows = b"".join(b"\x00" + pixels[index:index + width] for index in range(0, len(pixels), width))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))


class FrameEvidence(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    sample_target_ms: int = Field(ge=0, lt=MAX_DURATION_MS)
    timestamp_ms: int = Field(ge=0, lt=MAX_DURATION_MS)
    width: int = Field(ge=1, le=960)
    height: int = Field(ge=1, le=540)
    image: bytes = Field(repr=False, exclude=True, min_length=1, max_length=MAX_IMAGE_BYTES)
    text: str = Field(repr=False, exclude=True, max_length=16_000)

    @model_validator(mode="after")
    def valid_timestamp(self):
        if not self.sample_target_ms <= self.timestamp_ms <= self.sample_target_ms + 1000:
            raise ValueError("Decoded PTS does not match the requested neighborhood")
        return self

    @property
    def image_sha256(self) -> str:
        return hashlib.sha256(self.image).hexdigest()
