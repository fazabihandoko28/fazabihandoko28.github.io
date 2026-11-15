"""G2 isolated selector regression tests."""
import unittest
from hanz_app.research.g2_candidate_replacement import select_top_five


def row(ticker, score, eligible=True, date="2026-11-12"):
    return {"ticker": ticker, "rank_score": score, "eligible": eligible,
            "snapshot_date": date}


class G2SelectionTests(unittest.TestCase):
    def test_replaces_four_ineligible(self):
        rows = [row("AAA", 99), row("BBB", 98, False), row("CCC", 97, False),
                row("DDD", 96, False), row("EEE", 95, False),
                row("FFF", 94), row("GGG", 93), row("HHH", 92), row("III", 91)]
        result = select_top_five(rows, as_of="2026-11-12")
        self.assertEqual(result["selected"], ["AAA", "FFF", "GGG", "HHH", "III"])
        self.assertTrue(result["selection_complete"])
        self.assertFalse(result["buy_authorized"])

    def test_no_forced_fill_or_oos_claim(self):
        result = select_top_five([row("AAA", 80)], as_of="2026-11-12")
        self.assertEqual(result["vacant_slots"], 4)
        self.assertFalse(result["selection_complete"])
        self.assertFalse(result["oos_certified"])

    def test_newest_snapshot_wins_future_ignored(self):
        rows = [row("AAA", 5, False), row("AAA", 99),
                row("BBB", 100, date="2026-11-13"), row("CCC", 70)]
        self.assertEqual(select_top_five(rows, as_of="2026-11-12")["selected"], ["CCC"])

    def test_invalid_scores_rejected(self):
        rows = [row("AAA", float("nan")), row("BBB", True),
                row("CCC", 101), row("DDD", 40)]
        self.assertEqual(select_top_five(rows, as_of="2026-11-12")["selected"], ["DDD"])

    def test_tie_break_and_normalization(self):
        rows = [row(" bbb ", 70), row("BBB", 90), row("AAA", 70)]
        self.assertEqual(select_top_five(rows, as_of="2026-11-12")["selected"], ["AAA", "BBB"])


if __name__ == "__main__":
    unittest.main()
