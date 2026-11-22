"""G2 read-only production Top 5 research evidence. No BUY authorization."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from hanz_app.research.generate_top5_5y_backtest import _get_monitor_rows
from hanz_app.research.g2_monitor_adapter import _parse_timestamp, _cutoff
from hanz_app.research.g2_monitor_adapter import select_monitor_top_five

OUT = Path("docs/dashboard/swing/g2-top5-research.json")


def _candidate_exclusion_diagnostics(rows, *, as_of):
    """Aggregate latest per-ticker production risk reasons, never relax BUY gates."""
    from hanz_app.research.generate_top5_5y_backtest import _eligible, _rank, _zero_volume_days20, _num
    cutoff, _ = _cutoff(as_of)
    latest = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        stamp = _parse_timestamp(row.get("updated_at"))
        if not ticker or stamp is None or stamp > cutoff:
            continue
        if ticker not in latest or stamp > latest[ticker][0]:
            latest[ticker] = (stamp, [row])
        elif stamp == latest[ticker][0]:
            latest[ticker][1].append(row)
    # Market-regime diagnostics must not silently pick an arbitrary tied row.
    # Report snapshot age separately: old RED classifications are not proof
    # that the latest completed IDX session was RED.
    regimes, regime_reasons, age_buckets = {}, {}, {}
    for stamp, tied in latest.values():
        observations = set()
        for row in tied:
            r = row.get("risk_validation")
            if isinstance(r, dict):
                observations.add((
                    str(r.get("market_regime") or "UNKNOWN").strip().upper(),
                    str(r.get("market_reason") or "UNAVAILABLE").strip(),
                ))
            else:
                observations.add(("MALFORMED", "UNAVAILABLE"))
        regime, explanation = next(iter(observations)) if len(observations) == 1 else ("CONFLICTING_NEWEST_SNAPSHOT", "UNAVAILABLE")
        regimes[regime] = regimes.get(regime, 0) + 1
        if regime == "RED":
            regime_reasons[explanation] = regime_reasons.get(explanation, 0) + 1
        age_hours = (cutoff - stamp).total_seconds() / 3600
        bucket = "WITHIN_24H" if age_hours <= 24 else "24_TO_72H" if age_hours <= 72 else "OLDER_THAN_72H"
        age_buckets[bucket] = age_buckets.get(bucket, 0) + 1
    reasons = {}
    for _, tied in latest.values():
        signatures = []
        for row in tied:
            try:
                risk = row.get("risk_validation")
                regime_signature = ((str(risk.get("market_regime") or "UNKNOWN").strip().upper(),
                                     str(risk.get("market_reason") or "UNAVAILABLE").strip())
                                    if isinstance(risk, dict) else ("MALFORMED", "UNAVAILABLE"))
                signatures.append((bool(_eligible(row)), _rank(row), regime_signature))
            except (TypeError, ValueError, KeyError, AttributeError, OverflowError):
                signatures.append((False, None))
        if len(set(signatures)) > 1:
            reason = "CONFLICTING_NEWEST_SNAPSHOT"
        elif signatures[0][0]:
            reason = "ELIGIBLE"
        else:
            r = tied[0].get("risk_validation")
            if not isinstance(r, dict):
                reason = "MALFORMED_RISK_VALIDATION"
            elif str(r.get("hanz_action") or tied[0].get("hanz_action") or "").upper() in {"AVOID", "DO_NOT_CHASE"}:
                reason = "ACTION_RESTRICTED"
            elif r.get("top5_excluded") or (isinstance(r.get("momentum_guard"), dict) and r["momentum_guard"].get("blocked")):
                reason = "RISK_OR_MOMENTUM_BLOCK"
            elif str(r.get("volatility_status") or "").upper() == "EXTREME":
                reason = "EXTREME_VOLATILITY"
            elif _zero_volume_days20(r) is None or _zero_volume_days20(r) >= 5:
                reason = "ZERO_VOLUME_GUARD"
            elif _num(r.get("avg_value20")) is None or _num(r.get("avg_value20")) < 100_000_000:
                reason = "LIQUIDITY_OR_MISSING_VALUE"
            else:
                reason = "OTHER_ELIGIBILITY_OR_RANK_GUARD"
        reasons[reason] = reasons.get(reason, 0) + 1
    return {"latest_unique_tickers_at_cutoff": len(latest),
            "exclusion_reason_counts": dict(sorted(reasons.items())),
            "market_regime_counts": dict(sorted(regimes.items())),
            "red_market_reason_counts": dict(sorted(regime_reasons.items())),
            "snapshot_age_bucket_counts": dict(sorted(age_buckets.items())),
            "diagnostics_research_only": True}


def build_report(rows, *, as_of, generated_at):
    result = select_monitor_top_five(rows, as_of=as_of)
    # Timestamp diagnostics are evidence, not a claim of market-data freshness.
    stamps = [_parse_timestamp(row.get("updated_at")) for row in rows if isinstance(row, dict)]
    valid_stamps = sorted(dt for dt in stamps if dt is not None)
    result["source_latest_updated_at"] = valid_stamps[-1].isoformat() if valid_stamps else None
    result["source_oldest_updated_at"] = valid_stamps[0].isoformat() if valid_stamps else None
    result["source_rows_without_valid_timestamp"] = len(stamps) - len(valid_stamps)
    # Match adapter semantics: date-only cutoff means end of that UTC day;
    # intraday cutoffs must still be timezone-aware.
    cutoff, _ = _cutoff(as_of)
    eligible_stamps = [dt for dt in valid_stamps if dt <= cutoff]
    newest = eligible_stamps[-1] if eligible_stamps else None
    result["source_latest_at_cutoff"] = newest.isoformat() if newest else None
    result["source_age_hours"] = round((cutoff - newest).total_seconds() / 3600, 2) if newest else None
    result["source_future_timestamp_count"] = sum(dt > cutoff for dt in valid_stamps)
    result["source_timestamp_coverage_complete"] = len(valid_stamps) == len(stamps)
    result["market_session_freshness_verified"] = False
    result["production_top5_complete"] = result["selection_complete"]
    # Read-only counterfactual: remove leader from the same production snapshot.
    # This does not change LIVE selection, authorization, or trading.
    leader = result["selected"][0] if result["selected"] else None
    probe = {"removed_ticker": leader, "replacement_ticker": None,
             "verified": False, "reason": "NO_ELIGIBLE_LEADER" if leader is None else "NO_ELIGIBLE_REPLACEMENT"}
    if leader is not None:
        reduced = [row for row in rows if not (
            isinstance(row, dict) and str(row.get("ticker") or "").strip().upper() == leader
        )]
        reranked = select_monitor_top_five(reduced, as_of=as_of)
        entrants = [ticker for ticker in reranked["selected"] if ticker not in result["selected"]]
        if entrants:
            probe.update({"replacement_ticker": entrants[0], "verified": True,
                          "reason": "COUNTERFACTUAL_REPLACEMENT_FROM_SAME_SNAPSHOT"})
    result["replacement_probe"] = probe
    result["candidate_replacement_evidence"] = (
        "COUNTERFACTUAL_REPLACEMENT_VERIFIED" if probe["verified"]
        else "INSUFFICIENT_ELIGIBLE_CANDIDATES" if leader is None
        else "NO_ELIGIBLE_REPLACEMENT_IN_SNAPSHOT"
    )
    result["generated_at"] = generated_at
    result["status"] = "RESEARCH_ONLY_NOT_CERTIFIED"
    # Explicit negative authorization evidence: this module is read-only research.
    result["buy_authorized"] = False
    result["production_data_retrieved"] = True
    result["production_evidence_usable"] = bool(newest and len(valid_stamps) == len(stamps)
                                                  and not result["source_future_timestamp_count"])
    result["production_evidence_limitation"] = (
        "MISSING_OR_FUTURE_MONITOR_TIMESTAMPS" if not result["production_evidence_usable"]
        else "EXCHANGE_SESSION_FRESHNESS_NOT_INDEPENDENTLY_VERIFIED"
    )
    result["production_exclusion_diagnostics"] = _candidate_exclusion_diagnostics(rows, as_of=as_of)
    result["production_monitor_rows"] = len(rows)
    result["production_unique_tickers"] = len({str(r.get("ticker") or "").strip().upper() for r in rows if isinstance(r, dict) and r.get("ticker")})
    result["eligible_selected_count"] = len(result["selected"])
    result["candidate_shortfall"] = result["vacant_slots"]
    result["candidate_shortfall_reason"] = ("INSUFFICIENT_ELIGIBLE_PRODUCTION_SIGNALS" if result["vacant_slots"] else None)
    result["backtest_5y_certified"] = False
    result["historical_point_in_time_oos_verified"] = False
    return result


def main():
    now = datetime.now(timezone.utc)
    rows = _get_monitor_rows()  # real Supabase REST; fail closed on network/auth errors
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("No real production monitor rows; refusing empty evidence")
    # Precise UTC cutoff rejects future intraday snapshots; research only.
    result = build_report(rows, as_of=now.isoformat(),
                          generated_at=now.isoformat())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
