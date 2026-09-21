# ADR 0008: Dedicated hardened grading runner

- Status: Accepted
- Date: 2026-09-21

## Context

Learner submissions are hostile input. The API, ordinary workers, and Docker
daemon must not become part of the grading trust boundary.

## Decision

Route submissions through a dedicated coordinator and ephemeral gVisor, microVM,
or equivalent sandbox. Disable networking by default; run non-root with a
read-only base image and strict CPU, memory, disk, PID, output, and time limits.
Never mount the Docker socket, secrets, or production data.

## Consequences

Sandbox work is deferred to its dedicated sprint and security review. Ordinary
Docker containers alone are not considered sufficient isolation.
