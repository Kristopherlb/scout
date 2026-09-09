---
name: lfd-onboard
description: Establishes and resumes a Scout target registry entry through the stable onboarding CLI. Use in a private Scout hub when the user wants to register a repository, inspect its checkout, determine the artifact-derived stage, equip the verified agent bundle, diagnose prerequisites, or hand the target to design and audit without manual copying.
---

# LFD Onboard

Use Scout's CLI as the source of lifecycle truth. Do not hand-create registry
files, copy bundle contents, or set `lifecycle.status` to `active` directly.

## Start or resume

```bash
bin/lfd doctor --json
bin/lfd onboard start <name> <repo-url> --json
bin/lfd onboard inspect <name> --checkout <path> --json
bin/lfd onboard status <name> --checkout <path> --json
```

If the target already exists, start from `onboard status`. Interpret the stable
exit codes literally: `0` success, `2` invalid contract/input, `3` external or
judgment work pending, and `4` infrastructure/transport failure. GitHub
credentials are advisory unless the requested operation contacts GitHub.

At `needs_design`, hand off to `lfd-design`; do not fill scorer stubs with fake
success. After design completes:

```bash
bin/lfd onboard equip <name> --checkout <path> --json
bin/lfd onboard verify <name> --checkout <path> --json
bin/lfd onboard status <name> --checkout <path> --json
```

Equip is conflict-safe and manages only manifest files plus bounded instruction
blocks. Preserve all caller-owned content outside those blocks. At
`needs_audit` or `needs_judgment`, request `lfd-audit` in a fresh context. Run
`bin/lfd activate <name> --json` only after status reports
`ready_for_activation`.
