#!/usr/bin/env python3
"""Validate one fallback commit, create its immutable tag, clean its branch."""
import argparse
import json
import os
import re
import subprocess
import sys

REQUEST_ID_RE = re.compile(r"^[0-9a-f]{32}$")
SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


class MaterializeError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def git(*args, check=True):
    return subprocess.run(["git", *args], check=check, capture_output=True, text=True)


def load_protocol():
    try:
        with open(os.path.join(".lfd", "holdout-protocol.json")) as stream:
            value = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise MaterializeError("invalid_protocol", str(exc)) from exc
    if (set(value) != {"protocol_version", "tag_prefix", "status_context"}
            or value["protocol_version"] != 1
            or value["status_context"] != "lfd/holdout"
            or not isinstance(value["tag_prefix"], str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}-", value["tag_prefix"])):
        raise MaterializeError("invalid_protocol", "unsupported protocol configuration")
    return value


def load_appended_request(parent, event_sha):
    changed = git("diff-tree", "--no-commit-id", "--name-only", "-r", event_sha).stdout.splitlines()
    if changed != [".github/holdout-requests.jsonl"]:
        raise MaterializeError("unsafe_request_commit", "request commit must change only the request log")
    path = os.path.join(".github", "holdout-requests.jsonl")
    with open(path) as stream:
        current = stream.read().splitlines()
    prior_result = git("show", f"{parent}:.github/holdout-requests.jsonl", check=False)
    prior = prior_result.stdout.splitlines() if prior_result.returncode == 0 else []
    if len(current) != len(prior) + 1 or current[:-1] != prior:
        raise MaterializeError("unsafe_request_commit", "request commit must append exactly one line")
    try:
        request = json.loads(current[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise MaterializeError("invalid_request", "appended request is not JSON") from exc
    return request


def materialize(event_sha, event_ref):
    protocol = load_protocol()
    head = git("rev-parse", "HEAD").stdout.strip()
    if event_sha != head or not SHA_RE.fullmatch(event_sha):
        raise MaterializeError("event_mismatch", "checked-out HEAD does not equal the event commit")
    parents = git("rev-list", "--parents", "-n", "1", event_sha).stdout.split()
    if len(parents) != 2:
        raise MaterializeError("parent_mismatch", "request commit must have exactly one parent")
    parent = parents[1]
    request = load_appended_request(parent, event_sha)
    if not isinstance(request, dict) or set(request) != {"tag", "target", "payload"}:
        raise MaterializeError("invalid_request", "request entry has an unsupported shape")
    payload = request["payload"]
    allowed = {"schema_version", "request_id", "requested_sha", "dev_score", "dev_ci",
               "model_id", "reported_tokens_in", "reported_tokens_out",
               "reported_cost_usd", "reported_wall_clock"}
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise MaterializeError("invalid_request", "payload has an unsupported shape")
    request_id = payload.get("request_id")
    requested_sha = payload.get("requested_sha")
    if (payload.get("schema_version") != protocol["protocol_version"]
            or not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id)
            or requested_sha != parent or request["target"] != parent):
        raise MaterializeError("request_mismatch", "payload and request parent are not identical")
    expected_tag = (f"{protocol['tag_prefix']}v{protocol['protocol_version']}-"
                    f"{parent[:12]}-{request_id}")
    expected_ref = f"refs/heads/lfd-request/{request_id}"
    if request["tag"] != expected_tag or event_ref != expected_ref:
        raise MaterializeError("request_mismatch", "tag or request branch does not match the payload")
    collision = git("ls-remote", "--exit-code", "--tags", "origin",
                    f"refs/tags/{expected_tag}", check=False)
    if collision.returncode == 0:
        raise MaterializeError("request_collision", "request tag already exists")
    message = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    git("tag", "-a", expected_tag, "-m", message, parent)
    pushed = git("push", "--quiet", "origin", f"refs/tags/{expected_tag}", check=False)
    if pushed.returncode != 0:
        git("tag", "-d", expected_tag, check=False)
        raise MaterializeError("transport_failure", pushed.stderr.strip())
    deleted = git("push", "--quiet", "origin", "--delete",
                  f"lfd-request/{request_id}", check=False)
    if deleted.returncode != 0:
        raise MaterializeError("cleanup_failure", deleted.stderr.strip())
    return {"tag": expected_tag, "sha": parent}


def envelope(status, stage=None, artifacts=None, errors=None):
    return {"schema_version": 1, "command": "holdout.materialize", "target": None,
            "status": status, "stage": stage, "artifacts": artifacts or [],
            "errors": errors or [], "next_actions": []}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-sha", required=True)
    parser.add_argument("--event-ref", required=True)
    args = parser.parse_args()
    try:
        artifact = materialize(args.event_sha, args.event_ref)
        document = envelope("success", "materialized", [artifact])
        code = 0
    except MaterializeError as exc:
        document = envelope("error", errors=[{
            "code": exc.code, "message": str(exc)}])
        code = 4 if exc.code in {"transport_failure", "cleanup_failure"} else 2
    except (OSError, subprocess.SubprocessError) as exc:
        document = envelope("error", errors=[{
            "code": "transport_failure", "message": str(exc)}])
        code = 4
    print(json.dumps(document, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
