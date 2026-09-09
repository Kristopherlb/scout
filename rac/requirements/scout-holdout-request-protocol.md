---
schema_version: 1
id: SCOUT-MZ5PRT123456
type: requirement
---
# Scout Holdout Request Protocol

## Problem

Counter tags collide, mutable or weakly identified requests can score the wrong
commit, and a fallback commit can silently alter the caller's work.

## Requirements

- [REQ-001] Every target contract MUST declare a supported holdout protocol version.
- [REQ-002] A version-1 request tag MUST bind its random request ID to the full requested commit SHA.
- [REQ-003] Fallback transport MUST use an isolated worktree whose request commit has the requested SHA as its sole parent.
- [REQ-004] Hub polling MUST validate request identity and deduplicate by request ID plus SHA before scoring.
- [REQ-005] Target status MUST inspect only the exact `lfd/holdout` commit-status context.

## Success Metrics

Direct and fallback requests produce the same validated tag and payload. Dirty,
staged, and untracked caller state remains byte-for-byte unchanged. Unrelated CI
statuses cannot affect the reported holdout result.

## Risks

Remote branch cleanup can fail after a tag is created. The materializer reports
that infrastructure failure rather than claiming completion, leaving the exact
request branch visible for operator repair.

## Assumptions

Git object IDs are full lowercase SHA-1 or SHA-256 values. Version 1 names only
the first twelve characters for readability while the payload and validation
retain the full object ID.
