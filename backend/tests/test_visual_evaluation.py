from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.vision import evaluate as evaluation, smoke
from app.vision.contracts import WireResult
from app.vision.media import POLICY, encode_png


VIDEO = {"duration_ms": 20000, "width": 960, "height": 540,
         "fps_numerator": 2, "fps_denominator": 1}


def reference(text="Use FastAPI /health", intervals=None, **changes):
    return evaluation.Reference.model_validate({
        "schema_version": "visual-reference-v1", "label_status": "synthetic",
        "input_sha256": "a" * 64, "input_bytes": 1000, "video": VIDEO,
        "intervals": intervals if intervals is not None else [
            {"start_ms": 0, "end_ms": 20000, "language": "en", "text": text}], **changes})


def run(texts=("Use fastapi health", "Use FastAPI /health"), stamps=(0, 10000), language="en"):
    identity = {"provider": "local-ffmpeg-tesseract", "engines": {"ffmpeg": "5.1.9", "tesseract": "5.3.0"},
        "language_data": {"eng": "b" * 64, "tur": "c" * 64}, "language": language, "policy": POLICY}
    identity["profile"] = "local-visual-v1:" + hashlib.sha256(json.dumps(identity,
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    frames = []
    for ordinal, (stamp, text) in enumerate(zip(stamps, texts, strict=True)):
        png = encode_png(16, 16, bytes([ordinal]) * 256)
        frames.append({"sample_target_ms": stamp // 5000 * 5000, "timestamp_ms": stamp,
            "width": 16, "height": 16, "image_sha256": hashlib.sha256(png).hexdigest(),
            "image_base64": base64.b64encode(png).decode(), "text": text})
    return evaluation.EvaluationRun.model_validate({"schema_version": "visual-result-v1",
        "input_bytes": 1000, "result": {"input_sha256": "a" * 64, "video": VIDEO,
            "identity": identity, "candidates": 4, "frames": frames}})


def test_every_frame_scored_without_best_result_selection():
    labels = reference(intervals=[{"start_ms": 0, "end_ms": 20000, "language": "en",
        "text": "Use FastAPI /health", "identifiers": ["FastAPI", "/health"]}])
    report = evaluation.evaluate(labels, run())
    scores = report["ocr"]
    assert scores["scored_frames"] == 2 and scores["reference_words"] == 6
    assert scores["wer"] == scores["cer"] == 0  # Deliberately permissive prose normalization.
    # Four case changes in FastAPI and one omitted slash.
    assert scores["literal_character_errors"] == 5 and scores["literal_reference_characters"] == 38
    assert scores["literal_cer"] == 0.131579
    assert (scores["identifier_labels"], scores["identifier_matches"], scores["identifier_recall"]) == (4, 2, .5)
    assert report["sampling"]["interval_coverage"] == 1
    assert report["quality_approval"] == "not_established"
    assert report == evaluation.evaluate(labels, run())
    serialized = json.dumps(report)
    assert all(value not in serialized for value in ["Use FastAPI", "/health", "image_base64", "fastapi health"])


def test_half_open_actual_pts_coverage_missing_and_unlabeled_frames():
    intervals = [
        {"start_ms": 0, "end_ms": 1, "text": "a", "language": "en"},
        {"start_ms": 9000, "end_ms": 10000, "text": "missed", "language": "en"},
        {"start_ms": 10000, "end_ms": 10001, "text": "b", "language": "tr"}]
    report = evaluation.evaluate(reference(intervals=intervals), run(("a", "b")))
    assert report["sampling"] == {"method": "retained-pts-in-labeled-interval-v1",
        "labeled_intervals": 3, "covered_intervals": 2, "missed_intervals": 1,
        "interval_coverage": .666667, "labeled_frames": 2, "unlabeled_frames": 0}
    assert [item["selected_frame_count"] for item in report["intervals"]] == [1, 0, 1]
    assert not report["intervals"][2]["requested_language_compatible"]
    # Actual PTS 10,500, not its requested sample 10,000, determines the label.
    shifted = evaluation.evaluate(reference(intervals=intervals), run(("a", "b"), stamps=(0, 10500)))
    assert shifted["sampling"]["covered_intervals"] == shifted["sampling"]["unlabeled_frames"] == 1


def test_all_missed_intervals_have_null_ocr_not_perfect_score():
    report = evaluation.evaluate(reference(intervals=[
        {"start_ms": 6000, "end_ms": 7000, "language": "en", "text": "missing"}]), run())
    assert report["sampling"]["interval_coverage"] == 0
    assert report["sampling"]["unlabeled_frames"] == 2
    assert report["ocr"]["scored_frames"] == 0
    assert report["ocr"]["wer"] is report["ocr"]["literal_cer"] is report["ocr"]["identifier_recall"] is None


def test_insertions_deletions_and_rates_above_one():
    scores = evaluation.evaluate(reference("a"), run(("b c d", "")))["ocr"]
    assert (scores["word_errors"], scores["reference_words"], scores["wer"]) == (4, 2, 2)
    assert scores["character_errors"] == 6 and scores["cer"] == 3
    assert scores["literal_cer"] == 3


@pytest.mark.parametrize("text,unexpected", [("", 0), ("...", 1), ("unwanted OCR", 1)])
def test_blank_labels_have_null_rates_and_visible_insertions(text, unexpected):
    scores = evaluation.evaluate(reference(""), run((text,), stamps=(0,)))["ocr"]
    assert scores["blank_reference_frames"] == 1 and scores["blank_with_text"] == unexpected
    assert scores["wer"] is scores["cer"] is scores["literal_cer"] is None
    assert scores["literal_character_errors"] == len(text)


def test_punctuation_only_labels_are_scored_literally():
    scores = evaluation.evaluate(reference("():"), run(("()",), stamps=(0,)))["ocr"]
    assert scores["wer"] is scores["cer"] is None
    assert scores["literal_cer"] == .333333
    assert scores["blank_reference_frames"] == 0


def test_turkish_nfc_case_punctuation_and_line_breaks_remain_separate():
    labels = reference(intervals=[{"start_ms": 0, "end_ms": 20000,
        "language": "tr", "text": "IŞIK İŞLEM\nuser_id()", "identifiers": ["user_id"]}])
    report = evaluation.evaluate(labels, run(("ışık işlem user_id", "IŞIK İŞLEM\nuser_id()"), language="en+tr"))
    assert report["ocr"]["wer"] == report["ocr"]["cer"] == 0
    assert report["ocr"]["literal_cer"] > 0 and report["ocr"]["identifier_recall"] == 1
    assert report["intervals"][0]["requested_language_compatible"]
    equivalent = evaluation.evaluate(reference("ÇAĞRI"), run(("C\u0327AG\u0306RI",), stamps=(0,)))
    assert equivalent["ocr"]["literal_cer"] == 0


@pytest.mark.parametrize("changes", [
    {"intervals": []}, {"intervals": [{"start_ms": True, "end_ms": 1, "language": "en", "text": "x"}]},
    {"input_bytes": True}, {"input_bytes": 100_000_001}, {"input_sha256": "bad"},
    {"label_status": "approved"}, {"extra": 1},
    {"video": {**VIDEO, "fps_numerator": 61}},
])
def test_invalid_reference_shape(changes):
    with pytest.raises(ValidationError):
        reference(**changes)


@pytest.mark.parametrize("changes", [
    {"text": " "}, {"text": "private\x00"}, {"text": "\ud800"},
    {"text": "a" * 4001}, {"language": "en+tr"}, {"start_ms": 5, "end_ms": 5},
    {"end_ms": 20001}, {"identifiers": ["missing"]}, {"identifiers": ["Use", "Use"]},
    {"identifiers": ["user id"]}, {"identifiers": ["\x00"]},
])
def test_invalid_intervals_and_literal_identifiers(changes):
    with pytest.raises(ValidationError):
        reference(intervals=[{"start_ms": 0, "end_ms": 20000, "language": "en",
            "text": "Use FastAPI /health", **changes}])


def test_interval_overlap_order_and_max_count():
    interval = {"start_ms": 0, "end_ms": 2, "language": "en", "text": "a"}
    for intervals in [[interval, interval], [interval, {**interval, "start_ms": 1}], [interval] * 21]:
        with pytest.raises(ValidationError):
            reference(intervals=intervals)
    reference(intervals=[{**interval, "start_ms": i * 2, "end_ms": i * 2 + 2} for i in range(20)])


def test_input_and_metadata_binding_and_mutable_nested_models():
    value = run().model_dump()
    for changes in [{"input_bytes": 999}, {"result": {**value["result"], "input_sha256": "f" * 64}},
                    {"result": {**value["result"], "video": {**VIDEO, "width": 1920}}}]:
        candidate = evaluation.EvaluationRun.model_validate({**value, **changes})
        with pytest.raises(ValueError, match="binding mismatch"):
            evaluation.evaluate(reference(), candidate)
    candidate = run()
    candidate.result.video.duration_ms = 9000
    with pytest.raises(ValidationError):
        evaluation.evaluate(reference(), candidate)
    labels = reference()
    labels.intervals[0].identifiers.append("not-present")
    with pytest.raises(ValidationError):
        evaluation.evaluate(labels, run())


@pytest.mark.parametrize("field,value", [("text", "bad\x00"), ("image_sha256", "f" * 64),
    ("timestamp_ms", 20000), ("image_base64", "not base64")])
def test_bad_wire_result_fails_closed(field, value):
    candidate = run().model_dump()
    candidate["result"]["frames"][0][field] = value
    with pytest.raises(ValidationError):
        evaluation.EvaluationRun.model_validate(candidate)


def test_work_limit_is_total_across_frames_and_literal_metric_before_scoring(monkeypatch):
    # Each alignment fits on its own; sum of normalized + literal across frames does not.
    monkeypatch.setattr(evaluation, "edit_distance", lambda *_: pytest.fail("must preflight total work"))
    with pytest.raises(ValueError, match="work limit"):
        evaluation.evaluate(reference("a" * 1500), run(("a" * 1500, "a" * 1500)))


@pytest.mark.parametrize("payload", [b'{"a":1,"a":2}', b'{"nested":{"a":1,"a":2}}',
    b'{"x":NaN}', b'{"x":Infinity}', b'\xff', b'{broken', b'[' * 1100,
    b' ' * (evaluation.MAX_REFERENCE_BYTES + 1)])
def test_strict_bounded_json_reader(tmp_path, payload):
    path = tmp_path / "input.json"
    path.write_bytes(payload)
    with pytest.raises((ValueError, RecursionError)):
        evaluation.load_json(path, evaluation.MAX_REFERENCE_BYTES)


def test_fingerprints_change_without_publishing_text():
    labels, candidate = reference(), run()
    original = evaluation.evaluate(labels, candidate)
    changed = evaluation.evaluate(reference("PRIVATE_LABEL"), candidate)
    assert original["reference_sha256"] != changed["reference_sha256"]
    assert original["result_sha256"] == changed["result_sha256"]
    assert "PRIVATE_LABEL" not in json.dumps(changed) and "PRIVATE_LABEL" not in repr(reference("PRIVATE_LABEL"))


def test_fixture_cli_and_safe_failure(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    fixture = backend / "tests/fixtures/visual-evaluation"
    command = [sys.executable, "-m", "app.vision.evaluate", "--reference", str(fixture / "reference.json"),
        "--result", str(fixture / "result.json")]
    result = subprocess.run(command, cwd=tmp_path, env={"PYTHONPATH": str(backend)},
        capture_output=True, text=True, timeout=15)
    assert result.returncode == 0 and not result.stderr
    report = json.loads(result.stdout)
    assert report["sampling"]["interval_coverage"] == .666667
    assert report["ocr"]["identifier_recall"] == 0 and report["ocr"]["blank_with_text"] == 1
    assert report["input_binding"] == "declared-reference-result"
    bad = tmp_path / "PRIVATE_FILENAME.json"
    bad.write_text('{"PRIVATE_LABEL":"bad"}')
    command[4] = str(bad)
    failure = subprocess.run(command, cwd=tmp_path, env={"PYTHONPATH": str(backend)},
        capture_output=True, text=True, timeout=15)
    assert failure.returncode == 1 and not failure.stdout
    assert not any(item in failure.stderr for item in ["PRIVATE_FILENAME", "PRIVATE_LABEL", "Traceback"])


def test_native_hash_and_byte_count_checked_before_isolation_or_provider(tmp_path, monkeypatch):
    path = tmp_path / "reference.json"
    path.write_text(reference().model_dump_json())
    monkeypatch.setattr(sys, "argv", ["probe", "--authorized-input", "--reference", str(path)])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"x" * 1000)))
    monkeypatch.setattr(smoke, "block_outbound_sockets", lambda: pytest.fail("bad binding before native setup"))
    monkeypatch.setattr(smoke, "LocalVisualProvider", lambda: pytest.fail("bad binding before native work"))
    with pytest.raises(ValueError, match="exact MP4"):
        smoke.main()
    content = b"x" * 1000
    good = reference(input_sha256=hashlib.sha256(content).hexdigest())
    evaluation.verify_video(good, content)
    with pytest.raises(ValueError):
        evaluation.verify_video(good, content + b"x")


def test_native_reference_runs_one_provider_after_binding_and_isolation(tmp_path, monkeypatch, capsys):
    content = b"x" * 1000
    digest = hashlib.sha256(content).hexdigest()
    path = tmp_path / "reference.json"
    path.write_text(reference("PRIVATE_LABEL", input_sha256=digest).model_dump_json())
    monkeypatch.setattr(sys, "argv", ["probe", "--authorized-input", "--language", "tr", "--reference", str(path)])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(content)))
    calls = []
    monkeypatch.setattr(smoke, "block_outbound_sockets", lambda: calls.append("isolated"))
    class Provider:
        def extract(self, data, language):
            calls.append((data, language))
            wire = run(("PRIVATE_OCR", ""), language=language).result.model_dump()
            wire["input_sha256"] = digest
            return WireResult.model_validate(wire).result()
    monkeypatch.setattr(smoke, "LocalVisualProvider", Provider)
    smoke.main()
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert calls == ["isolated", (content, "tr")]
    assert report["input_binding"] == "verified-mp4-bytes" and report["quality_approval"] == "not_established"
    assert "PRIVATE" not in output.out and not output.err


def test_mutually_exclusive_diagnostics_and_required_rights_before_reads(monkeypatch):
    monkeypatch.setattr(sys, "stdin", None)
    for args in [["--reference", "private.json"], ["--authorized-input", "--reference", "private.json", "--synthetic-card-check"]]:
        monkeypatch.setattr(sys, "argv", ["probe", *args])
        with pytest.raises(SystemExit) as outcome:
            smoke.main()
        assert outcome.value.code == 2


def test_ordinary_smoke_keeps_summary_contract(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["probe", "--authorized-input"])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"fixture")))
    monkeypatch.setattr(smoke, "block_outbound_sockets", lambda: None)
    monkeypatch.setattr(smoke, "LocalVisualProvider", lambda: SimpleNamespace(extract=lambda *_: run().result.result()))
    smoke.main()
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["outcome"] == "component-complete" and not report["synthetic_check"]
    assert "ocr" not in report and "Use FastAPI" not in output.out
