# goal.md template

Fill every placeholder and drop no section. The emitted file is copied to the
target as `.lfd/goal.md`; it must describe properties and measurements, not
private cases or infrastructure secrets.

```markdown
# Goal: <one-line outcome>

## Stage 0 — Build to spec
Implement the agreed behavior and make the ordinary test suite pass. Keep it
green before using the visible development scorer.

## Target
<two-sided metric definition>. Acceptance bar: holdout lower confidence bound
≥ <score>. Visible scores come only from
`scripts/target-repo/score-dev.sh`; blinded results come only from the bounded
holdout status command. A bare point estimate is not a score.

Holdout size: <n> cases (power-derived for δ=<delta> at <confidence>).
Holdout budget: <max requests> with at least <hours> between scored requests.

## Constraints and instruments
- Wall-clock budget: <hours>; spend ceilings: <per surface>.
- Allowed surface: <paths, tools, and services>. Everything else is denied.
- Capacity caps: <artifact ≤ N>, enforced by <visible scorer check>.
- One coherent variable per cycle, checked by <diff-scope instrument>.
- `.lfd/goal.md`, `.lfd/eval/`, `.lfd/harness/`, and the bundle manifest are
  managed evidence and must not be edited by the executor.
- Hidden cases, answers, canaries, private scorers, audit evidence, and
  per-operator probe details are outside the executor's surface.

## Cycle protocol
1. Run ordinary tests and `scripts/target-repo/score-dev.sh`.
2. Treat overlapping confidence intervals as no confirmed movement.
3. Before editing, record one hypothesis, numeric expected range, likely
   failure, and diagnostic in `LOG.md`.
4. Make one coherent change and stage only its intended paths.
5. Record the observed interval and whether it confirmed the hypothesis.
6. Commit the intended paths with a narrow cycle message; avoid broad
   all-tracked-file commit shortcuts.
7. Request holdout only at <cadence> or before acceptance, using the bundled
   request command. Read its result only through the bundled status command.

## Entropy and escalation
- After a cycle without interval-clearing movement, change structure rather
  than turning the same knob harder.
- Every <K> cycles, try a structurally distinct approach.
- Halt and request hub-side patching on divergence, a bounded blocking-detector
  result, <N> consecutive stalls, bundle drift, or transport failure.
- The executor never patches its own loss function.

## Stop conditions
Stop when the holdout lower bound reaches the bar, any budget is exhausted, or
marginal movement remains unconfirmed for <N> cycles. Finish `LOG.md` with the
best interval, bounded holdout history, confirmed/refuted hypotheses,
confounded cycles, and next steps.
```
