#!/usr/bin/env python3
"""Scaffold a target registry entry from the validated contract template.

Usage: lfd_new_target.py <name> <repo-url> [--hub-root PATH]

Creates targets/<name>/ with target.json (status=onboarding), eval dirs,
an empty harness directory, and an empty append-only log. Prints the onboarding
checklist. Scoring remains unavailable until design mode writes real harnesses.
A target cannot go active until the Phase 8.5 audit report is committed
(audit-report.json) — CI enforces this.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfd_contract  # noqa: E402

def main():
    p = argparse.ArgumentParser()
    p.add_argument("name")
    p.add_argument("repo_url")
    p.add_argument("--hub-root", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".."))
    args = p.parse_args()

    try:
        contract = lfd_contract.new_contract(args.name, args.repo_url)
    except lfd_contract.ContractError as exc:
        sys.exit(str(exc))

    target_dir = os.path.join(os.path.abspath(args.hub_root), "targets", args.name)
    if os.path.exists(target_dir):
        sys.exit(f"target already exists: {target_dir}")

    for sub in ("eval/dev", "eval/holdout", "harness", "retros"):
        os.makedirs(os.path.join(target_dir, sub))

    with open(os.path.join(target_dir, "target.json"), "w") as f:
        json.dump(contract, f, indent=2)
        f.write("\n")
    open(os.path.join(target_dir, "log.jsonl"), "w").close()
    with open(os.path.join(target_dir, "canary-list.json"), "w") as f:
        f.write('{\n  "run_id": null,\n  "canaries": []\n}\n')

    rel = os.path.relpath(target_dir, os.path.abspath(args.hub_root))
    print(f"""Scaffolded {rel} (STATUS=onboarding)

Onboarding checklist (full guide: docs/onboarding-a-target.md):
 1. Run the LFD design skill from the hub to build {rel}/eval/dev,
    {rel}/eval/holdout, and write both harness scripts.
 2. ops/generate-canaries.sh {rel}
 3. Copy templates/target-repo/. plus the skill's
    references/agent-instructions.md and the generated goal.md into the
    target repo; commit there.
 4. Run the Phase 8.5 audit; commit its output as {rel}/audit-report.json.
    Then set lifecycle.status to active only after configuring liveness.
 5. Ensure the EVAL_REPO_STATUS_TOKEN secret covers the target repo,
    configure a schedule in .github/workflows/poll-holdout.yml, and smoke-test
    one holdout-check tag end to end.

Invariant: the agent identity working in {args.repo_url}
must NEVER gain read access to this hub repo.""")


if __name__ == "__main__":
    main()
