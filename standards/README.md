# Scout standards controls

The canonical requirements and architecture decisions live in `rac/`. The
control registry in `controls.json` gives every normative requirement exactly
one stable control ID and identifies how compliance is evidenced.

Controls use one of two enforcement modes:

- `ci` names a deterministic command that runs in the required CI checks.
- `human-review` names a concrete pull-request review procedure when semantic
  judgment cannot honestly be represented by a static rule.

`FAIL` controls are merge-blocking obligations. `WARN` controls are advisory
but must still be considered and recorded during review. The deterministic
checker validates mapping coverage, metadata, dependency direction, authorized
log-writing boundaries, and the CI workflow contract.

## Local validation

RAC is a standards-corpus validator and guidance generator. It does not inspect
Scout source semantics; Scout's checker owns those rules. Use Python 3.11 or
newer for RAC. The direct release is recorded in `rac-version.txt`; the complete
dependency graph and distribution hashes are pinned in
`rac-requirements.lock`.

```bash
RAC_VERSION=$(cat standards/rac-version.txt)
python3 -m pip install --require-hashes -r standards/rac-requirements.lock
test "$(rac --version)" = "rac $RAC_VERSION"
rac gate rac/
rac export rac/ --agent-rules --check
python3 tools/check_standards.py all
```

When an accepted decision changes, regenerate and commit the managed guidance:

```bash
rac export rac/ --agent-rules
```

Update the version pin only in a dedicated, reviewed change. Regenerate the
hash lock from that pin, then run the guidance generator and complete the standards
gate:

```bash
RAC_VERSION=$(cat standards/rac-version.txt)
printf 'rac-core==%s\n' "$RAC_VERSION" | uv pip compile - \
  --generate-hashes --python-version 3.12 \
  --output-file standards/rac-requirements.lock
```

RAC is maintained by the
[`asdecided/rac`](https://github.com/asdecided/rac) project.
