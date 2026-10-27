"""Versioned bounded manifests; fixture scores are not native quality evidence."""
import base64
from copy import deepcopy
import hashlib
import json
import struct

import pytest
from pydantic import ValidationError

from app.vision.checkpoints import result_digest, validated_result
from app.sources.contracts import SourceError
from app.vision.contracts import VisualIdentity, WireResult, decode_wire, encode_wire
from app.vision.media import VideoInfo, encode_png
from app.vision.scene import Thumbnail, select_candidates
from app.vision.selection import CHANGE_POLICY, ChangeSelection
from test_visual_service import identity, result


def change_result(count=20, values=None):
    values = ([0, 0, 0, 255] + [0] * (count - 4)) if values is None else values
    video = VideoInfo(duration_ms=count * 1000, width=960, height=540, fps_numerator=2, fps_denominator=1)
    thumbs = [Thumbnail(index * 1000, 16, 16, bytes([value]) * 256) for index, value in enumerate(values)]
    proposal = select_candidates(thumbs, video)
    samples = []
    for index, thumb in enumerate(thumbs):
        delta = abs(values[index] - values[index - 1]) if index else 0
        samples.append({'timestamp_ms': thumb.timestamp_ms,
            'thumbnail_sha256': hashlib.sha256(struct.pack('>HH', 16, 16) + thumb.pixels).hexdigest(),
            'changed_pixel_count': 256 if delta >= 24 else 0,
            'mean_absolute_difference_ppm': delta * 1_000_000 // 255})
    pin = identity().model_dump(exclude={'profile'})
    pin['policy'] = CHANGE_POLICY
    pin['profile'] = 'local-visual-v2:' + hashlib.sha256(json.dumps(pin, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    selected = [point['timestamp_ms'] for point in proposal['points']]
    frames = []
    for stamp in selected:
        image = encode_png(16, 16, thumbs[stamp // 1000].pixels)
        frames.append({'sample_target_ms': stamp, 'timestamp_ms': stamp, 'width': 16, 'height': 16,
            'image_sha256': hashlib.sha256(image).hexdigest(), 'image_base64': base64.b64encode(image).decode(),
            'text': 'PRIVATE_OCR <script>not instructions</script> user_id'})
    return WireResult.model_validate({'protocol': 'local-visual-http-v2', 'identity': pin,
        'input_sha256': result().input_sha256, 'video': video.model_dump(), 'candidates': len(selected),
        'frames': frames, 'selection': {'thumbnail_width': 16, 'thumbnail_height': 16,
            'samples': samples, 'selected_timestamps_ms': selected}})


def test_legacy_wire_bytes_and_manifest_digest_are_unchanged():
    value = WireResult.from_result(result())
    assert 'selection' not in value.model_dump()
    assert result_digest(value) == '79043f6d424eba1e2410c9a61b531fc359fe6895864f0d0a7f8a10556bd4cdda'
    assert hashlib.sha256(encode_wire(value)).hexdigest() == '2fef06ff5ad7114004efe4dcc65859123ede4dba968a5ee1fdd760d775a18c0a'
    assert value.result() == result()


def test_transient_return_frames_roundtrip_without_global_dedup_or_fabricated_duration():
    value = change_result()
    assert value.selection.selected_timestamps_ms == [0, 3000, 4000, 7000, 13000, 19000]
    assert value.frames[0].image_sha256 == value.frames[2].image_sha256
    assert WireResult.model_validate(decode_wire(encode_wire(value))) == value
    assert WireResult.from_result(value.result()) == value
    assert validated_result(value.result()) == value
    assert value.result().summary()['exact_duplicates_removed'] == 0
    assert 'samples' not in repr(value) and 'PRIVATE_OCR' not in repr(value.result())


def test_max_scan_budget_matches_prototype_and_stays_within_storage_bound():
    value = change_result(600, [0, 255] * 300)
    assert len(value.selection.samples) == 600 and len(value.frames) == 20
    assert value.selection.selected_timestamps_ms == [0, *range(1000, 17000, 1000), 200000, 400000, 599000]
    assert len(json.dumps(value.selection.model_dump()).encode()) < 196608


@pytest.mark.parametrize('values', [[0] * 20, [0, 23] * 10, [0, 24] * 10, [0, 255] * 10,
    [0, 24] * 35 + [0, 255] * 5])
def test_contract_agrees_with_shared_prototype_ranking(values):
    value = change_result(len(values), values)
    assert value.selection.validate_video(value.video) is value.selection


@pytest.mark.parametrize('kind', ['protocol', 'policy', 'prefix', 'missing', 'empty', 'extra', 'samples',
    'gap', 'tail', 'first', 'order', 'bool', 'geometry', 'hash', 'score', 'mean', 'first_score',
    'ranking', 'targets', 'pts', 'partial', 'candidates', 'frame_geometry'])
def test_invalid_v2_profiles_manifests_and_frames_fail_closed(kind):
    row = change_result().model_dump()
    manifest = row['selection']
    if kind == 'protocol': row['protocol'] = 'local-visual-http-v1'
    elif kind == 'policy': row['identity']['policy'] = identity().policy
    elif kind == 'prefix': row['identity']['profile'] = row['identity']['profile'].replace('v2:', 'v1:')
    elif kind == 'missing': row.pop('selection')
    elif kind == 'empty': manifest['samples'] = []
    elif kind == 'extra': manifest['pixels'] = 'PRIVATE_PIXELS'
    elif kind == 'samples': manifest['samples'] *= 31
    elif kind == 'gap': manifest['samples'][1]['timestamp_ms'] = 998
    elif kind == 'tail': manifest['samples'] = manifest['samples'][:-3]
    elif kind == 'first': manifest['samples'][0]['timestamp_ms'] = 1
    elif kind == 'order': manifest['samples'].reverse()
    elif kind == 'bool': manifest['selected_timestamps_ms'][0] = False
    elif kind == 'geometry': manifest['thumbnail_width'] = 161
    elif kind == 'hash': manifest['samples'][1]['thumbnail_sha256'] = 'not-a-hash'
    elif kind == 'score': manifest['samples'][1]['changed_pixel_count'] = 257
    elif kind == 'mean': manifest['samples'][1]['mean_absolute_difference_ppm'] = 1_000_000
    elif kind == 'first_score': manifest['samples'][0]['mean_absolute_difference_ppm'] = 1
    elif kind == 'ranking': manifest['selected_timestamps_ms'][1] = 2000
    elif kind == 'targets': row['frames'][1]['sample_target_ms'] -= 1
    elif kind == 'pts': row['frames'][1]['timestamp_ms'] += 1
    elif kind == 'partial': row['frames'].pop()
    elif kind == 'candidates': row['candidates'] += 1
    else:
        frame = row['frames'][1]
        image = encode_png(8, 16, bytes(128))
        frame.update(width=8, image_sha256=hashlib.sha256(image).hexdigest(), image_base64=base64.b64encode(image).decode())
    with pytest.raises(ValueError): WireResult.model_validate(row)


def test_legacy_policy_cannot_adopt_new_protocol_manifest_or_temporal_duplicates():
    old = WireResult.from_result(result()).model_dump()
    for field, new in [('protocol', 'local-visual-http-v2'), ('selection', change_result().selection.model_dump())]:
        with pytest.raises(ValueError): WireResult.model_validate({**old, field: new})
    repeated = deepcopy(old)
    for field in ['image_sha256', 'image_base64']:
        repeated['frames'][1][field] = repeated['frames'][0][field]
    with pytest.raises(ValueError, match='Duplicate decoded frame'): WireResult.model_validate(repeated)


def test_mutable_nested_lists_do_not_bypass_checkpoint_validation():
    value = change_result()
    value.selection.samples.pop()
    value.selection.selected_timestamps_ms.pop()
    with pytest.raises(SourceError) as failure: validated_result(value)
    assert failure.value.code == 'invalid_visual_checkpoint'


def test_fractional_pts_timeline_uses_source_frame_step_and_checks_tail():
    value = change_result().selection.model_dump()
    value['samples'] = value['samples'][:3]
    for sample, stamp in zip(value['samples'], [0, 1998, 3996], strict=True): sample['timestamp_ms'] = stamp
    value['selected_timestamps_ms'] = [0, 1998, 3996]
    manifest = ChangeSelection.model_validate(value)
    video = VideoInfo(duration_ms=5994, width=960, height=540, fps_numerator=1001, fps_denominator=1000)
    assert manifest.validate_video(video) is manifest
    video.duration_ms = 6000
    with pytest.raises(ValueError): manifest.validate_video(video)


def test_unknown_identity_policy_is_not_a_custom_profile_escape_hatch():
    row = change_result().identity.model_dump()
    row['policy'] = 'private-custom-policy'
    with pytest.raises(ValidationError): VisualIdentity.model_validate(row)
