#!/usr/bin/env python3
"""HANZ Pardo-style walk-forward evidence validator.

This module does NOT optimize the trading strategy itself. It validates evidence
exported by a proper sequential WFA process and refuses to produce a pass unless
minimum statistical/robustness fields are present.

Expected CSVs:
  trades.csv: window_id,trade_id,r_multiple,is_oos
  windows.csv: window_id,is_profit_r,oos_profit_r,oos_years,is_profit_r, is_years
Optional columns are tolerated; required columns are checked explicitly.
"""
import argparse, json, math
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

DEFAULT_MIN_OOS_TRADES=30
DEFAULT_MIN_DOF_REMAINING_PCT=90.0
DEFAULT_MIN_WFE=0.50       # HANZ implementation policy; configurable
DEFAULT_MIN_PROFITABLE_WINDOWS_PCT=50.0  # HANZ policy; configurable
DEFAULT_MAX_TRADE_PROFIT_SHARE_PCT=35.0  # HANZ concentration guard; configurable
DEFAULT_MIN_BACKTEST_YEARS=5.0


def safe_div(a,b):
    return None if b is None or abs(b)<1e-12 else a/b


def load_csv(path):
    p=Path(path)
    if not p.exists(): raise FileNotFoundError(p)
    return pd.read_csv(p)


def _evidence_span_years(trades, windows):
    """Return chronological evidence span in years, or None when dates are absent.

    We intentionally use the earliest/latest observed timestamps instead of
    summing rolling-window durations, because overlapping walk-forward windows
    can otherwise exaggerate the tested history.
    """
    # Reversed window bounds cannot represent a sequential historical test.
    # Without this check, a corrupt window can inflate apparent 5Y coverage.
    if {"window_start", "window_end"}.issubset(windows.columns):
        starts = pd.to_datetime(windows["window_start"], errors="coerce", utc=True)
        ends = pd.to_datetime(windows["window_end"], errors="coerce", utc=True)
        if (starts > ends).any():
            raise ValueError("Invalid walk-forward chronology evidence: reversed window boundaries")
    # A trade cannot close before it opens. Reversed timestamps can corrupt
    # execution-order drawdown and inflate chronological history evidence.
    if {"entry_date", "exit_date"}.issubset(trades.columns):
        entries = pd.to_datetime(trades["entry_date"], errors="coerce", utc=True)
        exits = pd.to_datetime(trades["exit_date"], errors="coerce", utc=True)
        if (entries > exits).any():
            raise ValueError("Invalid walk-forward trade chronology: exit before entry")
    # A trade execution cannot precede its entry or occur after its exit.
    # All three timestamps may be inside the OOS window yet contradict
    # the trade's actual lifecycle; reject that evidence before validation.
    if {"entry_date", "trade_date"}.issubset(trades.columns):
        entries = pd.to_datetime(trades["entry_date"], errors="coerce", utc=True)
        executions = pd.to_datetime(trades["trade_date"], errors="coerce", utc=True)
        if (executions < entries).any():
            raise ValueError("Invalid walk-forward trade chronology: trade before entry")
    if {"trade_date", "exit_date"}.issubset(trades.columns):
        executions = pd.to_datetime(trades["trade_date"], errors="coerce", utc=True)
        exits = pd.to_datetime(trades["exit_date"], errors="coerce", utc=True)
        if (executions > exits).any():
            raise ValueError("Invalid walk-forward trade chronology: trade after exit")

    candidates=[]
    # A partially exported OOS interval is not legacy evidence: it is corrupt.
    # Otherwise IS-inclusive window_start/window_end could falsely establish 5Y.
    oos_fields = {"oos_start", "oos_end"}.intersection(windows.columns)
    if oos_fields and len(oos_fields) != 2:
        raise ValueError("Incomplete walk-forward OOS chronology evidence: both oos_start and oos_end required")
    explicit_oos_bounds = len(oos_fields) == 2
    # Reversed OOS bounds can falsely extend five-year coverage even when
    # exports lack trade window IDs or dated entry/exit evidence.
    if explicit_oos_bounds:
        oos_starts = pd.to_datetime(windows["oos_start"], errors="coerce", utc=True)
        oos_ends = pd.to_datetime(windows["oos_end"], errors="coerce", utc=True)
        if (oos_starts > oos_ends).any():
            raise ValueError("Invalid walk-forward OOS chronology evidence: reversed OOS boundaries")
        # OOS test dates must lie inside the enclosing WFA window.
        if {"window_start", "window_end"}.issubset(windows.columns):
            starts = pd.to_datetime(windows["window_start"], errors="coerce", utc=True)
            ends = pd.to_datetime(windows["window_end"], errors="coerce", utc=True)
            if ((oos_starts < starts) | (oos_ends > ends)).any():
                raise ValueError("Invalid walk-forward OOS chronology evidence: outside enclosing window")
    for frame in (trades, windows):
        for col in (
            "timestamp","trade_date","entry_date","exit_date",
            "start_date","end_date","window_start","window_end",
            "is_start","is_end","oos_start","oos_end",
        ):
            if col in frame.columns:
                parsed=pd.to_datetime(frame[col],errors="coerce",utc=True)
                # A corrupt/missing timestamp cannot be silently discarded to
                # make a five-year evidence span appear valid.
                if parsed.isna().any():
                    raise ValueError("Invalid walk-forward chronology evidence: "+col)
                # A future-dated trade or window cannot establish realized history.
                # Check all rows, including IS rows, before selecting OOS evidence.
                if (parsed > pd.Timestamp.now(tz="UTC")).any():
                    raise ValueError("Future-dated walk-forward chronology evidence: "+col)
                # Validate every timestamp above, including IS rows, but only
                # realized OOS trades may establish trade-based 5Y coverage.
                # A stray old IS trade must not inflate the backtest span.
                if frame is trades and "is_oos" in trades.columns:
                    flags = trades["is_oos"].astype(str).str.strip().str.lower()
                    parsed = parsed.loc[flags.isin({"1", "true", "yes"})]
                # IS-only window dates are validation inputs, not proof of
                # five years of out-of-sample backtest coverage. Keep their
                # invalid/future-date checks above, but exclude from the span.
                # When explicit OOS bounds exist, IS-inclusive window dates
                # cannot extend the verified out-of-sample history span.
                # Still validate every timestamp before excluding it.
                # When the exporter supplies explicit OOS bounds, only those
                # bounds establish the tested history span. Unassigned trade
                # timestamps are still validated above, but cannot extend it.
                if frame is trades and explicit_oos_bounds:
                    continue
                if frame is windows and (col in {"is_start", "is_end"} or
                        (explicit_oos_bounds and col not in {"oos_start", "oos_end"})):
                    continue
                if len(parsed):
                    candidates.extend([parsed.min(),parsed.max()])
    if len(candidates)<2:
        return None
    start=min(candidates); end=max(candidates)
    # Five years means the fifth calendar anniversary, not a rounded
    # 365.2425-day estimate (which can reject an exact five-year span).
    start_day=start.date(); end_day=end.date()
    def anniversary(years):
        try:
            return start_day.replace(year=start_day.year+years)
        except ValueError:
            return start_day.replace(year=start_day.year+years, day=28)
    years=end_day.year-start_day.year
    if end_day<anniversary(years):
        years-=1
    current=anniversary(years)
    following=anniversary(years+1)
    return max(0.0, years+(end_day-current).days/(following-current).days)


def validate(trades, windows, dof_remaining_pct, min_oos_trades=30, min_wfe=0.50,
             min_profitable_windows_pct=50.0, max_trade_profit_share_pct=35.0,
             min_backtest_years=DEFAULT_MIN_BACKTEST_YEARS):
    # Five-year OOS history is a G1 safety floor, not a configurable bypass.
    # A lower CLI/API override must not certify a shorter test as five years.
    if not math.isfinite(min_backtest_years) or min_backtest_years < DEFAULT_MIN_BACKTEST_YEARS:
        raise ValueError("G1 minimum backtest history cannot be below 5 years")
    # G1 WFE safety floor: overrides may tighten the minimum, never reduce
    # the required out-of-sample / in-sample annualized performance ratio.
    if not math.isfinite(min_wfe) or min_wfe < DEFAULT_MIN_WFE:
        raise ValueError("G1 minimum WFE cannot be below 0.50")
    # G1 profitable-window consistency is a safety floor, not a bypassable knob.
    if (not math.isfinite(min_profitable_windows_pct)
            or min_profitable_windows_pct < DEFAULT_MIN_PROFITABLE_WINDOWS_PCT):
        raise ValueError("G1 minimum profitable walk-forward windows cannot be below 50%")
    # G1 profit concentration is a maximum safety ceiling. Callers may
    # tighten it, but cannot certify concentrated returns by raising it.
    if (not math.isfinite(max_trade_profit_share_pct)
            or not 0.0 <= max_trade_profit_share_pct <= DEFAULT_MAX_TRADE_PROFIT_SHARE_PCT):
        raise ValueError("G1 maximum trade profit concentration cannot exceed 35%")
    # G1 safety floor: CLI/API overrides may tighten, never reduce, the
    # minimum independent OOS trade sample required for validation.
    if min_oos_trades < DEFAULT_MIN_OOS_TRADES:
        raise ValueError("G1 minimum OOS trades cannot be below 30")
    req_t={"r_multiple","is_oos"}; req_w={"window_id","oos_profit_r"}
    missing_t=req_t-set(trades.columns); missing_w=req_w-set(windows.columns)
    if missing_t or missing_w:
        raise ValueError(f"Missing columns: trades={sorted(missing_t)} windows={sorted(missing_w)}")

    # A repeated or missing window ID is not an independent WFA window.
    # Reject it before calculating window consistency and annualized WFE.
    window_ids = windows["window_id"]
    normalized_ids = window_ids.astype(str).str.strip()
    if (window_ids.isna().any() or normalized_ids.eq("").any()
            or normalized_ids.duplicated().any()):
        raise ValueError("Invalid or duplicate walk-forward window_id evidence")

    # A trade assigned to an unknown WFA window cannot contribute independent
    # OOS evidence. Keep legacy exports without a trade window_id supported.
    if "window_id" in trades.columns:
        trade_window_ids = trades["window_id"]
        normalized_trade_window_ids = trade_window_ids.astype(str).str.strip()
        if trade_window_ids.isna().any() or normalized_trade_window_ids.eq("").any():
            raise ValueError("Invalid walk-forward trade window_id evidence")
        if not normalized_trade_window_ids.isin(set(normalized_ids)).all():
            raise ValueError("Unknown walk-forward trade window_id evidence")

    # Duplicate trade identities must not inflate the independent OOS sample.
    # A trade_id may be reused across distinct walk-forward windows, but not
    # within the same window. Preserve legacy exports without a trade_id.
    if "trade_id" in trades.columns:
        trade_ids = trades["trade_id"]
        normalized_trade_ids = trade_ids.astype(str).str.strip()
        if trade_ids.isna().any() or normalized_trade_ids.eq("").any():
            raise ValueError("Invalid or duplicate walk-forward trade_id evidence")
        if "window_id" in trades.columns:
            trade_window_ids = trades["window_id"]
            normalized_trade_window_ids = trade_window_ids.astype(str).str.strip()
            if trade_window_ids.isna().any() or normalized_trade_window_ids.eq("").any():
                raise ValueError("Invalid or duplicate walk-forward trade_id evidence")
            duplicate = pd.DataFrame({
                "window_id": normalized_trade_window_ids,
                "trade_id": normalized_trade_ids,
            }).duplicated().any()
        else:
            duplicate = normalized_trade_ids.duplicated().any()
        if duplicate:
            raise ValueError("Invalid or duplicate walk-forward trade_id evidence")

    # Fail closed on corrupt IS/OOS labels: silently dropping a losing OOS row
    # could turn a failing strategy into a false PASS.
    oos_flags=trades["is_oos"].astype(str).str.strip().str.lower()
    valid_oos_flags={"1","true","yes","0","false","no"}
    if not oos_flags.isin(valid_oos_flags).all():
        raise ValueError("Invalid OOS/IS trade classification evidence")

    # A realized OOS trade must close within its assigned OOS test window.
    # Otherwise an IS/out-of-window result can be mislabeled as independent OOS
    # evidence. Apply this check when exports supply explicit window bounds.
    if ("window_id" in trades.columns and {"oos_start", "oos_end"}.issubset(windows.columns)
            and any(col in trades.columns for col in ("entry_date", "exit_date", "trade_date"))):
        starts = pd.to_datetime(windows["oos_start"], errors="coerce", utc=True).dt.normalize()
        ends = pd.to_datetime(windows["oos_end"], errors="coerce", utc=True).dt.normalize()
        if starts.isna().any() or ends.isna().any() or (starts > ends).any():
            raise ValueError("Invalid walk-forward OOS window chronology evidence")
        bounds = dict(zip(normalized_ids, zip(starts, ends)))
        # An OOS trade must be opened AND closed within its assigned test
        # window. An IS-origin position closed during OOS is not an independent
        # OOS entry. Legacy exports without entry_date remain supported.
        oos_rows = oos_flags.isin({"1", "true", "yes"})
        # Every supplied trade date is provenance evidence. Previously,
        # trade_date was ignored when exit_date also existed, allowing an
        # out-of-window execution date to pass OOS validation.
        date_columns = [
            col for col in ("entry_date", "exit_date", "trade_date")
            if col in trades.columns
        ]
        for date_column in date_columns:
            observed = pd.to_datetime(trades[date_column], errors="coerce", utc=True).dt.normalize()
            for wid, day in zip(normalized_trade_window_ids[oos_rows], observed[oos_rows]):
                start, end = bounds[wid]
                if pd.isna(day) or not start <= day <= end:
                    raise ValueError("OOS trade outside assigned walk-forward window")

    t=trades.loc[oos_flags.isin({"1","true","yes"})].copy()
    t["r_multiple"]=pd.to_numeric(t["r_multiple"],errors="coerce")
    # Fail closed: silently dropping invalid OOS outcomes inflates sample quality.
    # NaN and +/-infinity must never contribute to expectancy, WFE or drawdown.
    if not t["r_multiple"].map(math.isfinite).all():
        raise ValueError("Invalid OOS trade return evidence")
    # Drawdown must follow actual OOS execution chronology, not CSV row order.
    # Prefer exit timestamps, since R is realized when a trade closes.
    for date_column in ("exit_date", "trade_date"):
        if date_column in t.columns:
            chronological_dates=pd.to_datetime(t[date_column],errors="coerce",utc=True)
            if chronological_dates.isna().any():
                raise ValueError("Invalid OOS trade chronology: "+date_column)
            t=t.assign(_chronological_date=chronological_dates).sort_values(
                "_chronological_date",kind="stable"
            ).drop(columns="_chronological_date")
            break
    windows=windows.copy(); windows["oos_profit_r"]=pd.to_numeric(windows["oos_profit_r"],errors="coerce")
    if not windows["oos_profit_r"].map(math.isfinite).all():
        raise ValueError("Invalid OOS window profit evidence")

    evidence_span_years=_evidence_span_years(trades, windows)

    oos_trades=len(t)
    expectancy=float(t["r_multiple"].mean()) if oos_trades else None
    wins=float((t["r_multiple"]>0).mean()*100) if oos_trades else None
    total_oos_r=float(t["r_multiple"].sum()) if oos_trades else 0.0
    profitable_windows_pct=float((windows["oos_profit_r"]>0).mean()*100) if len(windows) else None

    # WFE = annualized OOS P&L / annualized IS P&L when durations are supplied.
    wfe=None
    if {"is_profit_r","is_years","oos_years"}.issubset(windows.columns):
        for c in ["is_profit_r","is_years","oos_years"]: windows[c]=pd.to_numeric(windows[c],errors="coerce")
        # Never let pandas sum() silently skip missing/invalid WFE inputs.
        if (any(not windows[c].map(math.isfinite).all() for c in ("is_profit_r","is_years","oos_years"))
                or (windows[["is_years","oos_years"]] <= 0).any().any()):
            raise ValueError("Invalid walk-forward annualization evidence")
        is_profit=float(windows["is_profit_r"].sum())
        is_years=float(windows["is_years"].sum())
        oos_profit=float(windows["oos_profit_r"].sum())
        oos_years=float(windows["oos_years"].sum())
        ann_is=safe_div(is_profit,is_years); ann_oos=safe_div(oos_profit,oos_years)
        if ann_is is not None and ann_is>0 and ann_oos is not None: wfe=ann_oos/ann_is

    # Equity/drawdown in R from chronological OOS trades.
    equity=t["r_multiple"].cumsum()
    # Include the initial flat equity (0 R): an opening loss is a real drawdown.
    peak=equity.cummax().clip(lower=0.0)
    dd=peak-equity
    max_dd_r=float(dd.max()) if len(dd) else None

    # Big-fish concentration diagnostic: largest winning trade as share of all positive R.
    positives=t.loc[t["r_multiple"]>0,"r_multiple"]
    pos_sum=float(positives.sum()) if len(positives) else 0.0
    max_trade_share=(float(positives.max())/pos_sum*100) if pos_sum>0 else None

    # A percentage must be finite and within [0, 100]. Invalid evidence
    # must never satisfy the >=90% strategy-validation safety gate.
    dof_remaining_pct=float(dof_remaining_pct)
    if not math.isfinite(dof_remaining_pct) or not 0.0 <= dof_remaining_pct <= 100.0:
        raise ValueError("Invalid degrees-of-freedom remaining evidence")

    # Finite input rows can overflow during pandas sums/cumsums. Such
    # derived metrics must never certify a strategy (e.g. infinite WFE,
    # expectancy, or positive-R sum masking profit concentration).
    derived_metrics = {
        "oos_expectancy_r": expectancy,
        "total_oos_r": total_oos_r,
        "oos_win_rate_pct": wins,
        "profitable_wf_pct": profitable_windows_pct,
        "wfe": wfe,
        "oos_max_dd_r": max_dd_r,
        "positive_oos_r": pos_sum,
        "max_trade_profit_share_pct": max_trade_share,
    }
    for label, value in derived_metrics.items():
        if value is not None and not math.isfinite(value):
            raise ValueError("Nonfinite walk-forward derived evidence: " + label)

    checks={
      "five_year_history": evidence_span_years is not None and evidence_span_years>=min_backtest_years,
      "oos_trade_sample": oos_trades>=min_oos_trades,
      "degrees_of_freedom": float(dof_remaining_pct)>=90.0,
      "positive_oos_expectancy": expectancy is not None and expectancy>0,
      "multiple_walk_forward_windows": len(windows)>1,
      "profitable_window_consistency": profitable_windows_pct is not None and profitable_windows_pct>=min_profitable_windows_pct,
      "wfe": wfe is not None and wfe>=min_wfe,
      "profit_concentration": max_trade_share is not None and max_trade_share<=max_trade_profit_share_pct,
      "drawdown_measured": max_dd_r is not None,
    }
    passed=all(checks.values())
    return {
      "passed":passed,"checks":checks,"oos_trades":oos_trades,"wf_windows":int(len(windows)),
      "oos_expectancy_r":expectancy,"oos_win_rate_pct":wins,"total_oos_r":total_oos_r,
      "wfe":wfe,"oos_max_dd_r":max_dd_r,"profitable_wf_pct":profitable_windows_pct,
      "max_trade_profit_share_pct":max_trade_share,"dof_remaining_pct":float(dof_remaining_pct),
      "backtest_years":evidence_span_years,
      "policy":{"min_backtest_years":min_backtest_years,"min_oos_trades":min_oos_trades,"min_wfe":min_wfe,"min_dof_remaining_pct":90.0,
                "min_profitable_windows_pct":min_profitable_windows_pct,
                "max_trade_profit_share_pct":max_trade_profit_share_pct}
    }


def env_lines(r):
    def val(x): return "" if x is None else (f"{x:.6g}" if isinstance(x,float) else str(x))
    return "\n".join([
      f"HANZ_STRATEGY_WFA_VALIDATED={1 if r['passed'] else 0}",
      f"HANZ_STRATEGY_BACKTEST_YEARS={val(r['backtest_years'])}",
      f"HANZ_STRATEGY_WFE={val(r['wfe'])}",
      f"HANZ_STRATEGY_OOS_TRADES={r['oos_trades']}",
      f"HANZ_STRATEGY_WF_WINDOWS={r['wf_windows']}",
      f"HANZ_STRATEGY_OOS_EXPECTANCY_R={val(r['oos_expectancy_r'])}",
      f"HANZ_STRATEGY_DOF_REMAINING_PCT={val(r['dof_remaining_pct'])}",
      f"HANZ_STRATEGY_OOS_MAX_DD_R={val(r['oos_max_dd_r'])}",
      f"HANZ_STRATEGY_PROFITABLE_WF_PCT={val(r['profitable_wf_pct'])}",
      f"HANZ_STRATEGY_MAX_TRADE_PROFIT_SHARE_PCT={val(r['max_trade_profit_share_pct'])}",
      f"HANZ_STRATEGY_VALIDATED_AT={datetime.now(timezone.utc).isoformat()}",
    ])


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--trades',required=True); ap.add_argument('--windows',required=True)
    ap.add_argument('--dof-remaining-pct',required=True,type=float)
    ap.add_argument('--min-backtest-years',type=float,default=DEFAULT_MIN_BACKTEST_YEARS)
    ap.add_argument('--min-oos-trades',type=int,default=DEFAULT_MIN_OOS_TRADES)
    ap.add_argument('--min-wfe',type=float,default=DEFAULT_MIN_WFE)
    ap.add_argument('--min-profitable-windows-pct',type=float,default=DEFAULT_MIN_PROFITABLE_WINDOWS_PCT)
    ap.add_argument('--max-trade-profit-share-pct',type=float,default=DEFAULT_MAX_TRADE_PROFIT_SHARE_PCT)
    ap.add_argument('--json-out'); ap.add_argument('--env-out')
    a=ap.parse_args()
    r=validate(load_csv(a.trades),load_csv(a.windows),a.dof_remaining_pct,a.min_oos_trades,a.min_wfe,a.min_profitable_windows_pct,a.max_trade_profit_share_pct,a.min_backtest_years)
    text=json.dumps(r,indent=2)
    print(text); print('\n# Environment evidence\n'+env_lines(r))
    if a.json_out: Path(a.json_out).write_text(text)
    if a.env_out: Path(a.env_out).write_text(env_lines(r)+'\n')
    raise SystemExit(0 if r['passed'] else 2)

if __name__=='__main__': main()
