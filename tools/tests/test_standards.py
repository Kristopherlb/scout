#!/usr/bin/env python3
"""Tests for Scout's deterministic standards and architecture guardrails."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HUB_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CHECKER = os.path.join(HUB_ROOT, "tools", "check_standards.py")


class TestArchitectureChecks(unittest.TestCase):
    def test_contract_module_cannot_import_command_module(self):
        with tempfile.TemporaryDirectory() as root:
            tools_dir = os.path.join(root, "tools")
            os.makedirs(tools_dir)
            with open(os.path.join(tools_dir, "lfd_contract.py"), "w") as stream:
                stream.write("import lfd_status\n")
            with open(os.path.join(tools_dir, "lfd_status.py"), "w") as stream:
                stream.write("VALUE = 1\n")

            result = subprocess.run(
                [sys.executable, CHECKER, "architecture", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-ARCH-005", result.stdout)
        self.assertIn("lfd_contract.py", result.stdout)

    def test_core_cannot_import_command_module(self):
        with tempfile.TemporaryDirectory() as root:
            tools_dir = os.path.join(root, "tools")
            os.makedirs(tools_dir)
            with open(os.path.join(tools_dir, "lfd_common.py"), "w") as stream:
                stream.write("import lfd_status\n")
            with open(os.path.join(tools_dir, "lfd_status.py"), "w") as stream:
                stream.write("VALUE = 1\n")

            result = subprocess.run(
                [sys.executable, CHECKER, "architecture", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-ARCH-001", result.stdout)
        self.assertIn("lfd_common.py", result.stdout)

    def test_python_component_cycle_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            tools_dir = os.path.join(root, "tools")
            os.makedirs(tools_dir)
            with open(os.path.join(tools_dir, "alpha.py"), "w") as stream:
                stream.write("import beta\n")
            with open(os.path.join(tools_dir, "beta.py"), "w") as stream:
                stream.write("import alpha\n")

            result = subprocess.run(
                [sys.executable, CHECKER, "architecture", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-ARCH-002", result.stdout)
        self.assertIn("alpha -> beta -> alpha", result.stdout)

    def test_command_module_cannot_import_operations_adapter(self):
        with tempfile.TemporaryDirectory() as root:
            tools_dir = os.path.join(root, "tools")
            ops_dir = os.path.join(root, "ops")
            os.makedirs(tools_dir)
            os.makedirs(ops_dir)
            with open(os.path.join(tools_dir, "lfd_status.py"), "w") as stream:
                stream.write("from ops import log_utils\n")
            with open(os.path.join(ops_dir, "log_utils.py"), "w") as stream:
                stream.write("VALUE = 1\n")

            result = subprocess.run(
                [sys.executable, CHECKER, "architecture", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-ARCH-003", result.stdout)
        self.assertIn("lfd_status.py", result.stdout)

    def test_command_cannot_import_nested_operations_adapter(self):
        with tempfile.TemporaryDirectory() as root:
            tools_dir = os.path.join(root, "tools")
            adapter_dir = os.path.join(root, "ops", "adapters")
            os.makedirs(tools_dir)
            os.makedirs(adapter_dir)
            with open(os.path.join(tools_dir, "lfd_status.py"), "w") as stream:
                stream.write("from ops.adapters import client\n")
            with open(os.path.join(adapter_dir, "client.py"), "w") as stream:
                stream.write("VALUE = 1\n")

            result = subprocess.run(
                [sys.executable, CHECKER, "architecture", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-ARCH-003", result.stdout)
        self.assertIn("ops.adapters.client", result.stdout)

    def test_nested_python_component_cycle_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            package_dir = os.path.join(root, "tools", "package")
            os.makedirs(package_dir)
            with open(os.path.join(package_dir, "alpha.py"), "w") as stream:
                stream.write("from tools.package import beta\n")
            with open(os.path.join(package_dir, "beta.py"), "w") as stream:
                stream.write("from tools.package import alpha\n")

            result = subprocess.run(
                [sys.executable, CHECKER, "architecture", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-ARCH-002", result.stdout)
        self.assertIn("package.alpha -> package.beta -> package.alpha", result.stdout)

    def test_only_log_adapter_can_append_scoring_rows(self):
        with tempfile.TemporaryDirectory() as root:
            tools_dir = os.path.join(root, "tools")
            ops_dir = os.path.join(root, "ops")
            os.makedirs(tools_dir)
            os.makedirs(ops_dir)
            with open(os.path.join(tools_dir, "lfd_status.py"), "w") as stream:
                stream.write("import lfd_common\nlfd_common.append_log_row('log.jsonl', {})\n")
            with open(os.path.join(ops_dir, "log_utils.py"), "w") as stream:
                stream.write("import lfd_common\n")

            result = subprocess.run(
                [sys.executable, CHECKER, "architecture", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-RUN-003", result.stdout)
        self.assertIn("lfd_status.py", result.stdout)

    def test_aliased_log_writer_call_in_nested_module_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            package_dir = os.path.join(root, "tools", "package")
            ops_dir = os.path.join(root, "ops")
            os.makedirs(package_dir)
            os.makedirs(ops_dir)
            with open(os.path.join(package_dir, "writer.py"), "w") as stream:
                stream.write(
                    "from tools.lfd_common import append_log_row as write_row\n"
                    "write_row('log.jsonl', {})\n"
                )
            with open(os.path.join(ops_dir, "log_utils.py"), "w") as stream:
                stream.write("VALUE = 1\n")

            result = subprocess.run(
                [sys.executable, CHECKER, "architecture", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-RUN-003", result.stdout)
        self.assertIn("tools/package/writer.py", result.stdout)


class TestControlRegistry(unittest.TestCase):
    def test_requirement_without_control_mapping_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            requirements_dir = os.path.join(root, "rac", "requirements")
            standards_dir = os.path.join(root, "standards")
            os.makedirs(requirements_dir)
            os.makedirs(standards_dir)
            with open(os.path.join(requirements_dir, "boundary.md"), "w") as stream:
                stream.write("## Requirements\n\n- [REQ-001] Scout MUST stay bounded.\n")
            with open(os.path.join(standards_dir, "controls.json"), "w") as stream:
                json.dump({"schema_version": 1, "controls": []}, stream)

            result = subprocess.run(
                [sys.executable, CHECKER, "controls", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-CTRL-001", result.stdout)
        self.assertIn("boundary.md#REQ-001", result.stdout)

    def test_control_mapping_to_unknown_requirement_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            requirements_dir = os.path.join(root, "rac", "requirements")
            standards_dir = os.path.join(root, "standards")
            os.makedirs(requirements_dir)
            os.makedirs(standards_dir)
            with open(os.path.join(requirements_dir, "boundary.md"), "w") as stream:
                stream.write("## Requirements\n\n- [REQ-001] Scout MUST stay bounded.\n")
            control = {
                "control_id": "SCOUT-ARCH-001",
                "requirement": "rac/requirements/boundary.md#REQ-999",
                "enforcement": "ci",
                "severity": "FAIL",
                "evidence": "python3 tools/check_standards.py architecture",
            }
            with open(os.path.join(standards_dir, "controls.json"), "w") as stream:
                json.dump({"schema_version": 1, "controls": [control]}, stream)

            result = subprocess.run(
                [sys.executable, CHECKER, "controls", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-CTRL-002", result.stdout)
        self.assertIn("REQ-999", result.stdout)

    def test_control_metadata_contract_is_enforced(self):
        with tempfile.TemporaryDirectory() as root:
            requirements_dir = os.path.join(root, "rac", "requirements")
            standards_dir = os.path.join(root, "standards")
            os.makedirs(requirements_dir)
            os.makedirs(standards_dir)
            with open(os.path.join(requirements_dir, "boundary.md"), "w") as stream:
                stream.write("## Requirements\n\n- [REQ-001] Scout MUST stay bounded.\n")
            control = {
                "control_id": "not-stable",
                "requirement": "rac/requirements/boundary.md#REQ-001",
                "enforcement": "sometimes",
                "severity": "MAYBE",
                "evidence": "",
            }
            with open(os.path.join(standards_dir, "controls.json"), "w") as stream:
                json.dump({"schema_version": 1, "controls": [control]}, stream)

            result = subprocess.run(
                [sys.executable, CHECKER, "controls", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-CTRL-003", result.stdout)


class TestCiContract(unittest.TestCase):
    def test_unreachable_ci_commands_do_not_satisfy_contract(self):
        with tempfile.TemporaryDirectory() as root:
            workflows = os.path.join(root, ".github", "workflows")
            os.makedirs(workflows)
            with open(os.path.join(workflows, "ci.yml"), "w") as stream:
                stream.write(
                    "jobs:\n"
                    "  standards:\n"
                    "    steps:\n"
                    "      - run: |\n"
                    "          exit 0\n"
                    "          RAC_VERSION=$(cat standards/rac-version.txt)\n"
                    "          python3 -m pip install --require-hashes -r "
                    "standards/rac-requirements.lock\n"
                    "          test \"$(rac --version)\" = \"rac $RAC_VERSION\"\n"
                    "          rac gate rac/\n"
                    "          rac export rac/ --agent-rules --check\n"
                    "          python3 tools/check_standards.py all\n"
                )

            result = subprocess.run(
                [sys.executable, CHECKER, "ci", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-CI-003", result.stdout)
        self.assertIn("SCOUT-CI-004", result.stdout)

    def test_noop_shell_override_does_not_satisfy_contract(self):
        with tempfile.TemporaryDirectory() as root:
            workflows = os.path.join(root, ".github", "workflows")
            os.makedirs(workflows)
            with open(os.path.join(workflows, "ci.yml"), "w") as stream:
                stream.write(
                    "jobs:\n"
                    "  standards:\n"
                    "    defaults:\n"
                    "      run:\n"
                    "        shell: echo {0}\n"
                    "    steps:\n"
                    "      - run: python3 -m pip install --require-hashes -r "
                    "standards/rac-requirements.lock\n"
                    "      - run: test \"$(rac --version)\" = "
                    "\"rac $(cat standards/rac-version.txt)\"\n"
                    "      - run: rac gate rac/\n"
                    "      - run: rac export rac/ --agent-rules --check\n"
                    "      - run: python3 tools/check_standards.py all\n"
                )

            result = subprocess.run(
                [sys.executable, CHECKER, "ci", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-CI-003", result.stdout)
        self.assertIn("SCOUT-CI-004", result.stdout)

    def test_unconditional_single_command_steps_satisfy_contract(self):
        with tempfile.TemporaryDirectory() as root:
            workflows = os.path.join(root, ".github", "workflows")
            os.makedirs(workflows)
            with open(os.path.join(workflows, "ci.yml"), "w") as stream:
                stream.write(
                    "jobs:\n"
                    "  standards:\n"
                    "    steps:\n"
                    "      - run: python3 -m pip install --require-hashes -r "
                    "standards/rac-requirements.lock\n"
                    "      - run: test \"$(rac --version)\" = "
                    "\"rac $(cat standards/rac-version.txt)\"\n"
                    "      - run: rac gate rac/\n"
                    "      - run: rac export rac/ --agent-rules --check\n"
                    "      - run: python3 tools/check_standards.py all\n"
                )

            result = subprocess.run(
                [sys.executable, CHECKER, "ci", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stdout)

    def test_ci_commands_in_comments_do_not_satisfy_contract(self):
        with tempfile.TemporaryDirectory() as root:
            workflows = os.path.join(root, ".github", "workflows")
            os.makedirs(workflows)
            with open(os.path.join(workflows, "ci.yml"), "w") as stream:
                stream.write(
                    "jobs: {}\n"
                    "# standards:\n"
                    "# RAC_VERSION=$(cat standards/rac-version.txt)\n"
                    "# python3 -m pip install --require-hashes -r "
                    "standards/rac-requirements.lock\n"
                    "# test \"$(rac --version)\" = \"rac $RAC_VERSION\"\n"
                    "# rac gate rac/\n"
                    "# rac export rac/ --agent-rules --check\n"
                    "# python3 tools/check_standards.py all\n"
                )

            result = subprocess.run(
                [sys.executable, CHECKER, "ci", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-CI-003", result.stdout)
        self.assertIn("SCOUT-CI-004", result.stdout)

    def test_ci_commands_in_another_job_do_not_satisfy_contract(self):
        with tempfile.TemporaryDirectory() as root:
            workflows = os.path.join(root, ".github", "workflows")
            os.makedirs(workflows)
            with open(os.path.join(workflows, "ci.yml"), "w") as stream:
                stream.write(
                    "jobs:\n"
                    "  test:\n"
                    "    steps:\n"
                    "      - run: |\n"
                    "          RAC_VERSION=$(cat standards/rac-version.txt)\n"
                    "          python3 -m pip install --require-hashes -r "
                    "standards/rac-requirements.lock\n"
                    "          test \"$(rac --version)\" = \"rac $RAC_VERSION\"\n"
                    "          rac gate rac/\n"
                    "          rac export rac/ --agent-rules --check\n"
                    "          python3 tools/check_standards.py all\n"
                    "  standards:\n"
                    "    steps:\n"
                    "      - run: echo no standards here\n"
                )

            result = subprocess.run(
                [sys.executable, CHECKER, "ci", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-CI-003", result.stdout)
        self.assertIn("SCOUT-CI-004", result.stdout)

    def test_conditioned_ci_commands_do_not_satisfy_contract(self):
        with tempfile.TemporaryDirectory() as root:
            workflows = os.path.join(root, ".github", "workflows")
            os.makedirs(workflows)
            with open(os.path.join(workflows, "ci.yml"), "w") as stream:
                stream.write(
                    "jobs:\n"
                    "  standards:\n"
                    "    steps:\n"
                    "      - name: Disabled standards\n"
                    "        if: github.ref == 'refs/heads/never'\n"
                    "        run: |\n"
                    "          RAC_VERSION=$(cat standards/rac-version.txt)\n"
                    "          python3 -m pip install --require-hashes -r "
                    "standards/rac-requirements.lock\n"
                    "          test \"$(rac --version)\" = \"rac $RAC_VERSION\"\n"
                    "          rac gate rac/\n"
                    "          rac export rac/ --agent-rules --check\n"
                    "          python3 tools/check_standards.py all\n"
                )

            result = subprocess.run(
                [sys.executable, CHECKER, "ci", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-CI-003", result.stdout)
        self.assertIn("SCOUT-CI-004", result.stdout)

    def test_conditioned_standards_job_does_not_satisfy_contract(self):
        with tempfile.TemporaryDirectory() as root:
            workflows = os.path.join(root, ".github", "workflows")
            os.makedirs(workflows)
            with open(os.path.join(workflows, "ci.yml"), "w") as stream:
                stream.write(
                    "jobs:\n"
                    "  standards:\n"
                    "    if: github.ref == 'refs/heads/never'\n"
                    "    steps:\n"
                    "      - run: |\n"
                    "          RAC_VERSION=$(cat standards/rac-version.txt)\n"
                    "          python3 -m pip install --require-hashes -r "
                    "standards/rac-requirements.lock\n"
                    "          test \"$(rac --version)\" = \"rac $RAC_VERSION\"\n"
                    "          rac gate rac/\n"
                    "          rac export rac/ --agent-rules --check\n"
                    "          python3 tools/check_standards.py all\n"
                )

            result = subprocess.run(
                [sys.executable, CHECKER, "ci", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-CI-003", result.stdout)
        self.assertIn("SCOUT-CI-004", result.stdout)

    def test_nonblocking_standards_step_does_not_satisfy_contract(self):
        with tempfile.TemporaryDirectory() as root:
            workflows = os.path.join(root, ".github", "workflows")
            os.makedirs(workflows)
            with open(os.path.join(workflows, "ci.yml"), "w") as stream:
                stream.write(
                    "jobs:\n"
                    "  standards:\n"
                    "    steps:\n"
                    "      - continue-on-error: true\n"
                    "        run: |\n"
                    "          RAC_VERSION=$(cat standards/rac-version.txt)\n"
                    "          python3 -m pip install --require-hashes -r "
                    "standards/rac-requirements.lock\n"
                    "          test \"$(rac --version)\" = \"rac $RAC_VERSION\"\n"
                    "          rac gate rac/\n"
                    "          rac export rac/ --agent-rules --check\n"
                    "          python3 tools/check_standards.py all\n"
                )

            result = subprocess.run(
                [sys.executable, CHECKER, "ci", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-CI-003", result.stdout)
        self.assertIn("SCOUT-CI-004", result.stdout)

    def test_nonblocking_standards_job_does_not_satisfy_contract(self):
        with tempfile.TemporaryDirectory() as root:
            workflows = os.path.join(root, ".github", "workflows")
            os.makedirs(workflows)
            with open(os.path.join(workflows, "ci.yml"), "w") as stream:
                stream.write(
                    "jobs:\n"
                    "  standards:\n"
                    "    continue-on-error: true\n"
                    "    steps:\n"
                    "      - run: |\n"
                    "          RAC_VERSION=$(cat standards/rac-version.txt)\n"
                    "          python3 -m pip install --require-hashes -r "
                    "standards/rac-requirements.lock\n"
                    "          test \"$(rac --version)\" = \"rac $RAC_VERSION\"\n"
                    "          rac gate rac/\n"
                    "          rac export rac/ --agent-rules --check\n"
                    "          python3 tools/check_standards.py all\n"
                )

            result = subprocess.run(
                [sys.executable, CHECKER, "ci", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-CI-003", result.stdout)
        self.assertIn("SCOUT-CI-004", result.stdout)

    def test_ci_must_run_deterministic_standards_checker(self):
        with tempfile.TemporaryDirectory() as root:
            workflows = os.path.join(root, ".github", "workflows")
            os.makedirs(workflows)
            with open(os.path.join(workflows, "ci.yml"), "w") as stream:
                stream.write(
                    "jobs:\n  standards:\n    steps:\n"
                    "      - run: rac gate rac/\n"
                    "      - run: rac export rac/ --agent-rules --check\n"
                )

            result = subprocess.run(
                [sys.executable, CHECKER, "ci", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-CI-003", result.stdout)

    def test_ci_must_check_generated_agent_rules(self):
        with tempfile.TemporaryDirectory() as root:
            workflows = os.path.join(root, ".github", "workflows")
            os.makedirs(workflows)
            with open(os.path.join(workflows, "ci.yml"), "w") as stream:
                stream.write(
                    "jobs:\n  standards:\n    steps:\n"
                    "      - run: rac gate rac/\n"
                    "      - run: python3 tools/check_standards.py all\n"
                )

            result = subprocess.run(
                [sys.executable, CHECKER, "ci", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-CI-004", result.stdout)

    def test_ci_must_install_rac_from_committed_version_pin(self):
        with tempfile.TemporaryDirectory() as root:
            workflows = os.path.join(root, ".github", "workflows")
            os.makedirs(workflows)
            with open(os.path.join(workflows, "ci.yml"), "w") as stream:
                stream.write(
                    "jobs:\n  standards:\n    steps:\n"
                    "      - run: pip install rac-core\n"
                    "      - run: rac gate rac/\n"
                    "      - run: rac export rac/ --agent-rules --check\n"
                    "      - run: python3 tools/check_standards.py all\n"
                )

            result = subprocess.run(
                [sys.executable, CHECKER, "ci", "--hub-root", root],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SCOUT-CI-003", result.stdout)
        self.assertIn("version pin", result.stdout)


if __name__ == "__main__":
    unittest.main()
