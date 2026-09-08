#!/usr/bin/env python3
"""lfd_audit — run the skill's Phase 8.5 mechanical audit for a target and
stamp a hub-managed audit-report.json.

The stamp is what makes the audit *falsifiable over time*: it records the
harness_version audited, so the activation gate can detect an
audited-then-rewritten scorer (a certified Potemkin). Without the stamp, a
passing report is just a snapshot with no expiry.

Usage: lfd_audit.py <target> [--hub-root PATH]
Exit code is nonzero if the audit verdict is not PASS.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfd_common  # noqa: E402


def build_audit_report(target_dir, skill_output):
    """Merge the skill's mechanical audit with hub freshness metadata."""
    verdict = (skill_output.get("verdict")
               or skill_output.get("overall_mechanical_verdict") or "FAIL")
    report = dict(skill_output)
    report["verdict"] = verdict
    report["harness_version"] = lfd_common.harness_version(
        os.path.join(target_dir, "harness"))
    report["audited_at"] = datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("target")
    p.add_argument("--hub-root", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".."))
    args = p.parse_args()

    hub_root = os.path.abspath(args.hub_root)
    target_dir = os.path.join(hub_root, "targets", args.target)
    if not os.path.isdir(target_dir):
        sys.exit(f"no such target: {args.target}")

    checker = os.path.join(hub_root, "skills", "lfd-design",
                           "scripts", "design", "audit-checklist.py")
    proc = subprocess.run(
        [sys.executable, checker,
         "--goal-md", os.path.join(target_dir, "goal.md"),
         "--harness-dir", os.path.join(target_dir, "harness"),
         "--eval-dir", os.path.join(target_dir, "eval")],
        capture_output=True, text=True)
    if proc.returncode != 0 and not proc.stdout.strip():
        sys.exit(f"audit checker failed: {proc.stderr.strip()}")
    try:
        skill_output = json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.exit(f"audit checker produced non-JSON output:\n{proc.stdout}\n{proc.stderr}")

    report = build_audit_report(target_dir, skill_output)
    out_path = os.path.join(target_dir, "audit-report.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    print(f"audit-report.json written: verdict={report['verdict']} "
          f"harness_version={report['harness_version']}")
    for r in report.get("mechanical_results", []):
        if r.get("verdict") != "PASS":
            print(f"  {r.get('verdict')}: {r.get('item')} — {r.get('detail')}")
    if report.get("still_requires_independent_llm_judgment"):
        print("  MANUAL items still require the independent LLM auditor "
              "(see report).")
    sys.exit(0 if report["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
