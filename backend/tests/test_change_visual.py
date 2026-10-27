from pathlib import Path
from time import monotonic

import pytest

from app.vision import change
from app.vision.contracts import WireResult
from app.vision.scene import manifest_for
from test_scene_selection import Runner, info, samples
from test_visual import mp4
from test_visual_selection import change_result


class ChangeRunner(Runner):
    def __init__(self):
        super().__init__()
        self.corrupt = None

    def run(self, arguments, **kwargs):
        if arguments[0] == '/usr/bin/tesseract':
            self.calls.append((arguments, kwargs))
            return b'PRIVATE_OCR <script>not instructions</script> user_id\n'
        if arguments[0] == '/usr/bin/ffmpeg' and '-vf' in arguments and 'round(t*1000)' in arguments[arguments.index('-vf') + 1]:
            self.calls.append((arguments, kwargs))
            output = Path(arguments[-1]).parent
            data = samples([0, 0, 0, 255] + [0] * 16)
            for index in [0, 3, 4, 7, 13, 19]:
                (output / f'{index * 1000}.pgm').write_bytes(b'P5\n16 16\n255\n' + data[index].pixels)
            if self.corrupt: self.corrupt(output)
            return b''
        return super().run(arguments, **kwargs)


@pytest.fixture
def runner(monkeypatch):
    value = ChangeRunner()
    monkeypatch.setattr(change, 'NativeRunner', lambda: value)
    monkeypatch.setattr(change, 'require_isolation', lambda: None)
    monkeypatch.setattr(change, 'runtime_identity', lambda runner, language, selection: change_result().identity.model_dump())
    return value


def test_fixed_two_pass_extraction_preserves_complete_manifest_and_temporal_returns(runner):
    result = change.LocalChangeVisualProvider().extract(mp4())
    wire = WireResult.from_result(result)
    assert wire.protocol == 'local-visual-http-v2'
    assert [frame.timestamp_ms for frame in result.frames] == [0, 3000, 4000, 7000, 13000, 19000]
    assert len(wire.selection.samples) == 20 and len(result.frames) == result.candidates == 6
    assert result.frames[0].image == result.frames[2].image
    assert all(frame.text == 'PRIVATE_OCR <script>not instructions</script> user_id' for frame in result.frames)
    commands = [arguments for arguments, _ in runner.calls if arguments[0] == '/usr/bin/ffmpeg']
    assert len(commands) == 2
    full = commands[1]
    assert '-ss' not in full and '-copyts' in full and '-n' in full
    assert full[full.index('-frames:v') + 1] == '7'
    assert full[full.index('-protocol_whitelist') + 1] == 'file,pipe'
    assert full[full.index('-enable_drefs') + 1] == full[full.index('-use_absolute_path') + 1] == '0'
    assert not Path(full[-1]).parent.exists()


@pytest.mark.parametrize('kind', ['missing', 'extra', 'symlink', 'directory', 'alias', 'oversize', 'geometry', 'deadline'])
def test_bad_selected_output_never_delivers_partial_results_and_always_cleans_up(runner, kind):
    def corrupt(output):
        target = output / '3000.pgm'
        if kind == 'missing': target.unlink()
        elif kind == 'extra': (output / '3001.pgm').touch()
        elif kind == 'symlink':
            target.unlink(); target.symlink_to(output / '0.pgm')
        elif kind == 'directory':
            target.unlink(); target.mkdir()
        elif kind == 'alias': target.rename(output / '03000.pgm')
        elif kind == 'oversize': target.write_bytes(b'PRIVATE_PIXELS' * 60000)
        elif kind == 'geometry': target.write_bytes(b'P5\n8 16\n255\n' + bytes(128))
        else: runner.deadline = monotonic() - 1
    runner.corrupt = corrupt
    with pytest.raises(ValueError): change.LocalChangeVisualProvider().extract(mp4())
    full = [args for args, _ in runner.calls if args[0] == '/usr/bin/ffmpeg'][-1]
    assert not Path(full[-1]).parent.exists()


def test_manifest_builder_matches_original_experiment_and_validates_all_scan_points():
    data = samples([0, 0, 0, 255] + [0] * 16)
    manifest = manifest_for(data, info())
    assert len(manifest.samples) == 20
    assert manifest.selected_timestamps_ms == [0, 3000, 4000, 7000, 13000, 19000]
    assert manifest.samples[3].changed_pixel_count == 256
    with pytest.raises(ValueError): manifest_for(data[:-3], info())


def test_invalid_input_language_or_missing_isolation_precedes_native_work(monkeypatch):
    monkeypatch.setattr(change, 'NativeRunner', lambda: pytest.fail('Must reject before native construction'))
    with pytest.raises(ValueError): change.LocalChangeVisualProvider().extract(b'PRIVATE_INVALID_INPUT')
    with pytest.raises(ValueError): change.LocalChangeVisualProvider().extract(mp4(), 'auto')
    monkeypatch.setattr(change, 'require_isolation', lambda: (_ for _ in ()).throw(RuntimeError('Isolation unavailable')))
    with pytest.raises(RuntimeError): change.LocalChangeVisualProvider().extract(mp4())
