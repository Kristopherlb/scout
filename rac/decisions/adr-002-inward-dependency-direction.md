---
schema_version: 1
id: SCOUT-M214WWAJCBC5
type: decision
---
# Adopt an Inward Dependency Direction

## Context

Scout combines reusable policy logic, user-facing commands, privileged
operations adapters, workflow automation, and a shell entry point. A complete
package rewrite would obscure the open-source migration, but leaving the
dependency direction unstated would allow infrastructure details to spread.

## Decision

Scout adopts a partial Clean Architecture boundary around the current layout:

- `tools/lfd_common.py` is inner policy code.
- the remaining `tools/*.py` files are application commands and repository checks.
- `ops/` and `.github/workflows/` are outer operational adapters.
- `bin/lfd` is the composition root.

Dependencies point inward: adapters and the composition root may depend on
commands or policy, commands may depend on policy, and inner policy does not
depend on commands or adapters. Python runtime dependencies remain acyclic.
This decision establishes guardrails without claiming that the existing module
layout is the final architecture.

## Consequences

New coupling has a clear review rule and common violations can be rejected
deterministically. Existing subprocess boundaries remain visible but are not
misrepresented as Python imports. If command modules require adapter behavior,
they must receive it through an explicit interface or composition point rather
than importing privileged operations code.

## Status

Accepted

## Category

Architecture

## Alternatives Considered

An immediate full package reorganization was rejected because the migration
does not yet justify the churn. Unrestricted layer access was rejected because
it makes security-sensitive dependencies implicit. A strict ports-and-adapters
framework was deferred until concrete use cases show that additional
interfaces would deepen rather than fragment the modules.
