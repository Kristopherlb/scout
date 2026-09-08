#!/usr/bin/env bash
# post-status.sh — post score+interval+divergence back to target-repo as a
# commit status. This is the ONLY write eval-repo ever makes to target-repo.
# Deterministic. No eval content, no per-case detail, no verbose output —
# just the four numbers and a flag.
#
# Usage: post-status.sh <target-repo-url> <sha> <score> <ci_low> <ci_high> <divergence> [probe_verdict]
#   probe_verdict: "" (no probe run) | "ok" | "below-floor" — a boolean
#   verdict only; per-operator detail never leaves the hub (naming the weak
#   operator would hand the agent a which-axis-to-patch oracle).

set -euo pipefail

REPO_URL="$1"; SHA="$2"; SCORE="$3"; CI_LOW="$4"; CI_HIGH="$5"; DIVERGENCE="$6"
PROBE_VERDICT="${7:-}"

# Parse org/repo from the URL for the GitHub API call.
REPO_SLUG=$(echo "$REPO_URL" | sed -E 's#.*[:/]([^/]+/[^/]+)(\.git)?$#\1#; s#\.git$##')

STATE="success"
DESCRIPTION="holdout: ${SCORE} [${CI_LOW},${CI_HIGH}]"
if [ "$DIVERGENCE" = "true" ]; then
  STATE="failure"
  DESCRIPTION="DIVERGENCE flagged — ${DESCRIPTION}"
fi
if [ "$PROBE_VERDICT" = "below-floor" ]; then
  STATE="failure"
  DESCRIPTION="${DESCRIPTION} — probe: below floor"
elif [ "$PROBE_VERDICT" = "ok" ]; then
  DESCRIPTION="${DESCRIPTION} — probe: ok"
fi

# LFD_STATUS_DRYRUN skips the network write (tests / local poll runs).
if [ "${LFD_STATUS_DRYRUN:-}" = "1" ]; then
  echo "[dry-run] would post status for ${SHA}: ${STATE} — ${DESCRIPTION}"
  exit 0
fi

: "${EVAL_REPO_STATUS_TOKEN:?EVAL_REPO_STATUS_TOKEN must be configured}"
: "${GITHUB_API_URL:?GITHUB_API_URL must be configured}"
API_URL="${GITHUB_API_URL%/}"

curl --fail-with-body --silent --show-error -X POST \
  -H "Authorization: token ${EVAL_REPO_STATUS_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  "${API_URL}/repos/${REPO_SLUG}/statuses/${SHA}" \
  -d "{\"state\":\"${STATE}\",\"description\":\"${DESCRIPTION}\",\"context\":\"lfd/holdout\"}" \
  > /dev/null

echo "Posted status for ${SHA}: ${DESCRIPTION}"
