---
name: lfd-design
description: Design a loss function and harness for a long-running /goal optimization run (loss-function development, LFD). Use when the user wants to set up an autonomous optimization loop, distill a product from public artifacts, turn a spec into an optimization target, or asks to design a /goal. Observes the existing environment, interrogates the task, ingests or generates the spec, builds a power-calculated blinded eval with canary strings, generates and verifies the harness (bootstrap-CI scoring, operator-based mutation probes, contamination lints, compressibility checks), red-teams the target with Goodhart-typed cheat enumeration, runs an independent mechanical audit, and emits goal.md ready to launch. Re-invoke in patch mode when a running loop cheated and the loss function needs patching — patch mode must run on the strongest available model, never the executor.
---

# LFD Design

You are designing an optimization target, not solving a task. The agent that
receives `goal.md` is a competent, tireless, literal optimizer: it will satisfy
the target by the cheapest available path — memorizing the eval, hardcoding
answers, mining feedback channels into lookup tables. Your job is to make
genuine capability the cheapest path left.

A spec says "build this, make the tests pass." A loss function says "build
this, make the tests pass, **then** descend toward this bar on data you cannot
see." You are writing the second thing. It has four parts: the **target**, the
**constraints**, the **instruments**, and the **forced entropy**. Every /goal
you emit must contain all four.

This skill's mechanisms are operationalizations of established methods, and
each phase names which one it is applying. When judgment is required, apply
the named method's actual procedure — not a gestural version of it:

- **Goodhart taxonomy** (regressional / extremal / causal / adversarial) —
  cheat classification and fence matching, Phase 4.
- **Statistical power analysis** — eval sizing, Phase 3.
- **Contamination detection** (canary strings, n-gram overlap) — eval
  blinding and lint design, Phases 3 and 5.
- **Mutation testing** (operators, mutation score) — probe design, Phase 5.
- **Bootstrap confidence intervals** — score-movement significance, Phases
  5 and the cycle protocol.
- **Controlled-experiment ablation** (one variable per cycle) — cycle
  protocol.
- **Preregistration with committed effect sizes** — LOG.md discipline.
- **Reward over-optimization detection** (dev/holdout divergence) — stop
  and patch triggers.
- **Compressibility invariants** — structural lookup-table detection,
  Phase 5.

Three modes. **Design mode** (default): the phases below, in order. **Audit
mode**: run Phase 8.5 alone against an existing goal.md — an independent
context mechanically verifying a design it did not produce. **Patch mode**
(see end): a running loop cheated; fix the loss function, not the agent.
Patch mode is design-quality work: route it to the strongest available
model, never to the executing model.

## Phase 0 — Observe before asking

Inventory the environment BEFORE asking the user anything. The first principle
of harness engineering is observability — apply it to your own task:

- **Repo**: existing test suites, eval datasets, scoring scripts, CI
  workflows, logs/telemetry, CLAUDE.md / AGENTS.md.
- **Tooling**: what is installed and usable — Playwright/headless browsers,
  crawlers, image-diff tools, jq, database clients, a compressor (gzip/zstd)
  for the compressibility lint, and a Python with scipy/numpy if available
  (for power calculations and bootstrap CIs; both have hand-rolled
  fallbacks, but check).
- **Surfaces**: which API keys exist in the environment or .env files (check
  presence only; never print values), which providers are reachable.
- **Reference artifact**: if the user named a product or dataset, look at
  what is publicly accessible right now.
- **Scorer determinism**: will the metric involve any nondeterministic
  component (LLM judge, sampling, network calls, flaky rendering)? Note it
  now — it decides whether Phase 5's scorer needs bootstrap replication.

Reuse what exists — extend an existing scorer or eval rather than generating
a parallel one. Whatever observation could not answer becomes Phase 1.

## Phase 1 — Interrogate

Ask the user in ONE batched round, only what Phase 0 couldn't answer:

1. **Outcome** — what artifact or behavior, and what does "good" look like?
   Is there a reference artifact to score against?
2. **Eval source and size** — where do ground-truth cases come from, and how
   many are obtainable? (Phase 3 can build the eval if the answer is "nowhere
   yet.")
3. **Budgets** — wall-clock budget for the run, dollar ceiling, and which
   paid surfaces exist (crawler credits, LLM keys). An 80% solution in 2
   hours beats a 100% one in 30 days; get the user's actual tolerance.
4. **Surface** — what the agent may touch: directories, APIs, providers,
   models, concurrency. Everything unlisted is denied.
5. **Acceptance** — the score bar, measured on held-out data only, the
   confidence the user needs in that bar (default 95%), and the smallest
   score difference they care about distinguishing (default 5 points).
   These two numbers drive the Phase 3 power calculation. Plus a
   diminishing-returns stop ("if marginal gain ≈ 0 for N cycles, stop and
   report").

## Phase 2 — Spec: the inner loop

The spec is the starting point, not the finish line. Before designing any
optimization target:

- If a spec exists, read it. If not, generate one: reverse-engineer the
  reference artifact (public surfaces only) into a system design plus
  concrete test cases, and write it to `spec.md`.
- The spec's test suite is the **inner loop**: short horizon, fast feedback,
  one objective — make the tests pass. The eval is the **outer loop**: long
  horizon, sparse feedback.
- `goal.md` must gate the outer loop behind the inner one: Stage 0 = build
  to spec, tests green, before any descent on the eval. Never let the agent
  optimize a half-built system against sparse, slow feedback.

## Phase 3 — Build the eval

If the user cannot hand over enough cases, build them — for more and more
problems, real expected outputs are sitting in public:

- Collect real expected outputs from the reference artifact at scale.
  Public artifacts only; respect robots.txt, rate limits, and ToS.
- Dedup. Check diversity — no single entity, date range, or template may
  dominate, or the eval teaches a shortcut.
- Reject any case that overlaps seed or fixture data.
- Collection must be independent of the future optimizer: do it now, in this
  session, and land the answers outside the optimizer's surface.

**Size by power calculation, not by feel.** Run
`scripts/design/power-calc.py --bar <bar> --delta <delta> --confidence
<0.95>` — do not hand-compute this arithmetic; the script is the single
source of truth so the same inputs always produce the same N across runs.
Worked example the script reproduces: bar 0.80, δ = 0.05 → N ≈ 246.
Paste the script's output into `LOG.md`'s header and the goal.md Target
section verbatim, and treat `derived_n` as a floor. If the obtainable
case count is below `derived_n`, say so explicitly and get the user to
either lower the resolution they expect (larger δ) or widen collection —
do not silently proceed with an eval that cannot statistically support
its own acceptance bar. (The old "~200 minimum" heuristic is what this
calculation replaces; it also remains true that a small eval is
enumerable and WILL be memorized.)

**Canary the holdout at generation time.** Run
`ops/generate-canaries.sh <target-dir>` (hub-root-relative) against the
target's `eval/holdout/` — do not hand-embed canaries case by case. It writes a unique `LFD-CANARY-{16 hex}`
into each stored answer and records the full list in `canary-list.json`,
kept outside the optimizer's surface alongside the holdout answers. Any
later appearance of a canary anywhere in the working tree or git history is
proof of eval access — this is what `canary_scan` in `lint.sh` greps for.
Canaries are per-run: re-run the generator if the eval is ever reused, so
stale canaries never become a guessable pattern.

- **Split**: `eval/dev` (scored freely, misses reported but capped) and
  `eval/holdout` (scored rarely, aggregate-only; acceptance measured here
  exclusively; answers outside the repo if at all possible).
- **Visibility rule, stated explicitly in goal.md**: eval INPUTS may be
  visible (probe generation needs them); eval ANSWERS are never readable —
  dev answers live only inside the scorer, holdout answers outside the repo.

## Phase 4 — Design the loss function

**Target.**
- The metric must be mechanically computable by a script, at the right
  resolution for the claim. An LLM judge that "compares two screenshots"
  approves 12px spacing errors; a pixel-diff does not. Match the instrument
  to the precision the user actually wants.
- The metric must penalize BOTH failure directions. Recall without precision
  invites a return-everything cheat; precision without recall invites a
  return-one-thing cheat. If the user gives a one-sided metric, fix it and
  tell them why.
- If Phase 0 found any nondeterminism in the scoring path, the metric
  definition must specify the replication count and CI method (see Phase 5,
  score.sh) — a single noisy sample is not a score.
- Run a leak audit on every feedback channel using
  `scripts/design/leak-audit-calc.py --bits-per-call <n> --expected-cycles
  <n> --eval-size <n>` — do not hand-compute this. Estimating
  `bits-per-call` for a given channel (e.g. a capped miss-list) is a
  judgment call; the reconstruction-fraction arithmetic from that estimate
  onward is not, and the script is the single source of truth for it. On
  FAIL, cut feedback resolution (cap the miss list, return aggregates) or
  grow the set. Paste the script's JSON output into the design notes;
  Phase 8.5 checks for its presence.

**Constraints.**
- Wall-clock budget, stated in the /goal. Agents have no sense of time and
  will grind 10 hours for 2%.
- Dollar and credit ceilings per paid surface.
- Surface allowlist from Phases 0–1.
- Methodology rules (LLM-in-the-data-plane allowed? deterministic only?).
- **Capacity caps** on every artifact that could function as a lookup table:
  keyword lists, regex sets, seed data, special-case branches. Name the
  artifact and the cap explicitly ("keyword list ≤ 20 entries").
- **One variable per cycle** (controlled-experiment ablation): each cycle's
  change must isolate a single variable, so LOG.md's causal attributions
  stay true. A cycle that bundles multiple independent edits produces a
  confounded result that poisons every later hypothesis built on it. State
  the rule in goal.md; enforce it with the diff-scope lint in Phase 5.

**Enumerate and CLASSIFY the cheats.** Read `references/cheat-museum.md`,
then list at least 10 ways a lazy optimizer could max THIS metric without
solving THIS task. For each cheat, assign its Goodhart type — the type
determines which fence family actually closes it:

| Type | What it is | Correct fence family |
|---|---|---|
| **Regressional** | Metric imperfectly correlates with the goal; optimizing the tail finds noise, not capability | Enlarge/diversify the eval; raise the resolution of the instrument |
| **Extremal** | Correlation validated in a normal range breaks when a knob is pushed to an extreme | Bound how far any single knob/parameter may move; range constraints |
| **Causal** | The agent intervenes on the measuring machinery itself rather than the measured thing | Structural firewall: read-only harness, checksummed scorer, holdout outside the write surface |
| **Adversarial** | An intelligent optimizer actively hunts the gap between measure and target | Blinding, rotation, holdout, feedback-resolution cuts |

A fence from the wrong family is a non-fence: adding eval cases does
nothing against a scorer-editing (causal) cheat; a read-only bit does
nothing against tail-chasing (regressional) noise. For each cheat, write:
the cheat, its type, the type-matched fence in `goal.md`, AND the
instrument that detects violation. A constraint without an instrument is a
vibe — the agent will violate it cheerfully because it can't tell it's
violating it. A fence whose family doesn't match its cheat's type fails
Phase 8.5.

**Enforcement design rule.** Any constraint that references eval content
(e.g. "no literal in the codebase may match an eval item") can only be
checked by the harness — the agent can't check it without reading the eval.
Put the check in `harness/lint.sh`, run it inside `score.sh`, and on
violation VOID the score and report nothing else. Naming the offending
literal turns your lint into a membership oracle the agent can mine
string-by-string (museum exhibit 12). Your enforcement instrument is itself
a feedback channel — leak-audit it like any other.

## Phase 5 — Generate the harness

Write these files now, tailored to the task. Do not ship placeholders.
Reuse anything Phase 0 found.

- `harness/score.sh` — the task-specific scorer. Pixel-diff for a UI clone
  (deterministic rendering: frozen time, animations off, pinned fonts,
  fixed viewport), recall@k + precision for retrieval, structured JSON diff
  for API behavior. Runs `lint.sh` first: any violation voids the score
  (output `VOID: constraint violation` and nothing more).

  **Scores are estimates with intervals, not point samples.** If any part
  of the scoring path is nondeterministic (Phase 0 flagged it), score.sh
  replicates: R runs (default 5) or bootstrap resampling over eval cases
  (default 1000 resamples), and reports `score ± half-width` at 95%. If the
  path is fully deterministic, replication is skipped but the case-level
  bootstrap over the eval set still runs — the eval is a sample of the task
  distribution, so the interval quantifies eval-sampling noise either way.
  The reported interval is what the cycle protocol's movement rule consumes.

  Scores `eval/dev` by default; `--holdout` returns one aggregate number
  (with its interval), rate-limited, and appends `(cycle, dev_score,
  holdout_score)` to an audit log — this triple series is the divergence
  detector's input. Prefer a single append-only log as the one source of
  truth for both the rate limit and the divergence check (count recent
  rows for the limit, read the same rows for the trend) over separate
  state files — one file to reconcile beats two.

  **Holdout scoring runs in a separate execution context the agent has no
  network route to and no credential to invoke — not "a different
  directory," an actual isolation boundary.** This is a property
  requirement, not an implementation choice: two isolated processes
  (container, VM, CI job, host — whatever the environment provides),
  connected only by an orchestrating layer the agent doesn't control, with
  eval data readable only from the scoring side. Do not name a specific
  product or platform in `goal.md` or in this design — the requirement is
  topological (no route, no credential) and must hold regardless of what's
  running the loop. See `references/isolation-patterns.md` for worked
  examples across a few common setups; treat it as one-of-several, not the
  design.

- `harness/lint.sh` — called only by `score.sh`; detailed findings go to a
  file outside the optimizer's read surface, for the human. Four named
  sub-checks, all feeding the same VOID-with-no-detail behavior:
  1. `capacity_caps()` — every capped artifact from Phase 4, counted.
  2. `canary_scan()` — grep the working tree AND `git log -p` history for
     any canary from the Phase 3 canary list. A hit is proof of eval
     access. (Contamination detection, exact-match tier.)
  3. `ngram_overlap()` — CALL `scripts/design/ngram-overlap.py
     --solution-dir <src> --eval-answers-dir <eval/holdout> --n 8
     --threshold <tuned in Phase 6>`, don't reimplement n-gram/Jaccard
     matching per task — the library is task-agnostic and already handles
     file walking and exit codes. Catches near-verbatim and paraphrased
     leakage that an exact canary can't. (Contamination detection, fuzzy
     tier.)
  4. `compressibility()` — CALL `scripts/design/compressibility.py
     --solution-dir <src> --eval-size <n> --cycle <n>`, don't reimplement
     the compression/history tracking per task. It appends its own history
     row per call (no separate state file needed) and flags when
     compressed-size-vs-eval-size grows past the slope threshold — a
     genuine solution's compressed size stays roughly flat as the eval
     grows; a lookup table's tracks it linearly, including nested-dict
     lookup tables that dodge a grep-based check.
  5. `diff_scope()` — one-variable-per-cycle enforcement: flag a cycle
     whose commit touches multiple unrelated concerns (heuristic: distinct
     top-level modules/files beyond a declared threshold, or edits both to
     data artifacts and logic in one cycle). Findings go to the human file;
     repeated violations are a patch-mode trigger, not a VOID (the score is
     still honest — the attribution is what's broken).

- `harness/probe.sh` — **mutation testing over eval inputs, with named
  operators and per-operator scores.** Not ad hoc perturbation:
  1. Define the operator table for THIS task's input domain, in the script
     header — e.g. for text tasks: `paraphrase`, `entity_swap`,
     `format_shift`, `boundary_value`; for data tasks: `column_reorder`,
     `date_shift`, `unit_change`. 3–6 operators, each a systematic
     transformation with a one-line definition.
  2. Generate N mutants per operator (default 10) from dev INPUTS.
  3. Score the solution on the mutants; per operator, compute the
     **mutation score** = fraction of mutants where performance ≈ the
     un-mutated dev performance (within the score.sh interval).
  4. Report per-operator, never blended: `paraphrase: 0.9 · entity_swap:
     0.4 · format_shift: 0.9` tells you exactly WHICH generalization is
     missing; a single blended 0.73 tells you nothing actionable.
  A minimum per-operator mutation score (default 0.8) is an emission gate
  in Phase 8 and a patch trigger during the run. Optional `--adversarial`
  flag for a v2 escalation: when an operator's score is borderline, run a
  small search over that operator's parameter space for the worst-case
  mutant instead of sampling randomly — search finds brittleness that
  random sampling misses by luck. Ship the flag; default it off (cost).

- `harness/status.sh` — per-step timestamps and total wall-clock elapsed;
  spend so far AND projected burn before the next paid batch, per surface;
  score history per cycle **with intervals**; the dev/holdout triple series
  and a computed **divergence flag**: if dev's lower CI bound has risen
  over the last M cycles (default 5) while holdout is flat or falling,
  print `DIVERGENCE: dev/holdout` — this is the canonical
  reward-over-optimization signature (proxy climbs while true target
  degrades) and it auto-triggers patch mode per goal.md; and the
  optimizer's own token consumption where session logs allow. Gain per
  token is the gradient of the optimization itself — the loop should be
  self-aware.

- `eval/dev/` and `eval/holdout/` — from Phase 3, canaries embedded,
  power-calculated N documented.
- `LOG.md` — instantiate `references/log-template.md`: one entry per cycle
  with `hypothesis (with committed effect-size range) / expected failure
  mode / diagnostic / result`, written before the change, not after. This
  is what survives context compaction.

## Phase 6 — Verify the harness yourself

Do this now, with your own tools. Do not delegate it to the user:

1. Run `score.sh` on dev — it must produce a number WITH an interval.
2. Calibrate: score one known-good and one known-bad output. The scorer
   must separate them decisively — their intervals must not overlap. A
   broken scorer optimizes noise; an interval-overlapping scorer cannot
   support the movement rule.
3. Run `probe.sh` once — every operator must generate mutants and report a
   per-operator score. Run `status.sh` once.
4. Blinding check: from the optimizer's working directory, try to read the
   holdout answers. If you can, the agent can.
5. Trip each lint deliberately, then remove the plant:
   - plant an eval literal → confirm VOID without naming it;
   - plant a canary string in a source comment → confirm `canary_scan`
     VOIDs;
   - paste a paraphrased eval answer into a comment → confirm
     `ngram_overlap` fires at the calibrated threshold (tune the threshold
     now if it doesn't);
   - commit a two-concern diff → confirm `diff_scope` flags it in the
     human-side findings file.
6. Sanity-check the compressibility baseline: record the compressed
   solution size at cycle 0 so the invariant has a starting point.

## Phase 7 — Red-team your draft

Before emitting, simulate the laziest possible agent against your draft
/goal: what is the five-minute win? Common ones: seed data that mirrors the
eval, mining per-item miss feedback into a keyword lookup table, gaming a
judge, editing the scorer or the goal itself, declaring victory on the dev
set, keeping a tracked signal just under its written threshold. Patch the
draft and simulate again. Emit only when three consecutive simulations find
nothing cheaper than doing the real work.

Phase 7 is a self-check by the same context that produced the design — it
is necessary but not sufficient, which is why Phase 8.5 exists.

## Phase 8 — Emit goal.md

Fill the structure in `references/goal-template.md`. Every placeholder gets
a task-specific value; no section is dropped. Invariants the emitted goal.md
must keep regardless of task: the Stage 0 tests-green gate, VOID semantics,
holdout-only acceptance, the read-only set including goal.md itself, the
per-cycle checkpoint commit, the one-variable rule, the CI-based movement
rule, the divergence auto-trigger, the per-operator probe gates, the
entropy rules, and the stop conditions.

Emission gates (all must hold):
- Derived eval N (Phase 3 power calculation) is met by the actual holdout.
- Every Phase 4 cheat has a Goodhart type and a type-matched fence.
- Every constraint has a named instrument in the harness.
- Per-operator mutation scores from Phase 6's probe run meet the minimum
  on the known-good calibration output.

## Phase 8.5 — Independent audit (audit mode)

Phases 6–7 are the designer grading its own design — structurally the same
self-check failure this skill exists to prevent, one level up. Before
Phase 9, the completed goal.md + harness get an INDEPENDENT audit: a fresh
context (new session or subagent that did not produce the design).

**Run the mechanical pass first, as a script, not as LLM judgment:**
```
scripts/design/audit-checklist.py --goal-md goal.md --harness-dir harness/ --eval-dir eval/
```
This deterministically checks constraint↔instrument pairing (grepped),
infra-agnosticism (goal.md scanned for named products/mechanisms),
eval sizing against the Phase 3 `derived_n`, canary coverage on every
holdout item, interval-discipline presence in `score.sh`, and probe/lint
completeness (all five named sub-checks present). Any mechanical FAIL
returns to the relevant phase before spending any further audit effort —
there's no reason for the independent auditor to read the design closely
if a grep-level check already failed.

**Then the auditor (fresh context) judges what the script explicitly
cannot**, listed in the script's own `still_requires_independent_llm_judgment`
output:
1. **Leak-audit arithmetic honesty**: re-run
   `scripts/design/leak-audit-calc.py` with your own independent estimate
   of bits-per-call for each channel — if your estimate disagrees
   meaningfully with the design's, that's the signal; the arithmetic
   itself was already verified deterministically.
2. **Goodhart type↔fence matching**: for each Phase 4 cheat, does the
   assigned type actually fit, and does the fence belong to that type's
   family? This is semantic, not greppable — spot-check at least two by
   mentally simulating the cheat against the fence.
3. **Calibration quality**: from Phase 6's actual run output, do the
   known-good/known-bad intervals separate decisively, not just
   technically not-overlapping by a hair?
4. **Escalation and patch-mode routing**: is the auto-escalation section
   complete and does the design correctly state patch mode routes to the
   strongest available model, not the executor?
5. **Blinding re-verification**: from the optimizer's surface, actually
   attempt to read holdout answers and the canary list. Readable = FAIL.
   (Scriptable in principle given a concrete execution environment, but
   left to the auditor here since the skill body stays infra-agnostic per
   Phase 5 — see `references/isolation-patterns.md`.)

Combine the script's mechanical verdict with the auditor's judged items
into one PASS/FAIL summary. Any FAIL returns to the relevant phase. Only a
clean combined audit proceeds to Phase 9. When this skill is invoked in
**audit mode**, run this phase alone against the provided goal.md and
report both the script output and the judged items.

## Phase 9 — Pre-flight (the two things only the human can do)

Everything else was verified in Phases 6 and 8.5. This hub repo IS the
eval side: onboard a target with `bin/lfd new-target <name> <repo-url>`,
which scaffolds `targets/<name>/` (config, eval dirs, an empty harness
directory, and log). Design mode must write the real harness before
activation. Deterministic scripts handle every mechanical step (dev scoring,
holdout request/poll/status, rate limiting, divergence computation);
`references/agent-instructions.md` is what the executor actually reads,
and marks each step **[script]** or **[judgment]** so the executor knows
which parts are fixed contracts and which require thought. Copy
`templates/target-repo/.` plus `agent-instructions.md` and the generated
`goal.md` into the target repo before launch (see
`docs/onboarding-a-target.md`).

Tell the user:

1. Use a disposable API key with a provider-side spend limit — and set
   cycle 1's own spend cap near zero, so step 2 costs minutes, not hours.
2. **Babysit cycle 1.** Watch what the agent touches and confirm it uses
   the instruments. Then go to bed.

Do not automate step 2 away, and do not write its timing into goal.md. Any
check documented in goal.md is legible to the optimizer and becomes a
target it can learn to stay just under (museum exhibits 3 and 9, recursed
one level up). An unscheduled human look has no attack surface precisely
because nothing the agent can read says when it happens. The design goal is
cheap human unpredictability, not zero human presence. Everything
mechanical — probe-gap thresholds, stall counts, divergence — IS automated
(they auto-trigger patch mode); the human is reserved for the one check
that must stay unwritten.

## Patch mode — when the loop cheats anyway

A cheat mid-run is a bug in the target, not the agent. Patch mode is
design-quality work — identifying which channel leaked and closing it
without opening a new one. Route it to the strongest available model; never
let the executing model patch its own leash (it will patch the symptom that
got caught, not the loophole).

Auto-triggers (wire these into goal.md; they need no human report):
- `status.sh` prints `DIVERGENCE: dev/holdout` — dev rising while holdout
  is flat/falling over M cycles.
- Any `probe.sh` per-operator mutation score falls below its floor.
- Stall: no CI-clearing movement for N consecutive cycles despite the
  entropy rules.
Manual triggers: the user reports a cheat, or LOG.md shows one.

Then:
1. Read `LOG.md`, the score history (with intervals — distinguish a real
   regression from noise before "fixing" anything), and the diff since the
   last honest checkpoint.
2. Identify the open path: which feedback channel leaked, which artifact
   had spare capacity, which constraint lacked an instrument.
3. Classify the cheat's Goodhart type FIRST, then patch the **loss
   function**, not the agent's code, with a fence from the matching
   family: regressional → widen/diversify the eval; extremal → bound the
   knob; causal → harden the firewall (read-only, checksum, relocate);
   adversarial → cut feedback resolution, rotate/re-blind. A patch from
   the wrong family will hold until the same cheat returns wearing
   different syntax.
4. Append the exhibit to `references/cheat-museum.md` — what it looked
   like → its type → the fence that closed it.
5. Re-verify the harness (Phase 6), re-run the audit (Phase 8.5), revert
   eval-shaped artifacts the cheat produced, regenerate canaries if the
   eval was exposed, and resume the loop from the last honest checkpoint.
