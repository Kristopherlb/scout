#!/usr/bin/env python3
"""Execute the public _example lifecycle in an isolated temporary hub."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfd_interface  # noqa: E402


class WalkthroughError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _run(command, *, cwd, env=None, expected=(0,)):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                            text=True)
    if result.returncode not in expected:
        detail = result.stderr.strip() or result.stdout.strip()
        raise WalkthroughError("walkthrough_command_failed",
                               f"{' '.join(command)}: {detail}")
    return result


def _git_fixture(path):
    _run(["git", "init", "-q", "-b", "main"], cwd=path)
    _run(["git", "config", "user.name", "Scout Walkthrough"], cwd=path)
    _run(["git", "config", "user.email", "walkthrough@example.invalid"], cwd=path)
    _run(["git", "add", "solution.py"], cwd=path)
    _run(["git", "commit", "-q", "-m", "fixture"], cwd=path)


def execute(source_root):
    artifacts = []
    with tempfile.TemporaryDirectory(prefix="scout-walkthrough-") as temporary:
        hub = os.path.join(temporary, "scout")
        shutil.copytree(source_root, hub, ignore=shutil.ignore_patterns(
            ".git", ".mypy_cache", ".ruff_cache", ".venv", "__pycache__",
            "*.egg-info", "*.pyc", ".coverage", "dashboard"))
        target = os.path.join(hub, "targets", "_example")
        for name in ("audit-mechanical.json", "audit-report.json", "activation.json"):
            path = os.path.join(target, name)
            if os.path.isfile(path):
                os.remove(path)
        contract_path = os.path.join(target, "target.json")
        with open(contract_path) as stream:
            contract = json.load(stream)
        contract["lifecycle"]["status"] = "onboarding"
        with open(contract_path, "w") as stream:
            json.dump(contract, stream, indent=2, sort_keys=True)
            stream.write("\n")

        contract_result = _run([
            sys.executable, os.path.join(hub, "tools", "lfd_contract.py"),
            "get", "--target-dir", target, "--field", "identity.name"], cwd=hub)
        if contract_result.stdout.strip() != "_example":
            raise WalkthroughError("contract_mismatch", "fixture identity did not validate")
        artifacts.append({"stage": "contract_valid"})

        verify = _run([os.path.join(hub, "bin", "lfd"), "onboard", "verify",
                       "_example", "--json"], cwd=hub)
        if json.loads(verify.stdout)["status"] != "ok":
            raise WalkthroughError("bundle_invalid", "bundle verification did not succeed")
        artifacts.append({"stage": "bundle_verified"})

        good = os.path.join(temporary, "good")
        bad = os.path.join(temporary, "bad")
        shutil.copytree(os.path.join(target, "reference-target"), good)
        shutil.copytree(os.path.join(target, "reference-target-bad"), bad)
        _git_fixture(good)
        _git_fixture(bad)
        dev = _run([os.path.join(target, "dev-harness", "score-dev.sh"), good], cwd=hub)
        dev_result = json.loads(dev.stdout)
        if dev_result.get("score") != 1.0:
            raise WalkthroughError("dev_score_failed", "known-good target did not score 1.0")
        artifacts.append({"stage": "dev_scored", "score": dev_result["score"]})

        sandbox_env = dict(os.environ)
        sandbox_env.update({"LFD_SANDBOX": "none",
                            "RUN_SANDBOXED": os.path.join(hub, "ops", "run-sandboxed.sh"),
                            "HUB_ROOT": hub})
        score_command = os.path.join(target, "harness", "score-holdout.sh")
        good_result = json.loads(_run([score_command, good], cwd=hub,
                                      env=sandbox_env).stdout)
        bad_result = json.loads(_run([score_command, bad], cwd=hub,
                                     env=sandbox_env).stdout)
        with open(os.path.join(target, "calibration-report.json")) as stream:
            expected_calibration = json.load(stream)
        observed = (good_result["score"], good_result["ci_low"], good_result["ci_high"],
                    bad_result["score"], bad_result["ci_low"], bad_result["ci_high"])
        expected = (expected_calibration["good_score"], *expected_calibration["good_ci"],
                    expected_calibration["bad_score"], *expected_calibration["bad_ci"])
        if observed != expected:
            raise WalkthroughError("calibration_mismatch", "committed calibration does not match executable fixtures")
        artifacts.append({"stage": "calibration_verified"})

        mechanical = _run([os.path.join(hub, "bin", "lfd"), "audit", "mechanical",
                           "_example", "--json"], cwd=hub, expected=(3,))
        if json.loads(mechanical.stdout)["stage"] != "incomplete":
            raise WalkthroughError("mechanical_state_invalid", "mechanical PASS was not incomplete")
        artifacts.append({"stage": "mechanical_incomplete"})

        refused = _run([os.path.join(hub, "bin", "lfd"), "activate", "_example",
                        "--json"], cwd=hub, expected=(3,))
        refusal = json.loads(refused.stdout)
        if refusal["errors"][0]["code"] != "activation_blocked":
            raise WalkthroughError("activation_not_refused", "incomplete audit did not block activation")
        artifacts.append({"stage": "activation_refused"})

        finalized = _run([
            os.path.join(hub, "bin", "lfd"), "audit", "finalize", "_example",
            "--judgment-file", os.path.join(target, "fixture-judgment.json"), "--json"],
            cwd=hub)
        if json.loads(finalized.stdout)["status"] != "success":
            raise WalkthroughError("audit_finalize_failed", "fixture judgment did not finalize")
        artifacts.append({"stage": "audit_finalized"})

        activated = _run([os.path.join(hub, "bin", "lfd"), "activate", "_example",
                          "--json"], cwd=hub)
        if json.loads(activated.stdout)["stage"] != "active":
            raise WalkthroughError("activation_failed", "valid evidence did not activate")
        artifacts.append({"stage": "activation_succeeded"})
    return artifacts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hub-root", default=os.path.join(os.path.dirname(__file__), ".."))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        artifacts = execute(os.path.abspath(args.hub_root))
        document = lfd_interface.envelope("walkthrough", "_example", "success",
                                          "active", artifacts=artifacts)
        code = 0
    except (WalkthroughError, OSError, json.JSONDecodeError,
            subprocess.SubprocessError) as exc:
        document = lfd_interface.envelope("walkthrough", "_example", "error",
                                          errors=[{"code": getattr(exc, "code", "infrastructure_failure"),
                                                   "message": str(exc)}])
        code = 4
    if args.json:
        print(json.dumps(document, sort_keys=True))
    else:
        for artifact in document["artifacts"]:
            print(f"ok  {artifact['stage']}")
        print(document["status"])
    return code


if __name__ == "__main__":
    sys.exit(main())
