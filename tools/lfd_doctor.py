#!/usr/bin/env python3
"""Environment diagnostics for local Scout operation."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfd_onboard  # noqa: E402
import lfd_interface  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hub-root", default=os.path.join(os.path.dirname(__file__), ".."))
    parser.add_argument("--target")
    parser.add_argument("--checkout")
    parser.add_argument("--require-github", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = lfd_onboard.doctor(args.hub_root, args.target, args.checkout,
                                args.require_github)
    document = lfd_interface.envelope("doctor", args.target, result["status"],
                                      artifacts=result["checks"])
    if args.json:
        print(json.dumps(document, sort_keys=True))
    else:
        for check in result["checks"]:
            print(f"{check['status']:>8}  {check['name']}")
    return 0 if result["status"] == "ok" else 4


if __name__ == "__main__":
    sys.exit(main())
