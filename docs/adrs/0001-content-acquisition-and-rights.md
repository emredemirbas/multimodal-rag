# ADR 0001: Content acquisition and rights

- Status: Accepted
- Date: 2026-09-21

## Context

A public video URL does not itself grant permission to download, transform, or
retain audiovisual content. An unofficial downloader would make a critical
product path depend on an unsupported and potentially non-compliant behavior.

## Decision

The MVP accepts uploaded SRT/VTT transcripts and later user-owned, authorized,
or appropriately licensed media. Public YouTube URLs may provide allowlisted
metadata only until an authorized transcript or media path is supplied. Each
source records its authorization mode and retention class.

## Consequences

The first ingestion flow is narrower but testable and compliant. The UI must
explain why a URL alone may be insufficient. No worker receives an arbitrary
user-supplied URL to fetch.
