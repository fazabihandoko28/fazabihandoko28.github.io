from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from hanz_data import YahooFinanceProvider, load_yahoo_universe
from hanz_validation.walk_forward import WalkForwardValidator, DecisionOutcome

SUPABASE_URL=os.environ.get("SUPABASE_URL","").rstrip("/")
SUPABASE_KEY=os.environ.get("SUPABASE_SECRET_KEY","")
OUT=Path("docs/dashboard/swing/backtest-5y.json")
UNIVERSE=Path("config/universe/bei_candidate_pool.csv")


def _num(v, default=None):
    try:
        if v is None or v=="":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _get_monitor_rows():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SECRET_KEY are required")
    q=urlencode({
        "select":"*",
        "order":"updated_at.desc",
        "limit":"500",
    })
    req=Request(
        f"{SUPABASE_URL}/rest/v1/hanz_swing_signal_monitor?{q}",
        headers={
            "apikey":SUPABASE_KEY,
            "Authorization":f"Bearer {SUPABASE_KEY}",
            "Accept":"application/json",
        },
    )
    with urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _legacy_wait_eligible(row):
    r=row.get("risk_validation") or {}
    action=str(r.get("hanz_action") or row.get("hanz_action") or "").upper()
    if action!="AVOID":
        return False
    raw=_num((r.get("opportunity_score_breakdown") or {}).get("raw_score_before_action_cap"))
    rr2=_num(r.get("rr_target_2"))
    avg=_num(r.get("avg_value20"))
    zero=int(_num(r.get("zero_volume_days20"),0) or 0)
    vol=str(r.get("volatility_status") or "").upper()
    regime=str(r.get("market_regime") or "").upper()
    blocked=bool((r.get("momentum_guard") or {}).get("blocked"))
    lo=_num(row.get("entry_low")); hi=_num(row.get("entry_high")); t1=_num(row.get("target_1"))
    mid=(lo+hi)/2 if lo and hi else None
    upside=((t1-mid)/mid*100) if t1 is not None and mid else None
    return (
        raw is not None and raw>=30
        and rr2 is not None and rr2>=2
        and not blocked and vol!="EXTREME" and zero<5
        and (avg is None or avg>=100_000_000)
        and regime!="RED"
        and (upside is None or upside>=0.5)
    )


def _rank(row):
    r=row.get("risk_validation") or {}
    if _legacy_wait_eligible(row):
        raw=_num((r.get("opportunity_score_breakdown") or {}).get("raw_score_before_action_cap"),35)
        return max(35,min(54,raw))
    return max(0,min(100,_num(r.get("canonical_rank_score"),0) or 0))


def _eligible(row):
    r=row.get("risk_validation") or {}
    action="WAIT" if _legacy_wait_eligible(row) else str(r.get("hanz_action") or row.get("hanz_action") or "").upper()
    if action in {"AVOID","DO_NOT_CHASE"}:
        return False
    if bool(r.get("top5_excluded")) and action!="TP_RISK" and not _legacy_wait_eligible(row):
        return False
    if bool((r.get("momentum_guard") or {}).get("blocked")):
        return False
    if str(r.get("volatility_status") or "").upper()=="EXTREME":
        return False
    if int(_num(r.get("zero_volume_days20"),0) or 0)>=5:
        return False
    avg=_num(r.get("avg_value20"))
    if avg is not None and avg<100_000_000:
        return False
    lo=_num(row.get("entry_low")); hi=_num(row.get("entry_high")); t1=_num(row.get("target_1"))
    if lo and hi and t1:
        mid=(lo+hi)/2
        if ((t1-mid)/mid*100)<0.5:
            return False
    return _rank(row)>0


def _top5_symbols():
    rows=_get_monitor_rows()
    rows=[r for r in rows if _eligible(r)]
    rows.sort(key=lambda r:(-_rank(r),str(r.get("ticker") or "")))
    return [str(r.get("ticker") or "").upper() for r in rows[:5]]


def _summary(symbol, series, report):
    ready=[e for e in report.events if e.status=="READY"]
    target=sum(e.outcome is DecisionOutcome.TARGET_FIRST for e in ready)
    stop=sum(e.outcome is DecisionOutcome.STOP_FIRST for e in ready)
    ambiguous=sum(e.outcome is DecisionOutcome.TARGET_AND_STOP_SAME_BAR for e in ready)
    neither=sum(e.outcome is DecisionOutcome.NEITHER for e in ready)
    resolved=target+stop+ambiguous
    win_rate=(100.0*target/resolved) if resolved else None
    avg5=(100.0*report.average_ready_forward_return) if report.average_ready_forward_return is not None else None
    worst_mae=(100.0*min((e.max_adverse_excursion for e in ready), default=0.0)) if ready else None
    best_mfe=(100.0*max((e.max_favorable_excursion for e in ready), default=0.0)) if ready else None
    bars=series.bars
    span_start=bars[0].timestamp.date().isoformat() if bars else None
    span_end=bars[-1].timestamp.date().isoformat() if bars else None
    years=((bars[-1].timestamp-bars[0].timestamp).days/365.2425) if len(bars)>1 else 0.0
    return {
        "symbol":symbol,
        "status":"OK" if years>=4.8 else "LIMITED_HISTORY",
        "span_start":span_start,
        "span_end":span_end,
        "span_years":round(years,2),
        "bars":len(bars),
        "evaluated_events":report.evaluated_events,
        "ready_signals":report.ready_events,
        "target_first":target,
        "stop_first":stop,
        "ambiguous_same_bar":ambiguous,
        "neither":neither,
        "resolved_signals":resolved,
        "win_rate_pct":None if win_rate is None else round(win_rate,1),
        "target_hit_pct":None if not ready else round(100.0*target/len(ready),1),
        "stop_hit_pct":None if not ready else round(100.0*(stop+ambiguous)/len(ready),1),
        "avg_5d_return_pct":None if avg5 is None else round(avg5,2),
        "worst_mae_pct":None if worst_mae is None else round(worst_mae,2),
        "best_mfe_pct":None if best_mfe is None else round(best_mfe,2),
    }


def main():
    symbols=_top5_symbols()
    mappings=load_yahoo_universe(UNIVERSE)
    available={m.symbol.upper():m for m in mappings if m.market.upper()=="BEI"}
    selected=[available[s] for s in symbols if s in available]
    validator=WalkForwardValidator(minimum_bars=60,horizon_bars=5,step_bars=1,target_pct=0.04,stop_pct=0.025)
    results={}
    errors={}
    for mapping in selected:
        try:
            provider=YahooFinanceProvider([mapping],period="5y",interval="1d")
            series=provider.load_series("BEI",mapping.symbol)
            report=validator.validate(series)
            results[mapping.symbol.upper()]=_summary(mapping.symbol.upper(),series,report)
        except Exception as exc:
            errors[mapping.symbol.upper()]=str(exc)
    payload={
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "universe_size":200,
        "selected_top5":symbols,
        "methodology":{
            "name":"HANZ no-lookahead 5Y historical replay",
            "period":"5y daily",
            "minimum_bars":60,
            "horizon_bars":5,
            "step_bars":1,
            "target_pct":4.0,
            "stop_pct":2.5,
            "note":"Historical replay uses HANZ core technical decision rules. Live V43 ranking also uses market/flow layers that are not fully reconstructible historically."
        },
        "results":results,
        "errors":errors,
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    print(json.dumps({"top5":symbols,"results":list(results),"errors":errors},indent=2))


if __name__=="__main__":
    main()
