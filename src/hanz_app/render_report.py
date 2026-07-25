from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

STATUS_CLASS = {
    "READY": "ready",
    "WAIT": "wait",
    "HIGH_RISK": "risk",
    "REJECT": "reject",
}


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _reason_list(item: dict[str, Any]) -> str:
    reasons = list(item.get("selection_reasons") or [])
    if not reasons:
        reasons = list(item.get("rejection_reasons") or [])
    if not reasons:
        reasons = ["No explanatory evidence was recorded."]
    return "".join(f"<li>{_esc(reason)}</li>" for reason in reasons[:8])


def _candidate_card(item: dict[str, Any]) -> str:
    status = str(item.get("entry_status", "WAIT"))
    css_class = STATUS_CLASS.get(status, "wait")
    evidence = item.get("evidence") or {}
    positives = len(evidence.get("positive") or [])
    warnings = len(evidence.get("warning") or [])
    negatives = len(evidence.get("negative") or [])
    unknown = len(evidence.get("unknown") or [])
    return f"""
    <article class="candidate-card">
      <div class="candidate-head">
        <div>
          <div class="symbol">{_esc(item.get('symbol'))}</div>
          <div class="market">{_esc(item.get('market'))} · {_esc(item.get('tier'))}</div>
        </div>
        <span class="status {css_class}">{_esc(status)}</span>
      </div>
      <div class="metrics">
        <span>Positive <strong>{positives}</strong></span>
        <span>Warnings <strong>{warnings}</strong></span>
        <span>Negative <strong>{negatives}</strong></span>
        <span>Unknown <strong>{unknown}</strong></span>
      </div>
      <ul>{_reason_list(item)}</ul>
      <div class="meta">Signal close: {_esc(item.get('signal_close'))} · {_esc(item.get('signal_timestamp'))}</div>
    </article>
    """


def _market_section(market: dict[str, Any]) -> str:
    candidates = market.get("candidates") or []
    cards = "".join(_candidate_card(item) for item in candidates)
    errors = market.get("errors") or []
    error_details = ""
    if errors:
        items = "".join(
            f"<li><strong>{_esc(item.get('symbol'))}</strong>: {_esc(item.get('error'))}</li>"
            for item in errors[:20]
        )
        error_details = f'<details class="errors"><summary>Show data errors ({len(errors)})</summary><ul>{items}</ul></details>'
    if not cards:
        message = "No candidate met the current evidence standard."
        if errors and len(errors) == int(market.get("universe_size") or 0):
            message = "No stock was analyzed because market data acquisition failed for the full pilot universe."
        cards = f'<div class="empty">{_esc(message)}{error_details}</div>'
    return f"""
    <section class="market-section">
      <div class="section-head">
        <div>
          <h2>{_esc(market.get('market'))}</h2>
          <p>{_esc(market.get('universe_size'))} symbols scanned</p>
        </div>
        <div class="counts">
          <span>{_esc(market.get('candidate_count'))} candidates</span>
          <span>{_esc(market.get('rejected_count'))} rejected</span>
          <span>{_esc(market.get('error_count'))} errors</span>
        </div>
      </div>
      <div class="candidate-grid">{cards}</div>
    </section>
    """


def render_report(payload: dict[str, Any]) -> str:
    source = payload.get("source") or {}
    market_sections = "".join(_market_section(item) for item in payload.get("markets") or [])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HANZ Intelligence Alpha Report</title>
<style>
:root {{ color-scheme: dark; --bg:#08101d; --panel:#101b2d; --line:#263650; --text:#f3f6fb; --muted:#9eacc2; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Inter,Segoe UI,Arial,sans-serif; background:var(--bg); color:var(--text); }}
main {{ max-width:1100px; margin:auto; padding:28px 18px 48px; }}
.hero {{ padding:24px; border:1px solid var(--line); border-radius:22px; background:var(--panel); }}
h1 {{ margin:0 0 8px; font-size:clamp(28px,5vw,46px); }}
.motto {{ margin:0 0 18px; font-size:18px; }}
.notice {{ padding:12px 14px; border-radius:12px; background:#2c2430; color:#ffd7e2; }}
.meta-row {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:16px; color:var(--muted); }}
.meta-row span,.counts span,.metrics span {{ border:1px solid var(--line); border-radius:999px; padding:7px 10px; }}
.market-section {{ margin-top:28px; }}
.section-head {{ display:flex; align-items:end; justify-content:space-between; gap:16px; margin-bottom:14px; }}
h2 {{ margin:0; font-size:28px; }}
.section-head p {{ margin:5px 0 0; color:var(--muted); }}
.counts {{ display:flex; gap:8px; flex-wrap:wrap; color:var(--muted); font-size:14px; }}
.candidate-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:14px; }}
.candidate-card,.empty {{ background:var(--panel); border:1px solid var(--line); border-radius:18px; padding:18px; }}
.candidate-head {{ display:flex; justify-content:space-between; gap:12px; align-items:start; }}
.symbol {{ font-size:25px; font-weight:750; }}
.market,.meta {{ color:var(--muted); font-size:13px; }}
.status {{ border-radius:999px; padding:8px 12px; font-weight:800; font-size:13px; }}
.status.ready {{ background:#123d2c; color:#7df1b7; }} .status.wait {{ background:#3c3417; color:#ffe477; }}
.status.risk {{ background:#452918; color:#ffb877; }} .status.reject {{ background:#431e27; color:#ff9bae; }}
.metrics {{ display:flex; flex-wrap:wrap; gap:7px; margin:15px 0; font-size:12px; color:var(--muted); }}
ul {{ margin:0 0 15px; padding-left:18px; line-height:1.55; }}
footer {{ margin-top:30px; color:var(--muted); font-size:13px; }}
@media(max-width:600px) {{ .section-head {{ align-items:start; flex-direction:column; }} }}
</style>
</head>
<body><main>
<section class="hero">
  <h1>HANZ Intelligence</h1>
  <p class="motto">HANZ isn't loyal to stocks. HANZ is loyal to profits.</p>
  <div class="notice">PAPER-TRADE RESEARCH ONLY — not approved for live-money execution.</div>
  <div class="meta-row">
    <span>Generated: {_esc(payload.get('generated_at'))}</span>
    <span>Source: {_esc(source.get('name'))}</span>
    <span>Grade: {_esc(source.get('grade'))}</span>
    <span>Delayed: {_esc(source.get('delayed'))}</span>
  </div>
</section>
{market_sections}
<footer>Evidence-first output. A candidate is not a guaranteed profitable trade.</footer>
</main></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Render HANZ paper scan as a static HTML report")
    parser.add_argument("--input", default="artifacts/paper_scans/latest.json")
    parser.add_argument("--output", default="dashboard/index.html")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Scan report not found: {input_path}")
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_report(payload), encoding="utf-8")
    print(f"Alpha report written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
