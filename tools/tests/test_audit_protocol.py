#!/usr/bin/env python3
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
HUB_ROOT = os.path.abspath(os.path.join(TESTS_DIR, "..", ".."))
sys.path.insert(0, os.path.join(HUB_ROOT, "tools"))

import lfd_activate  # noqa: E402
import lfd_audit  # noqa: E402
import lfd_bundle  # noqa: E402
import lfd_common  # noqa: E402
import lfd_contract  # noqa: E402


def write(path, content, executable=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as stream:
        if isinstance(content, str):
            stream.write(content)
        else:
            json.dump(content, stream)
    if executable:
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


def passing_judgment():
    return {
        "schema_version": 1,
        "independent_context_attestation": True,
        "findings": {
            name: {"verdict": "PASS", "evidence": f"reviewed {name}"}
            for name in (
                "leakage_estimate", "goodhart_fence_matching", "calibration_quality",
                "escalation_wiring", "blinding_verification",
            )
        },
    }


class TestAuditProtocol(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.target = os.path.join(self.tmp, "targets", "demo")
        os.makedirs(self.target)
        contract = lfd_contract.new_contract("demo", self.tmp)
        contract["liveness"]["exemption"] = "pure library"
        write(os.path.join(self.target, "target.json"), contract)
        write(os.path.join(self.target, "goal.md"), "# Goal\n")
        write(os.path.join(self.target, "eval", "dev", "case.json"), {})
        write(os.path.join(self.target, "eval", "holdout", "case.json"), {})
        write(os.path.join(self.target, "dev-harness", "score-dev.sh"),
              "#!/bin/sh\necho ok\n", executable=True)
        write(os.path.join(self.target, "harness", "score-holdout.sh"),
              "#!/bin/sh\necho ok\n", executable=True)
        write(os.path.join(self.target, "harness", "probe-holdout.sh"),
              "#!/bin/sh\necho ok\n", executable=True)
        write(os.path.join(self.target, "calibration-report.json"), {
            "good_score": 0.9, "good_ci": [0.85, 0.95],
            "bad_score": 0.2, "bad_ci": [0.1, 0.3],
        })
        lfd_bundle.generate_bundle(self.target, os.path.join(HUB_ROOT, "templates"))
        self.mechanical = {
            "overall_mechanical_verdict": "PASS",
            "mechanical_results": [{"item": "all", "verdict": "PASS"}],
            "still_requires_independent_llm_judgment": ["semantic review"],
        }

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_mechanical_pass_remains_incomplete(self):
        report = lfd_audit.write_mechanical_report(self.target, self.mechanical)
        self.assertEqual(report["state"], "incomplete")
        self.assertEqual(lfd_common.audit_state(self.target)[0], "incomplete")

    def test_activation_blocked_by_judgment_exits_pending(self):
        lfd_audit.write_mechanical_report(self.target, self.mechanical)
        result = subprocess.run([
            sys.executable, os.path.join(HUB_ROOT, "tools", "lfd_activate.py"),
            "demo", "--hub-root", self.tmp, "--json",
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 3, result.stderr)
        document = json.loads(result.stdout)
        self.assertEqual(document["status"], "pending")
        self.assertEqual(document["errors"][0]["code"], "activation_blocked")

    def test_finalize_requires_every_finding(self):
        lfd_audit.write_mechanical_report(self.target, self.mechanical)
        judgment = passing_judgment()
        del judgment["findings"]["blinding_verification"]
        with self.assertRaises(lfd_audit.AuditError) as raised:
            lfd_audit.finalize_audit(self.target, judgment)
        self.assertEqual(raised.exception.code, "incomplete_judgment")

    def test_finalize_stamps_six_fresh_hashes(self):
        lfd_audit.write_mechanical_report(self.target, self.mechanical)
        report = lfd_audit.finalize_audit(self.target, passing_judgment())
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(set(report["hashes"]), {
            "goal", "eval_manifest", "bundle", "harness", "calibration", "judgment",
        })
        self.assertEqual(lfd_common.audit_state(self.target)[0], "ok")

    def test_changed_goal_makes_final_audit_stale(self):
        lfd_audit.write_mechanical_report(self.target, self.mechanical)
        lfd_audit.finalize_audit(self.target, passing_judgment())
        write(os.path.join(self.target, "goal.md"), "# changed\n")
        self.assertEqual(lfd_common.audit_state(self.target)[0], "stale")

    def test_handwritten_pass_with_incomplete_judgment_is_rejected(self):
        judgment = passing_judgment()
        del judgment["findings"]["leakage_estimate"]
        write(os.path.join(self.target, "audit-report.json"), {
            "schema_version": 1,
            "state": "complete",
            "verdict": "PASS",
            "judgment": judgment,
            "hashes": lfd_common.audit_artifact_hashes(self.target, judgment),
        })
        self.assertEqual(lfd_common.audit_state(self.target)[0], "failed")

    def test_activate_is_only_valid_active_transition(self):
        lfd_audit.write_mechanical_report(self.target, self.mechanical)
        lfd_audit.finalize_audit(self.target, passing_judgment())
        result = lfd_activate.activate(self.target)
        self.assertEqual(result["status"], "active")
        contract = lfd_contract.load_target(self.target)
        self.assertEqual(contract["lifecycle"]["status"], "active")
        self.assertEqual(lfd_common.activation_blockers(contract, self.target), [])

    def test_manual_active_edit_is_blocked_without_receipt(self):
        lfd_audit.write_mechanical_report(self.target, self.mechanical)
        lfd_audit.finalize_audit(self.target, passing_judgment())
        contract = lfd_contract.load_target(self.target)
        contract["lifecycle"]["status"] = "active"
        write(os.path.join(self.target, "target.json"), contract)
        blockers = lfd_common.activation_blockers(contract, self.target)
        self.assertTrue(any("activation receipt" in blocker for blocker in blockers))


if __name__ == "__main__":
    unittest.main()
