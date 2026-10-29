"""Internal durable-run values; no public generation producer is enabled."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import ConfigDict, Field, JsonValue, StringConstraints, model_validator

from ..models import TenantId
from .contracts import Contract, Digest


LEASE_SECONDS = 180
MAX_FAILURES = 3
RETRY_DELAY_SECONDS = 5
MAX_CHECKPOINTS = 64
MAX_CHECKPOINT_BYTES = 300_000
MAX_CHECKPOINT_STORAGE_BYTES = 327_680
MAX_CALLS_PER_RUN = 256
Identifier = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:/+@-]{0,127}$")]
RequestKey = Annotated[str, StringConstraints(min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")]
FailureCode = Literal[
    "provider_unavailable", "provider_timeout", "invalid_output", "worker_lost",
    "authorization_revoked", "project_archived", "cancelled", "processing_unavailable",
]
RunStatus = Literal["pending", "running", "retrying", "failed", "cancelled", "succeeded"]
Count = Annotated[int, Field(ge=0, le=2_147_483_647)]


class RunCreate(Contract):
    idempotency_key: RequestKey
    workflow_version: Identifier


class RunCommand(Contract):
    idempotency_key: RequestKey


class RunClaim(Contract):
    tenant_id: TenantId
    project_id: UUID
    run_id: UUID
    lease_token: UUID
    attempt_number: int = Field(ge=1, le=2_147_483_647)


class RunView(Contract):
    id: UUID
    tenant_id: TenantId
    project_id: UUID
    context_id: UUID
    actor_user_id: UUID
    workflow_version: Identifier
    status: RunStatus
    attempt_count: Count
    failure_count: Count
    checkpoint_seq: int = Field(ge=0, le=MAX_CHECKPOINTS)
    available_at: datetime
    lease_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    failure_code: FailureCode | None
    result_draft_id: UUID | None = None
    result_revision: int | None = Field(default=None, ge=1)


class CheckpointSave(Contract):
    model_config = ConfigDict(allow_inf_nan=False)

    sequence: int = Field(ge=1, le=MAX_CHECKPOINTS)
    stage: Identifier
    payload: dict[str, JsonValue]


class CheckpointView(CheckpointSave):
    tenant_id: TenantId
    project_id: UUID
    run_id: UUID
    attempt_number: int = Field(ge=1)
    workflow_version: Identifier
    content_sha256: Digest
    created_at: datetime


class ModelCallStart(Contract):
    call_id: UUID
    purpose: Identifier
    provider: Literal["ollama-local"]
    model: Identifier
    model_digest: Digest
    engine: Identifier
    prompt_version: Identifier
    input_characters: Count
    input_tokens: Count | None


class ModelCallFinish(Contract):
    call_id: UUID
    status: Literal["succeeded", "failed"]
    input_tokens: Count | None
    output_tokens: Count | None
    output_characters: Count | None
    duration_ms: Count
    failure_code: FailureCode | None

    @model_validator(mode="after")
    def consistent_outcome(self) -> Self:
        if (self.status == "failed") != (self.failure_code is not None):
            raise ValueError("Invalid call outcome")
        return self


class ModelCallView(ModelCallStart):
    tenant_id: TenantId
    project_id: UUID
    run_id: UUID
    attempt_number: int = Field(ge=1)
    status: Literal["started", "succeeded", "failed", "interrupted"]
    output_tokens: Count | None
    output_characters: Count | None
    duration_ms: Count | None
    billed_usd: Literal[0] = 0
    failure_code: FailureCode | None
    created_at: datetime
    finished_at: datetime | None
