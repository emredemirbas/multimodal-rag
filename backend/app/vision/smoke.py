"""Explicit authorized MP4 probe; content-free output, no application data."""
import argparse
import json
import sys

from ..asr.isolation import block_outbound_sockets
from .local import LocalVisualProvider
from .media import MAX_VIDEO_BYTES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorized-input", action="store_true", required=True)
    parser.add_argument("--language", choices=["en", "tr", "en+tr"], default="en")
    parser.add_argument("--synthetic-card-check", action="store_true", help="Require HEALTH and CHECK in explicitly authored synthetic cards, without printing OCR.")
    options = parser.parse_args()
    block_outbound_sockets()
    content = sys.stdin.buffer.read(MAX_VIDEO_BYTES + 1)
    result = LocalVisualProvider().extract(content, options.language)
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
