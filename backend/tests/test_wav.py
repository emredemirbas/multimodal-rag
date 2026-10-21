import io
import struct
import wave

import pytest

from app.asr.wav import MAX_FRAMES, MAX_WAV_BYTES, SAMPLE_RATE, SLICE_FRAMES, pcm_slice, validate_wav
from app.sources.contracts import SourceError


def wav_bytes(frames=SAMPLE_RATE, *, rate=SAMPLE_RATE, channels=1, width=2):
    output = io.BytesIO()
    with wave.open(output, "wb") as file:
        file.setnchannels(channels)
        file.setsampwidth(width)
        file.setframerate(rate)
        file.writeframes(b"\x00" * frames * channels * width)
    return output.getvalue()


def riff(chunks):
    payload = b"WAVE" + b"".join(kind + struct.pack("<I", len(data)) + data + (b"\x00" if len(data) % 2 else b"") for kind, data in chunks)
    return b"RIFF" + struct.pack("<I", len(payload)) + payload


def test_bounded_wav_timeline_and_exact_pcm_windows():
    content = wav_bytes(SLICE_FRAMES + 41)
    info = validate_wav("C:\\fakepath\\lesson.WAV", content)
    assert info.filename == "lesson.WAV" and info.frames == SLICE_FRAMES + 41 and info.duration_ms == 30_003
    assert len(pcm_slice(content, info, 0)) == SLICE_FRAMES * 2
    assert len(pcm_slice(content, info, SLICE_FRAMES)) == 82
    assert pcm_slice(content, info, 0) + pcm_slice(content, info, SLICE_FRAMES) == content[info.data_offset:]
    for offset in [-1, info.frames, True, 1.5]:
        with pytest.raises(SourceError):
            pcm_slice(content, info, offset)
    with pytest.raises(SourceError):
        pcm_slice(b"short", info, 0)


@pytest.mark.parametrize("change", [{"rate": 44100}, {"channels": 2}, {"width": 1}, {"width": 4}])
def test_other_wav_encodings_are_actionably_rejected(change):
    with pytest.raises(SourceError) as error:
        validate_wav("tutorial.wav", wav_bytes(**change))
    assert error.value.code == "unsupported_wav_encoding" and "16 kHz" in str(error.value)


def test_size_duration_and_filename_boundaries():
    assert validate_wav("valid.wav", wav_bytes(MAX_FRAMES)).duration_ms == 600_000
    with pytest.raises(SourceError) as error:
        validate_wav("long.wav", wav_bytes(MAX_FRAMES + 1))
    assert error.value.code == "audio_duration_limit"
    with pytest.raises(SourceError) as error:
        validate_wav("large.wav", b"x" * (MAX_WAV_BYTES + 1))
    assert error.value.status == 413 and error.value.code == "audio_too_large"
    for name in ["http://remote.test/audio.mp3", "video.mp4", "x\x00.wav", "x" * 256 + ".wav", "file.wav.exe"]:
        with pytest.raises(SourceError) as error:
            validate_wav(name, wav_bytes())
        assert error.value.code == "invalid_audio_type"


def test_riff_lengths_duplicates_metadata_padding_and_missing_chunks():
    fmt = struct.pack("<HHIIHH", 1, 1, SAMPLE_RATE, SAMPLE_RATE * 2, 2, 16)
    data = b"\x01\x00" * 80
    valid = riff([(b"JUNK", b"x"), (b"fmt ", fmt + b"\x00\x00"), (b"LIST", b"<script>never parsed</script>"), (b"data", data)])
    info = validate_wav("metadata.wav", valid)
    assert pcm_slice(valid, info, 0) == data
    broken = [b"", b"RIFF", valid[:-1], valid + b"extra", b"RIFX" + valid[4:], riff([(b"data", data), (b"fmt ", fmt)]),
        riff([(b"fmt ", fmt), (b"fmt ", fmt), (b"data", data)]), riff([(b"fmt ", fmt), (b"data", data), (b"data", data)]),
        riff([(b"fmt ", fmt)]), riff([(b"fmt ", fmt), (b"data", b"")]), riff([(b"fmt ", fmt), (b"data", b"x")]),
        riff([(b"fmt ", fmt), (b"data", data)] + [(b"JUNK", b"")] * 63), riff([(b"fmt ", fmt + b"invalid"), (b"data", data)]),
        riff([(b"fmt ", fmt + b"\x01\x00"), (b"data", data)])]
    for content in broken:
        with pytest.raises(SourceError):
            validate_wav("broken.wav", content)
    overflow = bytearray(riff([(b"fmt ", fmt), (b"data", data)]))
    struct.pack_into("<I", overflow, 40, 0xFFFFFFFF)
    with pytest.raises(SourceError):
        validate_wav("overflow.wav", bytes(overflow))
