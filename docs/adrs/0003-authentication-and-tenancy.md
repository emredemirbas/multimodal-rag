# ADR 0003: Authentication and tenant/project scope

- Status: Accepted
- Date: 2026-09-21

## Context

The beta begins with private single-user projects, but cross-project leakage is a
critical failure and later SaaS tenancy must not require a data-model rewrite.

## Decision

Every project-owned table and repository method carries both `tenant_id` and
`project_id`. Authentication will be supplied by a replaceable identity adapter.
The Sprint 0 `X-Tenant-ID` header is development-only and is not an authentication
mechanism. PostgreSQL RLS will be added as defense in depth before beta.

## Consequences

Queries are more verbose and require negative isolation tests. A trusted gateway
must replace the development header before deployment.
