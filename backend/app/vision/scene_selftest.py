"""Authored transient-view comparison; not representative scene/code recall."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from ..asr.isolation import block_outbound_sockets
from .local import LocalVisualProvider, NativeRunner
from .scene import probe


def authored_transient_video(rate='2') -> bytes:
    if rate not in {'2', '30000/1001', '1001/1000'}:
        raise ValueError('Unsupported authored frame rate')
    with tempfile.TemporaryDirectory(prefix='visual-transient-', dir='/tmp') as directory:
        path = Path(directory) / 'authored.mp4'
        NativeRunner().run(['/usr/bin/ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
            f"color=c=white:s=960x540:r={rate}:d=20,"
            "drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='gte(t,3)*lt(t,4)',"
            "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:text='BASE VIEW':fontsize=56:fontcolor=black:x=80:y=200:enable='lt(t,3)+gte(t,4)',"
            "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:text='BRIEF VIEW':fontsize=56:fontcolor=white:x=80:y=200:enable='gte(t,3)*lt(t,4)'",
            '-c:v', 'libx264', '-threads', '1', '-pix_fmt', 'yuv420p', '-crf', '0',
            '-preset', 'ultrafast', '-g', '1' if rate == '2' else '60',
            *([] if rate == '2' else ['-vsync', '0', '-r', rate]), '-t', '20', '-f', 'mp4', str(path)])
        with path.open('rb') as stream:
            content = stream.read(2_000_001)
        if len(content) > 2_000_000:
            raise ValueError('Authored transient fixture exceeded its bound')
        return content


def main():
    block_outbound_sockets()
    content = authored_transient_video()
    baseline = LocalVisualProvider().extract(content, 'en')
    candidate = probe(content)
    baseline_pts = [frame.timestamp_ms for frame in baseline.frames]
    proposed_pts = [point['timestamp_ms'] for point in candidate['points']]
    # Labels/expected transition times are authored above, not inferred from OCR.
    if (any(3000 <= stamp < 4000 for stamp in baseline_pts) or 3000 not in proposed_pts
            or 4000 not in proposed_pts or candidate['scan_samples'] != 20
            or candidate['selected_points'] > 20):
        raise ValueError('Authored transient/return comparison failed')
    environment = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
                   'PYTHONDONTWRITEBYTECODE': '1'}
    command = [sys.executable, '-m', 'app.vision.scene', '--authorized-input']
    delivered = subprocess.run(command, input=content, env=environment, capture_output=True, timeout=30)
    if delivered.returncode or delivered.stderr:
        raise ValueError('Native operator command failed')
    receipt = json.loads(delivered.stdout)
    if receipt != candidate or b'BASE VIEW' in delivered.stdout or b'BRIEF VIEW' in delivered.stdout:
        raise ValueError('Native receipt mismatch or content disclosure')
    rejected = subprocess.run(command, input=b'PRIVATE_INVALID_VIDEO', env=environment,
                              capture_output=True, timeout=5)
    if rejected.returncode != 1 or rejected.stdout or b'PRIVATE_INVALID_VIDEO' in rejected.stderr:
        raise ValueError('Malformed native input did not fail safely')
    print(json.dumps({'outcome': 'authored-change-prototype-complete', 'quality_approval': 'not_established',
        'baseline_retained_pts_ms': baseline_pts, 'candidate_selected_pts_ms': proposed_pts,
        'authored_transient_interval_ms': [3000, 4000], 'baseline_transient_covered': False,
        'candidate_transient_covered': True, 'temporal_return_preserved': True,
        'native_cli_and_safe_rejection': True, 'application_records_created': 0,
        'candidate': candidate}, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('FAIL: authored change comparison; no pixels, OCR, paths or raw exception was logged.') from None
