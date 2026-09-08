---
schema_version: 1
id: SCOUT-M214WTHX5RED
type: requirement
---
# Scout Architecture Boundaries

## Problem

Scout's Python commands, policy code, operations adapters, and composition root
currently share a repository without a machine-readable dependency contract.
That makes it possible for infrastructure concerns to leak inward or for
cycles to accumulate without an intentional architecture decision.

## Requirements

- [REQ-001] `tools/lfd_common.py` MUST NOT import any Scout command module or operations adapter.
- [REQ-002] Python runtime modules under `tools/` and `ops/` MUST form a directed acyclic graph.
- [REQ-003] Python command modules under `tools/` MUST NOT import Python operations adapters under `ops/`.
- [REQ-004] `bin/lfd` SHOULD remain a thin composition root that delegates behavior to command modules.
- [REQ-005] `tools/lfd_contract.py` MUST NOT import Scout command modules or operations adapters.

## Success Metrics

Every pull request receives a deterministic dependency-boundary result, and
new boundary violations fail before merge. Human review confirms that changes
to the composition root do not move application behavior into shell routing.

## Risks

The first boundary is deliberately partial: legacy modules remain grouped by
location rather than being immediately reorganized. Static import analysis can
also miss dynamic imports and subprocess coupling, which remain review
concerns.

## Assumptions

Scout remains a small Python and shell project in this phase. A deeper package
reorganization will be proposed separately if the current boundary becomes too
coarse.
