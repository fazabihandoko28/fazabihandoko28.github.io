from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

STATUS_CLASS = {"READY": "ready", "WAIT": "wait", "HIGH_RISK": "risk", "REJECT": "reject"}
SIGNAL_LABEL = {
    "POSITIVE": "SUPPORTIVE",
    "NEUTRAL": "NEUTRAL",
    "WARNING": "CAUTION",
    "NEGATIVE": "UNFAVORABLE",
    "UNKNOWN": "UNKNOWN",
}


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return _esc(value)


def _reason_list(item: dict[str, Any]) -> str:
    reasons = list(item.get("selection_reasons") or [])
    if not reasons:
        reasons = list(item.get("rejection_reasons") or [])
    if not reasons:
        reasons = ["No explanatory evidence was recorded."]
    return "".join(f"<li>{_esc(reason)}</li>" for reason in reasons[:8])


def _strength(item: dict[str, Any]) -> tuple[str, str]:
    evidence = item.get("evidence") or {}
    positive = len(evidence.get("positive") or [])
    warning = len(evidence.get("warning") or [])
    negative = len(evidence.get("negative") or [])
    unknown = len(evidence.get("unknown") or [])
    status = str(item.get("entry_status", "WAIT"))
    if status == "READY" and positive >= 3 and warning == 0 and negative == 0 and unknown == 0:
        return "STRONG", "strong"
    if status in {"READY", "WAIT"} and negative == 0 and unknown <= 1:
        return "DEVELOPING", "developing"
    return "WEAK", "weak"


def _evidence_signal(item: dict[str, Any], name: str) -> tuple[str, str]:
    evidence = item.get("evidence") or {}
    for bucket, css in (("positive", "good"), ("neutral", "neutral"), ("warning", "caution"), ("negative", "bad"), ("unknown", "unknown")):
        if name in (evidence.get(bucket) or []):
            return SIGNAL_LABEL[bucket.upper()], css
    return "UNKNOWN", "unknown"


def _technical_row(item: dict[str, Any]) -> str:
    fields = [
        ("Trend", "price_structure"),
        ("Volume", "volume_confirmation"),
        ("Resistance", "resistance"),
        ("Risk / Reward", "risk_reward"),
        ("Liquidity", "liquidity"),
        ("Extension", "extension_risk"),
    ]
    cells = []
    for label, key in fields:
        value, css = _evidence_signal(item, key)
        cells.append(f'<div class="signal"><small>{_esc(label)}</small><strong class="{css}">{_esc(value)}</strong></div>')
    return "".join(cells)


def _candidate_card(item: dict[str, Any], *, watchlist: bool = False) -> str:
    status = str(item.get("entry_status", "WAIT"))
    css_class = STATUS_CLASS.get(status, "wait")
    strength, strength_css = _strength(item)
    technical = item.get("technical") or {}
    label = "WATCHLIST" if watchlist else status
    return f"""
    <article class="candidate-card {'watch-card' if watchlist else ''}">
      <div class="candidate-head">
        <div><div class="symbol">{_esc(item.get('symbol'))}</div><div class="market">{_esc(item.get('market'))} · {_esc(item.get('tier'))}</div></div>
        <div class="badges"><span class="strength {strength_css}">{strength}</span><span class="status {css_class}">{_esc(label)}</span></div>
      </div>
      <div class="signal-grid">{_technical_row(item)}</div>
      <details><summary>Why HANZ classified it this way</summary><ul>{_reason_list(item)}</ul></details>
      <div class="technical-values">
        <span>Close {_fmt(item.get('signal_close'))}</span><span>RSI {_fmt(technical.get('rsi14'))}</span>
        <span>RVOL {_fmt(technical.get('relative_volume20'))}</span><span>Resistance {_fmt(technical.get('resistance20'))}</span>
      </div>
      <div class="meta">{_esc(item.get('signal_timestamp'))}</div>
    </article>"""


def _market_section(market: dict[str, Any]) -> str:
    candidates = market.get("candidates") or []
    reviewed = market.get("reviewed") or []
    errors = market.get("errors") or []
    cards = "".join(_candidate_card(item) for item in candidates)
    watch_cards = "".join(_candidate_card(item, watchlist=True) for item in reviewed[:5])
    if not cards:
        cards = '<div class="empty">No READY candidate met the current evidence standard. This is a valid outcome—not a forced signal.</div>'
    if not watch_cards:
        watch_cards = '<div class="empty">No developing setup is available.</div>'
    error_details = ""
    if errors:
        items = "".join(f"<li><strong>{_esc(item.get('symbol'))}</strong>: {_esc(item.get('error'))}</li>" for item in errors[:30])
        error_details = f'<details class="errors"><summary>Data errors ({len(errors)})</summary><ul>{items}</ul></details>'
    coverage = market.get("coverage_percent", 0)
    return f"""
    <section class="market-section">
      <div class="section-head"><div><h2>{_esc(market.get('market'))}</h2><p>{_esc(market.get('universe_size'))} symbols · {_esc(coverage)}% analyzed</p></div>
      <div class="counts"><span>{_esc(market.get('candidate_count'))} candidates</span><span>{_esc(market.get('reviewed_count'))} reviewed</span><span>{_esc(market.get('rejected_count'))} rejected</span><span>{_esc(market.get('error_count'))} errors</span></div></div>
      <h3>Actionable candidates</h3><div class="candidate-grid">{cards}</div>
      <h3>Top developing watchlist</h3><div class="candidate-grid">{watch_cards}</div>
      {error_details}
    </section>"""


def render_report(payload: dict[str, Any]) -> str:
    source = payload.get("source") or {}
    sections = "".join(_market_section(item) for item in payload.get("markets") or [])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HANZ Intelligence Alpha Report</title><style>
:root {{color-scheme:dark;--bg:#08101d;--panel:#101b2d;--line:#263650;--text:#f3f6fb;--muted:#9eacc2}}
*{{box-sizing:border-box}} body{{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--text)}} main{{max-width:1180px;margin:auto;padding:28px 18px 48px}}
.hero{{padding:24px;border:1px solid var(--line);border-radius:22px;background:linear-gradient(135deg,#162945,#101b2d)}} h1{{margin:0 0 8px;font-size:clamp(28px,5vw,46px)}} .motto{{margin:0 0 18px;font-size:18px}}
.notice{{padding:12px 14px;border-radius:12px;background:#2c2430;color:#ffd7e2}} .meta-row,.counts,.technical-values{{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px;color:var(--muted)}}
.meta-row span,.counts span,.technical-values span{{border:1px solid var(--line);border-radius:999px;padding:7px 10px}} .market-section{{margin-top:30px}} .section-head{{display:flex;align-items:end;justify-content:space-between;gap:16px;margin-bottom:14px}}
h2{{margin:0;font-size:30px}} h3{{margin:24px 0 12px;color:#dbe8ff}} .section-head p{{margin:5px 0 0;color:var(--muted)}} .candidate-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}}
.candidate-card,.empty,.errors{{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:18px}} .watch-card{{border-style:dashed}} .candidate-head{{display:flex;justify-content:space-between;gap:12px;align-items:start}}
.symbol{{font-size:27px;font-weight:800}} .market,.meta{{color:var(--muted);font-size:13px}} .badges{{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}} .status,.strength{{border-radius:999px;padding:7px 10px;font-weight:800;font-size:12px}}
.status.ready,.strength.strong{{background:#123d2c;color:#7df1b7}} .status.wait,.strength.developing{{background:#3c3417;color:#ffe477}} .status.risk,.status.reject,.strength.weak{{background:#431e27;color:#ff9bae}}
.signal-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:16px 0}} .signal{{padding:10px;border:1px solid var(--line);border-radius:12px;display:flex;flex-direction:column;gap:5px}} .signal small{{color:var(--muted)}}
.good{{color:#7df1b7}} .neutral{{color:#c8d4e6}} .caution{{color:#ffe477}} .bad{{color:#ff9bae}} .unknown{{color:#9eacc2}} details{{margin:12px 0}} summary{{cursor:pointer;color:#bcd5ff}} ul{{line-height:1.55}}
.technical-values{{font-size:12px}} footer{{margin-top:30px;color:var(--muted);font-size:13px}} @media(max-width:650px){{.section-head{{align-items:start;flex-direction:column}}.signal-grid{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main><section class="hero"><h1>HANZ Intelligence</h1><p class="motto">HANZ isn't loyal to stocks. HANZ is loyal to profits.</p>
<div class="notice">PAPER-TRADE RESEARCH ONLY — not approved for live-money execution.</div><div class="meta-row"><span>Generated: {_esc(payload.get('generated_at'))}</span><span>Source: {_esc(source.get('name'))}</span><span>Grade: {_esc(source.get('grade'))}</span><span>Delayed: {_esc(source.get('delayed'))}</span></div></section>{sections}
<footer>Evidence-first output. Colors describe evidence quality, not a guarantee of profit.</footer></main></body></html>"""


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
