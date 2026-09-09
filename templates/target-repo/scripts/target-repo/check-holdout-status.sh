#!/usr/bin/env bash
# Read only Scout's exact commit-status context for one holdout request.
set -euo pipefail

TAG="${1:?Usage: $0 <request-tag>}"
emit_error() {
  python3 - "$1" "$2" <<'PY'
import json, sys
print(json.dumps({"schema_version": 1, "command": "holdout.status",
                  "target": None, "status": "error", "stage": None,
                  "artifacts": [], "errors": [{"code": sys.argv[1],
                  "message": sys.argv[2]}], "next_actions": []}, sort_keys=True))
PY
}

if ! SHA=$(git rev-parse "${TAG}^{commit}" 2>/dev/null); then
  emit_error "request_not_found" "request tag is not available locally; fetch tags first"
  exit 2
fi
if ! REPO_URL=$(git remote get-url origin 2>/dev/null); then
  emit_error "missing_remote" "origin remote is required"
  exit 2
fi
REPO_SLUG=$(printf '%s' "$REPO_URL" | sed -E 's#.*[:/]([^/]+/[^/]+)(\.git)?$#\1#; s#\.git$##')
if [ -z "${GITHUB_API_URL:-}" ]; then
  emit_error "missing_api_url" "GITHUB_API_URL must be configured"
  exit 4
fi
TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
if [ -z "$TOKEN" ]; then
  emit_error "missing_credentials" "GH_TOKEN or GITHUB_TOKEN is required for holdout status"
  exit 4
fi
API_URL="${GITHUB_API_URL%/}"

if ! RESULT=$(curl --fail-with-body --silent --show-error \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    "${API_URL}/repos/${REPO_SLUG}/commits/${SHA}/statuses"); then
  emit_error "transport_failure" "GitHub commit-status request failed"
  exit 4
fi

STATUS_RESPONSE="$RESULT" python3 - "$SHA" "$TAG" <<'PY'
import json, os, sys

sha, tag = sys.argv[1:]
try:
    statuses = json.loads(os.environ["STATUS_RESPONSE"])
except json.JSONDecodeError:
    statuses = None
if not isinstance(statuses, list):
    document = {"schema_version": 1, "command": "holdout.status", "target": sha,
                "status": "error", "stage": None, "artifacts": [],
                "errors": [{"code": "invalid_response",
                            "message": "GitHub statuses response was not an array"}],
                "next_actions": []}
    print(json.dumps(document, sort_keys=True))
    raise SystemExit(4)
match = next((item for item in statuses
              if isinstance(item, dict) and item.get("context") == "lfd/holdout"), None)
if match is None:
    status, artifacts, actions, code = "pending", [{"tag": tag, "sha": sha}], ["check again later"], 3
else:
    state = match.get("state")
    status = state if state in {"success", "failure", "error"} else "pending"
    artifacts = [{"tag": tag, "sha": sha,
                  "description": str(match.get("description") or "")[:140]}]
    actions = ["check again later"] if status == "pending" else []
    code = 3 if status == "pending" else 0
document = {"schema_version": 1, "command": "holdout.status", "target": sha,
            "status": status, "stage": "result" if match else "waiting",
            "artifacts": artifacts, "errors": [], "next_actions": actions}
print(json.dumps(document, sort_keys=True))
raise SystemExit(code)
PY
