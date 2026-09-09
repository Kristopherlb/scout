#!/usr/bin/env bash
# Submit an immutable LFD v1 request without modifying the caller's worktree.
set -euo pipefail

emit_error() {
  python3 - "$1" "$2" <<'PY'
import json, sys
print(json.dumps({"schema_version": 1, "command": "holdout.request",
                  "target": None, "status": "error", "stage": None,
                  "artifacts": [], "errors": [{"code": sys.argv[1],
                  "message": sys.argv[2]}], "next_actions": []}, sort_keys=True))
PY
}

usage="Usage: $0 <dev_score> <dev_ci_low> <dev_ci_high> [model_id] [tokens_in] [tokens_out] [cost_usd] [wall_clock_secs]"
if [ "$#" -lt 3 ] || [ "$#" -gt 8 ]; then
  emit_error "invalid_input" "$usage"
  exit 2
fi
DEV_SCORE="$1"
DEV_CI_LOW="$2"
DEV_CI_HIGH="$3"
MODEL_ID="${4:-}"
TOKENS_IN="${5:-}"
TOKENS_OUT="${6:-}"
COST_USD="${7:-}"
WALL_CLOCK="${8:-}"

if ! REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null); then
  emit_error "invalid_input" "current directory is not a Git working tree"
  exit 2
fi
if ! cd "$REPO_ROOT"; then
  emit_error "infrastructure_failure" "could not enter the Git working tree"
  exit 4
fi
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
if ! REQUESTED_SHA=$(git rev-parse HEAD 2>/dev/null); then
  emit_error "infrastructure_failure" "could not resolve the requested commit"
  exit 4
fi
if [ -n "${LFD_REQUEST_ID:-}" ]; then
  REQUEST_ID="$LFD_REQUEST_ID"
elif ! REQUEST_ID=$(python3 -c 'import secrets; print(secrets.token_hex(16))'); then
  emit_error "infrastructure_failure" "could not generate a request ID"
  exit 4
fi
if [[ ! "$REQUEST_ID" =~ ^[0-9a-f]{32}$ ]]; then
  emit_error "invalid_request_id" "request ID must be 32 lowercase hexadecimal characters"
  exit 2
fi
TAG="${TAG_PREFIX}v${PROTOCOL_VERSION}-${REQUESTED_SHA:0:12}-${REQUEST_ID}"

if ! MSG=$(python3 - "$PROTOCOL_VERSION" "$REQUEST_ID" "$REQUESTED_SHA" \
    "$DEV_SCORE" "$DEV_CI_LOW" "$DEV_CI_HIGH" "$MODEL_ID" \
    "$TOKENS_IN" "$TOKENS_OUT" "$COST_USD" "$WALL_CLOCK" <<'PY'
import json, math, re, sys

def required_number(value, name, *, minimum=None, maximum=None):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and number < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return number

def optional_number(value, name):
    return None if value == "" else required_number(value, name, minimum=0)

try:
    payload = {
        "schema_version": int(sys.argv[1]),
        "request_id": sys.argv[2],
        "requested_sha": sys.argv[3],
        "dev_score": required_number(sys.argv[4], "dev_score", minimum=0, maximum=1),
        "dev_ci": [required_number(sys.argv[5], "dev_ci_low", minimum=0, maximum=1),
                   required_number(sys.argv[6], "dev_ci_high", minimum=0, maximum=1)],
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
    if not payload["dev_ci"][0] <= payload["dev_score"] <= payload["dev_ci"][1]:
        raise ValueError("dev_ci must be ordered and contain dev_score")
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
except ValueError as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(2)
PY
); then
  emit_error "invalid_input" "request metrics are invalid"
  exit 2
fi

if ! PUSH_ERROR=$(mktemp); then
  emit_error "infrastructure_failure" "could not create a temporary error file"
  exit 4
fi
TEMP_ROOT=""
WORKTREE=""
BRANCH=""
BRANCH_CREATED=0
LOCAL_TAG_OWNED=0
cleanup() {
  if [ -n "$WORKTREE" ] && [ -d "$WORKTREE" ]; then
    git -C "$REPO_ROOT" worktree remove --force "$WORKTREE" >/dev/null 2>&1 || true
  fi
  if [ "$BRANCH_CREATED" = "1" ]; then
    git -C "$REPO_ROOT" branch -D "$BRANCH" >/dev/null 2>&1 || true
  fi
  if [ "$LOCAL_TAG_OWNED" = "1" ]; then
    git -C "$REPO_ROOT" tag -d "$TAG" >/dev/null 2>&1 || true
  fi
  [ -z "$TEMP_ROOT" ] || rm -rf "$TEMP_ROOT"
  rm -f "$PUSH_ERROR"
}
trap cleanup EXIT

if ! git tag -a "$TAG" -m "$MSG" "$REQUESTED_SHA" 2>"$PUSH_ERROR"; then
  emit_error "request_collision" "request tag already exists locally"
  exit 2
fi
LOCAL_TAG_OWNED=1
if git push origin "refs/tags/${TAG}" 2>"$PUSH_ERROR"; then
  LOCAL_TAG_OWNED=0
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
  if ! git tag -d "$TAG" >/dev/null 2>"$PUSH_ERROR"; then
    emit_error "cleanup_failure" "could not remove the temporary local request tag"
    exit 4
  fi
  LOCAL_TAG_OWNED=0
  emit_error "request_collision" "request tag already exists on origin"
  exit 2
else
  LS_REMOTE_STATUS=$?
  if [ "$LS_REMOTE_STATUS" -ne 2 ]; then
    emit_error "transport_failure" "could not inspect the remote request tag"
    exit 4
  fi
fi

if ! git tag -d "$TAG" >/dev/null 2>"$PUSH_ERROR"; then
  emit_error "cleanup_failure" "could not remove the temporary local request tag"
  exit 4
fi
LOCAL_TAG_OWNED=0
if ! TEMP_ROOT=$(mktemp -d); then
  emit_error "infrastructure_failure" "could not create a fallback workspace"
  exit 4
fi
WORKTREE="$TEMP_ROOT/worktree"
BRANCH="lfd-request/${REQUEST_ID}"
if ! git worktree add --quiet --detach "$WORKTREE" "$REQUESTED_SHA" 2>"$PUSH_ERROR"; then
  emit_error "fallback_failed" "could not create isolated request worktree"
  exit 4
fi
if ! git -C "$WORKTREE" switch --quiet -c "$BRANCH" 2>"$PUSH_ERROR"; then
  emit_error "fallback_failed" "could not create ephemeral request branch"
  exit 4
fi
BRANCH_CREATED=1
REQUEST_LOG="$WORKTREE/.github/holdout-requests.jsonl"
if ! mkdir -p "$(dirname "$REQUEST_LOG")"; then
  emit_error "fallback_failed" "could not create the fallback request directory"
  exit 4
fi
if ! python3 - "$REQUEST_LOG" "$TAG" "$REQUESTED_SHA" "$MSG" <<'PY'
import json, sys
path, tag, target, payload = sys.argv[1:]
with open(path, "a") as stream:
    stream.write(json.dumps({"tag": tag, "target": target,
                             "payload": json.loads(payload)},
                            separators=(",", ":"), sort_keys=True) + "\n")
PY
then
  emit_error "fallback_failed" "could not write the fallback request payload"
  exit 4
fi
if ! git -C "$WORKTREE" add -- .github/holdout-requests.jsonl 2>"$PUSH_ERROR"; then
  emit_error "fallback_failed" "could not stage the fallback request payload"
  exit 4
fi
if ! git -C "$WORKTREE" commit --quiet -m "holdout request: ${REQUEST_ID}" 2>"$PUSH_ERROR"; then
  emit_error "fallback_failed" "could not commit the fallback request payload"
  exit 4
fi
if ! REQUEST_COMMIT=$(git -C "$WORKTREE" rev-parse HEAD 2>"$PUSH_ERROR"); then
  emit_error "fallback_failed" "could not resolve the fallback request commit"
  exit 4
fi
if ! PARENT=$(git -C "$WORKTREE" rev-parse HEAD^ 2>"$PUSH_ERROR"); then
  emit_error "fallback_failed" "could not resolve the fallback request parent"
  exit 4
fi
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
