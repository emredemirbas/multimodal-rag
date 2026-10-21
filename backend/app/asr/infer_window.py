"""One bounded PCM inference; stdin/stdout only, no retained audio or model pull."""
from importlib.metadata import version
import resource
import sys
from time import perf_counter

from .contracts import TranscriptionSlice
from .isolation import block_outbound_sockets
from .profile import MODEL_DIRECTORY, MAX_RESPONSE_BYTES, encode_result, identity, verify_model
from .wav import MAX_PCM_BYTES, SAMPLE_RATE


def main(language: str) -> None:
    if language not in {"auto", "en", "tr"}:
        raise ValueError("Unsupported language")
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_RESPONSE_BYTES, MAX_RESPONSE_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (30, 32))
    block_outbound_sockets()
    pcm = sys.stdin.buffer.read(MAX_PCM_BYTES + 1)
    if not pcm or len(pcm) > MAX_PCM_BYTES or len(pcm) % 2:
        raise ValueError("Invalid PCM window")
    started = perf_counter()
    verify_model()
    if version("faster-whisper") != "1.2.1" or version("ctranslate2") != "4.8.2":
        raise ValueError("Unapproved ASR runtime")
    # Imports happen after the inherited network filter and resource limits.
    import numpy as np
    from faster_whisper import WhisperModel
    from ..transcripts import clean_cue_text

    audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    model = WhisperModel(str(MODEL_DIRECTORY), device="cpu", compute_type="int8", cpu_threads=2,
                         num_workers=1, local_files_only=True)
    segments, info = model.transcribe(audio, language=None if language == "auto" else language,
        beam_size=1, best_of=1, temperature=0.0, condition_on_previous_text=False,
        vad_filter=False, word_timestamps=False, max_new_tokens=256)
    evidence = []
    for segment in segments:
        text = clean_cue_text([segment.text])
        if not text:
            continue
        evidence.append({"start_ms": round(segment.start * 1000), "end_ms": round(segment.end * 1000), "text": text})
        if len(evidence) > 100:
            raise ValueError("Too many speech segments")
    result = TranscriptionSlice.model_validate({**identity(), "input_frames": len(pcm) // 2,
        "requested_language": language, "language": info.language, "language_probability": info.language_probability,
        "duration_ms": round((perf_counter() - started) * 1000), "segments": evidence})
    sys.stdout.buffer.write(encode_result(result.model_dump()))


if __name__ == "__main__":
    try:
        main(sys.argv[1] if len(sys.argv) == 2 else "invalid")
    except Exception:
        # Never emit raw model errors, PCM, recognized text or filesystem details.
        raise SystemExit(1) from None
