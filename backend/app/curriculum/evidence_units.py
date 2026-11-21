"""Lossless source-span partitioning only; no inference or caller authorization."""

from hashlib import sha256
import json
from typing import TYPE_CHECKING, Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from .contracts import Contract, Digest, Version

if TYPE_CHECKING:
    from .objectives import SourceBatch


PARTITION_VERSION = "evidence-units-byte-v1"
MAX_UNIT_BYTES = 80
MAX_SLICE_BYTES = 1800
MAX_BATCH_SLICES = 4
MAX_BATCHES = 20
UnitId = Annotated[str, StringConstraints(pattern=r"^u[0-9]{5}$")]
SliceId = Annotated[str, StringConstraints(pattern=r"^s[0-9]{5}$")]


def _bytes(text):
    if type(text) is not str or not text or "\x00" in text:
        raise ValueError("Invalid evidence text")
    try:
        return text.encode("utf-8")
    except UnicodeError:
        raise ValueError("Invalid evidence text") from None


class _SourceSpan(Contract):
    model_config = ConfigDict(frozen=True)

    slice_id: SliceId
    source_id: UUID
    segment_id: UUID
    processing_version: Version
    modality: Literal["transcript", "frame"]
    origin: Literal["uploaded_transcript", "unreviewed_asr", "unreviewed_ocr", "unreviewed_ocr_and_description"]
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    text: str = Field(repr=False)

    @model_validator(mode="after")
    def coherent(self):
        if (len(_bytes(self.text)) > MAX_SLICE_BYTES
                or self.end_char - self.start_char != len(self.text)
                or not self.processing_version.strip()):
            raise ValueError("Invalid source span")
        _bytes(self.processing_version)
        transcript = self.origin in {"uploaded_transcript", "unreviewed_asr"}
        if transcript != (self.modality == "transcript"):
            raise ValueError("Invalid evidence origin")
        return self


class EvidenceUnit(_SourceSpan):
    """A frozen exact source span; its ID is local to one versioned batch plan."""

    id: UnitId

    @model_validator(mode="after")
    def bounded(self):
        if len(_bytes(self.text)) > MAX_UNIT_BYTES:
            raise ValueError("Evidence unit exceeded its byte bound")
        return self


def _spans(text, start_char):
    start = size = 0
    for offset, char in enumerate(text):
        width = len(char.encode("utf-8"))
        if size + width > MAX_UNIT_BYTES:
            yield start_char + start, start_char + offset, text[start:offset]
            start, size = offset, 0
        size += width
    yield start_char + start, start_char + len(text), text[start:]


def _validated_sources(sources):
    if not 1 <= len(sources) <= MAX_BATCH_SLICES or len({item.slice_id for item in sources}) != len(sources):
        raise ValueError("Invalid evidence batch")
    segments = {}
    for source in sources:
        previous = segments.get(source.segment_id)
        if previous is not None:
            identity = (source.source_id, source.processing_version, source.modality, source.origin)
            prior_identity = (previous.source_id, previous.processing_version, previous.modality, previous.origin)
            if identity != prior_identity or source.start_char < previous.end_char:
                raise ValueError("Incoherent repeated source segment")
        segments[source.segment_id] = source
    return sources


def _digest(batch_index, sources):
    payload = {"partition_version": PARTITION_VERSION, "max_unit_bytes": MAX_UNIT_BYTES,
               "batch_index": batch_index, "slices": [item.model_dump(mode="json") for item in sources]}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256(encoded).hexdigest()


class UnitPlan(Contract):
    """Immutable partition plus a fingerprint of the full ordered source input."""

    model_config = ConfigDict(frozen=True)

    partition_version: Version
    batch_index: int = Field(ge=0, lt=MAX_BATCHES)
    plan_sha256: Digest
    units: tuple[EvidenceUnit, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def coherent(self):
        if self.partition_version != PARTITION_VERSION:
            raise ValueError("Unknown evidence partition")
        sources = []
        for index, unit in enumerate(self.units):
            if unit.id != f"u{index:05d}":
                raise ValueError("Changed evidence unit order")
            values = unit.model_dump(exclude={"id"})
            if sources and sources[-1]["slice_id"] == unit.slice_id:
                prior = sources[-1]
                if (any(values[key] != prior[key] for key in values if key not in {"start_char", "end_char", "text"})
                        or unit.start_char != prior["end_char"]):
                    raise ValueError("Changed evidence source span")
                prior["end_char"] = unit.end_char
                prior["text"] += unit.text
            else:
                sources.append(values)
        checked = _validated_sources([_SourceSpan.model_validate(item, strict=True) for item in sources])
        expected = [(start, end, text) for source in checked
                    for start, end, text in _spans(source.text, source.start_char)]
        if (expected != [(unit.start_char, unit.end_char, unit.text) for unit in self.units]
                or self.plan_sha256 != _digest(self.batch_index, checked)):
            raise ValueError("Changed evidence partition")
        return self


def plan_evidence_units(batch: "SourceBatch") -> UnitPlan:
    """Revalidate a bounded source batch, retaining every original character.

    Context scope, authoritative selected generations and authorization remain the
    caller's responsibility. This function fetches nothing and changes no state.
    """
    # Keep the existing extraction module independent of this optional boundary.
    from .objectives import PromptSlice, SourceBatch

    if (not isinstance(batch, SourceBatch) or type(batch.index) is not int
            or not 0 <= batch.index < MAX_BATCHES or type(batch.slices) is not tuple
            or not 1 <= len(batch.slices) <= MAX_BATCH_SLICES):
        raise ValueError("Invalid evidence batch")
    sources = []
    for supplied in batch.slices:
        if not isinstance(supplied, PromptSlice):
            raise ValueError("Invalid evidence slice")
        # Validate raw values first: serialization can turn a constructed bool
        # offset into a JSON integer and conceal an invalid in-memory input.
        item = PromptSlice.model_validate(supplied, strict=True)
        values = item.model_dump()
        values["slice_id"] = values.pop("id")
        sources.append(_SourceSpan.model_validate(values, strict=True))
    _validated_sources(sources)
    units = []
    for source in sources:
        values = source.model_dump(exclude={"start_char", "end_char", "text"})
        for start, end, text in _spans(source.text, source.start_char):
            units.append(EvidenceUnit(id=f"u{len(units):05d}", **values,
                                      start_char=start, end_char=end, text=text))
    return UnitPlan(partition_version=PARTITION_VERSION, batch_index=batch.index,
                    plan_sha256=_digest(batch.index, sources), units=tuple(units))
