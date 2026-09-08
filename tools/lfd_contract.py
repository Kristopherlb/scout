#!/usr/bin/env python3
"""Strict target contract loading and validation.

This module is inward policy: it performs no subprocess or network I/O and
does not import command or operations modules. Runtime callers receive one
validated document instead of independently interpreting executable config.
"""
import json
import os
import re
import argparse
import sys
import copy


SCHEMA_VERSION = 1
VALID_STATUSES = {"onboarding", "active", "paused", "retired", "example"}
PROBE_MODES = {"off", "always", "every-k", "on-divergence"}
ENFORCEMENT_MODES = {"advisory", "blocking"}
SANDBOX_BACKENDS = {"docker"}
NAME_RE = re.compile(r"^[a-z0-9_][a-z0-9._-]{0,63}$")
TAG_PREFIX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}-$")
DIGEST_IMAGE_RE = re.compile(r"^\S+@sha256:[0-9a-f]{64}$")
MEMORY_RE = re.compile(r"^[1-9][0-9]*(?:[kKmMgG])?$")


class ContractError(ValueError):
    """A target contract is absent, unsupported, or invalid."""

    def __init__(self, code, path, message):
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code} at {path}: {message}")


def _error(code, path, message):
    raise ContractError(code, path, message)


def _object(value, path, required):
    if not isinstance(value, dict):
        _error("invalid_type", path, "must be an object")
    actual = set(value)
    missing = set(required) - actual
    unknown = actual - set(required)
    if missing:
        _error("missing_field", f"{path}.{sorted(missing)[0]}", "is required")
    if unknown:
        _error("unknown_field", f"{path}.{sorted(unknown)[0]}", "is not allowed")


def _string(value, path, *, allow_empty=False, single_line=False):
    if not isinstance(value, str):
        _error("invalid_type", path, "must be a string")
    if not allow_empty and not value:
        _error("invalid_value", path, "must not be empty")
    if "\x00" in value or (single_line and any(c in value for c in "\r\n")):
        _error("invalid_value", path, "contains forbidden control characters")
    return value


def _integer(value, path, minimum):
    if isinstance(value, bool) or not isinstance(value, int):
        _error("invalid_type", path, "must be an integer")
    if value < minimum:
        _error("invalid_value", path, f"must be at least {minimum}")
    return value


def _number(value, path, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _error("invalid_type", path, "must be numeric")
    value = float(value)
    if not minimum <= value <= maximum:
        _error("invalid_value", path, f"must be between {minimum} and {maximum}")
    return value


def _choice(value, path, choices):
    _string(value, path)
    if value not in choices:
        _error("invalid_value", path, f"must be one of {', '.join(sorted(choices))}")
    return value


def _validate_repository_url(value):
    value = _string(value, "identity.repository_url", single_line=True)
    if value.startswith("-") or any(ord(c) < 32 for c in value):
        _error("invalid_value", "identity.repository_url", "is not a safe Git repository location")
    accepted = (
        value.startswith(("https://", "http://", "ssh://", "git://", "file://", "/"))
        or re.match(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+:.+$", value)
    )
    if not accepted:
        _error("invalid_value", "identity.repository_url", "must be an absolute path or supported Git URL")


def validate(contract, *, expected_name=None):
    """Validate a parsed target contract and return it unchanged."""
    top = ("schema_version", "identity", "lifecycle", "holdout", "detectors",
           "liveness", "sandbox", "executor", "notes")
    _object(contract, "$", top)
    if contract["schema_version"] != SCHEMA_VERSION:
        _error("unsupported_version", "schema_version",
               f"expected {SCHEMA_VERSION}, got {contract['schema_version']!r}")

    identity = contract["identity"]
    _object(identity, "identity", ("name", "repository_url"))
    name = _string(identity["name"], "identity.name")
    if not NAME_RE.fullmatch(name):
        _error("invalid_value", "identity.name", "must be lowercase and use only alphanumeric ._-")
    if expected_name is not None and name != expected_name:
        _error("identity_mismatch", "identity.name",
               f"declares {name!r}, but directory is {expected_name!r}")
    _validate_repository_url(identity["repository_url"])

    lifecycle = contract["lifecycle"]
    _object(lifecycle, "lifecycle", ("status",))
    _choice(lifecycle["status"], "lifecycle.status", VALID_STATUSES)

    holdout = contract["holdout"]
    _object(holdout, "holdout", ("tag_prefix", "min_hours_between", "max_runs"))
    prefix = _string(holdout["tag_prefix"], "holdout.tag_prefix", single_line=True)
    if not TAG_PREFIX_RE.fullmatch(prefix) or ".." in prefix:
        _error("invalid_value", "holdout.tag_prefix", "must be a safe Git tag prefix ending in '-'")
    _number(holdout["min_hours_between"], "holdout.min_hours_between", 0, 8760)
    _integer(holdout["max_runs"], "holdout.max_runs", 1)

    detectors = contract["detectors"]
    _object(detectors, "detectors", ("divergence", "probe", "coverage_variance"))
    divergence = detectors["divergence"]
    _object(divergence, "detectors.divergence", ("window_cycles", "enforcement"))
    _integer(divergence["window_cycles"], "detectors.divergence.window_cycles", 2)
    _choice(divergence["enforcement"], "detectors.divergence.enforcement", ENFORCEMENT_MODES)
    probe = detectors["probe"]
    _object(probe, "detectors.probe", ("mode", "every_k", "floor", "enforcement"))
    _choice(probe["mode"], "detectors.probe.mode", PROBE_MODES)
    _integer(probe["every_k"], "detectors.probe.every_k", 1)
    _number(probe["floor"], "detectors.probe.floor", 0, 1)
    _choice(probe["enforcement"], "detectors.probe.enforcement", ENFORCEMENT_MODES)
    coverage = detectors["coverage_variance"]
    _object(coverage, "detectors.coverage_variance", ("floor", "enforcement"))
    _number(coverage["floor"], "detectors.coverage_variance.floor", 0, 1)
    _choice(coverage["enforcement"], "detectors.coverage_variance.enforcement", ENFORCEMENT_MODES)

    liveness = contract["liveness"]
    _object(liveness, "liveness", ("build_command", "boot_command", "health_check",
                                    "exemption", "timeout_seconds"))
    for key in ("build_command", "boot_command", "health_check", "exemption"):
        _string(liveness[key], f"liveness.{key}", allow_empty=True)
    _integer(liveness["timeout_seconds"], "liveness.timeout_seconds", 1)

    sandbox = contract["sandbox"]
    _object(sandbox, "sandbox", ("backend", "image", "cpus", "memory", "pids_limit"))
    _choice(sandbox["backend"], "sandbox.backend", SANDBOX_BACKENDS)
    image = _string(sandbox["image"], "sandbox.image", single_line=True)
    if not DIGEST_IMAGE_RE.fullmatch(image):
        _error("invalid_value", "sandbox.image", "must be pinned by sha256 digest")
    _number(sandbox["cpus"], "sandbox.cpus", 0.1, 1024)
    memory = _string(sandbox["memory"], "sandbox.memory", single_line=True)
    if not MEMORY_RE.fullmatch(memory):
        _error("invalid_value", "sandbox.memory", "must be a positive Docker memory value")
    _integer(sandbox["pids_limit"], "sandbox.pids_limit", 1)

    executor = contract["executor"]
    _object(executor, "executor", ("model",))
    _string(executor["model"], "executor.model", allow_empty=True, single_line=True)
    _string(contract["notes"], "notes", allow_empty=True)
    return contract


def new_contract(name, repository_url, template_path=None):
    """Instantiate the repository-owned target contract template."""
    if template_path is None:
        template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "templates", "target-contract.json")
    try:
        with open(template_path) as f:
            template = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        _error("invalid_template", "templates/target-contract.json", str(exc))
    contract = copy.deepcopy(template)
    contract["identity"] = {"name": name, "repository_url": repository_url}
    return validate(contract, expected_name=name)


def load_target(target_dir):
    """Load and strictly validate ``target.json`` from one registry entry."""
    target_dir = os.path.abspath(target_dir)
    path = os.path.join(target_dir, "target.json")
    if not os.path.isfile(path):
        if os.path.isfile(os.path.join(target_dir, "config.env")):
            _error("legacy_contract", "config.env",
                   "legacy executable configuration is unsupported; create target.json")
        _error("missing_contract", "target.json", "file does not exist")
    try:
        with open(path) as f:
            contract = json.load(f)
    except json.JSONDecodeError as exc:
        _error("invalid_json", "target.json", str(exc))
    return validate(contract, expected_name=os.path.basename(target_dir))


def value(contract, dotted_path):
    """Read a required value from an already validated contract."""
    current = contract
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            _error("missing_field", dotted_path, "is required")
        current = current[part]
    return current


def iter_targets(hub_root):
    """Yield validated ``(name, contract, directory)`` registry entries."""
    targets_dir = os.path.join(os.path.abspath(hub_root), "targets")
    if not os.path.isdir(targets_dir):
        return
    for name in sorted(os.listdir(targets_dir)):
        target_dir = os.path.join(targets_dir, name)
        if os.path.isfile(os.path.join(target_dir, "target.json")):
            yield name, load_target(target_dir), target_dir
        elif os.path.isfile(os.path.join(target_dir, "config.env")):
            load_target(target_dir)


def shell_values(contract):
    """Return the fixed adapter vocabulary consumed by hub shell scripts."""
    paths = {
        "TARGET_REPO_URL": "identity.repository_url",
        "HOLDOUT_TAG_PREFIX": "holdout.tag_prefix",
        "STATUS": "lifecycle.status",
        "MIN_HOURS_BETWEEN_HOLDOUT": "holdout.min_hours_between",
        "BUDGET_MAX_HOLDOUT_RUNS": "holdout.max_runs",
        "DIVERGENCE_WINDOW_CYCLES": "detectors.divergence.window_cycles",
        "PROBE_ON_HOLDOUT": "detectors.probe.mode",
        "PROBE_EVERY_K": "detectors.probe.every_k",
        "PROBE_FLOOR": "detectors.probe.floor",
        "COVERAGE_VARIANCE_FLOOR": "detectors.coverage_variance.floor",
        "BUILD_CMD": "liveness.build_command",
        "BOOT_CMD": "liveness.boot_command",
        "HEALTH_CHECK": "liveness.health_check",
        "LIVENESS_EXEMPT": "liveness.exemption",
        "LIVENESS_TIMEOUT": "liveness.timeout_seconds",
        "LFD_SANDBOX": "sandbox.backend",
        "SANDBOX_IMAGE": "sandbox.image",
        "SANDBOX_CPUS": "sandbox.cpus",
        "SANDBOX_MEMORY": "sandbox.memory",
        "SANDBOX_PIDS_LIMIT": "sandbox.pids_limit",
        "EXECUTOR_MODEL": "executor.model",
    }
    return {name: str(value(contract, path)) for name, path in paths.items()}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    shell = sub.add_parser("shell")
    shell.add_argument("--target-dir", required=True)
    get = sub.add_parser("get")
    get.add_argument("--target-dir", required=True)
    get.add_argument("--field", required=True)
    args = parser.parse_args()
    try:
        contract = load_target(args.target_dir)
    except ContractError as exc:
        print(json.dumps({"error": {"code": exc.code, "path": exc.path,
                                    "message": exc.message}}), file=sys.stderr)
        return 2
    if args.command == "shell":
        for key, item in shell_values(contract).items():
            sys.stdout.buffer.write(key.encode() + b"\0" + item.encode() + b"\0")
    elif args.command == "get":
        item = value(contract, args.field)
        if isinstance(item, (dict, list)):
            print(json.dumps(item, separators=(",", ":"), sort_keys=True))
        else:
            print(item)
    return 0


if __name__ == "__main__":
    sys.exit(main())
