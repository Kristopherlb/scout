---
schema_version: 1
id: SCOUT-MZ6SKK123456
type: requirement
---
# Scout Agent Skill Boundaries

## Problem

A single design/audit/execute skill gives one context conflicting authority,
while copied workflow logic can drift from the runtime contract or leak private
evaluation material into the target.

## Requirements

- [REQ-001] Shared scientific references and calculators MUST remain non-invocable.
- [REQ-002] The target bundle MUST contain `lfd-execute` and no hub-side skill.
- [REQ-003] `lfd-execute` MUST use the bundled scoring, request, and status interfaces without custom transport discovery.
- [REQ-004] Runtime instruction shims MUST update idempotent managed blocks while preserving caller-owned content.
- [REQ-005] Every skill pointer MUST resolve to committed material or an implemented command.

## Success Metrics

Onboarding, design, audit, execution, and patching have distinct authority. A
target agent receives enough instruction to operate the loop and no private
design, audit, holdout, or patch material.

## Risks

Instruction formats differ between agent runtimes. Scout therefore uses a
small Markdown block with one canonical skill pointer and verifies the exact
managed content after equip instead of claiming runtime-specific semantics.

## Assumptions

Each supported runtime reads its conventional repository instruction file.
Harmony and other runtime-specific integrations remain out of scope.
