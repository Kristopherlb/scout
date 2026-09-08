#!/usr/bin/env bash
# run-sandboxed.sh — Stage-1 execution jail for untrusted agent code.
#
# The isolation property this enforces: agent code runs with NO network,
# NO view of targets/ (holdout answers, canary lists), a read-only checkout,
# and hard resource limits. Holdout answers are compared OUTSIDE this jail
# (Stage 2, in the caller) — they are never mounted or readable here.
#
# Usage: run-sandboxed.sh <checkout-dir> <output-dir> <timeout-secs> <cmd> [args...]
#   <checkout-dir>  mounted/visible read-only at /work (docker) or in place
#   <output-dir>    the ONLY writable path, at /out (docker) or in place
#   <cmd>           executed with cwd=<checkout-dir>
# Exit 125 is reserved for sandbox infrastructure/configuration failures.
# Other nonzero exits are the sandboxed command's result.
#
# Backend selection comes from LFD_SANDBOX: auto, docker, sandbox-exec, or
# none. "none" is an explicit test/development escape hatch and must never be
# used for real scoring. Docker image and resource limits are required config.

set -euo pipefail

infrastructure_error() {
  echo "ERROR: $*" >&2
  exit 125
}

CHECKOUT="$(cd "$1" && pwd)"; OUTPUT="$(mkdir -p "$2" && cd "$2" && pwd)"
TIMEOUT_SECS="$3"; shift 3

# "none" is degraded passthrough for tests where isolation is not under test.
BACKEND="${LFD_SANDBOX:-}"
[ -n "$BACKEND" ] || infrastructure_error "LFD_SANDBOX must be configured"
case "$BACKEND" in auto|docker|sandbox-exec|none) ;; *)
  infrastructure_error "invalid LFD_SANDBOX=$BACKEND" ;; esac

if [ "$BACKEND" = "auto" ] || [ "$BACKEND" = "docker" ]; then
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    [ -n "${SANDBOX_IMAGE:-}" ] || infrastructure_error "SANDBOX_IMAGE must be configured"
    [ -n "${SANDBOX_CPUS:-}" ] || infrastructure_error "SANDBOX_CPUS must be configured"
    [ -n "${SANDBOX_MEMORY:-}" ] || infrastructure_error "SANDBOX_MEMORY must be configured"
    [ -n "${SANDBOX_PIDS_LIMIT:-}" ] || infrastructure_error "SANDBOX_PIDS_LIMIT must be configured"
    if [[ ! "$SANDBOX_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]]; then
      infrastructure_error "SANDBOX_IMAGE must be pinned by sha256 digest"
    fi
  exec docker run --rm \
    --network=none \
    --cpus="$SANDBOX_CPUS" \
    --memory="$SANDBOX_MEMORY" \
    --pids-limit="$SANDBOX_PIDS_LIMIT" \
    --security-opt no-new-privileges \
    --user "$(id -u):$(id -g)" \
    -v "${CHECKOUT}:/work:ro" \
    -v "${OUTPUT}:/out:rw" \
    -w /work \
    -e LFD_OUT=/out \
    "$SANDBOX_IMAGE" \
    timeout "${TIMEOUT_SECS}" "$@"
  elif [ "$BACKEND" = "docker" ]; then
    infrastructure_error "LFD_SANDBOX=docker but Docker is unavailable"
  fi
fi

if { [ "$BACKEND" = "auto" ] || [ "$BACKEND" = "sandbox-exec" ]; } && \
   command -v sandbox-exec >/dev/null 2>&1; then
  # macOS fallback for local dev: deny network and all file access except
  # the checkout (read) and output dir (write). TMPDIR needed by most tools.
  PROFILE=$(mktemp)
  trap 'rm -f "$PROFILE"' EXIT
  cat > "$PROFILE" <<EOF
(version 1)
(deny default)
(allow process-exec*)
(allow process-fork)
(allow signal (target same-sandbox))
(allow sysctl-read)
(allow mach-lookup)
(deny network*)
(allow file-read* (subpath "/usr") (subpath "/bin") (subpath "/sbin")
                  (subpath "/System") (subpath "/Library")
                  (subpath "/opt") (subpath "/private/tmp")
                  (subpath "${CHECKOUT}"))
(allow file-write* (subpath "${OUTPUT}") (subpath "/private/tmp"))
EOF
  cd "$CHECKOUT"
  LFD_OUT="$OUTPUT" exec sandbox-exec -f "$PROFILE" \
    python3 -c 'import subprocess,sys; sys.exit(subprocess.call(sys.argv[2:], timeout=float(sys.argv[1])))' \
    "$TIMEOUT_SECS" "$@"
fi

if [ "$BACKEND" != "none" ]; then
  infrastructure_error "no configured sandbox backend is available"
fi
echo "WARNING: running agent code UNSANDBOXED — holdout isolation is NOT enforced." >&2
echo "WARNING: do not use this mode for real holdout scoring." >&2
cd "$CHECKOUT"
LFD_OUT="$OUTPUT" exec python3 -c \
  'import subprocess,sys; sys.exit(subprocess.call(sys.argv[2:], timeout=float(sys.argv[1])))' \
  "$TIMEOUT_SECS" "$@"
