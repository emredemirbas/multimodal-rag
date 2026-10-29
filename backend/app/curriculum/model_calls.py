"""Fenced before-inference receipts and actual local-call usage; no run producer."""

from uuid import uuid4

from .execution import StageFailure
from .local_provider import (
    REQUEST_VERSION, CurriculumJsonProvider, CurriculumProviderError, JsonCallSpec, JsonModelResponse,
)
from .run_contracts import ModelCallFinish, ModelCallStart, RunClaim
from .run_progress import RunProgressRepository


class LeasedCurriculumCalls:
    def __init__(self, repository: RunProgressRepository, provider: CurriculumJsonProvider):
        self.repository, self.provider = repository, provider

    def invoke(self, claim: RunClaim, spec: JsonCallSpec) -> JsonModelResponse | None:
        # A fresh ID identifies one physical inference attempt. Accepted stage
        # reuse belongs to the workflow checkpoint, never re-invocation by call ID.
        try:
            prepared = self.provider.prepare(spec)
        except CurriculumProviderError as error:
            raise StageFailure(error.code, retryable=error.retryable) from None
        call_id = uuid4()
        started = False

        def before_inference():
            nonlocal started
            view = self.repository.begin_call(claim, ModelCallStart(
                call_id=call_id, purpose=prepared.spec.purpose, provider=prepared.identity.provider,
                model=prepared.identity.model, model_digest=prepared.identity.model_digest,
                engine=prepared.identity.engine, prompt_version=prepared.spec.prompt_version,
                input_characters=prepared.input_characters, input_tokens=None,
                input_sha256=prepared.input_sha256, schema_version=prepared.spec.schema_version,
                request_version=REQUEST_VERSION,
            ))
            started = view is not None and view.status == "started"
            return started

        try:
            response = self.provider.complete(prepared, before_inference=before_inference)
        except CurriculumProviderError as error:
            if started:
                accepted = self.repository.finish_call(claim, ModelCallFinish(
                    call_id=call_id, status="failed", input_tokens=error.input_tokens,
                    output_tokens=error.output_tokens, output_characters=None,
                    duration_ms=error.duration_ms, failure_code=error.code,
                ))
                if not accepted:
                    return None
            raise StageFailure(error.code, retryable=error.retryable) from None
        if response is None:
            return None
        # Do not return late output when cancellation, expiry or deletion won.
        accepted = self.repository.finish_call(claim, ModelCallFinish(
            call_id=call_id, status="succeeded", input_tokens=response.input_tokens,
            output_tokens=response.output_tokens, output_characters=len(response.content),
            duration_ms=response.duration_ms, failure_code=None,
        ))
        return response if accepted else None
