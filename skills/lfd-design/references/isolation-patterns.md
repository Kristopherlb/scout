# Isolation patterns for holdout scoring

Phase 5's requirement is a property, not a mechanism: holdout scoring runs
in an execution context the agent has no network route to and no
credential to invoke. The patterns below are worked examples of that
property implemented on a few common setups. None of these is "the
design" — pick or adapt one to whatever's actually running the loop, and
don't let the specific mechanism leak into `goal.md` or the skill body.
The only thing that has to be true, regardless of mechanism: no route, no
credential, eval data unreadable from the agent's side.

**Default recommendation: the poll-based pattern below.** It satisfies the
same isolation property with the least infrastructure — no listener
service, no webhook secret, no second state file — because holdout checks
are meant to be rare (every K cycles) and a scheduled poll matches that
load pattern for free. Reach for a push/webhook variant only if holdout
latency genuinely needs to be near-instant, which is unusual given the
design already wants holdout kept sparse and expensive relative to dev.

## Pattern: two-repo, poll-based (recommended default)

Leanest version that still satisfies the property. Two repos, no running
listener service, one log file as the single source of truth.

```
target-repo/                  agent's write surface, dev loop fully local
  spec.md, goal.md, harness/score.sh --dev, eval/dev/

eval-repo/                    private, zero agent access, single source of truth
  skills/lfd-design/  (design/patch mode runs ONLY from here —
                                target-repo does not need its own copy)
  eval/holdout/, canary-list.json
  score.sh --holdout
  log.jsonl                   one append-only file: every holdout run adds
                               {cycle, sha, dev_score, dev_ci, holdout_score,
                                holdout_ci, timestamp}
  poll.yml                    scheduled job (e.g. every 5 min)
```

Flow:
1. Dev checks run fully local in target-repo, every cycle, no round trip.
2. Agent requests a holdout check by pushing an annotated tag
   (`holdout-check-N`) to target-repo. The tag message carries the current
   dev score + interval — this is what lets eval-repo skip a second query
   back to target-repo for dev-side numbers.
3. `poll.yml` in eval-repo wakes on schedule and lists new tags on
   target-repo since its last check. No inbound webhook, no listener
   process, no signature verification to maintain — eval-repo is always
   the one initiating contact, never receiving unsolicited requests.
4. Rate limiting and divergence detection both read off `log.jsonl`
   directly — no separate state file. Rate limit = count rows in the
   last-K-cycles window; skip the tag if too soon. Divergence = same rows,
   dev vs. holdout trend.
5. Pull the exact tagged SHA (no "latest HEAD" race — a tag is pinned by
   definition), run `score.sh --holdout` in eval-repo's own job, append one
   row to `log.jsonl`, post score + interval + divergence flag back as a
   commit status on that tag in target-repo.
6. Agent reads the status whenever it next checks. No blocking wait, no
   live round trip — the interval is short (poll cadence) but async either
   way.

Why this is the default over the webhook version: a webhook-triggered
listener is infra sized for a request pattern that doesn't exist here
(holdout checks are meant to be rare, every K cycles, not every push) —
running a service, verifying signatures, and rotating a webhook secret is
overhead bought for a load that a scheduled poll handles for free. The
push-based version is only worth the extra machinery if holdout latency
needs to be near-instant, which contradicts the design's own intent that
holdout stay sparse and expensive relative to dev.

## Pattern: separate repo + external CI runner (heavier alternative)

Three repos, different access scopes:
- **Repo A** — the target codebase. Agent has PR/write access. No grading
  logic lives here — not even a workflow file the agent could edit to
  weaken its own grading.
- **Repo B** — the runner. Public or private, agent has zero access. Owns
  the trigger (webhook on A, or a tag-push pattern for rate-limited
  holdout requests specifically), owns read credentials for A and C, owns
  the scoring orchestration.
- **Repo C** — holdout answers + canaries. Never checked out anywhere the
  agent's process runs. B pulls it into an isolated, ephemeral job only.

Notes from working through this shape:
- Pin to an exact commit SHA in the trigger payload — resolving "latest"
  at pull time is a race an agent pushing rapidly can exploit.
- Tag-push (rather than webhook-on-every-PR) as the holdout trigger
  naturally rate-limits and removes the SHA race, since a tag is pinned by
  definition — and matches the cadence holdout scoring is supposed to
  have anyway (rare, not every cycle).
- Keep dev scoring fully local — routing every cycle through an external
  runner turns the fast inner loop into a slow one and pressures the agent
  toward bundling multiple changes into fewer PRs to amortize latency,
  which breaks the one-variable-per-cycle rule.
- B's response to A should include the score interval, not a bare number
  — easy to silently drop this when focused on the isolation boundary,
  but dropping it reopens exhibit #15 (lucky-roll victory).
- Redirect verbose logging away from any log the agent's repo permissions
  can read — a `set -x` in the scorer can leak holdout content into CI
  logs even when the repos themselves are access-controlled correctly.

## Pattern: two isolated processes, one orchestrator

Generic version of the above without naming a specific CI product: agent
work happens in one process (container/VM/job); scoring happens in a
second, independent process; something above both — whatever sequences
"agent step, then scoring step" in your setup — holds the only handle
connecting them, and the agent's process never holds that handle itself.

- The isolation should come from absence (the two processes never had a
  connection to begin with), not from policy layered on top of a
  connection that exists by default. If the environment's default is
  "these two things share a network namespace unless configured
  otherwise," that's the wrong default to start from — prefer a setup
  where isolation is the starting state.
- Eval data lives wherever the scoring process can read it and the agent
  process can't — a mounted path scoped to the scoring process only, a
  baked-in artifact for the scoring process's image, or a fetch the agent
  process has no credential to perform. Any of these satisfy the
  requirement equally; pick based on how often you rotate eval data
  (frequent rotation favors a mount or fetch over baking in, since baking
  in means rebuilding an artifact on every rotation) and whether the
  scoring artifact could plausibly leave your control (favors mount/fetch
  over bake-in, since a baked artifact is a permanent copy wherever it
  ends up cached or archived).

## Common mistake to avoid regardless of pattern

Naming the mechanism ("sidecar," a specific orchestrator, a specific CI
product) in `goal.md` or in conversation about the design tends to import
that mechanism's *default* posture along with it — e.g. "sidecar" in most
container platforms means shared-network-by-default, which is the
opposite of what's needed here and requires extra policy to undo. State
the requirement (no route, no credential) first, choose an implementation
second, and verify the chosen implementation actually satisfies the
requirement (Phase 6, blinding check) rather than assuming the mechanism's
name implies the right isolation.
