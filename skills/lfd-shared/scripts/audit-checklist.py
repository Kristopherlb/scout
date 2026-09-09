#!/usr/bin/env python3
"""
audit-checklist.py — independent audit mechanical pass. Runs the checkable items
from references/audit-checklist.md deterministically, so the independent
audit context spends its judgment only on what's genuinely subjective
(does this fence's TYPE actually match this cheat's TYPE — a semantic
call, not a grep). Everything else here is counting, grepping, and file
existence — no LLM call in this script.

Usage:
  audit-checklist.py --goal-md goal.md --harness-dir harness/ \
    --dev-harness-dir dev-harness/ --eval-dir eval/

Output: JSON per-item PASS/FAIL/MANUAL (MANUAL = needs the independent
LLM auditor's read, listed separately so it isn't silently skipped).
"""
import argparse
import json
import os
import re

BANNED_PRODUCT_TERMS = [
    "github actions", "gitlab ci", "circleci", "jenkins", "temporal",
    "kubernetes", "docker", "aws lambda", "cloudflare", "vercel",
    "sidecar", "istio", "linkerd",
]

def check_constraint_instrument_pairing(goal_text, harness_dir, dev_harness_dir):
    constraints_section = re.search(
        r"## Constraints\n(.*?)(?=\n## )", goal_text, re.S)
    if not constraints_section:
        return {"item": "A. constraint-instrument pairing",
                "verdict": "FAIL", "detail": "no Constraints section found"}
    lines = [line.strip("- ").strip()
             for line in constraints_section.group(1).splitlines()
             if line.strip().startswith("-")]
    lint_text = ""
    for score_path in (os.path.join(dev_harness_dir, "score-dev.sh"),
                       os.path.join(harness_dir, "score-holdout.sh"),
                       os.path.join(harness_dir, "probe-holdout.sh")):
        if os.path.exists(score_path):
            with open(score_path) as f:
                lint_text += f.read()
    unpaired = []
    for line in lines:
        # heuristic: does any word from the constraint line appear as a
        # function name or comment in lint.sh?
        key_terms = re.findall(r"[a-zA-Z_]{4,}", line.lower())
        if not any(term in lint_text.lower() for term in key_terms):
            unpaired.append(line)
    return {
        "item": "A. constraint-instrument pairing",
        "verdict": "FAIL" if unpaired else "PASS",
                "detail": f"{len(unpaired)}/{len(lines)} constraints have no obvious score-dev.sh match: {unpaired}" if unpaired else f"all {len(lines)} constraints matched"
    }

def check_infra_agnosticism(goal_text):
    hits = [term for term in BANNED_PRODUCT_TERMS if term in goal_text.lower()]
    return {
        "item": "D0. infra-agnosticism",
        "verdict": "FAIL" if hits else "PASS",
        "detail": f"named products/mechanisms found in goal.md: {hits}" if hits else "no product/mechanism names found"
    }

def check_eval_sizing(goal_text, eval_dir):
    holdout_dir = os.path.join(eval_dir, "holdout")
    actual_n = 0
    if os.path.isdir(holdout_dir):
        actual_n = len([f for f in os.listdir(holdout_dir) if f.endswith(".json")])
    m = re.search(r"Holdout size:\s*(\d+)", goal_text)
    derived_n = int(m.group(1)) if m else None
    if derived_n is None:
        return {"item": "D. eval sizing", "verdict": "FAIL",
                 "detail": "no 'Holdout size: N' line found in goal.md Target section"}
    return {
        "item": "D. eval sizing",
        "verdict": "PASS" if actual_n >= derived_n else "FAIL",
        "detail": f"actual holdout N={actual_n}, derived/required N={derived_n}"
    }

def check_canaries_present(eval_dir):
    holdout_dir = os.path.join(eval_dir, "holdout")
    if not os.path.isdir(holdout_dir):
        return {"item": "D. canary coverage", "verdict": "FAIL", "detail": "no holdout dir"}
    files = [f for f in os.listdir(holdout_dir) if f.endswith(".json")]
    missing = []
    for f in files:
        with open(os.path.join(holdout_dir, f)) as fh:
            item = json.load(fh)
        if "_canary" not in item:
            missing.append(f)
    return {
        "item": "D. canary coverage",
        "verdict": "FAIL" if missing else "PASS",
        "detail": f"{len(missing)}/{len(files)} holdout items missing a canary" if missing else f"all {len(files)} holdout items carry a canary"
    }

def check_interval_discipline(harness_dir):
    score_path = os.path.join(harness_dir, "score-holdout.sh")
    if not os.path.exists(score_path):
        return {"item": "E. interval discipline", "verdict": "FAIL", "detail": "no score-holdout.sh"}
    with open(score_path) as f:
        text = f.read().lower()
    has_interval = any(term in text for term in ["ci_low", "ci_high", "confidence", "bootstrap", "interval"])
    return {
        "item": "E. interval discipline",
        "verdict": "PASS" if has_interval else "FAIL",
        "detail": "score-holdout.sh references an uncertainty/range mechanism" if has_interval else "score-holdout.sh has no visible uncertainty computation"
    }

def check_probe_lint_completeness(harness_dir, dev_harness_dir):
    required = ["capacity_caps", "canary_scan", "ngram_overlap", "compressibility", "diff_scope"]
    text = ""
    for path in (os.path.join(dev_harness_dir, "score-dev.sh"),
                 os.path.join(harness_dir, "score-holdout.sh"),
                 os.path.join(harness_dir, "probe-holdout.sh")):
        if os.path.exists(path):
            with open(path) as f:
                text += f.read()
    missing = [r for r in required if r not in text]
    probe_path = os.path.join(harness_dir, "probe-holdout.sh")
    has_probe = os.path.exists(probe_path)
    return {
        "item": "F. probe/lint completeness",
        "verdict": "FAIL" if (missing or not has_probe) else "PASS",
        "detail": f"scorers missing named guardrails: {missing}; probe-holdout.sh present: {has_probe}"
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--goal-md", default="goal.md")
    p.add_argument("--harness-dir", default="harness")
    p.add_argument("--dev-harness-dir", default="dev-harness")
    p.add_argument("--eval-dir", default="eval")
    args = p.parse_args()

    with open(args.goal_md) as f:
        goal_text = f.read()

    results = [
        check_constraint_instrument_pairing(goal_text, args.harness_dir,
                                            args.dev_harness_dir),
        check_infra_agnosticism(goal_text),
        check_eval_sizing(goal_text, args.eval_dir),
        check_canaries_present(args.eval_dir),
        check_interval_discipline(args.harness_dir),
        check_probe_lint_completeness(args.harness_dir, args.dev_harness_dir),
    ]

    manual_items = [
        "B. leak-audit arithmetic correctness (run leak-audit-calc.py, "
        "but judging whether bits-per-call was estimated honestly needs a read)",
        "C. Goodhart type<->fence family matching (semantic judgment per cheat)",
        "E.2 calibration gap quality (known-good/known-bad separation, "
        "needs the actual calibration run output)",
        "G. escalation wiring quality and patch-mode routing statement",
        "H. blinding verification (agent-visible bundle contains no private evidence)",
    ]

    overall = "PASS" if all(r["verdict"] == "PASS" for r in results) else "FAIL"

    print(json.dumps({
        "mechanical_results": results,
        "overall_mechanical_verdict": overall,
        "still_requires_independent_llm_judgment": manual_items
    }, indent=2))

if __name__ == "__main__":
    main()
