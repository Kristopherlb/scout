#!/usr/bin/env python3
"""Two-stage audit protocol: mechanical evidence, then independent judgment."""
import argparse
import datetime
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfd_common  # noqa: E402
import lfd_interface  # noqa: E402


REQUIRED_FINDINGS = tuple(sorted(lfd_common.AUDIT_FINDINGS))


class AuditError(ValueError):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path, document):
    with open(path, "w") as stream:
        json.dump(document, stream, indent=2, sort_keys=True)
        stream.write("\n")


def write_mechanical_report(target_dir, checker_output):
    """Persist checkable findings without treating them as final approval."""
    verdict = checker_output.get("overall_mechanical_verdict")
    if verdict not in {"PASS", "FAIL"}:
        raise AuditError("invalid_mechanical_report", "mechanical verdict must be PASS or FAIL")
    try:
        hashes = lfd_common.audit_artifact_hashes(target_dir)
    except FileNotFoundError as exc:
        raise AuditError("missing_audit_artifact", str(exc)) from exc
    report = {
        "schema_version": 1,
        "state": "incomplete" if verdict == "PASS" else "failed",
        "verdict": verdict,
        "mechanical_results": checker_output.get("mechanical_results", []),
        "required_independent_findings": list(REQUIRED_FINDINGS),
        "hashes": hashes,
        "audited_at": _now(),
    }
    _write(os.path.join(target_dir, "audit-mechanical.json"), report)
    return report


def _validate_judgment(judgment):
    if not isinstance(judgment, dict) or set(judgment) != {
            "schema_version", "independent_context_attestation", "findings"}:
        raise AuditError("malformed_judgment", "judgment must contain only the version, attestation, and findings")
    if judgment["schema_version"] != 1:
        raise AuditError("malformed_judgment", "unsupported judgment schema version")
    if judgment["independent_context_attestation"] is not True:
        raise AuditError("incomplete_judgment", "independent-context process attestation is required")
    findings = judgment["findings"]
    if not isinstance(findings, dict) or set(findings) != set(REQUIRED_FINDINGS):
        raise AuditError("incomplete_judgment", "all five named findings are required")
    for name, finding in findings.items():
        if not isinstance(finding, dict) or set(finding) != {"verdict", "evidence"}:
            raise AuditError("malformed_judgment", f"{name} must contain verdict and evidence")
        if finding["verdict"] not in {"PASS", "FAIL"}:
            raise AuditError("malformed_judgment", f"{name} verdict must be PASS or FAIL")
        if not isinstance(finding["evidence"], str) or not finding["evidence"].strip():
            raise AuditError("incomplete_judgment", f"{name} requires non-empty evidence")


def finalize_audit(target_dir, judgment):
    """Combine fresh mechanical evidence with explicit independent findings."""
    mechanical_path = os.path.join(target_dir, "audit-mechanical.json")
    try:
        with open(mechanical_path) as stream:
            mechanical = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError("missing_mechanical_audit", str(exc)) from exc
    if mechanical.get("schema_version") != 1 or mechanical.get("verdict") != "PASS":
        raise AuditError("mechanical_audit_failed", "a passing version-1 mechanical audit is required")
    _validate_judgment(judgment)
    current_without_judgment = lfd_common.audit_artifact_hashes(target_dir)
    if mechanical.get("hashes") != current_without_judgment:
        raise AuditError("stale_mechanical_audit", "audited artifacts changed after the mechanical pass")
    verdict = "PASS" if all(
        finding["verdict"] == "PASS" for finding in judgment["findings"].values()
    ) else "FAIL"
    report = {
        "schema_version": 1,
        "state": "complete",
        "verdict": verdict,
        "mechanical_results": mechanical.get("mechanical_results", []),
        "judgment": judgment,
        "hashes": lfd_common.audit_artifact_hashes(target_dir, judgment),
        "finalized_at": _now(),
    }
    _write(os.path.join(target_dir, "audit-report.json"), report)
    return report


def run_mechanical(hub_root, target):
    target_dir = os.path.join(os.path.abspath(hub_root), "targets", target)
    if not os.path.isdir(target_dir):
        raise AuditError("target_not_found", target)
    checker = os.path.join(hub_root, "skills", "lfd-design", "scripts", "design",
                           "audit-checklist.py")
    proc = subprocess.run([
        sys.executable, checker,
        "--goal-md", os.path.join(target_dir, "goal.md"),
        "--harness-dir", os.path.join(target_dir, "harness"),
        "--dev-harness-dir", os.path.join(target_dir, "dev-harness"),
        "--eval-dir", os.path.join(target_dir, "eval"),
    ], capture_output=True, text=True)
    if proc.returncode != 0 and not proc.stdout.strip():
        raise AuditError("mechanical_check_failed", proc.stderr.strip())
    try:
        output = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AuditError("mechanical_check_failed", "checker did not return JSON") from exc
    return write_mechanical_report(target_dir, output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hub-root", default=os.path.join(os.path.dirname(__file__), ".."))
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="verb", required=True)
    mechanical = sub.add_parser("mechanical")
    mechanical.add_argument("target")
    mechanical.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    final = sub.add_parser("finalize")
    final.add_argument("target")
    final.add_argument("--judgment-file", required=True)
    final.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    args = parser.parse_args()
    command = f"audit.{args.verb}"
    try:
        if args.verb == "mechanical":
            report = run_mechanical(args.hub_root, args.target)
            status = "pending" if report["state"] == "incomplete" else "failure"
            document = lfd_interface.envelope(command, args.target, status=status,
                                            stage=report["state"],
                                            artifacts=["audit-mechanical.json"],
                                            next_actions=["audit finalize"] if status == "pending" else [])
            code = 3 if status == "pending" else 2
        else:
            with open(args.judgment_file) as stream:
                judgment = json.load(stream)
            target_dir = os.path.join(os.path.abspath(args.hub_root), "targets", args.target)
            report = finalize_audit(target_dir, judgment)
            status = "success" if report["verdict"] == "PASS" else "failure"
            document = lfd_interface.envelope(command, args.target, status=status,
                                            stage="complete",
                                            artifacts=["audit-report.json"],
                                            next_actions=["activate"] if status == "success" else [])
            code = 0 if status == "success" else 2
    except (AuditError, OSError, json.JSONDecodeError, lfd_common.ConfigError) as exc:
        error_code = getattr(exc, "code", "invalid_input")
        document = lfd_interface.envelope(command, getattr(args, "target", None),
                                        status="error", errors=[{
                                            "code": error_code, "message": str(exc)}])
        code = 2
    if getattr(args, "json", False):
        print(json.dumps(document, sort_keys=True))
    else:
        print(f"{document['status']}: {document.get('stage') or command}")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
