---
schema_version: 1
id: SCOUT-M214WVW7QV05
type: decision
---
# Keep Scout's Standards Authority in the Repository

## Context

Scout's rules are currently distributed across documentation, tests, workflow
steps, and contributor guidance. A separate standards repository can support a
large multi-repository organization, but Scout has one public source repository
and no present need for cross-repository governance.

## Decision

The canonical requirements and architecture decisions live under `rac/` in
the Scout repository. RAC validates the corpus and generates agent guidance.
The Scout-owned `tools/check_standards.py` enforces deterministic repository
properties, while `standards/controls.json` maps every normative requirement to
executable CI evidence or an explicit human-review procedure.

This is a deliberate partial boundary. The standards may move to a dedicated
authority repository only after multiple consumers need independent versioning
and Scout can pin that authority by immutable revision and content digest.

## Consequences

Standards and implementation change atomically, contributors can trace every
rule locally, and CI has no network dependency for the corpus. Scout must keep
the RAC tool version pinned and must review any future extraction as an
architecture migration rather than a file move.

## Status

Accepted

## Category

Architecture

## Alternatives Considered

A private or separate standards repository was rejected for now because it
would add synchronization and availability costs before there is a second
consumer. Unstructured prose alone was rejected because it cannot provide
coverage or drift checks. A language-model-only reviewer was rejected as the
blocking mechanism because its results would not be deterministic.
