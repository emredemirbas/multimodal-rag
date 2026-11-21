"""Exact local Qwen2.5 tag support; authored HTTP responses are not native quality."""

import json

import pytest

from app.curriculum.local_provider import (
    CurriculumProviderError, LocalCurriculumProvider, LocalModelIdentity,
)
from test_curriculum_local_provider import identity, local_curriculum_server, spec


MODEL = "qwen2.5:7b-instruct-q4_K_M"


@pytest.fixture
def qwen25_provider(local_curriculum_server):
    original, state = local_curriculum_server
    provider = LocalCurriculumProvider(original.base_url, identity(model=MODEL))
    state["tags"]["models"][0]["name"] = MODEL
    state["show"]["details"]["family"] = "qwen2"
    state["override"] = {"model": MODEL}
    return provider, state


def test_qwen25_changes_only_exact_model_in_existing_bounded_request(qwen25_provider):
    provider, state = qwen25_provider
    baseline = LocalCurriculumProvider(provider.base_url, identity()).prepare(spec())
    selected = provider.prepare(spec())
    selected_payload, baseline_payload = json.loads(selected.payload), json.loads(baseline.payload)
    assert selected_payload.pop("model") == MODEL
    assert baseline_payload.pop("model") == "qwen3:4b"
    assert selected_payload == baseline_payload
    assert selected.input_sha256 != baseline.input_sha256
    assert not state["calls"]


@pytest.mark.parametrize("other", ["qwen3:4b", "qwen3.5:4b", "qwen2.5:7b"])
def test_qwen25_rejects_a_response_with_another_model_identity(qwen25_provider, other):
    provider, state = qwen25_provider
    state["override"]["model"] = other
    with pytest.raises(CurriculumProviderError) as caught:
        provider.complete(provider.prepare(spec()), before_inference=lambda: True)
    assert caught.value.code == "invalid_output" and not caught.value.retryable
    assert (caught.value.input_tokens, caught.value.output_tokens) == (123, 35)
    assert state["calls"].count("/api/chat") == 1 and "/api/pull" not in state["calls"]


@pytest.mark.parametrize("field,value", [("thinking", "PRIVATE reasoning"),
                                        ("tool_calls", [{"function": "fetch"}])])
def test_qwen25_preserves_rejection_of_thinking_and_tool_output(qwen25_provider, field, value):
    provider, state = qwen25_provider
    state["override"]["message"] = {"role": "assistant", "content": "{}", field: value}
    with pytest.raises(CurriculumProviderError) as caught:
        provider.complete(provider.prepare(spec()), before_inference=lambda: True)
    assert caught.value.code == "invalid_output" and "PRIVATE" not in str(caught.value)
    assert state["calls"].count("/api/chat") == 1 and "/api/pull" not in state["calls"]


@pytest.mark.parametrize("model", ["qwen2.5:7b", "qwen2.5:latest", "qwen2.5:7b-instruct", "qwen2.5:14b-instruct-q4_K_M",
                                  "qwen2.5:7b-instruct-q5_K_M", b"qwen2.5:7b-instruct-q4_K_M"])
def test_no_unpinned_qwen25_alias_or_quantization_is_added(model):
    raw = LocalModelIdentity.model_construct(model=model, model_digest="a" * 64, engine="0.40.3")
    with pytest.raises(ValueError, match="explicit local model digest and engine pin"):
        LocalCurriculumProvider("http://127.0.0.1:11434", raw)


def test_qwen25_omitted_usage_remains_unknown(qwen25_provider):
    provider, state = qwen25_provider
    state["override"].update(prompt_eval_count=None, eval_count=None)
    result = provider.complete(provider.prepare(spec()), before_inference=lambda: True)
    assert (result.input_tokens, result.output_tokens) == (None, None)
    assert result.identity.model == MODEL
