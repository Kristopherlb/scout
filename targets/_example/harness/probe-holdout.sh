#!/usr/bin/env bash
# Non-executable fixture boundary. The example exists only to render synthetic
# status and dashboard history; it is never a probe target.
#
# Contract:
#   $1 = pinned checkout of the target repo (UNTRUSTED — use $RUN_SANDBOXED)
#   stdout = one JSON line: {"operators": {"<op>": <score 0..1>, ...}}
set -euo pipefail
echo '{"operators": {}, "error": "fixture-only target cannot be probed"}'
exit 1
