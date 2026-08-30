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
from pathlib import Path
import pandas as pd

DEFAULT_MIN_OOS_TRADES=30
DEFAULT_MIN_DOF_REMAINING_PCT=90.0
DEFAULT_MIN_WFE=0.50       # HANZ implementation policy; configurable
DEFAULT_MIN_PROFITABLE_WINDOWS_PCT=50.0  # HANZ policy; configurable
DEFAULT_MAX_TRADE_PROFIT_SHARE_PCT=35.0  # HANZ concentration guard; configurable


def safe_div(a,b):
    return None if b is None or abs(b)<1e-12 else a/b


def load_csv(path):
    p=Path(path)
    if not p.exists(): raise FileNotFoundError(p)
    return pd.read_csv(p)


def validate(trades, windows, dof_remaining_pct, min_oos_trades=30, min_wfe=0.50,
             min_profitable_windows_pct=50.0, max_trade_profit_share_pct=35.0):
    req_t={"r_multiple","is_oos"}; req_w={"window_id","oos_profit_r"}
    missing_t=req_t-set(trades.columns); missing_w=req_w-set(windows.columns)
    if missing_t or missing_w:
        raise ValueError(f"Missing columns: trades={sorted(missing_t)} windows={sorted(missing_w)}")

    t=trades.copy(); t=t[t["is_oos"].astype(str).str.lower().isin(["1","true","yes"])]
    t["r_multiple"]=pd.to_numeric(t["r_multiple"],errors="coerce"); t=t.dropna(subset=["r_multiple"])
    windows=windows.copy(); windows["oos_profit_r"]=pd.to_numeric(windows["oos_profit_r"],errors="coerce")

    oos_trades=len(t)
    expectancy=float(t["r_multiple"].mean()) if oos_trades else None
    wins=float((t["r_multiple"]>0).mean()*100) if oos_trades else None
    total_oos_r=float(t["r_multiple"].sum()) if oos_trades else 0.0
    profitable_windows_pct=float((windows["oos_profit_r"]>0).mean()*100) if len(windows) else None

    # WFE = annualized OOS P&L / annualized IS P&L when durations are supplied.
    wfe=None
    if {"is_profit_r","is_years","oos_years"}.issubset(windows.columns):
        for c in ["is_profit_r","is_years","oos_years"]: windows[c]=pd.to_numeric(windows[c],errors="coerce")
        is_profit=float(windows["is_profit_r"].sum())
        is_years=float(windows["is_years"].sum())
        oos_profit=float(windows["oos_profit_r"].sum())
        oos_years=float(windows["oos_years"].sum())
        ann_is=safe_div(is_profit,is_years); ann_oos=safe_div(oos_profit,oos_years)
        if ann_is is not None and ann_is>0 and ann_oos is not None: wfe=ann_oos/ann_is

    # Equity/drawdown in R from chronological OOS trades.
    equity=t["r_multiple"].cumsum()
    peak=equity.cummax()
    dd=peak-equity
    max_dd_r=float(dd.max()) if len(dd) else None

    # Big-fish concentration diagnostic: largest winning trade as share of all positive R.
    positives=t.loc[t["r_multiple"]>0,"r_multiple"]
    pos_sum=float(positives.sum()) if len(positives) else 0.0
    max_trade_share=(float(positives.max())/pos_sum*100) if pos_sum>0 else None

    checks={
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
      "policy":{"min_oos_trades":min_oos_trades,"min_wfe":min_wfe,"min_dof_remaining_pct":90.0,
                "min_profitable_windows_pct":min_profitable_windows_pct,
                "max_trade_profit_share_pct":max_trade_profit_share_pct}
    }


def env_lines(r):
    def val(x): return "" if x is None else (f"{x:.6g}" if isinstance(x,float) else str(x))
    return "\n".join([
      f"HANZ_STRATEGY_WFA_VALIDATED={1 if r['passed'] else 0}",
      f"HANZ_STRATEGY_WFE={val(r['wfe'])}",
      f"HANZ_STRATEGY_OOS_TRADES={r['oos_trades']}",
      f"HANZ_STRATEGY_WF_WINDOWS={r['wf_windows']}",
      f"HANZ_STRATEGY_OOS_EXPECTANCY_R={val(r['oos_expectancy_r'])}",
      f"HANZ_STRATEGY_DOF_REMAINING_PCT={val(r['dof_remaining_pct'])}",
      f"HANZ_STRATEGY_OOS_MAX_DD_R={val(r['oos_max_dd_r'])}",
      f"HANZ_STRATEGY_PROFITABLE_WF_PCT={val(r['profitable_wf_pct'])}",
      f"HANZ_STRATEGY_MAX_TRADE_PROFIT_SHARE_PCT={val(r['max_trade_profit_share_pct'])}",
    ])


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--trades',required=True); ap.add_argument('--windows',required=True)
    ap.add_argument('--dof-remaining-pct',required=True,type=float)
    ap.add_argument('--min-oos-trades',type=int,default=DEFAULT_MIN_OOS_TRADES)
    ap.add_argument('--min-wfe',type=float,default=DEFAULT_MIN_WFE)
    ap.add_argument('--min-profitable-windows-pct',type=float,default=DEFAULT_MIN_PROFITABLE_WINDOWS_PCT)
    ap.add_argument('--max-trade-profit-share-pct',type=float,default=DEFAULT_MAX_TRADE_PROFIT_SHARE_PCT)
    ap.add_argument('--json-out'); ap.add_argument('--env-out')
    a=ap.parse_args()
    r=validate(load_csv(a.trades),load_csv(a.windows),a.dof_remaining_pct,a.min_oos_trades,a.min_wfe,a.min_profitable_windows_pct,a.max_trade_profit_share_pct)
    text=json.dumps(r,indent=2)
    print(text); print('\n# Environment evidence\n'+env_lines(r))
    if a.json_out: Path(a.json_out).write_text(text)
    if a.env_out: Path(a.env_out).write_text(env_lines(r)+'\n')
    raise SystemExit(0 if r['passed'] else 2)

if __name__=='__main__': main()
