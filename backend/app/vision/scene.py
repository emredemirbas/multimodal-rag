"""Isolated operator-only change candidates; never a managed visual result."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
from time import monotonic

from ..asr.isolation import block_outbound_sockets
from .local import INPUT_OPTIONS, NativeRunner, require_isolation
from .media import MAX_FRAMES, MAX_VIDEO_BYTES, VideoInfo, parse_pgm, parse_probe, validate_mp4
from .selection import (ANCHORS, MAX_HEIGHT, MAX_SCAN_FRAMES, MAX_WIDTH, MIN_CHANGED_PPM,
                        PIXEL_DELTA, SCAN_INTERVAL_MS, ChangeSelection, selection_indices)

POLICY = "visual-change-probe-1s-gray160x90-d24-p002-cap20-v1"


@dataclass(frozen=True)
class Thumbnail:
    timestamp_ms: int
    width: int
    height: int
    pixels: bytes = field(repr=False)


def _parameters():
    return {"scan_interval_ms": SCAN_INTERVAL_MS, "max_scan_frames": MAX_SCAN_FRAMES,
        "max_width": MAX_WIDTH, "max_height": MAX_HEIGHT, "pixel_delta": PIXEL_DELTA,
        "min_changed_ppm": MIN_CHANGED_PPM, "anchors": ANCHORS, "max_selected_points": MAX_FRAMES}


def _scored_points(samples: list[Thumbnail], info: VideoInfo) -> list[dict]:
    """All scores use actual thumbnail pixels/PTS; no inferred visible duration."""
    info = VideoInfo.model_validate(info.model_dump())
    if not 1 <= Fraction(info.fps_numerator, info.fps_denominator) <= 60:
        raise ValueError("Unsupported scan frame rate")
    if not isinstance(samples, (list, tuple)) or not 1 <= len(samples) <= MAX_SCAN_FRAMES:
        raise ValueError("Invalid scan count")
    previous = None
    points = []
    # A constant-rate source may need up to one more source frame to meet the
    # one-second spacing; allow one millisecond for encoded-PTS quantization.
    frame_step_ms = (1000 * info.fps_denominator + info.fps_numerator - 1) // info.fps_numerator
    max_gap = SCAN_INTERVAL_MS + frame_step_ms + 1
    for sample in samples:
        if (not isinstance(sample, Thumbnail) or type(sample.timestamp_ms) is not int
                or not 0 <= sample.timestamp_ms < info.duration_ms
                or type(sample.width) is not int or type(sample.height) is not int
                or not 1 <= sample.width <= MAX_WIDTH or not 1 <= sample.height <= MAX_HEIGHT
                or type(sample.pixels) is not bytes or len(sample.pixels) != sample.width * sample.height):
            raise ValueError("Invalid scan thumbnail")
        if previous is None:
            if sample.timestamp_ms != 0:
                raise ValueError("Scan must begin at zero")
            changed = difference = 0
        else:
            gap = sample.timestamp_ms - previous.timestamp_ms
            if (not SCAN_INTERVAL_MS - 1 <= gap <= max_gap
                    or (sample.width, sample.height) != (previous.width, previous.height)):
                raise ValueError("Invalid scan timeline or geometry")
            changed = difference = 0
            for before, after in zip(previous.pixels, sample.pixels, strict=True):
                delta = abs(before - after)
                changed += delta >= PIXEL_DELTA
                difference += delta
        size = len(sample.pixels)
        points.append({"timestamp_ms": sample.timestamp_ms,
            "thumbnail_sha256": hashlib.sha256(struct.pack('>HH', sample.width, sample.height) + sample.pixels).hexdigest(),
            "changed_pixel_count": changed, "changed_ppm": changed * 1_000_000 // size,
            "mean_absolute_difference_ppm": difference * 1_000_000 // (size * 255)})
        previous = sample
    if info.duration_ms - samples[-1].timestamp_ms > max_gap:
        raise ValueError("Scan stopped before the end of the video")
    return points


def select_candidates(samples: list[Thumbnail], info: VideoInfo) -> dict:
    points = _scored_points(samples, info)

    anchor_indices, eligible, selected = selection_indices(
        [point['timestamp_ms'] for point in points], [point['changed_pixel_count'] for point in points],
        [point['mean_absolute_difference_ppm'] for point in points], len(samples[0].pixels), info.duration_ms)
    return {"scan_samples": len(samples), "thumbnail_width": samples[0].width,
        "thumbnail_height": samples[0].height, "eligible_changes": len(eligible),
        "omitted_changes": sum(index not in selected for index in eligible),
        "selected_points": len(selected), "parameters": _parameters(),
        "points": [{**point, "anchor": index in anchor_indices,
                    "change": point['changed_ppm'] >= MIN_CHANGED_PPM}
                   for index, point in enumerate(points) if index in selected]}


def manifest_for(samples: list[Thumbnail], info: VideoInfo) -> ChangeSelection:
    points = _scored_points(samples, info)
    _, _, selected = selection_indices([point['timestamp_ms'] for point in points],
        [point['changed_pixel_count'] for point in points],
        [point['mean_absolute_difference_ppm'] for point in points], len(samples[0].pixels), info.duration_ms)
    return ChangeSelection.model_validate({'thumbnail_width': samples[0].width,
        'thumbnail_height': samples[0].height,
        'samples': [{key: value for key, value in point.items() if key != 'changed_ppm'} for point in points],
        'selected_timestamps_ms': [points[index]['timestamp_ms'] for index in sorted(selected)]}).validate_video(info)


def scan_thumbnails(source: Path, root: Path, runner: NativeRunner) -> list[Thumbnail]:
    output = root / 'scan'
    output.mkdir()
    runner.run(['/usr/bin/ffmpeg', '-nostdin', '-v', 'error', '-threads', '1', '-filter_threads', '1',
        '-copyts', *INPUT_OPTIONS, '-i', str(source), '-map', '0:v:0', '-an', '-sn', '-dn', '-vf',
        "select='isnan(prev_selected_t)+gte(t-prev_selected_t,1)',scale=160:90:force_original_aspect_ratio=decrease:flags=bilinear,format=gray",
        '-frames:v', str(MAX_SCAN_FRAMES + 1), '-c:v', 'pgm', '-threads', '1', '-vsync', '0',
        '-enc_time_base', '1:1000', '-frame_pts', '1', '-f', 'image2', str(output / '%d.pgm')])
    files = []
    for path in output.iterdir():
        files.append(path)
        if len(files) > MAX_SCAN_FRAMES:
            raise ValueError("Excessive scan output")
    if not files:
        raise ValueError("Missing scan output")
    samples = []
    for path in files:
        if path.is_symlink() or not path.is_file() or not re.fullmatch(r'[0-9]{1,6}\.pgm', path.name):
            raise ValueError("Invalid scan output path")
        with path.open('rb') as stream:
            pgm = stream.read(15_001)
        if len(pgm) > 15_000:
            raise ValueError("Scan image exceeds limit")
        width, height, pixels = parse_pgm(pgm)
        samples.append(Thumbnail(int(path.stem), width, height, pixels))
    if monotonic() > runner.deadline:
        raise ValueError("Scan deadline exceeded")
    return sorted(samples, key=lambda sample: sample.timestamp_ms)


def probe(content: bytes) -> dict:
    validate_mp4(content)  # Invalid inputs must not start native processing.
    require_isolation()
    runner = NativeRunner()
    version = runner.run(['/usr/bin/ffmpeg', '-version'], limit=4096)
    match = re.match(rb'ffmpeg version ([0-9A-Za-z.+~:-]{1,64}) ', version)
    if not match:
        raise ValueError("Unknown native engine identity")
    engine = match[1].decode('ascii')
    with tempfile.TemporaryDirectory(prefix='visual-change-', dir='/tmp') as directory:
        root = Path(directory)
        source = root / 'input.mp4'
        source.write_bytes(content)
        metadata = runner.run(['/usr/bin/ffprobe', '-v', 'error', *INPUT_OPTIONS,
            '-show_entries', 'format=duration,start_time:stream=codec_type,codec_name,codec_tag_string,width,height,pix_fmt,start_time,duration,avg_frame_rate,r_frame_rate:stream_side_data=rotation',
            '-of', 'json', str(source)])
        info = parse_probe(metadata)
        selection = select_candidates(scan_thumbnails(source, root, runner), info)
        if monotonic() > runner.deadline:
            raise ValueError("Scan deadline exceeded")
    identity = {"provider": "local-ffmpeg-change-probe", "engine": engine,
                "policy": POLICY, "parameters": _parameters()}
    profile = 'visual-change-probe-v1:' + hashlib.sha256(json.dumps(identity,
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {"schema_version": "visual-change-candidates-v1", "outcome": "operator-prototype-complete",
        "quality_approval": "not_established", "input_sha256": hashlib.sha256(content).hexdigest(),
        "video": info.model_dump(), "identity": {**identity, "profile": profile}, **selection}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorized-input', action='store_true', required=True)
    parser.parse_args()
    content = sys.stdin.buffer.read(MAX_VIDEO_BYTES + 1)
    block_outbound_sockets()
    print(json.dumps(probe(content), sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('FAIL: isolated change probe; no pixels, OCR, paths or raw exception was logged.') from None
