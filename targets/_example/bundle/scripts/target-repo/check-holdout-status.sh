#!/usr/bin/env bash
# check-holdout-status.sh — poll for a result on a previously requested
# holdout check. Non-blocking: returns "pending" if the poll hasn't fired
# yet. Deterministic; safe to call repeatedly.
#
# Usage: ./check-holdout-status.sh <tag-name>

set -euo pipefail

TAG="${1:?Usage: $0 <tag-name>}"
SHA=$(git rev-list -n 1 "$TAG" 2>/dev/null) || { echo '{"status":"error","message":"tag not found locally — git fetch --tags"}'; exit 1; }

REPO_SLUG=$(git remote get-url origin | sed -E 's#.*[:/]([^/]+/[^/]+)(\.git)?$#\1#; s#\.git$##')
: "${GITHUB_API_URL:?GITHUB_API_URL must be configured (for github.com: https://api.github.com)}"
API_URL="${GITHUB_API_URL%/}"

RESULT=$(curl --fail-with-body --silent --show-error \
  "${API_URL}/repos/${REPO_SLUG}/commits/${SHA}/status")
STATE=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('state','pending'))" 2>/dev/null || echo "pending")

if [ "$STATE" = "pending" ]; then
  echo '{"status": "pending"}'
else
  DESC=$(echo "$RESULT" | python3 -c "
import json,sys
d = json.load(sys.stdin)
statuses = [s for s in d.get('statuses', []) if s.get('context') == 'lfd/holdout']
print(statuses[0]['description'] if statuses else 'no lfd/holdout status yet')
")
  echo "{\"status\": \"${STATE}\", \"description\": \"${DESC}\"}"
fi
