#!/usr/bin/env python3
"""Activation-gate logic — the anti-Potemkin gates that block a target from
going 'active' on a facade. Pure functions in lfd_common; ci_checks and
lfd_status both consume them so the terminal, CI, and dashboard can never
disagree about whether a target is trustworthy.
"""
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
import lfd_audit  # noqa: E402
import lfd_common  # noqa: E402
import lfd_contract  # noqa: E402


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content if isinstance(content, str) else json.dumps(content))


class TestLivenessState(unittest.TestCase):
    def contract(self):
        return lfd_contract.new_contract(
            "demo", "https://github.com/example/demo.git")

    def test_configured_when_build_set(self):
        contract = self.contract()
        contract["liveness"]["build_command"] = "make"
        self.assertEqual(lfd_common.liveness_state(contract)[0], "configured")

    def test_configured_when_health_set(self):
        contract = self.contract()
        contract["liveness"]["health_check"] = "curl localhost"
        self.assertEqual(lfd_common.liveness_state(contract)[0], "configured")

    def test_exempt_only_with_reason(self):
        contract = self.contract()
        contract["liveness"]["exemption"] = "pure library, no entrypoint"
        self.assertEqual(lfd_common.liveness_state(contract)[0], "exempt")

    def test_unset_is_the_failure(self):
        # empty-by-default is exactly the silent-skip hole we're closing
        self.assertEqual(lfd_common.liveness_state(self.contract())[0], "unset")


class TestAuditState(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        write(os.path.join(self.dir, "harness", "score-holdout.sh"), "#!/bin/sh\necho v1\n")
        write(os.path.join(self.dir, "goal.md"), "# Goal\n")
        write(os.path.join(self.dir, "eval", "holdout", "case.json"), {})
        write(os.path.join(self.dir, "bundle", ".lfd", "bundle-manifest.json"), {})
        write(os.path.join(self.dir, "calibration-report.json"),
              {"good_ci": [0.8, 1.0], "bad_ci": [0.0, 0.2]})
        self.judgment = {
            "schema_version": 1,
            "independent_context_attestation": True,
            "findings": {name: {"verdict": "PASS", "evidence": "reviewed"}
                         for name in lfd_audit.REQUIRED_FINDINGS},
        }

    def tearDown(self):
        shutil.rmtree(self.dir)

    def report(self, **kw):
        write(os.path.join(self.dir, "audit-report.json"), kw)

    def final_report(self, verdict="PASS"):
        report = {
            "schema_version": 1,
            "state": "complete",
            "verdict": verdict,
            "judgment": self.judgment,
            "hashes": lfd_common.audit_artifact_hashes(self.dir, self.judgment),
        }
        self.report(**report)

    def test_missing(self):
        self.assertEqual(lfd_common.audit_state(self.dir)[0], "missing")

    def test_failed_verdict(self):
        self.final_report("FAIL")
        self.assertEqual(lfd_common.audit_state(self.dir)[0], "failed")

    def test_mechanical_only_report_is_incomplete(self):
        self.report(overall_mechanical_verdict="PASS")
        self.assertEqual(lfd_common.audit_state(self.dir)[0], "incomplete")

    def test_stale_when_harness_changed_since_audit(self):
        self.final_report()
        write(os.path.join(self.dir, "harness", "score-holdout.sh"), "changed")
        self.assertEqual(lfd_common.audit_state(self.dir)[0], "stale")

    def test_unversioned_report_is_incomplete(self):
        self.report(verdict="PASS")
        self.assertEqual(lfd_common.audit_state(self.dir)[0], "incomplete")

    def test_ok_when_fresh_and_passing(self):
        self.final_report()
        self.assertEqual(lfd_common.audit_state(self.dir)[0], "ok")

    def test_malformed_json_is_failed(self):
        write(os.path.join(self.dir, "audit-report.json"), "{not json")
        self.assertEqual(lfd_common.audit_state(self.dir)[0], "failed")


class TestCalibrationState(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def report(self, content):
        write(os.path.join(self.dir, "calibration-report.json"), content)

    def test_missing(self):
        self.assertEqual(lfd_common.calibration_state(self.dir)[0], "missing")

    def test_ok_when_intervals_separate(self):
        self.report({"good_score": 0.95, "good_ci": [0.90, 0.99],
                     "bad_score": 0.20, "bad_ci": [0.12, 0.28]})
        self.assertEqual(lfd_common.calibration_state(self.dir)[0], "ok")

    def test_overlapping_intervals_rejected(self):
        # a scorer that can't separate good from bad is itself vaporware
        self.report({"good_score": 0.60, "good_ci": [0.50, 0.70],
                     "bad_score": 0.55, "bad_ci": [0.45, 0.65]})
        self.assertEqual(lfd_common.calibration_state(self.dir)[0], "overlapping")

    def test_malformed_is_invalid(self):
        self.report({"good_score": 0.9})
        self.assertEqual(lfd_common.calibration_state(self.dir)[0], "invalid")
        self.report("{not json")
        self.assertEqual(lfd_common.calibration_state(self.dir)[0], "invalid")


class TestActivationGateIntegration(unittest.TestCase):
    """The gate as CI runs it: an active target must clear all three."""

    def setUp(self):
        self.hub = tempfile.mkdtemp()
        self.tdir = os.path.join(self.hub, "targets", "demo")
        write(os.path.join(self.tdir, "harness", "score-holdout.sh"), "#!/bin/sh\n")
        write(os.path.join(self.tdir, "goal.md"), "# Goal\n")
        write(os.path.join(self.tdir, "eval", "holdout", "case.json"), {})
        write(os.path.join(self.tdir, "bundle", ".lfd", "bundle-manifest.json"), {})

    def tearDown(self):
        shutil.rmtree(self.hub)

    def configure(self, **overrides):
        contract = lfd_contract.new_contract("demo", self.tdir)
        contract["lifecycle"]["status"] = overrides.pop("STATUS", "active")
        contract["liveness"]["build_command"] = overrides.pop("BUILD_CMD", "make")
        contract["liveness"]["health_check"] = overrides.pop("HEALTH_CHECK", "")
        contract["liveness"]["exemption"] = overrides.pop("LIVENESS_EXEMPT", "")
        self.assertFalse(overrides)
        write(os.path.join(self.tdir, "target.json"), contract)
        write(os.path.join(self.tdir, "calibration-report.json"),
              {"good_score": 0.95, "good_ci": [0.9, 0.99],
               "bad_score": 0.2, "bad_ci": [0.1, 0.3]})
        judgment = {
            "schema_version": 1, "independent_context_attestation": True,
            "findings": {name: {"verdict": "PASS", "evidence": "reviewed"}
                         for name in lfd_audit.REQUIRED_FINDINGS},
        }
        audit = {"schema_version": 1, "state": "complete", "verdict": "PASS",
                 "judgment": judgment,
                 "hashes": lfd_common.audit_artifact_hashes(self.tdir, judgment)}
        write(os.path.join(self.tdir, "audit-report.json"), audit)
        receipt = {
            "schema_version": 1,
            "target_contract_hash": lfd_common.artifact_hash(os.path.join(self.tdir, "target.json")),
            "audit_report_hash": lfd_common.artifact_hash(os.path.join(self.tdir, "audit-report.json")),
            "activated_at": "2026-01-01T00:00:00Z",
        }
        write(os.path.join(self.tdir, "activation.json"), receipt)

    def run_gate(self):
        return subprocess.run(
            [sys.executable, os.path.join(HUB_ROOT, "tools", "ci_checks.py"),
             "activation-gate", "--hub-root", self.hub],
            capture_output=True, text=True)

    def test_fully_configured_active_target_passes(self):
        self.configure()
        self.assertEqual(self.run_gate().returncode, 0, self.run_gate().stdout)

    def test_onboarding_target_is_never_gated(self):
        self.configure(STATUS="onboarding")
        os.remove(os.path.join(self.tdir, "audit-report.json"))
        self.assertEqual(self.run_gate().returncode, 0)

    def test_active_without_liveness_blocked(self):
        self.configure(BUILD_CMD="", HEALTH_CHECK="")
        res = self.run_gate()
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("liveness", res.stdout.lower())

    def test_active_with_stale_audit_blocked(self):
        self.configure()
        write(os.path.join(self.tdir, "goal.md"), "changed")
        res = self.run_gate()
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("audit", res.stdout.lower())

    def test_active_with_overlapping_calibration_blocked(self):
        self.configure()
        write(os.path.join(self.tdir, "calibration-report.json"),
              {"good_score": 0.6, "good_ci": [0.5, 0.7],
               "bad_score": 0.55, "bad_ci": [0.45, 0.65]})
        res = self.run_gate()
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("calibration", res.stdout.lower())


class TestZeroDepsGate(unittest.TestCase):
    """pyproject.toml is allowed for dev-tool config; flagged only if it
    declares RUNTIME dependencies. requirements.txt/package.json always fail."""

    def setUp(self):
        sys.path.insert(0, os.path.join(HUB_ROOT, "tools"))
        import ci_checks
        self.ci_checks = ci_checks
        self.hub = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.hub)

    def test_toolonly_pyproject_allowed(self):
        write(os.path.join(self.hub, "pyproject.toml"),
              "[tool.ruff]\nline-length = 100\n[tool.mypy]\nfiles = ['tools']\n")
        self.assertEqual(self.ci_checks.check_zero_deps(self.hub), [])

    def test_pyproject_with_runtime_deps_flagged(self):
        write(os.path.join(self.hub, "pyproject.toml"),
              "[project]\nname = 'x'\ndependencies = ['requests']\n")
        self.assertTrue(self.ci_checks.check_zero_deps(self.hub))

    def test_requirements_txt_always_flagged(self):
        write(os.path.join(self.hub, "requirements.txt"), "requests==2\n")
        self.assertTrue(self.ci_checks.check_zero_deps(self.hub))

    def test_allow_deps_override(self):
        write(os.path.join(self.hub, "requirements.txt"), "requests==2\n")
        write(os.path.join(self.hub, ".allow-deps"), "justified\n")
        self.assertEqual(self.ci_checks.check_zero_deps(self.hub), [])


class TestPublicReleaseGate(unittest.TestCase):
    """A public framework checkout must never contain real eval campaigns."""

    def setUp(self):
        sys.path.insert(0, os.path.join(HUB_ROOT, "tools"))
        import ci_checks
        self.ci_checks = ci_checks
        self.hub = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.hub)

    def test_synthetic_fixture_is_allowed(self):
        write(os.path.join(self.hub, "targets", "_example", "target.json"), {})
        self.assertEqual(self.ci_checks.check_public_release(self.hub), [])

    def test_real_target_directory_is_blocked(self):
        write(os.path.join(self.hub, "targets", "customer-eval", "target.json"), {})
        failures = self.ci_checks.check_public_release(self.hub)
        self.assertEqual(len(failures), 1)
        self.assertIn("targets/customer-eval", failures[0])

    def test_underscore_prefixed_real_target_is_blocked(self):
        write(os.path.join(self.hub, "targets", "_private", "target.json"), {})
        failures = self.ci_checks.check_public_release(self.hub)
        self.assertTrue(any("targets/_private" in failure for failure in failures))

    def test_eval_shaped_file_outside_fixture_is_blocked(self):
        write(os.path.join(self.hub, "archive", "eval", "holdout", "case.json"),
              '{}\n')
        failures = self.ci_checks.check_public_release(self.hub)
        self.assertEqual(len(failures), 1)
        self.assertIn("archive/eval/holdout/case.json", failures[0])

    def test_holdout_path_outside_fixture_is_blocked(self):
        write(os.path.join(self.hub, "archive", "holdout", "case.json"), '{}\n')
        failures = self.ci_checks.check_public_release(self.hub)
        self.assertEqual(len(failures), 1)
        self.assertIn("archive/holdout/case.json", failures[0])

    def test_generated_root_artifacts_are_blocked(self):
        write(os.path.join(self.hub, ".coverage"), "generated")
        write(os.path.join(self.hub, ".compressibility-history.jsonl"), "{}\n")
        failures = self.ci_checks.check_public_release(self.hub)
        self.assertEqual(len(failures), 2)


class TestAppendOnlyLog(unittest.TestCase):
    """Real target logs are append-only; underscore-prefixed fixture targets
    (_example) are regenerated by design and exempt."""

    def setUp(self):
        sys.path.insert(0, os.path.join(HUB_ROOT, "tools"))
        import ci_checks
        self.ci_checks = ci_checks
        self.hub = tempfile.mkdtemp()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.hub, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.hub, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.hub, check=True)

    def tearDown(self):
        shutil.rmtree(self.hub)

    def commit_log(self, name, lines):
        p = os.path.join(self.hub, "targets", name, "log.jsonl")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(lines)
        subprocess.run(["git", "add", "-A"], cwd=self.hub, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=self.hub, check=True)

    def test_editing_real_log_flagged(self):
        self.commit_log("myrepo", '{"cycle":1}\n{"cycle":2}\n')
        self.commit_log("myrepo", '{"cycle":1}\n{"cycle":99}\n')  # rewrote line 2
        self.assertTrue(self.ci_checks.check_append_only_log(self.hub, "HEAD~1...HEAD"))

    def test_appending_real_log_ok(self):
        self.commit_log("myrepo", '{"cycle":1}\n')
        self.commit_log("myrepo", '{"cycle":1}\n{"cycle":2}\n')  # pure append
        self.assertEqual(self.ci_checks.check_append_only_log(self.hub, "HEAD~1...HEAD"), [])

    def test_fixture_target_exempt(self):
        self.commit_log("_example", '{"cycle":1}\n{"cycle":2}\n')
        self.commit_log("_example", '{"cycle":1}\n{"cycle":42}\n')  # regenerated
        self.assertEqual(self.ci_checks.check_append_only_log(self.hub, "HEAD~1...HEAD"), [])


class TestMechanicalAuditReport(unittest.TestCase):
    """Mechanical evidence is persisted, but never grants activation."""

    def setUp(self):
        sys.path.insert(0, os.path.join(HUB_ROOT, "tools"))
        import lfd_audit
        self.lfd_audit = lfd_audit
        self.dir = tempfile.mkdtemp()
        write(os.path.join(self.dir, "harness", "score-holdout.sh"), "#!/bin/sh\n")
        write(os.path.join(self.dir, "goal.md"), "# Goal\n")
        write(os.path.join(self.dir, "eval", "holdout", "case.json"), {})
        write(os.path.join(self.dir, "bundle", ".lfd", "bundle-manifest.json"), {})
        write(os.path.join(self.dir, "calibration-report.json"),
              {"good_ci": [0.8, 1.0], "bad_ci": [0.0, 0.2]})

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_pass_is_stamped_incomplete_with_artifact_hashes(self):
        skill_out = {"overall_mechanical_verdict": "PASS",
                     "mechanical_results": [{"item": "x", "verdict": "PASS"}]}
        report = self.lfd_audit.write_mechanical_report(self.dir, skill_out)
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(report["state"], "incomplete")
        self.assertEqual(set(report["hashes"]),
                         {"goal", "eval_manifest", "bundle", "harness", "calibration"})
        self.assertEqual(lfd_common.audit_state(self.dir)[0], "incomplete")

    def test_failing_skill_audit_produces_failed_state(self):
        report = self.lfd_audit.write_mechanical_report(
            self.dir, {"overall_mechanical_verdict": "FAIL"})
        self.assertEqual(report["verdict"], "FAIL")
        self.assertEqual(report["state"], "failed")


if __name__ == "__main__":
    unittest.main()
