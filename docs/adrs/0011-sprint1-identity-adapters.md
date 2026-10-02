# ADR 0011: Provider-neutral Sprint 1 identity adapters

- Status: Accepted
- Date: 2026-09-21

## Context

Sprint 1 requires an authentication boundary, but the MVP has not selected an
external identity vendor. The Sprint 0 `X-Tenant-ID` header is user-controlled
and therefore cannot establish either identity or tenant membership.

Choosing a hosted identity vendor now would create an avoidable product and
deployment commitment. Leaving the tenant header in place would make the first
web application insecure by construction.

## Decision

The API owns an `Authenticator` interface that returns a verified principal.
Tenant scope is derived only from that principal and is never accepted from a
project payload, URL, or ordinary client-selected header.

Sprint 1 ships two adapters:

1. A local-development adapter authenticates a single configured principal with
   a bearer token. It is permitted only in `development` and `test` environments
   and the application refuses to start with it in any other environment.
2. A trusted-proxy adapter accepts the authenticated subject and tenant asserted
   by an upstream identity gateway only when the request also carries a
   constant-time-verified shared proxy secret. Production networking must keep
   the API private behind that gateway, and the gateway must strip client-sent
   identity headers before adding its own.

Authenticated external subjects are mapped to application-owned users and
tenant memberships. Repository methods continue to enforce `tenant_id` and
`project_id` even after authentication succeeds.

The concrete upstream OIDC or identity vendor remains replaceable and will be
selected before a public deployment. It does not change the API's principal or
authorization contracts.

## Consequences

- The Next.js server can call the API without exposing credentials or tenant
  selectors in the browser bundle.
- Local Compose remains easy to run but requires a developer-generated token.
- A leaked development or proxy secret must be rotated; neither belongs in the
  repository, frontend bundle, URL, or logs.
- The trusted-proxy mode is unsafe if the API is directly reachable or if the
  gateway forwards untrusted identity headers.
- Provider-specific login, logout, account recovery, and consent UX remain a
  deployment integration rather than domain logic.
