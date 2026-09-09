#!/usr/bin/env bash
# Named mutation probes for the synthetic integer-square target.
set -euo pipefail

CHECKOUT="$(cd "${1:?usage: probe-holdout.sh <checkout>}" && pwd)"
: "${RUN_SANDBOXED:?RUN_SANDBOXED must identify the trusted sandbox adapter}"
OUTPUT=$(mktemp -d)
trap 'rm -rf "$OUTPUT"' EXIT

# sign_flip: negate a positive integer; boundary_zero: evaluate the identity boundary.
cat > "$OUTPUT/inputs.json" <<'JSON'
[{"id":"sign_flip","input":{"value":-3}},
 {"id":"boundary_zero","input":{"value":0}}]
JSON
"$RUN_SANDBOXED" "$CHECKOUT" "$OUTPUT" 30 python3 solution.py --batch
python3 - "$OUTPUT/predictions.json" <<'PY'
import json, sys
try:
    with open(sys.argv[1]) as stream:
        values = {item["id"]: item["answer"] for item in json.load(stream)}
except (OSError, json.JSONDecodeError, KeyError, TypeError):
    values = {}
print(json.dumps({"operators": {
    "sign_flip": 1.0 if values.get("sign_flip") == 9 else 0.0,
    "boundary_zero": 1.0 if values.get("boundary_zero") == 0 else 0.0,
}}, sort_keys=True))
PY
