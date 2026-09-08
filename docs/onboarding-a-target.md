# Onboarding a target repository

Onboard real targets only from a private operational copy of LFD Evals. The
public source repository must contain synthetic fixtures only.

## 1. Scaffold the registry entry

```bash
bin/lfd new-target myrepo git@github.com:YOUR-ORG/myrepo.git
```

This creates `targets/myrepo/` with `STATUS="onboarding"`, empty eval
directories, and fail-closed starter harnesses. An onboarding target is never
polled, and the generated harnesses return an error until the design workflow
replaces them with real implementations.

## 2. Design the eval and harness

Run the LFD design skill from the private hub. The canonical skill source is
`skills/lfd-design/`; copy or link it into the discovery directory used by your
agent runtime.

The design process must:

- size the evaluation from an explicit effect size and confidence target;
- build `targets/myrepo/eval/{dev,holdout}`;
- replace both scripts under `targets/myrepo/harness/`;
- preserve the two-stage sandbox contract in
  [architecture.md](architecture.md);
- emit `targets/myrepo/goal.md`;
- generate canaries with `bin/lfd canaries myrepo`;
- configure the liveness gate in `targets/myrepo/config.env`.

If `BUILD_CMD`, `HEALTH_CHECK`, and `LIVENESS_EXEMPT` are all empty, activation
is blocked. A skipped liveness gate must be an explicit, justified exemption.

## 3. Equip the target repository

Copy and commit the agent-visible files:

```bash
cp -R templates/target-repo/. /path/to/myrepo/
cp skills/lfd-design/references/agent-instructions.md /path/to/myrepo/
cp targets/myrepo/goal.md /path/to/myrepo/
```

Never copy the holdout suite, canary list, private scorer, or operational log.

The target receives a developer scorer, a holdout request script, a status
reader, and an optional GitHub Actions transport. The request script first
pushes an annotated `holdout-check-N` tag directly. If its environment cannot
push tag refs, it appends the same request to
`.github/holdout-requests.jsonl`; the target workflow creates the tag with the
repository's `GITHUB_TOKEN`.

The copied workflow triggers only when the request queue changes. It is not
tied to a particular branch name or agent provider.

For centralized maintenance, a target may call the reusable workflow hosted in
your framework or private hub repository:

```yaml
name: holdout-request-tag
on:
  push:
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
bin/lfd audit myrepo
```

Commit `targets/myrepo/audit-report.json`. The report must pass and its stamped
`harness_version` must match the current harness. Add a calibration report with
non-overlapping known-good and known-bad intervals. Then choose the probe
cadence, configure the sandbox image, and set `STATUS="active"`.

CI blocks activation when the liveness, audit, or calibration gate is missing,
failed, or stale.

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
For local status checks, set `GITHUB_API_URL` to the API root for your GitHub
host; GitHub Actions supplies this variable automatically.

## Ongoing operations

| When | Action |
|---|---|
| Any time | Run `bin/lfd status` or open the dashboard |
| Unscheduled review | Run `bin/lfd review myrepo` and inspect cases hub-side |
| Divergence or weak probes | Run the LFD design skill in patch mode with an independent, stronger reviewer |
| Run ends | Run `bin/lfd retro myrepo` and capture newly observed cheats |
| Eval is exposed or reused | Rotate cases and regenerate per-run canaries |
| Pausing a target | Set `STATUS="paused"` to retain history without polling |
