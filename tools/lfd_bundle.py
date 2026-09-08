#!/usr/bin/env python3
"""Generate, equip, and verify the explicitly agent-visible target bundle."""
import hashlib
import json
import os
import shutil


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


def _files(root):
    found = []
    if not os.path.isdir(root):
        return found
    for current, directories, names in os.walk(root):
        directories.sort()
        for name in sorted(names):
            found.append(os.path.relpath(os.path.join(current, name), root))
    return found


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


def generate_bundle(target_dir, template_root):
    """Rebuild ``target_dir/bundle`` from the narrow public allowlist."""
    target_dir = os.path.abspath(target_dir)
    bundle_dir = os.path.join(target_dir, "bundle")
    staging = bundle_dir + ".new"
    if os.path.isdir(staging):
        shutil.rmtree(staging)

    sources = []
    goal = os.path.join(target_dir, "goal.md")
    if not os.path.isfile(goal):
        raise BundleError("missing_public_artifact", "goal.md", "design has not emitted a goal")
    sources.append((goal, os.path.join(".lfd", "goal.md")))

    for source_root, destination_root in (
            (os.path.join(target_dir, "eval", "dev"), os.path.join(".lfd", "eval", "dev")),
            (os.path.join(target_dir, "dev-harness"), os.path.join(".lfd", "harness")),
            (os.path.join(template_root, "target-repo"), "")):
        for relative in _files(source_root):
            source_relative = os.path.relpath(os.path.join(source_root, relative), target_dir)
            if _private_source(source_relative):
                raise BundleError("private_material", source_relative,
                                  "path is not permitted in an agent-visible bundle")
            sources.append((os.path.join(source_root, relative),
                            os.path.join(destination_root, relative)))

    if not any(relative == os.path.join(".lfd", "harness", "score-dev.sh")
               for _, relative in sources):
        raise BundleError("missing_public_artifact", "dev-harness/score-dev.sh",
                          "the dev scorer is required")

    os.makedirs(staging)
    for source, relative in sources:
        _copy_file(source, os.path.join(staging, relative))

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
        raise BundleError("invalid_manifest", MANIFEST_PATH, str(exc))
    if set(manifest) != {"schema_version", "files"} or manifest["schema_version"] != BUNDLE_SCHEMA_VERSION:
        raise BundleError("invalid_manifest", MANIFEST_PATH, "unsupported manifest shape or version")
    if not isinstance(manifest["files"], dict):
        raise BundleError("invalid_manifest", MANIFEST_PATH, "files must be an object")
    return manifest


def verify_tree(root):
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


def verify_bundle(target_dir):
    manifest = verify_tree(os.path.join(os.path.abspath(target_dir), "bundle"))
    return {"status": "ok", "files": len(manifest["files"])}


def verify_equipped(checkout):
    """Verify managed files in a checkout while ignoring caller-owned files."""
    checkout = os.path.abspath(checkout)
    manifest = _load_manifest(checkout)
    for relative, expected_hash in manifest["files"].items():
        path = os.path.join(checkout, relative)
        if not os.path.isfile(path) or _hash(path) != expected_hash:
            raise BundleError("bundle_drift", relative,
                              "equipped file is missing or differs from its manifest hash")
        if _private_source(relative):
            raise BundleError("private_material", relative, "manifest contains a forbidden path")
    return manifest


def equip_bundle(target_dir, checkout):
    """Install a verified bundle without clobbering caller-owned content."""
    bundle_root = os.path.join(os.path.abspath(target_dir), "bundle")
    checkout = os.path.abspath(checkout)
    manifest = verify_tree(bundle_root)
    old_manifest = None
    if os.path.isfile(os.path.join(checkout, MANIFEST_PATH)):
        old_manifest = _load_manifest(checkout)

    for relative, new_hash in manifest["files"].items():
        destination = os.path.join(checkout, relative)
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
    verify_equipped(checkout)
    return {"status": "ok", "files": len(manifest["files"])}
