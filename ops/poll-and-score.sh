#!/usr/bin/env bash
# poll-and-score.sh — the hub's scheduled scoring job for ONE target.
# Fully deterministic, no agent/LLM call anywhere in this script.
# Pull-based: the hub always initiates contact, never receives requests.
#
# Usage: poll-and-score.sh <target-dir>          (e.g. targets/myrepo)
#
# Per new holdout-check tag on the target repo:
#   1. skip if already scored (tag dedup off log.jsonl — the one source of truth)
#   2. rate-limit off the last row's timestamp (MIN_HOURS_BETWEEN_HOLDOUT)
#   3. pull the exact tagged SHA into an isolated checkout
#   4. liveness gate (BUILD_CMD/BOOT_CMD/HEALTH_CHECK) inside the sandbox —
#      vaporware scores 0 with reason before a single eval case runs
#   5. score via the target's harness/score-holdout.sh (two-stage: agent code
#      runs sandboxed with no network and no view of holdout answers;
#      comparison happens hub-side)
#   6. optionally probe (holdout mutation testing) per PROBE_ON_HOLDOUT
#   7. append ONE validated row to log.jsonl (ops/log_utils.py — the only
#      writer; every agent-supplied value is type-validated, never eval'd)
#   8. divergence check off the same log
#   9. post score + interval + flags back as a commit status — and NOTHING
#      else: no per-case detail, no eval content, no operator names

set -euo pipefail

HUB_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="$(cd "${1:?Usage: $0 <target-dir>}" && pwd)"
TARGET_NAME="$(basename "$TARGET_DIR")"
LOG="$TARGET_DIR/log.jsonl"
LOG_UTILS="$HUB_ROOT/ops/log_utils.py"
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/null}"
WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT

# The Python contract module validates the document once and emits a fixed,
# NUL-delimited adapter vocabulary. Values are data; this script never sources
# or evaluates target configuration.
CONTRACT_DATA="$WORKDIR/contract.bin"
if ! python3 "$HUB_ROOT/tools/lfd_contract.py" shell \
    --target-dir "$TARGET_DIR" > "$CONTRACT_DATA"; then
  exit 2
fi
while IFS= read -r -d '' NAME && IFS= read -r -d '' VALUE; do
  printf -v "$NAME" '%s' "$VALUE"
  export "${NAME?}"
done < "$CONTRACT_DATA"

if [ "$STATUS" != "active" ]; then
  echo "[$TARGET_NAME] STATUS=$STATUS — skipping (only 'active' targets are polled)"
  exit 0
fi
if [ "$LFD_SANDBOX" != "docker" ]; then
  echo "[$TARGET_NAME] ERROR: active targets require LFD_SANDBOX=docker" >&2
  exit 2
fi

# CI is not the runtime trust boundary: re-enforce the activation gates before
# executing any target code in case a private operator bypassed branch checks.
python3 "$HUB_ROOT/tools/ci_checks.py" activation-gate --hub-root "$HUB_ROOT"

ROW_COUNT=$(python3 "$LOG_UTILS" count --log "$LOG")
if [ "$ROW_COUNT" -ge "$BUDGET_MAX_HOLDOUT_RUNS" ]; then
  echo "[$TARGET_NAME] WARNING: budget cap reached (${ROW_COUNT}/${BUDGET_MAX_HOLDOUT_RUNS} holdout runs) — skipping"
  exit 0
fi

POLL_START=$SECONDS

git clone --quiet --bare "$TARGET_REPO_URL" "$WORKDIR/target.git"

# Oldest first: preserve cycle ordering in the log.
NEW_TAGS=$(git -C "$WORKDIR/target.git" tag -l "${HOLDOUT_TAG_PREFIX}*" --sort=creatordate)
HUB_COMMIT=$(git -C "$HUB_ROOT" rev-parse --short HEAD)

for TAG in $NEW_TAGS; do
  if [ "$(python3 "$LOG_UTILS" has-tag --log "$LOG" --tag "$TAG")" = "true" ]; then
    continue  # idempotent — already scored this tag
  fi

  # --- rate limit: hours since last scored row, off log.jsonl only ---
  HOURS_SINCE=$(python3 "$LOG_UTILS" hours-since --log "$LOG")
  if python3 -c "import sys; sys.exit(0 if float(sys.argv[1]) < float(sys.argv[2]) else 1)" \
       "$HOURS_SINCE" "$MIN_HOURS_BETWEEN_HOLDOUT"; then
    echo "[$TARGET_NAME] rate limit: ${TAG} too soon (last check ${HOURS_SINCE}h ago < ${MIN_HOURS_BETWEEN_HOLDOUT}h) — will retry next poll"
    break  # tags are ordered oldest→newest; later ones are even newer
  fi

  # --- agent-supplied tag message: validated as DATA, never interpolated ---
  SHA=$(git -C "$WORKDIR/target.git" rev-list -n 1 "$TAG")
  AGENT_FIELDS=$(git -C "$WORKDIR/target.git" tag -l --format='%(contents)' "$TAG" \
    | python3 "$LOG_UTILS" parse-tag-msg)

  # --- pull exact tagged SHA (no "latest HEAD" race — tag is pinned) ---
  CHECKOUT="$WORKDIR/checkout-${SHA}"
  git clone --quiet "$WORKDIR/target.git" "$CHECKOUT"
  git -C "$CHECKOUT" checkout --quiet "$SHA"
  STAGE1_OUT="$WORKDIR/stage1-out-${SHA}"
  mkdir -p "$STAGE1_OUT"

  export RUN_SANDBOXED="$HUB_ROOT/ops/run-sandboxed.sh"
  export HUB_ROOT TARGET_DIR STAGE1_OUT
  export LFD_SANDBOX SANDBOX_IMAGE SANDBOX_CPUS SANDBOX_MEMORY SANDBOX_PIDS_LIMIT

  # --- liveness gate: fresh checkout must build/boot/respond, sandboxed ---
  LIVENESS="ok"
  if [ -n "${BUILD_CMD:-}" ] || [ -n "${HEALTH_CHECK:-}" ]; then
    LIVENESS_CMDS="set -e"
    [ -n "${BUILD_CMD:-}" ]    && LIVENESS_CMDS="$LIVENESS_CMDS
$BUILD_CMD"
    [ -n "${BOOT_CMD:-}" ]     && LIVENESS_CMDS="$LIVENESS_CMDS
( $BOOT_CMD ) & sleep 5"
    [ -n "${HEALTH_CHECK:-}" ] && LIVENESS_CMDS="$LIVENESS_CMDS
$HEALTH_CHECK"
    LIVENESS_ERROR="$WORKDIR/liveness-${SHA}.stderr"
    set +e
    "$RUN_SANDBOXED" "$CHECKOUT" "$STAGE1_OUT" "$LIVENESS_TIMEOUT" \
      bash -c "$LIVENESS_CMDS" >/dev/null 2>"$LIVENESS_ERROR"
    LIVENESS_EXIT=$?
    set -e
    if [ "$LIVENESS_EXIT" -eq 125 ]; then
      cat "$LIVENESS_ERROR" >&2
      echo "[$TARGET_NAME] ERROR: sandbox infrastructure failed during liveness" >&2
      exit 2
    elif [ "$LIVENESS_EXIT" -ne 0 ]; then
      LIVENESS="liveness_failed"
    fi
  fi

  PROBE_JSON=""; COVERAGE_VARIANCE=""
  if [ "$LIVENESS" = "liveness_failed" ]; then
    HOLDOUT_SCORE="0"; CI_LOW="0"; CI_HIGH="0"; SCORING_SECONDS="0"
    echo "[$TARGET_NAME] ${TAG}: LIVENESS FAILED — scored 0 (vaporware gate)"
  else
    # --- score: harness contract returns {"score","ci_low","ci_high"};
    #     an optional "coverage_variance" field feeds the lookup-table lint ---
    T0=$SECONDS
    RESULT=$("$TARGET_DIR/harness/score-holdout.sh" "$CHECKOUT")
    SCORING_SECONDS=$((SECONDS - T0))
    read -r HOLDOUT_SCORE CI_LOW CI_HIGH < <(echo "$RESULT" | python3 -c "
import json,sys
r = json.load(sys.stdin)
print(r['score'], r['ci_low'], r['ci_high'])")
    COVERAGE_VARIANCE=$(echo "$RESULT" | python3 -c "
import json,sys
v = json.load(sys.stdin).get('coverage_variance')
print('' if v is None else v)")

    # --- hub-side holdout mutation probe, per configured cadence ---
    RUN_PROBE="false"
    case "$PROBE_ON_HOLDOUT" in
      always) RUN_PROBE="true" ;;
      every-k)
        SINCE=$(python3 "$LOG_UTILS" rows-since-probe --log "$LOG")
        [ "$SINCE" -ge "$PROBE_EVERY_K" ] && RUN_PROBE="true" ;;
      on-divergence)
        [ "$(python3 "$HUB_ROOT/ops/check-divergence.py" --log "$LOG" --window "$DIVERGENCE_WINDOW_CYCLES")" = "true" ] \
          && RUN_PROBE="true" ;;
    esac
    if [ "$RUN_PROBE" = "true" ] && [ -x "$TARGET_DIR/harness/probe-holdout.sh" ]; then
      PROBE_JSON=$("$TARGET_DIR/harness/probe-holdout.sh" "$CHECKOUT")
    fi
  fi

  # --- persist Stage-1 outputs hub-side for `lfd review` (untracked) ---
  if [ -d "$STAGE1_OUT" ] && [ -n "$(ls -A "$STAGE1_OUT" 2>/dev/null)" ]; then
    mkdir -p "$TARGET_DIR/runs"
    rm -rf "$TARGET_DIR/runs/$TAG"
    cp -R "$STAGE1_OUT" "$TARGET_DIR/runs/$TAG"
  fi

  # --- one validated row, one file, source of truth for everything ---
  CYCLE=$(python3 "$LOG_UTILS" append \
    --log "$LOG" --target-dir "$TARGET_DIR" \
    --tag "$TAG" --sha "$SHA" \
    --holdout-score "$HOLDOUT_SCORE" --ci-low "$CI_LOW" --ci-high "$CI_HIGH" \
    --liveness "$LIVENESS" --hub-commit "$HUB_COMMIT" \
    --scoring-seconds "$SCORING_SECONDS" \
    --agent-fields "$AGENT_FIELDS" --probe-json "$PROBE_JSON" \
    --coverage-variance "$COVERAGE_VARIANCE")

  # --- divergence + probe verdict off the same log ---
  DIVERGENCE=$(python3 "$HUB_ROOT/ops/check-divergence.py" --log "$LOG" --window "$DIVERGENCE_WINDOW_CYCLES")
  PROBE_VERDICT=""
  if [ -n "$PROBE_JSON" ]; then
    PROBE_VERDICT=$(echo "$PROBE_JSON" | PYTHONPATH="$HUB_ROOT/tools" python3 -c "
import json, sys
import lfd_common
row = {'probe': json.load(sys.stdin)}
print('below-floor' if lfd_common.probe_floor_breaches(row, float(sys.argv[1])) else 'ok')" \
      "$PROBE_FLOOR")
  fi

  # --- egress: score + CI + flags only; operator detail stays hub-side ---
  "$HUB_ROOT/ops/post-status.sh" "$TARGET_REPO_URL" "$SHA" \
    "$HOLDOUT_SCORE" "$CI_LOW" "$CI_HIGH" "$DIVERGENCE" "$PROBE_VERDICT"

  # --- human-facing job summary (full detail is fine here — hub-side) ---
  if [ "$SUMMARY" != "/dev/null" ] && ! grep -q "| target |" "$SUMMARY" 2>/dev/null; then
    printf "| target | cycle | tag | sha | liveness | holdout ± CI | divergence | probe |\n|---|---|---|---|---|---|---|---|\n" >> "$SUMMARY"
  fi
  printf "| %s | %s | %s | %s | %s | %s [%s, %s] | %s | %s |\n" \
    "$TARGET_NAME" "$CYCLE" "$TAG" "${SHA:0:8}" "$LIVENESS" \
    "$HOLDOUT_SCORE" "$CI_LOW" "$CI_HIGH" "$DIVERGENCE" "${PROBE_JSON:-—}" >> "$SUMMARY"

  echo "[$TARGET_NAME] scored ${TAG}: holdout=${HOLDOUT_SCORE} [${CI_LOW},${CI_HIGH}] liveness=${LIVENESS} divergence=${DIVERGENCE}${PROBE_VERDICT:+ probe=$PROBE_VERDICT}"
done

# --- poll duration, so a slowly-degrading scorer shows as a trend ---
POLL_ELAPSED=$((SECONDS - POLL_START))
if [ "$SUMMARY" != "/dev/null" ]; then
  printf "\n_%s poll: %ss elapsed_\n" "$TARGET_NAME" "$POLL_ELAPSED" >> "$SUMMARY"
fi
echo "[$TARGET_NAME] poll complete in ${POLL_ELAPSED}s"
