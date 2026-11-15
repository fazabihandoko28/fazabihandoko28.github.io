"""G1-only execution cost model. Rates are assumptions, not broker quotes."""
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class ExecutionCosts:
    buy_fee_rate: float
    sell_fee_rate: float
    buy_slippage_rate: float
    sell_slippage_rate: float

    def __post_init__(self):
        for field in ("buy_fee_rate", "sell_fee_rate", "buy_slippage_rate", "sell_slippage_rate"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value < 1:
                raise ValueError(f"Invalid execution cost assumption: {field}")

def reconcile_long_trade(buy_price, sell_price, shares, initial_risk_rupiah, costs):
    """Long round trip: adverse fills, fees on filled notional, net cash and R."""
    if not isinstance(costs, ExecutionCosts):
        raise TypeError("costs must be ExecutionCosts")
    for name, value in (("buy_price", buy_price), ("sell_price", sell_price), ("shares", shares), ("initial_risk_rupiah", initial_risk_rupiah)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"Invalid trade input: {name}")
    if int(shares) != shares:
        raise ValueError("shares must be a whole number")
    gross = (sell_price - buy_price) * shares
    buy_fill = buy_price * (1 + costs.buy_slippage_rate)
    sell_fill = sell_price * (1 - costs.sell_slippage_rate)
    fee = buy_fill * shares * costs.buy_fee_rate + sell_fill * shares * costs.sell_fee_rate
    slippage = ((buy_fill - buy_price) + (sell_price - sell_fill)) * shares
    net = (sell_fill - buy_fill) * shares - fee
    if not all(math.isfinite(v) for v in (gross, fee, slippage, net)):
        raise ValueError("Nonfinite execution cost result")
    if not math.isclose(net, gross - fee - slippage, rel_tol=1e-10, abs_tol=1e-6):
        raise ValueError("Execution cost reconciliation failed")
    return {"gross_r_multiple": gross / initial_risk_rupiah, "fee_r": fee / initial_risk_rupiah, "slippage_r": slippage / initial_risk_rupiah, "r_multiple": net / initial_risk_rupiah, "gross_rupiah": gross, "fee_rupiah": fee, "slippage_rupiah": slippage, "net_rupiah": net}
