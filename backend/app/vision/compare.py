"""Paired authorized single-clip diagnostics, never a policy/quality approval."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys

from ..asr.isolation import block_outbound_sockets
from ..evaluation import MAX_EDIT_CELLS
from .change import LocalChangeVisualProvider
from .contracts import WireResult, checked_png
from .evaluate import (EvaluationRun, Reference, _empty_counts, _measure, _prepare,
                       _scores, load_reference, verify_video)
from .local import LocalVisualProvider
from .media import MAX_VIDEO_BYTES, POLICY, validate_mp4
from .selection import CHANGE_POLICY


def _pixel_id(frame):
    return frame.width, frame.height, hashlib.sha256(checked_png(
        base64.b64decode(frame.image_base64), frame.width, frame.height)).digest()


def compare(reference: Reference, uniform: EvaluationRun, change: EvaluationRun) -> dict:
    left = _prepare(reference, uniform)
    right = _prepare(left[0], change)  # Both measurements use the same validated label snapshot.
    baseline, candidate = left[1].result, right[1].result
    if baseline.identity.policy != POLICY or candidate.identity.policy != CHANGE_POLICY:
        raise ValueError('Compare uniform v1 against change v2 in that order')
    if baseline.identity.model_dump(exclude={'policy', 'profile'}) != candidate.identity.model_dump(exclude={'policy', 'profile'}):
        raise ValueError('Paired policies require identical OCR engine/language identities')
    if left[3] + right[3] > MAX_EDIT_CELLS:
        raise ValueError('Combined alignment work limit exceeded')
    before = {frame.timestamp_ms: frame for frame in baseline.frames}
    after = {frame.timestamp_ms: frame for frame in candidate.frames}
    common = sorted(before.keys() & after.keys())
    if any(_pixel_id(before[stamp]) != _pixel_id(after[stamp]) for stamp in common):
        raise ValueError('Conflicting pixels at a shared source timestamp')

    reports = {'uniform': _measure(*left[:3]), 'change': _measure(*right[:3])}
    covered = {name: {interval['ordinal'] for interval in report['intervals'] if interval['selected_frame_count']}
               for name, report in reports.items()}
    paired = {}
    for name, report in reports.items():
        totals = _empty_counts()
        for interval in report['intervals']:
            for frame in interval['frames']:
                if frame['timestamp_ms'] in common:
                    for key in totals: totals[key] += frame['ocr'][key]
        paired[name] = _scores(totals)
    all_intervals = set(range(len(left[0].intervals)))
    return {'schema_version': 'visual-policy-comparison-v1', 'evaluation_kind': 'paired_single_clip_diagnostic',
        'quality_approval': 'not_established', 'input_binding': 'declared-reference-results',
        'aggregation_note': 'All-frame OCR weights differ by sampling; compare coverage and identical shared-PTS OCR separately. No automatic winner.',
        'measurements': reports,
        'coverage_changes': {'gained_ordinals': sorted(covered['change'] - covered['uniform']),
            'lost_ordinals': sorted(covered['uniform'] - covered['change']),
            'shared_ordinals': sorted(covered['uniform'] & covered['change']),
            'missed_by_both_ordinals': sorted(all_intervals - covered['uniform'] - covered['change'])},
        'common_image_ocr': {'timestamps_ms': common, 'aggregation': 'micro-over-labeled-identical-shared-PTS-frames',
                             **paired}}


def native_compare(reference: Reference, content: bytes, language='en') -> dict:
    verify_video(reference, content)
    validate_mp4(content)
    if language not in {'en', 'tr', 'en+tr'}: raise ValueError('Unsupported OCR language')
    block_outbound_sockets()
    baseline = EvaluationRun(schema_version='visual-result-v1', input_bytes=len(content),
        result=WireResult.from_result(LocalVisualProvider().extract(content, language)))
    _prepare(reference, baseline)  # Bad expected metadata must stop before the second native call.
    candidate = EvaluationRun(schema_version='visual-result-v1', input_bytes=len(content),
        result=WireResult.from_result(LocalChangeVisualProvider().extract(content, language)))
    report = compare(reference, baseline, candidate)
    report['input_binding'] = 'verified-mp4-bytes'
    for measurement in report['measurements'].values(): measurement['input_binding'] = 'verified-mp4-bytes'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorized-input', action='store_true', required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--language', choices=['en', 'tr', 'en+tr'], default='en')
    args = parser.parse_args()
    reference = load_reference(args.reference)
    content = sys.stdin.buffer.read(MAX_VIDEO_BYTES + 1)
    print(json.dumps(native_compare(reference, content, args.language), sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    try: main()
    except Exception:
        raise SystemExit('FAIL: paired visual diagnostic; no media, OCR, labels, paths or raw exception was logged.') from None
