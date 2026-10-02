from __future__ import annotations

from html import unescape
import re

from .models import FrameCandidate, TranscriptCue


TIMING_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?[,.]\d{3})\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}(?::\d{2})?[,.]\d{3})"
)
# Strip known subtitle/HTML presentation tags, not code such as Foo<T> or x < y > z.
# Unrecognized text remains untrusted evidence and is always escaped by renderers.
TAG_RE = re.compile(
    r"</?(?:b|i|u|c(?:\.[\w-]+)*|v|lang|span|em|strong|p|br|s|code|pre|ruby|rt|"
    r"script|style|img|svg|div|h[1-6])(?:\s[^<>]*)?>|<\d{1,2}:\d{2}(?::\d{2})?\.\d{3}>",
    re.IGNORECASE,
)
TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


class TranscriptParseError(ValueError):
    pass


def timestamp_to_ms(value: str) -> int:
    normalized = value.replace(",", ".")
    pieces = normalized.split(":")
    if len(pieces) == 2:
        hours = 0
        minutes, seconds = pieces
    elif len(pieces) == 3:
        hours, minutes, seconds = pieces
    else:
        raise TranscriptParseError(f"invalid timestamp: {value}")
    whole_seconds, milliseconds = seconds.split(".")
    if int(minutes) >= 60 or int(whole_seconds) >= 60:
        raise TranscriptParseError(f"invalid timestamp: {value}")
    return (
        int(hours) * 3_600_000
        + int(minutes) * 60_000
        + int(whole_seconds) * 1_000
        + int(milliseconds)
    )


def clean_cue_text(lines: list[str]) -> str:
    text = " ".join(line.strip() for line in lines if line.strip())
    def strip_presentation(match: re.Match) -> str:
        # An opening tag immediately after an identifier may be a generic type.
        if not match.group().startswith("</") and match.start() and text[match.start()-1].isalnum():
            return match.group()
        return ""
    return " ".join(unescape(TAG_RE.sub(strip_presentation, text)).split())


def parse_transcript(content: str) -> list[TranscriptCue]:
    lines = content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues: list[TranscriptCue] = []
    index = 0

    while index < len(lines):
        timing_match = TIMING_RE.search(lines[index])
        if timing_match is None:
            index += 1
            continue

        start_ms = timestamp_to_ms(timing_match.group("start"))
        end_ms = timestamp_to_ms(timing_match.group("end"))
        if end_ms <= start_ms:
            raise TranscriptParseError("cue end must be after cue start")

        index += 1
        text_lines: list[str] = []
        while index < len(lines) and lines[index].strip():
            text_lines.append(lines[index])
            index += 1

        text = clean_cue_text(text_lines)
        if text:
            cues.append(TranscriptCue(start_ms=start_ms, end_ms=end_ms, text=text))

    if not cues:
        raise TranscriptParseError("no valid transcript cues were found")
    return cues


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(value) if len(token) > 1}


def select_novel_frames(
    candidates: list[FrameCandidate],
    *,
    similarity_threshold: float = 0.85,
    limit: int = 120,
) -> list[FrameCandidate]:
    """Keep meaningful, textually novel frame evidence in timeline order.

    Sprint 0 accepts pre-extracted frame candidates. Binary media extraction belongs
    to the isolated media worker introduced later; this function validates the
    selection/deduplication contract without processing untrusted media in the API.
    """

    selected: list[FrameCandidate] = []
    selected_tokens: list[set[str]] = []
    for candidate in sorted(candidates, key=lambda item: item.timestamp_seconds):
        tokens = _tokens(f"{candidate.ocr_text} {candidate.description}")
        if len(tokens) < 2:
            continue
        duplicate = False
        for previous in selected_tokens[-5:]:
            union = tokens | previous
            similarity = len(tokens & previous) / len(union) if union else 1.0
            if similarity >= similarity_threshold:
                duplicate = True
                break
        if duplicate:
            continue
        selected.append(candidate)
        selected_tokens.append(tokens)
        if len(selected) >= limit:
            break
    return selected
