---
schema_version: 1
id: SCOUT-M214WV02XCHE
type: requirement
---
# Scout Runtime Integrity

## Problem

Scout evaluates untrusted code and records security-sensitive scoring results.
An implicit operational choice, permissive fallback, alternate log writer, or
leak of real evaluation material could turn a passing command into false
evidence.

## Requirements

- [REQ-001] Active scoring MUST fail closed when required operational configuration is missing or invalid.
- [REQ-002] Operational choices MUST come from their owning validated configuration or contract instead of runtime literals or hidden defaults.
- [REQ-003] The `append_log_row` entry point MUST be referenced only by `ops/log_utils.py` in runtime modules.
- [REQ-004] Public source MUST exclude every real evaluation campaign and every target fixture other than the exact synthetic `targets/_example`.
- [REQ-005] Sandbox infrastructure failure MUST abort scoring without writing a score.
- [REQ-006] Scoring-log writer changes MUST receive human review confirming that every row still routes through `ops/log_utils.py`.
- [REQ-007] Target operational configuration MUST be a strictly validated, non-executable `target.json` contract loaded through `tools/lfd_contract.py`.
- [REQ-008] Runtime commands MUST reject legacy `config.env` target configuration.

## Success Metrics

CI rejects configuration bypasses covered by executable checks, unauthorized
uses of the authorized log entry point, real target material, and score-producing
sandbox failures. Every runtime-path change also receives an explicit review
for alternate log writers, operational literals, fallbacks, fake success, and
documentation drift.

## Risks

Some runtime-integrity properties require semantic review because a general
static rule would produce misleading coverage. Human-reviewed controls are
identified as such rather than represented as automated guarantees.

## Assumptions

The public repository contains framework source and synthetic examples only.
Real target configuration, credentials, holdouts, canaries, and score history
remain in a separate private operational repository.
