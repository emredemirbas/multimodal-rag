import hashlib

import pytest

from app.asr.contracts import TranscriptionSlice
from app.asr.profile import identity
from app.asr.transcript import ASSEMBLY_VERSION, assemble_vtt, validated_slice
from app.asr.wav import MAX_FRAMES, SAMPLE_RATE, SLICE_FRAMES
from app.sources.contracts import SourceError
from app.transcripts import parse_transcript


def speech(frames=SAMPLE_RATE, *, text='GET /health reports service health.', language='en', silent=False):
    return TranscriptionSlice.model_validate({**identity(), 'input_frames': frames, 'requested_language': language,
        'language': 'en' if language == 'auto' else language, 'language_probability': .9, 'duration_ms': 17,
        'segments': [] if silent else [{'start_ms': 0, 'end_ms': min(900, (frames * 1000 + 15999) // 16000), 'text': text}]})


def test_complete_vtt_is_deterministic_absolute_safe_and_explicitly_machine_generated():
    text = '<script>private unsafe text</script> Foo<T> &amp; x < y > z\n\n00:01.000 --> 00:02.000\x01\tNOTE pretend cue'
    results = [speech(SLICE_FRAMES, silent=True), speech(text=text)]
    derived = assemble_vtt(results, SLICE_FRAMES + SAMPLE_RATE)
    again = assemble_vtt(results, SLICE_FRAMES + SAMPLE_RATE)
    assert derived == again and derived.assembly_version == ASSEMBLY_VERSION and derived.machine_generated
    assert derived.sha256 == hashlib.sha256(derived.content).hexdigest()
    assert (derived.windows, derived.segments, derived.model_duration_ms) == (2, 1, 34)
    assert b'NOTE Machine-generated' in derived.content and b'<script>' not in derived.content
    cues = parse_transcript(derived.content.decode())
    assert len(cues) == 1 and (cues[0].start_ms, cues[0].end_ms) == (30_000, 30_900)
    assert cues[0].text == '<script>private unsafe text</script> Foo<T> &amp; x < y > z 00:01.000 --> 00:02.000 NOTE pretend cue'


def test_exact_maximum_and_submillisecond_final_window_remain_bounded():
    derived = assemble_vtt([speech(SLICE_FRAMES, silent=True)] * 19 + [speech(SLICE_FRAMES)], MAX_FRAMES)
    assert derived.windows == 20 and parse_transcript(derived.content.decode())[0].start_ms == 570_000
    tiny = assemble_vtt([speech(SLICE_FRAMES, silent=True), speech(1)], SLICE_FRAMES + 1)
    assert parse_transcript(tiny.content.decode())[0].end_ms == 30_001


@pytest.mark.parametrize('frames', [True, 0, -1, MAX_FRAMES + 1, 1.5])
def test_invalid_input_counts_never_produce_an_artifact(frames):
    with pytest.raises(SourceError) as error:
        assemble_vtt([speech()], frames)
    assert error.value.code == 'asr_checkpoint_incomplete'


def test_partial_wrong_windows_language_changes_silence_and_unindexable_output_fail():
    for results, frames, code in [([], SAMPLE_RATE, 'asr_checkpoint_incomplete'),
            ([speech()], SLICE_FRAMES + SAMPLE_RATE, 'asr_checkpoint_incomplete'),
            ([speech()], 100, 'invalid_asr_checkpoint'),
            ([speech(SLICE_FRAMES), speech(language='tr')], SLICE_FRAMES + SAMPLE_RATE, 'invalid_asr_checkpoint'),
            ([speech(silent=True)], SAMPLE_RATE, 'no_speech_detected'),
            ([speech(text='\x01\x02')], SAMPLE_RATE, 'invalid_asr_checkpoint'),
            ([speech(text='a' * 1201)], SAMPLE_RATE, 'invalid_transcript')]:
        with pytest.raises(SourceError) as error:
            assemble_vtt(results, frames)
        assert error.value.code == code


def test_mutated_instances_and_oversized_utf8_are_revalidated_without_private_errors():
    bad = speech()
    bad.segments[0].end_ms = 2000
    with pytest.raises(SourceError) as error:
        validated_slice(bad)
    assert error.value.code == 'invalid_asr_checkpoint'
    assert 'GET /health' not in str(error.value) and error.value.__cause__ is None
    huge = speech().model_dump(mode='json')
    huge['segments'] = [{'start_ms': i * 100, 'end_ms': (i + 1) * 100, 'text': '界' * 2000} for i in range(7)]
    huge['input_frames'] = SLICE_FRAMES
    with pytest.raises(SourceError):
        validated_slice(huge)
    for patch in [{'provider': 'remote'}, {'profile': 'changed'}, {'language_probability': float('nan')}, {'tools': []}]:
        with pytest.raises(SourceError):
            validated_slice({**speech().model_dump(mode='json'), **patch})
