"""G2 read-only production Top 5 research evidence. No BUY authorization."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from hanz_app.research.generate_top5_5y_backtest import _get_monitor_rows
from hanz_app.research.g2_monitor_adapter import select_monitor_top_five

OUT = Path("docs/dashboard/swing/g2-top5-research.json")


def build_report(rows, *, as_of, generated_at):
    result = select_monitor_top_five(rows, as_of=as_of)
    result["generated_at"] = generated_at
    result["status"] = "RESEARCH_ONLY_NOT_CERTIFIED"
    result["production_data_retrieved"] = True
    return result


def main():
    now = datetime.now(timezone.utc)
    rows = _get_monitor_rows()  # real Supabase REST; fail closed on network/auth errors
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("No real production monitor rows; refusing empty evidence")
    # UTC cutoff avoids selecting future rows; date-based selection remains research-only.
    result = build_report(rows, as_of=now.date().isoformat(),
                          generated_at=now.isoformat())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
