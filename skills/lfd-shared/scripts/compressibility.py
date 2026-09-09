#!/usr/bin/env python3
"""
compressibility.py — reusable structural lookup-table detector. Scout's
per-task lint.sh should CALL this, not reimplement it. Deterministic,
task-agnostic. Tracks compressed-solution-size-vs-eval-size across cycles;
a genuine solution's compressed size stays roughly flat as the eval grows,
a lookup table's tracks it linearly.

Usage:
  compressibility.py --solution-dir src/ --eval-size 246 \
                      --history-file .compressibility-history.jsonl \
                      --cycle 14

Output: JSON — {"compressed_bytes": int, "ratio_to_eval_size": float,
                 "trend": "flat"/"linear"/"insufficient_history", "verdict": "PASS"/"FLAG"}
Appends a row to the history file each call — this IS the deterministic
state, no separate tracking needed elsewhere.
"""
import argparse
import gzip
import json
import os


def compressed_size(root):
    total = 0
    for dirpath, _, files in os.walk(root):
        for fname in files:
            path = os.path.join(dirpath, fname)
            try:
                with open(path, "rb") as f:
                    total += len(gzip.compress(f.read()))
            except OSError:
                continue
    return total

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--solution-dir", required=True)
    p.add_argument("--eval-size", type=int, required=True)
    p.add_argument("--history-file", required=True)
    p.add_argument("--cycle", type=int, required=True)
    p.add_argument("--slope-threshold", type=float, required=True,
                    help="flag if compressed-size-vs-eval-size ratio grows "
                         "by more than this fraction relative to its "
                         "first recorded value")
    args = p.parse_args()
    if args.eval_size < 1:
        p.error("--eval-size must be at least 1")
    if args.cycle < 1:
        p.error("--cycle must be at least 1")
    if args.slope_threshold < 0:
        p.error("--slope-threshold must be non-negative")

    size = compressed_size(args.solution_dir)
    ratio = size / max(args.eval_size, 1)

    history = []
    if os.path.exists(args.history_file):
        with open(args.history_file) as f:
            history = [json.loads(line) for line in f if line.strip()]

    trend = "insufficient_history"
    verdict = "PASS"
    if history:
        first_ratio = history[0]["ratio_to_eval_size"]
        if first_ratio > 0 and ratio > first_ratio * (1 + args.slope_threshold):
            trend = "linear"
            verdict = "FLAG"
        else:
            trend = "flat"

    with open(args.history_file, "a") as f:
        f.write(json.dumps({
            "cycle": args.cycle, "compressed_bytes": size,
            "ratio_to_eval_size": ratio
        }) + "\n")

    print(json.dumps({
        "compressed_bytes": size,
        "ratio_to_eval_size": round(ratio, 4),
        "trend": trend,
        "verdict": verdict
    }))

if __name__ == "__main__":
    main()
