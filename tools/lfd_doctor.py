#!/usr/bin/env python3
"""Environment diagnostics for local Scout operation."""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfd_contract  # noqa: E402
import lfd_interface  # noqa: E402
import lfd_onboard  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hub-root", default=os.path.join(os.path.dirname(__file__), ".."))
    parser.add_argument("--target")
    parser.add_argument("--checkout")
    parser.add_argument("--require-github", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = lfd_onboard.doctor(args.hub_root, args.target, args.checkout,
                                    args.require_github)
        failed = [check["name"] for check in result["checks"]
                  if check["status"] == "fail"]
        errors = ([{"code": "infrastructure_failure",
                    "message": "failed checks: " + ", ".join(failed)}]
                  if failed else [])
        document = lfd_interface.envelope(
            "doctor", args.target, result["status"], artifacts=result["checks"],
            errors=errors,
        )
        exit_code = 0 if result["status"] == "ok" else 4
    except (lfd_contract.ContractError, ValueError) as exc:
        document = lfd_interface.envelope(
            "doctor", args.target, "error", errors=[{
                "code": getattr(exc, "code", "invalid_input"),
                "message": str(exc),
            }],
        )
        exit_code = 2
    except (OSError, subprocess.SubprocessError) as exc:
        document = lfd_interface.envelope(
            "doctor", args.target, "error", errors=[{
                "code": "infrastructure_failure", "message": str(exc),
            }],
        )
        exit_code = 4
    if args.json:
        print(json.dumps(document, sort_keys=True))
    else:
        for check in document["artifacts"]:
            print(f"{check['status']:>8}  {check['name']}")
        for error in document["errors"]:
            print(f"error: {error['message']}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
