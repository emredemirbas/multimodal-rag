import base64
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
from types import SimpleNamespace
import zlib

import pytest

from app.vision import compare as comparison
from app.vision.contracts import WireResult
from app.vision.evaluate import EvaluationRun, Reference
from app.vision.media import encode_png
from test_visual_selection import change_result
from test_visual_service import content, identity


def paired():
    changed = change_result().model_dump()
    changed['frames'][0]['text'] = 'Use user_id'
    first = deepcopy(changed['frames'][0])
    first['text'] = 'Use user_ID'
    image = encode_png(16, 16, bytes([128]) * 256)
    second = {**first, 'sample_target_ms': 5000, 'timestamp_ms': 5000,
        'image_sha256': hashlib.sha256(image).hexdigest(), 'image_base64': base64.b64encode(image).decode()}
    before = {**changed, 'protocol': 'local-visual-http-v1', 'identity': identity().model_dump(),
        'candidates': 4, 'frames': [first, second]}
    before.pop('selection')
    reference = Reference.model_validate({'schema_version': 'visual-reference-v1', 'label_status': 'synthetic',
        'input_sha256': changed['input_sha256'], 'input_bytes': len(content()), 'video': changed['video'],
        'intervals': [{'start_ms': start, 'end_ms': end, 'language': 'en', 'text': 'Use user_id', 'identifiers': ['user_id']}
            for start, end in [(0, 1000), (3000, 4000), (5000, 6000), (9000, 10000), (19000, 20000)]]})
    def run(value):
        return EvaluationRun.model_validate({'schema_version': 'visual-result-v1', 'input_bytes': len(content()), 'result': value})
    return reference, run(before), run(changed)


def test_coverage_tradeoffs_and_identical_point_ocr_do_not_hide_losses_or_weighting():
    report = comparison.compare(*paired())
    assert report['coverage_changes'] == {'gained_ordinals': [1, 4], 'lost_ordinals': [2],
        'shared_ordinals': [0], 'missed_by_both_ordinals': [3]}
    shared = report['common_image_ocr']
    assert shared['timestamps_ms'] == [0]
    assert shared['uniform']['scored_frames'] == shared['change']['scored_frames'] == 1
    assert shared['uniform']['wer'] == shared['change']['wer'] == 0
    assert shared['uniform']['literal_character_errors'] == 2
    assert shared['change']['literal_cer'] == 0
    assert shared['uniform']['identifier_recall'] == 0 and shared['change']['identifier_recall'] == 1
    assert report['quality_approval'] == 'not_established' and 'winner' not in report
    assert 'PRIVATE_OCR' not in json.dumps(report) and 'Use user_id' not in json.dumps(report)


def test_different_png_compression_with_identical_pixels_is_a_valid_pair():
    reference, uniform, change = paired()
    row = change.model_dump()
    image = encode_png(16, 16, bytes(256))
    # Preserve the bounded three-chunk PNG shape with a different valid zlib stream.
    payload = zlib.compress((b'\0' * 17) * 16, level=0)
    chunk = struct.pack('>I', len(payload)) + b'IDAT' + payload + struct.pack('>I', zlib.crc32(b'IDAT' + payload))
    image = image[:33] + chunk + image[-12:]
    row['result']['frames'][0].update(image_base64=base64.b64encode(image).decode(), image_sha256=hashlib.sha256(image).hexdigest())
    assert comparison.compare(reference, uniform, EvaluationRun.model_validate(row))['common_image_ocr']['timestamps_ms'] == [0]


def test_pair_uses_one_label_snapshot_even_if_callers_mutate_the_original(monkeypatch):
    reference, uniform, change = paired()
    prepare, calls = comparison._prepare, []
    def mutate_after_first(labels, run):
        result = prepare(labels, run)
        calls.append(1)
        if len(calls) == 1: reference.intervals.clear()
        return result
    monkeypatch.setattr(comparison, '_prepare', mutate_after_first)
    report = comparison.compare(reference, uniform, change)
    assert report['measurements']['uniform']['reference_sha256'] == report['measurements']['change']['reference_sha256']
    assert report['measurements']['change']['sampling']['labeled_intervals'] == 5


def test_conflicting_shared_pixels_fail_before_either_result_is_scored(monkeypatch):
    reference, uniform, change = paired()
    row = change.model_dump()
    image = encode_png(16, 16, bytes([1]) * 256)
    row['result']['frames'][0].update(image_base64=base64.b64encode(image).decode(), image_sha256=hashlib.sha256(image).hexdigest())
    monkeypatch.setattr(comparison, '_measure', lambda *_: pytest.fail('Must reject before scoring'))
    with pytest.raises(ValueError, match='Conflicting pixels'):
        comparison.compare(reference, uniform, EvaluationRun.model_validate(row))


@pytest.mark.parametrize('kind', ['order', 'engine', 'language', 'input', 'bytes', 'metadata', 'mutated'])
def test_invalid_pair_identity_binding_or_mutation_is_not_a_comparison(kind):
    reference, uniform, change = paired()
    if kind == 'order':
        with pytest.raises(ValueError): comparison.compare(reference, change, uniform)
        return
    if kind == 'mutated':
        change.result.selection.samples.pop()
        with pytest.raises(ValueError): comparison.compare(reference, uniform, change)
        return
    row = change.model_dump()
    if kind in {'engine', 'language'}:
        pin = row['result']['identity']
        if kind == 'engine': pin['engines']['ffmpeg'] = '5.1.10'
        else: pin['language'] = 'tr'
        pin['profile'] = 'local-visual-v2:' + hashlib.sha256(json.dumps(
            {key: value for key, value in pin.items() if key != 'profile'}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    elif kind == 'input': row['result']['input_sha256'] = 'f' * 64
    elif kind == 'bytes': row['input_bytes'] += 1
    else: row['result']['video']['width'] = 1920
    with pytest.raises(ValueError): comparison.compare(reference, uniform, EvaluationRun.model_validate(row))


def test_combined_work_budget_is_preflighted_before_scoring_either_policy(monkeypatch):
    reference, uniform, change = paired()
    labels = reference.model_dump()
    labels['intervals'] = [{**labels['intervals'][0], 'text': 'a' * 50, 'identifiers': []}]
    runs = []
    for run in (uniform, change):
        row = run.model_dump()
        row['result']['frames'][0]['text'] = 'a' * 50
        runs.append(EvaluationRun.model_validate(row))
    monkeypatch.setattr(comparison, 'MAX_EDIT_CELLS', 7500)  # Each 5,001-cell alignment fits; their sum does not.
    monkeypatch.setattr(comparison, '_measure', lambda *_: pytest.fail('Must preflight both results'))
    with pytest.raises(ValueError, match='Combined alignment work'):
        comparison.compare(Reference.model_validate(labels), *runs)


def test_no_labeled_shared_points_has_null_ocr_not_a_perfect_score():
    reference, uniform, change = paired()
    labels = reference.model_dump()
    labels['intervals'] = [labels['intervals'][3]]
    report = comparison.compare(Reference.model_validate(labels), uniform, change)
    assert report['coverage_changes']['missed_by_both_ordinals'] == [0]
    for name in ('uniform', 'change'):
        assert report['common_image_ocr'][name]['scored_frames'] == 0
        assert report['common_image_ocr'][name]['wer'] is report['common_image_ocr'][name]['identifier_recall'] is None


def test_native_binding_precedes_isolation_and_metadata_mismatch_precedes_second_call(monkeypatch):
    reference, uniform, change = paired()
    calls = []
    monkeypatch.setattr(comparison, 'block_outbound_sockets', lambda: calls.append('isolation'))
    monkeypatch.setattr(comparison, 'LocalVisualProvider', lambda: SimpleNamespace(extract=lambda *args: calls.append('uniform') or uniform.result.result()))
    monkeypatch.setattr(comparison, 'LocalChangeVisualProvider', lambda: SimpleNamespace(extract=lambda *args: calls.append('change') or change.result.result()))
    with pytest.raises(ValueError): comparison.native_compare(reference, b'PRIVATE_BAD_INPUT')
    assert not calls
    labels = reference.model_dump()
    labels['video']['width'] = 1920
    with pytest.raises(ValueError): comparison.native_compare(Reference.model_validate(labels), content())
    assert calls == ['isolation', 'uniform']
    calls.clear()
    report = comparison.native_compare(reference, content())
    assert calls == ['isolation', 'uniform', 'change']
    assert report['input_binding'] == 'verified-mp4-bytes'


def test_cli_requires_rights_before_reads_and_malformed_reference_is_private(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['compare', '--reference', 'PRIVATE_LABELS.json'])
    monkeypatch.setattr(sys, 'stdin', None)
    with pytest.raises(SystemExit) as failure: comparison.main()
    assert failure.value.code == 2
    path = tmp_path / 'PRIVATE_FILENAME.json'
    path.write_text('{"PRIVATE_LABEL":true}')
    backend = Path(__file__).resolve().parents[1]
    run = subprocess.run([sys.executable, '-m', 'app.vision.compare', '--authorized-input', '--reference', str(path)],
        input=b'PRIVATE_INPUT', env={'PYTHONPATH': str(backend)}, capture_output=True, timeout=10)
    assert run.returncode == 1 and not run.stdout
    assert not any(value in run.stderr for value in [b'PRIVATE', b'Traceback'])


def test_cli_success_is_content_free_and_bad_measurements_are_not_a_quality_failure(tmp_path, monkeypatch, capsys):
    reference, uniform, change = paired()
    path = tmp_path / 'reference.json'
    path.write_text(reference.model_dump_json())
    monkeypatch.setattr(sys, 'argv', ['compare', '--authorized-input', '--reference', str(path)])
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(content())))
    monkeypatch.setattr(comparison, 'native_compare', lambda *_: comparison.compare(reference, uniform, change))
    comparison.main()
    captured = capsys.readouterr()
    assert json.loads(captured.out)['quality_approval'] == 'not_established'
    assert 'PRIVATE' not in captured.out and not captured.err
