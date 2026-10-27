from dataclasses import replace
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace

import pytest

from app.vision import code_suite as suite
from test_visual_comparison import paired
from test_visual_service import content
from app.vision.compare import compare


def test_authored_schedules_are_complete_independent_synthetic_labels_with_literal_identifiers():
    assert len(suite.CASES) == 5 and len({case.case_id for case in suite.CASES}) == 5
    for case in suite.CASES:
        labels = case.reference(content())
        assert labels.label_status == 'synthetic'
        assert labels.intervals[0].start_ms == 0 and labels.intervals[-1].end_ms == 20000
        assert all(left.end_ms == right.start_ms for left, right in zip(labels.intervals, labels.intervals[1:]))
        assert case.language in {case.label_language, 'en+tr'}
        assert 'text=' not in repr(case) and 'pytest -q' not in repr(case)
    code = next(case for case in suite.CASES if case.case_id == 'single_digit')
    assert code.views[0].text != code.views[1].text
    assert code.views[0].text[:-1] == code.views[1].text[:-1]
    subsecond = next(case for case in suite.CASES if case.case_id == 'subsecond_view')
    assert subsecond.fps == 10 and subsecond.views[1].end_ms - subsecond.views[1].start_ms == 400
    assert next(case for case in suite.CASES if case.case_id == 'cursor_motion').cursor


@pytest.mark.parametrize('change', [{'fps': True}, {'fps': 30}, {'language': 'auto'}, {'cursor': 1},
    {'views': ()}, {'views': (suite.View(1, 20000, 'bad'),)},
    {'views': (suite.View(0, 19999, 'bad'),)},
    {'views': (suite.View(0, 1000, 'bad'), suite.View(999, 20000, 'bad'))}])
def test_bad_authoring_schedule_is_rejected_before_native_construction(monkeypatch, change):
    monkeypatch.setattr(suite, 'NativeRunner', lambda: pytest.fail('Invalid authoring before native work'))
    with pytest.raises(ValueError): suite.authored_video(replace(suite.CASES[0], **change))


@pytest.mark.parametrize('case', suite.CASES, ids=lambda case: case.case_id)
def test_fixed_renderer_preserves_literal_text_and_limits_then_cleans_tmp(monkeypatch, case):
    calls = []
    def run(args):
        calls.append(args)
        filters = args[args.index('-vf') + 1]
        paths = [Path(name) for name in re.findall(r'textfile=([^:]+):', filters)]
        assert [path.read_text() for path in paths] == [view.text for view in case.views]
        assert filters.count('expansion=none') == len(case.views)
        assert 'DejaVuSansMono.ttf' in filters and re.search(r'(?:^|:)text=', filters) is None
        assert args[args.index('-crf') + 1] == '0' and args[args.index('-r') + 1] == str(case.fps)
        assert args[args.index('-vsync') + 1] == '0' and '-an' in args
        assert ('drawbox=' in filters) == case.cursor
        Path(args[-1]).write_bytes(content())
    monkeypatch.setattr(suite, 'require_isolation', lambda: None)
    monkeypatch.setattr(suite, 'NativeRunner', lambda: SimpleNamespace(run=run))
    assert suite.authored_video(case) == content()
    assert len(calls) == 1 and not Path(calls[0][-1]).parent.exists()


def test_percent_expansion_and_prompt_like_text_are_never_inline_filter_expressions(monkeypatch):
    text = "print('%{metadata:SECRET}')\n<script>literal</script>"
    case = replace(suite.CASES[0], views=(suite.View(0, 20000, text),))
    def run(args):
        filters = args[args.index('-vf') + 1]
        assert 'SECRET' not in filters and '<script>' not in filters and 'expansion=none' in filters
        path = Path(re.search(r'textfile=([^:]+):', filters)[1])
        assert path.read_text() == text
        Path(args[-1]).write_bytes(content())
    monkeypatch.setattr(suite, 'require_isolation', lambda: None)
    monkeypatch.setattr(suite, 'NativeRunner', lambda: SimpleNamespace(run=run))
    suite.authored_video(case)


@pytest.mark.parametrize('mode', ['oversize', 'empty', 'failure'])
def test_native_fixture_failures_keep_limits_and_clean_temporary_files(monkeypatch, mode):
    calls = []
    def run(args):
        calls.append(args)
        if mode == 'failure': raise RuntimeError('PRIVATE_NATIVE_ERROR')
        Path(args[-1]).write_bytes(b'x' * (2_000_001 if mode == 'oversize' else 0))
    monkeypatch.setattr(suite, 'require_isolation', lambda: None)
    monkeypatch.setattr(suite, 'NativeRunner', lambda: SimpleNamespace(run=run))
    with pytest.raises((RuntimeError, ValueError)): suite.authored_video(suite.CASES[0])
    assert not Path(calls[0][-1]).parent.exists()


def test_fixture_generation_requires_isolation_before_construction(monkeypatch):
    monkeypatch.setattr(suite, 'require_isolation', lambda: (_ for _ in ()).throw(RuntimeError('Isolation missing')))
    monkeypatch.setattr(suite, 'NativeRunner', lambda: pytest.fail('Isolation must precede native work'))
    with pytest.raises(RuntimeError): suite.authored_video(suite.CASES[0])


def test_suite_summary_retains_bad_measurements_without_raw_text_or_a_winner(monkeypatch):
    report = compare(*paired())
    monkeypatch.setattr(suite, 'authored_video', lambda case: content())
    monkeypatch.setattr(suite, 'native_compare', lambda *args: report)
    summary = suite.run_cases(suite.CASES[:1])
    assert summary['case_count'] == 1 and summary['application_records_created'] == 0
    assert summary['quality_approval'] == 'not_established' and 'winner' not in summary
    item = summary['cases'][0]
    assert item['coverage_changes']['lost_ordinals'] == [2]
    assert item['measurements']['uniform']['ocr'] == report['measurements']['uniform']['ocr']
    assert item['measurements']['uniform']['identity'] == report['measurements']['uniform']['identity']
    assert 'PRIVATE_OCR' not in json.dumps(summary) and 'Use user_id' not in json.dumps(summary)


def test_named_cli_case_is_fixed_and_invalid_case_precedes_isolation(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['suite', '--case', 'PRIVATE_UNKNOWN_CASE'])
    monkeypatch.setattr(suite, 'block_outbound_sockets', lambda: pytest.fail('Unknown case before native setup'))
    with pytest.raises(SystemExit) as failure: suite.main()
    assert failure.value.code == 2
    capsys.readouterr()
    calls = []
    monkeypatch.setattr(sys, 'argv', ['suite', '--case', 'single_digit'])
    monkeypatch.setattr(suite, 'block_outbound_sockets', lambda: calls.append('isolated'))
    monkeypatch.setattr(suite, 'run_cases', lambda cases: {'ids': [case.case_id for case in cases]})
    suite.main()
    assert calls == ['isolated'] and json.loads(capsys.readouterr().out) == {'ids': ['single_digit']}
