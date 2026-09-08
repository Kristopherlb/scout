#!/usr/bin/env bash
# request-holdout-check.sh — the agent's ONLY interaction with the holdout
# boundary. Pushes an annotated tag carrying the current dev score plus
# run economics. Does NOT block, does NOT contact the eval hub directly —
# the hub's poll picks it up. Deterministic; the agent supplies the
# numbers, everything else is mechanical. All values are validated as
# plain numbers hub-side — anything non-numeric is dropped, so there is
# no point crafting anything else.
#
# Usage: ./request-holdout-check.sh <dev_score> <dev_ci_low> <dev_ci_high> \
#          [model_id] [tokens_in] [tokens_out] [cost_usd] [wall_clock_secs]

set -euo pipefail

DEV_SCORE="${1:?Usage: $0 <dev_score> <dev_ci_low> <dev_ci_high> [model_id] [tokens_in] [tokens_out] [cost_usd] [wall_clock_secs]}"
DEV_CI_LOW="${2:?missing dev_ci_low}"
DEV_CI_HIGH="${3:?missing dev_ci_high}"
MODEL_ID="${4:-}"
TOKENS_IN="${5:-}"
TOKENS_OUT="${6:-}"
COST_USD="${7:-}"
WALL_CLOCK="${8:-}"

CYCLE_FILE=".holdout-cycle-count"
N=$(( $(cat "$CYCLE_FILE" 2>/dev/null || echo 0) + 1 ))
echo "$N" > "$CYCLE_FILE"

TAG="holdout-check-${N}"
MSG=$(python3 - "$DEV_SCORE" "$DEV_CI_LOW" "$DEV_CI_HIGH" "$MODEL_ID" \
      "$TOKENS_IN" "$TOKENS_OUT" "$COST_USD" "$WALL_CLOCK" <<'PYEOF'
import json, sys

def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None

a = sys.argv
msg = {
    "dev_score": num(a[1]),
    "dev_ci": [num(a[2]), num(a[3])],
}
if a[4]:
    msg["model_id"] = a[4]
for key, val in (("reported_tokens_in", a[5]), ("reported_tokens_out", a[6]),
                 ("reported_cost_usd", a[7]), ("reported_wall_clock", a[8])):
    if num(val) is not None:
        msg[key] = num(val)
print(json.dumps(msg))
PYEOF
)

git tag -a "$TAG" -m "$MSG"
TARGET=$(git rev-list -n 1 "$TAG")

# Preferred transport: push the annotated tag directly. In hosted coding
# environments that reject refs/tags/*, fall back to the Actions transport:
# record the request in .github/holdout-requests.jsonl and push the current
# branch. The target repository's workflow then materializes the identical tag
# using its own GITHUB_TOKEN. Only the transport changes.
REQ=".github/holdout-requests.jsonl"

if git push origin "refs/tags/${TAG}" 2>/tmp/holdout-tag-push.err; then
  echo "Requested holdout check: ${TAG} (direct tag push)."
else
  echo "Direct tag push rejected (session proxy blocks refs/tags/*); using Actions transport." >&2
  sed 's/^/  proxy: /' /tmp/holdout-tag-push.err >&2 || true

  mkdir -p "$(dirname "$REQ")"
  python3 - "$TAG" "$TARGET" "$MSG" >> "$REQ" <<'PYEOF'
import json, sys
tag, target, msg = sys.argv[1], sys.argv[2], sys.argv[3]
print(json.dumps({"tag": tag, "target": target, "message": msg}))
PYEOF

  git add "$REQ"
  git commit -m "holdout request: ${TAG}" >/dev/null
  git push -u origin HEAD
  echo "Requested holdout check: ${TAG} via Actions transport (target ${TARGET})."
  echo "The holdout-request-tag workflow will create the tag on this push."
fi

echo "Result will appear as a commit status on ${TARGET} within one poll interval."
echo "Check with: scripts/target-repo/check-holdout-status.sh ${TAG}"
