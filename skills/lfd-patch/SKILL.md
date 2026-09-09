---
name: lfd-patch
description: Repairs a Scout loss function after divergence, probe weakness, leakage, a newly observed shortcut, or stale audit evidence. Use only when the user explicitly asks to patch the evaluation design; it changes hub-side goals, cases, fences, scorers, or feedback resolution and never patches the target solution on the executor's behalf.
---

# LFD Patch

Run this hub-side with the strongest available design model, never from the
executor's target context.

1. Read the append-only run log, bounded results, private probe evidence,
   previous audit, and diff since the last honest checkpoint. Distinguish real
   movement from interval noise.
2. State the exploited path. Classify it first using
   [`../lfd-shared/references/cheat-museum.md`](../lfd-shared/references/cheat-museum.md):
   regressional, extremal, causal, or adversarial.
3. Apply the matching fence family: diversify/raise resolution, bound the
   extreme, harden the measurement firewall, or cut/rotate/reblind feedback.
   Patch the loss function and private harness—not the target solution.
4. Add the newly observed pattern, classification, and effective fence to the
   cheat museum without adding target-private examples.
5. Re-run calibration and guardrail trip tests. If exposure occurred, rotate
   cases and regenerate canaries.
6. Re-equip and verify the agent bundle through `bin/lfd onboard equip` and
   `verify`. Then require `lfd-audit` in another fresh context. Activation must
   go through `bin/lfd activate` after the new evidence passes.
