#!/usr/bin/env python3
"""lfd_status — one-look health of every target, rendered from log.jsonl.

Every number shown here traces to a committed log row (sha + timestamp +
harness_version): no number without provenance.

Usage: lfd_status.py [--hub-root PATH] [--target NAME]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfd_common  # noqa: E402


def fmt_ci(score, ci):
    if score is None:
        return "—"
    if isinstance(ci, list) and len(ci) == 2 and all(
            isinstance(x, (int, float)) for x in ci):
        return f"{score:.3f} [{ci[0]:.3f}, {ci[1]:.3f}]"
    return f"{score:.3f}"


def efficiency(rows):
    """Δholdout per $ and per Mtoken across the logged run, where reported."""
    scored = [r for r in rows if r.get("holdout_score") is not None]
    if len(scored) < 2:
        return None, None
    delta = scored[-1]["holdout_score"] - scored[0]["holdout_score"]
    cost = sum(r.get("reported_cost_usd") or 0 for r in scored)
    tokens = sum((r.get("reported_tokens_in") or 0) +
                 (r.get("reported_tokens_out") or 0) for r in scored)
    per_dollar = delta / cost if cost > 0 else None
    per_mtok = delta / (tokens / 1e6) if tokens > 0 else None
    return per_dollar, per_mtok


def render_target(name, config, target_dir, verbose=False):
    rows = lfd_common.read_log(os.path.join(target_dir, "log.jsonl"))
    status = lfd_common.config_value(config, "STATUS")
    window = lfd_common.config_int(config, "DIVERGENCE_WINDOW_CYCLES", minimum=2)
    floor = lfd_common.config_float(config, "PROBE_FLOOR", minimum=0, maximum=1)
    budget = lfd_common.config_int(config, "BUDGET_MAX_HOLDOUT_RUNS", minimum=1)

    lines = [f"● {name}  [{status}]"]

    # Anti-Potemkin gate states — shown for every target, enforced for active.
    au_state, au_detail = lfd_common.audit_state(target_dir)
    cal_state, cal_detail = lfd_common.calibration_state(target_dir)
    lv_state, lv_detail = lfd_common.liveness_state(config)
    gate_glyph = {"ok": "✓", "configured": "✓", "exempt": "✓",
                  "missing": "○", "unset": "🚩", "failed": "🚩",
                  "stale": "🚩", "overlapping": "🚩", "invalid": "🚩"}
    if status not in ("example", "retired"):
        lines.append(
            f"  gates    audit {gate_glyph.get(au_state, '?')} {au_state}"
            f" · calibration {gate_glyph.get(cal_state, '?')} {cal_state}"
            f" · liveness {gate_glyph.get(lv_state, '?')} {lv_state}")
        for st, detail, label in ((au_state, au_detail, "audit"),
                                   (cal_state, cal_detail, "calibration"),
                                   (lv_state, lv_detail, "liveness")):
            if st in ("stale", "failed", "overlapping", "invalid", "unset"):
                lines.append(f"    ⚠ {label}: {detail}")
    blockers = lfd_common.activation_blockers(config, target_dir)
    if blockers:
        lines.append("  🚩 ACTIVATION BLOCKED: " + "; ".join(blockers))

    if not rows:
        lines.append("  no holdout runs logged yet")
        return "\n".join(lines)

    last = rows[-1]
    holdout_series = [r.get("holdout_score") for r in rows]
    lines.append(f"  holdout  {fmt_ci(last.get('holdout_score'), last.get('holdout_ci'))}"
                 f"   history {lfd_common.sparkline(holdout_series)}  ({len(rows)}/{budget} runs)")
    lines.append(f"  dev      {fmt_ci(last.get('dev_score'), last.get('dev_ci'))}")

    if lfd_common.check_divergence(rows, window):
        lines.append("  🚩 DIVERGENCE: dev rising while holdout flat/falling — patch mode trigger")

    if last.get("liveness") == "liveness_failed":
        lines.append("  🚩 LIVENESS FAILED on last run — build/boot/health gate (vaporware?)")

    probe_rows = [r for r in rows if r.get("probe")]
    if probe_rows:
        ops = (probe_rows[-1]["probe"].get("operators") or {})
        breaches = lfd_common.probe_floor_breaches(probe_rows[-1], floor)
        detail = " · ".join(f"{k}: {v:.2f}" if isinstance(v, (int, float)) else f"{k}: ?"
                            for k, v in sorted(ops.items()))
        flag = "  🚩 BELOW FLOOR: " + ", ".join(sorted(breaches)) if breaches else ""
        lines.append(f"  probe    {detail} (floor {floor:.2f}){flag}")

    cov_rows = [r for r in rows if r.get("coverage_variance") is not None]
    if cov_rows:
        cov = cov_rows[-1]["coverage_variance"]
        cov_floor = lfd_common.config_float(
            config, "COVERAGE_VARIANCE_FLOOR", minimum=0, maximum=1)
        flag = "  🚩 LOOKUP-TABLE SUSPICION (same paths across cases)" if cov < cov_floor else ""
        lines.append(f"  coverage variance {cov:.2f} (floor {cov_floor:.2f}){flag}")

    per_dollar, per_mtok = efficiency(rows)
    eff_bits = []
    if per_dollar is not None:
        eff_bits.append(f"Δholdout/$: {per_dollar:+.4f}")
    if per_mtok is not None:
        eff_bits.append(f"Δholdout/Mtok: {per_mtok:+.4f}")
    models = sorted({r.get("model_id") for r in rows if r.get("model_id")})
    declared = lfd_common.config_value(config, "EXECUTOR_MODEL", allow_empty=True)
    if models:
        eff_bits.append("models: " + ", ".join(models))
        if declared and any(m != declared for m in models):
            eff_bits.append(f"⚠ drift from declared {declared}")
    if eff_bits:
        lines.append("  economy  " + "   ".join(eff_bits))

    lines.append(f"  last run {last.get('timestamp', '?')}  sha {str(last.get('sha', ''))[:8]}"
                 f"  harness {last.get('harness_version', '?')}  liveness {last.get('liveness', '?')}")

    if verbose:
        for r in rows[-5:]:
            lines.append(f"    cycle {r.get('cycle')}: {fmt_ci(r.get('holdout_score'), r.get('holdout_ci'))}"
                         f"  {r.get('timestamp')}  {str(r.get('sha', ''))[:8]}")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hub-root", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".."))
    p.add_argument("--target", default=None)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    hub_root = os.path.abspath(args.hub_root)
    targets = list(lfd_common.iter_targets(hub_root))
    if args.target:
        targets = [t for t in targets if t[0] == args.target]
        if not targets:
            sys.exit(f"no such target: {args.target}")
    if not targets:
        print("No targets registered. Onboard one with: bin/lfd new-target <name> <repo-url>")
        return

    print(f"LFD eval hub — {len(targets)} target(s)\n")
    for name, config, target_dir in targets:
        try:
            print(render_target(name, config, target_dir, args.verbose))
        except lfd_common.ConfigError as exc:
            print(f"● {name}  [configuration error]\n  🚩 {exc}")
        print()


if __name__ == "__main__":
    main()
