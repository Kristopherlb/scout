#!/usr/bin/env bash
# generate-canaries.sh — embed a unique canary string in every holdout item.
# Cryptographically random. Re-run whenever the eval is rotated (canaries are per-run,
# per SKILL.md Phase 3 — never reuse across runs).
#
# Usage: ./generate-canaries.sh <target-dir>      (e.g. targets/myrepo)

set -euo pipefail

TARGET_DIR="${1:?Usage: $0 <target-dir>}"
cd "$TARGET_DIR"

RUN_ID="run-$(date +%Y%m%d-%H%M%S)"
HOLDOUT_DIR="eval/holdout"

if [ ! -d "$HOLDOUT_DIR" ]; then
  echo "ERROR: ${TARGET_DIR}/${HOLDOUT_DIR} not found. Run design mode first." >&2
  exit 1
fi

python3 - "$RUN_ID" "$HOLDOUT_DIR" <<'PYEOF'
import json, os, secrets, sys

run_id, holdout_dir = sys.argv[1], sys.argv[2]
canaries = []

for fname in sorted(os.listdir(holdout_dir)):
    path = os.path.join(holdout_dir, fname)
    if not fname.endswith(".json") or not os.path.isfile(path):
        continue
    canary = f"LFD-CANARY-{secrets.token_hex(8)}"
    with open(path) as f:
        item = json.load(f)
    item["_canary"] = canary  # embedded in the stored answer, never in inputs
    with open(path, "w") as f:
        json.dump(item, f, indent=2)
    canaries.append({"file": fname, "canary": canary})

with open("canary-list.json", "w") as f:
    json.dump({"run_id": run_id, "canaries": canaries}, f, indent=2)

print(f"Embedded {len(canaries)} canaries for {run_id}")
PYEOF

echo "canary-list.json updated. Keep this file OUTSIDE target-repo — it never gets pushed there."
