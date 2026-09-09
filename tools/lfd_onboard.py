#!/usr/bin/env python3
"""Resumable, artifact-derived onboarding commands for Scout targets."""
import argparse
import json
import os
import shutil
import stat
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfd_bundle  # noqa: E402
import lfd_common  # noqa: E402
import lfd_contract  # noqa: E402
import lfd_interface  # noqa: E402

envelope = lfd_interface.envelope


def _requires_action(stage):
    return stage not in {"ready_for_activation", "active", "example_ready"}


def _write_json(path, document):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as stream:
        json.dump(document, stream, indent=2, sort_keys=True)
        stream.write("\n")


def _write_unavailable(path, capability):
    body = ("#!/usr/bin/env bash\n# LFD_CAPABILITY_UNAVAILABLE\nset -euo pipefail\n"
            f"echo '{{\"status\":\"error\",\"error\":{{\"code\":\"capability_unavailable\",\"message\":\"{capability} requires completed LFD design\"}}}}' >&2\n"
            "exit 2\n")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as stream:
        stream.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


def start_target(hub_root, name, repository_url, template_root=None):
    hub_root = os.path.abspath(hub_root)
    target_dir = os.path.join(hub_root, "targets", name)
    if os.path.exists(target_dir):
        raise lfd_contract.ContractError("target_exists", target_dir,
                                         "target registry entry already exists")
    template_path = None
    if template_root:
        template_path = os.path.join(template_root, "target-contract.json")
    contract = lfd_contract.new_contract(name, repository_url, template_path)
    for relative in ("eval/dev", "eval/holdout", "dev-harness", "harness", "retros"):
        os.makedirs(os.path.join(target_dir, relative))
    _write_json(os.path.join(target_dir, "target.json"), contract)
    _write_json(os.path.join(target_dir, "canary-list.json"),
                {"run_id": None, "canaries": []})
    open(os.path.join(target_dir, "log.jsonl"), "a").close()
    _write_unavailable(os.path.join(target_dir, "dev-harness", "score-dev.sh"),
                       "developer scoring")
    _write_unavailable(os.path.join(target_dir, "harness", "score-holdout.sh"),
                       "holdout scoring")
    _write_unavailable(os.path.join(target_dir, "harness", "probe-holdout.sh"),
                       "holdout probing")
    return {"target_dir": target_dir}


def _is_git_checkout(path):
    return subprocess.run(
        ["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True,
    ).returncode == 0


def inspect_target(target_dir, checkout):
    target_dir = os.path.abspath(target_dir)
    checkout = os.path.abspath(checkout)
    if not _is_git_checkout(checkout):
        raise ValueError("checkout must be a Git working tree")
    extensions: dict[str, int] = {}
    build_names = {"pyproject.toml", "package.json", "Cargo.toml", "go.mod",
                   "Gemfile", "Makefile", "justfile"}
    build_files = []
    instruction_names = {"AGENTS.md", "CLAUDE.md", "copilot-instructions.md"}
    instruction_files = []
    for root, directories, files in os.walk(checkout):
        directories[:] = sorted(d for d in directories if d not in {".git", "node_modules", "vendor"})
        for name in sorted(files):
            relative = os.path.relpath(os.path.join(root, name), checkout)
            if name in build_names:
                build_files.append(relative)
            if name in instruction_names or name.endswith(".mdc"):
                instruction_files.append(relative)
            extension = os.path.splitext(name)[1].lower()
            if extension:
                extensions[extension] = extensions.get(extension, 0) + 1
    language_map = {".py": "python", ".js": "javascript", ".ts": "typescript",
                    ".tsx": "typescript", ".rs": "rust", ".go": "go", ".rb": "ruby"}
    languages = sorted({language_map[ext] for ext in extensions if ext in language_map})
    build_languages = {"pyproject.toml": "python", "package.json": "javascript",
                       "Cargo.toml": "rust", "go.mod": "go", "Gemfile": "ruby"}
    languages = sorted(set(languages) | {build_languages[os.path.basename(path)]
                                        for path in build_files
                                        if os.path.basename(path) in build_languages})
    sha = subprocess.run(["git", "-C", checkout, "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True).stdout.strip()
    profile = {
        "schema_version": 1,
        "source_sha": sha,
        "languages": languages,
        "build_files": sorted(build_files),
        "agent_instruction_files": sorted(instruction_files),
    }
    _write_json(os.path.join(target_dir, "target-profile.json"), profile)
    return profile


def _designed(target_dir):
    required_files = (
        "goal.md", "dev-harness/score-dev.sh", "harness/score-holdout.sh",
        "harness/probe-holdout.sh",
    )
    if not all(os.path.isfile(os.path.join(target_dir, path)) for path in required_files):
        return False
    if not any(name.endswith(".json") for name in os.listdir(os.path.join(target_dir, "eval", "dev"))):
        return False
    if not any(name.endswith(".json") for name in os.listdir(os.path.join(target_dir, "eval", "holdout"))):
        return False
    for relative in required_files[1:]:
        with open(os.path.join(target_dir, relative)) as stream:
            if "LFD_CAPABILITY_UNAVAILABLE" in stream.read():
                return False
    return True


def onboarding_status(target_dir, checkout=None):
    target_dir = os.path.abspath(target_dir)
    contract = lfd_contract.load_target(target_dir)
    is_example = contract["lifecycle"]["status"] == "example"
    if not is_example and not os.path.isfile(os.path.join(target_dir, "target-profile.json")):
        return {"stage": "needs_inspection", "next_actions": ["onboard inspect"]}
    if not _designed(target_dir):
        return {"stage": "needs_design", "next_actions": ["run lfd-design"]}
    if not os.path.isfile(os.path.join(target_dir, "bundle", lfd_bundle.MANIFEST_PATH)):
        return {"stage": "needs_bundle", "next_actions": ["onboard equip"]}
    try:
        lfd_bundle.verify_bundle(target_dir)
    except lfd_bundle.BundleError:
        return {"stage": "bundle_invalid", "next_actions": ["regenerate bundle"]}
    if checkout and not os.path.isfile(os.path.join(os.path.abspath(checkout),
                                                    lfd_bundle.MANIFEST_PATH)):
        return {"stage": "needs_equip", "next_actions": ["onboard equip"]}
    audit, _ = lfd_common.audit_state(target_dir)
    if audit == "missing":
        return {"stage": "needs_audit", "next_actions": ["audit mechanical"]}
    if audit == "incomplete":
        return {"stage": "needs_judgment", "next_actions": ["audit finalize"]}
    if audit != "ok":
        return {"stage": "audit_invalid", "next_actions": ["audit mechanical"]}
    calibration, _ = lfd_common.calibration_state(target_dir)
    if calibration != "ok":
        return {"stage": "calibration_invalid", "next_actions": ["run calibration"]}
    if contract["lifecycle"]["status"] == "active":
        blockers = lfd_common.activation_blockers(contract, target_dir)
        return ({"stage": "active", "next_actions": []} if not blockers else
                {"stage": "activation_invalid", "next_actions": ["activate"]})
    if is_example:
        return {"stage": "example_ready", "next_actions": ["walkthrough"]}
    return {"stage": "ready_for_activation", "next_actions": ["activate"]}


def run_onboarding(hub_root, name, checkout, repository_url=None, template_root=None):
    """Run deterministic stages until model or human judgment is required."""
    target_dir = os.path.join(os.path.abspath(hub_root), "targets", name)
    if not os.path.isdir(target_dir):
        if not repository_url:
            raise ValueError("repository_url is required when starting a target")
        target_dir = start_target(hub_root, name, repository_url, template_root)["target_dir"]
    if not os.path.isfile(os.path.join(target_dir, "target-profile.json")):
        inspect_target(target_dir, checkout)
    state = onboarding_status(target_dir, checkout)
    if state["stage"] == "needs_bundle":
        root = template_root or os.path.join(os.path.dirname(__file__), "..", "templates")
        lfd_bundle.generate_bundle(target_dir, root)
        lfd_bundle.equip_bundle(target_dir, checkout)
        state = onboarding_status(target_dir, checkout)
    elif state["stage"] == "needs_equip":
        lfd_bundle.equip_bundle(target_dir, checkout)
        state = onboarding_status(target_dir, checkout)
    return state


def doctor(hub_root, target=None, checkout=None, require_github=False):
    checks = []
    checks.append({"name": "python", "status": "ok" if sys.version_info >= (3, 9) else "fail"})
    checks.append({"name": "git", "status": "ok" if shutil.which("git") else "fail"})
    docker = shutil.which("docker")
    docker_ok = bool(docker and subprocess.run([docker, "info"], stdout=subprocess.DEVNULL,
                                                stderr=subprocess.DEVNULL).returncode == 0)
    checks.append({"name": "docker", "status": "ok" if docker_ok else "fail"})
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    checks.append({"name": "github_credentials",
                   "status": "ok" if token else ("fail" if require_github else "advisory")})
    if target:
        try:
            lfd_contract.load_target(os.path.join(os.path.abspath(hub_root), "targets", target))
            status = "ok"
        except lfd_contract.ContractError:
            status = "fail"
        checks.append({"name": "target_contract", "status": status})
    if checkout:
        checks.append({"name": "checkout", "status": "ok" if _is_git_checkout(
            os.path.abspath(checkout)) else "fail"})
    return {"checks": checks, "status": "fail" if any(c["status"] == "fail" for c in checks) else "ok"}


def _emit(document, as_json):
    if as_json:
        print(json.dumps(document, sort_keys=True))
    else:
        print(f"{document['status']}: {document.get('stage') or document['command']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hub-root", default=os.path.join(os.path.dirname(__file__), ".."))
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="verb", required=True)
    start = sub.add_parser("start")
    start.add_argument("name")
    start.add_argument("repo_url")
    start.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    for verb in ("inspect", "equip", "verify", "status", "run"):
        command = sub.add_parser(verb)
        command.add_argument("name")
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        if verb in {"inspect", "equip", "verify", "status", "run"}:
            command.add_argument("--checkout")
        if verb == "run":
            command.add_argument("--repo-url")
    args = parser.parse_args()
    target_dir = os.path.join(os.path.abspath(args.hub_root), "targets",
                              getattr(args, "name", ""))
    try:
        if args.verb == "start":
            result = start_target(args.hub_root, args.name, args.repo_url)
            document = envelope("onboard.start", args.name, artifacts=[result["target_dir"]],
                                stage="needs_inspection", next_actions=["onboard inspect"])
        elif args.verb == "inspect":
            if not args.checkout:
                raise ValueError("--checkout is required")
            inspect_target(target_dir, args.checkout)
            state = onboarding_status(target_dir, args.checkout)
            document = envelope("onboard.inspect", args.name, stage=state["stage"],
                                artifacts=["target-profile.json"], next_actions=state["next_actions"])
        elif args.verb == "equip":
            if not args.checkout:
                raise ValueError("--checkout is required")
            lfd_bundle.generate_bundle(target_dir, os.path.join(os.path.dirname(__file__), "..", "templates"))
            lfd_bundle.equip_bundle(target_dir, args.checkout)
            state = onboarding_status(target_dir, args.checkout)
            document = envelope("onboard.equip", args.name, stage=state["stage"],
                                artifacts=["bundle", lfd_bundle.MANIFEST_PATH],
                                next_actions=state["next_actions"])
        elif args.verb == "verify":
            lfd_bundle.verify_bundle(target_dir)
            if args.checkout:
                lfd_bundle.verify_equipped(os.path.abspath(args.checkout))
            state = onboarding_status(target_dir, args.checkout)
            document = envelope("onboard.verify", args.name, stage=state["stage"],
                                next_actions=state["next_actions"])
        else:
            if args.verb == "run":
                if not args.checkout:
                    raise ValueError("--checkout is required")
                state = run_onboarding(args.hub_root, args.name, args.checkout,
                                       args.repo_url)
            else:
                state = onboarding_status(target_dir, args.checkout)
            pending = _requires_action(state["stage"])
            document = envelope(f"onboard.{args.verb}", args.name,
                                status="action_required" if pending else "ok",
                                stage=state["stage"], next_actions=state["next_actions"])
            _emit(document, args.json)
            return 3 if pending else 0
        _emit(document, args.json)
        return 0
    except (lfd_contract.ContractError, lfd_bundle.BundleError, ValueError) as exc:
        code = getattr(exc, "code", "invalid_input")
        document = envelope(f"onboard.{args.verb}", getattr(args, "name", None),
                            status="error", errors=[{"code": code, "message": str(exc)}])
        _emit(document, args.json)
        return 2


if __name__ == "__main__":
    sys.exit(main())
