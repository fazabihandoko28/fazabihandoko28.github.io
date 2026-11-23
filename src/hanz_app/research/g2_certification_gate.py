"""Fail-closed G2 certification gate for research artifacts; never enables BUY."""
from __future__ import annotations

import json
from pathlib import Path

REQUIRED = (
    "production_top5_complete",
    "market_session_freshness_verified",
    "historical_point_in_time_oos_verified",
    "net_after_costs_verified",
    "fast_live_190_of_198_verified",
    "integration_regression_verified",
    "risk_safety_verified",
)

def evaluate(evidence):
    """Require explicit booleans; missing, string or numeric claims are not PASS."""
    if not isinstance(evidence, dict):
        raise ValueError("G2 evidence must be a JSON object")
    gates = {key: evidence.get(key) is True for key in REQUIRED}
    # Require evidence for every selected ticker, not merely the first probe.
    selected = evidence.get("selected")
    probes = evidence.get("replacement_probes")
    valid_probes = (
        isinstance(selected, list) and len(selected) == 5
        and isinstance(probes, list) and len(probes) == len(selected)
        and all(
            isinstance(p, dict)
            and p.get("verified") is True
            and p.get("removed_ticker") == ticker
            and isinstance(p.get("replacement_ticker"), str)
            and bool(p["replacement_ticker"].strip())
            and p["replacement_ticker"] not in selected
            and p.get("reason") == "COUNTERFACTUAL_REPLACEMENT_FROM_SAME_SNAPSHOT"
            for ticker, p in zip(selected, probes)
        )
        and evidence.get("replacement_verified_count") == len(selected)
        and evidence.get("replacement_probes_complete") is True
    )
    gates["candidate_replacement_verified"] = valid_probes
    selected = evidence.get("selected")
    gates["five_distinct_selected"] = (
        isinstance(selected, list) and len(selected) == 5
        and all(isinstance(t, str) and t.strip() for t in selected)
        and len(set(selected)) == 5
    )
    gates["no_buy_authorization"] = evidence.get("buy_authorized") is False
    return {"certified": all(gates.values()), "gates": gates,
            "missing": [k for k, passed in gates.items() if not passed]}

def main():
    source = Path("docs/dashboard/swing/g2-top5-research.json")
    if not source.is_file():
        print(json.dumps({"certified": False, "missing": ["PRODUCTION_ARTIFACT_MISSING"]}))
        return
    report = evaluate(json.loads(source.read_text(encoding="utf-8")))
    print(json.dumps(report, indent=2, sort_keys=True))
    # This is an evidence reporter: OPEN is not a test failure.
    # A separate approval process must never infer BUY from its output.

if __name__ == "__main__":
    main()
