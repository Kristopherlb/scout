# Executable public walkthrough

Scout ships one synthetic target, `_example`, so the public repository can
prove its lifecycle without private data, credentials, or an external target.

## Run it

Requirements: Python 3.9 or newer, Git, Bash, and a checkout you trust to
execute. From the repository root:

```bash
bin/lfd walkthrough
```

The command works in a disposable copy. It creates standalone Git repositories
for the committed known-good and known-bad solutions, then exercises the real
contract, bundle, scorer, audit, and activation commands. It does not alter the
checkout that launched it.

Expected stages:

```text
ok  contract_valid
ok  bundle_verified
ok  dev_scored
ok  calibration_verified
ok  mechanical_incomplete
ok  activation_refused
ok  audit_finalized
ok  activation_succeeded
success
```

For an agent-readable result, use:

```bash
bin/lfd walkthrough --json
```

The JSON response uses Scout's versioned command envelope. It includes the
command, target, status, stage, artifacts, stable errors, and next actions.

## What each stage proves

| Stage | Executable evidence |
|---|---|
| `contract_valid` | `_example/target.json` passes the one strict contract loader. |
| `bundle_verified` | Every allowlisted target-visible file matches its SHA-256 manifest and no private-shaped path appears. |
| `dev_scored` | The real visible scorer gives the known-good square implementation a score of 1.0. |
| `calibration_verified` | The real private scorer reproduces the committed non-overlapping good and bad calibration results. |
| `mechanical_incomplete` | Mechanical PASS writes evidence but returns exit 3 because independent judgment is still required. |
| `activation_refused` | Activation remains blocked while judgment is incomplete. |
| `audit_finalized` | The fixture judgment supplies five explicit findings and binds all six evidence hashes. |
| `activation_succeeded` | The only supported active transition succeeds and writes a matching receipt. |

The fixture is deliberately tiny. Its observed case range demonstrates the
score contract but makes no population-level confidence claim. Real designs
must size their holdout and use the uncertainty method declared in `goal.md`.

The walkthrough explicitly selects Scout's non-container development mode for
the committed fixture code. Operational targets do not inherit that choice:
active polling requires the digest-pinned Docker sandbox and fails closed when
it is unavailable.

## Continue with a private target

Read [Onboarding a target repository](onboarding-a-target.md). Real holdouts,
canaries, logs, audits, and target contracts belong in a separate private
operational hub, never in this public source repository.
