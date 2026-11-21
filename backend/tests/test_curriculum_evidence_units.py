"""Pure source partition invariants; authored text is not model-quality evidence."""

from copy import deepcopy
from hashlib import sha256
import json
from uuid import UUID, uuid4

from pydantic import ValidationError
import pytest

from app.curriculum import evidence_units
from app.curriculum.evidence_units import MAX_UNIT_BYTES, PARTITION_VERSION, UnitPlan, plan_evidence_units
from app.curriculum.objectives import PromptSlice, SourceBatch, plan_batches
from test_curriculum_contracts import context
from test_curriculum_workflow import Session


SOURCE = UUID("10000000-0000-4000-8000-000000000001")
SEGMENT = UUID("20000000-0000-4000-8000-000000000001")


def source(text="Define a GET route.", *, start=0, **changes):
    values = {"id": "s00000", "segment_id": SEGMENT, "source_id": SOURCE,
              "processing_version": "transcript-v1:g1", "modality": "transcript",
              "origin": "uploaded_transcript", "start_char": start,
              "end_char": start + len(text), "text": text}
    values.update(changes)
    return PromptSlice(**values)


def batch(*slices, index=0):
    return SourceBatch(index, tuple(slices) or (source(),))


@pytest.mark.parametrize("text", ["x", "x" * 80, "x" * 81, "x" * 1800,
                                        "İğüşçö" * 150, "🙂" * 450,
                                        "A" * 77 + "🙂" * 430, "e\u0301" * 500,
                                        " \t\r\n" * 400, "def f():\r\n    return 'ı🙂'\n"])
def test_partition_is_lossless_greedy_and_uses_absolute_character_spans(text):
    original = source(text, start=123)
    plan = plan_evidence_units(batch(original, index=7))
    assert plan.partition_version == PARTITION_VERSION and plan.batch_index == 7
    assert "".join(unit.text for unit in plan.units) == text
    assert [unit.id for unit in plan.units] == [f"u{index:05d}" for index in range(len(plan.units))]
    position = original.start_char
    for index, unit in enumerate(plan.units):
        assert 1 <= len(unit.text.encode("utf-8")) <= MAX_UNIT_BYTES
        assert unit.start_char == position and unit.end_char == position + len(unit.text)
        assert original.text[unit.start_char - original.start_char:unit.end_char - original.start_char] == unit.text
        assert (unit.slice_id, unit.source_id, unit.segment_id, unit.processing_version,
                unit.modality, unit.origin) == (original.id, original.source_id, original.segment_id,
                                               original.processing_version, original.modality, original.origin)
        if index + 1 < len(plan.units):
            assert len((unit.text + plan.units[index + 1].text[0]).encode("utf-8")) > MAX_UNIT_BYTES
        position = unit.end_char
    assert position == original.end_char


def test_multibyte_boundary_does_not_use_the_incorrect_23_units_per_slice_cap():
    text = "a" * 77 + "🙂" + ("a" * 73 + "🙂") * 22
    assert len(text.encode()) == 1775
    plan = plan_evidence_units(batch(source(text)))
    assert len(plan.units) == 24
    assert "".join(item.text for item in plan.units) == text


def test_whitespace_units_are_retained_without_claiming_meaningful_quotes():
    plan = plan_evidence_units(batch(source(" " * 80 + "\t\n  code  \n")))
    assert plan.units[0].text == " " * 80 and not plan.units[0].text.strip()
    assert "".join(unit.text for unit in plan.units) == " " * 80 + "\t\n  code  \n"


def test_units_never_join_parent_slices_or_reset_batch_local_ids():
    first = source("a" * 81, start=9)
    second = source("b" * 81, start=90, id="s00001")
    plan = plan_evidence_units(batch(first, second, index=19))
    assert [(unit.id, unit.slice_id, unit.start_char, unit.end_char) for unit in plan.units] == [
        ("u00000", "s00000", 9, 89), ("u00001", "s00000", 89, 90),
        ("u00002", "s00001", 90, 170), ("u00003", "s00001", 170, 171),
    ]
    assert plan_evidence_units(batch(second)).units[0].id == "u00000"


def test_plan_and_units_are_frozen_detached_and_strictly_round_trip():
    original = source("a" * 81)
    plan = plan_evidence_units(batch(original))
    assert isinstance(plan.units, tuple)
    assert UnitPlan.model_validate_json(plan.model_dump_json(), strict=True) == plan
    original.text = "Changed input"
    assert "".join(item.text for item in plan.units) == "a" * 81
    with pytest.raises(ValidationError):
        plan.batch_index = 2
    with pytest.raises(ValidationError):
        plan.units[0].text = "changed"
    with pytest.raises(TypeError):
        plan.units[0] = plan.units[1]


def test_fingerprint_has_a_fixed_canonical_full_input_recipe():
    original = source("İ🙂\r\n  x", start=31)
    plan = plan_evidence_units(batch(original, index=3))
    values = original.model_dump(mode="json")
    values["slice_id"] = values.pop("id")
    expected = {"partition_version": PARTITION_VERSION, "max_unit_bytes": MAX_UNIT_BYTES,
                "batch_index": 3, "slices": [values]}
    encoded = json.dumps(expected, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert plan.plan_sha256 == sha256(encoded).hexdigest()
    assert plan == plan_evidence_units(deepcopy(batch(original, index=3)))


@pytest.mark.parametrize("changes", [
    {"id": "s00001"}, {"source_id": UUID(int=3)}, {"segment_id": UUID(int=4)},
    {"processing_version": "transcript-v2:g2"}, {"origin": "unreviewed_asr"},
    {"modality": "frame", "origin": "unreviewed_ocr"},
    {"text": "Define a PUT route."}, {"start": 1},
])
def test_every_source_identity_or_exact_span_change_changes_the_fingerprint(changes):
    original = plan_evidence_units(batch(source()))
    values = {"text": "Define a GET route.", **changes}
    changed = plan_evidence_units(batch(source(**values)))
    assert changed.plan_sha256 != original.plan_sha256


def test_batch_order_index_partition_version_and_normalization_are_pinned(monkeypatch):
    first, second = source("é", segment_id=uuid4()), source("e\u0301", id="s00001", segment_id=uuid4())
    original = plan_evidence_units(batch(first, second))
    assert plan_evidence_units(batch(second, first)).plan_sha256 != original.plan_sha256
    assert plan_evidence_units(batch(first, second, index=1)).plan_sha256 != original.plan_sha256
    assert plan_evidence_units(batch(source("é"))).plan_sha256 != plan_evidence_units(batch(source("e\u0301"))).plan_sha256
    monkeypatch.setattr(evidence_units, "PARTITION_VERSION", "evidence-units-byte-test-v2")
    assert plan_evidence_units(batch(first, second)).plan_sha256 != original.plan_sha256


@pytest.mark.parametrize("index", [True, False, "0", 0.0, -1, 20])
def test_rejects_invalid_raw_batch_indices(index):
    with pytest.raises(ValueError):
        plan_evidence_units(batch(source(), index=index))


@pytest.mark.parametrize("value", [None, {}, (), [], "batch"])
def test_rejects_non_batch_inputs(value):
    with pytest.raises(ValueError):
        plan_evidence_units(value)


@pytest.mark.parametrize("slices", [(), [], [source()], (source(),) * 5, ({"id": "s00000"},)])
def test_rejects_invalid_raw_slice_collections(slices):
    with pytest.raises(ValueError):
        plan_evidence_units(SourceBatch(0, slices))


@pytest.mark.parametrize("field,value", [
    ("id", "s100000"), ("id", 0), ("source_id", str(SOURCE)), ("segment_id", str(SEGMENT)),
    ("processing_version", ""), ("processing_version", " " * 4),
    ("processing_version", "v" * 201), ("processing_version", "v\x00"),
    ("processing_version", "v\ud800"), ("text", ""), ("text", 123),
    ("text", "\x00"), ("text", "\udfff"), ("text", "a" * 1801),
    ("text", "🙂" * 451), ("start_char", True), ("start_char", -1),
    ("end_char", True), ("end_char", "19"), ("end_char", 0),
    ("modality", "audio"), ("origin", "reviewed"),
    ("modality", "frame"), ("origin", "unreviewed_ocr"),
])
@pytest.mark.parametrize("constructed", [False, True])
def test_rejects_mutated_and_constructed_slice_values_before_serialization(field, value, constructed):
    values = source().model_dump()
    values[field] = value
    if field == "text" and type(value) is str:
        values["end_char"] = values["start_char"] + len(value)
    if constructed:
        original = PromptSlice.model_construct(**values)
    else:
        original = source()
        setattr(original, field, value)
        if field == "text" and type(value) is str:
            original.end_char = len(value)
    with pytest.raises(ValueError):
        plan_evidence_units(batch(original))


@pytest.mark.parametrize("changes", [{"start_char": 1}, {"end_char": 1}, {"end_char": 99}])
def test_rejects_incoherent_character_span_lengths(changes):
    with pytest.raises(ValueError):
        plan_evidence_units(batch(source(**changes)))


@pytest.mark.parametrize("changes", [
    {"source_id": UUID(int=3)}, {"processing_version": "different-v1"},
    {"origin": "unreviewed_asr"}, {"modality": "frame", "origin": "unreviewed_ocr"},
    {"start": 2}, {"start": 0},
])
def test_repeated_segments_require_unchanged_pins_and_nondecreasing_disjoint_spans(changes):
    first = source("first", start=0)
    second = source("second", start=5, id="s00001", **changes) if "start" not in changes else source(
        "second", id="s00001", **changes)
    with pytest.raises(ValueError):
        plan_evidence_units(batch(first, second))


def test_duplicate_slice_ids_fail_even_when_their_segments_differ():
    with pytest.raises(ValueError):
        plan_evidence_units(batch(source(), source(segment_id=uuid4())))


@pytest.mark.parametrize("tamper", ["hash", "text", "span", "order", "id", "source", "partition", "nongreedy"])
def test_forged_or_repartitioned_saved_plans_fail_closed(tamper):
    plan = plan_evidence_units(batch(source("a" * 81)))
    value = plan.model_dump()
    units = list(value["units"])
    if tamper == "hash":
        value["plan_sha256"] = "0" * 64
    elif tamper == "partition":
        value["partition_version"] = "evidence-units-other-v1"
    elif tamper == "order":
        units.reverse()
    elif tamper == "nongreedy":
        units[0].update(text="a" * 79, end_char=79)
        units[1].update(text="aa", start_char=79)
    else:
        key, changed = {"text": ("text", "b" * 80), "span": ("start_char", 1),
                        "id": ("id", "u00009"), "source": ("source_id", uuid4())}[tamper]
        units[0][key] = changed
    value["units"] = tuple(units)
    with pytest.raises(ValueError):
        UnitPlan.model_validate(value, strict=True)


def test_existing_context_batch_planner_stays_unchanged_and_is_accepted(context):
    session = Session(context)
    batches = plan_batches(session.context)
    before = deepcopy(batches)
    plans = [plan_evidence_units(item) for item in batches]
    assert batches == before and plan_batches(session.context) == before
    assert len(plans) == len(batches)
    for original, plan in zip(batches, plans):
        for part in original.slices:
            assert "".join(unit.text for unit in plan.units if unit.slice_id == part.id) == part.text
