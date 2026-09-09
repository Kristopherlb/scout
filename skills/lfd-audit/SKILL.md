---
name: lfd-audit
description: Independently audits an existing Scout LFD design after mechanical checks. Use in a fresh private-hub context when the user explicitly asks to audit a target, assess leakage and Goodhart fences, verify calibration and blinding, finalize judgment evidence, or determine whether activation is justified.
---

# LFD Audit

This skill must run in a fresh context that did not produce the design. That is
a process requirement recorded by attestation, not cryptographic proof.

1. Read the target's `goal.md`, eval manifest, calibration, private harness,
   and verified bundle. Read
   [`../lfd-shared/references/audit-checklist.md`](../lfd-shared/references/audit-checklist.md)
   and [`../lfd-shared/references/science.md`](../lfd-shared/references/science.md).
2. Run:

   ```bash
   bin/lfd audit mechanical <name> --json
   ```

   A mechanical PASS exits `3` and remains `incomplete`. Any mechanical FAIL
   returns to design.
3. Independently judge exactly five findings: `leakage_estimate`,
   `goodhart_fence_matching`, `calibration_quality`, `escalation_wiring`, and
   `blinding_verification`. For each, record `PASS|FAIL` plus concrete,
   non-empty evidence. Actually test target-side unreadability for blinding.
4. Write a judgment file with schema version 1, a truthful
   `independent_context_attestation`, and those five findings. Finalize through:

   ```bash
   bin/lfd audit finalize <name> --judgment-file <path> --json
   ```

5. Report the final verdict and failed evidence. Do not activate a failed,
   incomplete, malformed, or stale audit. A passing report may proceed through
   `bin/lfd activate`; never edit active status manually.
