"""Pure bounded text diagnostics shared by the explicit ASR/OCR evaluators."""
from __future__ import annotations

import re
from typing import Sequence
import unicodedata

NORMALIZATION = "nfc-en-tr-words-v1"
MAX_EDIT_CELLS = 8_000_000


def words(text: str, language: str) -> list[str]:
    text = unicodedata.normalize("NFC", text)
    if language == "tr":
        text = text.replace("I", "ı").replace("İ", "i")
    text = text.casefold()
    return "".join(
        char if char == "_" or unicodedata.category(char)[0] in "LNM" else " "
        for char in text
    ).split()


def has_identifier(text: str, identifier: str) -> bool:
    # Literal, case-sensitive spelling with non-word boundaries; not code parsing.
    return re.search(r"(?<!\w)" + re.escape(identifier) + r"(?!\w)", text) is not None


def edit_distance(reference: Sequence, hypothesis: Sequence) -> int:
    """Unit-cost Levenshtein distance, with linear space and bounded work."""
    if len(reference) * len(hypothesis) > MAX_EDIT_CELLS:
        raise ValueError("Alignment work limit exceeded; use a shorter labeled clip")
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for row, expected in enumerate(reference, 1):
        current = [row]
        for column, actual in enumerate(hypothesis, 1):
            current.append(min(previous[column] + 1, current[-1] + 1,
                               previous[column - 1] + (expected != actual)))
        previous = current
    return previous[-1]
