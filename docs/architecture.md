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
repositories and interact with the private hub through immutable annotated
`<prefix>v1-<sha12>-<request-id>` tags (requests) and the exact
`lfd/holdout` commit-status context (responses).

The public project and each private operational hub are separate security
domains. A private hub may consume reviewed framework changes from public
source, but private target commits must never flow back into public history.

## Registry schema — `targets/<name>/`

| Path | Committed? | Purpose |
|---|---|---|
| `target.json` | yes | strictly validated operational contract; see fields below |
| `target-profile.json` | yes | sanitized inspection evidence: source SHA, languages, build files, and agent instructions |
| `eval/dev/` | yes | dev suite copied only through the verified bundle |
| `eval/holdout/` | yes | holdout cases with embedded canaries — **never leaves the hub** |
| `dev-harness/score-dev.sh` | yes | agent-visible scorer; owns lint plus scoring exactly once |
| `canary-list.json` | yes | per-run canary registry (proof-of-access detection) |
| `harness/score-holdout.sh` | yes | per-target scorer; two-stage contract |
| `harness/probe-holdout.sh` | yes | per-target holdout mutation probe |
| `log.jsonl` | yes | append-only scoring history; single source of truth |
| `audit-mechanical.json` | yes | Deterministic audit evidence; a PASS remains incomplete |
| `audit-report.json` | yes | Final audit judgment plus six freshness hashes; required before activation |
| `activation.json` | yes | Hub-issued receipt binding active `target.json` to its final audit |
| `calibration-report.json` | yes | Phase 6 known-good/known-bad scores + intervals; the two must not overlap; required before active status |
| `retros/` | yes | post-run retrospectives (`bin/lfd retro`) |
| `runs/` | **no** (gitignored) | captured Stage-1 outputs per tag, for `bin/lfd review` |
| `goal.md` | yes | the emitted optimization target (copied to the target repo at launch) |
| `bundle/` | yes | generated agent-visible tree with `.lfd/bundle-manifest.json` hashes |

The bundle generator has an exact source allowlist: `goal.md`, `eval/dev/`,
`dev-harness/`, the target-repository templates, and only `lfd-execute`. It rejects private-shaped
paths before generation and verifies every installed managed file by SHA-256.
Equip refuses to overwrite a caller-owned or locally modified file. Managed
Codex, Claude, Cursor, and Copilot blocks preserve everything outside their
markers.

## Agent skill boundaries

| Skill | Surface | Responsibility |
|---|---|---|
| `lfd-onboard` | private hub | register, inspect, equip, verify, and derive lifecycle state |
| `lfd-design` | private hub | build the powered eval, loss, scorers, calibration, and bundle |
| `lfd-audit` | fresh private context | mechanical pass plus five explicit independent findings |
| `lfd-patch` | private hub | repair the loss after a detected exploit or stale evidence |
| `lfd-execute` | target repository | run visible scoring and stable request/status commands only |

Calculators and scientific references live in `skills/lfd-shared/`, which has
no `SKILL.md` and cannot be invoked. Skills wrap existing CLI interfaces; they
do not reimplement scoring, Git request transport, or status discovery.

### `target.json` fields

The versioned contract groups operational values under `identity`, `lifecycle`,
`holdout`, `detectors`, `liveness`, `sandbox`, and `executor`. Detector entries
carry an explicit `advisory | blocking` enforcement policy. Unknown or missing
fields, unsafe repository locations, mutable sandbox images, and legacy
`config.env` files are rejected. `tools/lfd_contract.py` is the only loader;
shell adapters receive a fixed NUL-delimited vocabulary and never source or
evaluate configuration. `holdout.protocol_version` is required and must name an
implemented protocol.

The agent-facing command contract is a version-1 JSON envelope containing
`command`, `target`, `status`, `stage`, `artifacts`, `errors`, and
`next_actions`. Exit statuses are `0` success, `2` invalid input/contract,
`3` pending judgment or external result, and `4` infrastructure/transport
failure.

## The poll flow (`ops/poll-and-score.sh <target-dir>`)

1. Skip unless `lifecycle.status` is `active`; skip past the run budget.
2. Bare-clone the target; list tags for the configured protocol version oldest→newest.
3. Per tag: require an annotated object; validate tag, payload, full SHA, and
   request ID; deduplicate request ID + SHA against `log.jsonl`; rate-limit off
   the last row's timestamp.
4. Parse the validated request with `ops/log_utils.py parse-request` — every
   agent-supplied field becomes a validated float/enum or null. Nothing from
   the request is ever interpolated into code.
5. Clone the **pinned SHA** (tags can't race).
6. **Liveness gate**, sandboxed: configured build → boot (backgrounded) →
   health-check commands. Failure ⇒ row with `holdout_score: 0`,
   `liveness: "liveness_failed"`; no eval cases run.
7. **Score** via `harness/score-holdout.sh` (contract below).
8. **Probe** per the contract cadence via `harness/probe-holdout.sh`.
9. Append ONE row via `ops/log_utils.py append` (the only log writer).
10. Divergence check over the same log; post commit status (score ± CI +
    divergence flag + boolean probe and coverage-variance verdicts — nothing
    else); write a
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
a target run as `active` on a facade. `bin/lfd activate` is the sole supported
active transition and issues a receipt only after the prerequisites pass.
Runtime revalidates the same evidence before target code executes:

| Gate | Blocks activation when | Detector |
|---|---|---|
| **liveness** | no configured build/health command and no written exemption | `lfd_common.liveness_state` |
| **audit** | mechanical-only, missing/failed judgment, or any of six evidence hashes is stale | `lfd_common.audit_state` |
| **calibration** | `calibration-report.json` missing, malformed, or good/bad intervals overlap (scorer can't separate them) | `lfd_common.calibration_state` |
| **activation** | receipt missing or no longer matches the active contract and final audit | `lfd_common.activation_receipt_state` |

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
  "tag": "holdout-check-v1-a1b2c3d4e5f6-0123456789abcdef0123456789abcdef",
  "request_id": "0123456789abcdef0123456789abcdef",
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
poll passes it into the log row; `lfd status` flags any value below the
configured `detectors.coverage_variance.floor`. Its configured
`advisory | blocking` policy decides whether a low value is an informative
flag or a failing bounded status; the detector mathematics do not change.

## Canary lifecycle

1. Design mode builds `eval/holdout/` cases.
2. `bin/lfd canaries <target>` embeds `LFD-CANARY-{16hex}` in every stored
   answer and records the list in `canary-list.json`.
3. The target-visible development scorer and private scorer scan the working
   tree and reachable Git history for any canary — a hit is proof of eval
   access and rejects scoring.
4. Eval reused or exposed → regenerate (canaries are per-run).

## Divergence detection

`tools/lfd_common.check_divergence`: over the last `DIVERGENCE_WINDOW_CYCLES`
rows, dev's lower CI bound rising while holdout is flat/falling (2%
tolerance). This is one reward-over-optimization signal, not a universal
proof. Scout badges it and recommends the hub-side patch workflow. Its
configured `advisory | blocking` policy determines whether the bounded commit
status also fails; patch authority never belongs to the target-side executor.
