"""G1 regression: overlapping OOS windows cannot certify independent WFA."""
import unittest
import pandas as pd
from hanz_app.research.hanz_walk_forward_evidence_validator import _oos_windows_contiguous


class G1OverlappingOOSWindowsTests(unittest.TestCase):
    def windows(self, starts, ends):
        return pd.DataFrame({"oos_start": starts, "oos_end": ends})

    def test_distinct_windows_remain_valid(self):
        self.assertTrue(_oos_windows_contiguous(self.windows(
            ["2020-01-01", "2023-01-01"], ["2022-12-31", "2025-12-31"])))

    def test_same_day_boundary_remains_supported(self):
        self.assertTrue(_oos_windows_contiguous(self.windows(
            ["2020-01-01", "2023-01-01"], ["2023-01-01", "2026-01-01"])))

    def test_overlapping_oos_windows_fail_closed(self):
        self.assertFalse(_oos_windows_contiguous(self.windows(
            ["2020-01-01", "2022-01-01"], ["2023-12-31", "2026-01-01"])))

    def test_identical_oos_windows_fail_closed(self):
        self.assertFalse(_oos_windows_contiguous(self.windows(
            ["2020-01-01", "2020-01-01"], ["2026-01-01", "2026-01-01"])))

    def test_existing_fourteen_day_gap_policy_preserved(self):
        self.assertTrue(_oos_windows_contiguous(self.windows(
            ["2020-01-01", "2023-01-15"], ["2023-01-01", "2026-01-01"])))
        self.assertFalse(_oos_windows_contiguous(self.windows(
            ["2020-01-01", "2023-01-16"], ["2023-01-01", "2026-01-01"])))


    def test_same_day_intraday_overlap_fails_closed(self):
        # Date normalization previously hid overlapping hours within one day.
        self.assertFalse(_oos_windows_contiguous(self.windows(
            ["2020-01-01T09:00:00Z", "2020-01-01T11:00:00Z"],
            ["2020-01-01T12:00:00Z", "2020-01-01T15:00:00Z"])))

    def test_same_day_exact_intraday_boundary_remains_supported(self):
        self.assertTrue(_oos_windows_contiguous(self.windows(
            ["2020-01-01T09:00:00Z", "2020-01-01T12:00:00Z"],
            ["2020-01-01T12:00:00Z", "2020-01-01T15:00:00Z"])))


    def test_exact_fourteen_day_intraday_gap_remains_supported(self):
        self.assertTrue(_oos_windows_contiguous(self.windows(
            ["2020-01-01T09:00:00Z", "2023-01-15T09:00:00Z"],
            ["2023-01-01T09:00:00Z", "2026-01-01T09:00:00Z"])))

    def test_fourteen_day_gap_plus_one_second_fails_closed(self):
        # timedelta.days truncates the fractional day and used to allow
        # an untested interval longer than the G1 fourteen-day ceiling.
        self.assertFalse(_oos_windows_contiguous(self.windows(
            ["2020-01-01T09:00:00Z", "2023-01-15T09:00:01Z"],
            ["2023-01-01T09:00:00Z", "2026-01-01T09:00:00Z"])))


if __name__ == "__main__":
    unittest.main()
