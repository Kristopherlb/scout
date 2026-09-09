# Onboarding a target repository

Onboard real targets only from a private operational copy of Scout. The
public source repository must contain synthetic fixtures only.

Before using real material, run the public lifecycle proof from a trusted
checkout:

```bash
bin/lfd walkthrough
```

It uses only `_example`, makes no network request, and leaves the launching
checkout unchanged. [The walkthrough guide](walkthrough.md) explains every
stage and the fixture's limits.

## 1. Scaffold the registry entry

```bash
bin/lfd doctor
bin/lfd onboard start myrepo git@github.com:YOUR-ORG/myrepo.git
bin/lfd onboard inspect myrepo --checkout /path/to/myrepo
```

This creates `targets/myrepo/` with `lifecycle.status` set to `onboarding`, empty eval
directories, and executable harnesses that fail with `capability_unavailable`.
An onboarding target is never polled; scoring remains unavailable until the
design workflow replaces those fail-closed implementations. Inspection writes
a sanitized `target-profile.json` without local paths or source content.

## 2. Design the eval and harness

Run `lfd-design` from the private hub. It owns design only; shared scientific
references and calculators live under the non-invocable `skills/lfd-shared/`.

The design process must:

- size the evaluation from an explicit effect size and confidence target;
- build `targets/myrepo/eval/{dev,holdout}`;
- replace the private scripts under `targets/myrepo/harness/` and the visible
  `targets/myrepo/dev-harness/score-dev.sh`;
- preserve the two-stage sandbox contract in
  [architecture.md](architecture.md);
- emit `targets/myrepo/goal.md`;
- generate canaries with `bin/lfd canaries myrepo`;
- configure the liveness gate in `targets/myrepo/target.json`.

If the build command, health check, and written exemption are all empty, activation
is blocked. A skipped liveness gate must be an explicit, justified exemption.

## 3. Equip the target repository

Generate, verify, and install the agent-visible files:

```bash
bin/lfd onboard equip myrepo --checkout /path/to/myrepo
bin/lfd onboard verify myrepo --checkout /path/to/myrepo
```

The generated manifest is the allowlist and integrity record. Equip fails on
conflicts instead of overwriting caller-owned content. It installs only the
target-side `lfd-execute` skill and updates bounded Codex, Claude, Cursor, and
Copilot blocks idempotently; hub-side skills remain private. Never bypass it to copy
the holdout suite, canary list, private scorer, or operational log.

The target receives a developer scorer, a holdout request script, a status
reader, and a GitHub Actions fallback transport. Each request uses a random ID
and an immutable `<prefix>v1-<sha12>-<request-id>` annotated tag whose payload
contains the full requested SHA. The script pushes that tag directly when it
can. If tag refs are unavailable, it creates a one-commit
`lfd-request/<request-id>` branch in an isolated worktree. The caller's branch,
index, staged changes, and untracked files are untouched.

The fallback workflow validates that the request log is the only changed file,
the request commit's sole parent is the requested SHA, and the branch, tag, and
payload identities agree. It creates the tag and removes the ephemeral remote
branch. The hub repeats identity validation before scoring.

For centralized maintenance, a target may call the reusable workflow hosted in
your framework or private hub repository:

```yaml
name: holdout-request-tag
on:
  push:
    branches: ["lfd-request/**"]
    paths: [".github/holdout-requests.jsonl"]
permissions:
  contents: write
jobs:
  call:
    uses: OWNER/REPOSITORY/.github/workflows/holdout-request-tag-reusable.yml@main
```

Pin `OWNER/REPOSITORY` to the reviewed host and revision you operate. The caller
must be allowed to read the reusable workflow. The self-contained copied
workflow has no cross-repository dependency.

## 4. Audit, calibrate, and activate

```bash
bin/lfd audit mechanical myrepo
bin/lfd audit finalize myrepo --judgment-file /path/to/judgment.json
bin/lfd activate myrepo
```

The mechanical command writes deterministic evidence but deliberately remains
incomplete. Finalization requires a fresh-context judgment with explicit
PASS/FAIL findings and evidence for leakage, Goodhart fences, calibration,
escalation, and blinding. The attestation records process; it is not proof that
the context was independent.

The final report binds the goal, eval manifest, agent bundle, private harness,
calibration, and judgment with SHA-256 hashes. `bin/lfd activate` is the only
supported way to set active status and writes an activation receipt. Editing
`target.json` to active by hand remains blocked.

CI and polling block active targets when liveness, audit, calibration, or the
activation receipt is missing, failed, malformed, or stale.

All agent-facing commands accept `--json`. Their versioned envelope contains
the command, target, status, stage, artifacts, stable errors, and next actions.
Exit codes are `0` for success, `2` for invalid input or contract, `3` while
judgment or an external result is pending, and `4` for infrastructure or
transport failure.

## 5. Configure private automation

In the private hub only:

1. Create a fine-grained token scoped to the target repositories. It needs
   `Contents: read` to clone and `Commit statuses: write` to report results.
2. Store it as the `EVAL_REPO_STATUS_TOKEN` Actions secret.
3. Configure a deliberate polling schedule in
   `.github/workflows/poll-holdout.yml`. The public template is manual-only so
   cloning it cannot silently start an operational schedule.
4. Review the workflow's `contents: write` permission and branch protection so
   its append-only log commits can land safely.

Smoke-test one cycle:

```bash
# In the target repository
scripts/target-repo/request-holdout-check.sh 0.5 0.45 0.55

# In the private hub
bin/lfd poll myrepo
bin/lfd status
```

Confirm that exactly one log row was appended, the target commit received a
bounded status, and no holdout content appeared in target-visible output.
For status checks, set `GITHUB_API_URL` to the API root for your GitHub host and
provide `GH_TOKEN` or `GITHUB_TOKEN`. The reader queries only the exact
`lfd/holdout` context; unrelated aggregate CI failures do not change the result.

## Ongoing operations

| When | Action |
|---|---|
| Any time | Run `bin/lfd status` or open the dashboard |
| Unscheduled review | Run `bin/lfd review myrepo` and inspect cases hub-side |
| Divergence or weak probes | Invoke `lfd-patch` hub-side with a stronger design model, then require a fresh `lfd-audit` |
| Run ends | Run `bin/lfd retro myrepo` and capture newly observed cheats |
| Eval is exposed or reused | Rotate cases and regenerate per-run canaries |
| Pausing a target | Set `lifecycle.status` to `paused` to retain history without polling |
