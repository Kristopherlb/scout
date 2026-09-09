#!/usr/bin/env python3
"""
power-calc.py — Phase 3 eval sizing. Deterministic replacement for
hand-computed arithmetic. Given the acceptance bar and the resolution/
confidence the user specified in Phase 1, compute the required holdout N.

Usage:
  power-calc.py --bar 0.80 --delta 0.05 --confidence 0.95

Output: JSON with derived_n and the worked formula, so it can be pasted
directly into LOG.md's header and goal.md's Target section per SKILL.md.
"""
import argparse
import json
import math

Z = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bar", type=float, required=True,
                    help="acceptance bar, e.g. 0.80")
    p.add_argument("--delta", type=float, required=True,
                    help="smallest score difference to distinguish, e.g. 0.05")
    p.add_argument("--confidence", type=float, default=0.95,
                    choices=[0.90, 0.95, 0.99])
    args = p.parse_args()

    z = Z[args.confidence]
    p_hat = args.bar
    n = math.ceil((z**2 * p_hat * (1 - p_hat)) / (args.delta ** 2))

    result = {
        "derived_n": n,
        "formula": f"N = ceil(z^2 * p(1-p) / delta^2) = ceil({z}^2 * {p_hat}*{1-p_hat:.2f} / {args.delta}^2)",
        "bar": args.bar,
        "delta": args.delta,
        "confidence": args.confidence,
        "note": "Floor, not a target. If obtainable cases < derived_n, "
                "widen collection or relax delta/confidence — do not "
                "proceed silently under this number."
    }
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
