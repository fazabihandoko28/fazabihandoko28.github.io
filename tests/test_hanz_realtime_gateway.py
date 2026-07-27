from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from hanz_realtime import (
    OpportunityQueue,
    PortfolioGuardian,
    PositionState,
    RealtimeGateway,
    SmartScheduler,
    Tick,
)


class RealtimeGatewayTests(unittest.TestCase):
    def tick(self, second, price, volume, bid=None, ask=None):
        return Tick(
            symbol="TINS",
            market="BEI",
            price=price,
            volume=volume,
            timestamp=datetime(2026, 7, 27, 9, 0, second, tzinfo=timezone.utc),
            bid=bid,
            ask=ask,
        )

    def test_tick_validation(self):
        gateway = RealtimeGateway()
        with self.assertRaises(ValueError):
            gateway.ingest(self.tick(0, -1, 100))

    def test_incremental_state_updates(self):
        gateway = RealtimeGateway()
        first = gateway.ingest(self.tick(0, 100, 1000))
        second = gateway.ingest(self.tick(1, 101, 1200))
        self.assertEqual(second.tick_count, 2)
        self.assertEqual(second.cumulative_volume, 1200)
        self.assertGreater(second.price_change_pct, 0)

    def test_anomaly_enters_queue(self):
        gateway = RealtimeGateway()
        gateway.ingest(self.tick(0, 100, 1000))
        gateway.ingest(self.tick(1, 100.5, 1100))
        gateway.ingest(self.tick(2, 106, 5000))
        ranked = gateway.queue.ranked()
        self.assertTrue(ranked)
        self.assertEqual(ranked[0].symbol, "TINS")

    def test_queue_keeps_highest_scores(self):
        queue = OpportunityQueue(max_size=2)
        now = datetime.now(timezone.utc)
        queue.upsert("A", "BEI", 50, "PANTAU", now)
        queue.upsert("B", "BEI", 80, "MENGUAT", now)
        queue.upsert("C", "BEI", 70, "MENGUAT", now)
        self.assertEqual([item.symbol for item in queue.ranked()], ["B", "C"])

    def test_scheduler_intervals(self):
        scheduler = SmartScheduler()
        now = datetime.now(timezone.utc)
        self.assertTrue(scheduler.due("fast", now))
        self.assertFalse(scheduler.due("fast", now))
        self.assertTrue(scheduler.due("fast", now + timedelta(seconds=1)))

    def test_guardian_triggers_sell_at_stop(self):
        guardian = PortfolioGuardian()
        guardian.add_position(PositionState(
            symbol="TINS",
            market="BEI",
            entry_price=100,
            quantity=10,
            stop_price=95,
            target_price=120,
        ))
        status = guardian.on_tick(self.tick(1, 94, 1000))
        self.assertEqual(status, "JUAL")

    def test_guardian_trailing_stop_moves_up(self):
        guardian = PortfolioGuardian()
        guardian.add_position(PositionState(
            symbol="TINS",
            market="BEI",
            entry_price=100,
            quantity=10,
            stop_price=90,
            trailing_pct=5,
        ))
        guardian.on_tick(self.tick(1, 120, 1000))
        position = guardian.positions[("BEI", "TINS")]
        self.assertEqual(position.stop_price, 114)


if __name__ == "__main__":
    unittest.main()
