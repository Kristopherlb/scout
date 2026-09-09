#!/usr/bin/env python3
"""Validation policy for immutable version-1 holdout requests."""
import json
import re

import lfd_common


REQUEST_ID_RE = re.compile(r"^[0-9a-f]{32}$")
SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
PAYLOAD_FIELDS = {
    "schema_version", "request_id", "requested_sha", "dev_score", "dev_ci",
    "model_id", "reported_tokens_in", "reported_tokens_out",
    "reported_cost_usd", "reported_wall_clock",
}
STATUS_CONTEXT = "lfd/holdout"


class ProtocolError(ValueError):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def validate_request(tag, raw_payload, prefix, protocol_version, actual_sha):
    """Validate and bind a request tag, payload, and dereferenced commit."""
    if protocol_version != 1:
        raise ProtocolError("unsupported_protocol", "only holdout protocol version 1 is implemented")
    if not isinstance(actual_sha, str) or not SHA_RE.fullmatch(actual_sha):
        raise ProtocolError("invalid_commit", "tag does not resolve to a full hexadecimal commit SHA")
    try:
        payload = json.loads(raw_payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ProtocolError("invalid_payload", "tag message is not JSON") from exc
    if not isinstance(payload, dict):
        raise ProtocolError("invalid_payload", "tag message must be an object")
    unknown = set(payload) - PAYLOAD_FIELDS
    if unknown:
        raise ProtocolError("invalid_payload", f"unknown field: {sorted(unknown)[0]}")
    for field in ("schema_version", "request_id", "requested_sha"):
        if field not in payload:
            raise ProtocolError("invalid_payload", f"missing required field: {field}")
    if payload["schema_version"] != protocol_version:
        raise ProtocolError("unsupported_protocol", "payload version does not match target contract")
    request_id = payload["request_id"]
    requested_sha = payload["requested_sha"]
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise ProtocolError("invalid_request_id", "request_id must be 32 lowercase hexadecimal characters")
    if not isinstance(requested_sha, str) or not SHA_RE.fullmatch(requested_sha):
        raise ProtocolError("invalid_commit", "requested_sha must be a full hexadecimal commit SHA")
    if requested_sha != actual_sha:
        raise ProtocolError("commit_mismatch", "payload requested_sha does not equal the tagged commit")
    expected_tag = f"{prefix}v{protocol_version}-{requested_sha[:12]}-{request_id}"
    if tag != expected_tag:
        raise ProtocolError("tag_mismatch", "tag name does not match protocol version, commit, and request ID")
    parsed = lfd_common.parse_tag_message(raw_payload)
    parsed.update({
        "schema_version": protocol_version,
        "request_id": request_id,
        "requested_sha": requested_sha,
    })
    return parsed
