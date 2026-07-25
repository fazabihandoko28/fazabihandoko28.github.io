import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from hanz_core import Evidence, Signal, decide_entry

sample = [
    Evidence("data_freshness", Signal.POSITIVE, "licensed_feed", "2026-07-25T10:00:00Z", True),
    Evidence("liquidity", Signal.POSITIVE, "licensed_feed", "2026-07-25T10:00:00Z", True),
    Evidence("spread", Signal.POSITIVE, "licensed_feed", "2026-07-25T10:00:00Z"),
    Evidence("market_regime", Signal.NEUTRAL, "regime_engine", "2026-07-25T10:00:00Z"),
    Evidence("price_structure", Signal.POSITIVE, "price_engine", "2026-07-25T10:00:00Z"),
    Evidence("volume_confirmation", Signal.POSITIVE, "volume_engine", "2026-07-25T10:00:00Z"),
    Evidence("resistance", Signal.NEUTRAL, "resistance_engine", "2026-07-25T10:00:00Z"),
    Evidence("risk_reward", Signal.POSITIVE, "risk_engine", "2026-07-25T10:00:00Z", True),
    Evidence("historical_behaviour", Signal.POSITIVE, "history_engine", "2026-07-25T10:00:00Z"),
]

print(decide_entry(sample))
