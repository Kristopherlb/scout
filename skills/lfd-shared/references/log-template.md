# LOG.md template

The iteration log is what survives context compaction: the optimizer reads
it back to reflect across cycles, and the human reads it to audit the run.
Hypothesis, expected failure mode, and diagnostic are written BEFORE the
change — a hypothesis written after the result is a rationalization.

Preregistration discipline: the hypothesis commits to a NUMERIC effect-size
range, not a direction. "Score should improve" is confirmable by any lucky
roll; "0.61 → 0.68 ± 0.03" is falsifiable. A result outside the committed
range marks the hypothesis WRONG even if the score went up — a gain you
didn't predict is a gain you don't understand, and the reflection field
must say what actually caused it before it can be built on.

Ablation discipline: one variable per cycle. The Change field names the
single variable; if the diff touched more than one concern, the cycle's
Result is marked CONFOUNDED and its causal claim may not be cited by later
hypotheses.

Scores are estimates: always record the interval `score ± hw` that
score.sh reports, never a bare point. "Movement" means the intervals of
consecutive cycles do not overlap.

```markdown
# Iteration Log — <goal one-liner>

Started: <timestamp> · Budgets: <hours> wall-clock / <$> spend
Holdout N: <n> (derived by power calc: bar <bar>, δ <delta>, 95%)
Cycle-0 compressed solution size: <bytes> (compressibility baseline)

## Cycle <n> — <timestamp>
- Score (dev): <score ± hw> (prev: <score ± hw>) · Movement: <yes/no — intervals overlap?>
- Probe (per operator): <op1: s1 · op2: s2 · op3: s3> (floors: <floor>)
- Holdout triple (if called this cycle): (<n>, <dev ± hw>, <holdout ± hw>)
- Hypothesis: <what change should move the metric, and why>
- Predicted effect: <from> → <to> ± <tolerance>  ← committed BEFORE the change
- Expected failure mode: <how this change could fail or turn into a cheat>
- Diagnostic: <what observation distinguishes success from the failure mode>
- Change: <the ONE variable changed> (commit <hash>)
- Result: <score ± hw after> · Hypothesis: <confirmed — landed in range /
  refuted — outside range / CONFOUNDED — multi-variable diff> · <what was learned>
- Reflection: <generalizing or memorizing? which operator scores moved?
  if memorizing, which eval-shaped artifact gets removed next cycle;
  if result was outside the predicted range in EITHER direction, what
  actually caused it>

## Final report
- Best holdout score (± interval):
- Dev/holdout divergence over the run: <none / cycles where flagged>
- Per-operator probe scores at close:
- What generalized:
- What was abandoned (and why):
- Confounded cycles (excluded from causal claims):
- Highest-leverage next steps:
```
