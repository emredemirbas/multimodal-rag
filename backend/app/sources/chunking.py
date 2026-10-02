from dataclasses import dataclass
import hashlib
from uuid import UUID, NAMESPACE_URL, uuid5

from ..transcripts import TranscriptParseError, parse_transcript
from .contracts import SourceError

PROCESSING_VERSION = 'transcript-chunks-v1'


@dataclass(frozen=True)
class Chunk:
    start_ms: int
    end_ms: int
    text: str
    cue_start: int
    cue_end: int


def decode_transcript(content: bytes) -> str:
    try:
        decoded = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise SourceError('invalid_encoding', 'Save the transcript as UTF-8 or UTF-8 with BOM.') from None
    if '\x00' in decoded or any(ord(char) < 32 and char not in '\n\r\t' for char in decoded):
        raise SourceError('invalid_encoding', 'Upload a text SRT/VTT file, not binary media.')
    return decoded


def chunk_transcript(content: bytes, *, max_characters: int = 1200, max_duration_ms: int = 60000) -> list[Chunk]:
    try:
        cues = parse_transcript(decode_transcript(content))
    except TranscriptParseError:
        raise SourceError('invalid_transcript', 'Check SRT/VTT cue timestamps and subtitle text, then upload a corrected file.') from None
    if len(cues) > 20000:
        raise SourceError('transcript_limit', 'Split the transcript into files with at most 20,000 cues.')
    chunks: list[Chunk] = []
    current: Chunk | None = None
    previous_start = -1
    for index, cue in enumerate(cues):
        if cue.start_ms < previous_start or cue.end_ms - cue.start_ms > max_duration_ms:
            raise SourceError('invalid_timeline', 'Keep cues in timestamp order and each cue under 60 seconds.')
        previous_start = cue.start_ms
        # Bound long cues without breaking code identifiers in the middle.
        parts: list[str] = []
        part = ''
        for word in cue.text.split():
            if len(word) > max_characters:
                raise SourceError('invalid_transcript', 'A subtitle token is too long; split the cue text.')
            if part and len(part) + len(word) + 1 > max_characters:
                parts.append(part)
                part = ''
            part = f'{part} {word}'.strip()
        if part:
            parts.append(part)
        for part in parts:
            boundary = current is not None and (
                len(current.text) + len(part) + 1 > max_characters
                or cue.end_ms - current.start_ms > max_duration_ms
                or cue.start_ms - current.end_ms > 8000
                or (len(current.text) >= 300 and current.text.endswith(('.', '?', '!')))
            )
            if boundary:
                chunks.append(current)
                current = None
            if current is None:
                current = Chunk(cue.start_ms, cue.end_ms, part, index, index)
            else:
                current = Chunk(current.start_ms, max(current.end_ms, cue.end_ms), f'{current.text} {part}', current.cue_start, index)
    if current:
        chunks.append(current)
    if len(chunks) > 10000:
        raise SourceError('transcript_limit', 'Split this transcript into smaller files.')
    return chunks


def segment_id(source_id: UUID, generation: int, chunk: Chunk, ordinal: int = 0) -> UUID:
    digest = hashlib.sha256(chunk.text.encode()).hexdigest()
    return uuid5(NAMESPACE_URL, f'{source_id}:{generation}:{PROCESSING_VERSION}:{ordinal}:{chunk.cue_start}:{chunk.cue_end}:{chunk.start_ms}:{chunk.end_ms}:{digest}')
