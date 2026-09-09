#!/usr/bin/env bash
# Visible scorer for the synthetic square-function target.
set -euo pipefail

TARGET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECKOUT="${1:-$PWD}"
SOLUTION="$CHECKOUT/solution.py"

if [ ! -f "$SOLUTION" ]; then
  echo '{"status":"error","error":{"code":"capability_unavailable","message":"solution.py is missing"}}' >&2
  exit 2
fi

# capacity_caps: this fixture's implementation must stay compact.
if [ "$(wc -l < "$SOLUTION")" -gt 200 ]; then
  echo '{"status":"error","error":{"code":"constraint_violation","message":"capacity cap exceeded"}}' >&2
  exit 2
fi

# diff_scope: when the checkout has Git history, refuse a broad latest commit.
if git -C "$CHECKOUT" rev-parse --is-inside-work-tree >/dev/null 2>&1 &&
   [ "$(git -C "$CHECKOUT" diff-tree --no-commit-id --name-only -r HEAD | wc -l | tr -d ' ')" -gt 5 ]; then
  echo '{"status":"error","error":{"code":"constraint_violation","message":"diff scope exceeded"}}' >&2
  exit 2
fi

python3 - "$SOLUTION" "$TARGET_DIR/eval/dev" <<'PY'
import glob, json, subprocess, sys

solution, eval_dir = sys.argv[1:]
cases = []
for path in sorted(glob.glob(eval_dir + "/*.json")):
    with open(path) as stream:
        cases.append(json.load(stream))
correct = 0
for case in cases:
    result = subprocess.run([sys.executable, solution],
                            input=json.dumps(case["input"]), text=True,
                            capture_output=True, timeout=10)
    if result.returncode != 0:
        continue
    try:
        response = json.loads(result.stdout)
        if not isinstance(response, dict) or set(response) != {"answer"}:
            continue
        prediction = response["answer"]
    except (json.JSONDecodeError, KeyError, TypeError):
        continue
    correct += prediction == case["answer"]
score = correct / len(cases) if cases else 0.0
print(json.dumps({"score": score, "ci_low": score, "ci_high": score,
                  "void": False}, sort_keys=True))
PY
