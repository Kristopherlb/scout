#!/usr/bin/env python3
"""lfd_common — shared core for the eval hub. Pure stdlib, deterministic.

Single source of truth for: config.env parsing, log.jsonl reading/writing,
divergence detection, harness versioning, and target discovery. Both the
ops/ runtime and the tools/ CLIs import from here so the two can never
disagree about a row's meaning.
"""
import hashlib
import json
import os
import re

VALID_STATUSES = {"onboarding", "active", "paused", "retired", "example"}
PROBE_MODES = {"off", "always", "every-k", "on-divergence"}

# Row fields that arrive from the agent side (tag message) and must be
# numeric or absent — never trusted as code or free text.
AGENT_NUMERIC_FIELDS = (
    "dev_score", "reported_tokens_in", "reported_tokens_out",
    "reported_cost_usd", "reported_wall_clock",
)
# model_id is agent-reported free text; constrain to a safe charset.
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9._:/-]{1,128}$")


class ConfigError(ValueError):
    """A required target configuration value is absent or invalid."""


def config_value(config, key, *, allow_empty=False):
    """Return a required configuration value without inventing a default."""
    if key not in config:
        raise ConfigError(f"required config value {key} is missing")
    value = config[key]
    if not allow_empty and not str(value).strip():
        raise ConfigError(f"required config value {key} is empty")
    return value


def config_int(config, key, *, minimum=None):
    value = config_value(config, key)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"config value {key} must be an integer") from exc
    if minimum is not None and parsed < minimum:
        raise ConfigError(f"config value {key} must be at least {minimum}")
    return parsed


def config_float(config, key, *, minimum=None, maximum=None):
    value = config_value(config, key)
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"config value {key} must be numeric") from exc
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        raise ConfigError(f"config value {key} must be finite")
    if minimum is not None and parsed < minimum:
        raise ConfigError(f"config value {key} must be at least {minimum}")
    if maximum is not None and parsed > maximum:
        raise ConfigError(f"config value {key} must be at most {maximum}")
    return parsed


def parse_config_env(path):
    """Parse a KEY="VALUE" config.env without executing it."""
    config = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip()
            if value and value[0] in "\"'" and value[-1:] == value[0]:
                value = value[1:-1]
            config[key.strip()] = value
    return config


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


def iter_targets(hub_root):
    """Yield (name, config, target_dir) for every registered target."""
    targets_dir = os.path.join(hub_root, "targets")
    if not os.path.isdir(targets_dir):
        return
    for name in sorted(os.listdir(targets_dir)):
        target_dir = os.path.join(targets_dir, name)
        config_path = os.path.join(target_dir, "config.env")
        if os.path.isfile(config_path):
            yield name, parse_config_env(config_path), target_dir


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
    build = (config.get("BUILD_CMD") or "").strip()
    health = (config.get("HEALTH_CHECK") or "").strip()
    exempt = (config.get("LIVENESS_EXEMPT") or "").strip()
    if build or health:
        return "configured", "liveness gate armed"
    if exempt:
        return "exempt", exempt
    return "unset", ("no BUILD_CMD/HEALTH_CHECK and no LIVENESS_EXEMPT — a "
                     "facade that never builds or boots would still be scored")


def audit_state(target_dir):
    """Truth + freshness of the Phase 8.5 audit report.

    ('missing'/'failed'/'stale'/'ok', detail). 'stale' means the harness
    changed since the audit (or the report never recorded which harness it
    audited) — an audited-then-rewritten scorer is a certified Potemkin.
    """
    path = os.path.join(target_dir, "audit-report.json")
    if not os.path.isfile(path):
        return "missing", "no audit-report.json (run `bin/lfd audit <target>`)"
    try:
        with open(path) as f:
            report = json.load(f)
    except (json.JSONDecodeError, ValueError):
        return "failed", "audit-report.json is not valid JSON"
    verdict = report.get("verdict") or report.get("overall_mechanical_verdict")
    if verdict != "PASS":
        return "failed", f"audit verdict is {verdict!r}, not PASS"
    recorded = report.get("harness_version")
    current = harness_version(os.path.join(target_dir, "harness"))
    if not recorded:
        return "stale", "audit-report.json records no harness_version — can't prove it matches the current harness"
    if recorded != current:
        return "stale", (f"harness changed since audit (audited {recorded}, "
                         f"current {current}) — re-run `bin/lfd audit`")
    return "ok", f"audited at harness {current}"


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


def activation_blockers(config, target_dir):
    """Every reason an 'active' target should be blocked. Empty = clear.
    Non-active targets are never gated (return [])."""
    if config.get("STATUS") != "active":
        return []
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
