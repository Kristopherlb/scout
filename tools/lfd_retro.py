#!/usr/bin/env python3
"""lfd_retro — distill a run into institutional memory.

Scaffolds targets/<name>/retros/<date>.md from log.jsonl: best score,
divergence events, probe-floor breaches, liveness failures, cost totals —
then prompts the human for the parts only they know (what generalized,
what was a cheat) and reminds them to append new exhibits to the
cheat-museum so every future target's red-team inherits them.

Usage: lfd_retro.py <target> [--hub-root PATH]
"""
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfd_common  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("target")
    p.add_argument("--hub-root", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".."))
    args = p.parse_args()

    hub_root = os.path.abspath(args.hub_root)
    target_dir = os.path.join(hub_root, "targets", args.target)
    rows = lfd_common.read_log(os.path.join(target_dir, "log.jsonl"))
    if not rows:
        sys.exit(f"no logged runs for {args.target} — nothing to retro")

    config_path = os.path.join(target_dir, "config.env")
    config = lfd_common.parse_config_env(config_path) if os.path.isfile(config_path) else {}
    try:
        window = lfd_common.config_int(config, "DIVERGENCE_WINDOW_CYCLES", minimum=2)
        floor = lfd_common.config_float(config, "PROBE_FLOOR", minimum=0, maximum=1)
    except lfd_common.ConfigError as exc:
        sys.exit(f"invalid target configuration: {exc}")

    scored = [r for r in rows if r.get("holdout_score") is not None]
    best = max(scored, key=lambda r: r["holdout_score"]) if scored else None
    divergent_cycles = [rows[i - 1].get("cycle") for i in range(window, len(rows) + 1)
                        if lfd_common.check_divergence(rows[:i], window)]
    breaches = [(r.get("cycle"), lfd_common.probe_floor_breaches(r, floor))
                for r in rows if r.get("probe")
                and lfd_common.probe_floor_breaches(r, floor)]
    liveness_fails = [r.get("cycle") for r in rows
                      if r.get("liveness") == "liveness_failed"]
    cost = sum(r.get("reported_cost_usd") or 0 for r in rows)
    tokens = sum((r.get("reported_tokens_in") or 0) +
                 (r.get("reported_tokens_out") or 0) for r in rows)
    models = sorted({r.get("model_id") for r in rows if r.get("model_id")})

    today = datetime.date.today().isoformat()
    retro_dir = os.path.join(target_dir, "retros")
    os.makedirs(retro_dir, exist_ok=True)
    out = os.path.join(retro_dir, f"{today}.md")
    if os.path.exists(out):
        sys.exit(f"retro already exists: {out} — edit it directly")

    def fmt_best():
        if not best:
            return "no scored runs"
        ci = best.get("holdout_ci") or ["?", "?"]
        return (f"{best['holdout_score']} [{ci[0]}, {ci[1]}] at cycle "
                f"{best.get('cycle')} (sha {str(best.get('sha', ''))[:8]}, "
                f"harness {best.get('harness_version', '?')})")

    with open(out, "w") as f:
        f.write(f"""# Retro — {args.target} — {today}

## Mechanical summary (from log.jsonl — do not edit, it has provenance)
- Runs logged: {len(rows)} · models: {', '.join(models) or 'unreported'}
- Best holdout: {fmt_best()}
- Divergence flagged at cycles: {divergent_cycles or 'none'}
- Probe-floor breaches: {[(c, sorted(b)) for c, b in breaches] or 'none'}
- Liveness failures at cycles: {liveness_fails or 'none'}
- Reported spend: ${cost:.2f} · {tokens / 1e6:.2f} Mtokens
- Efficiency: {'Δholdout/$ = %.4f' % ((scored[-1]['holdout_score'] - scored[0]['holdout_score']) / cost) if len(scored) >= 2 and cost > 0 else 'n/a'}

## Human judgment (fill these in — the machine can't)
- What generalized:
- What was memorization / a cheat (append each as an exhibit to
  `skills/lfd-design/references/cheat-museum.md`: what it looked
  like → Goodhart type → the fence that closed it):
- Loss-function patches made mid-run (and which family):
- Model/efficiency verdict (keep, switch, or A/B next run):
- Highest-leverage next steps:
""")
    print(f"retro scaffolded: {out}")
    print("Fill in the human-judgment section, then append any new cheats "
          "to the cheat-museum — that's the memory every future run inherits.")


if __name__ == "__main__":
    main()
