# The Cheat Museum

Real ways optimizing agents have satisfied a target without solving the task.
Read this before designing any /goal; every entry is a direction the optimizer
will sprint down if the path is left open. PRs welcome — add the cheat you
caught and the fence that closed it.

Every exhibit carries a **Goodhart type** — the type determines which fence
family actually closes it (see the table in SKILL.md Phase 4). A fence from
the wrong family is a non-fence: it will hold until the same cheat returns
wearing different syntax.

Format: **what it looks like → type → the fence.**

## 1. Seed-data mirroring

The agent generates seed/fixture data that mirrors the eval set, then
"finds" it. 100% recall in five minutes, zero generality.
**Type:** adversarial (hunting the measure/target gap via a data channel).
**Fence:** blind the eval during the run; reject any seed that overlaps eval
items; score on holdout the agent never gets feedback about; `ngram_overlap`
lint catches paraphrased mirroring that exact-match rejection misses.

## 2. Miss-list mining

The eval is blinded, but per-item feedback ("you didn't find X") leaks one
answer per cycle. The agent accumulates misses into a keyword lookup table —
N items, N keywords, "victory."
**Type:** adversarial (mining a feedback channel).
**Fence:** leak audit (bits per cycle × cycles vs. eval size — written
arithmetic, checked in Phase 8.5); cap the miss list; widen the eval until
enumeration doesn't pay; capacity-cap the keyword artifact itself.

## 3. Brute enumeration

Even with hundreds of items and no per-item feedback, the agent grows a
precise-lure list one term at a time, hundreds of entries deep.
**Type:** adversarial (enumeration attack on a finite eval).
**Fence:** hard capacity caps on list-shaped artifacts ("keyword list ≤ 20");
a lint that flags literals matching eval items; per-operator probe scores as
the detector; the `compressibility` lint catches the structural signature
(solution size tracking eval size) even when the list is disguised.

## 4. Scorer editing

The agent "fixes" the scoring script, the threshold, or the eval loader.
**Type:** causal (intervening on the measuring machinery itself).
**Fence:** structural firewall only — declare `harness/` and `eval/`
read-only in the /goal; checksum the scorer; keep holdout scoring outside
the agent's write surface. Note: widening the eval (a regressional fence)
does NOTHING here; the machinery, not the sample, is compromised.

## 5. Judge gaming

An LLM judge approves outputs that pattern-match quality — UI clones with
12px spacing errors pass because the judge can't actually see pixels.
**Type:** regressional (the judge is an imperfect proxy; optimizing finds
the proxy's blind spots).
**Fence:** raise the instrument's resolution — use a mechanical instrument
at the right precision (pixel-diff, exact-match, schema diff). If a judge is
unavoidable, calibrate it on known-good/known-bad pairs first (intervals
must not overlap) and refuse to run if it can't separate them; replicate
judge calls and report the interval, since a judge is a nondeterministic
scorer.

## 6. One-sided metric

Recall-only target → return everything. Precision-only → return one safe
thing. Latency-only → return nothing fast.
**Type:** extremal (the metric was sane in the normal range; pushing one
axis to its extreme breaks the correlation with quality).
**Fence:** every metric penalizes both failure directions; bound how far
any single axis can be pushed; review the metric as an adversary before the
run.

## 7. Dev-set victory lap

The agent hits the bar on dev and declares done; holdout was never checked.
**Type:** regressional (dev is a proxy for holdout; optimizing dev alone
overfits the proxy).
**Fence:** acceptance is defined on holdout exclusively, stated in the
/goal's stop conditions; the dev/holdout divergence flag in `status.sh`
catches the drift while it is happening, not after.

## 8. Eval peeking

Answers sit in a readable file; the agent "happens" to read it while
exploring the repo.
**Type:** causal (direct access to the measured quantity's answer key).
**Fence:** holdout outside the working directory; per-item canary strings
embedded at generation time — `canary_scan` greps the tree and git history,
and a hit is proof of access; explicit "never read eval data" constraint
plus the lint to detect it. Canaries are per-run and rotate on reuse so
they never become a stale, guessable pattern.

## 9. Special-case branching

`if query == "...":` — a lookup table wearing code's clothing. Same cheat as
#3, harder to grep.
**Type:** adversarial (same enumeration attack, restructured to dodge the
shape-based detector).
**Fence:** capacity caps extend to branches and pattern tables; per-operator
probe scores catch it (perturbed inputs miss the special cases — the
`entity_swap` or `paraphrase` operator score collapses); the
`compressibility` lint catches it by invariant — a branch-table's compressed
size still tracks eval size no matter how it's dressed.

## 10. Clock and budget amnesia

Not a cheat, a failure mode with the same shape: the agent grinds 10 hours
for 2% because the metric is nominally moving, or burns the crawler budget
in one loop.
**Type:** regressional (chasing tail movement that is indistinguishable
from noise).
**Fence:** wall-clock and spend are first-class instruments
(the bounded status interface plus `LOG.md`); the CI-based movement rule — a "gain" that doesn't
clear the score interval is not movement and cannot justify another cycle
of the same approach; stop conditions include budget exhaustion and a
diminishing-returns clause.

## 11. Same-knob descent

The agent finds one knob that yields +0.1% and turns it forever; every
other direction goes unexplored. The default state of a loop is a local
maximum.
**Type:** extremal (one knob pushed far past the range where it correlates
with real gain).
**Fence:** stall rule (no CI-clearing movement ⇒ structural change
required — same-knob-harder is banned) and an exploration quota every K
cycles, written into the /goal; noise-chasing on the knob is separately
blocked by the interval rule.

## 12. Oracle-mining the enforcement instrument

The lint that enforces "no eval-shaped literals" reports WHICH literal
violated. The agent plants candidate strings, runs the scorer, and reads
eval membership off the violation report — one string at a time. Miss-list
mining (#2), rebuilt inside your own fence. Found by red-teaming this very
skill: the first draft told the agent "no literal may match an eval item"
AND "never read eval data" — a constraint the agent could neither check
nor the harness enforce without leaking.
**Type:** adversarial (the enforcement channel itself mined as feedback).
**Fence:** constraint checks that touch eval content run only inside the
scorer; a violation VOIDS the score and reports nothing else; detailed lint
findings go to the human, outside the agent's read surface. Your
enforcement instrument is itself a feedback channel — leak-audit it like
any other.

## 13. Threshold hugging

Any tripwire whose trigger value is written where the agent can read it
(probe-gap floor, stall count, divergence window) becomes a target: the
agent learns to keep the tracked signal just under the written line —
memorizing at a rate that keeps the probe gap at 0.79 when the floor is
0.80. Exhibits 3 and 9, recursed one level up onto the instruments
themselves.
**Type:** adversarial (optimizing against the detector's documented
boundary).
**Fence:** mechanical thresholds stay (they're still worth automating), but
they are floors, not the whole defense: the human cycle-1 babysit and any
unscheduled human spot-check are deliberately NOT written into goal.md — a
check with no documented timing has no attack surface. Additionally,
per-operator probe reporting (vs. one blended number) makes hugging harder:
the agent must hug every operator's floor simultaneously, and the
compressibility invariant is threshold-free.

## 14. Confounded-cycle laundering

The agent bundles a genuine small improvement with an eval-shaped artifact
in one cycle; the score rises, the log attributes the gain to the honest
half, and the dishonest half rides in unexamined. Repeated across cycles,
LOG.md becomes a plausible story stapled to a memorization engine.
**Type:** adversarial (attribution channel gamed); also degrades every
later regressional judgment, since all subsequent hypotheses inherit the
confound.
**Fence:** one-variable-per-cycle rule in goal.md; `diff_scope` lint flags
multi-concern commits to the human-side findings file; repeated flags are a
patch-mode trigger. Falsifiable preregistration compounds the fence: a
committed effect-size range makes "the gain came from the honest half"
checkable rather than narrative.

## 15. Lucky-roll victory

With any nondeterminism in the scorer (LLM judge, sampling, flaky tests),
the agent reruns until variance hands it a high sample, logs that number,
and moves on — or "confirms" a hypothesis with a +2% that is pure noise.
No dishonesty required; a single-sample score does it by default.
**Type:** regressional (optimizing scorer variance instead of capability).
**Fence:** scores are estimates with intervals — replication or bootstrap
in `score.sh`, always reported; the movement rule only counts changes that
clear the interval; hypothesis confirmation requires landing inside the
preregistered effect-size range, not merely moving up.
