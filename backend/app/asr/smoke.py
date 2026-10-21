"""Explicit stateless model probe. Reads an operator-owned <=30s WAV on stdin."""
import argparse
import json
import re
import sys

from .client import LocalAsrProvider
from .wav import MAX_WAV_BYTES, SLICE_FRAMES, pcm_slice, validate_wav


def synthetic_health_terms(text: str) -> bool:
    # Speech may spell the same noun as "end point"; do not require a code token
    # or accept unrelated substrings such as "healthy" or "sendpoint".
    return bool(re.search(r"\bhealth\b", text, re.IGNORECASE) and re.search(r"\bend\s*point\b", text, re.IGNORECASE))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=["auto", "en", "tr"], default="en")
    parser.add_argument("--synthetic-health-check", action="store_true", help="Require health and endpoint/end point in an explicitly generated synthetic fixture, without printing text.")
    options = parser.parse_args()
    content = sys.stdin.buffer.read(MAX_WAV_BYTES + 1)
    wav = validate_wav("operator-owned-probe.wav", content)
    if wav.frames > SLICE_FRAMES:
        raise ValueError("Use a probe of at most 30 seconds; product ingestion is not enabled")
    result = LocalAsrProvider().transcribe(pcm_slice(content, wav, 0), options.language)
    if options.synthetic_health_check:
        recognized = " ".join(segment.text.lower() for segment in result.segments)
        if not synthetic_health_terms(recognized):
            raise ValueError("The owned synthetic fixture was not recognized as expected")
    print(json.dumps({"outcome": "passed", "model": result.model, "revision": result.revision,
        "duration_ms": result.duration_ms, "input_frames": result.input_frames, "segment_count": len(result.segments),
        "language": result.language, "synthetic_check": options.synthetic_health_check,
        "network_policy": result.network_policy, "spend_policy": "no-paid-provider"}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("FAIL: local ASR foundation probe; no transcript or raw exception was logged.") from None
