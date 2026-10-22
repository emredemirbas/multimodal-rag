"""Deterministic derived text, not source publication or a quality certificate."""
from dataclasses import dataclass
import hashlib
from html import escape
import json

from pydantic import ValidationError

from ..sources.chunking import chunk_transcript
from ..sources.contracts import SourceError
from .contracts import TranscriptionSlice
from .profile import PROFILE, encode_result
from .wav import MAX_FRAMES, SLICE_FRAMES

ASSEMBLY_VERSION = 'asr-vtt-v1'


def validated_slice(value: dict | TranscriptionSlice) -> TranscriptionSlice:
    try:
        # Revalidate even an already constructed/mutated model; never trust a
        # Pydantic instance's old validation or a caller's retained list reference.
        payload = value.model_dump(mode='json') if isinstance(value, TranscriptionSlice) else value
        data = encode_result(payload)
        return TranscriptionSlice.model_validate(json.loads(data))
    except (ValidationError, ValueError, TypeError, UnicodeError, OverflowError):
        raise SourceError('invalid_asr_checkpoint', 'The saved speech result could not be validated.', 503) from None


def result_digest(result: TranscriptionSlice) -> str:
    payload = result.model_dump(mode='json')
    # JSONB uses PostgreSQL numeric semantics, which do not retain IEEE -0.0.
    # Both legal zero probabilities must produce the same durable checksum.
    if payload['language_probability'] == 0:
        payload['language_probability'] = 0.0
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class DerivedTranscript:
    content: bytes
    sha256: str
    input_frames: int
    windows: int
    segments: int
    model_duration_ms: int
    profile: str = PROFILE
    assembly_version: str = ASSEMBLY_VERSION
    machine_generated: bool = True


def _timestamp(milliseconds: int) -> str:
    seconds, remainder = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}.{remainder:03d}'


def assemble_vtt(results: list[TranscriptionSlice], input_frames: int) -> DerivedTranscript:
    if (type(input_frames) is not int or not 1 <= input_frames <= MAX_FRAMES
            or len(results) != (input_frames + SLICE_FRAMES - 1) // SLICE_FRAMES):
        raise SourceError('asr_checkpoint_incomplete', 'All audio windows must be saved before assembling a transcript.', 409)
    parts = ['WEBVTT', '', 'NOTE Machine-generated local speech recognition; inspect against the original.', '']
    segments, duration, requested_language = 0, 0, None
    for ordinal, untrusted in enumerate(results):
        result = validated_slice(untrusted)
        if (result.input_frames != min(SLICE_FRAMES, input_frames - ordinal * SLICE_FRAMES)
                or requested_language is not None and result.requested_language != requested_language):
            raise SourceError('invalid_asr_checkpoint', 'Audio windows do not match the pinned input and language.', 503)
        requested_language = result.requested_language
        duration += result.duration_ms
        for segment in result.segments:
            # Flatten cue separators/timing-like text and remove non-whitespace
            # C0 controls. Escape before writing VTT; the existing parser decodes
            # entities once, preserving code/HTML-like evidence as literal text.
            text = ' '.join(''.join(char if ord(char) >= 32 or char in '\n\r\t' else ' '
                                    for char in segment.text).split())
            if not text:
                raise SourceError('invalid_asr_checkpoint', 'Speech text was empty after normalization.', 503)
            offset = ordinal * 30_000
            parts.extend([f'{_timestamp(offset + segment.start_ms)} --> {_timestamp(offset + segment.end_ms)}', escape(text, quote=False), ''])
            segments += 1
    if not segments:
        raise SourceError('no_speech_detected', 'No speech was recognized; provide a corrected authorized transcript instead.')
    content = ('\n'.join(parts) + '\n').encode('utf-8')
    if len(content) > 2_000_000:
        raise SourceError('derived_transcript_limit', 'The derived transcript exceeds the existing subtitle limit.')
    chunk_transcript(content)  # Do not return an artifact the indexing path cannot parse.
    return DerivedTranscript(content, hashlib.sha256(content).hexdigest(), input_frames, len(results), segments, duration)
