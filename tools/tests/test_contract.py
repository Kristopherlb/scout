#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
HUB_ROOT = os.path.abspath(os.path.join(TESTS_DIR, "..", ".."))
sys.path.insert(0, os.path.join(HUB_ROOT, "tools"))

import lfd_contract  # noqa: E402


def valid_contract(name="demo", status="onboarding"):
    return {
        "schema_version": 1,
        "identity": {
            "name": name,
            "repository_url": "https://github.com/example/demo.git",
        },
        "lifecycle": {"status": status},
        "holdout": {
            "protocol_version": 1,
            "tag_prefix": "holdout-check-",
            "min_hours_between": 2,
            "max_runs": 100,
        },
        "detectors": {
            "divergence": {"window_cycles": 5, "enforcement": "advisory"},
            "probe": {
                "mode": "every-k",
                "every_k": 3,
                "floor": 0.8,
                "enforcement": "advisory",
            },
            "coverage_variance": {"floor": 0.2, "enforcement": "advisory"},
        },
        "liveness": {
            "build_command": "",
            "boot_command": "",
            "health_check": "",
            "exemption": "onboarding",
            "timeout_seconds": 600,
        },
        "sandbox": {
            "backend": "docker",
            "image": "python:3-slim@sha256:" + "a" * 64,
            "cpus": 2,
            "memory": "2g",
            "pids_limit": 512,
        },
        "executor": {"model": ""},
        "notes": "",
    }


class TestTargetContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.target = os.path.join(self.tmp, "targets", "demo")
        os.makedirs(self.target)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write(self, payload=None):
        with open(os.path.join(self.target, "target.json"), "w") as f:
            json.dump(payload or valid_contract(), f)

    def test_loads_strict_nested_contract(self):
        self.write()
        contract = lfd_contract.load_target(self.target)
        self.assertEqual(lfd_contract.value(contract, "lifecycle.status"), "onboarding")
        self.assertEqual(lfd_contract.value(contract, "holdout.max_runs"), 100)

    def test_rejects_unknown_field(self):
        payload = valid_contract()
        payload["mystery"] = True
        self.write(payload)
        with self.assertRaises(lfd_contract.ContractError) as raised:
            lfd_contract.load_target(self.target)
        self.assertEqual(raised.exception.code, "unknown_field")

    def test_rejects_missing_field(self):
        payload = valid_contract()
        del payload["sandbox"]["image"]
        self.write(payload)
        with self.assertRaises(lfd_contract.ContractError) as raised:
            lfd_contract.load_target(self.target)
        self.assertEqual(raised.exception.code, "missing_field")

    def test_rejects_legacy_config(self):
        with open(os.path.join(self.target, "config.env"), "w") as f:
            f.write('STATUS="onboarding"\n')
        with self.assertRaises(lfd_contract.ContractError) as raised:
            lfd_contract.load_target(self.target)
        self.assertEqual(raised.exception.code, "legacy_contract")

    def test_rejects_control_characters_in_repository_url(self):
        payload = valid_contract()
        payload["identity"]["repository_url"] = "https://example.test/repo.git\nMALICIOUS=1"
        self.write(payload)
        with self.assertRaises(lfd_contract.ContractError) as raised:
            lfd_contract.load_target(self.target)
        self.assertEqual(raised.exception.code, "invalid_value")

    def test_rejects_target_name_directory_mismatch(self):
        payload = valid_contract(name="somewhere-else")
        self.write(payload)
        with self.assertRaises(lfd_contract.ContractError) as raised:
            lfd_contract.load_target(self.target)
        self.assertEqual(raised.exception.code, "identity_mismatch")

    def test_iter_targets_reads_target_json_only(self):
        self.write()
        found = list(lfd_contract.iter_targets(self.tmp))
        self.assertEqual([(name, path) for name, _, path in found],
                         [("demo", self.target)])

    def test_shell_adapter_is_nul_delimited_data(self):
        self.write()
        proc = subprocess.run(
            [sys.executable, os.path.join(HUB_ROOT, "tools", "lfd_contract.py"),
             "shell", "--target-dir", self.target],
            capture_output=True, check=True)
        fields = proc.stdout.split(b"\0")
        self.assertEqual(fields[-1], b"")
        values = dict(zip((x.decode() for x in fields[0::2]),
                          (x.decode() for x in fields[1::2])))
        self.assertEqual(values["TARGET_REPO_URL"],
                         "https://github.com/example/demo.git")
        self.assertEqual(values["STATUS"], "onboarding")
        self.assertEqual(values["HOLDOUT_PROTOCOL_VERSION"], "1")
        self.assertEqual(values["DIVERGENCE_ENFORCEMENT"], "advisory")
        self.assertEqual(values["PROBE_ENFORCEMENT"], "advisory")
        self.assertEqual(values["COVERAGE_VARIANCE_ENFORCEMENT"], "advisory")

    def test_get_adapter_returns_one_validated_value(self):
        self.write()
        proc = subprocess.run(
            [sys.executable, os.path.join(HUB_ROOT, "tools", "lfd_contract.py"),
             "get", "--target-dir", self.target, "--field", "sandbox.image"],
            capture_output=True, text=True, check=True)
        self.assertEqual(proc.stdout.strip(), "python:3-slim@sha256:" + "a" * 64)

    def test_new_contract_is_valid_and_fail_closed(self):
        contract = lfd_contract.new_contract(
            "demo", "https://github.com/example/demo.git")
        lfd_contract.validate(contract, expected_name="demo")
        self.assertEqual(contract["lifecycle"]["status"], "onboarding")
        self.assertEqual(contract["detectors"]["probe"]["enforcement"], "advisory")
        self.assertEqual(contract["liveness"]["exemption"], "")


if __name__ == "__main__":
    unittest.main()
