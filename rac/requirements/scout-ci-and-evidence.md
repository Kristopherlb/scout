---
schema_version: 1
id: SCOUT-M214WVE5P808
type: requirement
---
# Scout CI and Evidence

## Problem

Prose standards do not protect the project unless contributors can see how
each normative statement is enforced and CI detects when requirements,
generated guidance, or executable checks drift apart.

## Requirements

- [REQ-001] Every normative Scout requirement MUST have exactly one control mapping.
- [REQ-002] Each control MUST declare a stable identifier, enforcement mode, severity, and evidence command or review procedure.
- [REQ-003] CI MUST run the pinned RAC gate and Scout's deterministic standards checker.
- [REQ-004] CI MUST reject generated agent guidance that is stale relative to accepted decisions.
- [REQ-005] Every new blocking source guardrail SHOULD include a negative regression test that proves the forbidden state is rejected.

## Success Metrics

The RAC corpus gates successfully, every requirement has a valid control, CI
runs both structural and repository-specific enforcement, and regeneration
drift is caught before merge.

## Risks

A control registry can become ceremonial if evidence is vague or does not run.
The registry therefore distinguishes executable CI evidence from named human
review procedures and treats unsupported automation claims as defects.

## Assumptions

RAC validates artifact structure and decision relationships. Scout-owned code
performs deterministic source and workflow checks; RAC is not treated as a
semantic source-code analyzer.
