# ADR 0010: Immutable assignments and deterministic grading

- Status: Accepted
- Date: 2026-09-21

## Context

Learners need reproducible expectations and objective results. Editing an
assignment after submission would invalidate evaluation history, while allowing
an LLM to change test outcomes would make grading nondeterministic.

## Decision

Assignments begin as editable drafts and require explicit activation. The active
version becomes immutable after its first submission. Deterministic tests decide
objective pass/fail; model output may explain results and apply versioned
qualitative rubrics but never overwrite test outcomes.

## Consequences

Corrections create a new assignment version. Evaluation records must retain test
bundle, runner, image digest, rubric, prompt, and model versions.
