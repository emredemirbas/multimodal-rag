"""Fixed isolated change-aware native producer, never an API/worker decoder."""
import hashlib
from pathlib import Path
import tempfile
from time import monotonic

from .contracts import WireResult
from .local import (INPUT_OPTIONS, Language, NativeRunner, VisualResult,
                    recognize_text, require_isolation, runtime_identity)
from .media import FrameEvidence, encode_png, parse_pgm, parse_probe, validate_mp4
from .scene import manifest_for, scan_thumbnails


class LocalChangeVisualProvider:
    def extract(self, content: bytes, language: Language = 'en') -> VisualResult:
        validate_mp4(content)
        if language not in {'en', 'tr', 'en+tr'}:
            raise ValueError('Unsupported OCR language')
        require_isolation()
        runner = NativeRunner()
        identity = runtime_identity(runner, language, 'change')
        with tempfile.TemporaryDirectory(prefix='visual-change-ocr-', dir='/tmp') as directory:
            root = Path(directory)
            source = root / 'input.mp4'
            source.write_bytes(content)
            info = parse_probe(runner.run(['/usr/bin/ffprobe', '-v', 'error', *INPUT_OPTIONS,
                '-show_entries', 'format=duration,start_time:stream=codec_type,codec_name,codec_tag_string,width,height,pix_fmt,start_time,duration,avg_frame_rate,r_frame_rate:stream_side_data=rotation',
                '-of', 'json', str(source)]))
            manifest = manifest_for(scan_thumbnails(source, root, runner), info)
            times = manifest.selected_timestamps_ms
            output = root / 'selected'
            output.mkdir()
            # Match the same millisecond PTS as the first pass, not -ss at a
            # rounded target (which can skip a fractional-rate source frame).
            expression = '+'.join(f'eq(round(t*1000),{stamp})' for stamp in times)
            runner.run(['/usr/bin/ffmpeg', '-nostdin', '-n', '-v', 'error', '-threads', '1', '-filter_threads', '1',
                '-copyts', *INPUT_OPTIONS, '-i', str(source), '-map', '0:v:0', '-an', '-sn', '-dn', '-vf',
                f"select='{expression}',scale=960:540:force_original_aspect_ratio=decrease:flags=bilinear,format=gray",
                '-frames:v', str(len(times) + 1), '-c:v', 'pgm', '-threads', '1', '-vsync', '0',
                '-enc_time_base', '1:1000', '-frame_pts', '1', '-f', 'image2', str(output / '%d.pgm')])
            files = []
            for path in output.iterdir():
                files.append(path)
                if len(files) > len(times):
                    raise ValueError('Excessive selected output')
            if ({path.name for path in files} != {f'{stamp}.pgm' for stamp in times}
                    or any(path.is_symlink() or not path.is_file() for path in files)):
                raise ValueError('Selected decoded PTS do not match the scan')
            frames = []
            for stamp in times:
                with (output / f'{stamp}.pgm').open('rb') as stream:
                    pgm = stream.read(600_001)
                width, height, pixels = parse_pgm(pgm)
                frames.append(FrameEvidence(sample_target_ms=stamp, timestamp_ms=stamp,
                    width=width, height=height, image=encode_png(width, height, pixels),
                    text=recognize_text(runner, pgm, language)))
            value = VisualResult(hashlib.sha256(content).hexdigest(), info, identity,
                len(times), tuple(frames), manifest.model_dump())
            # Validate native output too, including manifest/geometry/PNG bounds.
            WireResult.from_result(value)
            if monotonic() > runner.deadline:
                raise ValueError('Visual processing deadline exceeded')
        return value
