# Architecture

## Standards authority and dependency direction

Scout's canonical requirements and accepted decisions live in `rac/` and are
mapped to enforcement evidence in `standards/controls.json`. RAC validates the
corpus and generated agent guidance; `tools/check_standards.py` provides the
repository-specific deterministic checks. This separation avoids presenting a
document validator as a semantic source-code analyzer.

The current layout uses a partial inward dependency boundary:

| Layer | Current location | Dependency rule |
|---|---|---|
| Inner policy | `tools/lfd_common.py`, `tools/lfd_contract.py` | import no Scout command or operations adapter |
| Application commands | other `tools/*.py` | may depend on policy, not Python adapters in `ops/` |
| Operations adapters | `ops/`, workflows | may depend inward; own privileged I/O and integration |
| Composition root | `bin/lfd` | routes requests and delegates behavior |

Python runtime dependencies must remain acyclic. These are guardrails around
the present design, not a claim that the existing directories are a finished
package architecture. See ADR-001 and ADR-002 under `rac/decisions/` for the
rationale and alternatives.

## Public framework, private operational hub

The LFD design's core property: holdout scoring runs where the agent has no
route and no credential. The public project supplies the framework and
synthetic fixtures. Operators copy a release into a separate private hub that
manages real targets through the `targets/` registry. Agents work in their own
repositories and interact with the private hub through annotated
`holdout-check-N` tags (requests) and commit statuses (responses).

The public project and each private operational hub are separate security
domains. A private hub may consume reviewed framework changes from public
source, but private target commits must never flow back into public history.

## Registry schema — `targets/<name>/`

| Path | Committed? | Purpose |
|---|---|---|
| `target.json` | yes | strictly validated operational contract; see fields below |
| `eval/dev/` | yes | dev suite (also copied to the target repo) |
| `eval/holdout/` | yes | holdout cases with embedded canaries — **never leaves the hub** |
| `canary-list.json` | yes | per-run canary registry (proof-of-access detection) |
| `harness/score-holdout.sh` | yes | per-target scorer; two-stage contract |
| `harness/probe-holdout.sh` | yes | per-target holdout mutation probe |
| `log.jsonl` | yes | append-only scoring history; single source of truth |
| `audit-report.json` | yes | Phase 8.5 audit output, stamped by `bin/lfd audit` with the audited `harness_version`; must say PASS and match the current harness before active status |
| `calibration-report.json` | yes | Phase 6 known-good/known-bad scores + intervals; the two must not overlap; required before active status |
| `retros/` | yes | post-run retrospectives (`bin/lfd retro`) |
| `runs/` | **no** (gitignored) | captured Stage-1 outputs per tag, for `bin/lfd review` |
| `goal.md` | yes | the emitted optimization target (copied to the target repo at launch) |

### `target.json` fields

The versioned contract groups operational values under `identity`, `lifecycle`,
`holdout`, `detectors`, `liveness`, `sandbox`, and `executor`. Detector entries
carry an explicit `advisory | blocking` enforcement policy. Unknown or missing
fields, unsafe repository locations, mutable sandbox images, and legacy
`config.env` files are rejected. `tools/lfd_contract.py` is the only loader;
shell adapters receive a fixed NUL-delimited vocabulary and never source or
evaluate configuration.

## The poll flow (`ops/poll-and-score.sh <target-dir>`)

1. Skip unless `lifecycle.status` is `active`; skip past the run budget.
2. Bare-clone the target; list `holdout-check-*` tags oldest→newest.
3. Per tag: dedup against `log.jsonl` (JSON parse, not grep); rate-limit off
   the last row's timestamp.
4. Parse the tag message with `ops/log_utils.py parse-tag-msg` — every
   agent-supplied field becomes a validated float/enum or null. Nothing from
   the tag is ever interpolated into code.
5. Clone the **pinned SHA** (tags can't race).
6. **Liveness gate**, sandboxed: configured build → boot (backgrounded) →
   health-check commands. Failure ⇒ row with `holdout_score: 0`,
   `liveness: "liveness_failed"`; no eval cases run.
7. **Score** via `harness/score-holdout.sh` (contract below).
8. **Probe** per the contract cadence via `harness/probe-holdout.sh`.
9. Append ONE row via `ops/log_utils.py append` (the only log writer).
10. Divergence check over the same log; post commit status (score ± CI +
    divergence flag + boolean probe verdict — nothing else); write a
    `$GITHUB_STEP_SUMMARY` table row with full hub-side detail.

## Two-stage scoring contract

`harness/score-holdout.sh <checkout>` (hub-authored, per target):

- **Stage 1 — generate (sandboxed).** Run agent code only via
  `"$RUN_SANDBOXED" <checkout> <outdir> <timeout> <cmd...>`
  Active polling requires Docker and fails closed if it is unavailable.
  Direct test/development use may explicitly select `auto`, `sandbox-exec`, or
  the loudly unsandboxed `none` mode.
  The jail sees the checkout read-only and the output dir; it never sees
  `targets/`, holdout answers, canaries, or the network.
- **Stage 2 — compare (hub-side).** Read Stage-1 outputs, compare to
  `eval/holdout` answers, bootstrap the interval, emit one JSON line:
  `{"score": s, "ci_low": l, "ci_high": h}`.

`harness/probe-holdout.sh <checkout>` mutates holdout **inputs** with the
same operator table as the target's dev-side probe and emits
`{"operators": {"<op>": <0..1>, ...}}`. Per-operator detail never leaves the
hub; the agent sees only ok/below-floor.

## Activation gates (anti-Potemkin)

CI (`tools/ci_checks.py activation-gate`) and `bin/lfd status` refuse to let
a target run as `active` on a facade. An active target must clear
all three, each a place a Potemkin eval could otherwise slip through a gate
that merely *exists* but was silently skipped:

| Gate | Blocks activation when | Detector |
|---|---|---|
| **liveness** | no configured build/health command and no written exemption | `lfd_common.liveness_state` |
| **audit** | `audit-report.json` missing, not PASS, or its `harness_version` ≠ the current harness (audited-then-rewritten) | `lfd_common.audit_state` |
| **calibration** | `calibration-report.json` missing, malformed, or good/bad intervals overlap (scorer can't separate them) | `lfd_common.calibration_state` |

Non-active targets are shown these states but never blocked.

**Fixture targets**: an underscore-prefixed name (e.g. `_example`) marks a
demo/fixture target. It is never polled (`lifecycle.status: example`) and is exempt
from the append-only-log CI check, since its synthetic history is
regenerated by design. Real targets never start with `_`.

## log.jsonl row schema

Written exclusively by `ops/log_utils.py append`; append-only (CI-enforced).

```jsonc
{
  "cycle": 7,                       // row index, 1-based
  "tag": "holdout-check-7",
  "sha": "…",                       // pinned target SHA that was scored
  "timestamp": "2026-07-07T12:00:00Z",
  "holdout_score": 0.61, "holdout_ci": [0.57, 0.65],
  "dev_score": 0.66, "dev_ci": [0.63, 0.69],        // agent-reported, validated
  "liveness": "ok",                 // ok | liveness_failed | skipped
  "harness_version": "1f2e3d…",     // sha256 of targets/<n>/harness tree
  "hub_commit": "abc1234",          // hub commit that ran the scoring
  "scoring_seconds": 48,            // hub-measured
  "probe": {"operators": {"paraphrase": 0.92, "entity_swap": 0.61}},  // when run
  "coverage_variance": 0.34,        // optional anti-Potemkin fingerprint spread
  "model_id": "provider-model-v1",    // agent-reported, charset-validated
  "reported_tokens_in": 1.2e6, "reported_tokens_out": 4e5,
  "reported_cost_usd": 12.5, "reported_wall_clock": 3600
}
```

`reported_*` fields are agent-claimed (used for efficiency trends, flagged
as such); `holdout_*`, `liveness`, `probe`, `harness_version`,
`scoring_seconds` are hub-measured ground truth.

### coverage_variance (anti-lookup-table)

`ops/coverage_variance.py` is the code-shaped sibling of the
compressibility lint. A generated `score-holdout.sh` can import
`trace_lines` to fingerprint the code path each holdout case executes, then
emit `coverage_variance` (0 = every case ran the same lines → dispatcher
over a lookup table; 1 = diverse paths → genuine logic) in its JSON. The
poll passes it into the log row; `lfd status` flags any value below
`COVERAGE_VARIANCE_FLOOR` (default 0.2). Heuristic and advisory — a low
value is a "go look" signal for patch mode, never an automatic VOID.

## Canary lifecycle

1. Design mode builds `eval/holdout/` cases.
2. `bin/lfd canaries <target>` embeds `LFD-CANARY-{16hex}` in every stored
   answer and records the list in `canary-list.json`.
3. The target-side `lint.sh` (generated in design mode) greps working tree +
   git history for any canary — a hit is proof of eval access and VOIDs the
   score.
4. Eval reused or exposed → regenerate (canaries are per-run).

## Divergence detection

`tools/lfd_common.check_divergence`: over the last `DIVERGENCE_WINDOW_CYCLES`
rows, dev's lower CI bound rising while holdout is flat/falling (2%
tolerance). This is the canonical reward-over-optimization signature; it
flips the commit status to failure, badges the dashboard, and per `goal.md`
auto-triggers patch mode — routed to the strongest available model, never
the executor.
