#!/usr/bin/env python3
"""Provider-neutral Sprint 0 ingestion cost calculator.

Defaults are planning assumptions, not vendor price claims. Pass negotiated or
published provider rates before using the result for a business decision.
"""

from __future__ import annotations

import argparse
import json


def estimate(
    *,
    hours: float,
    tokens_per_hour: int,
    frames_per_hour: int,
    asr_per_minute: float,
    embedding_per_million_tokens: float,
    visual_per_frame: float,
    derived_storage_mb_per_hour: float,
    storage_per_gb_month: float,
    contingency: float,
) -> dict[str, float]:
    embedding = hours * tokens_per_hour / 1_000_000 * embedding_per_million_tokens
    visual = hours * frames_per_hour * visual_per_frame
    storage = hours * derived_storage_mb_per_hour / 1024 * storage_per_gb_month
    transcript_path = embedding + visual + storage
    asr = hours * 60 * asr_per_minute
    media_path = transcript_path + asr
    return {
        "hours": hours,
        "embedding_usd": round(embedding, 6),
        "visual_description_usd": round(visual, 6),
        "derived_storage_first_month_usd": round(storage, 6),
        "asr_usd": round(asr, 6),
        "uploaded_transcript_path_usd": round(transcript_path, 4),
        "authorized_media_path_usd": round(media_path, 4),
        "uploaded_transcript_with_contingency_usd": round(transcript_path * contingency, 4),
        "authorized_media_with_contingency_usd": round(media_path * contingency, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=1.0)
    parser.add_argument("--tokens-per-hour", type=int, default=15_000)
    parser.add_argument("--frames-per-hour", type=int, default=120)
    parser.add_argument("--asr-per-minute", type=float, default=0.006)
    parser.add_argument("--embedding-per-million-tokens", type=float, default=0.02)
    parser.add_argument("--visual-per-frame", type=float, default=0.0005)
    parser.add_argument("--derived-storage-mb-per-hour", type=float, default=25.0)
    parser.add_argument("--storage-per-gb-month", type=float, default=0.023)
    parser.add_argument("--contingency", type=float, default=1.2)
    args = parser.parse_args()
    if args.hours <= 0:
        parser.error("--hours must be greater than zero")
    if args.contingency < 1:
        parser.error("--contingency must be at least 1")
    print(json.dumps(estimate(**vars(args)), indent=2))


if __name__ == "__main__":
    main()
