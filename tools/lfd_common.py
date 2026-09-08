#!/usr/bin/env python3
"""Shared deterministic policy for logs, gates, and score interpretation."""
import hashlib
import json
import os
import re

import lfd_contract

ConfigError = lfd_contract.ContractError

# Row fields that arrive from the agent side (tag message) and must be
# numeric or absent — never trusted as code or free text.
AGENT_NUMERIC_FIELDS = (
    "dev_score", "reported_tokens_in", "reported_tokens_out",
    "reported_cost_usd", "reported_wall_clock",
)
# model_id is agent-reported free text; constrain to a safe charset.
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9._:/-]{1,128}$")
AUDIT_FINDINGS = {
    "leakage_estimate", "goodhart_fence_matching", "calibration_quality",
    "escalation_wiring", "blinding_verification",
}


def config_value(config, key, *, allow_empty=False):
    """Read the fixed shell-adapter vocabulary from a validated contract.

    Flat dictionaries remain accepted for pure function tests; runtime callers
    obtain nested documents exclusively through ``lfd_contract.load_target``.
    """
    paths = {
        "TARGET_NAME": "identity.name",
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
    if key in config:
        value = config[key]
    elif key in paths:
        value = lfd_contract.value(config, paths[key])
    else:
        raise ConfigError("missing_field", key, "required configuration value is missing")
    if not allow_empty and not str(value).strip():
        raise ConfigError("invalid_value", key, "required configuration value is empty")
    return value


def config_int(config, key, *, minimum=None):
    value = config_value(config, key)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError("invalid_type", key, "must be an integer") from exc
    if minimum is not None and parsed < minimum:
        raise ConfigError("invalid_value", key, f"must be at least {minimum}")
    return parsed


def config_float(config, key, *, minimum=None, maximum=None):
    value = config_value(config, key)
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError("invalid_type", key, "must be numeric") from exc
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        raise ConfigError("invalid_value", key, "must be finite")
    if minimum is not None and parsed < minimum:
        raise ConfigError("invalid_value", key, f"must be at least {minimum}")
    if maximum is not None and parsed > maximum:
        raise ConfigError("invalid_value", key, f"must be at most {maximum}")
    return parsed


def read_log(path):
    """Read log.jsonl → list of row dicts. Missing file → []."""
    rows = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except FileNotFoundError:
        pass
    return rows


def append_log_row(path, row):
    """Append one compact JSON row. The log is append-only by contract."""
    with open(path, "a") as f:
        f.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")


def validate_float(value, lo=None, hi=None):
    """Agent-supplied numeric field → float or None. Never raises."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    if lo is not None and f < lo:
        return None
    if hi is not None and f > hi:
        return None
    return f


def validate_model_id(value):
    """Agent-reported model id → sanitized string or None."""
    if isinstance(value, str) and MODEL_ID_RE.match(value):
        return value
    return None


def check_divergence(rows, window):
    """Reward-over-optimization signature: dev lower-CI rising over the
    window while holdout is flat or falling (2% tolerance band)."""
    if len(rows) < window:
        return False
    recent = rows[-window:]
    try:
        dev_lower = [
            r["dev_ci"][0] if isinstance(r.get("dev_ci"), list) and r["dev_ci"]
            else r.get("dev_score") for r in recent
        ]
        holdout = [r["holdout_score"] for r in recent]
    except (KeyError, TypeError):
        return False
    if any(v is None for v in dev_lower) or any(v is None for v in holdout):
        return False
    dev_rising = dev_lower[-1] > dev_lower[0]
    holdout_flat_or_falling = holdout[-1] <= holdout[0] * 1.02
    return dev_rising and holdout_flat_or_falling


def harness_version(harness_dir):
    """SHA-256 over the harness tree (relative path + content per file), so
    every score is attributable to the exact scorer that produced it."""
    h = hashlib.sha256()
    for root, dirs, files in sorted(os.walk(harness_dir)):
        dirs.sort()
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, harness_dir)
            h.update(rel.encode())
            with open(fpath, "rb") as f:
                h.update(f.read())
    return h.hexdigest()[:16]


def artifact_hash(path):
    """SHA-256 a file or a directory tree with stable relative paths."""
    digest = hashlib.sha256()
    if os.path.isfile(path):
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    if os.path.isdir(path):
        for root, directories, files in os.walk(path):
            directories.sort()
            for name in sorted(files):
                file_path = os.path.join(root, name)
                relative = os.path.relpath(file_path, path).replace(os.sep, "/")
                digest.update(relative.encode("utf-8"))
                digest.update(b"\0")
                with open(file_path, "rb") as stream:
                    for chunk in iter(lambda: stream.read(65536), b""):
                        digest.update(chunk)
                digest.update(b"\0")
        return digest.hexdigest()
    raise FileNotFoundError(path)


def json_hash(document):
    """SHA-256 a JSON-compatible value using canonical serialization."""
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def audit_artifact_hashes(target_dir, judgment=None):
    """Return the audit protocol's named evidence hashes."""
    paths = {
        "goal": os.path.join(target_dir, "goal.md"),
        "eval_manifest": os.path.join(target_dir, "eval"),
        "bundle": os.path.join(target_dir, "bundle", ".lfd", "bundle-manifest.json"),
        "harness": os.path.join(target_dir, "harness"),
        "calibration": os.path.join(target_dir, "calibration-report.json"),
    }
    hashes = {name: artifact_hash(path) for name, path in paths.items()}
    if judgment is not None:
        hashes["judgment"] = json_hash(judgment)
    return hashes


def iter_targets(hub_root):
    """Yield validated registry entries from the target contract module."""
    yield from lfd_contract.iter_targets(hub_root)


def probe_floor_breaches(row, floor):
    """Operators in a row's probe result scoring below the floor."""
    operators = (row.get("probe") or {}).get("operators") or {}
    return {op: s for op, s in operators.items()
            if isinstance(s, (int, float)) and s < floor}


def parse_tag_message(raw):
    """Agent-controlled tag message (raw text) → dict of validated fields.

    This is THE trust boundary: hostile content in, only typed data out
    (validated float / [lo,hi] / clean model-id / null). Never raises.
    """
    try:
        msg = json.loads(raw)
        if not isinstance(msg, dict):
            msg = {}
    except (json.JSONDecodeError, ValueError, TypeError):
        msg = {}
    out = {field: validate_float(msg.get(field)) for field in AGENT_NUMERIC_FIELDS}
    dev_ci = msg.get("dev_ci")
    if isinstance(dev_ci, list) and len(dev_ci) == 2:
        lo = validate_float(dev_ci[0])
        hi = validate_float(dev_ci[1])
        out["dev_ci"] = [lo, hi] if lo is not None and hi is not None else None
    else:
        out["dev_ci"] = None
    out["model_id"] = validate_model_id(msg.get("model_id"))
    return out


def liveness_state(config):
    """Is the anti-vaporware gate armed for this target?

    ('configured', ...) — BUILD_CMD or HEALTH_CHECK set; the gate runs.
    ('exempt', reason)  — LIVENESS_EXEMPT gives a justified skip.
    ('unset', ...)      — neither: the empty-by-default silent-skip hole.
    """
    build = str(config_value(config, "BUILD_CMD", allow_empty=True)).strip()
    health = str(config_value(config, "HEALTH_CHECK", allow_empty=True)).strip()
    exempt = str(config_value(config, "LIVENESS_EXEMPT", allow_empty=True)).strip()
    if build or health:
        return "configured", "liveness gate armed"
    if exempt:
        return "exempt", exempt
    return "unset", ("no BUILD_CMD/HEALTH_CHECK and no LIVENESS_EXEMPT — a "
                     "facade that never builds or boots would still be scored")


def audit_state(target_dir):
    """Truth and freshness of the finalized audit protocol."""
    path = os.path.join(target_dir, "audit-report.json")
    if not os.path.isfile(path):
        if os.path.isfile(os.path.join(target_dir, "audit-mechanical.json")):
            return "incomplete", "mechanical audit exists but independent judgment is not finalized"
        return "missing", "no audit-report.json (run `bin/lfd audit mechanical <target>`)"
    try:
        with open(path) as f:
            report = json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        return "failed", "audit-report.json is not valid JSON"
    if report.get("schema_version") != 1 or report.get("state") != "complete":
        return "incomplete", "audit report is not a complete version-1 finalization"
    verdict = report.get("verdict")
    if verdict != "PASS":
        return "failed", f"audit verdict is {verdict!r}, not PASS"
    judgment = report.get("judgment")
    recorded = report.get("hashes")
    if not isinstance(judgment, dict) or not isinstance(recorded, dict):
        return "failed", "final audit is missing judgment evidence or artifact hashes"
    if (set(judgment) != {"schema_version", "independent_context_attestation", "findings"}
            or judgment.get("schema_version") != 1
            or judgment.get("independent_context_attestation") is not True
            or not isinstance(judgment.get("findings"), dict)
            or set(judgment["findings"]) != AUDIT_FINDINGS):
        return "failed", "final audit contains malformed or incomplete judgment evidence"
    for finding in judgment["findings"].values():
        if (not isinstance(finding, dict)
                or set(finding) != {"verdict", "evidence"}
                or finding.get("verdict") != "PASS"
                or not isinstance(finding.get("evidence"), str)
                or not finding["evidence"].strip()):
            return "failed", "final audit contains a failed or unsupported finding"
    try:
        current = audit_artifact_hashes(target_dir, judgment)
    except FileNotFoundError as exc:
        return "stale", f"audited artifact is missing: {exc}"
    if recorded != current:
        changed = sorted(name for name in set(recorded) | set(current)
                         if recorded.get(name) != current.get(name))
        return "stale", f"audited artifacts changed: {', '.join(changed)}"
    return "ok", "final audit PASS matches all six evidence hashes"


def calibration_state(target_dir):
    """Does the scorer provably separate known-good from known-bad output?

    ('missing'/'invalid'/'overlapping'/'ok', detail). Decisive separation =
    good's lower CI bound above bad's upper CI bound. A scorer that returns
    plausible numbers for everything is itself vaporware.
    """
    path = os.path.join(target_dir, "calibration-report.json")
    if not os.path.isfile(path):
        return "missing", "no calibration-report.json (Phase 6 known-good/known-bad run)"
    try:
        with open(path) as f:
            rep = json.load(f)
        good_ci = rep["good_ci"]
        bad_ci = rep["bad_ci"]
        assert len(good_ci) == 2 and len(bad_ci) == 2
        good_lo = float(good_ci[0])
        bad_hi = float(bad_ci[1])
    except (json.JSONDecodeError, ValueError, KeyError, TypeError, AssertionError):
        return "invalid", "calibration-report.json missing good_ci/bad_ci as [lo, hi]"
    if good_lo <= bad_hi:
        return "overlapping", (f"good CI lower bound {good_lo} does not clear bad "
                               f"CI upper bound {bad_hi} — scorer can't separate them")
    return "ok", f"good [{good_ci[0]}, {good_ci[1]}] clears bad [{bad_ci[0]}, {bad_ci[1]}]"


def activation_prerequisite_blockers(config, target_dir):
    """Every liveness, audit, and calibration reason activation must stop."""
    blockers = []
    lv, detail = liveness_state(config)
    if lv == "unset":
        blockers.append(f"liveness gate unset — {detail}")
    au, detail = audit_state(target_dir)
    if au != "ok":
        blockers.append(f"audit {au} — {detail}")
    cal, detail = calibration_state(target_dir)
    if cal != "ok":
        blockers.append(f"calibration {cal} — {detail}")
    return blockers


def activation_receipt_state(config, target_dir):
    """Validate the hub-issued receipt proving the active transition."""
    path = os.path.join(target_dir, "activation.json")
    if not os.path.isfile(path):
        return "missing", "activation receipt is missing; use `bin/lfd activate`"
    try:
        with open(path) as stream:
            receipt = json.load(stream)
    except (OSError, json.JSONDecodeError):
        return "invalid", "activation receipt is not valid JSON"
    expected_keys = {"schema_version", "target_contract_hash", "audit_report_hash",
                     "activated_at"}
    if set(receipt) != expected_keys or receipt.get("schema_version") != 1:
        return "invalid", "activation receipt has an unsupported shape or version"
    contract_path = os.path.join(target_dir, "target.json")
    audit_path = os.path.join(target_dir, "audit-report.json")
    try:
        current_contract = artifact_hash(contract_path)
        current_audit = artifact_hash(audit_path)
    except FileNotFoundError as exc:
        return "stale", f"activation evidence is missing: {exc}"
    if receipt["target_contract_hash"] != current_contract:
        return "stale", "target contract changed after activation"
    if receipt["audit_report_hash"] != current_audit:
        return "stale", "audit report changed after activation"
    return "ok", "activation receipt matches contract and audit"


def activation_blockers(config, target_dir):
    """Every reason an active target must be blocked. Non-active is ungated."""
    if config_value(config, "STATUS") != "active":
        return []
    blockers = activation_prerequisite_blockers(config, target_dir)
    receipt, detail = activation_receipt_state(config, target_dir)
    if receipt != "ok":
        blockers.append(f"activation receipt {receipt} — {detail}")
    return blockers


def sparkline(values, lo=None, hi=None):
    """Unicode sparkline for a numeric series; None values render as a gap."""
    blocks = "▁▂▃▄▅▆▇█"
    present = [v for v in values if v is not None]
    if not present:
        return ""
    lo = min(present) if lo is None else lo
    hi = max(present) if hi is None else hi
    span = (hi - lo) or 1.0
    out = []
    for v in values:
        if v is None:
            out.append(" ")
        else:
            idx = int((v - lo) / span * (len(blocks) - 1))
            out.append(blocks[max(0, min(idx, len(blocks) - 1))])
    return "".join(out)
