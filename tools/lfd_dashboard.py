#!/usr/bin/env python3
"""lfd_dashboard — generate a single self-contained HTML dashboard from
every target's log.jsonl. No CDN, no external requests: inline CSS,
vanilla JS, inline SVG. Open dashboard/index.html via file:// or grab the
CI artifact.

Usage: lfd_dashboard.py [--hub-root PATH] [--out PATH]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfd_common  # noqa: E402

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LFD Eval Hub</title>
<style>
:root { --bg:#0f1115; --card:#181b22; --ink:#e8eaf0; --dim:#8b93a7;
        --dev:#e0a458; --holdout:#5ec8ad; --bad:#e05c5c; --ok:#5ec87a;
        --line:#2a2f3a; }
* { box-sizing:border-box; margin:0; }
body { background:var(--bg); color:var(--ink);
       font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
       padding:24px; }
h1 { font-size:20px; margin-bottom:4px; }
.sub { color:var(--dim); margin-bottom:24px; font-size:12px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px;
        padding:18px 20px; margin-bottom:20px; }
.card h2 { font-size:16px; display:flex; align-items:center; gap:10px;
           flex-wrap:wrap; }
.badge { font-size:11px; padding:2px 8px; border-radius:10px;
         border:1px solid var(--line); color:var(--dim); }
.badge.active { color:var(--ok); border-color:var(--ok); }
.badge.flag { color:#fff; background:var(--bad); border-color:var(--bad); }
.badge.warn { color:var(--dev); border-color:var(--dev); }
.grid { display:grid; grid-template-columns:2fr 1fr; gap:16px; margin-top:12px; }
@media (max-width:800px){ .grid { grid-template-columns:1fr; } }
svg { width:100%; height:auto; display:block; }
table { width:100%; border-collapse:collapse; font-size:12px; margin-top:10px; }
th, td { text-align:left; padding:4px 8px; border-bottom:1px solid var(--line);
         color:var(--dim); white-space:nowrap; }
th { color:var(--ink); font-weight:600; }
.mono { font-family:ui-monospace,Menlo,monospace; }
.kv { font-size:12px; color:var(--dim); }
.kv b { color:var(--ink); font-weight:600; }
.legend { font-size:11px; color:var(--dim); margin-top:4px; }
.legend .dev { color:var(--dev); } .legend .holdout { color:var(--holdout); }
.probe-bar { height:8px; border-radius:4px; background:var(--line);
             position:relative; overflow:hidden; }
.probe-bar i { position:absolute; left:0; top:0; bottom:0; display:block;
               background:var(--ok); }
.probe-bar.breach i { background:var(--bad); }
.probe-row { display:grid; grid-template-columns:110px 1fr 44px; gap:8px;
             align-items:center; font-size:12px; margin:4px 0; }
.empty { color:var(--dim); font-style:italic; padding:8px 0; }
</style>
</head>
<body>
<h1>LFD Eval Hub</h1>
<div class="sub" id="generated"></div>
<div id="app"></div>
<script id="lfd-data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById("lfd-data").textContent);
document.getElementById("generated").textContent =
  "generated at hub commit " + (DATA.hub_commit || "?") + " · " +
  DATA.targets.length + " target(s) · every number traces to a log.jsonl row";

function svgChart(rows) {
  const W = 640, H = 220, P = 34;
  const pts = rows.filter(r => r.holdout_score != null || r.dev_score != null);
  if (!pts.length) return '<div class="empty">no scored runs yet</div>';
  const all = [];
  pts.forEach(r => {
    if (r.holdout_score != null) all.push(r.holdout_score);
    if (r.dev_score != null) all.push(r.dev_score);
    (r.holdout_ci || []).forEach(v => v != null && all.push(v));
    (r.dev_ci || []).forEach(v => v != null && all.push(v));
  });
  let lo = Math.min(...all), hi = Math.max(...all);
  if (hi - lo < 1e-9) { hi = lo + 1; }
  const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
  const x = i => P + (W - 2 * P) * (pts.length === 1 ? 0.5 : i / (pts.length - 1));
  const y = v => H - P - (H - 2 * P) * ((v - lo) / (hi - lo));
  function path(key) {
    let d = "", started = false;
    pts.forEach((r, i) => {
      const v = r[key];
      if (v == null) { started = false; return; }
      d += (started ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1);
      started = true;
    });
    return d;
  }
  function band(key) {
    const seg = pts.map((r, i) => ({ ci: r[key], i })).filter(p =>
      Array.isArray(p.ci) && p.ci[0] != null && p.ci[1] != null);
    if (seg.length < 2) return "";
    let d = "M" + seg.map(p => x(p.i).toFixed(1) + " " + y(p.ci[1]).toFixed(1)).join("L");
    d += "L" + seg.slice().reverse().map(p => x(p.i).toFixed(1) + " " + y(p.ci[0]).toFixed(1)).join("L") + "Z";
    return d;
  }
  const ticks = [lo + pad, (lo + hi) / 2, hi - pad];
  let s = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img">';
  ticks.forEach(t => {
    s += '<line x1="' + P + '" x2="' + (W - P) + '" y1="' + y(t) + '" y2="' + y(t) +
         '" stroke="#2a2f3a" stroke-width="1"/>' +
         '<text x="4" y="' + (y(t) + 4) + '" fill="#8b93a7" font-size="10">' +
         t.toFixed(2) + '</text>';
  });
  s += '<path d="' + band("dev_ci") + '" fill="#e0a458" opacity="0.13"/>';
  s += '<path d="' + band("holdout_ci") + '" fill="#5ec8ad" opacity="0.15"/>';
  s += '<path d="' + path("dev_score") + '" fill="none" stroke="#e0a458" stroke-width="2"/>';
  s += '<path d="' + path("holdout_score") + '" fill="none" stroke="#5ec8ad" stroke-width="2.5"/>';
  pts.forEach((r, i) => {
    if (r.holdout_score != null)
      s += '<circle cx="' + x(i) + '" cy="' + y(r.holdout_score) + '" r="3" fill="#5ec8ad">' +
           '<title>cycle ' + r.cycle + ': ' + r.holdout_score + ' — ' + (r.sha || "").slice(0, 8) +
           ' @ ' + r.timestamp + '</title></circle>';
    if (r.liveness === "liveness_failed")
      s += '<text x="' + x(i) + '" y="' + (H - 8) + '" fill="#e05c5c" font-size="11" ' +
           'text-anchor="middle">✖</text>';
  });
  s += '</svg>';
  return s;
}

function probePanel(t) {
  const rows = t.rows.filter(r => r.probe && r.probe.operators);
  if (!rows.length) return '<div class="empty">no holdout probes run yet</div>';
  const ops = rows[rows.length - 1].probe.operators;
  let h = "";
  Object.keys(ops).sort().forEach(k => {
    const v = ops[k];
    const breach = v != null && v < t.probe_floor;
    h += '<div class="probe-row"><span>' + k + '</span>' +
         '<div class="probe-bar' + (breach ? " breach" : "") + '">' +
         '<i style="width:' + Math.round((v || 0) * 100) + '%"></i></div>' +
         '<span class="mono">' + (v == null ? "?" : v.toFixed(2)) + '</span></div>';
  });
  return h + '<div class="legend">floor ' + t.probe_floor.toFixed(2) +
         ' · per-operator detail is hub-side only</div>';
}

function econ(t) {
  const e = t.efficiency || {};
  const bits = [];
  if (e.per_dollar != null) bits.push("<b>" + e.per_dollar.toFixed(4) + "</b> Δholdout/$");
  if (e.per_mtok != null) bits.push("<b>" + e.per_mtok.toFixed(4) + "</b> Δholdout/Mtok");
  if (e.total_cost != null && e.total_cost > 0) bits.push("<b>$" + e.total_cost.toFixed(2) + "</b> reported spend");
  if (t.models.length) bits.push("models: <b>" + t.models.join(", ") + "</b>");
  return bits.length ? '<div class="kv">' + bits.join(" · ") + "</div>" : "";
}

const app = document.getElementById("app");
DATA.targets.forEach(t => {
  const card = document.createElement("div");
  card.className = "card";
  let badges = '<span class="badge ' + (t.status === "active" ? "active" : "") + '">' + t.status + "</span>";
  if (t.divergence) badges += '<span class="badge flag">DIVERGENCE</span>';
  if (t.liveness_failed) badges += '<span class="badge flag">LIVENESS FAILED</span>';
  if (t.probe_breach) badges += '<span class="badge flag">PROBE BELOW FLOOR</span>';
  if (!t.audited && t.status !== "example") badges += '<span class="badge warn">UNAUDITED</span>';
  const last = t.rows[t.rows.length - 1];
  card.innerHTML =
    "<h2>" + t.name + " " + badges + "</h2>" +
    (last ? '<div class="kv">last: <b>' + (last.holdout_score == null ? "—" : last.holdout_score.toFixed(3)) +
      "</b>" + (last.holdout_ci ? " [" + last.holdout_ci.map(v => v.toFixed(3)).join(", ") + "]" : "") +
      ' · <span class="mono">' + (last.sha || "").slice(0, 8) + "</span> · " + last.timestamp +
      ' · harness <span class="mono">' + (last.harness_version || "?") + "</span> · " +
      t.rows.length + "/" + t.budget + " runs</div>" : "") +
    econ(t) +
    '<div class="grid"><div>' + svgChart(t.rows) +
    '<div class="legend"><span class="holdout">— holdout</span> &nbsp; <span class="dev">— dev (agent-reported)</span>' +
    ' &nbsp; shaded = 95% CI &nbsp; ✖ = liveness failure</div></div>' +
    "<div><h3 style='font-size:13px;margin-bottom:6px'>holdout probes</h3>" + probePanel(t) + "</div></div>";
  app.appendChild(card);
});
if (!DATA.targets.length)
  app.innerHTML = '<div class="card empty">No targets registered. Onboard one with bin/lfd new-target.</div>';
</script>
</body>
</html>
"""


def build_data(hub_root):
    import subprocess
    try:
        hub_commit = subprocess.run(
            ["git", "-C", hub_root, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        hub_commit = ""
    targets = []
    for name, config, target_dir in lfd_common.iter_targets(hub_root):
        rows = lfd_common.read_log(os.path.join(target_dir, "log.jsonl"))
        window = lfd_common.config_int(config, "DIVERGENCE_WINDOW_CYCLES", minimum=2)
        floor = lfd_common.config_float(config, "PROBE_FLOOR", minimum=0, maximum=1)
        probe_rows = [r for r in rows if r.get("probe")]
        scored = [r for r in rows if r.get("holdout_score") is not None]
        cost = sum(r.get("reported_cost_usd") or 0 for r in scored)
        tokens = sum((r.get("reported_tokens_in") or 0) +
                     (r.get("reported_tokens_out") or 0) for r in scored)
        delta = (scored[-1]["holdout_score"] - scored[0]["holdout_score"]
                 if len(scored) >= 2 else None)
        targets.append({
            "name": name,
            "status": lfd_common.config_value(config, "STATUS"),
            "budget": lfd_common.config_int(
                config, "BUDGET_MAX_HOLDOUT_RUNS", minimum=1),
            "probe_floor": floor,
            "audited": lfd_common.audit_state(target_dir)[0] == "ok",
            "divergence": lfd_common.check_divergence(rows, window),
            "liveness_failed": bool(rows) and rows[-1].get("liveness") == "liveness_failed",
            "probe_breach": bool(probe_rows) and bool(
                lfd_common.probe_floor_breaches(probe_rows[-1], floor)),
            "models": sorted({r.get("model_id") for r in rows if r.get("model_id")}),
            "efficiency": {
                "per_dollar": (delta / cost) if (delta is not None and cost > 0) else None,
                "per_mtok": (delta / (tokens / 1e6)) if (delta is not None and tokens > 0) else None,
                "total_cost": cost or None,
            },
            "rows": rows,
        })
    return {"hub_commit": hub_commit, "targets": targets}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hub-root", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".."))
    p.add_argument("--out", default=None)
    args = p.parse_args()
    hub_root = os.path.abspath(args.hub_root)
    out = args.out or os.path.join(hub_root, "dashboard", "index.html")

    data = build_data(hub_root)
    # </script> inside a JSON string would end the data block early; escape it.
    blob = json.dumps(data).replace("</", "<\\/")
    html = PAGE.replace("__DATA__", blob)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write(html)
    print(f"dashboard written: {out} ({len(data['targets'])} target(s))")


if __name__ == "__main__":
    main()
