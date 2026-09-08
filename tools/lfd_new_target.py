#!/usr/bin/env python3
"""lfd_new_target — scaffold a target registry entry.

Usage: lfd_new_target.py <name> <repo-url> [--hub-root PATH]

Creates targets/<name>/ with config.env (STATUS=onboarding), eval dirs,
an empty harness directory, and an empty append-only log. Prints the onboarding
checklist. Scoring remains unavailable until design mode writes real harnesses.
A target cannot go active until the Phase 8.5 audit report is committed
(audit-report.json) — CI enforces this.
"""
import argparse
import os
import re
import sys

CONFIG_TEMPLATE = """\
# Target configuration — the only hand-edited file in this directory.
# See docs/onboarding-a-target.md for the full walkthrough.
TARGET_NAME="{name}"
TARGET_REPO_URL="{url}"
HOLDOUT_TAG_PREFIX="holdout-check-"

# Cadence & budgets
MIN_HOURS_BETWEEN_HOLDOUT=2
DIVERGENCE_WINDOW_CYCLES=5
BUDGET_MAX_HOLDOUT_RUNS=100

# Lifecycle: onboarding | active | paused | retired | example
# CI blocks STATUS="active" until audit-report.json exists (Phase 8.5).
STATUS="onboarding"

# Hub-side holdout mutation probing: off | always | every-k | on-divergence
PROBE_ON_HOLDOUT="every-k"
PROBE_EVERY_K=3
PROBE_FLOOR=0.8

# Code-shaped lookup-table lint: score-holdout.sh may emit a
# "coverage_variance" (0=same path every case, 1=diverse paths) using
# ops/coverage_variance.py. Below this floor flags a dispatcher/facade.
COVERAGE_VARIANCE_FLOOR=0.2

# Liveness gate (anti-vaporware): run sandboxed in a fresh checkout before
# scoring. BOOT_CMD is backgrounded 5s before HEALTH_CHECK. Activation is
# BLOCKED unless BUILD_CMD or HEALTH_CHECK is set, OR LIVENESS_EXEMPT gives
# a reason — an empty gate must be a deliberate, justified choice, not a
# forgotten default.
BUILD_CMD=""
BOOT_CMD=""
HEALTH_CHECK=""
LIVENESS_EXEMPT=""
LIVENESS_TIMEOUT=600

# Isolation backend and Docker resource policy. The image is digest-pinned so a
# private hub opts into upgrades deliberately.
LFD_SANDBOX="docker"
SANDBOX_IMAGE="python:3-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6"
SANDBOX_CPUS=2
SANDBOX_MEMORY="2g"
SANDBOX_PIDS_LIMIT=512

# Declared executor model — status flags drift vs agent-reported model_id
EXECUTOR_MODEL=""

NOTES=""
"""

def main():
    p = argparse.ArgumentParser()
    p.add_argument("name")
    p.add_argument("repo_url")
    p.add_argument("--hub-root", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".."))
    args = p.parse_args()

    if not re.match(r"^[a-z0-9_][a-z0-9._-]{0,63}$", args.name):
        sys.exit("target name must be lowercase alphanumeric with ._- (max 64 chars)")

    target_dir = os.path.join(os.path.abspath(args.hub_root), "targets", args.name)
    if os.path.exists(target_dir):
        sys.exit(f"target already exists: {target_dir}")

    for sub in ("eval/dev", "eval/holdout", "harness", "retros"):
        os.makedirs(os.path.join(target_dir, sub))

    with open(os.path.join(target_dir, "config.env"), "w") as f:
        f.write(CONFIG_TEMPLATE.format(name=args.name, url=args.repo_url))
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
    Then set STATUS="active" and configure BUILD_CMD/HEALTH_CHECK.
 5. Ensure the EVAL_REPO_STATUS_TOKEN secret covers the target repo,
    configure a schedule in .github/workflows/poll-holdout.yml, and smoke-test
    one holdout-check tag end to end.

Invariant: the agent identity working in {args.repo_url}
must NEVER gain read access to this hub repo.""")


if __name__ == "__main__":
    main()
