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
    replacement = evidence.get("replacement_probe")
    gates["candidate_replacement_verified"] = (
        isinstance(replacement, dict)
        and replacement.get("verified") is True
        and isinstance(replacement.get("removed_ticker"), str)
        and isinstance(replacement.get("replacement_ticker"), str)
        and isinstance(evidence.get("selected"), list)
        and replacement["removed_ticker"] in evidence["selected"]
        and replacement["replacement_ticker"].strip() != ""
        and replacement["replacement_ticker"] not in evidence["selected"]
        and replacement.get("reason") == "COUNTERFACTUAL_REPLACEMENT_FROM_SAME_SNAPSHOT"
    )
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
