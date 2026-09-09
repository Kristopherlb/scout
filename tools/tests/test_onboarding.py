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

import lfd_bundle  # noqa: E402
import lfd_onboard  # noqa: E402


def write(path, content="x\n", executable=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as stream:
        stream.write(content)
    if executable:
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


class TestOnboarding(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.hub = os.path.join(self.tmp, "hub")
        self.checkout = os.path.join(self.tmp, "checkout")
        os.makedirs(self.hub)
        os.makedirs(self.checkout)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.checkout,
                       check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.checkout,
                       check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.checkout,
                       check=True)
        write(os.path.join(self.checkout, "pyproject.toml"), "[tool.ruff]\n")
        write(os.path.join(self.checkout, "README.md"), "# target\n")
        subprocess.run(["git", "add", "-A"], cwd=self.checkout, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=self.checkout,
                       check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def start(self):
        return lfd_onboard.start_target(
            self.hub, "demo", self.checkout, template_root=os.path.join(HUB_ROOT, "templates"))

    def make_design(self, target):
        write(os.path.join(target, "goal.md"), "# Goal\n")
        write(os.path.join(target, "eval", "dev", "case.json"), "{}\n")
        write(os.path.join(target, "eval", "holdout", "case.json"), "{}\n")
        write(os.path.join(target, "dev-harness", "score-dev.sh"),
              '#!/usr/bin/env bash\necho \'{"score":0,"ci_low":0,"ci_high":0,"void":false}\'\n',
              executable=True)
        write(os.path.join(target, "harness", "score-holdout.sh"),
              '#!/usr/bin/env bash\necho \'{"score":0,"ci_low":0,"ci_high":0}\'\n',
              executable=True)
        write(os.path.join(target, "harness", "probe-holdout.sh"),
              '#!/usr/bin/env bash\necho \'{"operators":{}}\'\n', executable=True)

    def test_start_creates_valid_contract_and_fail_closed_harnesses(self):
        result = self.start()
        target = result["target_dir"]
        self.assertTrue(os.path.isfile(os.path.join(target, "target.json")))
        for relative in ("dev-harness/score-dev.sh", "harness/score-holdout.sh",
                         "harness/probe-holdout.sh"):
            path = os.path.join(target, relative)
            self.assertTrue(os.access(path, os.X_OK), relative)
            proc = subprocess.run([path], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("capability_unavailable", proc.stderr)

    def test_inspect_writes_sanitized_profile(self):
        target = self.start()["target_dir"]
        profile = lfd_onboard.inspect_target(target, self.checkout)
        self.assertEqual(profile["languages"], ["python"])
        self.assertIn("pyproject.toml", profile["build_files"])
        serialized = json.dumps(profile)
        self.assertNotIn(self.checkout, serialized)

    def test_inspect_accepts_git_worktree_checkout(self):
        target = self.start()["target_dir"]
        worktree = os.path.join(self.tmp, "linked-worktree")
        subprocess.run(["git", "-C", self.checkout, "worktree", "add", "--detach",
                        worktree], capture_output=True, text=True, check=True)
        profile = lfd_onboard.inspect_target(target, worktree)
        self.assertEqual(profile["source_sha"], subprocess.run(
            ["git", "-C", worktree, "rev-parse", "HEAD"], capture_output=True,
            text=True, check=True).stdout.strip())

    def test_bundle_is_deterministic_and_verifiable(self):
        target = self.start()["target_dir"]
        self.make_design(target)
        first = lfd_bundle.generate_bundle(target, os.path.join(HUB_ROOT, "templates"))
        first_manifest = json.dumps(first, sort_keys=True)
        second = lfd_bundle.generate_bundle(target, os.path.join(HUB_ROOT, "templates"))
        self.assertEqual(first_manifest, json.dumps(second, sort_keys=True))
        result = lfd_bundle.verify_bundle(target)
        self.assertEqual(result["status"], "ok")

    def test_bundle_verification_rejects_source_drift(self):
        target = self.start()["target_dir"]
        self.make_design(target)
        lfd_bundle.generate_bundle(target, os.path.join(HUB_ROOT, "templates"))
        write(os.path.join(target, "goal.md"), "# changed after generation\n")
        with self.assertRaises(lfd_bundle.BundleError) as raised:
            lfd_bundle.verify_bundle(target)
        self.assertEqual(raised.exception.code, "bundle_drift")

    def test_bundle_rejects_private_material(self):
        target = self.start()["target_dir"]
        self.make_design(target)
        write(os.path.join(target, "eval", "dev", "holdout-answer.json"), "{}\n")
        with self.assertRaises(lfd_bundle.BundleError) as raised:
            lfd_bundle.generate_bundle(target, os.path.join(HUB_ROOT, "templates"))
        self.assertEqual(raised.exception.code, "private_material")
        self.assertFalse(os.path.exists(os.path.join(target, "bundle.new")))

    def test_bundle_rejects_allowlisted_symlink_source(self):
        target = self.start()["target_dir"]
        self.make_design(target)
        os.symlink(os.path.join(target, "eval", "holdout", "case.json"),
                   os.path.join(target, "eval", "dev", "linked.json"))
        with self.assertRaises(lfd_bundle.BundleError) as raised:
            lfd_bundle.generate_bundle(target, os.path.join(HUB_ROOT, "templates"))
        self.assertEqual(raised.exception.code, "unsafe_symlink")

    def test_equip_preserves_unrelated_files_and_rejects_conflict(self):
        target = self.start()["target_dir"]
        self.make_design(target)
        lfd_bundle.generate_bundle(target, os.path.join(HUB_ROOT, "templates"))
        write(os.path.join(self.checkout, "unrelated.txt"), "mine\n")
        lfd_bundle.equip_bundle(target, self.checkout)
        with open(os.path.join(self.checkout, "unrelated.txt")) as stream:
            self.assertEqual(stream.read(), "mine\n")
        managed = os.path.join(self.checkout, ".lfd", "goal.md")
        write(managed, "user changed this\n")
        with self.assertRaises(lfd_bundle.BundleError) as raised:
            lfd_bundle.equip_bundle(target, self.checkout)
        self.assertEqual(raised.exception.code, "target_conflict")

    def test_equip_rejects_managed_destination_symlink(self):
        target = self.start()["target_dir"]
        self.make_design(target)
        lfd_bundle.generate_bundle(target, os.path.join(HUB_ROOT, "templates"))
        caller_file = os.path.join(self.checkout, "caller-owned.txt")
        write(caller_file, "do not overwrite\n")
        managed = os.path.join(self.checkout, ".lfd", "goal.md")
        os.makedirs(os.path.dirname(managed), exist_ok=True)
        os.symlink(caller_file, managed)
        with self.assertRaises(lfd_bundle.BundleError) as raised:
            lfd_bundle.equip_bundle(target, self.checkout)
        self.assertEqual(raised.exception.code, "target_conflict")
        with open(caller_file) as stream:
            self.assertEqual(stream.read(), "do not overwrite\n")

    def test_equipped_dev_command_delegates_once_to_managed_scorer(self):
        target = self.start()["target_dir"]
        self.make_design(target)
        lfd_bundle.generate_bundle(target, os.path.join(HUB_ROOT, "templates"))
        lfd_bundle.equip_bundle(target, self.checkout)
        proc = subprocess.run(
            [os.path.join(self.checkout, "scripts", "target-repo", "score-dev.sh")],
            cwd=self.checkout, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["void"], False)

    def test_status_is_derived_from_artifacts(self):
        target = self.start()["target_dir"]
        initial = lfd_onboard.onboarding_status(target, self.checkout)
        self.assertEqual(initial["stage"], "needs_inspection")
        lfd_onboard.inspect_target(target, self.checkout)
        inspected = lfd_onboard.onboarding_status(target, self.checkout)
        self.assertEqual(inspected["stage"], "needs_design")
        self.make_design(target)
        designed = lfd_onboard.onboarding_status(target, self.checkout)
        self.assertEqual(designed["stage"], "needs_bundle")

    def test_typed_unavailable_runtime_error_does_not_look_like_scaffold(self):
        target = self.start()["target_dir"]
        lfd_onboard.inspect_target(target, self.checkout)
        self.make_design(target)
        with open(os.path.join(target, "dev-harness", "score-dev.sh"), "a") as stream:
            stream.write("# capability_unavailable remains a valid runtime error code\n")
        self.assertEqual(lfd_onboard.onboarding_status(target, self.checkout)["stage"],
                         "needs_bundle")

    def test_run_executes_deterministic_stages_then_stops_for_design(self):
        result = lfd_onboard.run_onboarding(
            self.hub, "demo", self.checkout, repository_url=self.checkout,
            template_root=os.path.join(HUB_ROOT, "templates"))
        self.assertEqual(result["stage"], "needs_design")
        self.assertTrue(os.path.isfile(os.path.join(
            self.hub, "targets", "demo", "target-profile.json")))

    def test_doctor_does_not_require_github_credentials_for_local_checks(self):
        old = os.environ.pop("GITHUB_TOKEN", None)
        try:
            result = lfd_onboard.doctor(self.hub, checkout=self.checkout)
        finally:
            if old is not None:
                os.environ["GITHUB_TOKEN"] = old
        github = next(check for check in result["checks"] if check["name"] == "github_credentials")
        self.assertEqual(github["status"], "advisory")

    def test_unknown_cli_command_fails(self):
        proc = subprocess.run([os.path.join(HUB_ROOT, "bin", "lfd"), "not-a-command"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)

    def test_removed_new_target_alias_fails_with_stable_error(self):
        proc = subprocess.run([os.path.join(HUB_ROOT, "bin", "lfd"), "new-target",
                               "demo", self.checkout], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unknown command", proc.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.hub, "targets", "demo")))

    def test_agent_json_flag_works_after_onboard_verb(self):
        self.start()
        proc = subprocess.run(
            [sys.executable, os.path.join(HUB_ROOT, "tools", "lfd_onboard.py"),
             "--hub-root", self.hub, "status", "demo", "--json"],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "action_required")
        self.assertEqual(result["stage"], "needs_inspection")
        self.assertEqual(result["errors"], [])

    def test_active_status_is_success_not_pending(self):
        self.assertFalse(lfd_onboard._requires_action("active"))
        self.assertFalse(lfd_onboard._requires_action("ready_for_activation"))
        self.assertFalse(lfd_onboard._requires_action("example_ready"))
        self.assertTrue(lfd_onboard._requires_action("needs_judgment"))


if __name__ == "__main__":
    unittest.main()
