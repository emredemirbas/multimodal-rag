"""Explicit local OCR/retained-frame diagnostics, never quality certification."""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal
import unicodedata

from pydantic import Field, model_validator

from ..evaluation import MAX_EDIT_CELLS, NORMALIZATION, edit_distance, has_identifier, words
from .contracts import MAX_RESPONSE_BYTES, SHA256, StrictModel, WireResult
from .media import MAX_DURATION_MS, MAX_FRAMES, MAX_VIDEO_BYTES, VideoInfo, unique_json

MAX_REFERENCE_BYTES = 131_072
MAX_RESULT_BYTES = MAX_RESPONSE_BYTES + 1024
LITERAL_NORMALIZATION = "nfc-case-sensitive-v1"
Digest = Annotated[str, Field(min_length=64, max_length=64, pattern=SHA256)]
Identifier = Annotated[str, Field(min_length=1, max_length=128)]


class Interval(StrictModel):
    start_ms: int = Field(ge=0, lt=MAX_DURATION_MS)
    end_ms: int = Field(gt=0, le=MAX_DURATION_MS)
    language: Literal["en", "tr"]
    text: str = Field(repr=False, max_length=4000)
    identifiers: list[Identifier] = Field(default_factory=list, repr=False, max_length=32)

    @model_validator(mode="after")
    def valid_annotation(self):
        if self.end_ms <= self.start_ms or (self.text and not self.text.strip()):
            raise ValueError("Use positive intervals and an empty string for blank labels")
        if any(unicodedata.category(char) in {"Cc", "Cs"} and char not in "\n\r\t"
               for char in self.text):
            raise ValueError("Invalid annotation text")
        if len(set(self.identifiers)) != len(self.identifiers) or any(
            any(char.isspace() or unicodedata.category(char)[0] == "C" for char in item)
            or not has_identifier(self.text, item) for item in self.identifiers
        ):
            raise ValueError("Identifiers must be distinct literal annotation tokens")
        return self


class Reference(StrictModel):
    schema_version: Literal["visual-reference-v1"]
    label_status: Literal["synthetic", "unreviewed", "human_reviewed"]
    input_sha256: Digest
    input_bytes: int = Field(ge=24, le=MAX_VIDEO_BYTES)
    video: VideoInfo
    intervals: list[Interval] = Field(repr=False, min_length=1, max_length=MAX_FRAMES)

    @model_validator(mode="after")
    def valid_timeline(self):
        previous_end = 0
        if not 1 <= Fraction(self.video.fps_numerator, self.video.fps_denominator) <= 60:
            raise ValueError("Unsupported annotated frame rate")
        for interval in self.intervals:
            if interval.start_ms < previous_end or interval.end_ms > self.video.duration_ms:
                raise ValueError("Use ordered disjoint in-video annotation intervals")
            previous_end = interval.end_ms
        return self


class EvaluationRun(StrictModel):
    schema_version: Literal["visual-result-v1"]
    input_bytes: int = Field(ge=24, le=MAX_VIDEO_BYTES)
    result: WireResult = Field(repr=False)


def load_json(path: Path, limit: int):
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Visual evaluation document exceeds its limit")
    return unique_json(data)


def load_reference(path: Path) -> Reference:
    return Reference.model_validate(load_json(path, MAX_REFERENCE_BYTES))


def verify_video(reference: Reference, content: bytes) -> None:
    reference = Reference.model_validate(reference.model_dump())
    if (type(content) is not bytes or len(content) != reference.input_bytes
            or hashlib.sha256(content).hexdigest() != reference.input_sha256):
        raise ValueError("Reference does not describe these exact MP4 bytes")


def _digest(value: StrictModel) -> str:
    return hashlib.sha256(json.dumps(value.model_dump(mode="json"), sort_keys=True,
        separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _units(expected: str, actual: str, language: str):
    expected_words, actual_words = words(expected, language), words(actual, language)
    return ((expected_words, actual_words),
            (" ".join(expected_words), " ".join(actual_words)),
            (unicodedata.normalize("NFC", expected), unicodedata.normalize("NFC", actual)))


def _empty_counts():
    return {"scored_frames": 0, "reference_words": 0, "hypothesis_words": 0, "word_errors": 0,
        "reference_characters": 0, "hypothesis_characters": 0, "character_errors": 0,
        "literal_reference_characters": 0, "literal_hypothesis_characters": 0,
        "literal_character_errors": 0, "identifier_labels": 0, "identifier_matches": 0,
        "blank_reference_frames": 0, "blank_with_text": 0}


def _scores(counts):
    return {**counts, "wer": _rate(counts["word_errors"], counts["reference_words"]),
        "cer": _rate(counts["character_errors"], counts["reference_characters"]),
        "literal_cer": _rate(counts["literal_character_errors"], counts["literal_reference_characters"]),
        "identifier_recall": _rate(counts["identifier_matches"], counts["identifier_labels"])}


def evaluate(reference: Reference, run: EvaluationRun) -> dict:
    # Roundtrip also revalidates mutable nested models/lists and PNG/profile data.
    reference = Reference.model_validate(reference.model_dump())
    run = EvaluationRun.model_validate(run.model_dump())
    result = run.result
    if (reference.input_sha256 != result.input_sha256 or reference.input_bytes != run.input_bytes
            or reference.video != result.video):
        raise ValueError("Reference/result input or video binding mismatch")

    # Preflight the whole diagnostic before doing any quadratic alignments.
    paired, cells = [], 0
    for ordinal, interval in enumerate(reference.intervals):
        frames = [frame for frame in result.frames
                  if interval.start_ms <= frame.timestamp_ms < interval.end_ms]
        pairs = []
        for frame in frames:
            units = _units(interval.text, frame.text, interval.language)
            cells += sum(len(expected) * len(actual) for expected, actual in units)
            pairs.append((frame, units))
        paired.append((ordinal, interval, pairs))
    if cells > MAX_EDIT_CELLS:
        raise ValueError("Alignment work limit exceeded; use fewer or shorter labels")

    totals, intervals = _empty_counts(), []
    for ordinal, interval, pairs in paired:
        frames = []
        for frame, units in pairs:
            (ew, aw), (ec, ac), (el, al) = units
            counts = {"scored_frames": 1, "reference_words": len(ew), "hypothesis_words": len(aw),
                "word_errors": edit_distance(ew, aw), "reference_characters": len(ec),
                "hypothesis_characters": len(ac), "character_errors": edit_distance(ec, ac),
                "literal_reference_characters": len(el), "literal_hypothesis_characters": len(al),
                "literal_character_errors": edit_distance(el, al),
                "identifier_labels": len(interval.identifiers),
                "identifier_matches": sum(has_identifier(frame.text, item) for item in interval.identifiers),
                "blank_reference_frames": int(interval.text == ""),
                "blank_with_text": int(interval.text == "" and bool(frame.text.strip()))}
            for key, value in counts.items():
                totals[key] += value
            frames.append({"timestamp_ms": frame.timestamp_ms, "image_sha256": frame.image_sha256,
                           "ocr": _scores(counts)})
        intervals.append({"ordinal": ordinal, "start_ms": interval.start_ms, "end_ms": interval.end_ms,
            "language": interval.language, "requested_language_compatible": result.identity.language in
                {interval.language, "en+tr"}, "selected_frame_count": len(frames), "frames": frames})
    covered = sum(bool(pairs) for _, _, pairs in paired)
    return {"schema_version": "visual-evaluation-v1", "evaluation_kind": "single_clip_diagnostic",
        "quality_approval": "not_established", "input_binding": "declared-reference-result",
        "label_status": reference.label_status, "reference_sha256": _digest(reference),
        "result_sha256": _digest(run), "input_sha256": result.input_sha256,
        "input_bytes": run.input_bytes, "identity": result.identity.model_dump(),
        "video": result.video.model_dump(), "candidates": result.candidates,
        "selected_frames": len(result.frames), "exact_duplicates_removed": result.candidates - len(result.frames),
        "normalization": NORMALIZATION, "literal_normalization": LITERAL_NORMALIZATION,
        "aggregation": "micro-over-all-labeled-retained-frames; missed-intervals-excluded-from-ocr",
        "sampling": {"method": "retained-pts-in-labeled-interval-v1", "labeled_intervals": len(paired),
            "covered_intervals": covered, "missed_intervals": len(paired) - covered,
            "interval_coverage": _rate(covered, len(paired)), "labeled_frames": totals["scored_frames"],
            "unlabeled_frames": len(result.frames) - totals["scored_frames"]},
        "ocr": _scores(totals), "intervals": intervals}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    options = parser.parse_args()
    report = evaluate(load_reference(options.reference),
        EvaluationRun.model_validate(load_json(options.result, MAX_RESULT_BYTES)))
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("FAIL: visual evaluation input or measurement; no frames, OCR, labels, paths or raw exception was logged.") from None
