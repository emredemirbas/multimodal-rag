"""Bounded PCM/WAVE inspection; no native audio decoder processes uploads."""
from dataclasses import dataclass
import struct

from ..sources.contracts import SourceError

MAX_WAV_BYTES = 20_000_000
SAMPLE_RATE = 16_000
MAX_FRAMES = SAMPLE_RATE * 600
SLICE_FRAMES = SAMPLE_RATE * 30
MAX_PCM_BYTES = SLICE_FRAMES * 2


@dataclass(frozen=True)
class WavInput:
    filename: str
    data_offset: int
    frames: int

    @property
    def duration_ms(self) -> int:
        return (self.frames * 1000 + SAMPLE_RATE - 1) // SAMPLE_RATE


def validate_wav(filename: str, content: bytes) -> WavInput:
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if not name.lower().endswith(".wav") or not 1 <= len(name) <= 255 or any(ord(char) < 32 for char in name):
        raise SourceError("invalid_audio_type", "Select a WAV file; MP3/video and URLs are not supported.")
    if not content or len(content) > MAX_WAV_BYTES:
        raise SourceError("audio_too_large", "Select a non-empty WAV file of at most 20 MB.", 413)
    if len(content) < 44 or content[:4] != b"RIFF" or content[8:12] != b"WAVE" or struct.unpack_from("<I", content, 4)[0] + 8 != len(content):
        raise SourceError("invalid_wav", "The WAV structure is invalid or incomplete; export it again.")
    offset, chunks, fmt, data = 12, 0, None, None
    while offset < len(content):
        chunks += 1
        if chunks > 64 or offset + 8 > len(content):
            raise SourceError("invalid_wav", "The WAV metadata is invalid or exceeds the chunk limit.")
        kind = content[offset:offset + 4]
        size = struct.unpack_from("<I", content, offset + 4)[0]
        start, end = offset + 8, offset + 8 + size
        if end + size % 2 > len(content):
            raise SourceError("invalid_wav", "A WAV chunk extends beyond the uploaded file.")
        if kind == b"fmt ":
            if fmt is not None or size not in {16, 18} or (size == 18 and content[start + 16:end] != b"\x00\x00"):
                raise SourceError("unsupported_wav_encoding", "Export WAV as 16-bit PCM, 16 kHz, mono.")
            fmt = struct.unpack_from("<HHIIHH", content, start)
            if fmt != (1, 1, SAMPLE_RATE, SAMPLE_RATE * 2, 2, 16):
                raise SourceError("unsupported_wav_encoding", "Export WAV as 16-bit PCM, 16 kHz, mono.")
        elif kind == b"data":
            if fmt is None or data is not None or size == 0 or size % 2:
                raise SourceError("invalid_wav", "The WAV requires one complete PCM data chunk after its format.")
            data = WavInput(name, start, size // 2)
        # Unknown metadata is skipped as bytes, never decoded as XML/HTML/URLs.
        offset = end + size % 2
    if fmt is None or data is None:
        raise SourceError("invalid_wav", "The WAV is missing its format or audio data.")
    if data.frames > MAX_FRAMES:
        raise SourceError("audio_duration_limit", "The WAV must be at most 10 minutes long.")
    return data


def pcm_slice(content: bytes, info: WavInput, offset_frames: int) -> bytes:
    if type(offset_frames) is not int or not 0 <= offset_frames < info.frames:
        raise SourceError("invalid_audio_slice", "Choose a valid audio window.")
    if info.data_offset < 0 or info.data_offset + info.frames * 2 > len(content):
        raise SourceError("invalid_audio_slice", "The audio window does not match the WAV input.")
    start = info.data_offset + offset_frames * 2
    end = info.data_offset + min(info.frames, offset_frames + SLICE_FRAMES) * 2
    return content[start:end]
