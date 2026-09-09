#!/usr/bin/env bash
# post-status.sh — post score+interval+divergence back to target-repo as a
# commit status. This is the ONLY write eval-repo ever makes to target-repo.
# Deterministic. No eval content, no per-case detail, no verbose output —
# just the score interval and bounded detector flags.
#
# Usage: post-status.sh <target-repo-url> <sha> <score> <ci_low> <ci_high> \
#   <divergence> <divergence_enforcement> <probe_verdict> <probe_enforcement> \
#   <coverage_verdict> <coverage_enforcement>
#   probe_verdict: "" (no probe run) | "ok" | "below-floor" — a boolean
#   verdict only; per-operator detail never leaves the hub (naming the weak
#   operator would hand the agent a which-axis-to-patch oracle).

set -euo pipefail

if [ "$#" -ne 11 ]; then
  echo "usage: post-status.sh <repo-url> <sha> <score> <ci-low> <ci-high> <divergence> <divergence-enforcement> <probe-verdict> <probe-enforcement> <coverage-verdict> <coverage-enforcement>" >&2
  exit 2
fi
REPO_URL="$1"; SHA="$2"; SCORE="$3"; CI_LOW="$4"; CI_HIGH="$5"; DIVERGENCE="$6"
DIVERGENCE_ENFORCEMENT="$7"; PROBE_VERDICT="$8"; PROBE_ENFORCEMENT="$9"
COVERAGE_VERDICT="${10}"; COVERAGE_ENFORCEMENT="${11}"

case "$DIVERGENCE" in true|false) ;; *) echo "invalid divergence verdict" >&2; exit 2 ;; esac
case "$PROBE_VERDICT" in ""|ok|below-floor) ;; *) echo "invalid probe verdict" >&2; exit 2 ;; esac
case "$COVERAGE_VERDICT" in ""|ok|below-floor) ;; *) echo "invalid coverage verdict" >&2; exit 2 ;; esac
for MODE in "$DIVERGENCE_ENFORCEMENT" "$PROBE_ENFORCEMENT" "$COVERAGE_ENFORCEMENT"; do
  case "$MODE" in advisory|blocking) ;; *) echo "invalid detector enforcement" >&2; exit 2 ;; esac
done

# Parse org/repo from the URL for the GitHub API call.
REPO_SLUG=$(echo "$REPO_URL" | sed -E 's#.*[:/]([^/]+/[^/]+)(\.git)?$#\1#; s#\.git$##')

STATE="success"
DESCRIPTION="holdout: ${SCORE} [${CI_LOW},${CI_HIGH}]"
if [ "$DIVERGENCE" = "true" ]; then
  DESCRIPTION="DIVERGENCE flagged — ${DESCRIPTION}"
  if [ "$DIVERGENCE_ENFORCEMENT" = "blocking" ]; then STATE="failure"; fi
fi
if [ "$PROBE_VERDICT" = "below-floor" ]; then
  DESCRIPTION="${DESCRIPTION} — probe: below floor"
  if [ "$PROBE_ENFORCEMENT" = "blocking" ]; then STATE="failure"; fi
elif [ "$PROBE_VERDICT" = "ok" ]; then
  DESCRIPTION="${DESCRIPTION} — probe: ok"
fi
if [ "$COVERAGE_VERDICT" = "below-floor" ]; then
  DESCRIPTION="${DESCRIPTION} — coverage: below floor"
  if [ "$COVERAGE_ENFORCEMENT" = "blocking" ]; then STATE="failure"; fi
elif [ "$COVERAGE_VERDICT" = "ok" ]; then
  DESCRIPTION="${DESCRIPTION} — coverage: ok"
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
