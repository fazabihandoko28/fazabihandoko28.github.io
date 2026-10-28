import unittest
import io
import json
from urllib.error import HTTPError
from unittest.mock import Mock
from datetime import datetime, timedelta, timezone

import pandas as pd

from hanz_app.research.g1_fast_recovery import evaluate_bars, validated_bar, recover_missing_five_minute_bars, recover_missing_direct_chart, _latest_direct_chart_bar, live_session_exit_code


class G1IndependentFastRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 27, 3, 30, tzinfo=timezone.utc)
        self.symbols = [f"T{i:03d}" for i in range(198)]
        self.fresh = self.now - timedelta(minutes=2)

    def test_190_genuine_fresh_bars_are_live(self):
        bars = {s: self.fresh for s in self.symbols[:190]}
        result = evaluate_bars(self.symbols, bars, self.now)
        self.assertEqual(result["status"], "LIVE")
        self.assertEqual(result["fresh_valid_count"], 190)
        self.assertFalse(result["g1_closed"])
        self.assertFalse(result["g0_touched"])

    def test_189_fresh_bars_are_stale(self):
        bars = {s: self.fresh for s in self.symbols[:189]}
        self.assertEqual(evaluate_bars(self.symbols, bars, self.now)["status"], "STALE")

    def test_stale_bars_do_not_count_as_fresh(self):
        bars = {s: self.now - timedelta(hours=2) for s in self.symbols}
        self.assertEqual(evaluate_bars(self.symbols, bars, self.now)["fresh_valid_count"], 0)

    def test_future_bars_do_not_count(self):
        bars = {s: self.now + timedelta(seconds=1) for s in self.symbols}
        self.assertEqual(evaluate_bars(self.symbols, bars, self.now)["status"], "STALE")

    def test_wrong_universe_size_fails_closed(self):
        bars = {s: self.fresh for s in self.symbols}
        self.assertEqual(evaluate_bars(self.symbols[:190], bars, self.now)["status"], "STALE")

    def test_closed_session_never_live(self):
        sunday = datetime(2026, 10, 25, 3, 30, tzinfo=timezone.utc)
        bars = {s: sunday - timedelta(minutes=2) for s in self.symbols}
        self.assertEqual(evaluate_bars(self.symbols, bars, sunday)["status"], "STALE")

    def test_last_bar_ohlcv_is_validated(self):
        frame = pd.DataFrame([{"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10}], index=pd.DatetimeIndex([self.fresh]))
        self.assertEqual(validated_bar(frame), self.fresh)
        frame.loc[self.fresh, "High"] = 99
        self.assertIsNone(validated_bar(frame))

    def test_naive_and_missing_volume_rejected(self):
        frame = pd.DataFrame([{"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10}], index=pd.DatetimeIndex([self.fresh.replace(tzinfo=None)]))
        self.assertIsNone(validated_bar(frame))
        frame.index = pd.DatetimeIndex([self.fresh])
        frame.drop(columns=["Volume"], inplace=True)
        self.assertIsNone(validated_bar(frame))


    def test_invalid_tail_keeps_genuine_prior_timestamp(self):
        previous = self.now - timedelta(minutes=2)
        frame = pd.DataFrame([
            {"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10},
            {"Open": 100, "High": 99, "Low": 98, "Close": 103, "Volume": 10},
        ], index=pd.DatetimeIndex([previous, self.now - timedelta(minutes=1)]))
        self.assertEqual(validated_bar(frame), previous)

    def test_non_numeric_tail_does_not_hide_valid_prior(self):
        previous = self.now - timedelta(minutes=2)
        frame = pd.DataFrame([
            {"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10},
            {"Open": "invalid", "High": 105, "Low": 98, "Close": 103, "Volume": 10},
        ], index=pd.DatetimeIndex([previous, self.now - timedelta(minutes=1)]))
        self.assertEqual(validated_bar(frame), previous)

    def test_invalid_tail_cannot_make_old_prior_bar_live(self):
        stale = self.now - timedelta(hours=2)
        frame = pd.DataFrame([
            {"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10},
            {"Open": 100, "High": 99, "Low": 98, "Close": 103, "Volume": 10},
        ], index=pd.DatetimeIndex([stale, self.now - timedelta(minutes=1)]))
        stamp = validated_bar(frame)
        self.assertEqual(stamp, stale)
        bars = {s: self.fresh for s in self.symbols[:189]}
        bars[self.symbols[189]] = stamp
        self.assertEqual(evaluate_bars(self.symbols, bars, self.now)["status"], "STALE")

    def test_out_of_order_rows_select_newest_valid_timestamp(self):
        # A provider can return an older valid row after a fresh one.
        # The previous implementation picked the last valid row by position.
        stale = self.now - timedelta(hours=2)
        fresh = self.now - timedelta(minutes=2)
        row = {"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10}
        frame = pd.DataFrame([row, row], index=pd.DatetimeIndex([fresh, stale]))
        self.assertEqual(validated_bar(frame), fresh)

    def test_out_of_order_invalid_newest_uses_actual_older_valid(self):
        stale = self.now - timedelta(hours=2)
        fresh = self.now - timedelta(minutes=2)
        valid = {"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10}
        invalid = dict(valid, Volume=0)
        frame = pd.DataFrame([invalid, valid], index=pd.DatetimeIndex([fresh, stale]))
        self.assertEqual(validated_bar(frame), stale)
        bars = {s: self.fresh for s in self.symbols[:189]}
        bars[self.symbols[189]] = validated_bar(frame)
        self.assertEqual(evaluate_bars(self.symbols, bars, self.now)["status"], "STALE")

    def test_boolean_ohlcv_cannot_certify_cached_candle(self):
        row = {"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10}
        frame = pd.DataFrame([row], index=pd.DatetimeIndex([self.fresh]))
        self.assertEqual(validated_bar(frame), self.fresh)
        for field in ("Open", "Volume"):
            malformed = dict(row, **{field: True})
            if field == "Open":
                malformed["Low"] = 1
            frame = pd.DataFrame([malformed], index=pd.DatetimeIndex([self.fresh]))
            self.assertIsNone(validated_bar(frame), field)

    def test_zero_volume_only_candle_cannot_certify_live(self):
        frame = pd.DataFrame(
            [{"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 0}],
            index=pd.DatetimeIndex([self.fresh]),
        )
        self.assertIsNone(validated_bar(frame))

    def test_zero_volume_tail_retains_prior_genuine_traded_bar(self):
        previous = self.now - timedelta(minutes=3)
        frame = pd.DataFrame([
            {"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10},
            {"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 0},
        ], index=pd.DatetimeIndex([previous, self.fresh]))
        self.assertEqual(validated_bar(frame), previous)

    def test_zero_volume_prior_does_not_rescue_invalid_tail(self):
        frame = pd.DataFrame([
            {"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 0},
            {"Open": 100, "High": 99, "Low": 98, "Close": 103, "Volume": 10},
        ], index=pd.DatetimeIndex([self.now - timedelta(minutes=3), self.fresh]))
        self.assertIsNone(validated_bar(frame))

    def test_5m_fallback_recovers_only_missing_1m_symbols(self):
        engine = Mock()
        frame = pd.DataFrame(
            [{"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10}],
            index=pd.DatetimeIndex([self.now - timedelta(minutes=5)]),
        )
        engine._cached_market_frame.side_effect = (
            lambda ticker, interval, period: {"frame": frame} if ticker == "B" else None
        )
        original = self.now - timedelta(minutes=1)
        bars = recover_missing_five_minute_bars(
            engine, ["A", "B", "C"], {"A": original}, now=self.now
        )
        self.assertEqual(bars, {"A": original, "B": self.now - timedelta(minutes=5)})
        engine.prefetch_market_data.assert_called_once_with(["B", "C"], "5m", "5d")

    def test_5m_fallback_does_not_refetch_when_complete(self):
        engine = Mock()
        bars = {"A": self.fresh}
        self.assertEqual(recover_missing_five_minute_bars(engine, ["A"], bars, now=self.now), bars)
        engine.prefetch_market_data.assert_not_called()

    def test_5m_fallback_rejects_invalid_ohlcv(self):
        engine = Mock()
        frame = pd.DataFrame(
            [{"Open": 100, "High": 99, "Low": 98, "Close": 103, "Volume": 10}],
            index=pd.DatetimeIndex([self.fresh]),
        )
        engine._cached_market_frame.return_value = {"frame": frame}
        self.assertEqual(recover_missing_five_minute_bars(engine, ["A"], {}), {})

    def test_5m_fallback_old_bar_stays_stale(self):
        engine = Mock()
        frame = pd.DataFrame(
            [{"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10}],
            index=pd.DatetimeIndex([self.now - timedelta(hours=2)]),
        )
        engine._cached_market_frame.return_value = {"frame": frame}
        bars = recover_missing_five_minute_bars(engine, self.symbols, {})
        self.assertEqual(evaluate_bars(self.symbols, bars, self.now)["status"], "STALE")


    def test_5m_fallback_replaces_future_dated_1m_with_fresh_bar(self):
        engine = Mock()
        frame = pd.DataFrame(
            [{"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10}],
            index=pd.DatetimeIndex([self.fresh]),
        )
        engine._cached_market_frame.return_value = {"frame": frame}
        future = self.now + timedelta(hours=1)
        bars = recover_missing_five_minute_bars(
            engine, ["A"], {"A": future}, now=self.now,
        )
        self.assertEqual(bars["A"], self.fresh)
        engine.prefetch_market_data.assert_called_once_with(["A"], "5m", "5d")

    def test_5m_fallback_retries_stale_but_valid_1m_bar(self):
        engine = Mock()
        old = self.now - timedelta(hours=2)
        fresh_5m = self.now - timedelta(minutes=5)
        frame = pd.DataFrame(
            [{"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10}],
            index=pd.DatetimeIndex([fresh_5m]),
        )
        engine._cached_market_frame.return_value = {"frame": frame}
        bars = recover_missing_five_minute_bars(
            engine, ["A"], {"A": old}, now=self.now
        )
        self.assertEqual(bars["A"], fresh_5m)
        engine.prefetch_market_data.assert_called_once_with(["A"], "5m", "5d")

    def test_5m_fallback_never_overwrites_newer_1m_with_older_5m(self):
        engine = Mock()
        old_1m = self.now - timedelta(hours=2)
        older_5m = old_1m - timedelta(minutes=5)
        frame = pd.DataFrame(
            [{"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10}],
            index=pd.DatetimeIndex([older_5m]),
        )
        engine._cached_market_frame.return_value = {"frame": frame}
        bars = recover_missing_five_minute_bars(
            engine, ["A"], {"A": old_1m}, now=self.now
        )
        self.assertEqual(bars["A"], old_1m)

    def test_5m_fallback_retries_out_of_session_1m_bar(self):
        engine = Mock()
        preopen = datetime(2026, 10, 27, 0, 30, tzinfo=timezone.utc)
        fresh_5m = self.now - timedelta(minutes=5)
        frame = pd.DataFrame(
            [{"Open": 100, "High": 105, "Low": 98, "Close": 103, "Volume": 10}],
            index=pd.DatetimeIndex([fresh_5m]),
        )
        engine._cached_market_frame.return_value = {"frame": frame}
        bars = recover_missing_five_minute_bars(
            engine, ["A"], {"A": preopen}, now=self.now
        )
        self.assertEqual(bars["A"], fresh_5m)

    def test_5m_fallback_rejects_naive_verification_time(self):
        with self.assertRaises(ValueError):
            recover_missing_five_minute_bars(
                Mock(), ["A"], {}, now=self.now.replace(tzinfo=None)
            )




class G1ClosedSessionProbeTests(unittest.TestCase):
    """The scheduled G1 probe must conserve provider quota outside IDX hours."""

    def fake_engine(self):
        engine = Mock()
        engine._CYCLE_MARKET_BARS = {}
        engine.fetch_scout_universe.return_value = [f"T{i:03d}" for i in range(198)]
        engine.fetch_watchlist.return_value = []
        engine.supabase_request.return_value = []
        engine.INTRADAY_INTERVAL = "1m"
        engine.INTRADAY_PERIOD = "5d"
        engine._cached_market_frame.return_value = None
        return engine

    def test_closed_session_skips_provider_and_remains_stale(self):
        import hanz_app
        from unittest.mock import patch
        from hanz_app.research.g1_fast_recovery import collect

        engine = self.fake_engine()
        engine.prefetch_market_data.side_effect = AssertionError(
            "Closed-session G1 probe must not request Yahoo candles"
        )
        with patch.object(hanz_app, "fast_trading_engine", engine, create=True), \
                patch("hanz_app.research.g1_fast_recovery.session_open", return_value=False):
            result = collect()
        self.assertEqual(result["status"], "STALE")
        self.assertEqual(result["universe_count"], 198)
        self.assertEqual(result["fresh_valid_count"], 0)
        engine.prefetch_market_data.assert_not_called()

    def test_open_session_still_attempts_real_provider_probe(self):
        import hanz_app
        from unittest.mock import patch
        from hanz_app.research.g1_fast_recovery import collect

        engine = self.fake_engine()
        with patch.object(hanz_app, "fast_trading_engine", engine, create=True), \
                patch("hanz_app.research.g1_fast_recovery.session_open", return_value=True), \
                patch("hanz_app.research.g1_fast_recovery.recover_missing_five_minute_bars"), \
                patch("hanz_app.research.g1_fast_recovery.recover_missing_direct_chart"):
            result = collect()
        engine.prefetch_market_data.assert_called_once()
        self.assertEqual(result["universe_count"], 198)
        self.assertEqual(result["fresh_valid_count"], 0)


    def test_open_session_initial_prefetch_error_still_retries_fallbacks(self):
        import hanz_app
        from unittest.mock import patch
        from hanz_app.research.g1_fast_recovery import collect

        engine = self.fake_engine()
        engine.prefetch_market_data.side_effect = OSError("1m provider unavailable")
        with patch.object(hanz_app, "fast_trading_engine", engine, create=True), \
                patch("hanz_app.research.g1_fast_recovery.session_open", return_value=True), \
                patch("hanz_app.research.g1_fast_recovery.recover_missing_with_fallbacks") as fallback:
            result = collect()
        fallback.assert_called_once()
        self.assertEqual(result["status"], "STALE")
        self.assertEqual(result["fresh_valid_count"], 0)
        self.assertEqual(result["direct_chart_attempts"]["one_minute_prefetch_error"], "OSError")


class G1DirectChartRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 27, 8, 10, tzinfo=timezone.utc)
        self.fresh = self.now - timedelta(minutes=2)
        self.old = self.now - timedelta(days=1)

    def payload(self, stamp=None, symbol="BBCA.JK", volume=100, high=105):
        return {"chart": {"result": [{
            "meta": {"symbol": symbol},
            "timestamp": [int((stamp or self.fresh).timestamp())],
            "indicators": {"quote": [{
                "open": [100], "high": [high], "low": [98],
                "close": [103], "volume": [volume],
            }]},
        }]}}

    def opener(self, payload):
        def open_response(request, timeout):
            self.assertTrue(request.full_url.startswith(
                "https://query2.finance.yahoo.com/v8/finance/chart/"
            ))
            self.assertEqual(timeout, 8)
            return io.BytesIO(json.dumps(payload).encode())
        return open_response

    def test_direct_real_candle_timestamp_recovers_missing(self):
        result = recover_missing_direct_chart(
            ["BBCA"], {}, now=self.now, opener=self.opener(self.payload())
        )
        self.assertEqual(result, {"BBCA": self.fresh})

    def test_direct_wrong_symbol_rejected(self):
        result = recover_missing_direct_chart(
            ["BBCA"], {}, now=self.now,
            opener=self.opener(self.payload(symbol="BBRI.JK")),
        )
        self.assertEqual(result, {})

    def test_direct_boolean_ohlcv_cannot_certify_live(self):
        self.assertEqual(
            _latest_direct_chart_bar(self.payload(), "BBCA", self.now), self.fresh
        )
        for field in ("open", "volume"):
            payload = self.payload()
            quote = payload["chart"]["result"][0]["indicators"]["quote"][0]
            quote[field] = [True]
            if field == "open":
                quote["low"] = [1]
            self.assertIsNone(
                _latest_direct_chart_bar(payload, "BBCA", self.now), field
            )

    def test_direct_zero_volume_rejected(self):
        self.assertEqual(recover_missing_direct_chart(
            ["BBCA"], {}, now=self.now,
            opener=self.opener(self.payload(volume=0)),
        ), {})

    def test_corrupt_timestamp_does_not_hide_other_genuine_candle(self):
        # A corrupt timestamp can coexist with a valid Yahoo OHLCV bar.
        # Previously fromtimestamp() aborted the entire payload, returning None.
        for invalid_first in (False, True):
            with self.subTest(invalid_first=invalid_first):
                payload = self.payload()
                result = payload["chart"]["result"][0]
                valid = result["timestamp"][0]
                result["timestamp"] = ([10**20, valid] if invalid_first
                                       else [valid, 10**20])
                quote = result["indicators"]["quote"][0]
                for field in ("open", "high", "low", "close", "volume"):
                    value = quote[field][0]
                    quote[field] = [value, value]
                self.assertEqual(
                    _latest_direct_chart_bar(payload, "BBCA", self.now),
                    self.fresh,
                )

    def test_direct_stale_candle_rejected(self):
        self.assertEqual(recover_missing_direct_chart(
            ["BBCA"], {}, now=self.now,
            opener=self.opener(self.payload(stamp=self.old)),
        ), {})

    def test_direct_invalid_ohlc_rejected(self):
        self.assertEqual(recover_missing_direct_chart(
            ["BBCA"], {}, now=self.now,
            opener=self.opener(self.payload(high=99)),
        ), {})

    def test_direct_closed_session_does_not_fetch(self):
        def forbidden(*args, **kwargs):
            self.fail("Closed session must not fetch")
        self.assertEqual(recover_missing_direct_chart(
            ["BBCA"], {},
            now=datetime(2026, 10, 25, 8, 10, tzinfo=timezone.utc),
            opener=forbidden,
        ), {})

    def test_direct_http_failure_stays_unverified(self):
        def failed(*args, **kwargs):
            raise OSError("HTTP 429")
        self.assertEqual(recover_missing_direct_chart(
            ["BBCA"], {}, now=self.now, opener=failed,
        ), {})

    def test_direct_fresh_1m_never_refetched(self):
        def forbidden(*args, **kwargs):
            self.fail("Fresh bar must not be fetched again")
        self.assertEqual(recover_missing_direct_chart(
            ["BBCA"], {"BBCA": self.fresh}, now=self.now, opener=forbidden,
        ), {"BBCA": self.fresh})

    def test_direct_replaces_future_dated_prior_with_genuine_fresh_bar(self):
        future = self.now + timedelta(hours=1)
        bars = recover_missing_direct_chart(
            ["BBCA"], {"BBCA": future}, now=self.now,
            opener=self.opener(self.payload()),
        )
        self.assertEqual(bars["BBCA"], self.fresh)

    def test_direct_future_prior_not_replaced_by_stale_candidate(self):
        future = self.now + timedelta(hours=1)
        bars = recover_missing_direct_chart(
            ["BBCA"], {"BBCA": future}, now=self.now,
            opener=self.opener(self.payload(stamp=self.old)),
        )
        self.assertEqual(bars["BBCA"], future)

    def test_direct_replaces_stale_with_genuine_newer(self):
        self.assertEqual(recover_missing_direct_chart(
            ["BBCA"], {"BBCA": self.old}, now=self.now,
            opener=self.opener(self.payload()),
        )["BBCA"], self.fresh)

    def test_direct_retry_budget_rotates_across_missing_symbols(self):
        # Previously every 30-minute probe retried the same first 3 symbols.
        # The remaining 7 could never receive direct-chart verification.
        symbols = [f"T{i:03d}" for i in range(10)]
        start = datetime(2026, 10, 27, 2, 0, tzinfo=timezone.utc)
        seen = set()
        for slot in range(4):
            calls = []
            def failed(request, timeout):
                calls.append(request.full_url.split("/chart/")[1].split(".JK")[0])
                raise OSError("provider unavailable")
            diagnostics = {}
            result = recover_missing_direct_chart(
                symbols, {}, now=start + timedelta(minutes=30 * slot),
                opener=failed, max_requests=3, diagnostics=diagnostics,
            )
            self.assertEqual(result, {})
            self.assertEqual(len(calls), 3)
            self.assertEqual(
                {s for s, reason in diagnostics.items()
                 if reason == "provider_request_or_response_error"}, set(calls)
            )
            self.assertEqual(
                sum(reason == "request_budget_exhausted"
                    for reason in diagnostics.values()), 7
            )
            seen.update(calls)
        self.assertEqual(seen, set(symbols))

    def test_direct_retry_budget_is_stable_within_same_slot(self):
        symbols = [f"T{i:03d}" for i in range(10)]
        start = datetime(2026, 10, 27, 2, 0, tzinfo=timezone.utc)
        attempts = []
        for minute in (0, 10):
            calls = []
            def failed(request, timeout):
                calls.append(request.full_url)
                raise OSError("provider unavailable")
            recover_missing_direct_chart(
                symbols, {}, now=start + timedelta(minutes=minute),
                opener=failed, max_requests=3,
            )
            attempts.append(calls)
        self.assertEqual(attempts[0], attempts[1])

    def test_direct_request_limit_prevents_provider_hammering(self):
        requests = []
        def failed(request, timeout):
            requests.append(request.full_url)
            raise OSError("provider unavailable")
        recover_missing_direct_chart(
            ["BBCA", "BBRI", "BMRI"], {}, now=self.now,
            opener=failed, max_requests=2,
        )
        self.assertEqual(len(requests), 2)

    def test_direct_invalid_symbol_not_sent_to_provider(self):
        requests = []
        def failed(request, timeout):
            requests.append(request.full_url)
            raise OSError("provider unavailable")
        recover_missing_direct_chart(
            ["../", "BBCA"], {}, now=self.now, opener=failed,
        )
        self.assertEqual(len(requests), 1)

    def test_direct_rejects_short_price_array_without_timestamp_misalignment(self):
        payload = self.payload()
        row = payload["chart"]["result"][0]
        row["timestamp"].append(int((self.fresh - timedelta(minutes=1)).timestamp()))
        # Before the fix, zip silently accepted the first row and returned LIVE.
        self.assertIsNone(_latest_direct_chart_bar(payload, "BBCA", self.now))
        self.assertEqual(recover_missing_direct_chart(
            ["BBCA"], {}, now=self.now, opener=self.opener(payload),
        ), {})

    def test_direct_rejects_extra_volume_entry(self):
        payload = self.payload()
        payload["chart"]["result"][0]["indicators"]["quote"][0]["volume"].append(999)
        self.assertIsNone(_latest_direct_chart_bar(payload, "BBCA", self.now))

    def test_direct_out_of_order_rows_use_newest_valid_timestamp(self):
        payload = self.payload()
        row = payload["chart"]["result"][0]
        row["timestamp"] = [int(self.fresh.timestamp()), int(self.old.timestamp())]
        for key in ("open", "high", "low", "close", "volume"):
            row["indicators"]["quote"][0][key] *= 2
        self.assertEqual(
            _latest_direct_chart_bar(payload, "BBCA", self.now), self.fresh
        )


    def test_direct_records_http_429_per_ticker_without_fabricating_bar(self):
        diagnostics = {}
        def rate_limited(*args, **kwargs):
            raise HTTPError("https://example.test", 429, "rate limited", None, None)
        result = recover_missing_direct_chart(
            ["ADCP"], {}, now=self.now, opener=rate_limited, diagnostics=diagnostics
        )
        self.assertEqual(result, {})
        self.assertEqual(diagnostics, {"ADCP": "http_429"})

    def test_direct_records_invalid_provider_response(self):
        diagnostics = {}
        def bad_json(*args, **kwargs):
            return io.BytesIO(b"not-json")
        self.assertEqual(recover_missing_direct_chart(
            ["BBCA"], {}, now=self.now, opener=bad_json, diagnostics=diagnostics
        ), {})
        self.assertEqual(diagnostics, {"BBCA": "provider_request_or_response_error"})

    def test_direct_records_no_fresh_valid_candle(self):
        diagnostics = {}
        recover_missing_direct_chart(
            ["BBCA"], {}, now=self.now, opener=self.opener(self.payload(stamp=self.old)),
            diagnostics=diagnostics,
        )
        self.assertEqual(diagnostics, {"BBCA": "no_fresh_valid_bar"})

    def test_direct_records_real_fresh_bar_only_after_validation(self):
        diagnostics = {}
        result = recover_missing_direct_chart(
            ["BBCA"], {}, now=self.now, opener=self.opener(self.payload()),
            diagnostics=diagnostics,
        )
        self.assertEqual(result, {"BBCA": self.fresh})
        self.assertEqual(diagnostics, {"BBCA": "fresh_verified"})

    def test_direct_records_request_budget_exhaustion_without_fetch(self):
        diagnostics = {}
        def forbidden(*args, **kwargs):
            self.fail("No request permitted when budget is zero")
        self.assertEqual(recover_missing_direct_chart(
            ["BBCA", "BBRI"], {}, now=self.now, opener=forbidden,
            max_requests=0, diagnostics=diagnostics,
        ), {})
        self.assertEqual(diagnostics, {
            "BBCA": "request_budget_exhausted",
            "BBRI": "request_budget_exhausted",
        })




class G1IndependentLiveSessionGateTests(unittest.TestCase):
    def setUp(self):
        self.good = {
            "idx_session_open": True, "status": "LIVE",
            "fresh_valid_count": 190, "universe_count": 198,
        }

    def test_genuine_190_of_198_passes(self):
        self.assertEqual(live_session_exit_code(self.good, True), 0)

    def test_189_of_198_fails(self):
        row = {**self.good, "status": "STALE", "fresh_valid_count": 189}
        self.assertEqual(live_session_exit_code(row, True), 2)

    def test_stale_status_cannot_pass_with_190(self):
        self.assertEqual(live_session_exit_code({**self.good, "status": "STALE"}, True), 2)

    def test_wrong_universe_size_fails(self):
        self.assertEqual(live_session_exit_code({**self.good, "universe_count": 197}, True), 2)

    def test_false_live_count_fails(self):
        self.assertEqual(live_session_exit_code({**self.good, "fresh_valid_count": 0}, True), 2)

    def test_closed_session_does_not_fail_ci(self):
        row = {**self.good, "idx_session_open": False, "status": "STALE"}
        self.assertEqual(live_session_exit_code(row, True), 0)

    def test_opt_in_gate_is_nonblocking_by_default(self):
        self.assertEqual(live_session_exit_code({**self.good, "status": "STALE"}, False), 0)

    def test_missing_evidence_fails_during_open_session(self):
        self.assertEqual(live_session_exit_code({"idx_session_open": True}, True), 2)


if __name__ == "__main__":
    unittest.main()
