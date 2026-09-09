#!/usr/bin/env python3
"""check-divergence.py — reward-over-optimization detector (thin CLI).
Deterministic. Reads log.jsonl only. Prints "true" or "false" to stdout.

The detection logic lives in tools/lfd_common.check_divergence so the
status CLI and dashboard can never disagree with the poll job about what
counts as divergence.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import lfd_common  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--window", type=int, required=True)
    p.add_argument("--log", required=True)
    args = p.parse_args()
    rows = lfd_common.read_log(args.log)
    print("true" if lfd_common.check_divergence(rows, args.window) else "false")


if __name__ == "__main__":
    main()
