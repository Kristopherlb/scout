#!/usr/bin/env python3
"""lfd_review — the unscheduled human look, as a one-command habit.

Samples K random holdout cases and shows input, expected answer, and the
candidate's captured Stage-1 output side by side. Hub-side only — nothing
here is ever visible to the agent, and nothing about when you run it is
written anywhere the agent can read (that unpredictability is the point;
see SKILL.md Phase 9).

Usage: lfd_review.py <target> [--k 3] [--tag TAG] [--hub-root PATH]
"""
import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfd_common  # noqa: E402


def show_file(path, label, max_chars=2000):
    print(f"  ─ {label}: {os.path.basename(path)}")
    try:
        with open(path) as f:
            content = f.read(max_chars + 1)
        truncated = len(content) > max_chars
        content = content[:max_chars]
        for line in content.splitlines():
            print(f"    {line}")
        if truncated:
            print("    … (truncated)")
    except FileNotFoundError:
        print("    (missing)")
    except UnicodeDecodeError:
        print("    (binary)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("target")
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--tag", default=None)
    p.add_argument("--hub-root", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".."))
    args = p.parse_args()

    hub_root = os.path.abspath(args.hub_root)
    target_dir = os.path.join(hub_root, "targets", args.target)
    holdout_dir = os.path.join(target_dir, "eval", "holdout")
    if not os.path.isdir(holdout_dir):
        sys.exit(f"no holdout dir: {holdout_dir}")

    rows = lfd_common.read_log(os.path.join(target_dir, "log.jsonl"))
    tag = args.tag or (rows[-1].get("tag") if rows else None)
    runs_dir = os.path.join(target_dir, "runs", tag) if tag else None

    cases = sorted(f for f in os.listdir(holdout_dir)
                   if os.path.isfile(os.path.join(holdout_dir, f)))
    if not cases:
        sys.exit("holdout is empty — nothing to review")
    sample = random.sample(cases, min(args.k, len(cases)))

    print(f"Reviewing {len(sample)} of {len(cases)} holdout cases for "
          f"'{args.target}'" + (f" (run {tag})" if tag else " (no scored runs yet)"))
    print("=" * 72)
    for fname in sample:
        print(f"\ncase: {fname}")
        case_path = os.path.join(holdout_dir, fname)
        # JSON cases get structured display; anything else is shown raw.
        try:
            with open(case_path) as f:
                case = json.load(f)
            for key in ("input", "prompt", "question", "case"):
                if key in case:
                    print(f"  ─ input ({key}):")
                    print("    " + json.dumps(case[key], indent=2)
                          .replace("\n", "\n    "))
                    break
            for key in ("answer", "expected", "output", "label"):
                if key in case:
                    print(f"  ─ expected ({key}):")
                    print("    " + json.dumps(case[key], indent=2)
                          .replace("\n", "\n    "))
                    break
        except (json.JSONDecodeError, UnicodeDecodeError):
            show_file(case_path, "case (raw)")

        if runs_dir and os.path.isdir(runs_dir):
            stem = os.path.splitext(fname)[0]
            matches = [f for f in sorted(os.listdir(runs_dir)) if stem in f]
            if matches:
                for m in matches[:2]:
                    show_file(os.path.join(runs_dir, m), "candidate output")
            else:
                print("  ─ candidate output: none captured for this case")
        else:
            print("  ─ candidate output: no captured run "
                  "(runs/ is populated by poll-and-score)")
    print("\n" + "=" * 72)
    print("If anything above looks like memorization or a facade, invoke "
          "/lfd-design in patch mode (strongest model).")


if __name__ == "__main__":
    main()
