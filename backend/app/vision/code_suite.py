"""Fixed authored code/terminal diagnostics; not a representative benchmark."""
import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from ..asr.isolation import block_outbound_sockets
from .compare import native_compare
from .evaluate import Reference
from .local import NativeRunner, require_isolation


@dataclass(frozen=True)
class View:
    start_ms: int
    end_ms: int
    text: str = field(repr=False)
    identifiers: tuple[str, ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class Case:
    case_id: str
    language: str
    label_language: str
    fps: int
    views: tuple[View, ...]
    cursor: bool = False

    def reference(self, content: bytes) -> Reference:
        if (type(self.fps) is not int or self.fps not in {2, 10}
                or self.language not in {'en', 'tr', 'en+tr'} or type(self.cursor) is not bool
                or not self.views or self.views[0].start_ms != 0 or self.views[-1].end_ms != 20000
                or any(before.end_ms != after.start_ms for before, after in zip(self.views, self.views[1:]))):
            raise ValueError('Invalid authored schedule')
        return Reference.model_validate({'schema_version': 'visual-reference-v1', 'label_status': 'synthetic',
            'input_sha256': hashlib.sha256(content).hexdigest(), 'input_bytes': len(content),
            'video': {'duration_ms': 20000, 'width': 960, 'height': 540, 'fps_numerator': self.fps, 'fps_denominator': 1},
            'intervals': [{'start_ms': view.start_ms, 'end_ms': view.end_ms, 'language': self.label_language,
                'text': view.text, 'identifiers': list(view.identifiers)} for view in self.views]})


TERMINAL_OK = '$ pytest -q\n12 passed in 0.42s'
TERMINAL_ERROR = '$ pytest -q\nFAILED test_users.py::test_create_user\nAssertionError: 500 != 201'
CODE_201 = 'def test_create_user():\n    assert response.status_code == 201'
CODE_200 = 'def test_create_user():\n    assert response.status_code == 200'
TURKISH_CODE = '# KULLANICI İŞLEMİ\nuser_id = request.json()["user_id"]\nprint("sağlık kontrolü")'
CASES = (
    Case('terminal_error', 'en', 'en', 2, (
        View(0, 3000, TERMINAL_OK, ('pytest',)),
        View(3000, 4000, TERMINAL_ERROR, ('test_users.py::test_create_user', 'AssertionError')),
        View(4000, 20000, TERMINAL_OK, ('pytest',)))),
    Case('single_digit', 'en', 'en', 2, (
        View(0, 5000, CODE_201, ('test_create_user', 'response.status_code', '201')),
        View(5000, 6000, CODE_200, ('test_create_user', 'response.status_code', '200')),
        View(6000, 20000, CODE_201, ('test_create_user', 'response.status_code', '201')))),
    Case('cursor_motion', 'en', 'en', 2, (
        View(0, 20000, '$ python app.py\nGET /health 200 OK', ('app.py', '/health')),), cursor=True),
    Case('subsecond_view', 'en', 'en', 10, (
        View(0, 3200, 'print("READY")', ('READY',)),
        View(3200, 3600, 'raise RuntimeError("RETRY")', ('RuntimeError', 'RETRY')),
        View(3600, 20000, 'print("READY")', ('READY',)))),
    Case('turkish_code', 'en+tr', 'tr', 2, (
        View(0, 20000, TURKISH_CODE, ('user_id', 'request.json')),)),
)


def authored_video(case: Case) -> bytes:
    case.reference(b'x' * 24)  # Validate the authored labels/schedule before native work.
    require_isolation()
    runner = NativeRunner()
    with tempfile.TemporaryDirectory(prefix='visual-code-', dir='/tmp') as directory:
        root = Path(directory)
        filters = []
        for ordinal, view in enumerate(case.views):
            text = root / f'text-{ordinal}.txt'
            text.write_text(view.text, encoding='utf-8')
            filters.append('drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf:'
                f'textfile={text}:expansion=none:fontsize=32:fontcolor=white:x=48:y=48:line_spacing=12:'
                f"enable='gte(t,{view.start_ms / 1000:.3f})*lt(t,{view.end_ms / 1000:.3f})'")
        if case.cursor:
            filters.append("drawbox=x=700:y=420:w=80:h=36:color=white:t=fill:enable='gte(mod(t,2),1)'")
        target = root / 'authored.mp4'
        runner.run(['/usr/bin/ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
            f'color=c=0x202020:s=960x540:r={case.fps}:d=20', '-vf', ','.join(filters),
            '-an', '-sn', '-dn', '-c:v', 'libx264', '-threads', '1', '-pix_fmt', 'yuv420p', '-crf', '0',
            '-preset', 'ultrafast', '-g', str(case.fps * 2), '-r', str(case.fps), '-vsync', '0',
            '-t', '20', '-f', 'mp4', str(target)])
        with target.open('rb') as stream: content = stream.read(2_000_001)
        if not 24 <= len(content) <= 2_000_000: raise ValueError('Authored fixture byte bound exceeded')
        return content


def summarize(case: Case, report: dict) -> dict:
    # Reports have already been computed from validated native results, not loaded
    # from arbitrary summaries. Keep every bad measurement, without text export.
    measurements = {}
    for name, value in report['measurements'].items():
        measurements[name] = {key: value[key] for key in ('result_sha256', 'identity', 'selected_frames', 'sampling', 'ocr')}
        measurements[name]['retained_pts_ms'] = sorted(frame['timestamp_ms']
            for interval in value['intervals'] for frame in interval['frames'])
    baseline = report['measurements']['uniform']
    return {'case_id': case.case_id, 'label_status': baseline['label_status'],
        'input_sha256': baseline['input_sha256'], 'input_bytes': baseline['input_bytes'],
        'reference_sha256': baseline['reference_sha256'], 'video': baseline['video'],
        'input_binding': report['input_binding'], 'measurements': measurements,
        'coverage_changes': report['coverage_changes'], 'common_image_ocr': report['common_image_ocr']}


def run_cases(cases=CASES) -> dict:
    reports = []
    for case in cases:
        content = authored_video(case)
        reference = case.reference(content)  # Ground truth is the schedule, never recognized OCR.
        reports.append(summarize(case, native_compare(reference, content, case.language)))
    return {'schema_version': 'authored-code-policy-diagnostics-v1',
        'evaluation_kind': 'authored-code-policy-diagnostics-not-representative',
        'quality_approval': 'not_established', 'case_count': len(reports),
        'aggregation_note': 'No overall winner or quality threshold. Read interval losses alongside gains; all-frame OCR sample weights differ.',
        'application_records_created': 0, 'cases': reports}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=[case.case_id for case in CASES])
    args = parser.parse_args()
    block_outbound_sockets()
    chosen = tuple(case for case in CASES if args.case is None or case.case_id == args.case)
    print(json.dumps(run_cases(chosen), sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    try: main()
    except Exception:
        raise SystemExit('FAIL: authored code diagnostics; no frames, OCR, labels, paths or raw exception was logged.') from None
