# goal.md template

Fill every placeholder; drop no section. Each section maps to one of the
four parts of a loss function: Stage 0 + Target (target), Constraints
(constraints + instruments), Cycle protocol (instruments), Entropy rules and
Stop conditions (forced entropy).

```markdown
# Goal: <one-line outcome>

## Stage 0 — Build to spec (inner loop)
Implement spec.md. Make the test suite pass. Do not score against the eval
until tests are green. Tests stay green every cycle thereafter.

## Target (outer loop)
<metric definition, both directions> · Bar: <score> on holdout.
Score with `harness/score.sh`. Scores are reported as <score ± hw> at 95%;
a bare point is not a score. A VOID result means a constraint was
violated — find and remove the violation; the harness will not tell you
which it was. Holdout: aggregate-only, max <N> calls per <period>; every
holdout call is logged as a (cycle, dev, holdout) triple.
Holdout size: <n> cases (power-derived: distinguishes δ=<delta> at the bar
with 95% confidence). Acceptance is measured on holdout exclusively.

## Constraints
- Wall-clock budget: <hours>. Check `harness/status.sh` every cycle — it
  shows elapsed and per-step time, projected spend, score history with
  intervals, the dev/holdout divergence flag, and your own token burn.
  Watch gain per token; a flat gradient at high burn means stop.
- Spend ceilings: <per surface>.
- Surface: <allowlist>. Everything else is off-limits.
- Capacity caps: <artifact ≤ N>.
- One variable per cycle: each cycle's change isolates a single variable.
  Multi-concern diffs mark the cycle CONFOUNDED in LOG.md and its result
  may not be cited by later hypotheses.
- `goal.md`, `harness/`, and `eval/` are read-only. Eval inputs may be read
  where the harness exposes them; eval answers never.

## Cycle protocol
1. Score (dev) — record <score ± hw>. Movement means non-overlapping
   intervals vs. the previous cycle; an in-interval wiggle is noise and
   counts as no movement.
2. Reflect: run `harness/probe.sh` — per-operator mutation scores, floors
   at <floor>. A falling operator score means memorizing along that axis;
   the next change must REMOVE an eval-shaped artifact (cap a list, blind
   a feature, reject a seed), never add one.
3. Hypothesize: log hypothesis, a committed numeric effect range
   (<from> → <to> ± <tol>), expected failure mode, and diagnostic in
   LOG.md BEFORE changing code. Results outside the committed range are
   refutations even when the score rose.
4. Change — ONE variable.
5. Log the result against the committed range.
6. Checkpoint: `git commit -am "cycle <n>: <score ± hw>"` — every cycle,
   gain or no gain, so the run is bisectable and crash-safe.

## Entropy rules
- Stall rule: if the last cycle produced no CI-clearing movement, the next
  attempt must be a structural change — same-knob-harder is banned.
- Exploration quota: every <K> cycles, try a structurally different
  approach even if the current one is still inching up.

## Auto-escalation (patch-mode triggers — no human report needed)
- `status.sh` prints `DIVERGENCE: dev/holdout` (dev lower-CI rising over
  the last <M> cycles while holdout is flat or falling).
- Any per-operator probe score below <floor>.
- No CI-clearing movement for <N> consecutive cycles despite the entropy
  rules.
On trigger: halt the loop at the current checkpoint and hand off to patch
mode (strongest available model, per SKILL.md).

## Stop conditions
Bar hit on holdout (interval lower bound ≥ bar) · any budget exhausted ·
marginal gain ≈ 0 for <N> consecutive cycles. On stop: write a final
report in LOG.md — best score with interval, divergence history,
per-operator probe scores at close, what generalized, what was abandoned,
confounded cycles, highest-leverage next steps.
```
