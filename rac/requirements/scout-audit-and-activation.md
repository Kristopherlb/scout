---
schema_version: 1
id: SCOUT-MZ4ADT123456
type: requirement
---
# Scout Audit and Activation Integrity

## Problem

A mechanical checklist can look authoritative while leaving the semantic
security review undone, and a hand-edited lifecycle value can bypass an honest
activation decision.

## Requirements

- [REQ-001] A passing mechanical audit MUST remain incomplete until independent judgment is finalized.
- [REQ-002] Final audit judgment MUST contain explicit verdicts and evidence for leakage, Goodhart fences, calibration, escalation, and blinding.
- [REQ-003] A final audit MUST bind the goal, eval manifest, agent bundle, private harness, calibration, and judgment with SHA-256 hashes.
- [REQ-004] `lfd activate` MUST be the only supported transition of a target into the active lifecycle state.
- [REQ-005] Active runtime checks MUST revalidate current gate evidence and the activation receipt before target code executes.

## Success Metrics

Incomplete, failed, malformed, and stale evidence cannot activate or run a
target. An operator can distinguish deterministic checks from independent
judgment in both the CLI result and committed artifacts.

## Risks

Hashes prove freshness, not review quality. Required evidence fields make weak
or missing judgment visible, while human review remains responsible for the
substance of each finding.

## Assumptions

The independent-context attestation records required process evidence. It does
not cryptographically prove that a fresh context was used.
