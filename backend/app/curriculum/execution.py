"""One trusted, bounded workflow stage per delivery; no processor is enabled yet."""

from dataclasses import dataclass
from typing import Callable, Mapping
from uuid import UUID

from ..sources.contracts import SourceError
from .contracts import AssignmentContent
from .delivery import RunDeliveryRepository
from .persistence import ContextView
from .run_contracts import CheckpointSave, CheckpointView, FailureCode, RunClaim, RunView


@dataclass(frozen=True)
class StageInput:
    run: RunView
    context: ContextView
    checkpoints: tuple[CheckpointView, ...]
    # Trusted adapters need the lease identity to record each physical call
    # before inference; this private value never enters a public response.
    claim: RunClaim


@dataclass(frozen=True)
class StageResult:
    checkpoint: CheckpointSave | None = None
    content: AssignmentContent | None = None

    def __post_init__(self):
        if (self.checkpoint is None) == (self.content is None):
            raise ValueError("A stage must yield progress or final content.")


class StageFailure(Exception):
    """Application-owned provider adapters report only a fixed failure code."""

    def __init__(self, code: FailureCode, *, retryable: bool):
        self.code = code
        self.retryable = retryable
        super().__init__("The curriculum stage could not be completed.")


StageExecutor = Callable[[StageInput], StageResult]


def advance_run(repository: RunDeliveryRepository, tenant: str, project: UUID, run_id: UUID,
                processors: Mapping[str, StageExecutor]) -> None:
    claim = repository.claim(tenant, project, run_id)
    if claim is None:
        return
    loaded = repository.load_input(claim)
    if loaded is None:
        return
    run, context, checkpoints = loaded
    processor = processors.get(run.workflow_version)
    if processor is None:
        repository.fail(claim, "processing_unavailable", retryable=False)
        return
    try:
        # No database transaction or lock spans the processor invocation. Celery
        # bounds a delivery to 90/120 seconds, below the 180-second lease.
        result = processor(StageInput(run, context, tuple(checkpoints), claim.model_copy(deep=True)))
        if not isinstance(result, StageResult):
            raise ValueError("Invalid stage result")
        # Recheck even a mutated/constructed result before choosing a branch.
        if (result.checkpoint is None) == (result.content is None):
            raise ValueError("Invalid stage result")
    except StageFailure as error:
        repository.fail(claim, error.code, retryable=error.retryable)
        return
    except Exception:
        repository.fail(claim, "processing_unavailable", retryable=True)
        return
    try:
        # These transactions recheck authority, dependency existence and the
        # fresh lease, then accept all state/result changes atomically.
        if result.checkpoint is not None:
            repository.continue_with_checkpoint(claim, result.checkpoint)
        else:
            repository.publish_draft(claim, result.content)
    except SourceError:
        repository.fail(claim, "invalid_output", retryable=True)
