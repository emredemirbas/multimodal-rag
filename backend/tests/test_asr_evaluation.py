from __future__ import annotations

from functools import lru_cache
import hashlib
import io
import itertools
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import wave

import pytest
from pydantic import ValidationError

from app.asr import evaluate as evaluation
from app.asr import smoke
from app.asr.profile import identity


def reference(text="the cat sat on the mat", **changes):
    return evaluation.Reference.model_validate({
        "schema_version": "asr-reference-v1", "label_status": "synthetic",
        "audio_sha256": "a" * 64, "input_frames": 48_000, "language": "en",
        "text": text, **changes,
    })


def run(text="the cat sit on the", segments=None, **changes):
    return evaluation.EvaluationRun.model_validate({
        "schema_version": "asr-result-v1", "audio_sha256": "a" * 64,
        "result": {**identity(), "input_frames": 48_000, "requested_language": "auto",
            "language": "en", "language_probability": 0.9, "duration_ms": 100,
            "segments": segments if segments is not None else (
                [{"start_ms": 0, "end_ms": 2500, "text": text}] if text else []),
            **changes},
    })


def test_hand_computed_rates_and_stable_content_free_report():
    report = evaluation.evaluate(reference(), run())
    assert (report["word_errors"], report["reference_words"], report["wer"]) == (2, 6, 0.333333)
    assert (report["character_errors"], report["reference_characters"], report["cer"]) == (5, 22, 0.227273)
    assert report["quality_approval"] == "not_established"
    assert report["timing"]["coverage"] is None
    assert report["identifiers"]["recall"] is None
    assert report == evaluation.evaluate(reference(), run())
    assert "the cat" not in json.dumps(report)
    assert len(report["result_sha256"]) == len(report["reference_sha256"]) == 64
    changed = evaluation.evaluate(reference(), run(duration_ms=101))
    assert changed["result_sha256"] != report["result_sha256"]
    assert changed["reference_sha256"] == report["reference_sha256"]


def test_distance_against_independent_exhaustive_recursive_oracle():
    @lru_cache(None)
    def oracle(a, b):
        if not a or not b:
            return max(len(a), len(b))
        return min(oracle(a[1:], b) + 1, oracle(a, b[1:]) + 1,
                   oracle(a[1:], b[1:]) + (a[0] != b[0]))

    samples = ["".join(chars) for size in range(5)
               for chars in itertools.product("ab", repeat=size)]
    for a, b in itertools.product(samples, repeat=2):
        assert evaluation.edit_distance(a, b) == oracle(a, b)
        assert evaluation.edit_distance(a.split("b"), b.split("b")) == oracle(
            tuple(a.split("b")), tuple(b.split("b")))


def test_insertions_are_not_clamped_and_empty_hypothesis_counts_deletions():
    report = evaluation.evaluate(reference("a"), run("b c d"))
    assert report["wer"] == 3 and report["cer"] == 5
    empty = evaluation.evaluate(reference("hello world"), run(""))
    assert empty["wer"] == empty["cer"] == 1


@pytest.mark.parametrize("text,expected", [("", False), ("hallucinated speech", True), ("...", True)])
def test_silence_has_no_fabricated_zero_denominator_score(text, expected):
    report = evaluation.evaluate(reference(""), run(text))
    assert report["silence_reference"]
    assert report["silence_hallucination"] is expected
    assert report["wer"] is report["cer"] is None
    assert report["word_errors"] == report["hypothesis_words"]
    assert report["character_errors"] == report["hypothesis_characters"]


def test_normalization_preserves_turkish_diacritics_identifiers_and_word_boundaries():
    assert evaluation.words("IŞIK, İŞLEM! user_id", "tr") == ["ışık", "işlem", "user_id"]
    assert evaluation.words("ÇAĞRI C\u0327AG\u0306RI", "tr") == ["çağrı", "çağrı"]
    assert evaluation.words("end point", "en") != evaluation.words("endpoint", "en")
    assert evaluation.words("ş ı", "tr") != evaluation.words("s i", "tr")
    assert evaluation.words("ＦａｓｔＡＰＩ", "en") != evaluation.words("FastAPI", "en")
    perfect = evaluation.evaluate(reference("IŞIK İŞLEM", language="tr"), run("ışık işlem", language="tr"))
    assert perfect["wer"] == perfect["cer"] == 0
    mismatch = evaluation.evaluate(reference("ışık", language="tr"), run("ışık", language="en"))
    assert not mismatch["language_matches_reference"] and mismatch["wer"] == 0


def test_identifiers_are_literal_case_sensitive_delimited_and_never_printed():
    expected = reference("Use FastAPI /health user_id and x.y", identifiers=["FastAPI", "/health", "user_id", "x.y"])
    report = evaluation.evaluate(expected, run("Use fastapi health user_id and x.y"))
    assert report["wer"] == 0
    assert report["identifiers"] == {"total": 4, "matched": 2, "recall": 0.5}
    serialized = json.dumps(report)
    assert all(item not in serialized for item in expected.identifiers)
    assert not evaluation.has_identifier("NotFastAPI user_id_extra", "FastAPI")
    assert not evaluation.has_identifier("user_id_extra", "user_id")
    assert not evaluation.has_identifier("xay", "x.y")
    assert evaluation.has_identifier("(FastAPI)", "FastAPI")


def test_timing_matches_phrase_across_cues_and_reports_enclosing_boundaries():
    expected = reference("hello local audio world", anchors=[
        {"start_ms": 200, "end_ms": 1600, "text": "local audio"},
    ], timing_tolerance_ms=100)
    result = run(segments=[
        {"start_ms": 100, "end_ms": 800, "text": "hello local"},
        {"start_ms": 900, "end_ms": 1700, "text": "audio world"},
    ])
    timing = evaluation.evaluate(expected, result)["timing"]
    assert timing == {
        "method": "unique-phrase-enclosing-cue-v1", "total": 1, "scored": 1,
        "missing": 0, "ambiguous": 0, "coverage": 1.0, "tolerance_ms": 100,
        "within_tolerance": 1, "within_tolerance_fraction_all_labels": 1.0,
        "mean_start_error_ms": 100.0, "mean_end_error_ms": 100.0,
        "max_boundary_error_ms": 100,
    }


def test_missing_and_ambiguous_timing_never_masquerade_as_perfect_scores():
    expected = reference("hello world missing", anchors=[
        {"start_ms": 0, "end_ms": 500, "text": "hello"},
        {"start_ms": 500, "end_ms": 1000, "text": "missing"},
    ], timing_tolerance_ms=250)
    timing = evaluation.evaluate(expected, run("hello hello"))["timing"]
    assert (timing["scored"], timing["ambiguous"], timing["missing"]) == (0, 1, 1)
    assert timing["coverage"] == timing["within_tolerance_fraction_all_labels"] == 0
    assert timing["mean_start_error_ms"] is timing["max_boundary_error_ms"] is None


def test_timing_denominator_includes_missing_labels_and_unscored_is_not_zero_error():
    expected = reference("hello missing", anchors=[
        {"start_ms": 0, "end_ms": 1000, "text": "hello"},
        {"start_ms": 1000, "end_ms": 2000, "text": "missing"},
    ], timing_tolerance_ms=0)
    result = run(segments=[{"start_ms": 0, "end_ms": 1000, "text": "hello"}])
    timing = evaluation.evaluate(expected, result)["timing"]
    assert timing["coverage"] == timing["within_tolerance_fraction_all_labels"] == 0.5
    assert timing["scored"] == timing["missing"] == 1


@pytest.mark.parametrize("changes", [
    {"identifiers": ["absent"]}, {"identifiers": ["cat", "cat"]},
    {"identifiers": ["the cat"]}, {"identifiers": ["\x00"]},
    {"text": "..."}, {"text": " "}, {"text": "secret\x00"}, {"text": "\ud800"},
    {"input_frames": True}, {"input_frames": 480_001}, {"language": "de"},
    {"label_status": "certified"}, {"audio_sha256": "not-a-hash"},
    {"extra": "forbidden"}, {"timing_tolerance_ms": 250},
    {"anchors": [{"start_ms": 0, "end_ms": 1000, "text": "cat"}]},
    {"anchors": [{"start_ms": 0, "end_ms": 4000, "text": "cat"}], "timing_tolerance_ms": 250},
    {"anchors": [{"start_ms": 0, "end_ms": 1000, "text": "the"}], "timing_tolerance_ms": 250},
    {"anchors": [{"start_ms": 0, "end_ms": 1000, "text": "absent"}], "timing_tolerance_ms": 250},
    {"anchors": [{"start_ms": 0, "end_ms": 1000, "text": "cat"},
                 {"start_ms": 500, "end_ms": 1500, "text": "mat"}], "timing_tolerance_ms": 250},
])
def test_invalid_reference_labels_are_rejected(changes):
    with pytest.raises(ValidationError):
        reference(**changes)


def test_binding_and_mutated_instances_are_revalidated():
    candidate = run()
    candidate.audio_sha256 = "b" * 64
    with pytest.raises(ValueError, match="binding mismatch"):
        evaluation.evaluate(reference(), candidate)
    with pytest.raises(ValueError, match="binding mismatch"):
        evaluation.evaluate(reference(input_frames=16_000), run())
    candidate = run()
    candidate.result.segments[0].end_ms = 4000
    with pytest.raises(ValidationError):
        evaluation.evaluate(reference(), candidate)
    expected = reference()
    expected.identifiers.append("not-in-reference")
    with pytest.raises(ValidationError):
        evaluation.evaluate(expected, run())


def test_model_profile_and_invalid_native_timeline_fail_closed():
    for change in [{"profile": "other-profile"}, {"language_probability": float("nan")},
                   {"segments": [{"start_ms": 0, "end_ms": 4000, "text": "outside"}]}]:
        with pytest.raises(ValidationError):
            run(**change)


def test_alignment_work_is_bounded_before_any_scoring(monkeypatch):
    with pytest.raises(ValueError, match="work limit"):
        evaluation.edit_distance("a" * 3000, "a" * 3000)
    monkeypatch.setattr(evaluation, "edit_distance", lambda *_: pytest.fail("must preflight total work"))
    with pytest.raises(ValueError, match="work limit"):
        evaluation.evaluate(reference("a" * 4000), run("a" * 2000))


@pytest.mark.parametrize("payload", [
    b'{"text":"one","text":"two"}', b'{"nested":{"same":1,"same":2}}',
    b'{"value":NaN}', b'{"value":Infinity}', b'\xff', b'{broken', b'{"x":' + b'[' * 1100,
    b' ' * (evaluation.MAX_JSON_BYTES + 1),
])
def test_json_bounds_duplicates_and_nonfinite_values(tmp_path, payload):
    path = tmp_path / "input.json"
    path.write_bytes(payload)
    with pytest.raises((ValueError, RecursionError)):
        evaluation.load_json(path)


def test_fixture_cli_and_safe_failure_output(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    fixture = backend / "tests" / "fixtures" / "asr-evaluation"
    command = [sys.executable, "-m", "app.asr.evaluate", "--reference", str(fixture / "reference.json"),
               "--result", str(fixture / "result.json")]
    result = subprocess.run(command, cwd=tmp_path, env={"PYTHONPATH": str(backend)},
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0 and not result.stderr
    report = json.loads(result.stdout)
    assert report["label_status"] == "synthetic"
    assert report["wer"] == 0.25 and report["identifiers"]["recall"] == 0
    assert report["timing"]["coverage"] == 0
    bad = tmp_path / "PRIVATE_FILENAME.json"
    bad.write_text('{"PRIVATE_TEXT": "not valid reference"}')
    command[4] = str(bad)
    failure = subprocess.run(command, cwd=tmp_path, env={"PYTHONPATH": str(backend)},
                             capture_output=True, text=True, timeout=15)
    assert failure.returncode == 1 and not failure.stdout
    assert all(value not in failure.stderr for value in ["PRIVATE_FILENAME", "PRIVATE_TEXT", "Traceback"])


def wav_bytes():
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes(b"\x00\x00" * 48_000)
    return output.getvalue()


def test_native_reference_hash_is_checked_before_calling_provider(tmp_path, monkeypatch):
    path = tmp_path / "reference.json"
    path.write_text(reference().model_dump_json())
    monkeypatch.setattr(sys, "argv", ["probe", "--reference", str(path)])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(wav_bytes())))
    monkeypatch.setattr(smoke, "LocalAsrProvider", lambda: pytest.fail("mismatched WAV must not reach ASR"))
    with pytest.raises(ValueError, match="exact WAV"):
        smoke.main()


def test_exact_audio_binding_checks_frames_and_bytes():
    content = wav_bytes()
    expected = reference(audio_sha256=hashlib.sha256(content).hexdigest())
    evaluation.verify_audio(expected, content, 48_000)
    for audio, frames in [(content, 47_999), (content + b"different", 48_000)]:
        with pytest.raises(ValueError, match="exact WAV"):
            evaluation.verify_audio(expected, audio, frames)


def test_probe_diagnostics_are_mutually_exclusive_before_reading_audio(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["probe", "--synthetic-health-check", "--reference", "ref.json"])
    monkeypatch.setattr(sys, "stdin", None)
    with pytest.raises(SystemExit) as result:
        smoke.main()
    assert result.value.code == 2


def test_native_reference_probe_scores_one_actual_protocol_result_without_export(tmp_path, monkeypatch, capsys):
    content = wav_bytes()
    digest = hashlib.sha256(content).hexdigest()
    expected = reference("hello PRIVATE_REFERENCE", audio_sha256=digest)
    path = tmp_path / "reference.json"
    path.write_text(expected.model_dump_json())
    monkeypatch.setattr(sys, "argv", ["probe", "--reference", str(path), "--language", "tr"])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(content)))
    calls = []

    class Provider:
        def transcribe(self, pcm, language):
            calls.append((len(pcm), language))
            return run("hello PRIVATE_RESULT", language="tr", requested_language="tr").result

    monkeypatch.setattr(smoke, "LocalAsrProvider", Provider)
    smoke.main()
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert calls == [(96_000, "tr")]
    assert report["wer"] == 0.5 and not report["language_matches_reference"]
    assert report["input_binding"] == "verified-wav-bytes"
    assert "PRIVATE" not in output.out and not output.err


def test_ordinary_smoke_retains_its_content_free_contract(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["probe"])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(wav_bytes())))
    monkeypatch.setattr(smoke, "LocalAsrProvider", lambda: SimpleNamespace(transcribe=lambda *_: run().result))
    smoke.main()
    report = json.loads(capsys.readouterr().out)
    assert report["outcome"] == "passed" and report["synthetic_check"] is False
    assert "wer" not in report and "the cat" not in json.dumps(report)
