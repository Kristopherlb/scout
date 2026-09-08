#!/usr/bin/env bash
# score-dev.sh — run the local dev-loop scorer. Deterministic wrapper.
# Called every cycle, no round trip, no eval-repo involvement.
# The agent (or a human) runs this directly; no judgment required.
#
# Usage: ./score-dev.sh
# Output: JSON on stdout — {"score": <float>, "ci_low": <float>,
#                             "ci_high": <float>, "void": <bool>}

set -euo pipefail

# The managed scorer owns lint plus scoring. This script is only the stable
# target-side entry point, so stateful detectors run exactly once per call.
if [ ! -x .lfd/harness/score-dev.sh ]; then
  echo '{"status":"error","error":{"code":"capability_unavailable","message":"managed developer scorer is missing"}}' >&2
  exit 1
fi

exec .lfd/harness/score-dev.sh
