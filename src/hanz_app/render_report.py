from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

from hanz_app.decision_intelligence import (
    evidence_quality,
    explain_no_candidate,
    market_health,
    quality_grade,
    trade_plan,
)

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
    for bucket, css in (
        ("positive", "good"),
        ("neutral", "neutral"),
        ("warning", "caution"),
        ("negative", "bad"),
        ("unknown", "unknown"),
    ):
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
        cells.append(
            f'<div class="signal"><span class="signal-icon"></span><small>{_esc(label)}</small><strong class="{css}">{_esc(value)}</strong></div>'
        )
    return "".join(cells)


def _plan_html(item: dict[str, Any]) -> str:
    plan = trade_plan(item)
    if plan.entry_low is None:
        return f'<div class="plan-note">{_esc(plan.note)}</div>'
    validity = "ENTRY PLAN" if plan.valid else "WATCH PLAN"
    return f"""<div class="plan">
      <div class="plan-primary"><small>{validity}</small><strong>{_fmt(plan.entry_low)} – {_fmt(plan.entry_high)}</strong><span>Price zone to monitor</span></div>
      <div><small>STOP</small><strong>{_fmt(plan.stop)}</strong><span>Research invalidation</span></div>
      <div><small>TARGET 1</small><strong>{_fmt(plan.target_1)}</strong><span>R/R {_fmt(plan.reward_risk_1, 1)}</span></div>
      <div><small>TARGET 2</small><strong>{_fmt(plan.target_2)}</strong><span>R/R {_fmt(plan.reward_risk_2, 1)}</span></div>
    </div><div class="plan-note">{_esc(plan.note)}</div>"""


def _action_copy(item: dict[str, Any]) -> tuple[str, str, str]:
    status = str(item.get("entry_status", "WAIT"))
    symbol = _esc(item.get("symbol"))
    if status == "READY":
        return "READY", "ready", f"Review the {symbol} entry plan. Respect the stop and exposure limit."
    if status == "HIGH_RISK":
        return "AVOID", "risk", f"Do not enter {symbol}. Risk is above the current evidence standard."
    if status == "REJECT":
        return "AVOID", "reject", f"{symbol} does not meet the required evidence standard."
    return "WAIT", "wait", f"Monitor {symbol}. No entry until the status changes to READY."


def _candidate_card(item: dict[str, Any], *, watchlist: bool = False) -> str:
    status = str(item.get("entry_status", "WAIT"))
    css_class = STATUS_CLASS.get(status, "wait")
    strength, strength_css = _strength(item)
    technical = item.get("technical") or {}
    label = "WATCHLIST" if watchlist else status
    quality = evidence_quality(item)
    grade = quality_grade(quality, status)
    action, action_css, instruction = _action_copy(item)
    return f"""
    <article class="candidate-card {'watch-card' if watchlist else ''}">
      <div class="candidate-head">
        <div>
          <div class="symbol-row"><div class="symbol">{_esc(item.get('symbol'))}</div><span class="mini-action {action_css}">{action}</span></div>
          <div class="market">{_esc(item.get('market'))} · {_esc(item.get('tier'))}</div>
        </div>
        <div class="badges"><span class="quality">QUALITY {quality}/100</span><span class="grade">{grade}</span><span class="strength {strength_css}">{strength}</span><span class="status {css_class}">{_esc(label)}</span></div>
      </div>
      <div class="quality-meter"><span style="width:{quality}%"></span></div>
      <div class="instruction"><strong>WHAT TO DO</strong><p>{instruction}</p></div>
      <div class="signal-grid">{_technical_row(item)}</div>
      {_plan_html(item)}
      <details><summary>Why HANZ classified it this way</summary><ul>{_reason_list(item)}</ul></details>
      <div class="technical-values">
        <span>Close {_fmt(item.get('signal_close'))}</span><span>RSI {_fmt(technical.get('rsi14'))}</span>
        <span>RVOL {_fmt(technical.get('relative_volume20'))}</span><span>Resistance {_fmt(technical.get('resistance20'))}</span><span>ATR {_fmt(technical.get('atr14'))}</span>
      </div>
      <div class="meta">Signal time: {_esc(item.get('signal_timestamp'))}</div>
    </article>"""


def _decision_panel(market: dict[str, Any]) -> str:
    candidates = market.get("candidates") or []
    health = market_health(market)
    if candidates:
        top = candidates[0]
        action, css, instruction = _action_copy(top)
        symbol = _esc(top.get("symbol"))
        quality = evidence_quality(top)
        title = f"{action} · {symbol}"
        subtitle = instruction
    else:
        action, css = "STAY CASH", "risk"
        quality = 0
        title = action
        subtitle = "No READY setup passed. Preserving capital is the correct action."
    return f'''<section class="decision-panel">
      <div class="decision-main">
        <small>TODAY'S DECISION</small>
        <strong class="{css}">{title}</strong>
        <p>{subtitle}</p>
      </div>
      <div class="decision-stat"><small>MARKET POSTURE</small><strong>{_esc(health['label'])}</strong></div>
      <div class="decision-stat"><small>HEALTH</small><strong>{_esc(health['score'])}<span>/100</span></strong></div>
      <div class="decision-stat"><small>MAX EXPOSURE</small><strong>{_esc(health['paper_exposure_percent'])}<span>%</span></strong></div>
      <div class="decision-stat"><small>TOP QUALITY</small><strong>{quality}<span>/100</span></strong></div>
    </section>'''


def _market_section(market: dict[str, Any]) -> str:
    candidates = market.get("candidates") or []
    reviewed = market.get("reviewed") or []
    errors = market.get("errors") or []
    cards = "".join(_candidate_card(item) for item in candidates)
    watch_cards = "".join(_candidate_card(item, watchlist=True) for item in reviewed[:5])
    if not cards:
        cards = '<div class="empty"><strong>No READY candidate today.</strong><p>This is a valid outcome. HANZ does not force a trade.</p></div>'
    if not watch_cards:
        watch_cards = '<div class="empty"><strong>No developing setup.</strong><p>Keep the capital uncommitted.</p></div>'
    error_details = ""
    if errors:
        items = "".join(f"<li><strong>{_esc(item.get('symbol'))}</strong>: {_esc(item.get('error'))}</li>" for item in errors[:30])
        error_details = f'<details class="errors"><summary>Data errors ({len(errors)})</summary><ul>{items}</ul></details>'
    coverage = market.get("coverage_percent", 0)
    health = market_health(market)
    reasons = explain_no_candidate(market)
    no_candidate = ""
    if reasons:
        no_candidate = '<div class="market-explanation"><strong>Why no READY setup passed</strong><ul>' + "".join(f"<li>{_esc(reason)}</li>" for reason in reasons) + "</ul></div>"
    return f"""
    <section class="market-section" id="market">
      <div class="section-head">
        <div><span class="eyebrow">MARKET OVERVIEW</span><h2>{_esc(market.get('market'))}</h2><p>{_esc(market.get('universe_size'))} symbols · {_esc(coverage)}% analyzed</p></div>
        <div class="counts"><span><b>{_esc(market.get('candidate_count'))}</b> candidates</span><span><b>{_esc(market.get('reviewed_count'))}</b> reviewed</span><span><b>{_esc(market.get('rejected_count'))}</b> rejected</span><span><b>{_esc(market.get('error_count'))}</b> errors</span></div>
      </div>
      {_decision_panel(market)}
      <div class="health-line"><span style="width:{_esc(health['score'])}%"></span></div>
      <p class="health-copy">{_esc(health['explanation'])}</p>
      {no_candidate}
      <div class="subsection-head"><div><span class="eyebrow">PRIMARY SETUPS</span><h3>Actionable candidates</h3></div><a href="#watchlist">View watchlist ↓</a></div>
      <div class="candidate-grid">{cards}</div>
      <div class="subsection-head" id="watchlist"><div><span class="eyebrow">EARLY OPPORTUNITIES</span><h3>Top developing watchlist</h3></div><a href="#top">Back to top ↑</a></div>
      <div class="candidate-grid watch-grid">{watch_cards}</div>
      {error_details}
    </section>"""


def render_report(payload: dict[str, Any]) -> str:
    source = payload.get("source") or {}
    sections = "".join(_market_section(item) for item in payload.get("markets") or [])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>HANZ Intelligence</title><style>
:root{{--bg:#050b14;--panel:#0d1727;--panel2:#111f34;--line:#263650;--text:#f5f7fb;--muted:#98a7bd;--blue:#54a8ff;--green:#66e3a4;--yellow:#ffd76a;--red:#ff8299;--violet:#c5a7ff}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:radial-gradient(circle at top right,#10213c 0,#050b14 38%);color:var(--text)}}
body:before{{content:"";position:fixed;inset:0;pointer-events:none;background:linear-gradient(rgba(255,255,255,.018) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.018) 1px,transparent 1px);background-size:32px 32px;mask-image:linear-gradient(to bottom,black,transparent 70%)}}
main{{max-width:1280px;margin:auto;padding:26px 20px 56px;position:relative}}a{{color:#9bcaff;text-decoration:none}}.eyebrow{{color:#7fa7d6;font-size:11px;font-weight:800;letter-spacing:.14em}}
.hero{{padding:30px;border:1px solid #2a3f5f;border-radius:26px;background:linear-gradient(135deg,rgba(27,53,91,.96),rgba(13,23,39,.96));box-shadow:0 24px 60px rgba(0,0,0,.32);position:relative;overflow:hidden}}
.hero:after{{content:"HANZ";position:absolute;right:-14px;top:-42px;font-size:160px;font-weight:900;color:rgba(255,255,255,.025);letter-spacing:-.08em}}h1{{margin:0 0 8px;font-size:clamp(34px,5vw,58px);letter-spacing:-.04em}}.motto{{margin:0 0 20px;font-size:18px;color:#d8e4f4}}
.notice{{display:inline-flex;padding:10px 14px;border:1px solid #5b3548;border-radius:999px;background:#2c1c28;color:#ffd4df;font-size:13px;font-weight:700}}.meta-row{{display:flex;gap:8px;flex-wrap:wrap;margin-top:20px;color:var(--muted)}}.meta-row span{{border:1px solid #324765;background:rgba(8,15,26,.35);border-radius:999px;padding:7px 10px;font-size:12px}}
.market-section{{margin-top:34px}}.section-head,.subsection-head{{display:flex;align-items:end;justify-content:space-between;gap:16px;margin-bottom:16px}}h2{{margin:4px 0 0;font-size:34px}}h3{{margin:4px 0 0;font-size:24px}}.section-head p{{margin:5px 0 0;color:var(--muted)}}
.counts{{display:flex;gap:8px;flex-wrap:wrap}}.counts span{{border:1px solid var(--line);background:rgba(13,23,39,.72);border-radius:999px;padding:8px 11px;color:var(--muted);font-size:12px}}.counts b{{color:var(--text);font-size:15px}}
.decision-panel{{display:grid;grid-template-columns:2fr repeat(4,1fr);gap:10px;background:linear-gradient(135deg,#132744,#0b1524);border:1px solid #35527a;border-radius:22px;padding:16px;margin:18px 0 10px;box-shadow:0 18px 44px rgba(0,0,0,.24)}}
.decision-main,.decision-stat{{border:1px solid rgba(130,170,220,.16);border-radius:16px;padding:15px;display:flex;flex-direction:column;justify-content:center;min-width:0}}.decision-main small,.decision-stat small{{color:var(--muted);font-size:10px;font-weight:800;letter-spacing:.12em}}.decision-main strong{{font-size:30px;margin-top:4px;line-height:1.05}}.decision-main p{{margin:8px 0 0;color:#d8e5f5;font-size:13px;line-height:1.45}}.decision-stat strong{{font-size:24px;margin-top:7px}}.decision-stat strong span{{font-size:13px;color:var(--muted)}}
.ready,.good{{color:var(--green)}}.wait,.caution{{color:var(--yellow)}}.risk,.reject,.bad{{color:var(--red)}}.neutral{{color:#cbd6e7}}.unknown{{color:var(--muted)}}
.health-line,.quality-meter{{height:6px;background:#15243a;border-radius:999px;overflow:hidden}}.health-line span,.quality-meter span{{display:block;height:100%;background:linear-gradient(90deg,#3f88ff,#66e3a4);border-radius:999px}}.health-copy{{color:var(--muted);margin:10px 2px 24px;font-size:13px}}
.candidate-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:16px}}.candidate-card,.empty,.errors,.market-explanation{{background:linear-gradient(180deg,#111f34,#0d1727);border:1px solid var(--line);border-radius:22px;padding:19px;box-shadow:0 14px 34px rgba(0,0,0,.18)}}.watch-card{{border-style:dashed}}.candidate-head{{display:flex;justify-content:space-between;gap:14px;align-items:start}}.symbol-row{{display:flex;align-items:center;gap:10px}}.symbol{{font-size:31px;font-weight:900;letter-spacing:-.03em}}.market,.meta{{color:var(--muted);font-size:12px}}.mini-action{{font-size:10px;font-weight:900;padding:5px 8px;border-radius:999px;background:#17263c}}
.badges{{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}}.status,.strength,.quality,.grade{{border-radius:999px;padding:6px 9px;font-weight:800;font-size:11px}}.status.ready,.strength.strong{{background:#113729;color:var(--green)}}.status.wait,.strength.developing{{background:#3c3316;color:var(--yellow)}}.status.risk,.status.reject,.strength.weak{{background:#401d27;color:var(--red)}}.quality{{background:#17314e;color:#b8dcff}}.grade{{background:#30264b;color:#d8c7ff}}.quality-meter{{margin:13px 0 14px}}
.instruction{{border-left:3px solid #4d9fff;background:#0b1628;border-radius:10px;padding:10px 12px;margin-bottom:14px}}.instruction strong{{font-size:10px;letter-spacing:.12em;color:#8ebfff}}.instruction p{{margin:4px 0 0;font-size:13px;color:#dce7f5;line-height:1.45}}
.signal-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0}}.signal{{padding:11px;border:1px solid var(--line);border-radius:13px;display:flex;flex-direction:column;gap:5px;background:#0b1626}}.signal small{{color:var(--muted);font-size:11px}}.signal strong{{font-size:13px}}
.plan{{display:grid;grid-template-columns:1.3fr repeat(3,1fr);gap:8px;margin:14px 0}}.plan>div{{border:1px solid var(--line);border-radius:13px;padding:11px;display:flex;flex-direction:column;gap:4px;background:#0b1626}}.plan-primary{{background:linear-gradient(145deg,#122b49,#0b1626)!important}}.plan small,.plan span,.plan-note{{color:var(--muted);font-size:11px}}.plan strong{{font-size:16px}}.plan-note{{line-height:1.45}}
details{{margin:14px 0}}summary{{cursor:pointer;color:#bad6ff;font-weight:700}}ul{{line-height:1.55}}.technical-values{{display:flex;gap:7px;flex-wrap:wrap;margin-top:14px}}.technical-values span{{border:1px solid var(--line);border-radius:999px;padding:6px 8px;color:var(--muted);font-size:11px}}.meta{{margin-top:8px}}.market-explanation{{background:#17162a;border-color:#3d3760;margin:16px 0}}.empty p{{color:var(--muted);margin-bottom:0}}footer{{margin-top:34px;color:var(--muted);font-size:12px;line-height:1.5}}
@media(max-width:980px){{.decision-panel{{grid-template-columns:2fr repeat(2,1fr)}}.decision-main{{grid-row:span 2}}.plan{{grid-template-columns:repeat(2,1fr)}}}}
@media(max-width:720px){{body{{background:#060d18;padding-bottom:24px}}main{{padding:12px 10px 34px;max-width:none}}.hero{{padding:20px 16px;border-radius:20px}}.hero:after{{font-size:100px}}h1{{font-size:38px}}.motto{{font-size:14px;line-height:1.45}}.notice{{font-size:11px;border-radius:12px;line-height:1.35}}.meta-row{{display:grid;grid-template-columns:1fr;gap:6px}}.meta-row span{{font-size:10px;overflow-wrap:anywhere}}
.section-head,.subsection-head{{align-items:start;flex-direction:column;gap:10px}}h2{{font-size:28px}}h3{{font-size:21px}}.counts{{display:grid;grid-template-columns:repeat(2,1fr);width:100%}}.counts span{{text-align:center}}
.decision-panel{{position:sticky;top:8px;z-index:8;grid-template-columns:repeat(2,1fr);padding:12px;border-radius:18px;box-shadow:0 16px 30px rgba(0,0,0,.4)}}.decision-main{{grid-column:1/-1;grid-row:auto;padding:13px}}.decision-main strong{{font-size:25px}}.decision-main p{{font-size:12px}}.decision-stat{{padding:10px}}.decision-stat strong{{font-size:18px}}
.candidate-grid{{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;gap:12px;padding:2px 2px 12px;margin:0 -2px}}.candidate-card{{min-width:calc(100vw - 30px);scroll-snap-align:center;padding:16px;border-radius:18px}}.watch-card{{min-width:88vw}}.candidate-head{{flex-direction:column;gap:10px}}.badges{{justify-content:flex-start}}.symbol{{font-size:34px}}.quality-meter{{margin-top:10px}}
.signal-grid{{grid-template-columns:repeat(2,1fr);gap:7px}}.signal{{min-height:68px;padding:10px 9px}}.plan{{grid-template-columns:repeat(2,1fr);gap:7px}}.plan>div{{min-height:92px;padding:10px 9px}}.technical-values{{gap:6px}}.technical-values span{{font-size:10px}}.subsection-head a{{font-size:12px}}}}
@media(max-width:390px){{.decision-panel{{grid-template-columns:1fr 1fr}}.candidate-card{{min-width:calc(100vw - 22px)}}.watch-card{{min-width:92vw}}}}
</style></head><body><main id="top"><section class="hero"><span class="eyebrow">INSTITUTIONAL RESEARCH DASHBOARD</span><h1>HANZ Intelligence</h1><p class="motto">HANZ isn't loyal to stocks. HANZ is loyal to profits.</p>
<div class="notice">PAPER-TRADE RESEARCH ONLY — not approved for live-money execution.</div><div class="meta-row"><span>Generated: {_esc(payload.get('generated_at'))}</span><span>Source: {_esc(source.get('name'))}</span><span>Grade: {_esc(source.get('grade'))}</span><span>Delayed: {_esc(source.get('delayed'))}</span></div></section>{sections}
<footer>Evidence-first output. Quality scores summarize evidence completeness and alignment; they are not win probabilities or guarantees.</footer></main></body></html>"""


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
