from __future__ import annotations

import pytest

from app.models import FrameCandidate
from app.transcripts import TranscriptParseError, parse_transcript, select_novel_frames


def test_parses_webvtt_and_removes_tags() -> None:
    cues = parse_transcript(
        """WEBVTT

00:00:01.000 --> 00:00:03.500
Create a <b>FastAPI</b> application.

00:03.500 --> 00:00:05.000
Run it with Uvicorn.
"""
    )

    assert [(cue.start_ms, cue.end_ms, cue.text) for cue in cues] == [
        (1_000, 3_500, "Create a FastAPI application."),
        (3_500, 5_000, "Run it with Uvicorn."),
    ]


def test_parses_srt_timestamp_commas() -> None:
    cues = parse_transcript(
        """1
00:00:02,000 --> 00:00:04,250
Use the health endpoint.
"""
    )
    assert cues[0].start_ms == 2_000
    assert cues[0].end_ms == 4_250


def test_rejects_empty_or_invalid_transcript() -> None:
    with pytest.raises(TranscriptParseError):
        parse_transcript("WEBVTT\n\nThis has no timing line")
    with pytest.raises(TranscriptParseError):
        parse_transcript("WEBVTT\n\n00:99:00.000 --> 00:99:01.000\nInvalid time")


def test_frame_selection_deduplicates_and_discards_empty_frames() -> None:
    selected = select_novel_frames(
        [
            FrameCandidate(timestamp_seconds=1, ocr_text="", description="blank"),
            FrameCandidate(timestamp_seconds=2, ocr_text="GET /health", description="API docs"),
            FrameCandidate(timestamp_seconds=3, ocr_text="GET /health", description="API docs"),
            FrameCandidate(timestamp_seconds=4, ocr_text="200 OK", description="JSON response"),
        ]
    )
    assert [frame.timestamp_seconds for frame in selected] == [2, 4]
