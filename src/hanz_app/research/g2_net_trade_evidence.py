"""G2 trade-level net-return reconciliation for independently sourced fills.

No default fee or slippage rates: caller must supply documented assumptions.
This is research evidence only, not an order executor or BUY gate.
"""
from __future__ import annotations

import math
from hanz_app.research.g1_execution_cost_model import ExecutionCosts, reconcile_long_trade


def net_trade_evidence(trades, *, buy_fee_rate, sell_fee_rate,
                       buy_slippage_rate, sell_slippage_rate, assumption_source):
    if not isinstance(assumption_source, str) or not assumption_source.strip():
        raise ValueError("Documented fee/slippage assumption source required")
    costs = ExecutionCosts(buy_fee_rate, sell_fee_rate,
                           buy_slippage_rate, sell_slippage_rate)
    results = []
    seen = set()
    for trade in trades:
        if not isinstance(trade, dict):
            raise ValueError("Invalid trade row")
        trade_id = trade.get("trade_id")
        if not isinstance(trade_id, str) or not trade_id.strip() or trade_id in seen:
            raise ValueError("Missing or duplicate trade_id")
        seen.add(trade_id)
        if trade.get("is_oos") is not True:
            raise ValueError("Only independently verified OOS trades permitted")
        computed = reconcile_long_trade(
            trade.get("buy_price"), trade.get("sell_price"),
            trade.get("shares"), trade.get("initial_risk_rupiah"), costs)
        if not all(math.isfinite(value) for value in computed.values()):
            raise ValueError("Nonfinite net trade result")
        results.append({"trade_id": trade_id, **computed})
    return {
        "trades": results,
        "trade_count": len(results),
        "assumption_source": assumption_source.strip(),
        "research_only": True,
        "buy_authorized": False,
        "oos_certified": False,
    }
