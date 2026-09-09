#!/usr/bin/env python3
"""Reject the removed pre-contract target creation entry point."""
import json
import sys


def main():
    print(json.dumps({
        "schema_version": 1,
        "command": "new-target",
        "target": None,
        "status": "error",
        "stage": None,
        "artifacts": [],
        "errors": [{
            "code": "unsupported_command",
            "message": "use bin/lfd onboard start <name> <repo-url>",
        }],
        "next_actions": ["run bin/lfd onboard start"],
    }, sort_keys=True))
    return 2


if __name__ == "__main__":
    sys.exit(main())
