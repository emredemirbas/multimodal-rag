"""Explicit local, single-clip diagnostics; never a model-quality certificate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Annotated, Literal, Sequence
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import SpeechSegment, TranscriptionSlice
from .wav import SAMPLE_RATE, SLICE_FRAMES

NORMALIZATION = "nfc-en-tr-words-v1"
MAX_JSON_BYTES = 131_072
MAX_EDIT_CELLS = 8_000_000
Digest = Annotated[str, Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")]
Identifier = Annotated[str, Field(min_length=1, max_length=128)]


def words(text: str, language: str) -> list[str]:
    text = unicodedata.normalize("NFC", text)
    if language == "tr":
        text = text.replace("I", "ı").replace("İ", "i")
    text = text.casefold()
    return "".join(
        char if char == "_" or unicodedata.category(char)[0] in "LNM" else " "
        for char in text
    ).split()


def has_identifier(text: str, identifier: str) -> bool:
    # Delimited literal spelling, not a parser or a substring/casefold match.
    return re.search(r"(?<!\w)" + re.escape(identifier) + r"(?!\w)", text) is not None


def occurrences(tokens: list[str], phrase: list[str]) -> list[int]:
    return [index for index in range(len(tokens) - len(phrase) + 1)
            if tokens[index:index + len(phrase)] == phrase]


class Reference(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    schema_version: Literal["asr-reference-v1"]
    label_status: Literal["synthetic", "unreviewed", "human_reviewed"]
    audio_sha256: Digest
    input_frames: int = Field(ge=1, le=SLICE_FRAMES)
    language: Literal["en", "tr"]
    text: str = Field(max_length=4000)
    identifiers: list[Identifier] = Field(default_factory=list, max_length=32)
    anchors: list[SpeechSegment] = Field(default_factory=list, max_length=16)
    timing_tolerance_ms: int | None = Field(default=None, ge=0, le=5000)

    @model_validator(mode="after")
    def valid_labels(self):
        tokens = words(self.text, self.language)
        if self.text and not tokens:
            raise ValueError("A silence reference must be the empty string")
        if any(unicodedata.category(char) in {"Cs", "Cc"} and char not in "\n\r\t"
               for char in self.text):
            raise ValueError("Reference contains invalid controls")
        if len(set(self.identifiers)) != len(self.identifiers) or any(
            any(char.isspace() or unicodedata.category(char)[0] == "C" for char in item)
            or not has_identifier(self.text, item) for item in self.identifiers
        ):
            raise ValueError("Identifiers must be distinct literal reference tokens")
        if bool(self.anchors) != (self.timing_tolerance_ms is not None):
            raise ValueError("Timing labels require an explicit tolerance, and vice versa")
        duration = (self.input_frames * 1000 + SAMPLE_RATE - 1) // SAMPLE_RATE
        previous_end = 0
        for anchor in self.anchors:
            phrase = words(anchor.text, self.language)
            if (not phrase or len(occurrences(tokens, phrase)) != 1
                    or anchor.start_ms < previous_end or anchor.end_ms > duration):
                raise ValueError("Timing labels require unique phrases and ordered in-clip bounds")
            previous_end = anchor.end_ms
        return self


class EvaluationRun(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    schema_version: Literal["asr-result-v1"]
    audio_sha256: Digest
    result: TranscriptionSlice


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _invalid_number(_):
    raise ValueError("Non-finite JSON number")


def load_json(path: Path) -> dict:
    # Bound the actual read, not only a possibly stale filesystem size.
    with path.open("rb") as stream:
        data = stream.read(MAX_JSON_BYTES + 1)
    if len(data) > MAX_JSON_BYTES:
        raise ValueError("Evaluation input is too large")
    return json.loads(data.decode("utf-8"), object_pairs_hook=_unique_fields,
                      parse_constant=_invalid_number)


def load_reference(path: Path) -> Reference:
    return Reference.model_validate(load_json(path))


def verify_audio(reference: Reference, content: bytes, input_frames: int) -> None:
    if (reference.input_frames != input_frames
            or reference.audio_sha256 != hashlib.sha256(content).hexdigest()):
        raise ValueError("Reference does not describe this exact WAV")


def edit_distance(reference: Sequence, hypothesis: Sequence) -> int:
    """Unit-cost Levenshtein distance, with a linear-space bounded work table."""
    if len(reference) * len(hypothesis) > MAX_EDIT_CELLS:
        raise ValueError("Alignment work limit exceeded; use a shorter labeled clip")
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for row, expected in enumerate(reference, 1):
        current = [row]
        for column, actual in enumerate(hypothesis, 1):
            current.append(min(previous[column] + 1, current[-1] + 1,
                               previous[column - 1] + (expected != actual)))
        previous = current
    return previous[-1]


def _rate(errors: int, count: int) -> float | None:
    return round(errors / count, 6) if count else None


def evaluate(reference: Reference, run: EvaluationRun) -> dict:
    # Revalidate mutated instances as well as documents loaded by the CLI.
    reference = Reference.model_validate(reference.model_dump())
    run = EvaluationRun.model_validate(run.model_dump())
    result = run.result
    if (reference.audio_sha256 != run.audio_sha256
            or reference.input_frames != result.input_frames):
        raise ValueError("Reference/result input binding mismatch")
    recognized = " ".join(segment.text for segment in result.segments)
    expected_words = words(reference.text, reference.language)
    actual_words = words(recognized, reference.language)
    expected_chars, actual_chars = " ".join(expected_words), " ".join(actual_words)
    cells = (len(expected_words) * len(actual_words)
             + len(expected_chars) * len(actual_chars))
    if cells > MAX_EDIT_CELLS:
        raise ValueError("Alignment work limit exceeded; use a shorter labeled clip")
    word_errors = edit_distance(expected_words, actual_words)
    character_errors = edit_distance(expected_chars, actual_chars)
    hits = sum(has_identifier(recognized, item) for item in reference.identifiers)

    token_cues = []
    cue_tokens = []
    for index, segment in enumerate(result.segments):
        tokens = words(segment.text, reference.language)
        cue_tokens.extend(tokens)
        token_cues.extend([index] * len(tokens))
    start_errors, end_errors, within = [], [], 0
    missing = ambiguous = 0
    for anchor in reference.anchors:
        phrase = words(anchor.text, reference.language)
        matches = occurrences(cue_tokens, phrase)
        if not matches:
            missing += 1
            continue
        if len(matches) != 1:
            ambiguous += 1
            continue
        first = result.segments[token_cues[matches[0]]]
        last = result.segments[token_cues[matches[0] + len(phrase) - 1]]
        start, end = abs(first.start_ms - anchor.start_ms), abs(last.end_ms - anchor.end_ms)
        start_errors.append(start)
        end_errors.append(end)
        within += int(max(start, end) <= reference.timing_tolerance_ms)
    scored, total = len(start_errors), len(reference.anchors)
    return {
        "schema_version": "asr-evaluation-v1",
        "evaluation_kind": "single_clip_diagnostic",
        "quality_approval": "not_established",
        "input_binding": "declared-reference-result",
        "label_status": reference.label_status,
        "normalization": NORMALIZATION,
        "reference_sha256": hashlib.sha256(json.dumps(reference.model_dump(mode="json"),
            sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest(),
        "audio_sha256": run.audio_sha256,
        "result_sha256": hashlib.sha256(json.dumps(run.model_dump(mode="json"),
            sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest(),
        "provider": result.provider, "model": result.model, "revision": result.revision,
        "profile": result.profile, "engine": result.engine,
        "input_frames": result.input_frames, "inference_duration_ms": result.duration_ms,
        "reference_language": reference.language, "requested_language": result.requested_language,
        "detected_language": result.language,
        "language_matches_reference": result.language == reference.language,
        "reference_words": len(expected_words), "hypothesis_words": len(actual_words),
        "word_errors": word_errors, "wer": _rate(word_errors, len(expected_words)),
        "reference_characters": len(expected_chars), "hypothesis_characters": len(actual_chars),
        "character_errors": character_errors, "cer": _rate(character_errors, len(expected_chars)),
        "silence_reference": not expected_words,
        "silence_hallucination": bool(not expected_words and recognized.strip()),
        "identifiers": {"total": len(reference.identifiers), "matched": hits,
                        "recall": _rate(hits, len(reference.identifiers))},
        "timing": {
            "method": "unique-phrase-enclosing-cue-v1", "total": total, "scored": scored,
            "missing": missing, "ambiguous": ambiguous, "coverage": _rate(scored, total),
            "tolerance_ms": reference.timing_tolerance_ms, "within_tolerance": within,
            "within_tolerance_fraction_all_labels": _rate(within, total),
            "mean_start_error_ms": _rate(sum(start_errors), scored),
            "mean_end_error_ms": _rate(sum(end_errors), scored),
            "max_boundary_error_ms": max(start_errors + end_errors, default=None),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    options = parser.parse_args()
    report = evaluate(load_reference(options.reference),
                      EvaluationRun.model_validate(load_json(options.result)))
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("FAIL: ASR evaluation input or measurement; no text, paths or raw exception was logged.") from None
