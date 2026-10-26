"""Bounded private wire format; never log serialized OCR/image payloads."""
from __future__ import annotations

import base64
from fractions import Fraction
import hashlib
import json
import struct
from typing import Literal
import unicodedata
import zlib

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .media import (MAX_FRAMES, MAX_IMAGE_BYTES, POLICY, FrameEvidence, VideoInfo,
                    sample_times, unique_json)

Language = Literal["en", "tr", "en+tr"]
MAX_RESPONSE_BYTES = 18_000_000
SHA256 = r"^[0-9a-f]{64}$"


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class Engines(StrictModel):
    ffmpeg: str = Field(pattern=r"^[0-9A-Za-z.+~:-]{1,64}$")
    tesseract: str = Field(pattern=r"^[0-9A-Za-z.+~:-]{1,64}$")


class LanguageData(StrictModel):
    eng: str = Field(pattern=SHA256)
    tur: str = Field(pattern=SHA256)


class VisualIdentity(StrictModel):
    provider: Literal["local-ffmpeg-tesseract"]
    engines: Engines
    language_data: LanguageData
    language: Language
    policy: Literal[POLICY]
    profile: str = Field(pattern=r"^local-visual-v1:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def profile_matches(self):
        digest = hashlib.sha256(json.dumps(self.model_dump(exclude={"profile"}),
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if self.profile != "local-visual-v1:" + digest:
            raise ValueError("Visual profile does not match its identity")
        return self


def checked_png(image: bytes, width: int, height: int) -> bytes:
    """Only our three-chunk grayscale PNG subset; bounded zlib, no native decoder."""
    if (type(width) is not int or type(height) is not int or not 1 <= width <= 960 or not 1 <= height <= 540
            or not 1 <= len(image) <= MAX_IMAGE_BYTES or image[:8] != b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Invalid frame image")
    offset, chunks = 8, []
    for expected in (b"IHDR", b"IDAT", b"IEND"):
        if offset + 12 > len(image):
            raise ValueError("Truncated frame image")
        size, kind = struct.unpack_from(">I4s", image, offset)
        end = offset + 8 + size
        if kind != expected or end + 4 > len(image):
            raise ValueError("Unsupported frame image")
        data = image[offset + 8:end]
        if zlib.crc32(kind + data) != struct.unpack_from(">I", image, end)[0]:
            raise ValueError("Corrupt frame image")
        chunks.append(data)
        offset = end + 4
    if (offset != len(image) or chunks[2] or chunks[0] != struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)):
        raise ValueError("Frame geometry or encoding mismatch")
    expected_size = (width + 1) * height
    decoder = zlib.decompressobj()
    try:
        rows = decoder.decompress(chunks[1], expected_size + 1)
    except zlib.error:
        raise ValueError("Invalid compressed frame image") from None
    if (len(rows) != expected_size or not decoder.eof or decoder.unconsumed_tail
            or decoder.unused_data or any(rows[index] != 0 for index in range(0, expected_size, width + 1))):
        raise ValueError("Invalid or oversized decoded image")
    return b"".join(rows[index + 1:index + width + 1] for index in range(0, expected_size, width + 1))


class WireFrame(StrictModel):
    sample_target_ms: int = Field(ge=0, lt=600_000)
    timestamp_ms: int = Field(ge=0, lt=600_000)
    width: int = Field(ge=1, le=960)
    height: int = Field(ge=1, le=540)
    image_sha256: str = Field(pattern=SHA256)
    image_base64: str = Field(repr=False, min_length=1, max_length=800_000)
    text: str = Field(repr=False, max_length=16_000)

    @model_validator(mode="after")
    def validate_evidence(self):
        image = base64.b64decode(self.image_base64, validate=True)
        if base64.b64encode(image).decode("ascii") != self.image_base64:
            raise ValueError("Noncanonical image encoding")
        checked_png(image, self.width, self.height)
        if hashlib.sha256(image).hexdigest() != self.image_sha256:
            raise ValueError("Frame digest mismatch")
        if not self.sample_target_ms <= self.timestamp_ms <= self.sample_target_ms + 1000:
            raise ValueError("Frame timestamp mismatch")
        if any(unicodedata.category(char) in {"Cc", "Cs"} and char not in "\n\r\t" for char in self.text):
            raise ValueError("Invalid OCR text")
        return self

    def evidence(self) -> FrameEvidence:
        return FrameEvidence(sample_target_ms=self.sample_target_ms, timestamp_ms=self.timestamp_ms,
            width=self.width, height=self.height, image=base64.b64decode(self.image_base64), text=self.text)


class WireResult(StrictModel):
    protocol: Literal["local-visual-http-v1"] = "local-visual-http-v1"
    input_sha256: str = Field(pattern=SHA256)
    identity: VisualIdentity
    video: VideoInfo
    candidates: int = Field(ge=1, le=MAX_FRAMES)
    frames: list[WireFrame] = Field(repr=False, min_length=1, max_length=MAX_FRAMES)

    @model_validator(mode="after")
    def validate_timeline(self):
        times = sample_times(self.video.duration_ms)
        if self.candidates != len(times) or not 1 <= Fraction(self.video.fps_numerator, self.video.fps_denominator) <= 60:
            raise ValueError("Invalid candidate count or frame rate")
        targets = [frame.sample_target_ms for frame in self.frames]
        stamps = [frame.timestamp_ms for frame in self.frames]
        if (targets[0] != 0 or targets != sorted(set(targets)) or not set(targets) <= set(times)
                or stamps != sorted(set(stamps)) or stamps[-1] >= self.video.duration_ms):
            raise ValueError("Invalid frame selection or timeline")
        seen = set()
        for frame in self.frames:
            pixels = checked_png(base64.b64decode(frame.image_base64), frame.width, frame.height)
            fingerprint = (frame.width, frame.height, hashlib.sha256(pixels).digest())
            if fingerprint in seen:
                raise ValueError("Duplicate decoded frame")
            seen.add(fingerprint)
        return self

    @classmethod
    def from_result(cls, result):
        return cls.model_validate({"input_sha256": result.input_sha256, "identity": result.identity,
            "video": result.info.model_dump(), "candidates": result.candidates,
            "frames": [{"sample_target_ms": f.sample_target_ms, "timestamp_ms": f.timestamp_ms,
                "width": f.width, "height": f.height, "image_sha256": f.image_sha256,
                "image_base64": base64.b64encode(f.image).decode("ascii"), "text": f.text}
                for f in result.frames]})

    def result(self):
        from .local import VisualResult
        return VisualResult(self.input_sha256, self.video, self.identity.model_dump(), self.candidates,
                            tuple(frame.evidence() for frame in self.frames))


def encode_wire(value: StrictModel | dict) -> bytes:
    data = json.dumps(value.model_dump() if isinstance(value, StrictModel) else value,
                      ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("Visual response exceeds limit")
    return data


def decode_wire(data: bytes):
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("Visual response exceeds limit")
    return unique_json(data)
