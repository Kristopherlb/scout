#!/usr/bin/env bash
# Non-executable fixture boundary. The example exists only to render synthetic
# status and dashboard history; it is never a scoring target.
#
# Contract:
#   $1 = pinned checkout of the target repo (treat as UNTRUSTED code)
#   stdout = one JSON line: {"score": <float>, "ci_low": <float>, "ci_high": <float>}
#
set -euo pipefail
echo '{"score": null, "ci_low": null, "ci_high": null, "error": "fixture-only target cannot be scored"}'
exit 1
