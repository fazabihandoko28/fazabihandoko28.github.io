"""Reconstructed historical OOS research, never actual production decision evidence.

Input rows are historical decisions rebuilt using information available at their
timestamp, with independently dated next-session fills. No future information
may enter the ranking inputs. This module does not fabricate historical signals.
"""
from __future__ import annotations

from datetime import date
from hanz_app.research.g2_candidate_replacement import select_top_five
from hanz_app.research.g2_net_trade_evidence import net_trade_evidence


def reconstructed_oos(decisions, fills, *, buy_fee_rate, sell_fee_rate,
                      buy_slippage_rate, sell_slippage_rate, assumption_source,
                      provenance):
    """Replay date-scoped candidate rankings and subsequent observed fills.

    decisions: {snapshot_date, ticker, eligible, rank_score, evidence_cutoff}
    fills: {trade_id, ticker, decision_date, buy_date, sell_date,
            buy_price, sell_price, shares, initial_risk_rupiah}
    """
    if not isinstance(provenance, str) or not provenance.strip():
        raise ValueError("Historical reconstruction provenance required")
    if not isinstance(decisions, list) or not isinstance(fills, list):
        raise ValueError("Decisions and fills must be lists")
    dates = sorted({row["snapshot_date"] for row in decisions
                    if isinstance(row, dict) and isinstance(row.get("snapshot_date"), str)})
    if not dates:
        raise ValueError("Historical dated decisions required")
    for row in decisions:
        if not isinstance(row, dict):
            raise ValueError("Malformed historical decision")
        try:
            day = date.fromisoformat(row["snapshot_date"])
            cutoff = date.fromisoformat(row["evidence_cutoff"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("Missing or invalid decision evidence cutoff") from exc
        if cutoff > day:
            raise ValueError("Look-ahead evidence in historical decision")
        if not isinstance(row.get("ticker"), str) or not row["ticker"].strip():
            raise ValueError("Missing historical ticker")
    snapshots = {}
    for day in dates:
        rows = [r for r in decisions if r["snapshot_date"] <= day]
        snapshots[day] = select_top_five(rows, as_of=day)
    trades = []
    seen_ids = set()
    for fill in fills:
        if not isinstance(fill, dict):
            raise ValueError("Malformed fill")
        try:
            decision_day = date.fromisoformat(fill["decision_date"])
            buy_day = date.fromisoformat(fill["buy_date"])
            sell_day = date.fromisoformat(fill["sell_date"])
            ticker = fill["ticker"]
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("Missing or invalid trade dates") from exc
        if not decision_day < buy_day <= sell_day:
            raise ValueError("Trade must execute after decision date")
        trade_id = fill.get("trade_id")
        if not isinstance(trade_id, str) or not trade_id.strip() or trade_id in seen_ids:
            raise ValueError("Missing or duplicate historical trade ID")
        seen_ids.add(trade_id)
        if fill["decision_date"] not in snapshots or ticker not in snapshots[fill["decision_date"]]["selected"]:
            raise ValueError("Trade was not in reconstructed point-in-time selection")
        trades.append({k: fill[k] for k in ("trade_id", "buy_price", "sell_price",
                                            "shares", "initial_risk_rupiah")})
        trades[-1]["is_oos"] = True
    result = net_trade_evidence(
        trades, buy_fee_rate=buy_fee_rate, sell_fee_rate=sell_fee_rate,
        buy_slippage_rate=buy_slippage_rate, sell_slippage_rate=sell_slippage_rate,
        assumption_source=assumption_source)
    return {
        "status": "RECONSTRUCTED_RESEARCH_ONLY",
        "provenance": provenance.strip(),
        "decision_dates": len(dates),
        "history_start": dates[0],
        "history_end": dates[-1],
        "five_year_coverage_verified": False,
        "five_year_coverage_reason": "INSUFFICIENT_INDEPENDENT_HISTORICAL_EVIDENCE",
        "trade_count": result["trade_count"],
        "net_trades": result["trades"],
        "assumption_source": result["assumption_source"],
        "reconstructed_oos": True,
        "actual_production_oos": False,
        "oos_certified": False,
        "buy_authorized": False,
        "incomplete_selection_dates": [d for d, s in snapshots.items()
                                        if not s["selection_complete"]],
    }
