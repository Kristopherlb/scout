# Agent-visible execution contract

The maintained target-side instructions live in `skills/lfd-execute/SKILL.md`
and are bundled at `.agents/skills/lfd-execute/SKILL.md`. Runtime shims point
Codex, Claude, Cursor, and Copilot to that single copy.

The executor uses exactly three interfaces:

- `scripts/target-repo/score-dev.sh` for visible lint and scoring;
- `scripts/target-repo/request-holdout-check.sh` for immutable requests;
- `scripts/target-repo/check-holdout-status.sh` for the bounded result.

It does not run private probes, inspect Git tags directly, query aggregate CI
state, edit `.lfd` evidence, or redesign the loss function. A pending external
result exits `3`; invalid input exits `2`; infrastructure failure exits `4`.
