# Agent Instructions — LFD Cycle Execution

You are executing `goal.md`. Everything mechanical below is a script call
with a fixed contract — run it, read its output, don't improvise the
mechanism. Everything marked **[judgment]** is where you actually think.
Do not swap these roles: don't hand-roll a scoring calculation the script
already does, and don't skip the judgment steps by treating a script's
output as self-explanatory.

## Every cycle

1. **[script]** `scripts/target-repo/score-dev.sh`
   Returns `{"score": ..., "ci_low": ..., "ci_high": ..., "void": bool}`.
   If `"void": true` — stop. Find and remove the constraint violation
   yourself; the script will not tell you which one (see goal.md VOID
   semantics). Do not proceed to step 2 on a VOID result.

2. **[judgment]** Compare this cycle's `[ci_low, ci_high]` to the previous
   cycle's. Movement = the intervals do not overlap. A score that moved
   but whose interval still overlaps the prior one is noise, not
   movement — do not log it as a confirmed result either direction.

3. **[script]** `harness/probe.sh` (if it exists — Fable generates this in
   design mode). Returns per-operator mutation scores. Note which
   operators are near/below their floor — a falling operator score means
   memorizing along that specific axis.

4. **[judgment]** Write the LOG.md entry BEFORE changing code, using
   `references/log-template.md`'s cycle format:
   - Hypothesis: what you're about to change and why
   - **Predicted effect: a committed number**, e.g. "0.61 → 0.68 ± 0.03" —
     not "should improve." If you can't commit to a range, you don't
     understand the change well enough to make it yet.
   - Expected failure mode and diagnostic
   - **One variable.** If your planned change touches more than one
     concern (e.g. a logic fix AND a data/seed change), split it into two
     cycles. A confounded cycle poisons every hypothesis built on it
     later — this is not a style preference.

5. **[script]** Make the change, commit: `git commit -am "cycle <n>: <ci_low>-<ci_high>"`.
   Every cycle, gain or no gain — this is what makes the run bisectable.

6. **[judgment]** Log the result: did it land inside the predicted range?
   Outside the range is a refutation even if the score went up — figure
   out what actually happened before the next cycle inherits a wrong
   causal story.

## Requesting a holdout check (rare — every K cycles, not every cycle)

Only request this when [judgment]: you've had sustained, CI-clearing dev
movement over several cycles and want to confirm it's generalizing, OR
the entropy rules require a checkpoint, OR you're about to declare
acceptance. Do not request one just because you can — the rate limit
(`MIN_CYCLES_BETWEEN_HOLDOUT` in eval-repo's config) will silently skip
over-frequent requests anyway, so there's no benefit to asking often.

1. **[script]** `scripts/target-repo/request-holdout-check.sh <dev_score> <dev_ci_low> <dev_ci_high>`
   Pass your current cycle's dev numbers. This pushes a tag and returns
   immediately — do NOT block waiting for a response. Continue the dev
   loop while it's pending.

2. **[script]** Later — next cycle or two — check:
   `scripts/target-repo/check-holdout-status.sh <tag-name>`
   Returns `{"status": "pending"}` or `{"status": "success"/"failure",
   "description": "holdout: <score> [<ci_low>,<ci_high>]"}`.

3. **[judgment — this is the one that matters most]** If the description
   contains `DIVERGENCE flagged`: **stop the dev-only loop.** This means
   dev score has been rising while holdout is flat or falling — the
   canonical reward-over-optimization signature. Do not try to patch this
   yourself by tuning further. This is a design problem, not an execution
   problem — hand off to patch mode (a human invokes `/lfd-design` in
   patch mode on the strongest available model; you should not attempt to
   self-patch your own loss function). Log the divergence event in
   LOG.md's Final Report section and halt.

4. **[judgment]** If holdout score is healthy and close to the acceptance
   bar with no divergence: this is a legitimate signal you're close.
   Continue the normal cycle protocol; don't declare victory on a single
   holdout check — the stop condition requires the bar held on holdout,
   not glimpsed once.

## Stop conditions — all [script]-checkable, [judgment] to act on

Check `log.jsonl`-derived state (surfaced via the holdout status, plus
your own dev history) against goal.md's stop conditions each cycle:
- Bar hit on holdout (interval lower bound ≥ bar) → write the Final
  Report, stop.
- Budget exhausted (`status.sh` reports elapsed/spend) → stop regardless
  of score.
- No CI-clearing movement for N consecutive cycles → this is a stall.
  **[judgment]**: your next change must be structurally different from
  the last several — not the same knob turned harder. If you can't think
  of a structurally different approach, that itself is worth logging; a
  human patch-mode pass may need to widen the eval or the surface.

## What you should never do

- Never read `eval/holdout/` or anything in eval-repo. You don't have
  access, and if you somehow do, that's a bug to report, not an
  opportunity.
- Never edit `harness/`, `eval/`, or `goal.md`. They're read-only for a
  reason stated in goal.md's Constraints — respect it even if you believe
  you know a better scoring approach. Propose it in LOG.md instead; a
  human or patch-mode pass evaluates harness changes, not you mid-run.
- Never bundle a fix to the harness/lint into the same cycle as a
  solution change, even if you think the lint is wrong. That's the
  scorer-editing cheat regardless of your intent.
- Never treat a VOID result as something to interpret — find the
  violation yourself; the harness deliberately won't name it.
