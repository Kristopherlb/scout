# Audit checklist (Phase 8.5 — independent audit)

Run by a context that did NOT produce the design (fresh session, subagent,
or a plain script wherever the check is structural). The audit is
deliberately mechanical — counting, grepping, arithmetic — so it cannot be
argued with. Emit PASS/FAIL per line plus a one-page summary. Any FAIL
returns to the named phase. Only a clean audit proceeds to Phase 9.

## A. Constraint↔instrument pairing (→ Phase 4/5 on FAIL)
- [ ] Enumerate every constraint line in goal.md's Constraints section.
- [ ] For each, name the harness check that detects violation
      (`lint.sh` sub-check, `score.sh` behavior, or `status.sh` field).
- [ ] Zero unpaired constraints. A constraint without an instrument is a
      vibe.

## B. Leak-audit arithmetic (→ Phase 4 on FAIL)
- [ ] The design notes contain the written arithmetic: bits revealed per
      scoring call × expected cycle count, compared against eval size.
- [ ] Recompute it. The inequality holds with margin (reconstructable
      fraction of the eval over the whole run < 25%).
- [ ] The enforcement channel itself (VOID reporting) was included in the
      audit — VOID output is exactly `VOID: constraint violation`, nothing
      else, verified by tripping it.

## C. Goodhart coverage (→ Phase 4 on FAIL)
- [ ] Every cheat in the Phase 4 enumeration and every applicable museum
      exhibit carries a type tag: regressional / extremal / causal /
      adversarial.
- [ ] Every fence belongs to its cheat's matching family
      (regressional→eval enlargement/instrument resolution;
      extremal→knob bounds; causal→structural firewall;
      adversarial→blinding/rotation/feedback cuts).
- [ ] Spot-check two: simulate the cheat mentally against the fence; a
      wrong-family fence fails even if a fence exists.

## D0. Infra-agnosticism of the isolation requirement (→ Phase 5 on FAIL)
- [ ] goal.md's holdout-scoring language states the property (no network
      route, no credential, from the agent's execution context) and does
      NOT name a specific product, platform, or orchestrator.
- [ ] If a concrete implementation was chosen, it lives in
      `references/isolation-patterns.md` or an equivalent project-specific
      doc — not inlined into goal.md itself. Swapping infra later should
      not require touching goal.md.

## D. Eval sizing and blinding (→ Phase 3 on FAIL)
- [ ] The power calculation is written down (bar, δ, confidence → derived
      N) and holdout N ≥ derived N.
- [ ] Dev answers live only inside the scorer; holdout answers live outside
      the repo. Physically verify the paths.
- [ ] Every holdout item carries a canary; the canary list lives outside
      the optimizer surface; canaries are unique to this run.
- [ ] From the optimizer's working directory, attempt to read holdout
      answers and the canary list. Readable = FAIL.

## E. Interval and movement discipline (→ Phase 5/6 on FAIL)
- [ ] `score.sh` output includes an interval (replication or bootstrap).
- [ ] Phase 6 calibration recorded: known-good vs known-bad intervals do
      not overlap.
- [ ] goal.md's movement rule, stall rule, and stop conditions all
      reference the interval, not a bare point.

## F. Probe and lint completeness (→ Phase 5 on FAIL)
- [ ] `probe.sh` defines named operators (3–6) with one-line definitions;
      reporting is per-operator, never blended; floors are stated in
      goal.md.
- [ ] `lint.sh` contains the named sub-checks: `capacity_caps`,
      `canary_scan`, `ngram_overlap`, `compressibility`, `diff_scope` —
      and Phase 6 tripped each one deliberately (evidence recorded).
- [ ] Compressibility baseline (cycle-0 compressed size) recorded in
      LOG.md header.

## G. Escalation wiring (→ Phase 8 on FAIL)
- [ ] goal.md contains the auto-escalation section: divergence flag,
      per-operator floor breach, CI-stall — each halting to patch mode.
- [ ] Patch mode is routed to the strongest available model, stated in
      goal.md or the run configuration — the executor may not patch its
      own leash.
- [ ] The human cycle-1 babysit and any spot-check timing are NOT
      documented in goal.md or anywhere on the optimizer's read surface
      (threshold-hugging fence, museum exhibit 13).
