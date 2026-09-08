---
schema_version: 1
id: SCOUT-MZ2DXBND1234
type: requirement
---
# Scout Onboarding and Agent Interface

## Problem

Manual copying makes the private/public boundary advisory and gives agents no
stable, resumable interface for establishing a target.

## Requirements

- [REQ-001] Agent-visible bundles MUST be generated from an explicit public allowlist recorded with SHA-256 hashes.
- [REQ-002] Bundle equip MUST refuse to overwrite caller-owned or locally modified target files.
- [REQ-003] Onboarding status MUST be derived from validated artifacts and hashes.
- [REQ-004] Agent-facing onboarding commands MUST emit the versioned JSON envelope and documented exit statuses.
- [REQ-005] Starter scoring harnesses MUST fail closed with a typed unavailable-capability error.
- [REQ-006] Doctor credential findings MUST remain advisory when the requested operation does not use GitHub.

## Success Metrics

An operator can register, inspect, equip, and verify a temporary target without
exposing private material or changing unrelated target content. An agent can
resume from command output without parsing prose.

## Risks

A bundle allowlist can become ceremonial if generators bypass it. Tests invoke
the real generator and verifier against both safe and forbidden trees.

## Assumptions

Design and independent audit remain judgment boundaries. The onboarding runner
stops at those boundaries rather than becoming a workflow engine.
