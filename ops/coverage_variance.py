#!/usr/bin/env python3
"""coverage_variance — the code-shaped-lookup-table detector.

Two roles:
  * library — a generated harness imports `trace_lines` to fingerprint the
    code path each holdout case executes, then `variance_score` to collapse
    those fingerprints into one number.
  * CLI — `variance --stdin` takes {"fingerprints": [[...], ...]} and emits
    {"coverage_variance": x, "n_cases": k, "below_floor": bool}.

Semantics: 1.0 = every case took a disjoint path (healthy, diverse logic);
0.0 = every case took the same lines (a dispatcher over a lookup table).
It complements compressibility.py, which catches DATA lookup tables but not
a nested-branch dispatcher that grep and gzip both miss.

The score is heuristic and advisory: a low value is a patch-mode signal for
a human to look, never an automatic VOID.
"""
import argparse
import json
import sys
from itertools import combinations


def _jaccard(a, b):
    if not a and not b:
        return 1.0
    union = len(a | b)
    return len(a & b) / union if union else 1.0


def mean_pairwise_similarity(fingerprints):
    fps = [frozenset(f) for f in fingerprints]
    pairs = list(combinations(fps, 2))
    if not pairs:
        return None
    return sum(_jaccard(a, b) for a, b in pairs) / len(pairs)


def variance_score(fingerprints):
    """1 - mean pairwise Jaccard similarity. None if < 2 cases."""
    sim = mean_pairwise_similarity(fingerprints)
    return None if sim is None else round(1.0 - sim, 4)


def trace_lines(func, root=None):
    """Run func() under a line tracer; return a frozenset of (file, lineno)
    executed. `root`, if given, restricts to files whose path starts with it
    (the checkout dir), so stdlib noise doesn't dominate the fingerprint."""
    lines = set()
    this_file = __file__

    def tracer(frame, event, arg):
        frame.f_trace_lines = True
        fn = frame.f_code.co_filename
        if fn == this_file:
            return tracer
        if event in ("call", "line"):
            if root is None or fn.startswith(root):
                lines.add((fn, frame.f_lineno))
        return tracer

    old = sys.gettrace()
    sys.settrace(tracer)
    try:
        func()
    finally:
        sys.settrace(old)
    return frozenset(lines)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("variance")
    v.add_argument("--stdin", action="store_true",
                   help="read {\"fingerprints\": [[...], ...]} from stdin")
    v.add_argument("--floor", type=float, default=None)
    args = p.parse_args()

    payload = json.load(sys.stdin) if args.stdin else {}
    fingerprints = payload.get("fingerprints", [])
    score = variance_score(fingerprints)
    result = {"coverage_variance": score, "n_cases": len(fingerprints)}
    if args.floor is not None and score is not None:
        result["below_floor"] = score < args.floor
    print(json.dumps(result))


if __name__ == "__main__":
    main()
