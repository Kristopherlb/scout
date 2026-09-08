#!/usr/bin/env python3
"""ci_checks — policy gates run in CI (and locally via `python3 tools/ci_checks.py`).

Checks:
  activation-gate   every STATUS="active" target has audit-report.json
  zero-deps         no dependency manifests appear without explicit override
  public-release    public source contains fixtures only, never real eval data
  append-only-log   no committed diff edits/deletes existing log.jsonl lines
  all               activation-gate plus zero-deps (append-only-log only when
                    a diff range is supplied; public-release is explicit)
"""
import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfd_common  # noqa: E402

# Blanket-flagged: their mere presence implies a dependency install step.
DEP_MANIFESTS = ("requirements.txt", "requirements-dev.txt",
                 "package.json", "Gemfile", "Cargo.toml", "go.mod")
PUBLIC_FORBIDDEN_ROOT_ARTIFACTS = (".coverage", ".compressibility-history.jsonl")
PRIVATE_EVAL_FILENAMES = {
    "audit-report.json", "calibration-report.json", "canary-list.json",
    "config.env", "target.json", "log.jsonl",
}


def _is_tracked(hub_root, relative_path):
    inside = subprocess.run(
        ["git", "-C", hub_root, "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True)
    if inside.returncode != 0:
        return os.path.exists(os.path.join(hub_root, relative_path))
    tracked = subprocess.run(
        ["git", "-C", hub_root, "ls-files", "--error-unmatch", "--", relative_path],
        capture_output=True, text=True)
    return tracked.returncode == 0


def _pyproject_declares_runtime_deps(path):
    """pyproject.toml is fine for dev-tool config ([tool.*]); it only breaks
    the zero-runtime-dependency policy if it declares actual deps. Text scan
    (not tomllib) to stay Python-version-agnostic."""
    with open(path) as f:
        text = f.read()
    if re.search(r"(?m)^\s*\[tool\.poetry\.dependencies\]", text):
        return True
    # [project] ... dependencies = [ ... with a non-empty list
    proj = re.search(r"(?ms)^\[project\].*?(?=^\[|\Z)", text)
    if proj:
        m = re.search(r"(?ms)^\s*dependencies\s*=\s*\[(.*?)\]", proj.group(0))
        if m and m.group(1).strip():
            return True
    return False


def check_activation_gate(hub_root):
    """An 'active' target must clear liveness, audit (truth + freshness),
    and calibration gates — the three silent-skip holes that let a facade
    look production-ready."""
    failures = []
    for name, config, target_dir in lfd_common.iter_targets(hub_root):
        for blocker in lfd_common.activation_blockers(config, target_dir):
            failures.append(f"targets/{name}: STATUS=\"active\" but {blocker}")
    return failures


def check_zero_deps(hub_root):
    if os.path.isfile(os.path.join(hub_root, ".allow-deps")):
        return []
    failures = []
    for root, dirs, files in os.walk(hub_root):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "runs")]
        for f in files:
            path = os.path.join(root, f)
            rel = os.path.relpath(path, hub_root)
            hit = (f in DEP_MANIFESTS or
                   (f == "pyproject.toml" and _pyproject_declares_runtime_deps(path)))
            if hit:
                failures.append(
                    f"{rel}: runtime dependency manifest found — this hub is "
                    "stdlib-only by policy. If intentional, commit an .allow-deps "
                    "file at the repo root explaining why.")
    return failures


def check_public_release(hub_root):
    """Reject data that belongs only in a private operational deployment.

    Public source may ship only the exact synthetic ``targets/_example``
    fixture. Real target data or eval-shaped files elsewhere would disclose
    evaluation material and invalidate the repository's security boundary.
    """
    failures = []
    targets_dir = os.path.join(hub_root, "targets")
    if os.path.isdir(targets_dir):
        for name in sorted(os.listdir(targets_dir)):
            path = os.path.join(targets_dir, name)
            if os.path.isdir(path) and name != "_example":
                failures.append(
                    f"targets/{name}: real evaluation campaign found in public source — "
                    "move it to a private operational repository")
    for root, dirs, files in os.walk(hub_root):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        rel_root = os.path.relpath(root, hub_root)
        example_root = os.path.join("targets", "_example")
        if rel_root == "targets":
            dirs[:] = [d for d in dirs if d == "_example"]
            continue
        if rel_root == example_root or rel_root.startswith(example_root + os.sep):
            dirs[:] = []
            continue
        parts = set(rel_root.split(os.sep))
        for filename in files:
            rel = os.path.relpath(os.path.join(root, filename), hub_root)
            if filename in PRIVATE_EVAL_FILENAMES or parts.intersection({"eval", "holdout"}):
                failures.append(
                    f"{rel}: private-eval-shaped file found outside targets/_example")
    for name in PUBLIC_FORBIDDEN_ROOT_ARTIFACTS:
        if _is_tracked(hub_root, name):
            failures.append(
                f"{name}: generated local artifact found in public source — remove it")
    return sorted(set(failures))


def check_append_only_log(hub_root, diff_range):
    """Any removed line in a targets/*/log.jsonl diff is a history rewrite."""
    out = subprocess.run(
        ["git", "-C", hub_root, "diff", diff_range, "--", "targets/*/log.jsonl"],
        capture_output=True, text=True)
    if out.returncode != 0:
        return [f"append-only-log: git diff failed for range {diff_range!r}: "
                f"{out.stderr.strip()}"]
    failures = []
    current = None
    exempt = False
    for line in out.stdout.splitlines():
        if line.startswith("--- a/"):
            current = line[6:]
            # underscore-prefixed targets (e.g. _example) are fixtures,
            # regenerated by design — the provenance rule is for real evals.
            exempt = "/targets/_" in ("/" + current)
        elif not exempt and line.startswith("-") and not line.startswith("---"):
            failures.append(
                f"{current}: existing log line edited or deleted — log.jsonl is "
                "append-only (provenance). Revert the rewrite; corrections get "
                "a new row, never an edit.")
    return sorted(set(failures))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("check", choices=["activation-gate", "zero-deps", "public-release",
                                     "append-only-log", "all"], nargs="?",
                   default="all")
    p.add_argument("--hub-root", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".."))
    p.add_argument("--diff-range", default=None,
                   help="e.g. origin/main...HEAD (required for append-only-log)")
    args = p.parse_args()
    hub_root = os.path.abspath(args.hub_root)

    failures = []
    if args.check in ("activation-gate", "all"):
        failures += check_activation_gate(hub_root)
    if args.check in ("zero-deps", "all"):
        failures += check_zero_deps(hub_root)
    if args.check == "public-release":
        failures += check_public_release(hub_root)
    if args.check == "append-only-log" or (args.check == "all" and args.diff_range):
        if not args.diff_range:
            sys.exit("append-only-log needs --diff-range")
        failures += check_append_only_log(hub_root, args.diff_range)

    for f in failures:
        print(f"FAIL: {f}")
    if failures:
        sys.exit(1)
    print(f"ci_checks [{args.check}]: OK")


if __name__ == "__main__":
    main()
