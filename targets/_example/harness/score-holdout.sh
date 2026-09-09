#!/usr/bin/env bash
# Real two-stage scorer for the synthetic square-function fixture.
set -euo pipefail

TARGET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HUB_ROOT="${HUB_ROOT:-$(cd "$TARGET_DIR/../.." && pwd)}"
CHECKOUT="$(cd "${1:?usage: score-holdout.sh <checkout>}" && pwd)"
: "${RUN_SANDBOXED:?RUN_SANDBOXED must identify the trusted sandbox adapter}"

if [ ! -f "$CHECKOUT/solution.py" ]; then
  echo '{"status":"error","error":{"code":"capability_unavailable","message":"solution.py is missing"}}' >&2
  exit 2
fi

# capacity_caps and compressibility: bound code volume and compressed volume.
if [ "$(wc -l < "$CHECKOUT/solution.py")" -gt 200 ] ||
   [ "$(gzip -c "$CHECKOUT/solution.py" | wc -c | tr -d ' ')" -gt 4096 ]; then
  echo '{"status":"error","error":{"code":"constraint_violation","message":"structural capacity guard failed"}}' >&2
  exit 2
fi

# diff_scope: reject a broad most-recent checkpoint when Git history exists.
if git -C "$CHECKOUT" rev-parse --is-inside-work-tree >/dev/null 2>&1 &&
   [ "$(git -C "$CHECKOUT" diff-tree --no-commit-id --name-only -r HEAD | wc -l | tr -d ' ')" -gt 5 ]; then
  echo '{"status":"error","error":{"code":"constraint_violation","message":"diff scope guard failed"}}' >&2
  exit 2
fi

# canary_scan: exact contamination proof across the tree and reachable history.
while IFS= read -r canary; do
  if grep -R -F --exclude-dir=.git -- "$canary" "$CHECKOUT" >/dev/null 2>&1 ||
     { git -C "$CHECKOUT" rev-parse --is-inside-work-tree >/dev/null 2>&1 &&
       git -C "$CHECKOUT" log -p --all | grep -F -- "$canary" >/dev/null 2>&1; }; then
    echo '{"status":"error","error":{"code":"constraint_violation","message":"contamination guard failed"}}' >&2
    exit 2
  fi
done < <(python3 - "$TARGET_DIR/canary-list.json" <<'PY'
import json, sys
with open(sys.argv[1]) as stream:
    for item in json.load(stream)["canaries"]:
        print(item["canary"])
PY
)

# ngram_overlap: fuzzy contamination tier, with the fixture policy explicit.
if ! python3 "$HUB_ROOT/skills/lfd-shared/scripts/ngram-overlap.py" \
    --solution-dir "$CHECKOUT" --eval-answers-dir "$TARGET_DIR/eval/holdout" \
    --n 8 --threshold 0.4 >/dev/null; then
  echo '{"status":"error","error":{"code":"constraint_violation","message":"overlap guard failed"}}' >&2
  exit 2
fi

OWN_OUTPUT=0
if [ -n "${STAGE1_OUT:-}" ]; then
  OUTPUT="$STAGE1_OUT"
  mkdir -p "$OUTPUT"
else
  OUTPUT=$(mktemp -d)
  OWN_OUTPUT=1
fi
cleanup() {
  if [ "$OWN_OUTPUT" -eq 1 ]; then
    rm -rf "$OUTPUT"
  fi
}
trap cleanup EXIT

# Stage 1: copy inputs without answers into the output exchange, then run only
# target code through the configured sandbox. Hidden answers never enter it.
python3 - "$TARGET_DIR/eval/holdout" "$OUTPUT/inputs.json" <<'PY'
import glob, json, sys
cases = []
for path in sorted(glob.glob(sys.argv[1] + "/*.json")):
    with open(path) as stream:
        item = json.load(stream)
    cases.append({"id": item["id"], "input": item["input"]})
with open(sys.argv[2], "w") as stream:
    json.dump(cases, stream)
PY
"$RUN_SANDBOXED" "$CHECKOUT" "$OUTPUT" 30 python3 solution.py --batch

# Stage 2: trusted comparison reads predictions and private answers hub-side.
python3 - "$TARGET_DIR/eval/holdout" "$OUTPUT/predictions.json" <<'PY'
import glob, json, sys
expected = {}
for path in sorted(glob.glob(sys.argv[1] + "/*.json")):
    with open(path) as stream:
        item = json.load(stream)
    expected[item["id"]] = item["answer"]
try:
    with open(sys.argv[2]) as stream:
        predictions = json.load(stream)
    if (not isinstance(predictions, list)
            or any(not isinstance(item, dict) or set(item) != {"id", "answer"}
                   for item in predictions)):
        raise TypeError("predictions must contain only id and answer")
    actual = {item["id"]: item["answer"] for item in predictions}
    if len(actual) != len(predictions) or set(actual) != set(expected):
        raise ValueError("prediction identities must exactly match the cases")
except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
    actual = {}
scores = [1.0 if actual.get(case_id) == answer else 0.0
          for case_id, answer in expected.items()]
score = sum(scores) / len(scores) if scores else 0.0
# This deliberately tiny fixture reports the observed case range. Real target
# designs use a powered holdout and the interval method named in their goal.
ci_low = min(scores) if scores else 0.0
ci_high = max(scores) if scores else 0.0
print(json.dumps({"score": score, "ci_low": ci_low, "ci_high": ci_high},
                 sort_keys=True))
PY
