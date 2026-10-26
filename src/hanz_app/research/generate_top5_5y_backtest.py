from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from hanz_data import MarketSeries, YahooFinanceProvider, YahooSymbol, load_yahoo_universe
from hanz_validation.walk_forward import WalkForwardValidator, DecisionOutcome

SUPABASE_URL=os.environ.get("SUPABASE_URL","").rstrip("/")
SUPABASE_KEY=os.environ.get("SUPABASE_SECRET_KEY","")
OUT=Path("docs/dashboard/swing/backtest-5y.json")
UNIVERSE=Path("config/universe/bei_candidate_pool.csv")
# A five-year calendar span with sparse candles is not a complete daily backtest.
MIN_5Y_TRADING_DAYS = 1000
# A long gap can hide years of missing trading evidence even with 1000 bars.
MAX_5Y_GAP_DAYS = 45


def _num(v, default=None):
    try:
        # JSON booleans are not numeric trading evidence (True == 1 in Python).
        if isinstance(v, bool) or v is None or v=="":
            return default
        value = float(v)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _zero_volume_days20(r):
    """Do not truncate malformed liquidity counts into a safe-looking integer."""
    raw = r.get("zero_volume_days20")
    if raw is None or raw == "":
        return 0  # Preserve legacy snapshots without this optional field.
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        count = raw
    elif isinstance(raw, str) and raw.isdecimal():
        count = int(raw)
    else:
        return None
    return count if 0 <= count <= 20 else None


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


def _valid_explicit_avg_value20(r):
    # Absent legacy liquidity evidence remains optional; malformed explicit
    # evidence must not silently bypass the Top 5 liquidity threshold.
    return ("avg_value20" not in r or r["avg_value20"] is None
            or _num(r["avg_value20"]) is not None)


def _legacy_wait_eligible(row):
    r=row.get("risk_validation") or {}
    action=str(r.get("hanz_action") or row.get("hanz_action") or "").upper()
    if action!="AVOID":
        return False
    raw=_num((r.get("opportunity_score_breakdown") or {}).get("raw_score_before_action_cap"))
    rr2=_num(r.get("rr_target_2"))
    avg=_num(r.get("avg_value20"))
    zero=_zero_volume_days20(r)
    vol=str(r.get("volatility_status") or "").upper()
    regime=str(r.get("market_regime") or "").upper()
    blocked=bool((r.get("momentum_guard") or {}).get("blocked"))
    lo=_num(row.get("entry_low")); hi=_num(row.get("entry_high")); t1=_num(row.get("target_1"))
    mid=(lo+hi)/2 if lo and hi else None
    upside=((t1-mid)/mid*100) if t1 is not None and mid else None
    return (
        raw is not None and raw>=30
        and rr2 is not None and rr2>=2
        and not blocked and vol!="EXTREME" and zero is not None and zero<5
        and _valid_explicit_avg_value20(r)
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
    zero=_zero_volume_days20(r)
    if zero is None or zero>=5:
        return False
    if not _valid_explicit_avg_value20(r):
        return False
    avg=_num(r.get("avg_value20"))
    if avg is not None and avg<100_000_000:
        return False
    # An explicit malformed price is not equivalent to absent optional evidence.
    if any(key in row and row[key] is not None and _num(row[key]) is None
           for key in ("entry_low", "entry_high", "target_1")):
        return False
    lo=_num(row.get("entry_low")); hi=_num(row.get("entry_high")); t1=_num(row.get("target_1"))
    # Explicit nonpositive prices are invalid, not absent optional evidence.
    # Truthiness previously skipped the upside guard for zero entry/target prices.
    if any(v is not None and v <= 0 for v in (lo, hi, t1)):
        return False
    if lo is not None and hi is not None and hi < lo:
        return False
    if lo is not None and hi is not None and t1 is not None:
        mid=(lo+hi)/2
        if ((t1-mid)/mid*100)<0.5:
            return False
    return _rank(row)>0


def _top5_symbols():
    # Monitor rows are newest-first. Only the newest snapshot of each
    # ticker is authoritative; an older eligible duplicate must not
    # override a newer excluded one or consume a second Top 5 slot.
    latest = {}
    for row in _get_monitor_rows():
        ticker = str(row.get("ticker") or "").strip().upper()
        if ticker and ticker not in latest:
            latest[ticker] = row
    rows = [r for r in latest.values() if _eligible(r)]
    rows.sort(key=lambda r: (-_rank(r), str(r.get("ticker") or "")))
    return [str(r.get("ticker") or "").strip().upper() for r in rows[:5]]


# Explicit Yahoo research mappings for selected symbols missing from the static pool.
# Delayed, non-official data: never eligible as independent execution evidence.
RESEARCH_ONLY_FALLBACK_TICKERS = {"MPMX": "MPMX.JK", "BDMN": "BDMN.JK", "AGII": "AGII.JK"}


def _research_mappings(mappings):
    available = {m.symbol.upper(): m for m in mappings if m.market.upper() == "BEI"}
    for symbol, yahoo_ticker in RESEARCH_ONLY_FALLBACK_TICKERS.items():
        available.setdefault(symbol, YahooSymbol(market="BEI", symbol=symbol, yahoo_ticker=yahoo_ticker))
    return available


def _five_year_replay_series(series: MarketSeries) -> MarketSeries:
    """Use real candles across the fifth calendar anniversary, not a 5y API cutoff.

    Yahoo's rolling period='5y' can begin after the calendar anniversary on a
    weekend/holiday, yielding only 4.99 years. Fetch a longer real history and
    retain seven calendar days of pre-anniversary trading sessions. A newly
    listed symbol stays LIMITED_HISTORY; no candles are synthesized.
    """
    if not series.bars:
        return series
    last_day = series.bars[-1].timestamp.date()
    try:
        five_years_ago = last_day.replace(year=last_day.year - 5)
    except ValueError:
        five_years_ago = last_day.replace(year=last_day.year - 5, day=28)
    cutoff = five_years_ago - timedelta(days=7)
    return MarketSeries.from_iterable(
        series.symbol, series.market,
        (bar for bar in series.bars if bar.timestamp.date() >= cutoff),
    )


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
    # A 4.8-year span is not five calendar years. Require the full fifth
    # anniversary, including leap-day starts, before claiming 5Y coverage.
    full_five_years=False
    if len(bars)>1:
        first_day=bars[0].timestamp.date()
        last_day=bars[-1].timestamp.date()
        try:
            fifth_anniversary=first_day.replace(year=first_day.year+5)
        except ValueError:
            fifth_anniversary=first_day.replace(year=first_day.year+5,day=28)
        full_five_years=last_day>=fifth_anniversary
    trading_days=sorted({bar.timestamp.date() for bar in bars})
    distinct_days=len(trading_days)
    sufficient_sessions=distinct_days>=MIN_5Y_TRADING_DAYS
    max_gap_days=max(((b-a).days for a,b in zip(trading_days,trading_days[1:])),default=None)
    continuous_history=max_gap_days is not None and max_gap_days<=MAX_5Y_GAP_DAYS
    return {
        "symbol":symbol,
        "status":"OK" if full_five_years and sufficient_sessions and continuous_history else "LIMITED_HISTORY",
        "distinct_trading_days":distinct_days,
        "minimum_trading_days":MIN_5Y_TRADING_DAYS,
        "max_gap_days":max_gap_days,
        "max_allowed_gap_days":MAX_5Y_GAP_DAYS,
        "history_gap_reason":("SHORT_CALENDAR_SPAN" if not full_five_years else
                              "INSUFFICIENT_TRADING_SESSIONS" if not sufficient_sessions else
                              "LONG_HISTORY_GAP" if not continuous_history else None),
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


def _selection_coverage(symbols, available, results, errors):
    """Account for every selected ticker; a missing mapping is not a backtest."""
    for symbol in symbols:
        if symbol not in available:
            errors.setdefault(symbol, "MISSING_UNIVERSE_MAPPING")
    evaluated=sum(symbol in results for symbol in symbols)
    unavailable=sum(symbol in errors for symbol in symbols)
    # A downloaded history shorter than five years is an evaluated ticker,
    # NOT a completed five-year backtest. Never inflate validated coverage.
    full_history=sum(
        symbol in results and results[symbol].get("status") == "OK"
        for symbol in symbols
    )
    limited_history=[symbol for symbol in symbols if symbol in results
                     and results[symbol].get("status") != "OK"]
    # Contradictory result/error evidence cannot certify complete coverage;
    # double-counting one ticker must not hide another unaccounted ticker.
    contradictory=any(symbol in results and symbol in errors for symbol in symbols)
    accounted=all(symbol in results or symbol in errors for symbol in symbols)
    return {
        "selected_count":len(symbols),
        "evaluated_count":evaluated,
        "unavailable_count":unavailable,
        "five_year_history_count":full_history,
        "limited_history_symbols":limited_history,
        "all_selected_accounted_for":accounted and not contradictory,
        # A Top 5 report is complete only with five DISTINCT full-history tickers.
        # An empty, short or duplicate selection must never pass vacuously.
        "backtest_complete":len(symbols)==5 and len(set(symbols))==5
                            and evaluated==5 and full_history==5
                            and unavailable==0 and not contradictory,
    }


def main():
    symbols=_top5_symbols()
    mappings=load_yahoo_universe(UNIVERSE)
    available=_research_mappings(mappings)
    selected=[available[s] for s in symbols if s in available]
    validator=WalkForwardValidator(minimum_bars=60,horizon_bars=5,step_bars=1,target_pct=0.04,stop_pct=0.025)
    results={}
    errors={}
    for mapping in selected:
        try:
            provider=YahooFinanceProvider([mapping],period="10y",interval="1d")
            series=_five_year_replay_series(provider.load_series("BEI",mapping.symbol))
            report=validator.validate(series)
            results[mapping.symbol.upper()]=_summary(mapping.symbol.upper(),series,report)
        except Exception as exc:
            errors[mapping.symbol.upper()]=str(exc)
    coverage=_selection_coverage(symbols, available, results, errors)
    payload={
        "coverage":coverage,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "universe_size":200,
        "selected_top5":symbols,
        "methodology":{
            "name":"HANZ no-lookahead 5Y historical replay",
            "period":"5 calendar years plus up to 7 real trading-calendar buffer days; Yahoo 10y acquisition",
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
