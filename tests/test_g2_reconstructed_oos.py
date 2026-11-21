import unittest
from hanz_app.research.g2_reconstructed_oos import reconstructed_oos

COSTS = dict(buy_fee_rate=0.0015, sell_fee_rate=0.0025,
             buy_slippage_rate=0.001, sell_slippage_rate=0.001,
             assumption_source="TEST_FIXTURE_ONLY", provenance="TEST_FIXTURE_ONLY")


def decision(ticker="ABCD", cutoff="2021-01-04"):
    return dict(ticker=ticker, snapshot_date="2021-01-04",
                evidence_cutoff=cutoff, eligible=True, rank_score=90)


def fill(ticker="ABCD", buy_date="2021-01-05"):
    return dict(trade_id="sample-1", ticker=ticker, decision_date="2021-01-04",
                buy_date=buy_date, sell_date="2021-02-01", buy_price=100,
                sell_price=110, shares=100, initial_risk_rupiah=1000)


class ReconstructedOosTests(unittest.TestCase):
    def test_net_replay_is_never_actual_oos(self):
        report = reconstructed_oos([decision()], [fill()], **COSTS)
        self.assertEqual(report["trade_count"], 1)
        self.assertTrue(report["reconstructed_oos"])
        self.assertFalse(report["actual_production_oos"])
        self.assertFalse(report["oos_certified"])
        self.assertFalse(report["buy_authorized"])
        self.assertFalse(report["five_year_coverage_verified"])
        self.assertEqual(report["history_start"], "2021-01-04")
        self.assertEqual(report["incomplete_selection_dates"], ["2021-01-04"])

    def test_future_evidence_rejected(self):
        with self.assertRaisesRegex(ValueError, "Look-ahead"):
            reconstructed_oos([decision(cutoff="2021-01-05")], [], **COSTS)

    def test_same_day_buy_rejected(self):
        with self.assertRaisesRegex(ValueError, "after decision"):
            reconstructed_oos([decision()], [fill(buy_date="2021-01-04")], **COSTS)

    def test_unselected_trade_rejected(self):
        with self.assertRaisesRegex(ValueError, "not in reconstructed"):
            reconstructed_oos([decision()], [fill(ticker="EFGH")], **COSTS)

    def test_duplicate_trade_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate historical trade ID"):
            reconstructed_oos([decision()], [fill(), fill()], **COSTS)

    def test_no_historical_data_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Historical dated decisions"):
            reconstructed_oos([], [], **COSTS)


if __name__ == "__main__":
    unittest.main()
