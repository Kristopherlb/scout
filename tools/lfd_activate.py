#!/usr/bin/env python3
"""Activate a target only after all current gate evidence passes."""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfd_bundle  # noqa: E402
import lfd_common  # noqa: E402
import lfd_contract  # noqa: E402
import lfd_interface  # noqa: E402


class ActivationError(ValueError):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _write(path, document):
    with open(path, "w") as stream:
        json.dump(document, stream, indent=2, sort_keys=True)
        stream.write("\n")


def activate(target_dir):
    target_dir = os.path.abspath(target_dir)
    contract = lfd_contract.load_target(target_dir)
    lfd_bundle.verify_bundle(target_dir)
    blockers = lfd_common.activation_prerequisite_blockers(contract, target_dir)
    if blockers:
        raise ActivationError("activation_blocked", "; ".join(blockers))
    if contract["lifecycle"]["status"] not in {"onboarding", "paused", "active"}:
        raise ActivationError("invalid_lifecycle_transition",
                              f"cannot activate from {contract['lifecycle']['status']}")
    contract["lifecycle"]["status"] = "active"
    _write(os.path.join(target_dir, "target.json"), contract)
    receipt = {
        "schema_version": 1,
        "target_contract_hash": lfd_common.artifact_hash(os.path.join(target_dir, "target.json")),
        "audit_report_hash": lfd_common.artifact_hash(os.path.join(target_dir, "audit-report.json")),
        "activated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _write(os.path.join(target_dir, "activation.json"), receipt)
    refreshed = lfd_contract.load_target(target_dir)
    remaining = lfd_common.activation_blockers(refreshed, target_dir)
    if remaining:
        raise ActivationError("activation_receipt_invalid", "; ".join(remaining))
    return {"status": "active", "receipt": receipt}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    parser.add_argument("--hub-root", default=os.path.join(os.path.dirname(__file__), ".."))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    target_dir = os.path.join(os.path.abspath(args.hub_root), "targets", args.target)
    try:
        activate(target_dir)
        document = lfd_interface.envelope("activate", args.target, status="success",
                                        stage="active", artifacts=["target.json", "activation.json"])
        code = 0
    except ActivationError as exc:
        pending = exc.code == "activation_blocked"
        document = lfd_interface.envelope("activate", args.target,
                                        status="pending" if pending else "error",
                                        stage="activation_blocked" if pending else None,
                                        errors=[{"code": exc.code, "message": str(exc)}],
                                        next_actions=["resolve activation blockers"] if pending else [])
        code = 3 if pending else 2
    except (lfd_contract.ContractError, lfd_bundle.BundleError) as exc:
        document = lfd_interface.envelope("activate", args.target, status="error",
                                        errors=[{"code": getattr(exc, "code", "invalid_input"),
                                                 "message": str(exc)}])
        code = 2
    except OSError as exc:
        document = lfd_interface.envelope("activate", args.target, status="error",
                                        errors=[{"code": "infrastructure_failure",
                                                 "message": str(exc)}])
        code = 4
    if args.json:
        print(json.dumps(document, sort_keys=True))
    else:
        print(f"{document['status']}: {document.get('stage') or 'activate'}")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
