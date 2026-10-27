"""Explicit authorized MP4 probe; content-free output, no application data."""
import argparse
import json
from pathlib import Path
import sys

from ..asr.isolation import block_outbound_sockets
from .local import LocalVisualProvider
from .change import LocalChangeVisualProvider
from .contracts import WireResult
from .evaluate import EvaluationRun, evaluate, load_reference, verify_video
from .media import MAX_VIDEO_BYTES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorized-input", action="store_true", required=True)
    parser.add_argument("--language", choices=["en", "tr", "en+tr"], default="en")
    parser.add_argument('--selection', choices=['uniform', 'change'], default='uniform')
    diagnostic = parser.add_mutually_exclusive_group()
    diagnostic.add_argument("--synthetic-card-check", action="store_true", help="Require HEALTH and CHECK in explicitly authored synthetic cards, without printing OCR.")
    diagnostic.add_argument("--reference", type=Path, help="Explicit local labels bound to this MP4; print content-free OCR/retained-frame diagnostics.")
    options = parser.parse_args()
    reference = load_reference(options.reference) if options.reference else None
    content = sys.stdin.buffer.read(MAX_VIDEO_BYTES + 1)
    if reference is not None:
        verify_video(reference, content)
    block_outbound_sockets()
    provider = LocalChangeVisualProvider() if options.selection == 'change' else LocalVisualProvider()
    result = provider.extract(content, options.language)
    if reference is not None:
        report = evaluate(reference, EvaluationRun(schema_version="visual-result-v1",
            input_bytes=len(content), result=WireResult.from_result(result)))
        report["input_binding"] = "verified-mp4-bytes"
        print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
        return
    if options.synthetic_card_check:
        import re
        text = " ".join(frame.text for frame in result.frames)
        if not re.search(r"\bhealth\b", text, re.IGNORECASE) or not re.search(r"\bcheck\b", text, re.IGNORECASE):
            raise ValueError("Synthetic card terms were not recognized")
    print(json.dumps({**result.summary(), "synthetic_check": options.synthetic_card_check}, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("FAIL: local visual probe; no frames, OCR, paths or raw exception was logged.") from None
