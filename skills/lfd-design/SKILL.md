---
name: lfd-design
description: Designs a blinded, anti-Goodhart Scout evaluation and its real dev, holdout, and probe scorers in a private hub. Use after Scout onboarding inspection when the user needs a goal, powered eval split, task-specific loss function, calibration fixtures, liveness policy, detector policy, and verified agent-visible bundle for a new target.
---

# LFD Design

Design the measurement system; do not optimize the target implementation. Work
only in a private Scout hub. Real cases, answers, canaries, private scorers, and
audit evidence must never enter public source or the target checkout.

## Inputs

Require a validated `targets/<name>/target.json` and the sanitized
`target-profile.json` produced by:

```bash
bin/lfd onboard inspect <name> --checkout <target-checkout>
```

Read the target's existing tests, build files, and agent instructions. Ask one
batched set of questions only for facts inspection cannot answer: desired
behavior, ground-truth source, time/cost ceilings, permitted surfaces, holdout
acceptance bar, confidence, and smallest meaningful movement.

## Design sequence

1. Write `goal.md` from
   [`../lfd-shared/references/goal-template.md`](../lfd-shared/references/goal-template.md).
   Ground every constraint in a named instrument and require one coherent
   variable per optimization cycle.
2. Size the eval with `../lfd-shared/scripts/power-calc.py --bar <bar>
   --delta <delta> --confidence <confidence>`. Record its inputs and result;
   never replace the calculation with intuition. Build diverse, non-overlapping
   `eval/dev` and `eval/holdout` sets at or above the result.
3. Generate per-run holdout canaries with `bin/lfd canaries <name>`. Keep
   holdout answers and the canary list private.
4. Enumerate at least ten target-specific shortcuts using
   [`../lfd-shared/references/cheat-museum.md`](../lfd-shared/references/cheat-museum.md).
   Classify each as regressional, extremal, causal, or adversarial; pair it
   with the matching fence family and an executable detector.
5. Measure every feedback channel with
   `../lfd-shared/scripts/leak-audit-calc.py`, passing the design's explicit
   reconstruction threshold. Reduce feedback resolution or enlarge/rotate the
   eval when the estimate fails.
6. Replace all fail-closed onboarding harnesses with executable task-specific
   implementations:

   - `dev-harness/score-dev.sh` owns visible lint and scoring exactly once;
   - `harness/score-holdout.sh` runs target code in Stage 1 and compares hidden
     answers only in trusted Stage 2;
   - `harness/probe-holdout.sh` reports per-operator mutation scores privately.

   Use bootstrap intervals over cases. Respect the topology in
   [`../lfd-shared/references/isolation-patterns.md`](../lfd-shared/references/isolation-patterns.md).
   Never leave a placeholder, skipped check, or success-without-work path.
7. Configure liveness, sandbox, cadence/budget, executor, and each detector's
   `advisory|blocking` enforcement in `target.json`. Operational values belong
   only in that contract.
8. Execute the dev scorer and probe. Score known-good and known-bad fixtures;
   write `calibration-report.json` only when their intervals do not overlap.
   Deliberately trip each guardrail and confirm it fails closed without leaking
   case-level detail.
9. Generate and verify the public surface:

   ```bash
   bin/lfd onboard equip <name> --checkout <target-checkout>
   bin/lfd onboard verify <name> --checkout <target-checkout>
   bin/lfd onboard status <name> --checkout <target-checkout>
   ```

10. Stop at the independent-judgment boundary. Ask for `lfd-audit` in a fresh
    context; do not grade this design in the producing context.

## Completion criteria

- The powered dev/holdout split exists and holdout material remains private.
- All three scorers are executable and fail closed on unavailable dependencies.
- Known-good and known-bad intervals separate.
- Every constraint, cheat, and feedback channel has an explicit instrument or
  fence.
- Bundle generation and equipped verification pass.
- Onboarding status says `needs_audit`, never `active`.

For the scientific rationale and canonical terminology, read
[`../lfd-shared/references/science.md`](../lfd-shared/references/science.md).
