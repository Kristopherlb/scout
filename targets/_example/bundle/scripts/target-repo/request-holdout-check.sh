#!/usr/bin/env bash
# Submit an immutable LFD v1 request without modifying the caller's worktree.
set -euo pipefail

usage="Usage: $0 <dev_score> <dev_ci_low> <dev_ci_high> [model_id] [tokens_in] [tokens_out] [cost_usd] [wall_clock_secs]"
DEV_SCORE="${1:?$usage}"
DEV_CI_LOW="${2:?missing dev_ci_low}"
DEV_CI_HIGH="${3:?missing dev_ci_high}"
MODEL_ID="${4:-}"
TOKENS_IN="${5:-}"
TOKENS_OUT="${6:-}"
COST_USD="${7:-}"
WALL_CLOCK="${8:-}"

emit_error() {
  python3 - "$1" "$2" <<'PY'
import json, sys
print(json.dumps({"schema_version": 1, "command": "holdout.request",
                  "target": None, "status": "error", "stage": None,
                  "artifacts": [], "errors": [{"code": sys.argv[1],
                  "message": sys.argv[2]}], "next_actions": []}, sort_keys=True))
PY
}

if ! REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null); then
  emit_error "invalid_input" "current directory is not a Git working tree"
  exit 2
fi
cd "$REPO_ROOT"
PROTOCOL_FILE=".lfd/holdout-protocol.json"
if [ ! -f "$PROTOCOL_FILE" ]; then
  emit_error "missing_protocol" "$PROTOCOL_FILE is required"
  exit 2
fi

if ! PROTOCOL_VALUES=$(python3 - "$PROTOCOL_FILE" <<'PY'
import json, re, sys
try:
    with open(sys.argv[1]) as stream:
        value = json.load(stream)
    if set(value) != {"protocol_version", "tag_prefix", "status_context"}:
        raise ValueError("unsupported protocol shape")
    if value["protocol_version"] != 1:
        raise ValueError("only protocol version 1 is implemented")
    if not isinstance(value["tag_prefix"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}-", value["tag_prefix"]):
        raise ValueError("unsafe tag prefix")
    if value["status_context"] != "lfd/holdout":
        raise ValueError("unsupported status context")
    print(value["protocol_version"])
    print(value["tag_prefix"])
    print(value["status_context"])
except (OSError, ValueError, json.JSONDecodeError) as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(2)
PY
); then
  emit_error "invalid_protocol" "holdout protocol configuration is invalid"
  exit 2
fi
PROTOCOL_VERSION=$(printf '%s\n' "$PROTOCOL_VALUES" | sed -n '1p')
TAG_PREFIX=$(printf '%s\n' "$PROTOCOL_VALUES" | sed -n '2p')
REQUESTED_SHA=$(git rev-parse HEAD)
REQUEST_ID="${LFD_REQUEST_ID:-$(python3 -c 'import secrets; print(secrets.token_hex(16))')}"
if [[ ! "$REQUEST_ID" =~ ^[0-9a-f]{32}$ ]]; then
  emit_error "invalid_request_id" "request ID must be 32 lowercase hexadecimal characters"
  exit 2
fi
TAG="${TAG_PREFIX}v${PROTOCOL_VERSION}-${REQUESTED_SHA:0:12}-${REQUEST_ID}"

if ! MSG=$(python3 - "$PROTOCOL_VERSION" "$REQUEST_ID" "$REQUESTED_SHA" \
    "$DEV_SCORE" "$DEV_CI_LOW" "$DEV_CI_HIGH" "$MODEL_ID" \
    "$TOKENS_IN" "$TOKENS_OUT" "$COST_USD" "$WALL_CLOCK" <<'PY'
import json, math, re, sys

def required_number(value, name):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number

def optional_number(value, name):
    return None if value == "" else required_number(value, name)

try:
    payload = {
        "schema_version": int(sys.argv[1]),
        "request_id": sys.argv[2],
        "requested_sha": sys.argv[3],
        "dev_score": required_number(sys.argv[4], "dev_score"),
        "dev_ci": [required_number(sys.argv[5], "dev_ci_low"),
                   required_number(sys.argv[6], "dev_ci_high")],
    }
    if sys.argv[7]:
        if not re.fullmatch(r"[A-Za-z0-9._:/-]{1,128}", sys.argv[7]):
            raise ValueError("model_id has unsupported characters")
        payload["model_id"] = sys.argv[7]
    for name, value in zip(("reported_tokens_in", "reported_tokens_out",
                            "reported_cost_usd", "reported_wall_clock"), sys.argv[8:]):
        parsed = optional_number(value, name)
        if parsed is not None:
            payload[name] = parsed
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
except ValueError as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(2)
PY
); then
  emit_error "invalid_input" "request metrics are invalid"
  exit 2
fi

PUSH_ERROR=$(mktemp)
TEMP_ROOT=""
WORKTREE=""
BRANCH=""
cleanup() {
  if [ -n "$WORKTREE" ] && [ -d "$WORKTREE" ]; then
    git -C "$REPO_ROOT" worktree remove --force "$WORKTREE" >/dev/null 2>&1 || true
  fi
  if [ -n "$BRANCH" ]; then
    git -C "$REPO_ROOT" branch -D "$BRANCH" >/dev/null 2>&1 || true
  fi
  [ -z "$TEMP_ROOT" ] || rm -rf "$TEMP_ROOT"
  rm -f "$PUSH_ERROR"
}
trap cleanup EXIT

if ! git tag -a "$TAG" -m "$MSG" "$REQUESTED_SHA" 2>"$PUSH_ERROR"; then
  emit_error "request_collision" "request tag already exists locally"
  exit 2
fi
if git push origin "refs/tags/${TAG}" 2>"$PUSH_ERROR"; then
  python3 - "$TAG" "$REQUESTED_SHA" <<'PY'
import json, sys
print(json.dumps({"schema_version": 1, "command": "holdout.request",
                  "target": sys.argv[2], "status": "submitted", "stage": "direct",
                  "artifacts": [{"tag": sys.argv[1], "sha": sys.argv[2]}],
                  "errors": [], "next_actions": ["check holdout status"]}, sort_keys=True))
PY
  exit 0
fi

if git ls-remote --exit-code --tags origin "refs/tags/${TAG}" >/dev/null 2>&1; then
  git tag -d "$TAG" >/dev/null
  emit_error "request_collision" "request tag already exists on origin"
  exit 2
fi

git tag -d "$TAG" >/dev/null
TEMP_ROOT=$(mktemp -d)
WORKTREE="$TEMP_ROOT/worktree"
BRANCH="lfd-request/${REQUEST_ID}"
if ! git worktree add --quiet --detach "$WORKTREE" "$REQUESTED_SHA" 2>"$PUSH_ERROR"; then
  emit_error "fallback_failed" "could not create isolated request worktree"
  exit 4
fi
git -C "$WORKTREE" switch --quiet -c "$BRANCH"
REQUEST_LOG="$WORKTREE/.github/holdout-requests.jsonl"
mkdir -p "$(dirname "$REQUEST_LOG")"
python3 - "$REQUEST_LOG" "$TAG" "$REQUESTED_SHA" "$MSG" <<'PY'
import json, sys
path, tag, target, payload = sys.argv[1:]
with open(path, "a") as stream:
    stream.write(json.dumps({"tag": tag, "target": target,
                             "payload": json.loads(payload)},
                            separators=(",", ":"), sort_keys=True) + "\n")
PY
git -C "$WORKTREE" add -- .github/holdout-requests.jsonl
git -C "$WORKTREE" commit --quiet -m "holdout request: ${REQUEST_ID}"
REQUEST_COMMIT=$(git -C "$WORKTREE" rev-parse HEAD)
PARENT=$(git -C "$WORKTREE" rev-parse HEAD^)
if [ "$PARENT" != "$REQUESTED_SHA" ]; then
  emit_error "parent_mismatch" "fallback request parent is not the requested commit"
  exit 4
fi
if ! git -C "$WORKTREE" push --quiet origin "HEAD:refs/heads/${BRANCH}" 2>"$PUSH_ERROR"; then
  emit_error "fallback_failed" "could not push isolated request branch"
  exit 4
fi
python3 - "$TAG" "$REQUESTED_SHA" "$BRANCH" "$REQUEST_COMMIT" <<'PY'
import json, sys
print(json.dumps({"schema_version": 1, "command": "holdout.request",
                  "target": sys.argv[2], "status": "submitted", "stage": "fallback",
                  "artifacts": [{"tag": sys.argv[1], "sha": sys.argv[2],
                                 "branch": sys.argv[3], "request_commit": sys.argv[4]}],
                  "errors": [], "next_actions": ["check holdout status"]}, sort_keys=True))
PY
