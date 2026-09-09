#!/usr/bin/env python3
"""log_utils — the only writer/reader of log.jsonl used by ops scripts.

Every agent-supplied value crosses this boundary as a *validated datum*
(argparse arg or stdin JSON field), never as interpolated code. This is
the injection fix: bash passes strings, Python validates types, and only
typed values reach the row.

Subcommands:
  has-tag       --log L --tag T            → prints true/false
  last-ts       --log L                    → prints last row ISO timestamp or ""
  count         --log L                    → prints row count
  rows-since-probe --log L                 → rows since last row with probe data
  parse-tag-msg                            → stdin: raw tag message (JSON);
                                             stdout: validated JSON fields
  append        --log L --target-dir D ... → validate + append one row
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import lfd_common  # noqa: E402
import lfd_holdout_protocol  # noqa: E402


def cmd_has_tag(args):
    rows = lfd_common.read_log(args.log)
    print("true" if any(r.get("tag") == args.tag for r in rows) else "false")


def cmd_has_request(args):
    rows = lfd_common.read_log(args.log)
    found = any(r.get("request_id") == args.request_id and r.get("sha") == args.sha
                for r in rows)
    print("true" if found else "false")


def cmd_last_ts(args):
    rows = lfd_common.read_log(args.log)
    print(rows[-1].get("timestamp", "") if rows else "")


def cmd_count(args):
    print(len(lfd_common.read_log(args.log)))


def cmd_rows_since_probe(args):
    rows = lfd_common.read_log(args.log)
    since = 0
    for row in reversed(rows):
        if row.get("probe"):
            break
        since += 1
    else:
        since = len(rows)  # no probe row ever → force one
    print(since)


def cmd_hours_since(args):
    """Hours elapsed since the last row's timestamp; large number if none."""
    rows = lfd_common.read_log(args.log)
    if not rows or not rows[-1].get("timestamp"):
        print("999999")
        return
    try:
        last = datetime.datetime.fromisoformat(
            rows[-1]["timestamp"].replace("Z", "+00:00"))
        now = datetime.datetime.now(datetime.timezone.utc)
        print(f"{(now - last).total_seconds() / 3600:.4f}")
    except ValueError:
        print("999999")


def cmd_parse_tag_msg(_args):
    """stdin: raw agent-controlled tag message. stdout: one JSON object of
    validated fields (invalid/missing → null). Never raises on hostile input."""
    json.dump(lfd_common.parse_tag_message(sys.stdin.read()), sys.stdout)


def cmd_parse_request(args):
    try:
        parsed = lfd_holdout_protocol.validate_request(
            args.tag, sys.stdin.read(), args.prefix, args.protocol_version,
            args.actual_sha)
    except lfd_holdout_protocol.ProtocolError as exc:
        print(json.dumps({"error": {"code": exc.code,
                                    "message": exc.message}}), file=sys.stderr)
        raise SystemExit(2)
    json.dump(parsed, sys.stdout, sort_keys=True)


def cmd_append(args):
    """Validate every field, then append exactly one row."""
    rows = lfd_common.read_log(args.log)
    if not lfd_holdout_protocol.REQUEST_ID_RE.fullmatch(args.request_id):
        sys.exit("append: request_id is not 32 lowercase hexadecimal characters")

    def req_float(name, value):
        v = lfd_common.validate_float(value)
        if v is None:
            sys.exit(f"append: {name} is not a finite number: {value!r}")
        return v

    row = {
        "cycle": len(rows) + 1,
        "tag": args.tag,
        "request_id": args.request_id,
        "sha": args.sha,
        "timestamp": datetime.datetime.now(datetime.timezone.utc)
                     .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "holdout_score": req_float("holdout_score", args.holdout_score),
        "holdout_ci": [req_float("ci_low", args.ci_low),
                       req_float("ci_high", args.ci_high)],
        "liveness": args.liveness,
        "harness_version": lfd_common.harness_version(
            os.path.join(args.target_dir, "harness")),
        "hub_commit": args.hub_commit or None,
        "scoring_seconds": lfd_common.validate_float(args.scoring_seconds),
    }
    # Agent-reported fields arrive pre-validated as JSON on stdin
    # (the parse-tag-msg output), re-validated here anyway.
    if args.agent_fields:
        try:
            agent = json.loads(args.agent_fields)
        except json.JSONDecodeError:
            agent = {}
        for field in lfd_common.AGENT_NUMERIC_FIELDS:
            row[field] = lfd_common.validate_float(agent.get(field))
        ci = agent.get("dev_ci")
        row["dev_ci"] = ci if (isinstance(ci, list) and len(ci) == 2 and
                               all(lfd_common.validate_float(x) is not None
                                   for x in ci)) else None
        row["model_id"] = lfd_common.validate_model_id(agent.get("model_id"))
    if args.probe_json:
        try:
            probe = json.loads(args.probe_json)
            ops = probe.get("operators")
            if isinstance(ops, dict):
                row["probe"] = {"operators": {
                    str(k)[:64]: lfd_common.validate_float(v)
                    for k, v in list(ops.items())[:32]
                }}
        except json.JSONDecodeError:
            pass
    cov = lfd_common.validate_float(args.coverage_variance, lo=0.0, hi=1.0)
    if cov is not None:
        row["coverage_variance"] = cov

    lfd_common.append_log_row(args.log, row)
    print(row["cycle"])


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("has-tag", "has-request", "last-ts", "count", "rows-since-probe", "hours-since"):
        sp = sub.add_parser(name)
        sp.add_argument("--log", required=True)
        if name == "has-tag":
            sp.add_argument("--tag", required=True)
        elif name == "has-request":
            sp.add_argument("--request-id", required=True)
            sp.add_argument("--sha", required=True)

    sub.add_parser("parse-tag-msg")
    request = sub.add_parser("parse-request")
    request.add_argument("--tag", required=True)
    request.add_argument("--prefix", required=True)
    request.add_argument("--protocol-version", required=True, type=int)
    request.add_argument("--actual-sha", required=True)

    ap = sub.add_parser("append")
    ap.add_argument("--log", required=True)
    ap.add_argument("--target-dir", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--request-id", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--holdout-score", required=True)
    ap.add_argument("--ci-low", required=True)
    ap.add_argument("--ci-high", required=True)
    ap.add_argument("--liveness", default="ok",
                    choices=["ok", "liveness_failed", "skipped"])
    ap.add_argument("--hub-commit", default="")
    ap.add_argument("--scoring-seconds", default=None)
    ap.add_argument("--agent-fields", default="")
    ap.add_argument("--probe-json", default="")
    ap.add_argument("--coverage-variance", default=None)

    args = p.parse_args()
    {
        "has-tag": cmd_has_tag,
        "has-request": cmd_has_request,
        "last-ts": cmd_last_ts,
        "count": cmd_count,
        "rows-since-probe": cmd_rows_since_probe,
        "hours-since": cmd_hours_since,
        "parse-tag-msg": cmd_parse_tag_msg,
        "parse-request": cmd_parse_request,
        "append": cmd_append,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
