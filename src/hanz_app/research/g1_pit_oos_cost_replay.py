"""Point-in-time G1 OOS research replay; never uses current monitor Top 5.

Inputs:
  bars.csv: symbol,date,open,close,volume
  snapshots.csv: asof_date,symbol,eligible,rank_score
Snapshots MUST be archived as-of decisions, not reconstructed current rankings.
Outputs are research evidence, never LIVE/BUY certification.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd

def replay(bars, snapshots, *, train_days=252, test_days=63,
           hold_days=5, top_n=5, buy_fee_pct=0.15,
           sell_fee_pct=0.25, slippage_pct=0.10):
    if min(train_days, test_days, hold_days, top_n) < 1:
        raise ValueError("Positive train/test/hold/top_n required")
    if min(buy_fee_pct, sell_fee_pct, slippage_pct) < 0:
        raise ValueError("Costs cannot be negative")
    if buy_fee_pct + sell_fee_pct + 2 * slippage_pct <= 0:
        raise ValueError("Positive execution costs required")
    required_bars={"symbol","date","open","close","volume"}
    required_snap={"asof_date","symbol","eligible","rank_score"}
    if not required_bars.issubset(bars) or not required_snap.issubset(snapshots):
        raise ValueError("Missing PIT bars or archived snapshot columns")
    b=bars.copy(); s=snapshots.copy()
    b["date"]=pd.to_datetime(b["date"],utc=True,errors="raise").dt.normalize()
    s["asof_date"]=pd.to_datetime(s["asof_date"],utc=True,errors="raise").dt.normalize()
    if b.duplicated(["symbol","date"]).any() or s.duplicated(["symbol","asof_date"]).any():
        raise ValueError("Duplicate market bars or archived decisions")
    for col in ("open","close","volume"):
        b[col]=pd.to_numeric(b[col],errors="raise")
    s["rank_score"]=pd.to_numeric(s["rank_score"],errors="raise")
    if not b[["open","close","volume"]].apply(lambda x: x.map(lambda v: pd.notna(v) and abs(v)!=float("inf"))).all().all():
        raise ValueError("Invalid OHLCV")
    if (b[["open","close"]] <= 0).any().any() or (b["volume"] < 0).any():
        raise ValueError("Invalid price or volume")
    if s["rank_score"].isna().any() or (~s["rank_score"].map(lambda v: abs(v)!=float("inf"))).any():
        raise ValueError("Invalid historical ranking")
    if not s["eligible"].isin([True,False,0,1]).all():
        raise ValueError("Invalid historical eligibility")
    b=b.sort_values(["symbol","date"])
    dates=sorted(b["date"].unique())
    trades=[]; windows=[]
    # IS precedes every OOS window; historical snapshot must predate execution.
    for start in range(train_days,len(dates)-hold_days,test_days):
        end=min(start+test_days,len(dates)-hold_days)
        cutoff=dates[start-1]
        oos_start=dates[start]; oos_end=dates[end-1]
        # Fail closed if no actual archived decision at the cutoff.
        decision=s[s["asof_date"]==cutoff]
        if decision.empty:
            windows.append({"window_id":len(windows)+1,"is_end":str(cutoff.date()),
                            "oos_start":str(oos_start.date()),"oos_end":str(oos_end.date()),
                            "status":"MISSING_PIT_SNAPSHOT","oos_profit_pct":None})
            continue
        picks=(decision[decision["eligible"].astype(bool)]
               .sort_values(["rank_score","symbol"],ascending=[False,True])
               .head(top_n)["symbol"].tolist())
        # Selection is frozen at the historical cutoff, never refreshed using later data.
        window_trades=[]
        for sym in picks:
            hist=b[b["symbol"]==sym].set_index("date")
            for i in range(start,end,hold_days):
                if i+hold_days>=end: break
                entry_day=dates[i]; exit_day=dates[i+hold_days]
                if entry_day not in hist.index or exit_day not in hist.index: continue
                entry=float(hist.loc[entry_day,"open"]); exit_price=float(hist.loc[exit_day,"close"])
                gross=(exit_price/entry-1)*100
                # Buy and sell slippage charged separately, both adverse.
                net=((exit_price*(1-(sell_fee_pct+slippage_pct)/100)) /
                     (entry*(1+(buy_fee_pct+slippage_pct)/100))-1)*100
                window_trades.append({"window_id":len(windows)+1,"symbol":sym,
                    "selection_asof":str(cutoff.date()),"entry_date":str(entry_day.date()),
                    "exit_date":str(exit_day.date()),"is_oos":True,
                    "gross_return_pct":round(gross,6),"net_return_pct":round(net,6),
                    "buy_fee_pct":buy_fee_pct,"sell_fee_pct":sell_fee_pct,
                    "slippage_per_side_pct":slippage_pct})
        trades.extend(window_trades)
        windows.append({"window_id":len(windows)+1,"is_end":str(cutoff.date()),
            "oos_start":str(oos_start.date()),"oos_end":str(oos_end.date()),
            "status":"EVALUATED" if window_trades else "NO_EXECUTABLE_TRADES",
            "selected_symbols":picks,"oos_trades":len(window_trades),
            "oos_profit_pct":round(sum(t["net_return_pct"] for t in window_trades),6)})
    return {"schema":"hanz-g1-pit-oos-cost-v1","method":"archived-asof-snapshot-frozen-selection",
        "status":"RESEARCH_EVIDENCE_ONLY","trades":trades,"windows":windows,
        "summary":{"oos_trades":len(trades),"windows":len(windows),
          "missing_pit_windows":sum(w["status"]=="MISSING_PIT_SNAPSHOT" for w in windows),
          "gross_mean_pct":round(sum(t["gross_return_pct"] for t in trades)/len(trades),6) if trades else None,
          "net_mean_pct":round(sum(t["net_return_pct"] for t in trades)/len(trades),6) if trades else None},
        "limitations":"Requires genuine archived PIT rankings. Frozen picks per OOS window; not live ranking replication, execution fills, five-year OOS certification or BUY readiness."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--bars",required=True);p.add_argument("--snapshots",required=True)
    p.add_argument("--output",default="docs/dashboard/swing/g1-pit-oos-cost.json")
    p.add_argument("--train-days",type=int,default=252)
    p.add_argument("--test-days",type=int,default=63)
    p.add_argument("--hold-days",type=int,default=5)
    p.add_argument("--buy-fee-pct",type=float,default=.15)
    p.add_argument("--sell-fee-pct",type=float,default=.25)
    p.add_argument("--slippage-pct",type=float,default=.10)
    a=p.parse_args()
    result=replay(pd.read_csv(a.bars),pd.read_csv(a.snapshots),train_days=a.train_days,
        test_days=a.test_days,hold_days=a.hold_days,buy_fee_pct=a.buy_fee_pct,
        sell_fee_pct=a.sell_fee_pct,slippage_pct=a.slippage_pct)
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result["summary"],indent=2))
    if result["summary"]["missing_pit_windows"] or not result["summary"]["oos_trades"]:
        raise SystemExit(2)

if __name__=="__main__":
    main()
