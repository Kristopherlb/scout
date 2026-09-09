#!/usr/bin/env python3
import os
import re
import shutil
import sys
import tempfile
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
HUB_ROOT = os.path.abspath(os.path.join(TESTS_DIR, "..", ".."))
sys.path.insert(0, os.path.join(HUB_ROOT, "tools"))

import lfd_bundle  # noqa: E402
import lfd_contract  # noqa: E402
import lfd_shims  # noqa: E402


class TestSkillPack(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.target = os.path.join(self.tmp, "targets", "demo")
        os.makedirs(os.path.join(self.target, "eval", "dev"))
        os.makedirs(os.path.join(self.target, "eval", "holdout"))
        os.makedirs(os.path.join(self.target, "dev-harness"))
        os.makedirs(os.path.join(self.target, "harness"))
        contract = lfd_contract.new_contract("demo", self.tmp)
        self.write(os.path.join(self.target, "target.json"), __import__("json").dumps(contract))
        self.write(os.path.join(self.target, "goal.md"), "# Goal\n")
        self.write(os.path.join(self.target, "eval", "dev", "case.json"), "{}\n")
        self.write(os.path.join(self.target, "dev-harness", "score-dev.sh"), "#!/bin/sh\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    @staticmethod
    def write(path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as stream:
            stream.write(text)

    @staticmethod
    def read(path):
        with open(path) as stream:
            return stream.read()

    def test_managed_shims_preserve_user_content_and_are_idempotent(self):
        checkout = os.path.join(self.tmp, "checkout")
        os.makedirs(checkout)
        self.write(os.path.join(checkout, "AGENTS.md"), "# Team rules\nKeep this.\n")
        lfd_shims.apply_all(checkout)
        first = self.read(os.path.join(checkout, "AGENTS.md"))
        self.assertIn("# Team rules\nKeep this.", first)
        self.assertEqual(first.count(lfd_shims.BEGIN), 1)
        lfd_shims.apply_all(checkout)
        self.assertEqual(self.read(os.path.join(checkout, "AGENTS.md")), first)

    def test_bundle_contains_execute_skill_only(self):
        lfd_bundle.generate_bundle(self.target, os.path.join(HUB_ROOT, "templates"))
        bundle = os.path.join(self.target, "bundle")
        self.assertTrue(os.path.isfile(os.path.join(
            bundle, ".agents", "skills", "lfd-execute", "SKILL.md")))
        visible = "\n".join(
            os.path.relpath(os.path.join(root, name), bundle)
            for root, _, names in os.walk(bundle) for name in names)
        for private_skill in ("lfd-design", "lfd-audit", "lfd-onboard",
                              "lfd-patch", "lfd-shared"):
            self.assertNotIn(private_skill, visible)

    def test_equip_writes_all_runtime_shims_without_clobbering(self):
        checkout = os.path.join(self.tmp, "checkout")
        os.makedirs(checkout)
        self.write(os.path.join(checkout, "CLAUDE.md"), "existing\n")
        lfd_bundle.generate_bundle(self.target, os.path.join(HUB_ROOT, "templates"))
        lfd_bundle.equip_bundle(self.target, checkout)
        self.assertTrue(os.path.isfile(os.path.join(checkout, "AGENTS.md")))
        self.assertIn("existing", self.read(os.path.join(checkout, "CLAUDE.md")))
        self.assertTrue(os.path.isfile(os.path.join(
            checkout, ".cursor", "rules", "scout-lfd.mdc")))
        self.assertTrue(os.path.isfile(os.path.join(
            checkout, ".github", "copilot-instructions.md")))
        lfd_bundle.verify_equipped(checkout)

    def test_shared_material_is_not_invocable(self):
        shared = os.path.join(HUB_ROOT, "skills", "lfd-shared")
        self.assertTrue(os.path.isdir(os.path.join(shared, "references")))
        self.assertFalse(os.path.exists(os.path.join(shared, "SKILL.md")))

    def test_skill_pointers_resolve_and_execute_avoids_custom_transport(self):
        for name in ("lfd-design", "lfd-onboard", "lfd-audit", "lfd-patch",
                     "lfd-execute"):
            skill_dir = os.path.join(HUB_ROOT, "skills", name)
            text = self.read(os.path.join(skill_dir, "SKILL.md"))
            for link in re.findall(r"\]\((\.\./lfd-shared/[^)]+)\)", text):
                self.assertTrue(os.path.exists(os.path.normpath(
                    os.path.join(skill_dir, link))), f"missing pointer {name}: {link}")
        execute = self.read(os.path.join(HUB_ROOT, "skills", "lfd-execute", "SKILL.md"))
        for forbidden in ("git tag", "git ls-remote", "curl ", "gh api"):
            self.assertNotIn(forbidden, execute)
        for command in ("score-dev.sh", "request-holdout-check.sh",
                        "check-holdout-status.sh"):
            self.assertIn(command, execute)


if __name__ == "__main__":
    unittest.main()
