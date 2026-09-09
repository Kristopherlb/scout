---
name: lfd-execute
description: Executes an equipped Scout LFD optimization loop from an agent-visible bundle. Use when working in a target repository that contains .lfd/bundle-manifest.json and the user asks to improve the target, run the visible scorer, request a blinded holdout check, inspect its bounded result, or continue the next evidence-driven cycle.
---

# LFD Execute

Work only from the agent-visible target bundle. Hidden cases, answers, canaries,
private scorers, audit evidence, and operator detail are intentionally absent.
Do not search for, infer, or request them.

## Establish the contract

1. Read `.lfd/goal.md` and the repository's existing agent instructions.
2. Confirm `.lfd/bundle-manifest.json` and
   `.lfd/holdout-protocol.json` exist. If either is absent, stop with a
   truthful `capability_unavailable` result; do not invent replacements.
3. Use `scripts/target-repo/score-dev.sh` as the only development scoring
   entrypoint. It owns lint and scoring exactly once.

## Run one optimization cycle

1. Record the hypothesis, expected score movement, and likely failure mode in
   `LOG.md` before editing.
2. Make one coherent change. Stage and commit only the intended paths; avoid
   broad all-tracked-file commit shortcuts.
3. Run the repository's ordinary tests, then run:

   ```bash
   scripts/target-repo/score-dev.sh
   ```

4. Record the visible score and interval. If tests or scoring fail, fix that
   cycle before requesting hidden evaluation.
5. Commit the intended change, then submit the current commit through:

   ```bash
   scripts/target-repo/request-holdout-check.sh \
     <dev-score> <ci-low> <ci-high> [model-id] [tokens-in] [tokens-out] [cost-usd] [seconds]
   ```

6. Preserve the returned request tag. Check only through:

   ```bash
   scripts/target-repo/check-holdout-status.sh <request-tag>
   ```

   Exit `3` and status `pending` mean the external result is not ready. Do not
   replace the command with custom Git inspection, API calls, or aggregate CI
   scraping.
7. When the bounded result arrives, append it to `LOG.md`. Continue only when
   the movement rule and remaining budgets in `.lfd/goal.md` permit it.

## Stop and escalate

Stop rather than improvising when the bundle reports drift, a capability is
unavailable, the request transport returns an error, the loss has stalled, or
the bounded result indicates divergence or a blocking detector. Report the
stable error and next action. Loss-function redesign, private audit, and fence
patching belong to the hub-side skills and are outside this skill's authority.
