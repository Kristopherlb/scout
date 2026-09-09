#!/usr/bin/env python3
"""Generate, equip, and verify the explicitly agent-visible target bundle."""
import hashlib
import json
import os
import shutil

import lfd_contract
import lfd_holdout_protocol
import lfd_shims

BUNDLE_SCHEMA_VERSION = 1
MANIFEST_PATH = os.path.join(".lfd", "bundle-manifest.json")


class BundleError(ValueError):
    def __init__(self, code, path, message):
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code} at {path}: {message}")


def _hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _files(root):
    found: list[str] = []
    if not os.path.isdir(root):
        return found
    for current, directories, names in os.walk(root):
        directories.sort()
        for name in sorted(names):
            found.append(os.path.relpath(os.path.join(current, name), root))
    return found


def _symlinks(root):
    found: list[str] = []
    if not os.path.isdir(root):
        return found
    for current, directories, names in os.walk(root, followlinks=False):
        for name in directories + names:
            path = os.path.join(current, name)
            if os.path.islink(path):
                found.append(os.path.relpath(path, root))
    return sorted(found)


def _managed_path_has_symlink(root, relative):
    current = root
    for part in relative.split(os.sep):
        current = os.path.join(current, part)
        if os.path.islink(current):
            return True
    return False


def _private_source(relative):
    parts = relative.lower().split(os.sep)
    name = parts[-1]
    if any(part in {"holdout", "runs"} for part in parts):
        return True
    if name in {"activation.json", "audit-mechanical.json", "audit-report.json",
                "canary-list.json", "log.jsonl", "calibration-report.json",
                "score-holdout.sh", "probe-holdout.sh"}:
        return True
    if parts[:2] == ["eval", "dev"] and any(word in name for word in ("answer", "holdout", "canary")):
        return True
    return False


def _copy_file(source, destination):
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    shutil.copy2(source, destination)


def _bundle_inputs(target_dir, template_root):
    """Return destination paths and current bytes for the public allowlist."""
    target_dir = os.path.abspath(target_dir)
    sources = []
    goal = os.path.join(target_dir, "goal.md")
    if not os.path.isfile(goal):
        raise BundleError("missing_public_artifact", "goal.md", "design has not emitted a goal")
    sources.append((goal, os.path.join(".lfd", "goal.md")))

    for source_root, destination_root in (
            (os.path.join(target_dir, "eval", "dev"), os.path.join(".lfd", "eval", "dev")),
            (os.path.join(target_dir, "dev-harness"), os.path.join(".lfd", "harness")),
            (os.path.join(template_root, "target-repo"), "")):
        links = _symlinks(source_root)
        if links:
            raise BundleError("unsafe_symlink", os.path.join(source_root, links[0]),
                              "agent-visible bundle sources must not contain symbolic links")
        for relative in _files(source_root):
            source_relative = os.path.relpath(os.path.join(source_root, relative), target_dir)
            if _private_source(source_relative):
                raise BundleError("private_material", source_relative,
                                  "path is not permitted in an agent-visible bundle")
            sources.append((os.path.join(source_root, relative),
                            os.path.join(destination_root, relative)))

    execute_skill = os.path.join(os.path.dirname(os.path.abspath(template_root)),
                                 "skills", "lfd-execute")
    if not os.path.isfile(os.path.join(execute_skill, "SKILL.md")):
        raise BundleError("missing_public_artifact", "skills/lfd-execute/SKILL.md",
                          "target-side execution skill is required")
    links = _symlinks(execute_skill)
    if links:
        raise BundleError("unsafe_symlink", os.path.join(execute_skill, links[0]),
                          "agent-visible bundle sources must not contain symbolic links")
    for relative in _files(execute_skill):
        sources.append((os.path.join(execute_skill, relative),
                        os.path.join(".agents", "skills", "lfd-execute", relative)))

    if not any(relative == os.path.join(".lfd", "harness", "score-dev.sh")
               for _, relative in sources):
        raise BundleError("missing_public_artifact", "dev-harness/score-dev.sh",
                          "the dev scorer is required")

    inputs = {}
    for source, relative in sources:
        if os.path.islink(source):
            raise BundleError("unsafe_symlink", relative,
                              "agent-visible bundle sources must be regular files")
        with open(source, "rb") as stream:
            inputs[relative] = (stream.read(), os.stat(source).st_mode)

    contract = lfd_contract.load_target(target_dir)
    protocol = {
        "protocol_version": contract["holdout"]["protocol_version"],
        "tag_prefix": contract["holdout"]["tag_prefix"],
        "status_context": lfd_holdout_protocol.STATUS_CONTEXT,
    }
    inputs[os.path.join(".lfd", "holdout-protocol.json")] = (
        (json.dumps(protocol, indent=2, sort_keys=True) + "\n").encode(), 0o644)
    return inputs


def generate_bundle(target_dir, template_root):
    """Rebuild ``target_dir/bundle`` from the narrow public allowlist."""
    target_dir = os.path.abspath(target_dir)
    bundle_dir = os.path.join(target_dir, "bundle")
    staging = bundle_dir + ".new"
    if os.path.isdir(staging):
        shutil.rmtree(staging)
    inputs = _bundle_inputs(target_dir, template_root)

    os.makedirs(staging)
    for relative, (content, mode) in inputs.items():
        destination = os.path.join(staging, relative)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with open(destination, "wb") as stream:
            stream.write(content)
        os.chmod(destination, mode)

    file_hashes = {relative: _hash(os.path.join(staging, relative))
                   for relative in _files(staging)}
    manifest = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "files": file_hashes,
    }
    manifest_file = os.path.join(staging, MANIFEST_PATH)
    os.makedirs(os.path.dirname(manifest_file), exist_ok=True)
    with open(manifest_file, "w") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
        stream.write("\n")

    if os.path.isdir(bundle_dir):
        shutil.rmtree(bundle_dir)
    os.replace(staging, bundle_dir)
    return manifest


def _load_manifest(root):
    path = os.path.join(root, MANIFEST_PATH)
    try:
        with open(path) as stream:
            manifest = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleError("invalid_manifest", MANIFEST_PATH, str(exc)) from exc
    if set(manifest) != {"schema_version", "files"} or manifest["schema_version"] != BUNDLE_SCHEMA_VERSION:
        raise BundleError("invalid_manifest", MANIFEST_PATH, "unsupported manifest shape or version")
    if not isinstance(manifest["files"], dict):
        raise BundleError("invalid_manifest", MANIFEST_PATH, "files must be an object")
    return manifest


def verify_tree(root):
    links = _symlinks(root)
    if links:
        raise BundleError("unsafe_symlink", links[0],
                          "bundle trees must not contain symbolic links")
    manifest = _load_manifest(root)
    actual = set(_files(root)) - {MANIFEST_PATH}
    expected = set(manifest["files"])
    if actual != expected:
        detail = f"missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
        raise BundleError("bundle_drift", root, detail)
    for relative, expected_hash in manifest["files"].items():
        if _hash(os.path.join(root, relative)) != expected_hash:
            raise BundleError("bundle_drift", relative, "content hash does not match manifest")
        if _private_source(relative):
            raise BundleError("private_material", relative, "manifest contains a forbidden path")
    return manifest


def verify_bundle(target_dir, template_root=None):
    target_dir = os.path.abspath(target_dir)
    if template_root is None:
        template_root = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "templates")
    manifest = verify_tree(os.path.join(target_dir, "bundle"))
    inputs = _bundle_inputs(target_dir, template_root)
    current = {relative: _hash_bytes(content) for relative, (content, _) in inputs.items()}
    if manifest["files"] != current:
        changed = sorted(relative for relative in set(manifest["files"]) | set(current)
                         if manifest["files"].get(relative) != current.get(relative))
        raise BundleError("bundle_drift", "bundle", "source changed: " + ", ".join(changed))
    return {"status": "ok", "files": len(manifest["files"])}


def verify_equipped(checkout):
    """Verify managed files in a checkout while ignoring caller-owned files."""
    checkout = os.path.abspath(checkout)
    manifest = _load_manifest(checkout)
    for relative, expected_hash in manifest["files"].items():
        path = os.path.join(checkout, relative)
        if (_managed_path_has_symlink(checkout, relative)
                or not os.path.isfile(path) or _hash(path) != expected_hash):
            raise BundleError("bundle_drift", relative,
                              "equipped file is missing or differs from its manifest hash")
        if _private_source(relative):
            raise BundleError("private_material", relative, "manifest contains a forbidden path")
    lfd_shims.verify_all(checkout)
    return manifest


def equip_bundle(target_dir, checkout):
    """Install a verified bundle without clobbering caller-owned content."""
    bundle_root = os.path.join(os.path.abspath(target_dir), "bundle")
    checkout = os.path.abspath(checkout)
    verify_bundle(target_dir)
    manifest = verify_tree(bundle_root)
    old_manifest = None
    if _managed_path_has_symlink(checkout, MANIFEST_PATH):
        raise BundleError("target_conflict", MANIFEST_PATH,
                          "managed manifest path contains a symbolic link")
    if os.path.isfile(os.path.join(checkout, MANIFEST_PATH)):
        old_manifest = _load_manifest(checkout)
    lfd_shims.preflight_all(checkout)

    for relative, new_hash in manifest["files"].items():
        destination = os.path.join(checkout, relative)
        if _managed_path_has_symlink(checkout, relative):
            raise BundleError("target_conflict", relative,
                              "managed destination path contains a symbolic link")
        if not os.path.exists(destination):
            continue
        current_hash = _hash(destination)
        prior_hash = (old_manifest or {}).get("files", {}).get(relative)
        if current_hash != new_hash and current_hash != prior_hash:
            raise BundleError("target_conflict", relative,
                              "target file differs from both current and previously managed content")

    if old_manifest:
        for relative, prior_hash in old_manifest["files"].items():
            if relative in manifest["files"]:
                continue
            destination = os.path.join(checkout, relative)
            if os.path.isfile(destination) and _hash(destination) == prior_hash:
                os.remove(destination)

    for relative in manifest["files"]:
        _copy_file(os.path.join(bundle_root, relative), os.path.join(checkout, relative))
    _copy_file(os.path.join(bundle_root, MANIFEST_PATH),
               os.path.join(checkout, MANIFEST_PATH))
    lfd_shims.apply_all(checkout)
    verify_equipped(checkout)
    return {"status": "ok", "files": len(manifest["files"])}
