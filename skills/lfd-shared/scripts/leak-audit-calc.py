#!/usr/bin/env python3
"""
leak-audit-calc.py — Phase 4 leak audit. Deterministic replacement for
hand-written arithmetic. For a given feedback channel, computes whether
an agent could reconstruct the eval before the run ends.

Usage:
  leak-audit-calc.py --bits-per-call 4.3 --expected-cycles 50 --eval-size 246

Output: JSON with reconstructable_fraction and a PASS/FAIL against the
25% threshold used by the Phase 8.5 audit (item B).
"""
import argparse
import json

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bits-per-call", type=float, required=True,
                    help="information revealed per scoring call, in bits "
                         "(e.g. a capped miss-list of k items out of n "
                         "categories is roughly k*log2(n) bits)")
    p.add_argument("--expected-cycles", type=int, required=True)
    p.add_argument("--eval-size", type=int, required=True)
    p.add_argument("--threshold", type=float, default=0.25,
                    help="max acceptable reconstructable fraction of the "
                         "eval over the whole run")
    args = p.parse_args()

    total_bits_revealed = args.bits_per_call * args.expected_cycles
    # bits needed to fully specify one eval item's identity, rough floor:
    bits_per_item = max(1.0, __import__("math").log2(max(args.eval_size, 2)))
    items_reconstructable = total_bits_revealed / bits_per_item
    fraction = items_reconstructable / args.eval_size

    result = {
        "total_bits_revealed_over_run": total_bits_revealed,
        "eval_size": args.eval_size,
        "reconstructable_fraction": round(fraction, 4),
        "threshold": args.threshold,
        "verdict": "FAIL — cut feedback resolution or grow the eval" if fraction > args.threshold else "PASS",
    }
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
