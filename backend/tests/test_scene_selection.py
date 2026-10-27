from dataclasses import replace
import io
import json
from pathlib import Path
import sys
from time import monotonic
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.vision import scene
from app.vision.media import VideoInfo
from test_visual import mp4, probe as metadata


def info(duration_ms=20000, **changes):
    return VideoInfo(duration_ms=duration_ms, width=960, height=540,
                     fps_numerator=2, fps_denominator=1, **changes)


def samples(values=None, count=20):
    values = [0] * count if values is None else values
    return [scene.Thumbnail(index * 1000, 16, 16, bytes([value]) * 256)
            for index, value in enumerate(values)]


def test_static_anchors_are_actual_pts_and_deterministic_not_duplicate_durations():
    result = scene.select_candidates(samples(), info())
    assert [point['timestamp_ms'] for point in result['points']] == [0, 7000, 13000, 19000]
    assert result['eligible_changes'] == result['omitted_changes'] == 0
    assert result['selected_points'] == 4
    assert len({point['thumbnail_sha256'] for point in result['points']}) == 1
    assert result == scene.select_candidates(samples(), info())
    assert all(point['anchor'] and not point['change'] for point in result['points'])


def test_transient_view_and_return_both_selected_between_uniform_grid_points():
    result = scene.select_candidates(samples([0, 0, 0, 255] + [0] * 16), info())
    by_time = {point['timestamp_ms']: point for point in result['points']}
    assert result['eligible_changes'] == 2 and result['selected_points'] == 6
    assert by_time[3000]['change'] and by_time[4000]['change']
    assert by_time[4000]['thumbnail_sha256'] == by_time[0]['thumbnail_sha256']
    assert by_time[3000]['changed_ppm'] == by_time[3000]['mean_absolute_difference_ppm'] == 1_000_000


def test_noise_below_pixel_delta_is_not_a_change():
    result = scene.select_candidates(samples([0, 23] * 10), info())
    assert result['eligible_changes'] == 0
    assert result['points'][1]['changed_ppm'] == 0
    assert result['points'][1]['mean_absolute_difference_ppm'] > 0
    at_threshold = scene.select_candidates(samples([0, 24] * 10), info())
    assert at_threshold['eligible_changes'] == 19


def test_changed_pixel_fraction_threshold_is_independent_of_geometry():
    before = bytes(8192)
    for changed, expected in [(16, 0), (17, 1)]:
        data = [scene.Thumbnail(0, 128, 64, before),
                scene.Thumbnail(1000, 128, 64, bytes([24]) * changed + before[changed:])]
        result = scene.select_candidates(data, info(2000))
        assert result['eligible_changes'] == expected
        assert result['points'][1]['changed_pixel_count'] == changed


def test_max_budget_retains_anchors_and_earliest_ranked_changes_not_first_twenty_only():
    result = scene.select_candidates(samples([0, 255] * 300), info(600000))
    points = result['points']
    assert len(points) == 20 and result['eligible_changes'] == 599 and result['omitted_changes'] == 580
    assert points[0]['timestamp_ms'] == 0 and points[-1]['timestamp_ms'] == 599000
    assert [point['timestamp_ms'] for point in points if not point['anchor']] == list(range(1000, 17000, 1000))


def test_ranking_prefers_larger_magnitude_when_changed_fraction_ties():
    values = [0, 24] * 40
    values[70:] = [0, 255] * 5
    result = scene.select_candidates(samples(values), info(80000))
    chosen = {point['timestamp_ms'] for point in result['points']}
    # The first 70s transition is only 24 gray levels; 71s onward is 255.
    assert set(range(71000, 80000, 1000)) <= chosen


def test_anchor_ties_choose_earlier_actual_sample():
    result = scene.select_candidates(samples(count=5), info(4501))
    assert [point['timestamp_ms'] for point in result['points']] == [0, 1000, 3000, 4000]


def test_tiny_duration_and_no_fabricated_end_timestamp():
    result = scene.select_candidates(samples(count=1), info(1))
    assert result['selected_points'] == 1 and result['points'][0]['timestamp_ms'] == 0
    result = scene.select_candidates(samples(count=2), info(1500))
    assert [point['timestamp_ms'] for point in result['points']] == [0, 1000]


@pytest.mark.parametrize('change', [
    {'timestamp_ms': True}, {'timestamp_ms': -1}, {'timestamp_ms': 20000},
    {'width': True}, {'width': 161}, {'height': 91}, {'width': 0},
    {'pixels': b''}, {'pixels': bytearray(256)}, {'pixels': 'not bytes'},
])
def test_invalid_thumbnails(change):
    data = samples()
    data[1] = replace(data[1], **change)
    with pytest.raises(ValueError):
        scene.select_candidates(data, info())


@pytest.mark.parametrize('data', [[], samples(count=601), samples()[1:], samples()[:-3],
    list(reversed(samples())), [samples()[0], samples()[0]],
    [samples()[0], replace(samples()[1], width=8, height=32)],
    [samples()[0], replace(samples()[1], timestamp_ms=998)],
    [samples()[0], replace(samples()[1], timestamp_ms=1502)]])
def test_incomplete_unordered_gapped_or_excessive_scan_rejected(data):
    with pytest.raises(ValueError):
        scene.select_candidates(data, info())


def test_fractional_source_fps_and_source_step_gap_bounds():
    source = VideoInfo(duration_ms=6000, width=960, height=540, fps_numerator=1001, fps_denominator=1000)
    data = [replace(sample, timestamp_ms=stamp) for sample, stamp in zip(samples(count=3), [0, 1998, 3996])]
    with pytest.raises(ValueError):  # Tail gap 2004 > allowed 2001.
        scene.select_candidates(data, source)
    source.duration_ms = 5994
    assert scene.select_candidates(data, source)['scan_samples'] == 3
    source.fps_numerator = True
    with pytest.raises(ValidationError):
        scene.select_candidates(data, source)


def test_unknown_source_fps_rejected():
    source = info()
    source.fps_numerator = 61
    with pytest.raises(ValueError):
        scene.select_candidates(samples(), source)


class Runner:
    def __init__(self):
        self.deadline = monotonic() + 120
        self.calls = []
        self.bad_output = None

    def run(self, arguments, **kwargs):
        self.calls.append((arguments, kwargs))
        if arguments == ['/usr/bin/ffmpeg', '-version']:
            return b'ffmpeg version 5.1.9 fixture'
        if arguments[0] == '/usr/bin/ffprobe':
            data = metadata(avg_frame_rate='2/1', r_frame_rate='2/1', duration='20.000')
            data['format']['duration'] = '20.000'
            return json.dumps(data).encode()
        if arguments[0] == '/usr/bin/ffmpeg':
            root = Path(arguments[-1]).parent
            for sample in samples([0, 0, 0, 255] + [0] * 16):
                (root / f'{sample.timestamp_ms}.pgm').write_bytes(b'P5\n16 16\n255\n' + sample.pixels)
            if self.bad_output:
                self.bad_output(root)
            return b''
        pytest.fail('Unsupported tool call')


@pytest.fixture
def runner(monkeypatch):
    value = Runner()
    monkeypatch.setattr(scene, 'NativeRunner', lambda: value)
    monkeypatch.setattr(scene, 'require_isolation', lambda: None)
    return value


def test_native_probe_uses_fixed_filtered_decoder_only_and_cleans_temporary_files(runner):
    report = scene.probe(mp4())
    assert report['quality_approval'] == 'not_established' and report['scan_samples'] == 20
    assert report['selected_points'] == 6 and report['outcome'] == 'operator-prototype-complete'
    assert report['identity']['profile'].startswith('visual-change-probe-v1:')
    assert len(runner.calls) == 3
    command = runner.calls[-1][0]
    assert command[command.index('-frames:v') + 1] == '601'
    assert 'prev_selected_t' in command[command.index('-vf') + 1]
    assert '-copyts' in command and '-frame_pts' in command and '-an' in command
    assert all(command[command.index(flag) + 1] == '0' for flag in ['-enable_drefs', '-use_absolute_path'])
    assert command[command.index('-protocol_whitelist') + 1] == 'file,pipe'
    assert not Path(command[-1]).parent.exists()
    assert 'pixels' not in json.dumps(report) and 'ocr' not in report
    # Standalone prototype identities cannot be mistaken for managed evidence.
    from app.vision.contracts import VisualIdentity
    with pytest.raises(ValidationError):
        VisualIdentity.model_validate(report['identity'])


@pytest.mark.parametrize('kind', ['symlink', 'filename', 'oversized', 'geometry', 'duplicate_pts', 'count', 'deadline'])
def test_bad_native_scan_output_fails_safely_and_cleans_up(runner, kind):
    def corrupt(root):
        if kind == 'symlink':
            (root / '1000.pgm').unlink()
            (root / '1000.pgm').symlink_to(root / '0.pgm')
        elif kind == 'filename':
            (root / 'private.pgm').write_bytes(b'PRIVATE_PIXELS')
        elif kind == 'oversized':
            (root / '1000.pgm').write_bytes(b'PRIVATE_PIXELS' * 2000)
        elif kind == 'geometry':
            (root / '1000.pgm').write_bytes(b'P5\n161 16\n255\n' + bytes(161 * 16))
        elif kind == 'duplicate_pts':
            (root / '00.pgm').write_bytes((root / '0.pgm').read_bytes())
        elif kind == 'count':
            for index in range(601):
                (root / f'{index}.pgm').touch()
        else:
            runner.deadline = monotonic() - 1
    runner.bad_output = corrupt
    with pytest.raises(ValueError):
        scene.probe(mp4())
    assert not Path(runner.calls[-1][0][-1]).parent.exists()


def test_bad_input_and_missing_isolation_precede_native_construction(monkeypatch):
    monkeypatch.setattr(scene, 'NativeRunner', lambda: pytest.fail('Must fail before native construction'))
    with pytest.raises(ValueError):
        scene.probe(b'PRIVATE_INVALID_VIDEO')
    monkeypatch.setattr(scene, 'require_isolation', lambda: (_ for _ in ()).throw(RuntimeError('Missing isolation')))
    with pytest.raises(RuntimeError, match='Missing isolation'):
        scene.probe(mp4())


def test_cli_requires_rights_before_stdin_and_keeps_bounded_content_free_output(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['probe'])
    monkeypatch.setattr(sys, 'stdin', None)
    with pytest.raises(SystemExit) as outcome:
        scene.main()
    assert outcome.value.code == 2
    capsys.readouterr()
    calls = []
    monkeypatch.setattr(sys, 'argv', ['probe', '--authorized-input'])
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(mp4())))
    monkeypatch.setattr(scene, 'block_outbound_sockets', lambda: calls.append('isolated'))
    monkeypatch.setattr(scene, 'probe', lambda content: {'bytes': len(content), 'quality_approval': 'not_established'})
    scene.main()
    assert calls == ['isolated']
    assert json.loads(capsys.readouterr().out)['bytes'] == len(mp4())
