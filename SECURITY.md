# Security policy

## Reporting a vulnerability

Do not disclose suspected vulnerabilities in a public issue. Use GitHub's
private vulnerability reporting for this repository. If that feature is not
available, contact the repository owner privately and include the affected
revision, impact, reproduction steps, and any suggested mitigation.

Security fixes are supported on the current `main` branch. Maintainers may ask
reporters to validate a fix before coordinated disclosure.

## Public source versus private operations

This repository is safe to publish only because it contains framework code and
synthetic fixtures. A deployment containing real `targets/<name>/` data is a
different security domain and must remain private.

The operational invariant is:

> No agent identity under evaluation, and no credential available to that
> identity, may read the operational hub.

Real holdout answers, canary lists, score logs, audit reports, and target
configuration must never be committed to this public repository. CI runs
`python3 tools/ci_checks.py public-release` to reject non-fixture target
directories and generated root artifacts.

Deletion in a later commit is not sanitization: Git history still contains the
data. If private evaluation content enters a public repository or a repository
that will become public, rotate the affected eval and rebuild the public source
from a clean, history-free snapshot.

## Operational access checklist

Apply these controls to every private operational hub:

- Grant access only to recognized humans who need it.
- Do not add bot or agent accounts that an evaluated system can control.
- Do not reuse deploy keys or tokens from target repositories.
- Scope the hub's status token to `Contents: read` and
  `Commit statuses: write` on target repositories only.
- Keep third-party Actions pinned to reviewed commit SHAs.
- Keep real target data out of Actions artifacts and logs.
- Review collaborators, deploy keys, secrets, and visibility at least
  quarterly.

## Egress discipline

The intended egress path is `ops/post-status.sh`. It returns only the score,
confidence interval, divergence flag, and boolean probe verdict. Do not add
case-level detail, operator names, holdout content, or scorer output to a
target-visible status.

## Running untrusted code

Target code is untrusted. Run it only through `ops/run-sandboxed.sh` with:

- networking disabled;
- the target checkout mounted read-only;
- a dedicated output directory;
- explicit resource and time limits;
- no mount or credential that exposes the hub, holdouts, or canaries.

Active target polling requires the Docker backend so CPU, memory, process,
network, and filesystem limits are all enforced. Non-container modes are for
tests and development only. A missing or unavailable isolation capability
fails closed.
