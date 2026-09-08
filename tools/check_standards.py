#!/usr/bin/env python3
"""Deterministic conformance checks for Scout's recorded standards."""
import argparse
import ast
import json
import os
import re
import sys


def import_references(path, module_name):
    with open(path, encoding="utf-8") as stream:
        tree = ast.parse(stream.read(), filename=path)
    references = set()
    module_parts = module_name.split(".")
    package_parts = module_parts if os.path.basename(path) == "__init__.py" else module_parts[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                references.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parent_count = max(0, len(package_parts) - node.level + 1)
                base_parts = package_parts[:parent_count]
            else:
                base_parts = []
            if node.module:
                base_parts.extend(node.module.split("."))
            base = ".".join(base_parts)
            if base:
                references.add(base)
            for alias in node.names:
                if alias.name != "*":
                    references.add(".".join(part for part in (base, alias.name) if part))
    return references


def references_function(path, function_name):
    with open(path, encoding="utf-8") as stream:
        tree = ast.parse(stream.read(), filename=path)
    local_names = {function_name}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == function_name:
                    local_names.add(alias.asname or alias.name)
        if isinstance(node, ast.Attribute) and node.attr == function_name:
            return True
        if isinstance(node, ast.Name) and node.id in local_names:
            return True
    return False


def local_python_modules(hub_root):
    modules = {}
    for directory in ("tools", "ops"):
        root = os.path.join(hub_root, directory)
        if not os.path.isdir(root):
            continue
        for current_root, directory_names, file_names in os.walk(root):
            directory_names[:] = sorted(
                name for name in directory_names
                if name not in {"tests", "__pycache__"} and not name.startswith(".")
            )
            for name in sorted(file_names):
                if not name.endswith(".py"):
                    continue
                path = os.path.join(current_root, name)
                relative = os.path.relpath(path, hub_root)
                parts = os.path.splitext(relative)[0].split(os.sep)
                if parts[-1] == "__init__":
                    parts.pop()
                if parts:
                    modules[".".join(parts)] = path
    return modules


def module_dependencies(module_name, path, modules):
    dependencies = set()
    for reference in import_references(path, module_name):
        if reference in modules:
            dependencies.add(reference)
            continue
        if "." not in reference:
            matches = [name for name in modules if name.rsplit(".", 1)[-1] == reference]
            if len(matches) == 1:
                dependencies.add(matches[0])
    return dependencies


def dependency_cycles(modules):
    graph = {
        name: sorted(module_dependencies(name, path, modules))
        for name, path in modules.items()
    }
    cycles = set()

    def visit(node, path):
        if node in path:
            cycle = path[path.index(node):] + [node]
            rotations = [tuple(cycle[index:-1] + cycle[:index] + [cycle[index]])
                         for index in range(len(cycle) - 1)]
            cycles.add(min(rotations))
            return
        for dependency in graph[node]:
            visit(dependency, path + [node])

    for module in sorted(graph):
        visit(module, [])
    return sorted(cycles)


def check_architecture(hub_root):
    failures = []
    core_path = os.path.join(hub_root, "tools", "lfd_common.py")
    local_modules = local_python_modules(hub_root)
    if os.path.isfile(core_path):
        forbidden = sorted(
            module_dependencies("tools.lfd_common", core_path, local_modules)
        )
        for module in forbidden:
            failures.append(
                "SCOUT-ARCH-001 tools/lfd_common.py must not depend on "
                f"outer module {module}"
            )
    for name, path in sorted(local_modules.items()):
        if name.startswith("tools.") and name != "tools.lfd_common":
            dependencies = module_dependencies(name, path, local_modules)
            for module in sorted(
                dependency for dependency in dependencies
                if dependency == "ops" or dependency.startswith("ops.")
            ):
                failures.append(
                    f"SCOUT-ARCH-003 {os.path.relpath(path, hub_root)} must not depend on "
                    f"operations adapter {module}"
                )
    for cycle in dependency_cycles(local_modules):
        displayed = [name.split(".", 1)[-1] for name in cycle]
        failures.append(f"SCOUT-ARCH-002 Python dependency cycle: {' -> '.join(displayed)}")
    allowed_writer = os.path.join(hub_root, "ops", "log_utils.py")
    for path in sorted(local_modules.values()):
        if path != allowed_writer and references_function(path, "append_log_row"):
            relative_path = os.path.relpath(path, hub_root)
            failures.append(
                f"SCOUT-RUN-003 {relative_path} writes scoring rows outside "
                "ops/log_utils.py"
            )
    return failures


def requirement_references(hub_root):
    requirements_dir = os.path.join(hub_root, "rac", "requirements")
    references: set[str] = set()
    if not os.path.isdir(requirements_dir):
        return references
    for name in sorted(os.listdir(requirements_dir)):
        path = os.path.join(requirements_dir, name)
        if not name.endswith(".md") or not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                match = re.match(r"^- \[(REQ-\d{3})\]", line)
                if match:
                    references.add(f"rac/requirements/{name}#{match.group(1)}")
    return references


def check_controls(hub_root):
    controls_path = os.path.join(hub_root, "standards", "controls.json")
    try:
        with open(controls_path, encoding="utf-8") as stream:
            document = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        return [f"SCOUT-CTRL-003 invalid control registry: {error}"]
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        return ["SCOUT-CTRL-003 control registry schema_version must equal 1"]
    controls = document.get("controls")
    if not isinstance(controls, list):
        return ["SCOUT-CTRL-003 control registry controls must be a list"]

    failures = []
    control_ids = set()
    mapped = set()
    for index, control in enumerate(controls):
        valid = isinstance(control, dict)
        if valid:
            control_id = control.get("control_id")
            requirement = control.get("requirement")
            evidence = control.get("evidence")
            valid = (
                isinstance(control_id, str)
                and re.fullmatch(r"SCOUT-[A-Z]+-\d{3}", control_id) is not None
                and isinstance(requirement, str)
                and re.fullmatch(
                    r"rac/requirements/[a-z0-9-]+\.md#REQ-\d{3}", requirement
                ) is not None
                and control.get("enforcement") in {"ci", "human-review"}
                and control.get("severity") in {"FAIL", "WARN"}
                and isinstance(evidence, str)
                and bool(evidence.strip())
                and control_id not in control_ids
                and requirement not in mapped
            )
        if not valid:
            failures.append(
                f"SCOUT-CTRL-003 controls[{index}] violates the metadata contract"
            )
            continue
        control_ids.add(control_id)
        mapped.add(requirement)

    requirements = requirement_references(hub_root)
    failures.extend(
        f"SCOUT-CTRL-001 {reference} has no control mapping"
        for reference in sorted(requirements - mapped)
    )
    failures.extend(
        f"SCOUT-CTRL-002 control maps unknown requirement {reference}"
        for reference in sorted(mapped - requirements)
    )
    return failures


def workflow_job_run_lines(workflow, job_name):
    lines = workflow.splitlines()
    if any(re.match(r"^defaults:", line) for line in lines):
        return set()
    try:
        jobs_start = next(
            index for index, line in enumerate(lines)
            if re.fullmatch(r"jobs:\s*(?:#.*)?", line)
        )
    except StopIteration:
        return set()
    jobs_end = next(
        (
            index for index in range(jobs_start + 1, len(lines))
            if lines[index] and not lines[index].startswith((" ", "#"))
        ),
        len(lines),
    )
    job_pattern = re.compile(rf"^  {re.escape(job_name)}:\s*(?:#.*)?$")
    try:
        job_start = next(
            index for index in range(jobs_start + 1, jobs_end)
            if job_pattern.fullmatch(lines[index])
        )
    except StopIteration:
        return set()
    job_end = next(
        (
            index for index in range(job_start + 1, jobs_end)
            if re.match(r"^  [A-Za-z0-9_-]+:\s*(?:#.*)?$", lines[index])
        ),
        jobs_end,
    )
    job_lines = lines[job_start + 1:job_end]
    if any(re.match(r"^\s+shell:", line) for line in job_lines):
        return set()
    if any(
        re.match(r"^    (?:if|continue-on-error):", line)
        for line in job_lines
    ):
        return set()
    step_starts = [
        index for index, line in enumerate(job_lines)
        if re.match(r"^      -\s+", line)
    ]
    commands = set()
    for position, step_start in enumerate(step_starts):
        step_end = step_starts[position + 1] if position + 1 < len(step_starts) else len(job_lines)
        step = job_lines[step_start:step_end]
        if any(
            re.match(r"^ {6,8}(?:-\s+)?(?:if|continue-on-error):", line)
            for line in step
        ):
            continue
        step_commands = []
        for index, line in enumerate(step):
            match = re.match(r"^(\s*)(?:-\s+)?run:\s*(.*)$", line)
            if not match:
                continue
            indent = len(match.group(1))
            value = match.group(2).strip()
            if value and value not in {"|", ">", "|-", ">-"}:
                if not value.startswith("#"):
                    step_commands.append(value)
                continue
            for continuation in step[index + 1:]:
                stripped = continuation.strip()
                if len(continuation) - len(continuation.lstrip()) <= indent:
                    break
                if stripped and not stripped.startswith("#"):
                    step_commands.append(stripped)
        if len(step_commands) == 1:
            commands.add(step_commands[0])
    return commands


def check_ci_contract(hub_root):
    workflow_path = os.path.join(hub_root, ".github", "workflows", "ci.yml")
    try:
        with open(workflow_path, encoding="utf-8") as stream:
            workflow = stream.read()
    except OSError as error:
        return [f"SCOUT-CI-003 CI workflow unavailable: {error}"]
    commands = workflow_job_run_lines(workflow, "standards")
    failures = []
    required_commands = (
        "python3 -m pip install --require-hashes -r standards/rac-requirements.lock",
        'test "$(rac --version)" = "rac $(cat standards/rac-version.txt)"',
        "rac gate rac/",
        "python3 tools/check_standards.py all",
    )
    missing = [command for command in required_commands if command not in commands]
    if missing:
        failures.append(
            "SCOUT-CI-003 CI standards gate or version pin missing: "
            + ", ".join(missing)
        )
    if "rac export rac/ --agent-rules --check" not in commands:
        failures.append("SCOUT-CI-004 CI does not check generated agent-rule drift")
    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("check", choices=["architecture", "controls", "ci", "all"])
    parser.add_argument("--hub-root", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".."))
    args = parser.parse_args()

    hub_root = os.path.abspath(args.hub_root)
    checks = {
        "architecture": check_architecture,
        "controls": check_controls,
        "ci": check_ci_contract,
    }
    selected = checks.values() if args.check == "all" else (checks[args.check],)
    failures = []
    for check in selected:
        failures.extend(check(hub_root))
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print(f"standards [{args.check}]: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
