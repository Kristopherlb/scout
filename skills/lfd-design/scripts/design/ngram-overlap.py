#!/usr/bin/env python3
"""
ngram-overlap.py — reusable contamination-detection library (fuzzy tier).
Fable's per-task lint.sh should CALL this, not reimplement n-gram overlap
each time. Deterministic, task-agnostic.

Usage:
  ngram-overlap.py --solution-dir src/ --eval-answers-dir /path/to/eval/holdout \
                    --n 8 --threshold 0.4

Output: JSON — {"max_overlap": float, "flagged_files": [...], "verdict": "PASS"/"VOID"}
Exit code 1 on VOID (for use in lint.sh's own exit-code chaining).
"""
import argparse
import json
import sys
import os
import re

def ngrams(text, n):
    tokens = re.findall(r"\w+", text.lower())
    return set(tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1))

def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

def read_text_files(root):
    for dirpath, _, files in os.walk(root):
        for fname in files:
            if fname.endswith((".py", ".js", ".ts", ".md", ".txt", ".json", ".sh")):
                path = os.path.join(dirpath, fname)
                try:
                    with open(path, errors="ignore") as f:
                        yield path, f.read()
                except OSError:
                    continue

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--solution-dir", required=True)
    p.add_argument("--eval-answers-dir", required=True)
    p.add_argument("--n", type=int, default=8)
    p.add_argument("--threshold", type=float, default=0.4)
    args = p.parse_args()

    eval_ngrams = set()
    for _, text in read_text_files(args.eval_answers_dir):
        eval_ngrams |= ngrams(text, args.n)

    flagged = []
    max_overlap = 0.0
    for path, text in read_text_files(args.solution_dir):
        sol_ngrams = ngrams(text, args.n)
        overlap = jaccard(sol_ngrams, eval_ngrams)
        max_overlap = max(max_overlap, overlap)
        if overlap > args.threshold:
            flagged.append(path)

    verdict = "VOID" if flagged else "PASS"
    print(json.dumps({
        "max_overlap": round(max_overlap, 4),
        "flagged_files": flagged,
        "verdict": verdict
    }))
    sys.exit(1 if flagged else 0)

if __name__ == "__main__":
    main()
