"""Actual opt-in HTTP/OCR and fractional-PTS probes with authored input only."""
import argparse
from fractions import Fraction
import json
import subprocess
import sys
import tempfile
from time import monotonic, sleep

from .client import LocalVisualClient, VisualError
from .contracts import WireResult
from .selection import CHANGE_POLICY


def main():
    environment = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1', 'LANG': 'C.UTF-8'}
    with tempfile.TemporaryFile() as log:
        child = subprocess.Popen([sys.executable, '-m', 'app.vision.server'], env=environment,
            stdout=log, stderr=log, start_new_session=True)
        try:
            client = LocalVisualClient('http://127.0.0.1:8091')
            deadline = monotonic() + 10
            while True:
                if child.poll() is not None: raise ValueError('Private service startup failed')
                try:
                    identity = client.ready('en', selection='change')
                    break
                except VisualError:
                    if monotonic() >= deadline: raise ValueError('Private service readiness deadline') from None
                    sleep(.05)
            if identity.policy != CHANGE_POLICY: raise ValueError('Incorrect change identity')
            reports = []
            for rate in ('2', '30000/1001', '1001/1000'):
                fixture = subprocess.run([sys.executable, '-m', 'app.vision.change_selftest', '--fixture', '--rate', rate],
                    env=environment, capture_output=True, check=True, timeout=20).stdout
                if not 24 <= len(fixture) <= 2_000_000: raise ValueError('Authored fixture bound exceeded')
                result = client.extract(fixture, expected_identity=identity)
                if Fraction(result.info.fps_numerator, result.info.fps_denominator) != Fraction(rate):
                    raise ValueError('Authored fixture did not preserve its requested frame rate')
                wire = WireResult.from_result(result)
                points = wire.selection.selected_timestamps_ms
                if wire.protocol != 'local-visual-http-v2' or points != [f.timestamp_ms for f in result.frames]:
                    raise ValueError('Authored selected-frame timeline mismatch')
                if not any(3000 <= frame.timestamp_ms < 4000 and 'BRIEF VIEW' in frame.text for frame in result.frames):
                    raise ValueError(f'Authored transient OCR missing: rate={rate}, selected_pts_ms={points}')
                if rate == '2':
                    if points != [0, 3000, 4000, 7000, 13000, 19000] or result.frames[0].image != result.frames[2].image:
                        raise ValueError('Temporal return was not preserved')
                    baseline = client.extract(fixture, expected_identity=client.ready('en'))
                    if [f.timestamp_ms for f in baseline.frames] != [0]: raise ValueError('Uniform compatibility failed')
                    cli = subprocess.run([sys.executable, '-m', 'app.vision.smoke', '--authorized-input', '--selection', 'change'],
                        input=fixture, env=environment, capture_output=True, check=True, timeout=40)
                    receipt = json.loads(cli.stdout)
                    if receipt['profile'] != identity.profile or receipt['frames'] != 6 or b'BRIEF VIEW' in cli.stdout:
                        raise ValueError('Operator CLI privacy/profile mismatch')
                reports.append({'fps': rate, 'selected_pts_ms': points, 'scan_samples': len(wire.selection.samples),
                    'brief_ocr_recognized': True, 'exact_pts_matched': True})
            log.seek(0)
            output = log.read(65_537)
            if len(output) > 65_536 or b'BRIEF VIEW' in output or b'BASE VIEW' in output:
                raise ValueError('Native log privacy/bound failure')
            if output.count(b'"event": "visual_extraction_complete"') != 4:
                raise ValueError('Unrequested native retry')
            print(json.dumps({'outcome': 'authored-change-ocr-complete', 'quality_approval': 'not_established',
                'profile': identity.profile, 'probes': reports, 'uniform_compatible': True,
                'temporal_return_preserved': True, 'application_records_created': 0}, sort_keys=True))
        finally:
            child.terminate()
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=5)


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--fixture', action='store_true')
        parser.add_argument('--rate', choices=['2', '30000/1001', '1001/1000'], default='2')
        args = parser.parse_args()
        if args.fixture:
            from ..asr.isolation import block_outbound_sockets
            from .scene_selftest import authored_transient_video
            block_outbound_sockets()
            sys.stdout.buffer.write(authored_transient_video(args.rate))
        else: main()
    except Exception:
        raise SystemExit('FAIL: change OCR native self-test; no frames, OCR, paths or raw errors logged.') from None
