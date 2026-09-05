
import json
import math
# HANZ BOOK-ALIGNED DOCTRINE — V10.0
# Source hierarchy: market/trend -> structure/location -> setup/trigger -> volume -> risk.
# Adds explicit Pardo-style research validation gate before any real-money actionability.
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

# Firebase Admin is optional. Alerts continue writing to Supabase even
# when the GitHub Actions Firebase secret is not configured.
try:
    import firebase_admin
    from firebase_admin import credentials, messaging
except Exception:
    firebase_admin = None
    credentials = None
    messaging = None



# ============================================================
# HANZ SWING / WEEKLY TRADING ENGINE
# Separate from Fast Engine. Do NOT replace fast_trading_engine.py
# ============================================================

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")

SWING_INTERVAL = int(
    os.getenv("HANZ_SWING_INTERVAL", "1800")
)
RUN_ONCE = os.getenv(
    "HANZ_SWING_RUN_ONCE", "0"
) == "1"

DAILY_INTERVAL = os.getenv(
    "HANZ_SWING_DAILY_TIMEFRAME", "1d"
)
DAILY_PERIOD = os.getenv(
    "HANZ_SWING_DAILY_PERIOD", "1y"
)

WEEKLY_INTERVAL = os.getenv(
    "HANZ_SWING_WEEKLY_TIMEFRAME", "1wk"
)
WEEKLY_PERIOD = os.getenv(
    "HANZ_SWING_WEEKLY_PERIOD", "2y"
)

MIN_WATCH_SCORE = int(
    os.getenv("HANZ_SWING_MIN_WATCH_SCORE", "6")
)
MIN_CONFIRM_SCORE = int(
    os.getenv("HANZ_SWING_MIN_CONFIRM_SCORE", "7")
)
MIN_BUY_SCORE = int(
    os.getenv("HANZ_SWING_MIN_BUY_SCORE", "8")
)

# Pardo-style validation gate. Historical optimization alone is not enough.
# HANZ remains research/paper-only until walk-forward validation has been
# completed outside the live signal engine and these values are explicitly set.
STRATEGY_WFA_VALIDATED = os.getenv("HANZ_STRATEGY_WFA_VALIDATED", "0") == "1"
STRATEGY_WFE = safe_wfe_env = os.getenv("HANZ_STRATEGY_WFE", "").strip()
STRATEGY_OOS_TRADES = int(os.getenv("HANZ_STRATEGY_OOS_TRADES", "0") or 0)
STRATEGY_WF_WINDOWS = int(os.getenv("HANZ_STRATEGY_WF_WINDOWS", "0") or 0)
STRATEGY_OOS_EXPECTANCY_R = os.getenv("HANZ_STRATEGY_OOS_EXPECTANCY_R", "").strip()
STRATEGY_VALIDATED_AT = os.getenv("HANZ_STRATEGY_VALIDATED_AT", "").strip()
STRATEGY_DOF_REMAINING_PCT = os.getenv("HANZ_STRATEGY_DOF_REMAINING_PCT", "").strip()
STRATEGY_OOS_MAX_DD_R = os.getenv("HANZ_STRATEGY_OOS_MAX_DD_R", "").strip()
STRATEGY_PROFITABLE_WF_PCT = os.getenv("HANZ_STRATEGY_PROFITABLE_WF_PCT", "").strip()
STRATEGY_MAX_TRADE_PROFIT_SHARE_PCT = os.getenv("HANZ_STRATEGY_MAX_TRADE_PROFIT_SHARE_PCT", "").strip()
# HANZ implementation policies used to operationalize the supplied Pardo material.
# The book supports 30–50 trades as an adequate minimum and >=90% remaining DOF;
# exact WFE / profitable-window / concentration cutoffs remain configurable research policy.
MIN_WFA_OOS_TRADES = int(os.getenv("HANZ_MIN_WFA_OOS_TRADES", "30"))
MIN_DOF_REMAINING_PCT = float(os.getenv("HANZ_MIN_DOF_REMAINING_PCT", "90"))
MIN_WFE_RATIO = float(os.getenv("HANZ_MIN_WFE_RATIO", "0.50"))
MIN_PROFITABLE_WF_PCT = float(os.getenv("HANZ_MIN_PROFITABLE_WF_PCT", "50"))
MAX_SINGLE_TRADE_PROFIT_SHARE_PCT = float(os.getenv("HANZ_MAX_SINGLE_TRADE_PROFIT_SHARE_PCT", "35"))

# V6 EARLY SIGNAL + RECONFIRMATION
EARLY_WATCH_SCORE = int(os.getenv("HANZ_SWING_EARLY_WATCH_SCORE", "5"))
PRE_ALERT_SCORE = int(os.getenv("HANZ_SWING_PRE_ALERT_SCORE", "7"))
SETUP_READY_SCORE = int(os.getenv("HANZ_SWING_SETUP_READY_SCORE", "8"))
EARLY_BREAKOUT_DISTANCE_PCT = float(
    os.getenv("HANZ_SWING_EARLY_BREAKOUT_DISTANCE_PCT", "5.0")
)
SETUP_READY_BREAKOUT_DISTANCE_PCT = float(
    os.getenv("HANZ_SWING_SETUP_READY_BREAKOUT_DISTANCE_PCT", "2.0")
)

# V10.4 EARLY CONFIRMED BUY research hypotheses.
# These are explicit/testable parameters, not claims of validated IDX edge.
EARLY_SUPPORT_ATR = float(
    os.getenv("HANZ_EARLY_SUPPORT_ATR", "1.25")
)
EARLY_EMA20_MIN_SLOPE_5D_PCT = float(
    os.getenv("HANZ_EARLY_EMA20_MIN_SLOPE_5D_PCT", "-0.50")
)
EARLY_MAX_RET3_PCT = float(
    os.getenv("HANZ_EARLY_MAX_RET3_PCT", "5.0")
)
EARLY_MAX_RET5_PCT = float(
    os.getenv("HANZ_EARLY_MAX_RET5_PCT", "8.0")
)
EARLY_MAX_DOWN_VOLUME_RATIO_5D = float(
    os.getenv("HANZ_EARLY_MAX_DOWN_VOLUME_RATIO_5D", "1.25")
)
EARLY_MIN_CLOSE_LOCATION = float(
    os.getenv("HANZ_EARLY_MIN_CLOSE_LOCATION", "0.60")
)
EARLY_WEEKLY_EMA_TOLERANCE = float(
    os.getenv("HANZ_EARLY_WEEKLY_EMA_TOLERANCE", "0.97")
)

BUY_STATES = {"SWING_BUY", "EARLY_CONFIRMED_BUY"}

# V10.5 Foreign Flow Intelligence (research hypotheses; calibrate with IDX OOS/WFA)
FOREIGN_FLOW_ENABLED = os.getenv("HANZ_FOREIGN_FLOW_ENABLED", "1").strip() != "0"
FOREIGN_FLOW_LOOKBACK_DAYS = int(os.getenv("HANZ_FOREIGN_FLOW_LOOKBACK_DAYS", "5"))
FOREIGN_FLOW_STRONG_BUY_PCT = float(os.getenv("HANZ_FOREIGN_FLOW_STRONG_BUY_PCT", "1.0"))
FOREIGN_FLOW_STRONG_SELL_PCT = float(os.getenv("HANZ_FOREIGN_FLOW_STRONG_SELL_PCT", "-1.0"))
FOREIGN_FLOW_WARN_SELL_PCT = float(os.getenv("HANZ_FOREIGN_FLOW_WARN_SELL_PCT", "-0.35"))
FOREIGN_FLOW_CONFIRM_DAYS = int(os.getenv("HANZ_FOREIGN_FLOW_CONFIRM_DAYS", "2"))

# V10.6 Public Insider Disclosure Intelligence.
# ONLY public disclosures are eligible. Never use leaked/confidential/MNPI data.
INSIDER_DISCLOSURE_ENABLED = os.getenv("HANZ_INSIDER_DISCLOSURE_ENABLED", "1").strip() != "0"
INSIDER_LOOKBACK_DAYS = int(os.getenv("HANZ_INSIDER_LOOKBACK_DAYS", "90"))
INSIDER_RECENT_DAYS = int(os.getenv("HANZ_INSIDER_RECENT_DAYS", "30"))
INSIDER_MIN_VALUE_IDR = float(os.getenv("HANZ_INSIDER_MIN_VALUE_IDR", "100000000"))
INSIDER_REPEAT_COUNT = int(os.getenv("HANZ_INSIDER_REPEAT_COUNT", "2"))

# V10.7 Broker Flow Intelligence.
# Broker codes represent intermediaries, not a single investor. This is confirmation only.
BROKER_FLOW_ENABLED = os.getenv("HANZ_BROKER_FLOW_ENABLED", "1").strip() != "0"
BROKER_LOOKBACK_DAYS = int(os.getenv("HANZ_BROKER_LOOKBACK_DAYS", "5"))
BROKER_STRONG_NET_PCT_5D = float(os.getenv("HANZ_BROKER_STRONG_NET_PCT_5D", "1.25"))
BROKER_WARNING_NET_PCT_5D = float(os.getenv("HANZ_BROKER_WARNING_NET_PCT_5D", "0.60"))
BROKER_CONFIRM_DAYS = int(os.getenv("HANZ_BROKER_CONFIRM_DAYS", "3"))
BROKER_CONCENTRATION_BONUS_PCT = float(os.getenv("HANZ_BROKER_CONCENTRATION_BONUS_PCT", "45"))

# V10.8 Market Movers Intelligence.
# Publishes Top-5 gainers + Top-5 losers from the HANZ scanned universe.
# "Why it moved" is evidence-based (price/volume/structure/flow), never invented news causality.
MARKET_MOVERS_ENABLED = os.getenv("HANZ_MARKET_MOVERS_ENABLED", "1").strip() != "0"
MARKET_MOVERS_TOP_N = int(os.getenv("HANZ_MARKET_MOVERS_TOP_N", "5"))
MARKET_MOVERS_CHART_BARS = int(os.getenv("HANZ_MARKET_MOVERS_CHART_BARS", "20"))
_MARKET_MOVER_ROWS = []

# V10.8.3 Canonical Ranking Freeze.
# One ranking formula is computed by the engine and reused everywhere.
# This does NOT change BUY gates/states; it only prevents dashboard-side ranking drift.
CANONICAL_RANK_VERSION = "CRV1_2026_09_05"

# V8.5 Predictive Radar
# Radar states are INTERNAL ONLY and must never be shown as user-facing BUY signals.
RADAR_BASE_MIN_SCORE = int(os.getenv("HANZ_RADAR_BASE_MIN_SCORE", "4"))
RADAR_WATCH_SCORE = int(os.getenv("HANZ_RADAR_WATCH_SCORE", "6"))
RADAR_PRE_ALERT_SCORE = int(os.getenv("HANZ_RADAR_PRE_ALERT_SCORE", "8"))
RADAR_ARMED_SCORE = int(os.getenv("HANZ_RADAR_ARMED_SCORE", "9"))
RADAR_ARM_DISTANCE_PCT = float(os.getenv("HANZ_RADAR_ARM_DISTANCE_PCT", "2.5"))
RADAR_MIN_VOLUME_PACE = float(os.getenv("HANZ_RADAR_MIN_VOLUME_PACE", "1.0"))
RADAR_INTERVAL = os.getenv("HANZ_RADAR_INTRADAY_INTERVAL", "5m")
RADAR_PERIOD = os.getenv("HANZ_RADAR_INTRADAY_PERIOD", "5d")


# Chart persistence: completed daily candles are stored server-side in Supabase.
# The dashboard never calls Yahoo Finance directly.
CHART_LOOKBACK_BARS = int(
    os.getenv("HANZ_SWING_CHART_LOOKBACK_BARS", "130")
)
CHART_STATES = {
    "EARLY_WATCH",
    "PRE_ALERT",
    "SETUP_READY",
    "EARLY_CONFIRMED_BUY",
    "SWING_BUY",
}


# If Yahoo daily bars lag, rebuild the latest completed IDX daily candle from
# intraday data. This is server-side only; the browser still reads Supabase.
CHART_REPAIR_INTRADAY_INTERVAL = os.getenv(
    "HANZ_SWING_CHART_REPAIR_INTERVAL", "5m"
)
CHART_REPAIR_INTRADAY_PERIOD = os.getenv(
    "HANZ_SWING_CHART_REPAIR_PERIOD", "5d"
)

MAX_SYMBOLS_PER_CYCLE = int(
    os.getenv("HANZ_SWING_MAX_SYMBOLS_PER_CYCLE", "220")
)


# Intraday quote freshness guard.
# Yahoo/yfinance IDX quotes are treated as delayed, not tick-by-tick realtime.
INTRADAY_INTERVAL = os.getenv(
    "HANZ_SWING_INTRADAY_TIMEFRAME", "1m"
)
INTRADAY_PERIOD = os.getenv(
    "HANZ_SWING_INTRADAY_PERIOD", "1d"
)

# Intraday provider fallback chain.
# Primary remains 1m/1d for the freshest quote.
# Fallbacks are only used when the primary call returns no usable market data.
INTRADAY_FALLBACK_CHAIN = [
    ("1m", "5d"),
    ("2m", "5d"),
    ("5m", "5d"),
    ("15m", "5d"),
]

INTRADAY_STALE_MINUTES = int(
    os.getenv("HANZ_SWING_STALE_GUARD_MINUTES", "20")
)

# Adaptive feed-health guard:
# A quote older than the ticker threshold is not automatically "stale".
# First evaluate whether the overall provider/feed is still updating.
INTRADAY_FEED_HEALTH_MIN_SYMBOLS = int(
    os.getenv("HANZ_SWING_FEED_HEALTH_MIN_SYMBOLS", "2")
)
INTRADAY_FEED_HEALTH_FRESH_RATIO = float(
    os.getenv("HANZ_SWING_FEED_HEALTH_FRESH_RATIO", "0.50")
)


# Discount Intelligence V1
# Analyst-target calls are deliberately limited to stronger setups
# so the 200-stock scan does not hammer Yahoo analysis endpoints.
DISCOUNT_ANALYST_STATES = {
    "SWING_CONFIRMING",
    "SETUP_READY",
    "EARLY_CONFIRMED_BUY",
    "SWING_BUY",
}
DISCOUNT_ANALYST_DELAY_SECONDS = float(
    os.getenv("HANZ_SWING_ANALYST_DELAY_SECONDS", "0.25")
)


# Fundamental Intelligence is fetched only for stronger setups.
# This keeps the 200-stock final scan reasonable while enriching
# SWING_CONFIRMING and SWING_BUY candidates.
FUNDAMENTAL_STATES = {
    "SWING_CONFIRMING",
    "SETUP_READY",
    "EARLY_CONFIRMED_BUY",
    "SWING_BUY",
}
FUNDAMENTAL_FETCH_DELAY_SECONDS = float(
    os.getenv("HANZ_SWING_FUNDAMENTAL_DELAY_SECONDS", "0.25")
)


JAKARTA_TZ = ZoneInfo("Asia/Jakarta")

TRAILING_ATR_MULTIPLIER_T1 = float(
    os.getenv("HANZ_SWING_TRAILING_ATR_T1", "1.5")
)
TRAILING_ATR_MULTIPLIER_T2 = float(
    os.getenv("HANZ_SWING_TRAILING_ATR_T2", "1.0")
)


# ============================================================
# V8 REAL-MONEY GUARD
#
# Important:
# - HANZ still produces its technical state (EARLY/PRE/READY/SWING_BUY).
# - risk_gate is a separate execution-safety layer.
# - No broker orders are sent by this engine.
# - Account capital is intentionally NOT guessed. If it is not configured,
#   SWING_BUY remains PAPER_ONLY for position sizing / execution purposes.
# ============================================================

RISK_LIVE_GATE_ENABLED = (
    os.getenv("HANZ_RISK_LIVE_GATE_ENABLED", "1").strip() != "0"
)

ACCOUNT_CAPITAL_IDR = float(
    os.getenv("HANZ_ACCOUNT_CAPITAL_IDR", "0")
)
RISK_PER_TRADE_PCT = float(
    os.getenv("HANZ_RISK_PER_TRADE_PCT", "0.50")
)
MAX_PORTFOLIO_RISK_PCT = float(
    os.getenv("HANZ_MAX_PORTFOLIO_RISK_PCT", "3.00")
)
MAX_POSITION_PCT = float(
    os.getenv("HANZ_MAX_POSITION_PCT", "15.0")
)
MAX_OPEN_POSITIONS = int(
    os.getenv("HANZ_MAX_OPEN_POSITIONS", "6")
)
MAX_SECTOR_EXPOSURE_PCT = float(
    os.getenv("HANZ_MAX_SECTOR_EXPOSURE_PCT", "30.0")
)

# Broker costs differ by broker/account. HANZ deliberately does not guess them.
# Configure all three before a signal can become ELIGIBLE for real-money use.
BUY_FEE_PCT = float(
    os.getenv("HANZ_BUY_FEE_PCT", "-1")
)
SELL_FEE_PCT = float(
    os.getenv("HANZ_SELL_FEE_PCT", "-1")
)
SLIPPAGE_PCT = float(
    os.getenv("HANZ_SLIPPAGE_PCT", "-1")
)

# HANZ defaults below are strategy guardrails, not IDX regulatory thresholds.
MIN_AVG_DAILY_VALUE_IDR = float(
    os.getenv("HANZ_MIN_AVG_DAILY_VALUE_IDR", "5000000000")
)
MAX_ZERO_VOLUME_DAYS_20 = int(
    os.getenv("HANZ_MAX_ZERO_VOLUME_DAYS_20", "1")
)
MAX_ATR_PCT = float(
    os.getenv("HANZ_MAX_ATR_PCT", "12.0")
)

# Swing-specific volatility suitability.
SWING_HIGH_ATR_PCT = float(os.getenv("HANZ_SWING_HIGH_ATR_PCT", "4.0"))
SWING_EXTREME_ATR_PCT = float(os.getenv("HANZ_SWING_EXTREME_ATR_PCT", "7.0"))
SWING_EXTREME_1D_MOVE_PCT = float(os.getenv("HANZ_SWING_EXTREME_1D_MOVE_PCT", "8.0"))
SWING_HIGH_GAP_PCT = float(os.getenv("HANZ_SWING_HIGH_GAP_PCT", "4.0"))
SWING_EXTREME_GAP_PCT = float(os.getenv("HANZ_SWING_EXTREME_GAP_PCT", "8.0"))
SWING_HIGH_DAY_RANGE_PCT = float(os.getenv("HANZ_SWING_HIGH_DAY_RANGE_PCT", "8.0"))
SWING_EXTREME_MOVE_DAYS_10 = int(os.getenv("HANZ_SWING_EXTREME_MOVE_DAYS_10", "2"))
SWING_HIGH_VOL_SIZE_MULTIPLIER = float(os.getenv("HANZ_SWING_HIGH_VOL_SIZE_MULTIPLIER", "0.50"))
MAX_ADV_PARTICIPATION_PCT = float(
    os.getenv("HANZ_MAX_ADV_PARTICIPATION_PCT", "0.50")
)
MIN_RR_T1 = float(
    os.getenv("HANZ_MIN_RR_T1", "1.30")
)
MIN_RR_T2 = float(
    os.getenv("HANZ_MIN_RR_T2", "2.00")
)

KILL_SWITCH_CONSECUTIVE_LOSSES = int(
    os.getenv("HANZ_KILL_SWITCH_CONSECUTIVE_LOSSES", "4")
)
KILL_SWITCH_LOOKBACK_TRADES = int(
    os.getenv("HANZ_KILL_SWITCH_LOOKBACK_TRADES", "10")
)
KILL_SWITCH_MIN_WIN_RATE_PCT = float(
    os.getenv("HANZ_KILL_SWITCH_MIN_WIN_RATE_PCT", "35.0")
)

MARKET_REGIME_TICKER = os.getenv(
    "HANZ_MARKET_REGIME_TICKER", "^JKSE"
)

_REAL_MONEY_CONTEXT = None

FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv(
    "FIREBASE_SERVICE_ACCOUNT_JSON", ""
).strip()

PUSH_DASHBOARD_URL = os.getenv(
    "HANZ_SWING_DASHBOARD_URL",
    "https://hanzcuan.com/dashboard/swing/",
)

# Production portfolio push events.
# Device delivery has been validated end-to-end via HANZ FID self-heal test.
PUSH_ALERT_TYPES = {
    "TARGET_1_REACHED",
    "TARGET_2_REACHED",
    "TRAILING_ACTIVATED",
    "PROTECT_PROFIT",
    "DISTRIBUTION_WATCH",
    "FOREIGN_SELL_CAUTION",
    "INSIDER_SELL_CAUTION",
    "BROKER_DISTRIBUTION_WATCH",
    "STOP_LOSS",
    "CONFIRMED_SELL",
}

_FIREBASE_APP = None



# ============================================================
# IDX / BEI TRADING CALENDAR GATE
# Time zone: Asia/Jakarta (WIB)
#
# 2026 holidays follow the published IDX 2026 trading-holiday
# calendar (Peng-00171/BEI.POP/09-2025). The environment variable
# HANZ_IDX_HOLIDAYS_JSON can override/extend this map without code
# changes, e.g. {"2026-12-31":"Trading Holiday"}.
# ============================================================

IDX_HOLIDAYS_2026 = {
    "2026-01-01": "New Year 2026",
    "2026-01-16": "Isra Mikraj",
    "2026-02-16": "Chinese New Year Collective Leave",
    "2026-02-17": "Chinese New Year",
    "2026-03-18": "Nyepi Collective Leave",
    "2026-03-19": "Nyepi",
    "2026-03-20": "Eid al-Fitr Collective Leave",
    "2026-03-23": "Eid al-Fitr Collective Leave",
    "2026-03-24": "Eid al-Fitr Collective Leave",
    "2026-04-03": "Good Friday",
    "2026-05-01": "Labour Day",
    "2026-05-14": "Ascension Day",
    "2026-05-15": "Ascension Day Collective Leave",
    "2026-05-27": "Eid al-Adha",
    "2026-05-28": "Eid al-Adha Collective Leave",
    "2026-06-01": "Pancasila Day",
    "2026-06-16": "Islamic New Year",
    "2026-08-17": "Independence Day",
    "2026-08-25": "Prophet Muhammad's Birthday",
    "2026-12-24": "Christmas Collective Leave",
    "2026-12-25": "Christmas Day",
    "2026-12-31": "IDX Trading Holiday",
}

IDX_HOLIDAYS = dict(IDX_HOLIDAYS_2026)

try:
    extra_holidays = json.loads(
        os.getenv("HANZ_IDX_HOLIDAYS_JSON", "{}")
    )
    if isinstance(extra_holidays, dict):
        IDX_HOLIDAYS.update(
            {
                str(k): str(v)
                for k, v in extra_holidays.items()
            }
        )
except Exception as exc:
    print(
        f"IDX calendar override ignored: {exc}",
        flush=True,
    )


def jakarta_now():
    return utc_now().astimezone(JAKARTA_TZ)


def idx_trading_day(date_obj):
    if date_obj.weekday() >= 5:
        return False, "Weekend"

    key = date_obj.isoformat()
    if key in IDX_HOLIDAYS:
        return False, IDX_HOLIDAYS[key]

    # Fail-safe: the embedded official calendar is verified for 2026.
    # For another year, require explicit holiday data rather than
    # pretending every weekday is a trading day.
    if date_obj.year != 2026:
        return False, "IDX calendar year not verified"

    return True, "Trading Day"


def idx_market_session(now=None):
    now = now or jakarta_now()
    trading_day, reason = idx_trading_day(now.date())

    if not trading_day:
        state = (
            "CLOSED_WEEKEND"
            if now.weekday() >= 5
            else "CLOSED_HOLIDAY"
        )
        if reason == "IDX calendar year not verified":
            state = "CALENDAR_UNVERIFIED"

        return {
            "state": state,
            "reason": reason,
            "is_trading_day": False,
            "allow_portfolio_monitor": False,
            "allow_final_scan": False,
            "now_wib": now.isoformat(),
        }

    minutes = now.hour * 60 + now.minute
    friday = now.weekday() == 4

    session_1_end = 11 * 60 + 30 if friday else 12 * 60
    session_2_start = 14 * 60 if friday else 13 * 60 + 30

    if minutes < 8 * 60 + 45:
        state = "CLOSED_BEFORE_HOURS"
    elif minutes < 9 * 60:
        state = "PRE_OPEN"
    elif minutes < session_1_end:
        state = "SESSION_1"
    elif minutes < session_2_start:
        state = "LUNCH_BREAK"
    elif minutes < 15 * 60 + 50:
        state = "SESSION_2"
    elif minutes <= 16 * 60 + 15:
        state = "POST_CLOSE"
    else:
        state = "CLOSED_AFTER_HOURS"

    # Portfolio monitoring is useful during active trading and lunch.
    allow_portfolio_monitor = state in {
        "SESSION_1",
        "LUNCH_BREAK",
        "SESSION_2",
        "POST_CLOSE",
    }

    # Swing candidate generation only uses the completed daily bar.
    allow_final_scan = state == "POST_CLOSE"

    return {
        "state": state,
        "reason": "Trading Day",
        "is_trading_day": True,
        "allow_portfolio_monitor": allow_portfolio_monitor,
        "allow_final_scan": allow_final_scan,
        "now_wib": now.isoformat(),
    }


def previous_idx_trading_day(date_obj):
    candidate = date_obj
    for _ in range(370):
        candidate = candidate.fromordinal(
            candidate.toordinal() - 1
        )
        ok, _ = idx_trading_day(candidate)
        if ok:
            return candidate
    return None


def next_idx_trading_day(date_obj):
    candidate = date_obj
    for _ in range(370):
        candidate = candidate.fromordinal(
            candidate.toordinal() + 1
        )
        ok, _ = idx_trading_day(candidate)
        if ok:
            return candidate
    return None

def utc_now():
    return datetime.now(timezone.utc)


def now_iso():
    return utc_now().isoformat()


def normalize_ticker(ticker):
    ticker = str(ticker or "").strip().upper()
    if not ticker:
        return None

    # Yahoo index symbols are already complete symbols.
    # Example: IDX Composite is ^JKSE, NOT ^JKSE.JK.
    if ticker.startswith("^"):
        return ticker

    if not ticker.endswith(".JK"):
        ticker += ".JK"
    return ticker


def clean_ticker(ticker):
    return str(ticker or "").upper().replace(".JK", "")


def safe_float(value):
    try:
        if value is None:
            return None
        x = float(value)
        if math.isnan(x):
            return None
        return x
    except Exception:
        return None


def safe_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def values_different(a, b, tolerance=1e-9):
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    try:
        return abs(float(a) - float(b)) > tolerance
    except Exception:
        return a != b


def supabase_request(method, path, payload=None, prefer=None):
    if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_SECRET_KEY missing"
        )

    url = f"{SUPABASE_URL}/rest/v1/{path}"

    headers = {
        "apikey": SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url=url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(
            req, timeout=45
        ) as resp:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(
            "utf-8", errors="replace"
        )
        raise RuntimeError(
            f"HTTP {exc.code}: {body}"
        ) from exc


def download_frame(ticker, interval, period):
    symbol = normalize_ticker(ticker)

    df = yf.download(
        symbol,
        interval=interval,
        period=period,
        auto_adjust=False,
        progress=False,
        threads=False,
    )

    if df is None or df.empty:
        raise RuntimeError("No market data")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            col[0] if isinstance(col, tuple)
            else col
            for col in df.columns
        ]

    df = df.dropna(
        subset=["Open", "High", "Low", "Close"]
    )

    if df.empty:
        raise RuntimeError("No usable bars")

    return df


def _quote_from_intraday_frame(df, source):
    """
    Convert a usable intraday frame into the standard HANZ quote payload.
    The caller decides which provider/interval/period produced the frame.
    """
    price = safe_float(df["Close"].iloc[-1])
    bar_ts = pd.Timestamp(df.index[-1])

    if bar_ts.tzinfo is None:
        bar_ts = bar_ts.tz_localize(JAKARTA_TZ)
    else:
        bar_ts = bar_ts.tz_convert(JAKARTA_TZ)

    now_wib = datetime.now(JAKARTA_TZ)
    age_minutes = max(
        0.0,
        (now_wib - bar_ts.to_pydatetime()).total_seconds() / 60.0,
    )

    fresh_by_age = (
        price is not None
        and age_minutes <= INTRADAY_STALE_MINUTES
    )

    return {
        "price": price,
        "bar_at": bar_ts.isoformat(),
        "age_minutes": round(age_minutes, 2),
        "fresh_by_age": fresh_by_age,
        "status": "OK" if fresh_by_age else "OLD_BAR",
        "source": source,
    }


def _ticker_history_frame(ticker, interval, period):
    """
    Secondary yfinance access path.
    Uses Ticker.history() only when yf.download() failed for the same request.
    """
    symbol = normalize_ticker(ticker)

    df = yf.Ticker(symbol).history(
        interval=interval,
        period=period,
        auto_adjust=False,
        actions=False,
        prepost=False,
        raise_errors=False,
    )

    if df is None or df.empty:
        raise RuntimeError("No market data")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            col[0] if isinstance(col, tuple)
            else col
            for col in df.columns
        ]

    required = ["Open", "High", "Low", "Close"]
    if not all(col in df.columns for col in required):
        raise RuntimeError("Missing OHLC columns")

    df = df.dropna(subset=required)

    if df.empty:
        raise RuntimeError("No usable bars")

    return df


def latest_intraday_quote(ticker):
    """
    Return the latest intraday quote with provider-bar timestamp.

    Fallback policy:
      1) Primary: configured interval/period (normally 1m/1d)
      2) Same 1m interval with a wider 5d window
      3) 2m/5d
      4) 5m/5d
      5) 15m/5d
      6) For each failed yf.download request, try Ticker.history()

    IMPORTANT:
    - A fallback is used only when the preceding request has NO usable bars.
    - An OLD_BAR is still returned as a valid last trade. The existing
      adaptive feed-health logic decides whether it may overwrite stored price.
    - We never substitute a daily close as an intraday quote.
    """
    attempts = [(INTRADAY_INTERVAL, INTRADAY_PERIOD)]

    for item in INTRADAY_FALLBACK_CHAIN:
        if item not in attempts:
            attempts.append(item)

    errors = []

    for interval, period in attempts:
        # Path A: yf.download()
        try:
            df = download_frame(
                ticker,
                interval,
                period,
            )
            quote = _quote_from_intraday_frame(
                df,
                f"YF_DOWNLOAD_{interval}_{period}",
            )
            quote["fallback_used"] = (
                interval != INTRADAY_INTERVAL
                or period != INTRADAY_PERIOD
            )
            quote["attempt_errors"] = errors
            return quote
        except Exception as exc:
            errors.append(
                f"download {interval}/{period}: {exc}"
            )

        # Path B: Ticker.history()
        try:
            df = _ticker_history_frame(
                ticker,
                interval,
                period,
            )
            quote = _quote_from_intraday_frame(
                df,
                f"YF_HISTORY_{interval}_{period}",
            )
            quote["fallback_used"] = True
            quote["attempt_errors"] = errors
            return quote
        except Exception as exc:
            errors.append(
                f"history {interval}/{period}: {exc}"
            )

    raise RuntimeError(
        "No market data after intraday fallback chain | "
        + " | ".join(errors[-6:])
    )


def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False,
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False,
    ).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def atr(df, period=14):
    prev_close = df["Close"].shift(1)

    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return tr.ewm(
        alpha=1 / period,
        adjust=False,
    ).mean()


def _swing_pivots(df, left=2, right=2):
    """Return confirmed local swing highs/lows using only completed bars.

    HANZ operationalization of HH/HL/LH/LL. The pivot width is an implementation
    parameter, not a literal rule from the supplied books, and must be validated.
    """
    highs=[]; lows=[]
    if df is None or len(df) < left + right + 5:
        return highs, lows
    h=df["High"].astype(float).reset_index(drop=True)
    l=df["Low"].astype(float).reset_index(drop=True)
    for i in range(left, len(df)-right):
        hv=float(h.iloc[i]); lv=float(l.iloc[i])
        if hv >= float(h.iloc[i-left:i+right+1].max()):
            highs.append((i,hv))
        if lv <= float(l.iloc[i-left:i+right+1].min()):
            lows.append((i,lv))
    return highs, lows


def _structure_from_pivots(df):
    highs,lows=_swing_pivots(df,2,2)
    out={
        "state":"UNKNOWN","last_swing_high":None,"prev_swing_high":None,
        "last_swing_low":None,"prev_swing_low":None,
    }
    if len(highs)>=2:
        out["prev_swing_high"]=safe_float(highs[-2][1]); out["last_swing_high"]=safe_float(highs[-1][1])
    if len(lows)>=2:
        out["prev_swing_low"]=safe_float(lows[-2][1]); out["last_swing_low"]=safe_float(lows[-1][1])
    if None not in (out["last_swing_high"],out["prev_swing_high"],out["last_swing_low"],out["prev_swing_low"]):
        hh=out["last_swing_high"]>out["prev_swing_high"]
        hl=out["last_swing_low"]>out["prev_swing_low"]
        lh=out["last_swing_high"]<out["prev_swing_high"]
        ll=out["last_swing_low"]<out["prev_swing_low"]
        if hh and hl: out["state"]="BULLISH_HH_HL"
        elif lh and ll: out["state"]="BEARISH_LH_LL"
        else: out["state"]="MIXED"
    return out


def _candle_context(df):
    """Contextual candlestick evidence; never a standalone BUY trigger."""
    if df is None or len(df)<2:
        return {"name":"NEUTRAL","bullish":False,"bearish":False}
    o=float(df["Open"].iloc[-1]); h=float(df["High"].iloc[-1]); l=float(df["Low"].iloc[-1]); c=float(df["Close"].iloc[-1])
    po=float(df["Open"].iloc[-2]); pc=float(df["Close"].iloc[-2])
    rng=max(h-l,1e-12); body=abs(c-o); upper=h-max(o,c); lower=min(o,c)-l
    bull_engulf=(c>o and pc<po and o<=pc and c>=po)
    bear_engulf=(c<o and pc>po and o>=pc and c<=po)
    hammer=(c>=o and lower>=2*max(body,1e-12) and upper<=max(body,1e-12))
    shooting=(c<=o and upper>=2*max(body,1e-12) and lower<=max(body,1e-12))
    strong_bull=(c>o and (c-l)/rng>=0.75 and body/rng>=0.5)
    strong_bear=(c<o and (h-c)/rng>=0.75 and body/rng>=0.5)
    if bull_engulf: name="BULLISH_ENGULFING"
    elif hammer: name="HAMMER_REJECTION"
    elif bear_engulf: name="BEARISH_ENGULFING"
    elif shooting: name="SHOOTING_STAR_REJECTION"
    elif strong_bull: name="STRONG_BULL_CLOSE"
    elif strong_bear: name="STRONG_BEAR_CLOSE"
    elif c>o: name="BULLISH_CANDLE"
    elif c<o: name="BEARISH_CANDLE"
    else: name="NEUTRAL"
    return {"name":name,"bullish":name in {"BULLISH_ENGULFING","HAMMER_REJECTION","STRONG_BULL_CLOSE","BULLISH_CANDLE"},"bearish":name in {"BEARISH_ENGULFING","SHOOTING_STAR_REJECTION","STRONG_BEAR_CLOSE","BEARISH_CANDLE"}}


def _strategy_validation_evidence():
    def f(v):
        try: return float(v) if str(v).strip() else None
        except Exception: return None
    wfe=f(STRATEGY_WFE); exp=f(STRATEGY_OOS_EXPECTANCY_R); dof=f(STRATEGY_DOF_REMAINING_PCT)
    dd=f(STRATEGY_OOS_MAX_DD_R); profitable=f(STRATEGY_PROFITABLE_WF_PCT); concentration=f(STRATEGY_MAX_TRADE_PROFIT_SHARE_PCT)
    checks={
        "flag": bool(STRATEGY_WFA_VALIDATED),
        "wfe": wfe is not None and wfe >= MIN_WFE_RATIO,
        "oos_trades": STRATEGY_OOS_TRADES >= MIN_WFA_OOS_TRADES,
        "wf_windows": STRATEGY_WF_WINDOWS > 1,
        "expectancy": exp is not None and exp > 0,
        "dof": dof is not None and dof >= MIN_DOF_REMAINING_PCT,
        "drawdown_recorded": dd is not None and dd >= 0,
        "window_consistency": profitable is not None and profitable >= MIN_PROFITABLE_WF_PCT,
        "profit_concentration": concentration is not None and concentration <= MAX_SINGLE_TRADE_PROFIT_SHARE_PCT,
        "validated_at": bool(STRATEGY_VALIDATED_AT),
    }
    passed=all(checks.values())
    return {"passed":passed,"checks":checks,"wfe":wfe,"oos_trades":STRATEGY_OOS_TRADES,"wf_windows":STRATEGY_WF_WINDOWS,"oos_expectancy_r":exp,"dof_remaining_pct":dof,"oos_max_dd_r":dd,"profitable_wf_pct":profitable,"max_trade_profit_share_pct":concentration,"validated_at":STRATEGY_VALIDATED_AT or None}


def daily_metrics(df):
    if len(df) < 60:
        raise RuntimeError(
            "Insufficient daily history"
        )

    close = df["Close"].astype(float)
    volume = df["Volume"].astype(float)

    ema20 = close.ewm(
        span=20, adjust=False
    ).mean()
    ema50 = close.ewm(
        span=50, adjust=False
    ).mean()

    rsi14 = rsi(close, 14)
    atr14 = atr(df, 14)

    avg_vol20 = volume.rolling(20).mean()

    traded_value = close * volume
    avg_value20 = traded_value.rolling(20).mean()
    median_value20 = traded_value.rolling(20).median()
    zero_volume_days20 = int((volume.iloc[-20:] <= 0).sum())
    atr_pct = None

    ema20_slope_5d_pct = None
    rsi_change_5d = None
    volume_accel_5d = None

    if len(df) >= 8:
        ema20_base = safe_float(ema20.iloc[-6])
        ema20_now = safe_float(ema20.iloc[-1])
        if ema20_base not in (None, 0) and ema20_now is not None:
            ema20_slope_5d_pct = (
                (ema20_now - ema20_base) / abs(ema20_base) * 100
            )

        rsi_then = safe_float(rsi14.iloc[-6])
        rsi_now = safe_float(rsi14.iloc[-1])
        if rsi_then is not None and rsi_now is not None:
            rsi_change_5d = rsi_now - rsi_then

        recent_avg = safe_float(volume.iloc[-3:].mean())
        prior_avg = safe_float(volume.iloc[-8:-3].mean())
        if recent_avg is not None and prior_avg not in (None, 0):
            volume_accel_5d = recent_avg / prior_avg

    last = len(df) - 1
    prior_high20 = safe_float(
        df["High"].iloc[
            max(0, last - 20):last
        ].max()
    )
    prior_low20 = safe_float(
        df["Low"].iloc[
            max(0, last - 20):last
        ].min()
    )

    # Minor structure for early-entry confirmation.
    # Excludes the current bar to avoid look-ahead.
    prior_high3 = safe_float(
        df["High"].iloc[max(0, last - 3):last].max()
    )
    prior_low10 = safe_float(
        df["Low"].iloc[max(0, last - 10):last].min()
    )

    price = safe_float(close.iloc[-1])
    vol = safe_float(volume.iloc[-1])
    avg_vol = safe_float(avg_vol20.iloc[-1])

    rvol = (
        vol / avg_vol
        if (
            vol is not None
            and avg_vol not in (None, 0)
        )
        else None
    )

    atr_now = safe_float(atr14.iloc[-1])
    if price not in (None, 0) and atr_now is not None:
        atr_pct = atr_now / price * 100

    # Volatility diagnostics for a multi-day swing strategy.
    prior_close = safe_float(close.iloc[-2]) if len(close) >= 2 else None
    day_open = safe_float(df["Open"].iloc[-1])
    day_high = safe_float(df["High"].iloc[-1])
    day_low = safe_float(df["Low"].iloc[-1])

    gap_pct = None
    if prior_close not in (None, 0) and day_open is not None:
        gap_pct = (day_open / prior_close - 1) * 100

    day_range_pct = None
    if price not in (None, 0) and day_high is not None and day_low is not None:
        day_range_pct = (day_high - day_low) / abs(price) * 100

    extreme_move_days10 = 0
    if len(close) >= 11:
        recent_ret = close.pct_change().iloc[-10:] * 100
        extreme_move_days10 = int(
            (recent_ret.abs() >= SWING_EXTREME_1D_MOVE_PCT).sum()
        )

    ret1 = None
    if len(close) >= 2:
        base = safe_float(close.iloc[-2])
        if base not in (None, 0) and price is not None:
            ret1 = (price / base - 1) * 100

    ret3 = None
    if len(close) >= 4:
        base = safe_float(close.iloc[-4])
        if base not in (None, 0) and price is not None:
            ret3 = (price / base - 1) * 100

    ret5 = None
    if len(close) >= 6:
        base = safe_float(close.iloc[-6])
        if base and price:
            ret5 = (
                (price - base)
                / base
                * 100
            )

    recent_high_5d = safe_float(df["High"].iloc[-5:].max()) if len(df) >= 5 else None
    recent_high_10d = safe_float(df["High"].iloc[-10:].max()) if len(df) >= 10 else None
    drawdown_5d_high_pct = None
    drawdown_10d_high_pct = None

    if price is not None and recent_high_5d not in (None, 0):
        drawdown_5d_high_pct = (recent_high_5d - price) / recent_high_5d * 100
    if price is not None and recent_high_10d not in (None, 0):
        drawdown_10d_high_pct = (recent_high_10d - price) / recent_high_10d * 100

    down_volume_ratio_5d = None
    if len(df) >= 6:
        recent_close = df["Close"].iloc[-5:].astype(float)
        recent_vol = df["Volume"].iloc[-5:].astype(float)
        prev_close_5 = df["Close"].shift(1).iloc[-5:].astype(float)
        down_mask = recent_close.values < prev_close_5.values
        up_mask = recent_close.values >= prev_close_5.values
        down_vol = float(recent_vol.values[down_mask].sum()) if down_mask.any() else 0.0
        up_vol = float(recent_vol.values[up_mask].sum()) if up_mask.any() else 0.0
        if up_vol > 0:
            down_volume_ratio_5d = down_vol / up_vol
        elif down_vol > 0:
            down_volume_ratio_5d = 99.0

    lookback_52w = df.iloc[-252:] if len(df) >= 252 else df
    week52_high = safe_float(lookback_52w["High"].max())
    week52_low = safe_float(lookback_52w["Low"].min())

    week52_discount_pct = None
    week52_position_pct = None

    if price is not None and week52_high not in (None, 0):
        week52_discount_pct = (
            (week52_high - price) / week52_high * 100
        )

    if (
        price is not None
        and week52_high is not None
        and week52_low is not None
        and week52_high > week52_low
    ):
        week52_position_pct = (
            (price - week52_low)
            / (week52_high - week52_low)
            * 100
        )

    breakout_distance_pct = None
    if price is not None and prior_high20 not in (None, 0):
        breakout_distance_pct = (
            (prior_high20 - price) / prior_high20 * 100
        )

    # Price-action structure from confirmed local swing pivots.
    structure_info = _structure_from_pivots(df)
    structure_state = structure_info.get("state", "UNKNOWN")
    last_swing_high = structure_info.get("last_swing_high")
    prev_swing_high = structure_info.get("prev_swing_high")
    last_swing_low = structure_info.get("last_swing_low")
    prev_swing_low = structure_info.get("prev_swing_low")

    candle_info = _candle_context(df)
    candle_context = candle_info.get("name", "NEUTRAL")
    candle_range = None
    candle_body_pct_range = None
    close_location = None
    if None not in (day_open, day_high, day_low, price) and day_high > day_low:
        candle_range = day_high - day_low
        candle_body_pct_range = abs(price - day_open) / candle_range * 100
        close_location = (price - day_low) / candle_range

    # Setup-location diagnostics used later by the two setup families.
    ema20_distance_atr = None
    swing_high_distance_atr = None
    if atr_now not in (None, 0) and price is not None:
        if safe_float(ema20.iloc[-1]) is not None:
            ema20_distance_atr = abs(price - safe_float(ema20.iloc[-1])) / atr_now
        if last_swing_high is not None:
            swing_high_distance_atr = abs(price - last_swing_high) / atr_now

    return {
        "price": price,
        "open": safe_float(df["Open"].iloc[-1]),
        "high": safe_float(df["High"].iloc[-1]),
        "low": safe_float(df["Low"].iloc[-1]),
        "week52_high": week52_high,
        "week52_low": week52_low,
        "week52_discount_pct": safe_float(week52_discount_pct),
        "week52_position_pct": safe_float(week52_position_pct),
        "ema20": safe_float(ema20.iloc[-1]),
        "ema50": safe_float(ema50.iloc[-1]),
        "rsi14": safe_float(rsi14.iloc[-1]),
        "atr14": safe_float(atr14.iloc[-1]),
        "rvol20": safe_float(rvol),
        "avg_value20": safe_float(avg_value20.iloc[-1]),
        "median_value20": safe_float(median_value20.iloc[-1]),
        "zero_volume_days20": zero_volume_days20,
        "atr_pct": safe_float(atr_pct),
        "gap_pct": safe_float(gap_pct),
        "day_range_pct": safe_float(day_range_pct),
        "extreme_move_days10": extreme_move_days10,
        "prior_high20": prior_high20,
        "prior_low20": prior_low20,
        "prior_high3": prior_high3,
        "prior_low10": prior_low10,
        "ret1_pct": safe_float(ret1),
        "ret3_pct": safe_float(ret3),
        "ret5_pct": safe_float(ret5),
        "recent_high_5d": safe_float(recent_high_5d),
        "recent_high_10d": safe_float(recent_high_10d),
        "drawdown_5d_high_pct": safe_float(drawdown_5d_high_pct),
        "drawdown_10d_high_pct": safe_float(drawdown_10d_high_pct),
        "down_volume_ratio_5d": safe_float(down_volume_ratio_5d),
        "ema20_slope_5d_pct": safe_float(ema20_slope_5d_pct),
        "rsi_change_5d": safe_float(rsi_change_5d),
        "volume_accel_5d": safe_float(volume_accel_5d),
        "breakout_distance_pct": safe_float(breakout_distance_pct),
        "structure_state": structure_state,
        "last_swing_high": safe_float(last_swing_high),
        "prev_swing_high": safe_float(prev_swing_high),
        "last_swing_low": safe_float(last_swing_low),
        "prev_swing_low": safe_float(prev_swing_low),
        "ema20_distance_atr": safe_float(ema20_distance_atr),
        "swing_high_distance_atr": safe_float(swing_high_distance_atr),
        "candle_context": candle_context,
        "candle_body_pct_range": safe_float(candle_body_pct_range),
        "close_location": safe_float(close_location),
        "bar_at": pd.Timestamp(
            df.index[-1]
        ).isoformat(),
    }


def weekly_metrics(df):
    if len(df) < 25:
        raise RuntimeError(
            "Insufficient weekly history"
        )

    close = df["Close"].astype(float)

    ema10 = close.ewm(
        span=10, adjust=False
    ).mean()
    ema20 = close.ewm(
        span=20, adjust=False
    ).mean()

    rsi14 = rsi(close, 14)

    ema10_now = safe_float(ema10.iloc[-1])
    ema20_now = safe_float(ema20.iloc[-1])
    ema_spread_pct = None
    ema_spread_change_4w = None

    if ema20_now not in (None, 0) and ema10_now is not None:
        ema_spread_pct = (
            (ema10_now - ema20_now) / abs(ema20_now) * 100
        )

    if len(close) >= 5:
        old_ema20 = safe_float(ema20.iloc[-5])
        old_ema10 = safe_float(ema10.iloc[-5])
        if old_ema20 not in (None, 0) and old_ema10 is not None:
            old_spread = (
                (old_ema10 - old_ema20) / abs(old_ema20) * 100
            )
            if ema_spread_pct is not None:
                ema_spread_change_4w = ema_spread_pct - old_spread

    return {
        "price": safe_float(close.iloc[-1]),
        "ema10": ema10_now,
        "ema20": ema20_now,
        "rsi14": safe_float(rsi14.iloc[-1]),
        "ema_spread_pct": safe_float(ema_spread_pct),
        "ema_spread_change_4w": safe_float(ema_spread_change_4w),
        "bar_at": pd.Timestamp(
            df.index[-1]
        ).isoformat(),
    }




def _completed_daily_frame_for_radar(daily_df):
    """Keep radar baseline strictly on completed IDX daily candles."""
    target = latest_completed_idx_date()
    frame = daily_df.copy()
    keep = [
        pd.Timestamp(x).date() <= target
        for x in frame.index
    ]
    frame = frame.loc[keep]
    if len(frame) < 60:
        raise RuntimeError("Insufficient completed daily history for radar")
    return frame


def _idx_session_progress_fraction(now=None):
    """Approximate fraction of today's active IDX trading minutes completed."""
    now = now or jakarta_now()
    minute = now.hour * 60 + now.minute
    friday = now.weekday() == 4

    s1_start = 9 * 60
    s1_end = 11 * 60 + 30 if friday else 12 * 60
    s2_start = 14 * 60 if friday else 13 * 60 + 30
    s2_end = 15 * 60 + 50

    s1_len = max(0, s1_end - s1_start)
    s2_len = max(0, s2_end - s2_start)
    total = max(1, s1_len + s2_len)

    if minute <= s1_start:
        elapsed = 0
    elif minute <= s1_end:
        elapsed = minute - s1_start
    elif minute < s2_start:
        elapsed = s1_len
    elif minute <= s2_end:
        elapsed = s1_len + (minute - s2_start)
    else:
        elapsed = total

    # Opening minutes are noisy; floor the denominator so volume pace
    # is useful without exploding on the first few prints.
    return max(0.15, min(1.0, elapsed / total))


def intraday_radar_snapshot(ticker, completed_daily_df, daily):
    """
    Build a live, non-actionable radar snapshot from intraday bars.

    The snapshot is used only to detect leading conditions BEFORE the
    completed daily candle confirms them. It can arm a candidate, but it
    can never create a SWING_BUY by itself.
    """
    attempts = [
        (RADAR_INTERVAL, RADAR_PERIOD),
        ("15m", "5d"),
    ]
    last_error = None
    frame = None
    source = None

    for interval, period in attempts:
        try:
            candidate = download_frame(ticker, interval, period).copy()
            if candidate is None or candidate.empty:
                continue
            frame = candidate
            source = f"{interval}/{period}"
            break
        except Exception as exc:
            last_error = exc

    if frame is None or frame.empty:
        raise RuntimeError(f"Radar intraday data unavailable: {last_error}")

    idx = pd.DatetimeIndex(frame.index)
    if idx.tz is None:
        idx = idx.tz_localize(JAKARTA_TZ)
    else:
        idx = idx.tz_convert(JAKARTA_TZ)
    frame.index = idx

    today = jakarta_now().date()
    today_frame = frame.loc[[x.date() == today for x in frame.index]].copy()
    if today_frame.empty:
        raise RuntimeError("No current-session intraday bars for predictive radar")

    last_ts = pd.Timestamp(today_frame.index[-1])
    age_minutes = max(
        0.0,
        (jakarta_now() - last_ts.to_pydatetime()).total_seconds() / 60.0,
    )
    fresh = age_minutes <= max(INTRADAY_STALE_MINUTES, 30)

    current_price = safe_float(today_frame["Close"].iloc[-1])
    day_open = safe_float(today_frame["Open"].iloc[0])
    day_high = safe_float(today_frame["High"].max())
    day_low = safe_float(today_frame["Low"].min())
    volume_today = safe_float(today_frame["Volume"].fillna(0).sum()) or 0.0

    prior_close = safe_float(daily.get("price"))
    prior_high20 = safe_float(daily.get("prior_high20"))
    ema20 = safe_float(daily.get("ema20"))

    intraday_return_pct = None
    gap_pct = None
    breakout_distance_pct = None
    day_range_pct = None

    if current_price is not None and prior_close not in (None, 0):
        intraday_return_pct = (current_price / prior_close - 1) * 100
    if day_open is not None and prior_close not in (None, 0):
        gap_pct = (day_open / prior_close - 1) * 100
    if current_price is not None and prior_high20 not in (None, 0):
        breakout_distance_pct = (
            (prior_high20 - current_price) / prior_high20 * 100
        )
    if current_price not in (None, 0) and day_high is not None and day_low is not None:
        day_range_pct = (day_high - day_low) / abs(current_price) * 100

    avg_daily_volume20 = None
    if len(completed_daily_df) >= 20:
        avg_daily_volume20 = safe_float(
            completed_daily_df["Volume"].astype(float).iloc[-20:].mean()
        )

    progress = _idx_session_progress_fraction()
    projected_rvol = None
    if avg_daily_volume20 not in (None, 0):
        expected_volume_now = avg_daily_volume20 * progress
        if expected_volume_now > 0:
            projected_rvol = volume_today / expected_volume_now

    last_30m_return_pct = None
    intraday_volume_accel = None
    if len(today_frame) >= 7:
        base_price = safe_float(today_frame["Close"].iloc[-7])
        if base_price not in (None, 0) and current_price is not None:
            last_30m_return_pct = (
                (current_price / base_price) - 1
            ) * 100

    if len(today_frame) >= 12:
        recent_volume = safe_float(today_frame["Volume"].iloc[-6:].sum())
        prior_volume = safe_float(today_frame["Volume"].iloc[-12:-6].sum())
        if recent_volume is not None and prior_volume not in (None, 0):
            intraday_volume_accel = recent_volume / prior_volume

    return {
        "fresh": fresh,
        "age_minutes": round(age_minutes, 2),
        "source": source,
        "bar_at": last_ts.isoformat(),
        "price": current_price,
        "day_open": day_open,
        "day_high": day_high,
        "day_low": day_low,
        "volume_today": volume_today,
        "session_progress": round(progress, 4),
        "projected_rvol": safe_float(projected_rvol),
        "intraday_return_pct": safe_float(intraday_return_pct),
        "gap_pct": safe_float(gap_pct),
        "breakout_distance_pct": safe_float(breakout_distance_pct),
        "day_range_pct": safe_float(day_range_pct),
        "last_30m_return_pct": safe_float(last_30m_return_pct),
        "intraday_volume_accel": safe_float(intraday_volume_accel),
        "ema20": ema20,
        "prior_high20": prior_high20,
    }


def predictive_radar_signal(daily, weekly, snapshot):
    """
    Leading-condition score.

    Goal: identify improving structure BEFORE a textbook breakout becomes
    obvious, while remaining explicitly NON-ACTIONABLE until post-close
    completed-bar reconfirmation.
    """
    base = early_signal_score(daily, weekly)
    score = int(base.get("score") or 0)
    evidence = list(base.get("evidence") or [])

    if not snapshot.get("fresh"):
        return {
            "state": "NO_SETUP",
            "score": min(score, 10),
            "evidence": evidence + [
                f"RADAR_INTERNAL: stale intraday feed ({snapshot.get('age_minutes')}m)"
            ],
            "armed": False,
        }

    live_price = safe_float(snapshot.get("price"))
    ema20 = safe_float(snapshot.get("ema20"))
    distance = safe_float(snapshot.get("breakout_distance_pct"))
    pace = safe_float(snapshot.get("projected_rvol"))
    ret = safe_float(snapshot.get("intraday_return_pct"))
    ret30 = safe_float(snapshot.get("last_30m_return_pct"))
    vol_accel = safe_float(snapshot.get("intraday_volume_accel"))
    weekly_spread = safe_float(weekly.get("ema_spread_pct"))
    weekly_improve = safe_float(weekly.get("ema_spread_change_4w"))

    if live_price is not None and ema20 is not None and live_price >= ema20:
        score += 1
        evidence.append("RADAR: live price holding above EMA20")

    if distance is not None:
        if -1.0 <= distance <= RADAR_ARM_DISTANCE_PCT:
            score += 2
            evidence.append(
                f"RADAR: live price within {abs(distance):.2f}% of 20d trigger"
            )
        elif 0 <= distance <= EARLY_BREAKOUT_DISTANCE_PCT:
            score += 1
            evidence.append(
                f"RADAR: approaching trigger ({distance:.2f}% away)"
            )

    if pace is not None:
        if pace >= 1.50:
            score += 2
            evidence.append(f"RADAR: projected volume pace {pace:.2f}x")
        elif pace >= 1.10:
            score += 1
            evidence.append(f"RADAR: projected volume pace {pace:.2f}x")

    if ret is not None and 0.40 <= ret <= 5.0:
        score += 1
        evidence.append(f"RADAR: session momentum +{ret:.2f}%")

    if ret30 is not None and ret30 >= 0.30:
        score += 1
        evidence.append(f"RADAR: 30m price acceleration +{ret30:.2f}%")

    if vol_accel is not None and vol_accel >= 1.20:
        score += 1
        evidence.append(f"RADAR: intraday volume acceleration {vol_accel:.2f}x")

    if (
        (weekly_spread is not None and weekly_spread > 0)
        or (weekly_improve is not None and weekly_improve > 0)
    ):
        score += 1
        evidence.append("RADAR: weekly structure supportive")

    score = min(score, 10)

    state = "NO_SETUP"
    if score >= RADAR_WATCH_SCORE:
        state = "RADAR_WATCH"
    if score >= RADAR_PRE_ALERT_SCORE:
        state = "RADAR_PRE_ALERT"

    armed = (
        score >= RADAR_ARMED_SCORE
        and distance is not None
        and -1.0 <= distance <= RADAR_ARM_DISTANCE_PCT
        and pace is not None
        and pace >= RADAR_MIN_VOLUME_PACE
    )
    if armed:
        state = "RADAR_ARMED"

    evidence.append(
        "RADAR_INTERNAL_ONLY: never actionable; waits for completed daily-bar reconfirmation"
    )

    return {
        "state": state,
        "score": score,
        "evidence": evidence,
        "armed": armed,
    }


def early_signal_score(daily, weekly):
    """Leading score; never actionable by itself."""
    score = 0
    evidence = []

    price = safe_float(daily.get("price"))
    ema20 = safe_float(daily.get("ema20"))
    rsi_d = safe_float(daily.get("rsi14"))
    rsi_change = safe_float(daily.get("rsi_change_5d"))
    ema_slope = safe_float(daily.get("ema20_slope_5d_pct"))
    rvol = safe_float(daily.get("rvol20"))
    vol_accel = safe_float(daily.get("volume_accel_5d"))
    ret5 = safe_float(daily.get("ret5_pct"))
    distance = safe_float(daily.get("breakout_distance_pct"))

    weekly_rsi = safe_float(weekly.get("rsi14"))
    weekly_spread = safe_float(weekly.get("ema_spread_pct"))
    weekly_improve = safe_float(weekly.get("ema_spread_change_4w"))

    if price is not None and ema20 is not None and price >= ema20:
        score += 1
        evidence.append("price holding/reclaiming EMA20")

    if ema_slope is not None and ema_slope > 0:
        score += 1
        evidence.append(f"EMA20 5d slope +{ema_slope:.2f}%")

    if rsi_d is not None and 45 <= rsi_d <= 68:
        score += 1
        evidence.append(f"daily RSI constructive {rsi_d:.1f}")

    if rsi_change is not None and rsi_change >= 3:
        score += 1
        evidence.append(f"RSI improving +{rsi_change:.1f} in 5d")

    if ret5 is not None and ret5 > 0:
        score += 1
        evidence.append(f"5d momentum +{ret5:.2f}%")

    if (rvol is not None and rvol >= 1.0) or (
        vol_accel is not None and vol_accel >= 1.20
    ):
        score += 1
        evidence.append(
            f"RVOL building {rvol:.2f}x"
            if rvol is not None and rvol >= 1.0
            else f"volume acceleration {vol_accel:.2f}x"
        )

    if distance is not None:
        if -0.5 <= distance <= SETUP_READY_BREAKOUT_DISTANCE_PCT:
            score += 2
            evidence.append(f"within {abs(distance):.2f}% of 20d trigger")
        elif 0 <= distance <= EARLY_BREAKOUT_DISTANCE_PCT:
            score += 1
            evidence.append(f"approaching 20d trigger ({distance:.2f}% away)")

    if (
        (weekly_spread is not None and weekly_spread > 0)
        or (weekly_improve is not None and weekly_improve > 0)
    ):
        score += 1
        evidence.append("weekly structure bullish/improving")

    if weekly_rsi is not None and weekly_rsi >= 45:
        score += 1
        evidence.append(f"weekly RSI supportive {weekly_rsi:.1f}")

    return {"score": min(score, 10), "evidence": evidence}


def fetch_prior_monitor(ticker):
    encoded = urllib.parse.quote(clean_ticker(ticker), safe="")
    rows = supabase_request(
        "GET",
        "hanz_swing_signal_monitor"
        f"?ticker=eq.{encoded}"
        "&select=ticker,state,score,price,breakout_level,daily_bar_at,updated_at"
        "&limit=1",
    ) or []
    return rows[0] if rows else None



def momentum_damage_guard(daily, prior_monitor=None):
    """Hard veto for failed breakouts and sharp short-term deterioration."""
    price = safe_float(daily.get("price"))
    ema20 = safe_float(daily.get("ema20"))
    ret1 = safe_float(daily.get("ret1_pct"))
    ret3 = safe_float(daily.get("ret3_pct"))
    ret5 = safe_float(daily.get("ret5_pct"))
    dd5 = safe_float(daily.get("drawdown_5d_high_pct"))
    dd10 = safe_float(daily.get("drawdown_10d_high_pct"))
    down_vol_ratio = safe_float(daily.get("down_volume_ratio_5d"))

    prior_state = str((prior_monitor or {}).get("state") or "").upper()
    prior_breakout = safe_float((prior_monitor or {}).get("breakout_level"))
    prior_price = safe_float((prior_monitor or {}).get("price"))

    reasons = []
    severe = False
    failed_breakout = False

    if (
        price is not None
        and prior_breakout not in (None, 0)
        and prior_state in {"SETUP_READY", "SWING_CONFIRMING", "SWING_BUY"}
        and price < prior_breakout * 0.98
    ):
        failed_breakout = True
        severe = True
        reasons.append(
            f"failed breakout: price {price:.2f} is >2% below prior trigger {prior_breakout:.2f}"
        )

    if ret5 is not None and ret5 <= -8.0:
        severe = True
        reasons.append(f"5-day momentum damaged ({ret5:.2f}%)")

    if ret3 is not None and ret3 <= -6.0:
        severe = True
        reasons.append(f"3-day momentum damaged ({ret3:.2f}%)")

    if dd10 is not None and dd10 >= 12.0:
        severe = True
        reasons.append(f"{dd10:.2f}% below 10-day high")

    if (
        price is not None
        and ema20 is not None
        and price < ema20
        and ret5 is not None
        and ret5 <= -5.0
    ):
        severe = True
        reasons.append("price below EMA20 while 5-day momentum is negative")

    if (
        ret1 is not None
        and ret1 <= -5.0
        and down_vol_ratio is not None
        and down_vol_ratio >= 1.5
    ):
        severe = True
        reasons.append(
            f"heavy downside pressure: 1D {ret1:.2f}% / down-volume ratio {down_vol_ratio:.2f}x"
        )

    caution = False
    if not severe:
        if ret5 is not None and ret5 <= -4.0:
            caution = True
            reasons.append(f"5-day momentum weakening ({ret5:.2f}%)")
        if dd5 is not None and dd5 >= 7.0:
            caution = True
            reasons.append(f"{dd5:.2f}% below 5-day high")

    return {
        "blocked": severe,
        "caution": caution,
        "failed_breakout": failed_breakout,
        "reasons": reasons,
        "ret1_pct": ret1,
        "ret3_pct": ret3,
        "ret5_pct": ret5,
        "drawdown_5d_high_pct": dd5,
        "drawdown_10d_high_pct": dd10,
        "down_volume_ratio_5d": down_vol_ratio,
        "prior_breakout_level": prior_breakout,
        "prior_price": prior_price,
    }


def apply_early_state_and_reconfirmation(
    ticker, daily, weekly, base_result, prior_monitor
):
    """
    Progressive confirmation:
      EARLY_WATCH -> PRE_ALERT -> SETUP_READY
      -> EARLY_CONFIRMED_BUY (early reversal family)
      -> or SWING_BUY (trend continuation family)

    A BUY still requires a NEW completed daily bar after the setup was armed.
    The difference in V10.4 is that EARLY_REVERSAL does not wait for a full
    EMA20>EMA50 + weekly EMA10>EMA20 trend before it can confirm.
    """
    early = early_signal_score(daily, weekly)
    early_score = early["score"]

    prior_state = str((prior_monitor or {}).get("state") or "").upper()
    prior_bar = str((prior_monitor or {}).get("daily_bar_at") or "")
    current_bar = str(daily.get("bar_at") or "")
    new_completed_bar = bool(
        current_bar and prior_bar and current_bar != prior_bar
    )

    raw_buy = bool(base_result.get("hard_buy_gate"))
    early_raw_buy = bool(base_result.get("early_buy_gate"))

    momentum_guard = momentum_damage_guard(daily, prior_monitor)
    if momentum_guard.get("blocked"):
        raw_buy = False
        early_raw_buy = False

    distance = safe_float(daily.get("breakout_distance_pct"))
    state = "NO_SETUP"

    if early_score >= EARLY_WATCH_SCORE:
        state = "EARLY_WATCH"

    if (
        early_score >= PRE_ALERT_SCORE
        and distance is not None
        and distance <= EARLY_BREAKOUT_DISTANCE_PCT
    ):
        state = "PRE_ALERT"

    # Early-reversal setups can become READY based on location/structure,
    # even when still farther from the 20-day breakout level.
    if (
        base_result.get("setup_family") == "EARLY_REVERSAL"
        and base_result.get("early_location_ok")
        and base_result.get("early_structure_ok")
        and base_result.get("score", 0) >= max(5, MIN_CONFIRM_SCORE - 1)
    ):
        state = "SETUP_READY"
    elif (
        early_score >= SETUP_READY_SCORE
        and distance is not None
        and distance <= SETUP_READY_BREAKOUT_DISTANCE_PCT
        and base_result.get("score", 0) >= MIN_CONFIRM_SCORE
    ):
        state = "SETUP_READY"

    if raw_buy:
        if early_raw_buy:
            previously_armed = prior_state in {
                "EARLY_WATCH",
                "PRE_ALERT",
                "RADAR_PRE_ALERT",
                "RADAR_ARMED",
                "SETUP_READY",
                "SWING_CONFIRMING",
                "EARLY_CONFIRMED_BUY",
            }
            if prior_state == "EARLY_CONFIRMED_BUY":
                state = "EARLY_CONFIRMED_BUY"
            elif previously_armed and new_completed_bar:
                state = "EARLY_CONFIRMED_BUY"
            else:
                state = "SETUP_READY"
        else:
            previously_armed = prior_state in {
                "RADAR_ARMED",
                "SETUP_READY",
                "SWING_CONFIRMING",
                "SWING_BUY",
                "EARLY_CONFIRMED_BUY",
            }
            if prior_state == "SWING_BUY":
                state = "SWING_BUY"
            elif previously_armed and new_completed_bar:
                state = "SWING_BUY"
            else:
                state = "SETUP_READY"

    if momentum_guard.get("blocked"):
        state = "MOMENTUM_BROKEN"
    elif momentum_guard.get("caution") and state in BUY_STATES:
        state = "SETUP_READY"

    evidence = list(base_result.get("evidence") or [])
    evidence.extend(f"EARLY:{x}" for x in early["evidence"])

    if momentum_guard.get("blocked"):
        evidence.extend(
            f"MOMENTUM_GUARD: {reason}"
            for reason in momentum_guard.get("reasons", [])
        )
        evidence.append(
            "FINAL_ACTION: BUY blocked until a fresh setup is reconfirmed"
        )
    elif momentum_guard.get("caution"):
        evidence.extend(
            f"MOMENTUM_CAUTION: {reason}"
            for reason in momentum_guard.get("reasons", [])
        )

    if raw_buy and state not in BUY_STATES:
        evidence.append(
            "RECONFIRM: BUY hierarchy passed; waiting next completed daily bar"
        )
    elif state == "EARLY_CONFIRMED_BUY":
        evidence.append(
            "RECONFIRM: early bullish transition persisted on a new completed daily bar before full trend expansion"
        )
    elif state == "SWING_BUY":
        evidence.append(
            "RECONFIRM: trend-continuation BUY gate persisted on a new completed daily bar"
        )

    out = dict(base_result)
    out["state"] = state
    out["early_score"] = early_score
    out["early_evidence"] = early["evidence"]
    out["raw_buy_gate"] = raw_buy
    out["reconfirmed"] = state in BUY_STATES
    out["momentum_guard"] = momentum_guard
    out["final_action"] = (
        "AVOID"
        if state == "MOMENTUM_BROKEN"
        else ("BUY" if state in BUY_STATES else "WAIT")
    )
    out["evidence"] = evidence
    return out


def foreign_flow_snapshot(ticker):
    """Per-ticker foreign flow from Supabase; missing data => UNKNOWN."""
    empty={"status":"UNKNOWN","score":0,"available":False,"net_1d":None,"net_3d":None,"net_5d":None,"net_pct_1d":None,"net_pct_3d":None,"net_pct_5d":None,"buy_days_5d":0,"sell_days_5d":0,"reason":"Foreign-flow data unavailable."}
    if not FOREIGN_FLOW_ENABLED:
        out=dict(empty); out.update(status="DISABLED",reason="Foreign-flow layer disabled."); return out
    try:
        enc=urllib.parse.quote(clean_ticker(ticker),safe="")
        rows=supabase_request("GET","hanz_foreign_flow_daily"+f"?ticker=eq.{enc}"+"&select=trade_date,foreign_net_value,total_value,foreign_buy_value,foreign_sell_value"+"&order=trade_date.desc"+f"&limit={max(FOREIGN_FLOW_LOOKBACK_DAYS,5)}") or []
    except Exception as exc:
        out=dict(empty); out["reason"]=f"Foreign-flow query unavailable: {exc}"; return out
    if not rows:
        out=dict(empty); out["reason"]="No foreign-flow rows for ticker."; return out
    def sums(n):
        s=rows[:n]; net=sum(safe_float(r.get("foreign_net_value")) or 0.0 for r in s); tv=sum(safe_float(r.get("total_value")) or 0.0 for r in s); return net,(net/tv*100.0 if tv>0 else None)
    net1,p1=sums(1); net3,p3=sums(min(3,len(rows))); net5,p5=sums(min(5,len(rows)))
    bd=sum(1 for r in rows[:5] if (safe_float(r.get("foreign_net_value")) or 0)>0); sd=sum(1 for r in rows[:5] if (safe_float(r.get("foreign_net_value")) or 0)<0)
    status="NEUTRAL"; score=0; reason="Foreign flow neutral / inconclusive."
    if p5 is not None and p5>=FOREIGN_FLOW_STRONG_BUY_PCT and bd>=FOREIGN_FLOW_CONFIRM_DAYS: status,score,reason="ACCUMULATING",12,"5D foreign accumulation."
    elif p3 is not None and p3>=FOREIGN_FLOW_STRONG_BUY_PCT: status,score,reason="ACCUMULATING",9,"3D foreign accumulation."
    elif p5 is not None and p5<=FOREIGN_FLOW_STRONG_SELL_PCT and sd>=FOREIGN_FLOW_CONFIRM_DAYS: status,score,reason="DISTRIBUTING",-12,"5D foreign distribution."
    elif p3 is not None and p3<=FOREIGN_FLOW_WARN_SELL_PCT and sd>=FOREIGN_FLOW_CONFIRM_DAYS: status,score,reason="DISTRIBUTION_WATCH",-7,"Multi-day foreign net sell."
    elif p1 is not None and p1<=FOREIGN_FLOW_WARN_SELL_PCT: status,score,reason="CAUTION",-3,"1D foreign net sell."
    elif p1 is not None and p1>0: status,score,reason="MILD_ACCUMULATION",3,"1D foreign net buy."
    return {"status":status,"score":score,"available":True,"net_1d":safe_float(net1),"net_3d":safe_float(net3),"net_5d":safe_float(net5),"net_pct_1d":safe_float(p1),"net_pct_3d":safe_float(p3),"net_pct_5d":safe_float(p5),"buy_days_5d":bd,"sell_days_5d":sd,"reason":reason}

def apply_foreign_flow_to_risk_validation(risk_validation,foreign_flow):
    out=dict(risk_validation or {}); ff=dict(foreign_flow or {})
    for k,v in {"foreign_flow_status":"status","foreign_flow_score":"score","foreign_net_1d":"net_1d","foreign_net_3d":"net_3d","foreign_net_5d":"net_5d","foreign_net_pct_1d":"net_pct_1d","foreign_net_pct_3d":"net_pct_3d","foreign_net_pct_5d":"net_pct_5d","foreign_buy_days_5d":"buy_days_5d","foreign_sell_days_5d":"sell_days_5d","foreign_flow_reason":"reason"}.items(): out[k]=ff.get(v)
    out["score"]=int(max(0,min(100,round((safe_float(out.get("score")) or 0)+(safe_float(ff.get("score")) or 0)))))
    cautions=list(out.get("cautions") or []); status=str(ff.get("status") or "").upper()
    if status in {"DISTRIBUTING","DISTRIBUTION_WATCH"} and "FOREIGN_DISTRIBUTION" not in cautions: cautions.append("FOREIGN_DISTRIBUTION")
    out["cautions"]=cautions; return out

def foreign_exit_overlay(position,daily,foreign_flow):
    """Foreign sell = prepare-exit warning; price/structure confirms actual SELL."""
    status=str((foreign_flow or {}).get("status") or "UNKNOWN").upper(); close=safe_float(daily.get("price")); ema20=safe_float(daily.get("ema20")); prior_low20=safe_float(daily.get("prior_low20")); pnl=safe_float(position.get("last_pnl_pct"))
    if status=="DISTRIBUTING":
        if close is not None and prior_low20 is not None and close<prior_low20: return {"signal":"CONFIRMED_SELL","priority":96,"reason":"Foreign distribution confirmed by daily support breakdown."}
        if close is not None and ema20 is not None and close<ema20: return {"signal":"PROTECT_PROFIT" if (pnl is not None and pnl>0) else "DISTRIBUTION_WATCH","priority":82,"reason":"Heavy foreign distribution + close below EMA20. Prepare exit / tighten risk."}
        return {"signal":"DISTRIBUTION_WATCH","priority":70,"reason":"Heavy foreign net sell. Prepare exit; wait for price/structure confirmation."}
    if status=="DISTRIBUTION_WATCH": return {"signal":"DISTRIBUTION_WATCH","priority":60,"reason":"Multi-day foreign net sell detected. Tighten monitoring."}
    if status=="CAUTION": return {"signal":"FOREIGN_SELL_CAUTION","priority":45,"reason":"One-day foreign net sell. Early warning only."}
    return None


def insider_disclosure_snapshot(ticker):
    """Summarize ONLY verified public insider disclosures from Supabase."""
    empty = {
        "status":"UNKNOWN","score":0,"available":False,
        "buy_count_30d":0,"sell_count_30d":0,
        "buy_count_90d":0,"sell_count_90d":0,
        "buy_value_90d":0.0,"sell_value_90d":0.0,
        "distinct_buyers_90d":0,"distinct_sellers_90d":0,
        "latest_action":None,"latest_disclosure_date":None,
        "reason":"Public insider disclosure data unavailable."
    }
    if not INSIDER_DISCLOSURE_ENABLED:
        out=dict(empty); out.update(status="DISABLED",reason="Public insider disclosure layer disabled."); return out
    try:
        enc=urllib.parse.quote(clean_ticker(ticker),safe="")
        rows=supabase_request(
            "GET",
            "hanz_insider_activity"
            f"?ticker=eq.{enc}"
            "&verified_public=eq.true"
            "&select=disclosure_date,transaction_date,insider_name,role,action,shares,price,transaction_value,ownership_after,source_name,source_url"
            "&order=disclosure_date.desc&limit=100"
        ) or []
    except Exception as exc:
        out=dict(empty); out["reason"]=f"Public insider query unavailable: {exc}"; return out
    if not rows:
        out=dict(empty); out["reason"]="No verified public insider disclosures stored for ticker."; return out

    today=jakarta_now().date()
    def row_date(r):
        for key in ("transaction_date","disclosure_date"):
            try:
                if r.get(key): return pd.Timestamp(r.get(key)).date()
            except Exception:
                pass
        return None
    def act(r): return str(r.get("action") or "").strip().upper()
    def val(r):
        v=safe_float(r.get("transaction_value"))
        if v is not None: return max(0.0,v)
        sh=safe_float(r.get("shares")); px=safe_float(r.get("price"))
        return max(0.0,(sh or 0.0)*(px or 0.0))

    r90=[]; r30=[]
    for r in rows:
        d=row_date(r)
        if d is None: continue
        age=(today-d).days
        if 0 <= age <= INSIDER_LOOKBACK_DAYS:
            r90.append(r)
            if age <= INSIDER_RECENT_DAYS: r30.append(r)

    b90=[r for r in r90 if act(r)=="BUY"]; s90=[r for r in r90 if act(r)=="SELL"]
    b30=[r for r in r30 if act(r)=="BUY"]; s30=[r for r in r30 if act(r)=="SELL"]
    bv=sum(val(r) for r in b90); sv=sum(val(r) for r in s90)
    buyers={str(r.get("insider_name") or "").strip().lower() for r in b90 if str(r.get("insider_name") or "").strip()}
    sellers={str(r.get("insider_name") or "").strip().lower() for r in s90 if str(r.get("insider_name") or "").strip()}

    status="NEUTRAL"; score=0; reason="No decisive public insider accumulation/distribution signal."
    if len(b90)>=INSIDER_REPEAT_COUNT and bv>=INSIDER_MIN_VALUE_IDR and bv>max(sv*2.0,INSIDER_MIN_VALUE_IDR):
        status="STRONG_INSIDER_BUY"; score=12 if len(buyers)>=2 else 10
        reason="Multiple/repeated verified public insider purchases." if len(buyers)>=2 else "Repeated verified public insider purchases."
    elif b90 and bv>=INSIDER_MIN_VALUE_IDR and bv>sv:
        status,score,reason="INSIDER_BUY",6,"Verified public insider buying exceeds insider selling."
    elif len(s90)>=INSIDER_REPEAT_COUNT and sv>=INSIDER_MIN_VALUE_IDR and sv>max(bv*2.0,INSIDER_MIN_VALUE_IDR):
        status="HEAVY_INSIDER_SELL"; score=-12 if len(sellers)>=2 else -10
        reason="Multiple/repeated verified public insider sales." if len(sellers)>=2 else "Repeated verified public insider sales."
    elif s90 and sv>=INSIDER_MIN_VALUE_IDR and sv>bv:
        status,score,reason="INSIDER_SELL",-5,"Verified public insider selling exceeds insider buying."

    latest=rows[0]
    return {
        "status":status,"score":score,"available":True,
        "buy_count_30d":len(b30),"sell_count_30d":len(s30),
        "buy_count_90d":len(b90),"sell_count_90d":len(s90),
        "buy_value_90d":safe_float(bv),"sell_value_90d":safe_float(sv),
        "distinct_buyers_90d":len(buyers),"distinct_sellers_90d":len(sellers),
        "latest_action":act(latest) or None,
        "latest_disclosure_date":latest.get("disclosure_date"),
        "reason":reason
    }


def apply_insider_to_risk_validation(risk_validation,insider):
    out=dict(risk_validation or {}); ins=dict(insider or {})
    mp={
        "insider_status":"status","insider_score":"score",
        "insider_buy_count_30d":"buy_count_30d","insider_sell_count_30d":"sell_count_30d",
        "insider_buy_count_90d":"buy_count_90d","insider_sell_count_90d":"sell_count_90d",
        "insider_buy_value_90d":"buy_value_90d","insider_sell_value_90d":"sell_value_90d",
        "insider_distinct_buyers_90d":"distinct_buyers_90d","insider_distinct_sellers_90d":"distinct_sellers_90d",
        "insider_latest_action":"latest_action","insider_latest_disclosure_date":"latest_disclosure_date",
        "insider_reason":"reason"
    }
    for k,v in mp.items(): out[k]=ins.get(v)
    # Confirmation/ranking only; cannot bypass a failed technical/risk gate.
    out["score"]=int(max(0,min(100,round((safe_float(out.get("score")) or 0)+(safe_float(ins.get("score")) or 0)))))
    cautions=list(out.get("cautions") or [])
    if str(ins.get("status") or "").upper() in {"INSIDER_SELL","HEAVY_INSIDER_SELL"} and "PUBLIC_INSIDER_SELLING" not in cautions:
        cautions.append("PUBLIC_INSIDER_SELLING")
    out["cautions"]=cautions
    return out


def insider_exit_overlay(position,daily,insider):
    """Public insider selling is a warning layer, never a standalone confirmed SELL."""
    status=str((insider or {}).get("status") or "UNKNOWN").upper()
    close=safe_float(daily.get("price")); ema20=safe_float(daily.get("ema20"))
    pnl=safe_float(position.get("last_pnl_pct"))
    if status=="HEAVY_INSIDER_SELL":
        if close is not None and ema20 is not None and close<ema20:
            return {"signal":"PROTECT_PROFIT" if (pnl is not None and pnl>0) else "INSIDER_SELL_CAUTION","priority":78,"reason":"Repeated public insider selling + close below EMA20. Tighten risk."}
        return {"signal":"INSIDER_SELL_CAUTION","priority":58,"reason":"Repeated public insider selling disclosed. Prepare exit; wait for price/structure confirmation."}
    if status=="INSIDER_SELL":
        return {"signal":"INSIDER_SELL_CAUTION","priority":42,"reason":"Public insider selling disclosed. Warning only; no automatic sell."}
    return None


def broker_flow_snapshot(ticker):
    """Summarize broker activity from hanz_broker_flow_daily.

    IMPORTANT:
    A broker code is an intermediary and can represent many unrelated clients.
    Therefore this layer is confirmation/ranking only, never proof of insider/smart money.

    Expected rows (one broker per ticker/date):
      ticker, trade_date, broker_code,
      buy_value, sell_value, buy_volume, sell_volume,
      avg_buy_price, avg_sell_price, source, verified_public
    """
    empty = {
        "status": "UNKNOWN", "score": 0, "available": False,
        "net_1d": 0.0, "net_3d": 0.0, "net_5d": 0.0,
        "net_pct_1d": None, "net_pct_3d": None, "net_pct_5d": None,
        "buy_days_5d": 0, "sell_days_5d": 0,
        "top_buyers": [], "top_sellers": [],
        "buyer_concentration_pct": None, "seller_concentration_pct": None,
        "weighted_avg_buy_price_5d": None,
        "reason": "Broker-flow data unavailable.",
    }
    if not BROKER_FLOW_ENABLED:
        out = dict(empty)
        out.update(status="DISABLED", reason="Broker-flow layer disabled.")
        return out
    try:
        enc = urllib.parse.quote(clean_ticker(ticker), safe="")
        rows = supabase_request(
            "GET",
            "hanz_broker_flow_daily"
            f"?ticker=eq.{enc}"
            "&verified_public=eq.true"
            "&select=trade_date,broker_code,buy_value,sell_value,buy_volume,sell_volume,avg_buy_price,avg_sell_price,source"
            "&order=trade_date.desc"
            "&limit=250",
        ) or []
    except Exception as exc:
        out = dict(empty)
        out["reason"] = f"Broker-flow query unavailable: {exc}"
        return out

    if not rows:
        out = dict(empty)
        out["reason"] = "No verified broker-flow rows stored for ticker."
        return out

    # Group by latest distinct trade dates.
    by_date = {}
    for r in rows:
        d = str(r.get("trade_date") or "")[:10]
        if not d:
            continue
        by_date.setdefault(d, []).append(r)
    dates = sorted(by_date.keys(), reverse=True)[:max(1, BROKER_LOOKBACK_DAYS)]
    if not dates:
        return empty

    def n(v): return safe_float(v) or 0.0
    daily = []
    broker_net_5d = {}
    broker_buy_value_5d = {}
    buy_px_num = 0.0
    buy_px_den = 0.0

    for d in dates:
        items = by_date[d]
        buy = sum(n(x.get("buy_value")) for x in items)
        sell = sum(n(x.get("sell_value")) for x in items)
        total = buy + sell
        net = buy - sell
        daily.append({"date": d, "buy": buy, "sell": sell, "total": total, "net": net})

        for x in items:
            b = n(x.get("buy_value")); s = n(x.get("sell_value"))
            code = str(x.get("broker_code") or "?").strip().upper()
            broker_net_5d[code] = broker_net_5d.get(code, 0.0) + b - s
            broker_buy_value_5d[code] = broker_buy_value_5d.get(code, 0.0) + b
            vol = n(x.get("buy_volume"))
            px = safe_float(x.get("avg_buy_price"))
            if vol > 0 and px is not None:
                buy_px_num += vol * px
                buy_px_den += vol

    def window(k):
        w = daily[:k]
        net = sum(x["net"] for x in w)
        total = sum(x["total"] for x in w)
        pct = (100.0 * net / total) if total > 0 else None
        return net, pct

    net1, p1 = window(1)
    net3, p3 = window(min(3, len(daily)))
    net5, p5 = window(min(5, len(daily)))
    buy_days = sum(1 for x in daily[:5] if x["net"] > 0)
    sell_days = sum(1 for x in daily[:5] if x["net"] < 0)

    buyers = sorted(
        ((k, v) for k, v in broker_net_5d.items() if v > 0),
        key=lambda kv: kv[1], reverse=True
    )[:3]
    sellers = sorted(
        ((k, -v) for k, v in broker_net_5d.items() if v < 0),
        key=lambda kv: kv[1], reverse=True
    )[:3]
    positive_total = sum(v for v in broker_net_5d.values() if v > 0)
    negative_total = sum(-v for v in broker_net_5d.values() if v < 0)
    buyer_conc = (100.0 * sum(v for _, v in buyers) / positive_total) if positive_total > 0 else None
    seller_conc = (100.0 * sum(v for _, v in sellers) / negative_total) if negative_total > 0 else None

    status, score = "NEUTRAL", 0
    reason = "Broker activity is mixed/neutral."
    if p5 is not None and p5 >= BROKER_STRONG_NET_PCT_5D and buy_days >= BROKER_CONFIRM_DAYS:
        status, score = "BROKER_ACCUMULATING", 8
        reason = "Persistent multi-day broker net accumulation."
        if buyer_conc is not None and buyer_conc >= BROKER_CONCENTRATION_BONUS_PCT:
            score = 9
            reason += " Top buyers are concentrated."
    elif p3 is not None and p3 >= BROKER_WARNING_NET_PCT_5D and buy_days >= 2:
        status, score, reason = "BROKER_ACCUMULATION_WATCH", 4, "Broker net buying is building but not fully confirmed."
    elif p5 is not None and p5 <= -BROKER_STRONG_NET_PCT_5D and sell_days >= BROKER_CONFIRM_DAYS:
        status, score = "BROKER_DISTRIBUTING", -8
        reason = "Persistent multi-day broker net distribution."
        if seller_conc is not None and seller_conc >= BROKER_CONCENTRATION_BONUS_PCT:
            score = -9
            reason += " Top sellers are concentrated."
    elif p3 is not None and p3 <= -BROKER_WARNING_NET_PCT_5D and sell_days >= 2:
        status, score, reason = "BROKER_DISTRIBUTION_WATCH", -4, "Broker net selling is building; early caution."

    return {
        "status": status, "score": int(score), "available": True,
        "net_1d": safe_float(net1), "net_3d": safe_float(net3), "net_5d": safe_float(net5),
        "net_pct_1d": safe_float(p1), "net_pct_3d": safe_float(p3), "net_pct_5d": safe_float(p5),
        "buy_days_5d": buy_days, "sell_days_5d": sell_days,
        "top_buyers": [{"broker": k, "net_value": safe_float(v)} for k, v in buyers],
        "top_sellers": [{"broker": k, "net_value": safe_float(v)} for k, v in sellers],
        "buyer_concentration_pct": safe_float(buyer_conc),
        "seller_concentration_pct": safe_float(seller_conc),
        "weighted_avg_buy_price_5d": safe_float(buy_px_num / buy_px_den) if buy_px_den > 0 else None,
        "reason": reason,
    }


def apply_broker_flow_to_risk_validation(risk_validation, broker_flow):
    out = dict(risk_validation or {})
    bf = dict(broker_flow or {})
    mapping = {
        "broker_flow_status":"status","broker_flow_score":"score",
        "broker_net_1d":"net_1d","broker_net_3d":"net_3d","broker_net_5d":"net_5d",
        "broker_net_pct_1d":"net_pct_1d","broker_net_pct_3d":"net_pct_3d","broker_net_pct_5d":"net_pct_5d",
        "broker_buy_days_5d":"buy_days_5d","broker_sell_days_5d":"sell_days_5d",
        "broker_top_buyers":"top_buyers","broker_top_sellers":"top_sellers",
        "broker_buyer_concentration_pct":"buyer_concentration_pct",
        "broker_seller_concentration_pct":"seller_concentration_pct",
        "broker_weighted_avg_buy_price_5d":"weighted_avg_buy_price_5d",
        "broker_flow_reason":"reason",
    }
    for out_key, in_key in mapping.items():
        out[out_key] = bf.get(in_key)

    # Smaller weight than foreign + public insider; broker identity is not investor identity.
    out["score"] = int(max(0, min(100, round(
        (safe_float(out.get("score")) or 0) + (safe_float(bf.get("score")) or 0)
    ))))
    cautions = list(out.get("cautions") or [])
    if str(bf.get("status") or "").upper() in {"BROKER_DISTRIBUTING","BROKER_DISTRIBUTION_WATCH"}:
        if "BROKER_DISTRIBUTION" not in cautions:
            cautions.append("BROKER_DISTRIBUTION")
    out["cautions"] = cautions
    return out


def broker_exit_overlay(position, daily, broker_flow):
    """Broker distribution is only an early warning; price/structure remains decisive."""
    status = str((broker_flow or {}).get("status") or "UNKNOWN").upper()
    close = safe_float(daily.get("price"))
    ema20 = safe_float(daily.get("ema20"))
    if status == "BROKER_DISTRIBUTING":
        if close is not None and ema20 is not None and close < ema20:
            return {
                "signal":"BROKER_DISTRIBUTION_WATCH","priority":68,
                "reason":"Persistent broker distribution + close below EMA20. Tighten risk."
            }
        return {
            "signal":"BROKER_DISTRIBUTION_WATCH","priority":52,
            "reason":"Persistent broker distribution. Prepare exit; wait for technical confirmation."
        }
    if status == "BROKER_DISTRIBUTION_WATCH":
        return {
            "signal":"BROKER_DISTRIBUTION_WATCH","priority":38,
            "reason":"Broker selling is building. Early warning only."
        }
    return None



def canonical_rank_score(result, risk_validation):
    """Single frozen ranking score used by all HANZ views.

    Formula is intentionally identical to the previous dashboard ranking:
      technical swing score (0..10)*10
      + foreign-flow adjustment
      + public-insider adjustment
      + broker-flow adjustment
    clamped to 0..100.

    IMPORTANT: this ranking cannot create a BUY. State/actionability remain
    controlled only by the existing engine gates and reconfirmation logic.
    """
    technical = max(
        0.0,
        min(10.0, safe_float((result or {}).get("score")) or 0.0),
    ) * 10.0
    foreign = safe_float((risk_validation or {}).get("foreign_flow_score")) or 0.0
    insider = safe_float((risk_validation or {}).get("insider_score")) or 0.0
    broker = safe_float((risk_validation or {}).get("broker_flow_score")) or 0.0
    return int(
        max(
            0,
            min(
                100,
                round(technical + foreign + insider + broker),
            ),
        )
    )


def swing_score(daily, weekly):
    """Book-guided hierarchy with three explicit setup families.

    1) EARLY_REVERSAL:
       accumulation/base -> location -> structure shift -> price/candle trigger
       -> volume/selling-pressure check -> risk.
       Full EMA bullish alignment is NOT required.

    2) BREAKOUT:
       established bullish context -> fresh resistance break -> volume.

    3) PULLBACK_RETEST:
       established bullish context -> support/retest location -> reversal trigger.

    Candles/indicators are contextual. No candle alone can create a BUY.
    V10.4 early thresholds are research hypotheses and must be validated on IDX.
    """
    evidence = []
    score = 0

    price = safe_float(daily.get("price"))
    ema20 = safe_float(daily.get("ema20"))
    ema50 = safe_float(daily.get("ema50"))
    ema20_slope = safe_float(daily.get("ema20_slope_5d_pct"))
    weekly_ema10 = safe_float(weekly.get("ema10"))
    weekly_ema20 = safe_float(weekly.get("ema20"))
    weekly_rsi = safe_float(weekly.get("rsi14"))

    structure = str(daily.get("structure_state") or "UNKNOWN").upper()
    last_high = safe_float(daily.get("last_swing_high"))
    last_low = safe_float(daily.get("last_swing_low"))
    prev_low = safe_float(daily.get("prev_swing_low"))

    prior_high20 = safe_float(daily.get("prior_high20"))
    prior_low20 = safe_float(daily.get("prior_low20"))
    prior_high3 = safe_float(daily.get("prior_high3"))
    prior_low10 = safe_float(daily.get("prior_low10"))
    atr14 = safe_float(daily.get("atr14"))
    rvol = safe_float(daily.get("rvol20"))
    down_vol_ratio = safe_float(daily.get("down_volume_ratio_5d"))
    close_location = safe_float(daily.get("close_location"))
    candle = str(daily.get("candle_context") or "NEUTRAL").upper()
    ret1 = safe_float(daily.get("ret1_pct"))
    ret3 = safe_float(daily.get("ret3_pct"))
    ret5 = safe_float(daily.get("ret5_pct"))

    bullish_candle = candle in {
        "BULLISH_ENGULFING",
        "HAMMER_REJECTION",
        "STRONG_BULL_CLOSE",
        "BULLISH_CANDLE",
    }

    daily_trend = (
        ema20 is not None
        and ema50 is not None
        and ema20 > ema50
    )
    weekly_trend = (
        weekly_ema10 is not None
        and weekly_ema20 is not None
        and weekly_ema10 > weekly_ema20
    )
    trend_context = daily_trend and weekly_trend
    structure_ok = structure in {"BULLISH_HH_HL", "MIXED"}

    # ------------------------------------------------------------
    # Family 0: EARLY REVERSAL / ACCUMULATION TRANSITION
    # ------------------------------------------------------------
    # Goal: confirm a bullish transition BEFORE full trend expansion,
    # without guessing a bottom.
    support_candidates = [
        x for x in (last_low, prior_low10, prior_low20, ema20)
        if x is not None and price is not None and x <= price
    ]
    support_distance_atr = None
    if support_candidates and atr14 not in (None, 0) and price is not None:
        support_distance_atr = min(
            abs(price - s) / atr14 for s in support_candidates
        )
    near_support = (
        support_distance_atr is not None
        and support_distance_atr <= EARLY_SUPPORT_ATR
    )

    higher_low = (
        last_low is not None
        and prev_low is not None
        and last_low > prev_low
    )
    mixed_or_improving_structure = (
        structure == "MIXED"
        or higher_low
    )

    # Minor CHoCH proxy: close through the previous 3-session high,
    # which is deliberately earlier than the 20-day breakout gate.
    minor_structure_break = (
        price is not None
        and prior_high3 is not None
        and price > prior_high3
        and ret1 is not None
        and ret1 >= 0
    )

    trigger_quality = (
        bullish_candle
        and (minor_structure_break or higher_low)
        and (
            close_location is None
            or close_location >= EARLY_MIN_CLOSE_LOCATION
        )
    )

    selling_pressure_easing = (
        down_vol_ratio is None
        or down_vol_ratio <= EARLY_MAX_DOWN_VOLUME_RATIO_5D
    )

    ema_flattening = (
        ema20_slope is None
        or ema20_slope >= EARLY_EMA20_MIN_SLOPE_5D_PCT
    )

    weekly_not_broken = (
        weekly_ema10 is None
        or weekly_ema20 is None
        or weekly_ema10 >= weekly_ema20 * EARLY_WEEKLY_EMA_TOLERANCE
        or (weekly_rsi is not None and weekly_rsi >= 45)
    )

    not_extended = (
        (ret3 is None or ret3 <= EARLY_MAX_RET3_PCT)
        and (ret5 is None or ret5 <= EARLY_MAX_RET5_PCT)
        and (
            prior_high20 is None
            or price is None
            or price <= prior_high20
        )
    )

    early_location_ok = near_support and not_extended
    early_structure_ok = mixed_or_improving_structure
    early_volume_ok = selling_pressure_easing
    early_buy_gate = all([
        early_location_ok,
        early_structure_ok,
        trigger_quality,
        early_volume_ok,
        ema_flattening,
        weekly_not_broken,
    ])

    # ------------------------------------------------------------
    # Family A: fresh breakout / continuation
    # ------------------------------------------------------------
    breakout_level = max(
        [x for x in (prior_high20, last_high) if x is not None],
        default=None,
    )
    breakout = (
        price is not None
        and breakout_level is not None
        and price > breakout_level
    )
    near_breakout = False
    if price is not None and breakout_level not in (None, 0):
        dist = (breakout_level - price) / breakout_level * 100
        near_breakout = (
            0 <= dist <= SETUP_READY_BREAKOUT_DISTANCE_PCT
        )

    breakout_volume_ok = rvol is not None and rvol >= 1.0
    breakout_trigger = bool(
        breakout
        and ret1 is not None
        and ret1 > 0
    )

    # ------------------------------------------------------------
    # Family B: pullback/retest inside an established uptrend
    # ------------------------------------------------------------
    near_ema20 = False
    near_retest = False
    if price is not None and atr14 not in (None, 0):
        if ema20 is not None:
            near_ema20 = abs(price - ema20) <= 0.75 * atr14
        if last_high is not None:
            near_retest = (
                abs(price - last_high) <= 0.75 * atr14
                or (
                    price >= last_high
                    and price - last_high <= 0.75 * atr14
                )
            )

    pullback_location = (
        trend_context
        and structure_ok
        and (near_ema20 or near_retest)
    )
    pullback_trigger = bool(
        pullback_location
        and bullish_candle
        and ret1 is not None
        and ret1 >= 0
    )
    pullback_volume_ok = (
        rvol is None
        or rvol <= 1.20
        or (pullback_trigger and rvol >= 1.0)
    )

    setup_family = "NONE"
    hard_buy_gate = False
    location_ok = False
    trigger_confirmed = False
    volume_confirm = False

    # EARLY_REVERSAL is intentionally evaluated first because HANZ should
    # prefer a valid asymmetric entry before the stock becomes extended.
    if early_buy_gate:
        setup_family = "EARLY_REVERSAL"
        hard_buy_gate = True
        location_ok = True
        trigger_confirmed = True
        volume_confirm = True
    elif trend_context and structure_ok and breakout_trigger and breakout_volume_ok:
        setup_family = "BREAKOUT"
        hard_buy_gate = True
        location_ok = True
        trigger_confirmed = True
        volume_confirm = True
    elif trend_context and structure_ok and pullback_trigger and pullback_volume_ok:
        setup_family = "PULLBACK_RETEST"
        hard_buy_gate = True
        location_ok = True
        trigger_confirmed = True
        volume_confirm = True
    elif early_location_ok and early_structure_ok:
        setup_family = "EARLY_REVERSAL"
        location_ok = True
    elif trend_context and structure_ok and (near_breakout or pullback_location):
        setup_family = "BREAKOUT" if near_breakout else "PULLBACK_RETEST"
        location_ok = True

    # Diagnostic score: hierarchy still controls permission.
    if weekly_trend:
        score += 2
        evidence.append("weekly trend bullish")
    elif weekly_not_broken:
        score += 1
        evidence.append("weekly context not broken; full uptrend not required for early reversal")

    if daily_trend:
        score += 2
        evidence.append("daily trend bullish")
    elif ema_flattening:
        score += 1
        evidence.append("EMA20 flattening / downside momentum slowing")

    if structure == "BULLISH_HH_HL":
        score += 2
        evidence.append("confirmed swing structure HH/HL")
    elif structure == "MIXED":
        score += 1
        evidence.append("mixed structure: transition zone")
    elif structure == "BEARISH_LH_LL":
        evidence.append("confirmed LH/LL structure; early BUY requires evidence of improvement")

    if setup_family == "EARLY_REVERSAL":
        evidence.append("setup family EARLY_REVERSAL / accumulation transition")
        if near_support:
            score += 1
            evidence.append(
                f"early location near support ({support_distance_atr:.2f} ATR)"
            )
        if higher_low:
            score += 1
            evidence.append("structure shift: higher low detected")
        if minor_structure_break:
            score += 2
            evidence.append("minor CHoCH proxy: close above prior 3-session high")
        if bullish_candle:
            score += 1
            evidence.append(f"contextual bullish trigger: {candle}")
        if selling_pressure_easing:
            score += 1
            evidence.append("selling pressure/volume not expanding")
        if not_extended:
            evidence.append("early entry condition: price expansion not yet extended")

    elif setup_family == "BREAKOUT":
        evidence.append("setup family BREAKOUT")
        if breakout_trigger:
            score += 2
            evidence.append("price trigger: closes through resistance/swing high")
        elif near_breakout:
            score += 1
            evidence.append("location: near resistance trigger")
        if breakout_volume_ok:
            score += 1
            evidence.append(f"breakout volume confirms ({rvol:.2f}x)")

    elif setup_family == "PULLBACK_RETEST":
        evidence.append("setup family PULLBACK_RETEST")
        if near_ema20:
            evidence.append("location: pullback near EMA20 dynamic support")
        if near_retest:
            evidence.append("location: retest near prior swing-high support")
        if pullback_trigger:
            score += 2
            evidence.append(f"bullish price/candle trigger: {candle}")
        if pullback_volume_ok:
            score += 1
            evidence.append("pullback volume behavior acceptable")

    rsi_d = safe_float(daily.get("rsi14"))
    if rsi_d is not None:
        evidence.append(f"context RSI14 {rsi_d:.1f}")
    evidence.append(f"candle context {candle}")

    state = "NO_SETUP"
    if hard_buy_gate:
        # Final reconfirmation state is assigned by
        # apply_early_state_and_reconfirmation().
        state = "SWING_BUY"
    elif setup_family == "EARLY_REVERSAL" and location_ok:
        state = "SWING_CONFIRMING"
    elif trend_context and structure_ok and location_ok:
        state = "SWING_CONFIRMING"
    elif trend_context and structure_ok:
        state = "SWING_WATCH"

    return {
        "score": min(score, 10),
        "state": state,
        "daily_trend": "BULLISH" if daily_trend else "NOT_BULLISH",
        "weekly_trend": "BULLISH" if weekly_trend else "NOT_BULLISH",
        "structure_state": structure,
        "setup_family": setup_family,
        "breakout": breakout,
        "near_breakout": near_breakout,
        "pullback_location": pullback_location,
        "early_location_ok": early_location_ok,
        "early_structure_ok": early_structure_ok,
        "early_buy_gate": early_buy_gate,
        "minor_structure_break": minor_structure_break,
        "higher_low": higher_low,
        "support_distance_atr": safe_float(support_distance_atr),
        "trigger_confirmed": trigger_confirmed,
        "volume_confirm": volume_confirm,
        "hard_buy_gate": hard_buy_gate,
        "evidence": evidence,
    }


def risk_levels(
    daily,
    result=None,
    discount=None,
    fundamental=None,
):
    """Adaptive Swing entry + risk + dynamic take-profit plan.

    Entry:
    - uses completed daily close as reference
    - gives an entry zone, not a fake exact fill
    - avoids chasing excessively far above breakout/EMA20

    Targets:
    - based on actual risk (R), ATR, trend/score quality
    - nearby 52-week high can become a practical resistance target
    - T2 can stretch toward analyst mean only when it is reasonably close
    - after T1 the existing portfolio logic activates ATR trailing, so
      profit protection keeps moving dynamically with the trade.
    """
    price = safe_float(daily.get("price"))
    atr14 = safe_float(daily.get("atr14"))
    prior_low20 = safe_float(daily.get("prior_low20"))
    swing_low = safe_float(daily.get("last_swing_low"))
    breakout_level = safe_float(daily.get("last_swing_high")) or safe_float(daily.get("prior_high20"))
    ema20 = safe_float(daily.get("ema20"))
    week52_high = safe_float(daily.get("week52_high"))

    result = result or {}
    discount = discount or {}
    fundamental = fundamental or {}

    if (
        price is None
        or atr14 is None
        or atr14 <= 0
    ):
        return {
            "entry_price": None,
            "entry_low": None,
            "entry_high": None,
            "entry_status": "NO_DATA",
            "entry_note": "Insufficient price/ATR data",
            "stop_loss": None,
            "target_1": None,
            "target_2": None,
            "risk_per_share": None,
            "rr_target_1": None,
            "rr_target_2": None,
            "target_mode": None,
        }

    # -------------------------
    # STOP LOSS
    # -------------------------
    atr_stop = price - (2.0 * atr14)

    support_candidates = [x for x in (prior_low20, swing_low) if x is not None and x < price]
    if not support_candidates:
        stop = atr_stop
    else:
        stop = max([atr_stop] + support_candidates)

    if stop >= price:
        stop = atr_stop

    # -------------------------
    # ENTRY ZONE
    # -------------------------
    # Ideal entry is around the confirmed close / breakout retest.
    entry_price = price
    entry_low = price - (0.40 * atr14)
    entry_high = price + (0.25 * atr14)

    setup_family = str(result.get("setup_family") or "").upper()
    if breakout_level is not None and setup_family == "BREAKOUT":
        # For breakout setups, keep the lower edge around the reclaimed resistance.
        entry_low = max(entry_low, breakout_level)
    elif setup_family == "PULLBACK_RETEST" and ema20 is not None:
        # Pullback entries are centered around dynamic/structural support, not forced above breakout.
        entry_price = max(ema20, min(price, entry_price))
        entry_low = min(entry_low, entry_price - 0.20 * atr14)
        entry_high = max(entry_high, entry_price + 0.30 * atr14)
    elif setup_family == "EARLY_REVERSAL":
        # Early confirmation should keep the proposed entry near the base.
        # Never move the entry upward toward a later breakout.
        entry_price = price
        entry_low = price - (0.35 * atr14)
        entry_high = price + (0.15 * atr14)

    # Detect an overextended breakout so HANZ can say "wait pullback"
    # instead of encouraging a chase above the ideal swing zone.
    breakout_extension_atr = None
    if breakout_level is not None:
        breakout_extension_atr = (
            (price - breakout_level) / atr14
        )

    ema_extension_pct = None
    if ema20 not in (None, 0):
        ema_extension_pct = (
            (price - ema20) / ema20 * 100
        )

    if (
        (
            breakout_extension_atr is not None
            and breakout_extension_atr > 1.25
        )
        or (
            ema_extension_pct is not None
            and ema_extension_pct > 10
        )
    ):
        entry_status = "WAIT_PULLBACK"
        entry_price = max(
            breakout_level or (price - 0.75 * atr14),
            price - 0.75 * atr14,
        )
        entry_low = max(
            breakout_level or (entry_price - 0.25 * atr14),
            entry_price - 0.25 * atr14,
        )
        entry_high = entry_price + (0.25 * atr14)
        entry_note = (
            "SWING BUY confirmed, but price is extended. "
            "Prefer pullback into the entry zone; do not chase."
        )
    else:
        entry_status = "ENTRY_ZONE"
        entry_note = (
            "SWING BUY confirmed. Use the entry zone on the next "
            "trading session and avoid buying above the upper band."
        )

    # Risk is calculated from ideal/reference entry, not blindly from close.
    risk = entry_price - stop

    if risk <= 0:
        stop = entry_price - (2.0 * atr14)
        risk = entry_price - stop

    # -------------------------
    # DYNAMIC TARGET STRENGTH
    # -------------------------
    swing_score = safe_float(result.get("score")) or 0
    fundamental_score = safe_float(
        fundamental.get("fundamental_score")
    )
    discount_score = safe_float(
        discount.get("discount_score")
    )

    strength = 0

    if swing_score >= 9:
        strength += 2
    elif swing_score >= 8:
        strength += 1

    if result.get("weekly_trend") == "BULLISH":
        strength += 1

    if (
        fundamental_score is not None
        and fundamental_score >= 75
    ):
        strength += 1

    if (
        discount_score is not None
        and discount_score >= 70
    ):
        strength += 1

    # Stronger setups are allowed more room to run.
    if strength >= 5:
        t1_r = 2.0
        t2_r = 4.0
        target_mode = "STRONG_TREND"
    elif strength >= 3:
        t1_r = 1.8
        t2_r = 3.2
        target_mode = "QUALITY_TREND"
    else:
        t1_r = 1.5
        t2_r = 2.5
        target_mode = "STANDARD_SWING"

    t1 = entry_price + (t1_r * risk)
    t2 = entry_price + (t2_r * risk)

    # -------------------------
    # RESISTANCE-AWARE TARGETS
    # -------------------------
    # If 52W high is a realistic nearby resistance, use it rather than
    # blindly placing T1 beyond an obvious supply zone.
    if (
        week52_high is not None
        and week52_high > entry_price
    ):
        resistance_r = (
            (week52_high - entry_price) / risk
        )

        if 1.0 <= resistance_r <= (t1_r + 0.6):
            t1 = week52_high
            target_mode += "+52W_RESISTANCE"

        elif (
            resistance_r > t1_r
            and resistance_r <= (t2_r + 0.8)
        ):
            t2 = week52_high
            target_mode += "+52W_RESISTANCE"

    # Analyst mean is not treated as a guaranteed target.
    # It may extend T2 only if reasonably close to the technical target.
    analyst_target = safe_float(
        discount.get("analyst_target_mean")
    )

    if (
        analyst_target is not None
        and analyst_target > entry_price
        and analyst_target > t2
    ):
        analyst_r = (
            (analyst_target - entry_price) / risk
        )

        if analyst_r <= (t2_r + 1.0):
            t2 = analyst_target
            target_mode += "+ANALYST_CAP"

    # Ensure logical ordering.
    if t1 <= entry_price:
        t1 = entry_price + (1.5 * risk)

    if t2 <= t1:
        t2 = max(
            entry_price + (2.5 * risk),
            t1 + risk,
        )

    rr1 = (
        (t1 - entry_price) / risk
        if risk > 0
        else None
    )
    rr2 = (
        (t2 - entry_price) / risk
        if risk > 0
        else None
    )

    return {
        "entry_price": round(entry_price, 4),
        "entry_low": round(entry_low, 4),
        "entry_high": round(entry_high, 4),
        "entry_status": entry_status,
        "entry_note": entry_note,
        "stop_loss": round(stop, 4),
        "target_1": round(t1, 4),
        "target_2": round(t2, 4),
        "risk_per_share": round(risk, 4),
        "rr_target_1": (
            round(rr1, 2)
            if rr1 is not None
            else None
        ),
        "rr_target_2": (
            round(rr2, 2)
            if rr2 is not None
            else None
        ),
        "target_mode": target_mode,
    }




# ============================================================
# V10.1 REAL-MONEY RISK / VALIDATION LAYER
# Restores portfolio_risk_context() and closed_trade_performance_context()
# accidentally omitted during V10.0 book-guided refactor.
# ============================================================

def _position_quantity(position):
    qty = safe_float(position.get("quantity"))
    if qty is not None and qty > 0:
        return qty

    lots = safe_float(position.get("lots"))
    if lots is not None and lots > 0:
        return lots * 100.0

    return 0.0


def market_regime_context():
    """Broad IDX regime: price structure first, indicators as confirmation."""
    try:
        df=download_frame(MARKET_REGIME_TICKER,DAILY_INTERVAL,DAILY_PERIOD)
        if len(df)<80: raise RuntimeError("Insufficient IHSG history")
        close=df["Close"].astype(float); price=safe_float(close.iloc[-1])
        structure=_structure_from_pivots(df).get("state","UNKNOWN")
        ema20=safe_float(close.ewm(span=20,adjust=False).mean().iloc[-1]); ema50=safe_float(close.ewm(span=50,adjust=False).mean().iloc[-1]); rsi14=safe_float(rsi(close,14).iloc[-1])
        ret5=None
        if len(close)>=6:
            base=safe_float(close.iloc[-6]); ret5=(price/base-1)*100 if base not in (None,0) and price is not None else None
        bullish_structure=structure=="BULLISH_HH_HL"; bearish_structure=structure=="BEARISH_LH_LL"
        trend_confirm=price is not None and ema20 is not None and ema50 is not None and price>ema20>ema50
        weak_confirm=price is not None and ema50 is not None and price<ema50
        if bullish_structure and trend_confirm and (ret5 is None or ret5>-3):
            regime="GREEN"; score=100; multiplier=1.0; reason="IHSG confirmed HH/HL structure with EMA trend confirmation."
        elif bearish_structure and (weak_confirm or (ret5 is not None and ret5<=-5)):
            regime="RED"; score=20; multiplier=0.0; reason="IHSG confirmed LH/LL structure with weak trend confirmation; new real-money BUY blocked."
        else:
            regime="YELLOW"; score=60; multiplier=0.5; reason="IHSG structure/trend mixed; only reduced-size high-quality setups allowed."
        return {"regime":regime,"score":score,"size_multiplier":multiplier,"reason":reason,"benchmark":MARKET_REGIME_TICKER,"structure_state":structure,"price":price,"ema20":ema20,"ema50":ema50,"rsi14":rsi14,"ret5_pct":ret5}
    except Exception as exc:
        return {"regime":"UNKNOWN","score":0,"size_multiplier":0.0,"reason":f"IHSG regime unavailable: {exc}","benchmark":MARKET_REGIME_TICKER,"structure_state":"UNKNOWN"}


def closed_trade_performance_context():
    """Use manually closed real positions to create a simple system kill switch."""
    try:
        rows = supabase_request(
            "GET",
            "hanz_swing_portfolio"
            "?status=eq.CLOSED"
            "&realized_pnl_pct=not.is.null"
            "&select=ticker,realized_pnl_pct,closed_at"
            "&order=closed_at.desc"
            "&limit=20",
        ) or []
    except Exception as exc:
        return {
            "status": "UNKNOWN",
            "trade_count": 0,
            "reason": f"Closed-trade history unavailable: {exc}",
        }

    pnls = []
    for row in rows:
        value = safe_float(row.get("realized_pnl_pct"))
        if value is not None:
            pnls.append(value)

    if not pnls:
        return {
            "status": "WARMUP",
            "trade_count": 0,
            "consecutive_losses": 0,
            "win_rate_pct": None,
            "avg_pnl_pct": None,
            "reason": "No closed real-money trade history yet.",
        }

    consecutive_losses = 0
    for pnl in pnls:
        if pnl < 0:
            consecutive_losses += 1
        else:
            break

    sample = pnls[:max(1, KILL_SWITCH_LOOKBACK_TRADES)]
    wins = sum(1 for x in sample if x > 0)
    win_rate = wins / len(sample) * 100
    avg_pnl = sum(sample) / len(sample)

    status = "NORMAL"
    reason = "Recent closed-trade performance is within guardrails."

    if consecutive_losses >= KILL_SWITCH_CONSECUTIVE_LOSSES:
        status = "LOCKED"
        reason = (
            f"{consecutive_losses} consecutive losing trades reached "
            f"the kill-switch limit."
        )
    elif (
        len(sample) >= KILL_SWITCH_LOOKBACK_TRADES
        and win_rate < KILL_SWITCH_MIN_WIN_RATE_PCT
        and avg_pnl < 0
    ):
        status = "LOCKED"
        reason = (
            f"Rolling {len(sample)}-trade performance is negative "
            f"(win rate {win_rate:.1f}%, avg {avg_pnl:.2f}%)."
        )
    elif consecutive_losses >= max(2, KILL_SWITCH_CONSECUTIVE_LOSSES - 1):
        status = "CAUTION"
        reason = (
            f"{consecutive_losses} consecutive losses; "
            "position size should be reduced."
        )

    return {
        "status": status,
        "trade_count": len(pnls),
        "consecutive_losses": consecutive_losses,
        "win_rate_pct": round(win_rate, 2),
        "avg_pnl_pct": round(avg_pnl, 3),
        "reason": reason,
    }

def portfolio_risk_context():
    positions = fetch_swing_portfolio()
    total_risk_idr = 0.0
    total_market_value_idr = 0.0

    ticker_list = []
    for position in positions:
        ticker = clean_ticker(position.get("ticker"))
        if ticker:
            ticker_list.append(ticker)

        qty = _position_quantity(position)
        avg_buy = safe_float(position.get("avg_buy"))
        stop = safe_float(position.get("stop_loss"))

        if qty > 0 and avg_buy is not None:
            total_market_value_idr += qty * avg_buy

        if (
            qty > 0
            and avg_buy is not None
            and stop is not None
            and avg_buy > stop
        ):
            total_risk_idr += qty * (avg_buy - stop)

    sectors = {}
    if ticker_list:
        try:
            encoded = ",".join(
                urllib.parse.quote(t, safe="")
                for t in sorted(set(ticker_list))
            )
            rows = supabase_request(
                "GET",
                "hanz_swing_signal_monitor"
                f"?ticker=in.({encoded})"
                "&select=ticker,sector",
            ) or []
            sectors = {
                clean_ticker(row.get("ticker")): row.get("sector")
                for row in rows
            }
        except Exception:
            sectors = {}

    sector_market_value = {}
    for position in positions:
        ticker = clean_ticker(position.get("ticker"))
        sector = sectors.get(ticker) or "UNKNOWN"
        qty = _position_quantity(position)
        avg_buy = safe_float(position.get("avg_buy"))
        if qty > 0 and avg_buy is not None:
            sector_market_value[sector] = (
                sector_market_value.get(sector, 0.0)
                + qty * avg_buy
            )

    portfolio_risk_pct = None
    if ACCOUNT_CAPITAL_IDR > 0:
        portfolio_risk_pct = total_risk_idr / ACCOUNT_CAPITAL_IDR * 100

    return {
        "open_positions": len(positions),
        "total_risk_idr": round(total_risk_idr, 2),
        "total_market_value_idr": round(total_market_value_idr, 2),
        "portfolio_risk_pct": safe_float(portfolio_risk_pct),
        "sector_market_value": sector_market_value,
    }

def build_real_money_context():
    return {
        "market": market_regime_context(),
        "portfolio": portfolio_risk_context(),
        "performance": closed_trade_performance_context(),
        "account_capital_idr": ACCOUNT_CAPITAL_IDR,
    }


def liquidity_validation(daily):
    avg_value = safe_float(daily.get("avg_value20"))
    median_value = safe_float(daily.get("median_value20"))
    zero_days = int(daily.get("zero_volume_days20") or 0)
    atr_pct = safe_float(daily.get("atr_pct"))

    reasons = []
    passed = True
    score = 100

    if avg_value is None or avg_value < MIN_AVG_DAILY_VALUE_IDR:
        passed = False
        score -= 50
        reasons.append(
            f"20d avg traded value below HANZ minimum "
            f"Rp{MIN_AVG_DAILY_VALUE_IDR:,.0f}."
        )
    else:
        reasons.append(
            f"20d avg traded value Rp{avg_value:,.0f}."
        )

    if zero_days > MAX_ZERO_VOLUME_DAYS_20:
        passed = False
        score -= 30
        reasons.append(
            f"{zero_days} zero-volume days in last 20 sessions."
        )

    if atr_pct is not None and atr_pct > MAX_ATR_PCT:
        passed = False
        score -= 25
        reasons.append(
            f"ATR {atr_pct:.1f}% exceeds HANZ volatility guard."
        )

    if not passed:
        grade = "FAIL"
    elif avg_value is not None and avg_value >= MIN_AVG_DAILY_VALUE_IDR * 5:
        grade = "A"
    elif avg_value is not None and avg_value >= MIN_AVG_DAILY_VALUE_IDR * 2:
        grade = "B"
    else:
        grade = "C"

    return {
        "pass": passed,
        "grade": grade,
        "score": max(0, min(100, score)),
        "avg_value20": avg_value,
        "median_value20": median_value,
        "zero_volume_days20": zero_days,
        "atr_pct": atr_pct,
        "reason": " ".join(reasons),
    }



def swing_volatility_guard(daily):
    """Classify whether current volatility is suitable for HANZ Swing."""
    atr_pct = safe_float(daily.get("atr_pct"))
    ret1_pct = safe_float(daily.get("ret1_pct"))
    gap_pct = safe_float(daily.get("gap_pct"))
    day_range_pct = safe_float(daily.get("day_range_pct"))
    extreme_move_days10 = int(daily.get("extreme_move_days10") or 0)

    extreme_reasons = []
    high_reasons = []

    if atr_pct is not None:
        if atr_pct > SWING_EXTREME_ATR_PCT:
            extreme_reasons.append(
                f"ATR {atr_pct:.1f}% > {SWING_EXTREME_ATR_PCT:.1f}% swing limit."
            )
        elif atr_pct >= SWING_HIGH_ATR_PCT:
            high_reasons.append(
                f"ATR {atr_pct:.1f}% is elevated for swing trading."
            )

    if ret1_pct is not None and abs(ret1_pct) >= SWING_EXTREME_1D_MOVE_PCT:
        extreme_reasons.append(
            f"1D move {ret1_pct:+.1f}% is extreme for HANZ Swing."
        )

    if gap_pct is not None:
        if abs(gap_pct) >= SWING_EXTREME_GAP_PCT:
            extreme_reasons.append(f"Session gap {gap_pct:+.1f}% is extreme.")
        elif abs(gap_pct) >= SWING_HIGH_GAP_PCT:
            high_reasons.append(f"Session gap {gap_pct:+.1f}% is elevated.")

    if day_range_pct is not None and day_range_pct >= SWING_HIGH_DAY_RANGE_PCT:
        high_reasons.append(
            f"Daily range {day_range_pct:.1f}% is wide for a swing setup."
        )

    if extreme_move_days10 >= SWING_EXTREME_MOVE_DAYS_10:
        extreme_reasons.append(
            f"{extreme_move_days10} sessions moved >=±{SWING_EXTREME_1D_MOVE_PCT:.0f}% "
            f"within the last 10 trading days."
        )

    if extreme_reasons:
        status = "EXTREME"
        blocked = True
        size_multiplier = 0.0
        warning = "EXTREME VOLATILITY — NOT SUITABLE FOR HANZ SWING"
        reasons = extreme_reasons + high_reasons
    elif high_reasons:
        status = "HIGH"
        blocked = False
        size_multiplier = max(0.0, min(1.0, SWING_HIGH_VOL_SIZE_MULTIPLIER))
        warning = "HIGH VOLATILITY — SWING RISK ELEVATED"
        reasons = high_reasons
    else:
        status = "NORMAL"
        blocked = False
        size_multiplier = 1.0
        warning = "NORMAL VOLATILITY"
        reasons = []

    return {
        "status": status,
        "blocked": blocked,
        "size_multiplier": size_multiplier,
        "warning": warning,
        "atr_pct": atr_pct,
        "ret1_pct": ret1_pct,
        "gap_pct": gap_pct,
        "day_range_pct": day_range_pct,
        "extreme_move_days10": extreme_move_days10,
        "reason": " ".join(reasons),
    }


def real_money_validation(
    ticker,
    daily,
    result,
    levels,
    fundamental,
    context,
):
    """Independent execution gate. Technical SWING_BUY is preserved."""
    context = context or build_real_money_context()
    market = context.get("market") or {}
    portfolio = context.get("portfolio") or {}
    performance = context.get("performance") or {}
    liquidity = liquidity_validation(daily)
    volatility_guard = swing_volatility_guard(daily)
    momentum_guard = result.get("momentum_guard") or momentum_damage_guard(daily)

    entry = safe_float(levels.get("entry_price") or daily.get("price"))
    stop = safe_float(levels.get("stop_loss"))
    target1 = safe_float(levels.get("target_1"))
    target2 = safe_float(levels.get("target_2"))

    stop_distance_pct = None
    risk_per_share = None
    rr1 = None
    rr2 = None
    net_rr1 = None
    net_rr2 = None

    costs_configured = (
        BUY_FEE_PCT >= 0
        and SELL_FEE_PCT >= 0
        and SLIPPAGE_PCT >= 0
    )

    # Entry-location guard: a technically confirmed breakout can still be a
    # bad execution if price is already too extended.  risk_levels() labels
    # those cases WAIT_PULLBACK; preserve the signal, but do not allow it to
    # become real-money actionable until price returns to a valid entry zone.
    entry_status = str(levels.get("entry_status") or "").upper()
    entry_note = levels.get("entry_note")

    if (
        entry not in (None, 0)
        and stop is not None
        and entry > stop
    ):
        risk_per_share = entry - stop
        stop_distance_pct = risk_per_share / entry * 100
        if target1 is not None and target1 > entry:
            rr1 = (target1 - entry) / risk_per_share
        if target2 is not None and target2 > entry:
            rr2 = (target2 - entry) / risk_per_share

        if costs_configured:
            buy_cost_rate = (BUY_FEE_PCT + SLIPPAGE_PCT) / 100.0
            sell_cost_rate = (SELL_FEE_PCT + SLIPPAGE_PCT) / 100.0

            effective_entry = entry * (1.0 + buy_cost_rate)
            effective_stop = stop * (1.0 - sell_cost_rate)
            effective_risk = effective_entry - effective_stop

            if effective_risk > 0:
                if target1 is not None and target1 > entry:
                    effective_t1 = target1 * (1.0 - sell_cost_rate)
                    net_rr1 = (effective_t1 - effective_entry) / effective_risk
                if target2 is not None and target2 > entry:
                    effective_t2 = target2 * (1.0 - sell_cost_rate)
                    net_rr2 = (effective_t2 - effective_entry) / effective_risk

    gate = "MONITOR"
    score = 100
    blockers = []
    cautions = []

    try:
        wfe_value = float(STRATEGY_WFE) if STRATEGY_WFE else None
    except Exception:
        wfe_value = None
    try:
        oos_expectancy_r = float(STRATEGY_OOS_EXPECTANCY_R) if STRATEGY_OOS_EXPECTANCY_R else None
    except Exception:
        oos_expectancy_r = None

    strategy_validation = _strategy_validation_evidence()
    strategy_validation["status"] = "VALIDATED" if strategy_validation.get("passed") else "RESEARCH_ONLY"

    if momentum_guard.get("blocked"):
        gate = "BLOCKED"
        score = 0
        blockers.append("MOMENTUM_BROKEN")
        if momentum_guard.get("failed_breakout"):
            blockers.append("FAILED_BREAKOUT")
    elif volatility_guard.get("blocked"):
        gate = "BLOCKED"
        score = 0
        blockers.append("EXTREME_VOLATILITY")
    elif result.get("state") != "SWING_BUY":
        gate = "MONITOR"
        score = 0
    else:
        if entry_status == "WAIT_PULLBACK":
            cautions.append("WAIT_PULLBACK_DO_NOT_CHASE")
            score -= 25

        if not liquidity.get("pass"):
            blockers.append("LIQUIDITY")

        if market.get("regime") in {"RED", "UNKNOWN"}:
            blockers.append("MARKET_REGIME")
        elif market.get("regime") == "YELLOW":
            cautions.append("MARKET_YELLOW")
            score -= 15

        if performance.get("status") == "LOCKED":
            blockers.append("KILL_SWITCH")
        elif performance.get("status") in {"CAUTION", "WARMUP", "UNKNOWN"}:
            cautions.append(f"PERFORMANCE_{performance.get('status')}")
            score -= 10

        if risk_per_share is None or risk_per_share <= 0:
            blockers.append("INVALID_STOP")
        else:
            if stop_distance_pct is not None and stop_distance_pct > 12.0:
                blockers.append("STOP_TOO_WIDE")
            elif stop_distance_pct is not None and stop_distance_pct < 1.0:
                cautions.append("STOP_VERY_TIGHT")
                score -= 10

        if not costs_configured:
            cautions.append("TRADING_COSTS_NOT_CONFIGURED")
            score -= 10

        rr1_for_gate = net_rr1 if costs_configured else rr1
        rr2_for_gate = net_rr2 if costs_configured else rr2

        if rr1_for_gate is None or rr1_for_gate < MIN_RR_T1:
            blockers.append("RR_T1")
        if rr2_for_gate is None or rr2_for_gate < MIN_RR_T2:
            blockers.append("RR_T2")

        portfolio_risk_pct = safe_float(portfolio.get("portfolio_risk_pct"))
        if (
            portfolio_risk_pct is not None
            and portfolio_risk_pct >= MAX_PORTFOLIO_RISK_PCT
        ):
            blockers.append("PORTFOLIO_RISK_LIMIT")

        if int(portfolio.get("open_positions") or 0) >= MAX_OPEN_POSITIONS:
            blockers.append("MAX_OPEN_POSITIONS")

        sector = fundamental.get("sector") or "UNKNOWN"
        sector_value = safe_float(
            (portfolio.get("sector_market_value") or {}).get(sector)
        ) or 0.0
        sector_exposure_pct = None
        if ACCOUNT_CAPITAL_IDR > 0:
            sector_exposure_pct = sector_value / ACCOUNT_CAPITAL_IDR * 100
            if sector != "UNKNOWN" and sector_exposure_pct >= MAX_SECTOR_EXPOSURE_PCT:
                blockers.append("SECTOR_CONCENTRATION")

        if blockers:
            gate = "BLOCKED"
            score -= 50
        elif not strategy_validation.get("passed"):
            gate = "RESEARCH_ONLY"
            failed_checks = [k for k,v in (strategy_validation.get("checks") or {}).items() if not v]
            cautions.append("STRATEGY_VALIDATION_FAIL:" + ",".join(failed_checks))
            score -= 25
        elif ACCOUNT_CAPITAL_IDR <= 0 or not costs_configured:
            gate = "PAPER_ONLY"
            if ACCOUNT_CAPITAL_IDR <= 0:
                cautions.append("ACCOUNT_CAPITAL_NOT_CONFIGURED")
            if not costs_configured and "TRADING_COSTS_NOT_CONFIGURED" not in cautions:
                cautions.append("TRADING_COSTS_NOT_CONFIGURED")
            score -= 20
        elif cautions:
            gate = "CAUTION"
        else:
            gate = "ELIGIBLE"

    score -= max(0, 100 - int(liquidity.get("score") or 0)) * 0.35
    score = int(max(0, min(100, round(score))))

    # Position sizing
    suggested_lots = None
    suggested_shares = None
    suggested_position_idr = None
    risk_budget_idr = None

    if (
        result.get("state") in BUY_STATES
        and ACCOUNT_CAPITAL_IDR > 0
        and risk_per_share not in (None, 0)
        and entry not in (None, 0)
        and gate in {"ELIGIBLE", "CAUTION"}
    ):
        size_multiplier = safe_float(market.get("size_multiplier"))
        if size_multiplier is None:
            size_multiplier = 0.0
        if performance.get("status") == "CAUTION":
            size_multiplier *= 0.5

        volatility_size_multiplier = safe_float(
            volatility_guard.get("size_multiplier")
        )
        if volatility_size_multiplier is not None:
            size_multiplier *= volatility_size_multiplier

        risk_budget_idr = (
            ACCOUNT_CAPITAL_IDR
            * (RISK_PER_TRADE_PCT / 100.0)
            * size_multiplier
        )

        shares_by_risk = int(risk_budget_idr // risk_per_share)

        max_position_idr = ACCOUNT_CAPITAL_IDR * (MAX_POSITION_PCT / 100.0)
        shares_by_position = int(max_position_idr // entry)

        avg_value = safe_float(liquidity.get("avg_value20"))
        shares_by_liquidity = shares_by_position
        if avg_value not in (None, 0):
            max_liq_value = avg_value * (MAX_ADV_PARTICIPATION_PCT / 100.0)
            shares_by_liquidity = int(max_liq_value // entry)

        shares = min(
            shares_by_risk,
            shares_by_position,
            shares_by_liquidity,
        )
        lots = max(0, shares // 100)

        if lots > 0:
            suggested_lots = lots
            suggested_shares = lots * 100
            suggested_position_idr = suggested_shares * entry

    actionable = (
        result.get("state") in BUY_STATES
        and entry_status != "WAIT_PULLBACK"
        and strategy_validation.get("passed")
        and (
            (not RISK_LIVE_GATE_ENABLED)
            or gate == "ELIGIBLE"
        )
    )

    return {
        "gate": gate,
        "score": score,
        "actionable": actionable,
        "entry_status": entry_status or None,
        "entry_note": entry_note,
        "do_not_chase": entry_status == "WAIT_PULLBACK",
        "strategy_validation": strategy_validation,
        "structure_state": result.get("structure_state") or daily.get("structure_state"),
        "setup_family": result.get("setup_family"),
        "trigger_confirmed": result.get("trigger_confirmed"),
        "volume_confirm": result.get("volume_confirm"),
        "pullback_location": result.get("pullback_location"),
        "early_location_ok": result.get("early_location_ok"),
        "early_structure_ok": result.get("early_structure_ok"),
        "early_buy_gate": result.get("early_buy_gate"),
        "minor_structure_break": result.get("minor_structure_break"),
        "higher_low": result.get("higher_low"),
        "support_distance_atr": result.get("support_distance_atr"),
        "candle_context": daily.get("candle_context"),
        "daily_rvol": daily.get("rvol20"),
        "blockers": blockers,
        "cautions": cautions,
        "market_regime": market.get("regime"),
        "market_reason": market.get("reason"),
        "market_score": market.get("score"),
        "liquidity_grade": liquidity.get("grade"),
        "liquidity_pass": liquidity.get("pass"),
        "liquidity_reason": liquidity.get("reason"),
        "volatility_status": volatility_guard.get("status"),
        "volatility_warning": volatility_guard.get("warning"),
        "volatility_reason": volatility_guard.get("reason"),
        "volatility_size_multiplier": volatility_guard.get("size_multiplier"),
        "gap_pct": volatility_guard.get("gap_pct"),
        "day_range_pct": volatility_guard.get("day_range_pct"),
        "extreme_move_days10": volatility_guard.get("extreme_move_days10"),
        "momentum_guard": momentum_guard,
        "momentum_status": (
            "BROKEN" if momentum_guard.get("blocked")
            else ("WEAKENING" if momentum_guard.get("caution") else "HEALTHY")
        ),
        "failed_breakout": bool(momentum_guard.get("failed_breakout")),
        "ret1_pct": momentum_guard.get("ret1_pct"),
        "ret3_pct": momentum_guard.get("ret3_pct"),
        "ret5_pct": momentum_guard.get("ret5_pct"),
        "drawdown_5d_high_pct": momentum_guard.get("drawdown_5d_high_pct"),
        "drawdown_10d_high_pct": momentum_guard.get("drawdown_10d_high_pct"),
        "avg_value20": liquidity.get("avg_value20"),
        "median_value20": liquidity.get("median_value20"),
        "zero_volume_days20": liquidity.get("zero_volume_days20"),
        "atr_pct": liquidity.get("atr_pct"),
        "daily_rsi": safe_float(daily.get("rsi14")),
        "daily_rvol": safe_float(daily.get("rvol20")),
        "breakout_distance_pct": safe_float(daily.get("breakout_distance_pct")),
        "ema20_slope_5d_pct": safe_float(daily.get("ema20_slope_5d_pct")),
        "volume_accel_5d": safe_float(daily.get("volume_accel_5d")),
        "stop_distance_pct": safe_float(stop_distance_pct),
        "rr_target_1": safe_float(rr1),
        "rr_target_2": safe_float(rr2),
        "net_rr_target_1": safe_float(net_rr1),
        "net_rr_target_2": safe_float(net_rr2),
        "costs_configured": costs_configured,
        "buy_fee_pct": BUY_FEE_PCT if BUY_FEE_PCT >= 0 else None,
        "sell_fee_pct": SELL_FEE_PCT if SELL_FEE_PCT >= 0 else None,
        "slippage_pct": SLIPPAGE_PCT if SLIPPAGE_PCT >= 0 else None,
        "risk_per_share": safe_float(risk_per_share),
        "risk_budget_idr": safe_float(risk_budget_idr),
        "suggested_lots": suggested_lots,
        "suggested_shares": suggested_shares,
        "suggested_position_idr": safe_float(suggested_position_idr),
        "portfolio_risk_pct": portfolio.get("portfolio_risk_pct"),
        "open_positions": portfolio.get("open_positions"),
        "kill_switch": performance.get("status"),
        "kill_switch_reason": performance.get("reason"),
        "performance_win_rate_pct": performance.get("win_rate_pct"),
        "performance_avg_pnl_pct": performance.get("avg_pnl_pct"),
        "account_capital_configured": ACCOUNT_CAPITAL_IDR > 0,
        "generated_at": now_iso(),
    }


# ============================================================
# SWING PORTFOLIO / ALERTS
# ============================================================

def fetch_swing_portfolio():
    return supabase_request(
        "GET",
        "hanz_swing_portfolio"
        "?status=eq.OPEN"
        "&select=*"
        "&order=opened_at.asc",
    ) or []


def update_swing_portfolio(portfolio_id, payload):
    if portfolio_id is None or not payload:
        return

    encoded = urllib.parse.quote(
        str(portfolio_id),
        safe="",
    )

    payload = dict(payload)
    payload["updated_at"] = now_iso()

    supabase_request(
        "PATCH",
        f"hanz_swing_portfolio?id=eq.{encoded}",
        payload,
        prefer="return=minimal",
    )


def swing_alert_dedupe_key(
    portfolio_id,
    ticker,
    alert_type,
    *,
    daily=False,
):
    base = (
        f"{portfolio_id}:"
        f"{clean_ticker(ticker)}:"
        f"{alert_type}"
    )

    if daily:
        return (
            base
            + ":"
            + utc_now()
            .astimezone(JAKARTA_TZ)
            .date()
            .isoformat()
        )

    return base


def insert_swing_alert(
    *,
    position,
    alert_type,
    priority,
    message,
    reason=None,
    daily_dedupe=False,
):
    user_id = position.get("user_id")
    portfolio_id = position.get("id")
    ticker = position.get("ticker")

    if not user_id or portfolio_id is None or not ticker:
        return False

    dedupe_key = swing_alert_dedupe_key(
        portfolio_id,
        ticker,
        alert_type,
        daily=daily_dedupe,
    )

    payload = {
        "user_id": user_id,
        "portfolio_id": portfolio_id,
        "ticker": clean_ticker(ticker),
        "alert_type": alert_type,
        "priority": priority,
        "message": message,
        "reason": reason,
        "dedupe_key": dedupe_key,
        "created_at": now_iso(),
    }

    try:
        supabase_request(
            "POST",
            "hanz_swing_alerts",
            payload,
            prefer="return=minimal",
        )

        print(
            f"SWING ALERT: {clean_ticker(ticker)} "
            f"{alert_type} portfolio={portfolio_id}",
            flush=True,
        )

        # Make the phone notification immediately identify the portfolio stock.
        push_ticker = clean_ticker(ticker)
        push_event = alert_type.replace("_", " ")
        avg_buy = safe_float(position.get("avg_buy"))
        last_price = safe_float(position.get("last_price"))
        pnl_pct = safe_float(position.get("last_pnl_pct"))

        context_bits = []
        if avg_buy is not None:
            context_bits.append(f"Buy {avg_buy:.2f}")
        if last_price is not None:
            context_bits.append(f"Last {last_price:.2f}")
        if pnl_pct is not None:
            context_bits.append(f"P/L {pnl_pct:+.2f}%")

        push_body = f"{push_event} — {message}"
        if context_bits:
            push_body += " | " + " | ".join(context_bits)

        send_selective_push(
            ticker=ticker,
            alert_type=alert_type,
            title=f"HANZ • {push_ticker}",
            message=push_body,
            user_id=user_id,
            portfolio_id=portfolio_id,
        )

        return True

    except Exception as exc:
        # Unique dedupe_key suppresses repeat trigger spam.
        if "409" in str(exc):
            return False
        raise


def jakarta_date_string():
    return (
        utc_now()
        .astimezone(JAKARTA_TZ)
        .date()
        .isoformat()
    )


def firebase_app():
    global _FIREBASE_APP

    if _FIREBASE_APP is not None:
        return _FIREBASE_APP

    if firebase_admin is None or credentials is None:
        return None

    if not FIREBASE_SERVICE_ACCOUNT_JSON:
        return None

    try:
        info = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
        cred = credentials.Certificate(info)

        try:
            _FIREBASE_APP = firebase_admin.get_app()
        except ValueError:
            _FIREBASE_APP = firebase_admin.initialize_app(cred)

        return _FIREBASE_APP

    except Exception as exc:
        print(
            f"SWING FCM init unavailable: {exc}",
            flush=True,
        )
        return None


def push_event_key(
    *,
    ticker,
    alert_type,
    user_id,
    portfolio_id,
):
    if alert_type == "PROTECT_PROFIT":
        return (
            f"SWING:{user_id}:{portfolio_id}:"
            f"{alert_type}:{jakarta_date_string()}"
        )

    return (
        f"SWING:{user_id}:{portfolio_id}:"
        f"{alert_type}"
    )


def reserve_push_event(
    *,
    event_key,
    ticker,
    alert_type,
    user_id,
    portfolio_id,
):
    payload = {
        "event_key": event_key,
        "user_id": user_id,
        "portfolio_id": portfolio_id,
        "ticker": clean_ticker(ticker),
        "alert_type": alert_type,
        "status": "PENDING",
        "created_at": now_iso(),
    }

    try:
        supabase_request(
            "POST",
            "hanz_push_log",
            payload,
            prefer="return=minimal",
        )
        return True
    except Exception as exc:
        if "409" in str(exc):
            return False
        raise


def finish_push_event(event_key, status, error=None):
    encoded = urllib.parse.quote(
        str(event_key),
        safe="",
    )

    payload = {
        "status": status,
        "updated_at": now_iso(),
    }

    if status == "SENT":
        payload["sent_at"] = now_iso()

    if error:
        payload["last_error"] = str(error)[:1000]

    try:
        supabase_request(
            "PATCH",
            f"hanz_push_log?event_key=eq.{encoded}",
            payload,
            prefer="return=minimal",
        )
    except Exception:
        pass


def release_failed_push_event(event_key):
    encoded = urllib.parse.quote(
        str(event_key),
        safe="",
    )

    try:
        supabase_request(
            "DELETE",
            f"hanz_push_log?event_key=eq.{encoded}",
            prefer="return=minimal",
        )
    except Exception:
        pass


def get_push_installation_ids(user_id):
    encoded_user = urllib.parse.quote(
        str(user_id),
        safe="",
    )

    rows = supabase_request(
        "GET",
        "hanz_push_devices"
        "?enabled=eq.true"
        f"&user_id=eq.{encoded_user}"
        "&select=installation_id",
    ) or []

    ids = []
    seen = set()

    for row in rows:
        installation_id = str(
            row.get("installation_id")
            or ""
        ).strip()

        if (
            installation_id
            and installation_id not in seen
        ):
            seen.add(installation_id)
            ids.append(installation_id)

    return ids


def send_selective_push(
    *,
    ticker,
    alert_type,
    title,
    message,
    user_id,
    portfolio_id,
):
    if alert_type not in PUSH_ALERT_TYPES:
        return

    app = firebase_app()

    if app is None or messaging is None:
        print(
            f"SWING PUSH SKIPPED: Firebase not configured "
            f"({alert_type} {clean_ticker(ticker)})",
            flush=True,
        )
        return

    event_key = push_event_key(
        ticker=ticker,
        alert_type=alert_type,
        user_id=user_id,
        portfolio_id=portfolio_id,
    )

    if not reserve_push_event(
        event_key=event_key,
        ticker=ticker,
        alert_type=alert_type,
        user_id=user_id,
        portfolio_id=portfolio_id,
    ):
        print(
            f"SWING PUSH SUPPRESSED duplicate: {event_key}",
            flush=True,
        )
        return

    try:
        installation_ids = get_push_installation_ids(
            user_id
        )

        if not installation_ids:
            finish_push_event(
                event_key,
                "NO_DEVICE",
            )
            return

        messages = []

        for fid in installation_ids:
            messages.append(
                messaging.Message(
                    data={
                        "title": str(title),
                        "body": str(message),
                        "message": str(message),
                        "ticker": clean_ticker(ticker),
                        "alert_type": str(alert_type),
                        "url": PUSH_DASHBOARD_URL,
                        "portfolio_id": str(portfolio_id),
                        "dedupe_key": event_key,
                    },
                    fid=fid,
                )
            )

        response = messaging.send_each(
            messages,
            app=app,
        )

        finish_push_event(
            event_key,
            "SENT",
        )

        print(
            f"SWING PUSH SENT: {event_key} "
            f"success={response.success_count} "
            f"failed={response.failure_count}",
            flush=True,
        )

    except Exception as exc:
        release_failed_push_event(event_key)

        print(
            f"SWING PUSH FAILED: {event_key} — {exc}",
            flush=True,
        )


def apply_swing_auto_trailing(
    position,
    daily,
):
    """Manage peak/trailing from daily bars.

    Important:
    - Target reach uses today's HIGH.
    - Peak uses today's HIGH.
    - A newly activated trailing stop is NOT allowed to trigger a
      same-day CONFIRMED_SELL because daily OHLC cannot tell whether
      the day's low happened before or after the day's high.
    """
    if not safe_bool(
        position.get("auto_trailing"),
        True,
    ):
        return position, False

    portfolio_id = position.get("id")
    high = safe_float(daily.get("high"))
    atr14 = safe_float(daily.get("atr14"))
    avg_buy = safe_float(position.get("avg_buy"))
    target_1 = safe_float(position.get("target_1"))
    target_2 = safe_float(position.get("target_2"))
    current_peak = safe_float(position.get("peak_price"))
    current_trail = safe_float(position.get("trailing_stop"))
    was_active = safe_bool(
        position.get("trailing_active"),
        False,
    )

    if high is None:
        return position, False

    peak = max(
        value
        for value in [current_peak, high]
        if value is not None
    )

    reached_t1 = (
        target_1 is not None
        and high >= target_1
    )

    reached_t2 = (
        target_2 is not None
        and high >= target_2
    )

    active = was_active or reached_t1

    multiplier = (
        TRAILING_ATR_MULTIPLIER_T2
        if reached_t2
        else TRAILING_ATR_MULTIPLIER_T1
    )

    new_trail = current_trail

    if (
        active
        and atr14 is not None
        and atr14 > 0
    ):
        candidate = peak - multiplier * atr14

        if avg_buy is not None:
            candidate = max(
                candidate,
                avg_buy,
            )

        if current_trail is None:
            new_trail = candidate
        else:
            new_trail = max(
                current_trail,
                candidate,
            )

    updates = {
        "last_price": daily.get("price"),
        "last_monitor_at": now_iso(),
        "last_daily_bar_at": daily.get("bar_at"),
    }

    if values_different(current_peak, peak):
        updates["peak_price"] = peak

    if active != was_active:
        updates["trailing_active"] = active

        if active and not position.get(
            "trailing_activated_at"
        ):
            updates[
                "trailing_activated_at"
            ] = now_iso()

    if (
        active
        and values_different(
            safe_float(
                position.get(
                    "trailing_atr_multiplier"
                )
            ),
            multiplier,
        )
    ):
        updates[
            "trailing_atr_multiplier"
        ] = multiplier

    if (
        active
        and values_different(
            current_trail,
            new_trail,
        )
    ):
        updates["trailing_stop"] = new_trail
        updates[
            "last_trailing_update_at"
        ] = now_iso()

    if reached_t1 and not position.get(
        "target_1_reached_at"
    ):
        updates["target_1_reached_at"] = now_iso()

    if reached_t2 and not position.get(
        "target_2_reached_at"
    ):
        updates["target_2_reached_at"] = now_iso()

    if updates and portfolio_id is not None:
        update_swing_portfolio(
            portfolio_id,
            updates,
        )
        position.update(updates)

    just_activated = (
        active
        and not was_active
    )

    if just_activated:
        insert_swing_alert(
            position=position,
            alert_type="TRAILING_ACTIVATED",
            priority=75,
            message=(
                f"Target 1 reached. "
                f"High {high:.2f}. "
                f"Swing trailing activated at "
                f"{new_trail:.2f} "
                f"({multiplier:.1f}× ATR)."
            ),
            reason="Target 1 activated swing trailing protection.",
        )

    if (
        reached_t1
        and not position.get(
            "_t1_alert_processed"
        )
    ):
        insert_swing_alert(
            position=position,
            alert_type="TARGET_1_REACHED",
            priority=60,
            message=(
                f"Target 1 reached. "
                f"Daily high {high:.2f}."
            ),
            reason="First swing target reached.",
        )
        position["_t1_alert_processed"] = True

    if (
        reached_t2
        and not position.get(
            "_t2_alert_processed"
        )
    ):
        insert_swing_alert(
            position=position,
            alert_type="TARGET_2_REACHED",
            priority=70,
            message=(
                f"Target 2 reached. "
                f"Daily high {high:.2f}."
            ),
            reason="Second swing target reached.",
        )
        position["_t2_alert_processed"] = True

    return position, just_activated


def swing_portfolio_signal(
    position,
    daily,
    weekly,
    *,
    trailing_just_activated=False,
    allow_structural_exit=True,
):
    close = safe_float(daily.get("price"))
    low = safe_float(daily.get("low"))
    high = safe_float(daily.get("high"))

    avg_buy = safe_float(
        position.get("avg_buy")
    )
    stop_loss = safe_float(
        position.get("stop_loss")
    )
    trailing_stop = safe_float(
        position.get("trailing_stop")
    )
    target_1 = safe_float(
        position.get("target_1")
    )
    target_2 = safe_float(
        position.get("target_2")
    )

    trailing_active = safe_bool(
        position.get("trailing_active"),
        False,
    )

    if close is None:
        return {
            "signal": "NO_DATA",
            "priority": 0,
            "reason": "No daily close.",
            "pnl_pct": None,
        }

    pnl_pct = None

    if avg_buy not in (None, 0):
        pnl_pct = (
            close / avg_buy - 1
        ) * 100

    # Highest priority: hard stop breach.
    if (
        stop_loss is not None
        and low is not None
        and low <= stop_loss
    ):
        return {
            "signal": "STOP_LOSS",
            "priority": 100,
            "reason": (
                f"Daily low {low:.2f} "
                f"breached hard stop {stop_loss:.2f}."
            ),
            "pnl_pct": pnl_pct,
        }

    # Trailing breach is actionable only if trailing existed before
    # this daily bar. This avoids false same-day OHLC sequencing.
    if (
        trailing_active
        and not trailing_just_activated
        and trailing_stop is not None
        and low is not None
        and low <= trailing_stop
    ):
        return {
            "signal": "CONFIRMED_SELL",
            "priority": 95,
            "reason": (
                f"Daily low {low:.2f} "
                f"breached swing trailing stop "
                f"{trailing_stop:.2f}."
            ),
            "pnl_pct": pnl_pct,
        }

    daily_breakdown = (
        daily.get("prior_low20") is not None
        and close < daily["prior_low20"]
    )

    daily_bearish = (
        daily.get("ema20") is not None
        and close < daily["ema20"]
    )

    weekly_bearish = (
        weekly.get("ema10") is not None
        and weekly.get("ema20") is not None
        and weekly["ema10"] < weekly["ema20"]
    )

    if (
        allow_structural_exit
        and daily_breakdown
        and daily_bearish
        and weekly_bearish
    ):
        return {
            "signal": "CONFIRMED_SELL",
            "priority": 90,
            "reason": (
                "Daily 20-day breakdown + close below "
                "daily EMA20 + weekly EMA10 below EMA20."
            ),
            "pnl_pct": pnl_pct,
        }

    reached_t1 = (
        target_1 is not None
        and high is not None
        and high >= target_1
    )

    if (
        allow_structural_exit
        and reached_t1
        and pnl_pct is not None
        and pnl_pct > 0
        and (
            daily_bearish
            or (
                daily.get("rsi14") is not None
                and daily["rsi14"] < 50
            )
        )
    ):
        return {
            "signal": "PROTECT_PROFIT",
            "priority": 65,
            "reason": (
                "Position has reached Target 1 but "
                "daily momentum is weakening."
            ),
            "pnl_pct": pnl_pct,
        }

    if (
        target_2 is not None
        and high is not None
        and high >= target_2
    ):
        return {
            "signal": "TARGET_2_REACHED",
            "priority": 50,
            "reason": "Target 2 reached; trailing remains active.",
            "pnl_pct": pnl_pct,
        }

    if reached_t1:
        return {
            "signal": "TARGET_1_REACHED",
            "priority": 40,
            "reason": "Target 1 reached; trailing protection active.",
            "pnl_pct": pnl_pct,
        }

    return {
        "signal": "HOLD",
        "priority": 10,
        "reason": "Swing structure remains valid.",
        "pnl_pct": pnl_pct,
    }


def monitor_swing_portfolio(*, allow_structural_exit=True):
    positions = fetch_swing_portfolio()
    monitored = 0
    errors = 0
    frame_cache = {}

    for position in positions:
        ticker = position.get("ticker")
        portfolio_id = position.get("id")

        if not ticker:
            continue

        try:
            cache_key = clean_ticker(ticker)

            if cache_key not in frame_cache:
                daily_df = download_frame(
                    ticker,
                    DAILY_INTERVAL,
                    DAILY_PERIOD,
                )

                weekly_df = download_frame(
                    ticker,
                    WEEKLY_INTERVAL,
                    WEEKLY_PERIOD,
                )

                frame_cache[cache_key] = (
                    daily_metrics(daily_df),
                    weekly_metrics(weekly_df),
                )

            daily, weekly = frame_cache[cache_key]
            monitored += 1

            position, just_activated = (
                apply_swing_auto_trailing(
                    position,
                    daily,
                )
            )

            result = swing_portfolio_signal(
                position,
                daily,
                weekly,
                trailing_just_activated=just_activated,
                allow_structural_exit=allow_structural_exit,
            )

            foreign_flow = foreign_flow_snapshot(ticker)
            foreign_overlay = foreign_exit_overlay(position, daily, foreign_flow)
            insider = insider_disclosure_snapshot(ticker)
            insider_overlay = insider_exit_overlay(position, daily, insider)
            broker_flow = broker_flow_snapshot(ticker)
            broker_overlay = broker_exit_overlay(position, daily, broker_flow)

            signal = result["signal"]
            for overlay in (foreign_overlay, insider_overlay, broker_overlay):
                if overlay is not None and int(overlay.get("priority") or 0) > int(result.get("priority") or 0):
                    result = dict(result)
                    result.update(overlay)
                    signal = result["signal"]

            updates = {
                "signal": signal,
                "last_price": daily.get("price"),
                "last_pnl_pct": result.get("pnl_pct"),
                "last_monitor_at": now_iso(),
                "last_daily_bar_at": daily.get("bar_at"),
                "last_weekly_bar_at": weekly.get("bar_at"),
                "last_signal_reason": result.get("reason"),
                "foreign_flow_status": foreign_flow.get("status"),
                "foreign_net_1d": foreign_flow.get("net_1d"),
                "foreign_net_3d": foreign_flow.get("net_3d"),
                "foreign_net_5d": foreign_flow.get("net_5d"),
                "foreign_net_pct_1d": foreign_flow.get("net_pct_1d"),
                "foreign_net_pct_3d": foreign_flow.get("net_pct_3d"),
                "foreign_net_pct_5d": foreign_flow.get("net_pct_5d"),
                "foreign_flow_reason": foreign_flow.get("reason"),
                "insider_status": insider.get("status"),
                "insider_score": insider.get("score"),
                "insider_buy_count_30d": insider.get("buy_count_30d"),
                "insider_sell_count_30d": insider.get("sell_count_30d"),
                "insider_buy_count_90d": insider.get("buy_count_90d"),
                "insider_sell_count_90d": insider.get("sell_count_90d"),
                "insider_buy_value_90d": insider.get("buy_value_90d"),
                "insider_sell_value_90d": insider.get("sell_value_90d"),
                "insider_latest_action": insider.get("latest_action"),
                "insider_latest_disclosure_date": insider.get("latest_disclosure_date"),
                "insider_reason": insider.get("reason"),
                "broker_flow_status": broker_flow.get("status"),
                "broker_flow_score": broker_flow.get("score"),
                "broker_net_1d": broker_flow.get("net_1d"),
                "broker_net_3d": broker_flow.get("net_3d"),
                "broker_net_5d": broker_flow.get("net_5d"),
                "broker_net_pct_1d": broker_flow.get("net_pct_1d"),
                "broker_net_pct_3d": broker_flow.get("net_pct_3d"),
                "broker_net_pct_5d": broker_flow.get("net_pct_5d"),
                "broker_top_buyers": broker_flow.get("top_buyers"),
                "broker_top_sellers": broker_flow.get("top_sellers"),
                "broker_weighted_avg_buy_price_5d": broker_flow.get("weighted_avg_buy_price_5d"),
                "broker_flow_reason": broker_flow.get("reason"),
            }

            update_swing_portfolio(
                portfolio_id,
                updates,
            )
            position.update(updates)

            if signal in {
                "STOP_LOSS",
                "CONFIRMED_SELL",
            }:
                insert_swing_alert(
                    position=position,
                    alert_type=signal,
                    priority=result["priority"],
                    message=(
                        f"Price {daily['price']:.2f}. "
                        f"{result['reason']}"
                    ),
                    reason=result["reason"],
                )

            elif signal == "PROTECT_PROFIT":
                insert_swing_alert(
                    position=position,
                    alert_type=signal,
                    priority=result["priority"],
                    message=(
                        f"Price {daily['price']:.2f}. "
                        f"{result['reason']}"
                    ),
                    reason=result["reason"],
                    daily_dedupe=True,
                )

            elif signal in {"DISTRIBUTION_WATCH", "FOREIGN_SELL_CAUTION"}:
                insert_swing_alert(
                    position=position, alert_type=signal, priority=result["priority"],
                    message=(f"Price {daily['price']:.2f}. {result['reason']} Foreign 1D/3D/5D: {foreign_flow.get('net_pct_1d')}% / {foreign_flow.get('net_pct_3d')}% / {foreign_flow.get('net_pct_5d')}%."),
                    reason=result["reason"], daily_dedupe=True,
                )

            elif signal == "INSIDER_SELL_CAUTION":
                insert_swing_alert(
                    position=position,
                    alert_type=signal,
                    priority=result["priority"],
                    message=(
                        f"Price {daily['price']:.2f}. {result['reason']} "
                        f"Public insider BUY/SELL 30D: {insider.get('buy_count_30d')}/{insider.get('sell_count_30d')}."
                    ),
                    reason=result["reason"],
                    daily_dedupe=True,
                )

            elif signal == "BROKER_DISTRIBUTION_WATCH":
                insert_swing_alert(
                    position=position,
                    alert_type=signal,
                    priority=result["priority"],
                    message=(
                        f"Price {daily['price']:.2f}. {result['reason']} "
                        f"Broker 1D/3D/5D: {broker_flow.get('net_pct_1d')}% / "
                        f"{broker_flow.get('net_pct_3d')}% / {broker_flow.get('net_pct_5d')}%."
                    ),
                    reason=result["reason"],
                    daily_dedupe=True,
                )

            print(
                f"SWING PORTFOLIO {clean_ticker(ticker)} "
                f"portfolio={portfolio_id} "
                f"signal={signal} "
                f"pnl={result.get('pnl_pct')}",
                flush=True,
            )

        except Exception as exc:
            errors += 1
            print(
                f"SWING PORTFOLIO {ticker} failed: {exc}",
                flush=True,
            )

    return {
        "positions": len(positions),
        "monitored": monitored,
        "errors": errors,
    }



def fetch_universe():
    rows = supabase_request(
        "GET",
        "hanz_swing_universe"
        "?enabled=eq.true"
        "&select=ticker,priority"
        "&order=priority.desc,ticker.asc",
    ) or []

    tickers = []

    for row in rows:
        ticker = clean_ticker(
            row.get("ticker")
        )
        if ticker:
            tickers.append(ticker)

    return tickers[:MAX_SYMBOLS_PER_CYCLE]



# ============================================================
# DISCOUNT INTELLIGENCE V1
#
# Purpose:
# "Cheap" is not automatically "good".
# We combine:
#   1) analyst target gap (when available)
#   2) distance below 52-week high
#   3) technical quality / not-overextended structure
#   4) existing HANZ Swing score
#
# Missing analyst data is never invented. In that case HANZ labels
# the result TECHNICAL_ONLY rather than pretending it is an
# analyst-confirmed valuation discount.
# ============================================================


def _latest_two_values(df, row_candidates):
    """Return latest and previous numeric values from a financial statement row."""
    if df is None or getattr(df, "empty", True):
        return None, None

    row_name = None

    for candidate in row_candidates:
        if candidate in df.index:
            row_name = candidate
            break

    if row_name is None:
        return None, None

    series = df.loc[row_name]

    try:
        series = series.dropna()
    except Exception:
        return None, None

    values = []

    for value in series.tolist():
        number = safe_float(value)
        if number is not None:
            values.append(number)

    if not values:
        return None, None

    latest = values[0]
    previous = values[1] if len(values) > 1 else None
    return latest, previous


def _growth_pct(latest, previous):
    if (
        latest is None
        or previous is None
        or previous == 0
    ):
        return None

    # For negative-to-positive or negative-base cases, percentage growth
    # becomes misleading. We leave it unavailable and score profitability
    # separately instead of inventing a percentage.
    if previous < 0:
        return None

    return (latest - previous) / abs(previous) * 100


def _safe_ratio_pct(numerator, denominator):
    if (
        numerator is None
        or denominator in (None, 0)
    ):
        return None
    return numerator / denominator * 100


def get_company_intelligence(
    ticker,
    *,
    include_analyst=True,
    include_fundamental=True,
):
    """Fetch analyst + fundamental data once for one ticker.

    Source: yfinance/Yahoo public financial endpoints.
    Missing fields remain None. HANZ never fabricates missing fundamentals.
    """
    symbol = normalize_ticker(ticker)

    if not symbol:
        return {
            "analyst": {},
            "fundamental": {},
        }

    analyst = {}
    fundamental = {}

    try:
        obj = yf.Ticker(symbol)

        # ---------------------------------
        # Analyst targets
        # ---------------------------------
        if include_analyst:
            try:
                targets = obj.get_analyst_price_targets()

                if isinstance(targets, dict):
                    analyst = {
                        "current": safe_float(
                            targets.get("current")
                        ),
                        "low": safe_float(
                            targets.get("low")
                        ),
                        "high": safe_float(
                            targets.get("high")
                        ),
                        "mean": safe_float(
                            targets.get("mean")
                        ),
                        "median": safe_float(
                            targets.get("median")
                        ),
                    }
            except Exception as exc:
                print(
                    f"SWING INTEL {clean_ticker(ticker)} "
                    f"analyst unavailable: {exc}",
                    flush=True,
                )

        # ---------------------------------
        # Fundamental statements
        # ---------------------------------
        if include_fundamental:
            try:
                income = obj.get_income_stmt(
                    freq="yearly"
                )
            except Exception:
                income = None

            try:
                balance = obj.get_balance_sheet(
                    freq="yearly"
                )
            except Exception:
                balance = None

            try:
                cashflow = obj.get_cashflow(
                    freq="yearly"
                )
            except Exception:
                cashflow = None

            try:
                info = obj.get_info()
                if not isinstance(info, dict):
                    info = {}
            except Exception:
                info = {}

            revenue, revenue_prev = _latest_two_values(
                income,
                [
                    "Total Revenue",
                    "Operating Revenue",
                ],
            )

            net_income, net_income_prev = _latest_two_values(
                income,
                [
                    "Net Income",
                    "Net Income Common Stockholders",
                ],
            )

            operating_income, operating_income_prev = _latest_two_values(
                income,
                [
                    "Operating Income",
                ],
            )

            gross_profit, gross_profit_prev = _latest_two_values(
                income,
                [
                    "Gross Profit",
                ],
            )

            total_debt, total_debt_prev = _latest_two_values(
                balance,
                [
                    "Total Debt",
                    "Total Debt And Capital Lease Obligation",
                ],
            )

            equity, equity_prev = _latest_two_values(
                balance,
                [
                    "Stockholders Equity",
                    "Total Equity Gross Minority Interest",
                    "Common Stock Equity",
                ],
            )

            total_assets, total_assets_prev = _latest_two_values(
                balance,
                [
                    "Total Assets",
                ],
            )

            operating_cf, operating_cf_prev = _latest_two_values(
                cashflow,
                [
                    "Operating Cash Flow",
                    "Cash Flow From Continuing Operating Activities",
                ],
            )

            capex, capex_prev = _latest_two_values(
                cashflow,
                [
                    "Capital Expenditure",
                ],
            )

            revenue_growth = _growth_pct(
                revenue,
                revenue_prev,
            )

            net_income_growth = _growth_pct(
                net_income,
                net_income_prev,
            )

            operating_income_growth = _growth_pct(
                operating_income,
                operating_income_prev,
            )

            roe = safe_float(
                info.get("returnOnEquity")
            )
            if roe is not None:
                roe *= 100
            else:
                roe = _safe_ratio_pct(
                    net_income,
                    equity,
                )

            roa = safe_float(
                info.get("returnOnAssets")
            )
            if roa is not None:
                roa *= 100
            else:
                roa = _safe_ratio_pct(
                    net_income,
                    total_assets,
                )

            debt_to_equity = safe_float(
                info.get("debtToEquity")
            )
            if debt_to_equity is not None:
                # Yahoo convention is typically percentage points.
                debt_to_equity /= 100
            elif (
                total_debt is not None
                and equity not in (None, 0)
            ):
                debt_to_equity = (
                    total_debt / equity
                )

            net_margin = safe_float(
                info.get("profitMargins")
            )
            if net_margin is not None:
                net_margin *= 100
            else:
                net_margin = _safe_ratio_pct(
                    net_income,
                    revenue,
                )

            operating_margin = safe_float(
                info.get("operatingMargins")
            )
            if operating_margin is not None:
                operating_margin *= 100
            else:
                operating_margin = _safe_ratio_pct(
                    operating_income,
                    revenue,
                )

            gross_margin = safe_float(
                info.get("grossMargins")
            )
            if gross_margin is not None:
                gross_margin *= 100
            else:
                gross_margin = _safe_ratio_pct(
                    gross_profit,
                    revenue,
                )

            pe_ratio = safe_float(
                info.get("trailingPE")
            )
            pb_ratio = safe_float(
                info.get("priceToBook")
            )

            sector = str(
                info.get("sector")
                or ""
            ).strip() or None

            industry = str(
                info.get("industry")
                or ""
            ).strip() or None

            free_cf = None
            if operating_cf is not None:
                if capex is not None:
                    free_cf = (
                        operating_cf
                        + capex
                        if capex < 0
                        else operating_cf - capex
                    )
                else:
                    free_cf = operating_cf

            fundamental = {
                "sector": sector,
                "industry": industry,
                "revenue": revenue,
                "revenue_prev": revenue_prev,
                "revenue_growth_pct": safe_float(
                    revenue_growth
                ),
                "net_income": net_income,
                "net_income_prev": net_income_prev,
                "net_income_growth_pct": safe_float(
                    net_income_growth
                ),
                "operating_income_growth_pct": safe_float(
                    operating_income_growth
                ),
                "roe_pct": safe_float(roe),
                "roa_pct": safe_float(roa),
                "debt_to_equity": safe_float(
                    debt_to_equity
                ),
                "operating_cash_flow": operating_cf,
                "free_cash_flow": safe_float(free_cf),
                "net_margin_pct": safe_float(
                    net_margin
                ),
                "operating_margin_pct": safe_float(
                    operating_margin
                ),
                "gross_margin_pct": safe_float(
                    gross_margin
                ),
                "pe_ratio": pe_ratio,
                "pb_ratio": pb_ratio,
            }

    except Exception as exc:
        print(
            f"SWING INTEL {clean_ticker(ticker)} "
            f"company data unavailable: {exc}",
            flush=True,
        )

    return {
        "analyst": analyst,
        "fundamental": fundamental,
    }


def fundamental_intelligence_v1(
    fundamental,
):
    """Universal fundamental quality score 0-100.

    This is deliberately sector-agnostic V1. Banks/miners/property can
    receive sector-specific models later without changing table structure.
    """
    f = fundamental or {}

    components = []
    evidence = []

    revenue_growth = safe_float(
        f.get("revenue_growth_pct")
    )
    net_income_growth = safe_float(
        f.get("net_income_growth_pct")
    )
    roe = safe_float(
        f.get("roe_pct")
    )
    debt_to_equity = safe_float(
        f.get("debt_to_equity")
    )
    operating_cf = safe_float(
        f.get("operating_cash_flow")
    )
    free_cf = safe_float(
        f.get("free_cash_flow")
    )
    net_margin = safe_float(
        f.get("net_margin_pct")
    )
    operating_margin = safe_float(
        f.get("operating_margin_pct")
    )

    # Revenue growth — 20
    if revenue_growth is not None:
        if revenue_growth >= 15:
            points = 20
        elif revenue_growth >= 8:
            points = 16
        elif revenue_growth >= 3:
            points = 12
        elif revenue_growth >= 0:
            points = 8
        elif revenue_growth >= -5:
            points = 4
        else:
            points = 0
        components.append(("revenue_growth", points, 20))
        evidence.append(
            f"revenue growth {revenue_growth:+.1f}%"
        )

    # Net income growth — 20
    if net_income_growth is not None:
        if net_income_growth >= 20:
            points = 20
        elif net_income_growth >= 10:
            points = 16
        elif net_income_growth >= 3:
            points = 12
        elif net_income_growth >= 0:
            points = 8
        elif net_income_growth >= -10:
            points = 4
        else:
            points = 0
        components.append(("earnings_growth", points, 20))
        evidence.append(
            f"net income growth {net_income_growth:+.1f}%"
        )
    elif safe_float(f.get("net_income")) is not None:
        # Profitability direction still matters if growth cannot be
        # computed because the previous base was negative.
        net_income = safe_float(f.get("net_income"))
        points = 10 if net_income > 0 else 0
        components.append(("profitability", points, 20))
        evidence.append(
            "net income positive"
            if net_income > 0
            else "net income negative"
        )

    # ROE — 20
    if roe is not None:
        if roe >= 20:
            points = 20
        elif roe >= 15:
            points = 17
        elif roe >= 10:
            points = 13
        elif roe >= 5:
            points = 8
        elif roe > 0:
            points = 4
        else:
            points = 0
        components.append(("roe", points, 20))
        evidence.append(f"ROE {roe:.1f}%")

    # Debt / equity — 15
    if debt_to_equity is not None:
        if debt_to_equity <= 0.5:
            points = 15
        elif debt_to_equity <= 1.0:
            points = 12
        elif debt_to_equity <= 1.5:
            points = 8
        elif debt_to_equity <= 2.5:
            points = 4
        else:
            points = 0
        components.append(("leverage", points, 15))
        evidence.append(
            f"D/E {debt_to_equity:.2f}x"
        )

    # Operating cash flow — 15
    if operating_cf is not None:
        points = 15 if operating_cf > 0 else 0
        components.append(("operating_cf", points, 15))
        evidence.append(
            "operating cash flow positive"
            if operating_cf > 0
            else "operating cash flow negative"
        )

    # Margin quality — 10
    margin = (
        operating_margin
        if operating_margin is not None
        else net_margin
    )
    if margin is not None:
        if margin >= 20:
            points = 10
        elif margin >= 12:
            points = 8
        elif margin >= 7:
            points = 6
        elif margin > 0:
            points = 3
        else:
            points = 0
        components.append(("margin", points, 10))
        evidence.append(
            f"margin {margin:.1f}%"
        )

    max_available = sum(
        max_points
        for _, _, max_points in components
    )
    raw_points = sum(
        points
        for _, points, _ in components
    )

    if max_available == 0:
        score = None
        label = "NO_FUNDAMENTAL_DATA"
        confidence = "NONE"
    else:
        score = round(
            raw_points / max_available * 100,
            1,
        )

        coverage = max_available / 100

        if coverage >= 0.80:
            confidence = "HIGH"
        elif coverage >= 0.55:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        if score >= 75:
            label = "GOOD"
        elif score >= 55:
            label = "ACCEPTABLE"
        elif score >= 40:
            label = "WEAK"
        else:
            label = "BAD"

    return {
        "fundamental_score": score,
        "fundamental_label": label,
        "fundamental_confidence": confidence,
        "fundamental_coverage_pct": round(
            max_available,
            1,
        ),
        "fundamental_reason": "; ".join(evidence),
        **f,
    }



def discount_intelligence_v2(
    ticker,
    daily,
    weekly,
    result,
    analyst,
    fundamental_result,
):
    price = safe_float(daily.get("price"))
    score = safe_float(result.get("score")) or 0

    target_mean = safe_float(analyst.get("mean"))
    target_low = safe_float(analyst.get("low"))
    target_high = safe_float(analyst.get("high"))
    target_median = safe_float(analyst.get("median"))

    analyst_upside_pct = None
    target_discount_pct = None

    if (
        price not in (None, 0)
        and target_mean not in (None, 0)
    ):
        analyst_upside_pct = (
            (target_mean - price) / price * 100
        )
        target_discount_pct = (
            (target_mean - price) / target_mean * 100
        )

    # ---------------------
    # Component A: analyst valuation gap — 30 points
    # ---------------------
    analyst_points = None

    if target_discount_pct is not None:
        if target_discount_pct >= 35:
            analyst_points = 30
        elif target_discount_pct >= 25:
            analyst_points = 26
        elif target_discount_pct >= 15:
            analyst_points = 21
        elif target_discount_pct >= 8:
            analyst_points = 15
        elif target_discount_pct >= 3:
            analyst_points = 7
        else:
            analyst_points = 0

    # ---------------------
    # Component B: discount to 52-week high — 15 points
    # ---------------------
    week52_discount = safe_float(
        daily.get("week52_discount_pct")
    )

    if week52_discount is None:
        week52_points = 0
    elif week52_discount >= 30:
        week52_points = 15
    elif week52_discount >= 20:
        week52_points = 13
    elif week52_discount >= 10:
        week52_points = 10
    elif week52_discount >= 5:
        week52_points = 5
    else:
        week52_points = 1

    # ---------------------
    # Component C: technical quality — 20 points
    # Prevents "cheap because broken" from looking attractive.
    # ---------------------
    technical_points = 0

    if result.get("weekly_trend") == "BULLISH":
        technical_points += 8

    if result.get("daily_trend") == "BULLISH":
        technical_points += 5

    rsi_d = safe_float(daily.get("rsi14"))
    if rsi_d is not None and 50 <= rsi_d <= 70:
        technical_points += 3

    ema20 = safe_float(daily.get("ema20"))
    if (
        price not in (None, 0)
        and ema20 not in (None, 0)
        and price >= ema20
    ):
        extension_pct = (
            (price - ema20) / ema20 * 100
        )
        if extension_pct <= 8:
            technical_points += 4
        elif extension_pct <= 12:
            technical_points += 2

    # ---------------------
    # Component D: existing Swing score — 20 points
    # ---------------------
    swing_points = max(
        0,
        min(20, score * 2),
    )

    # ---------------------
    # Component E: fundamental quality — 15 points
    # ---------------------
    fundamental_score = safe_float(
        fundamental_result.get("fundamental_score")
        if fundamental_result else None
    )

    if fundamental_score is None:
        fundamental_points = None
    else:
        fundamental_points = max(
            0,
            min(
                15,
                fundamental_score / 100 * 15,
            ),
        )

    if analyst_points is not None:
        raw_score = (
            analyst_points
            + week52_points
            + technical_points
            + swing_points
            + (
                fundamental_points
                if fundamental_points is not None
                else 0
            )
        )

        max_score = (
            85
            + (
                15
                if fundamental_points is not None
                else 0
            )
        )

        raw_score = (
            raw_score / max_score * 100
        )
        discount_score = round(
            max(0, min(100, raw_score)),
            1,
        )
        confidence = "ANALYST_CONFIRMED"

        if (
            discount_score >= 75
            and result.get("state") in BUY_STATES
            and analyst_upside_pct is not None
            and analyst_upside_pct > 0
        ):
            label = "DISCOUNT_CONFIRMED"
        elif discount_score >= 65:
            label = "QUALITY_DISCOUNT"
        elif discount_score >= 50:
            label = "DISCOUNT_WATCH"
        else:
            label = "NOT_DISCOUNT"

    else:
        # No analyst target: normalize the factors we truly have.
        available = (
            week52_points
            + technical_points
            + swing_points
            + (
                fundamental_points
                if fundamental_points is not None
                else 0
            )
        )

        available_max = (
            55
            + (
                15
                if fundamental_points is not None
                else 0
            )
        )

        discount_score = round(
            max(
                0,
                min(
                    100,
                    available / available_max * 100,
                ),
            ),
            1,
        )

        confidence = (
            "FUNDAMENTAL_TECHNICAL"
            if fundamental_points is not None
            else "TECHNICAL_ONLY"
        )

        if discount_score >= 75:
            label = "TECHNICAL_VALUE_ZONE"
        elif discount_score >= 55:
            label = "FAIR_TECHNICAL_VALUE"
        else:
            label = "EXTENDED_OR_WEAK_VALUE"

    reason_parts = []

    if target_mean is not None and price is not None:
        reason_parts.append(
            f"analyst mean {target_mean:.2f}"
        )
        if analyst_upside_pct is not None:
            reason_parts.append(
                f"analyst upside {analyst_upside_pct:+.1f}%"
            )
    else:
        reason_parts.append(
            "analyst target unavailable"
        )

    if week52_discount is not None:
        reason_parts.append(
            f"{week52_discount:.1f}% below 52W high"
        )

    reason_parts.append(
        f"technical quality {technical_points}/20"
    )
    reason_parts.append(
        f"swing {int(score)}/10"
    )

    if fundamental_score is not None:
        reason_parts.append(
            f"fundamental {fundamental_score:.0f}/100 "
            f"{fundamental_result.get('fundamental_label')}"
        )
    else:
        reason_parts.append(
            "fundamental unavailable"
        )

    return {
        "analyst_target_mean": target_mean,
        "analyst_target_median": target_median,
        "analyst_target_low": target_low,
        "analyst_target_high": target_high,
        "analyst_upside_pct": safe_float(
            analyst_upside_pct
        ),
        "target_discount_pct": safe_float(
            target_discount_pct
        ),
        "week52_high": daily.get("week52_high"),
        "week52_low": daily.get("week52_low"),
        "week52_discount_pct": daily.get(
            "week52_discount_pct"
        ),
        "week52_position_pct": daily.get(
            "week52_position_pct"
        ),
        "discount_score": discount_score,
        "discount_label": label,
        "discount_confidence": confidence,
        "discount_reason": "; ".join(reason_parts),
        "fundamental_score": fundamental_score,
        "fundamental_label": (
            fundamental_result.get("fundamental_label")
            if fundamental_result else None
        ),
        "fundamental_confidence": (
            fundamental_result.get("fundamental_confidence")
            if fundamental_result else None
        ),
    }



def fetch_active_swing_monitor_rows():
    data = supabase_request(
        "GET",
        "hanz_swing_signal_monitor"
        "?state=eq.SWING_BUY"
        "&select=ticker,price,updated_at"
        "&order=score.desc",
    )
    return data or []


def refresh_swing_buy_intraday_prices():
    """
    Adaptive intraday price refresh for existing SWING_BUY rows.

    Key rule:
      - A ticker bar older than INTRADAY_STALE_MINUTES is NOT automatically stale.
      - First evaluate overall feed health using all active SWING_BUY tickers.
      - If the feed is healthy, an old ticker bar is classified LAST_TRADE
        (valid last traded price; ticker may simply have no recent transaction).
      - If the feed is unhealthy and the ticker bar is old, classify STALE_FEED
        and do NOT overwrite the stored price.

    This prevents illiquid/quiet IDX stocks from being falsely marked stale.
    """
    rows = fetch_active_swing_monitor_rows()
    refreshed = 0
    last_trade = 0
    stale_feed = 0
    errors = 0
    details = []

    # Phase 1: collect all quotes before deciding whether the provider feed is healthy.
    quote_rows = []
    for row in rows:
        ticker = row.get("ticker")
        if not ticker:
            continue

        try:
            q = latest_intraday_quote(ticker)
            quote_rows.append((row, ticker, q))
        except Exception as exc:
            errors += 1
            details.append({
                "ticker": clean_ticker(ticker),
                "status": "ERROR",
                "error": str(exc),
            })
            print(
                f"SWING QUOTE {clean_ticker(ticker)} ERROR: {exc}",
                flush=True,
            )

    valid_quotes = [
        q for _, _, q in quote_rows
        if q.get("price") is not None
    ]
    fresh_quotes = [
        q for q in valid_quotes
        if q.get("fresh_by_age")
    ]

    total_valid = len(valid_quotes)
    fresh_count = len(fresh_quotes)
    fresh_ratio = (
        fresh_count / total_valid
        if total_valid
        else 0.0
    )

    if total_valid == 0:
        feed_healthy = False
    elif total_valid < INTRADAY_FEED_HEALTH_MIN_SYMBOLS:
        # With only one usable symbol, accept the feed only if that symbol itself is fresh.
        feed_healthy = fresh_count == total_valid
    else:
        feed_healthy = (
            fresh_ratio >= INTRADAY_FEED_HEALTH_FRESH_RATIO
        )

    feed_status = "HEALTHY" if feed_healthy else "STALE_FEED"

    print(
        "SWING FEED HEALTH "
        f"{feed_status} "
        f"fresh={fresh_count}/{total_valid} "
        f"ratio={fresh_ratio:.0%} "
        f"age_guard={INTRADAY_STALE_MINUTES}m",
        flush=True,
    )

    # Phase 2: classify each quote using overall feed health.
    for row, ticker, q in quote_rows:
        clean = clean_ticker(ticker)
        age = q["age_minutes"]
        price_value = q["price"]

        if q.get("fresh_by_age"):
            status = "OK"
            allow_update = True
            refreshed += 1
        elif feed_healthy:
            # Provider is updating other symbols normally.
            # This ticker most likely simply has no recent transaction.
            status = "LAST_TRADE"
            allow_update = True
            last_trade += 1
        else:
            status = "STALE_FEED"
            allow_update = False
            stale_feed += 1

        if allow_update:
            supabase_request(
                "PATCH",
                "hanz_swing_signal_monitor"
                f"?ticker=eq.{urllib.parse.quote(clean)}",
                {
                    "price": price_value,
                    "updated_at": now_iso(),
                },
                prefer="return=minimal",
            )

        details.append({
            "ticker": clean,
            "status": status,
            "price": price_value,
            "age_minutes": age,
            "bar_at": q["bar_at"],
            "feed_status": feed_status,
            "updated": allow_update,
            "source": q.get("source"),
            "fallback_used": q.get("fallback_used", False),
        })

        if status == "OK":
            print(
                f"SWING QUOTE {clean} "
                f"price={price_value} "
                f"age={age:.1f}m "
                f"bar={q['bar_at']} "
                f"source={q.get('source')} "
                f"fallback={q.get('fallback_used', False)} OK",
                flush=True,
            )
        elif status == "LAST_TRADE":
            print(
                f"SWING QUOTE {clean} "
                f"price={price_value} "
                f"age={age:.1f}m "
                f"bar={q['bar_at']} "
                f"source={q.get('source')} "
                f"fallback={q.get('fallback_used', False)} LAST_TRADE "
                f"| feed={feed_status}; price accepted.",
                flush=True,
            )
        else:
            print(
                f"SWING QUOTE {clean} STALE_FEED "
                f"age={age:.1f}m "
                f"bar={q['bar_at']} "
                f"source={q.get('source')} "
                f"fallback={q.get('fallback_used', False)} "
                f"| feed={feed_status}; stored price NOT overwritten.",
                flush=True,
            )

    return {
        "rows": len(rows),
        "valid_quotes": total_valid,
        "fresh_quotes": fresh_count,
        "fresh_ratio": round(fresh_ratio, 4),
        "feed_status": feed_status,
        "refreshed": refreshed,
        "last_trade": last_trade,
        "stale_feed": stale_feed,
        "errors": errors,
        "stale_guard_minutes": INTRADAY_STALE_MINUTES,
        "feed_health_fresh_ratio": INTRADAY_FEED_HEALTH_FRESH_RATIO,
        "details": details,
    }




def latest_completed_idx_date(now=None):
    """
    Return the latest IDX trading date whose daily candle should be complete.
    Before today's close, this is the previous trading day. After POST_CLOSE,
    it is today.
    """
    now = now or jakarta_now()
    market = idx_market_session(now)

    if market.get("is_trading_day") and market.get("allow_final_scan"):
        return now.date()

    return previous_idx_trading_day(now.date())


def intraday_to_daily_frame(ticker):
    """
    Aggregate recent intraday bars into Jakarta-date OHLCV daily bars.
    Used only to repair a missing/stale latest completed daily candle.
    """
    df = download_frame(
        ticker,
        CHART_REPAIR_INTRADAY_INTERVAL,
        CHART_REPAIR_INTRADAY_PERIOD,
    ).copy()

    if df.empty:
        return df

    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        idx = idx.tz_localize(JAKARTA_TZ)
    else:
        idx = idx.tz_convert(JAKARTA_TZ)

    df.index = idx
    df["_date"] = idx.date

    grouped = df.groupby("_date", sort=True).agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
    )
    grouped.index = pd.to_datetime(grouped.index)
    return grouped


def ensure_latest_completed_daily_bar(ticker, daily_df):
    """
    Repair stale Yahoo 1d history when the latest completed IDX session is
    missing. We never fabricate a candle: the repair happens only when recent
    intraday bars contain the exact completed trading date.
    """
    frame = daily_df.copy()
    target_date = latest_completed_idx_date()

    last_date = pd.Timestamp(frame.index[-1]).date()
    if last_date >= target_date:
        return frame, {
            "target_date": target_date.isoformat(),
            "source": "DAILY",
            "repaired": False,
            "last_date": last_date.isoformat(),
        }

    intraday_daily = intraday_to_daily_frame(ticker)
    if intraday_daily is None or intraday_daily.empty:
        raise RuntimeError(
            f"Latest completed candle missing: daily={last_date}, "
            f"target={target_date}, intraday repair unavailable"
        )

    repair_row = None
    for idx, row in intraday_daily.iterrows():
        if pd.Timestamp(idx).date() == target_date:
            repair_row = row
            break

    if repair_row is None:
        available = [
            pd.Timestamp(x).date().isoformat()
            for x in intraday_daily.index
        ]
        raise RuntimeError(
            f"Latest completed candle missing: daily={last_date}, "
            f"target={target_date}, intraday dates={available}"
        )

    repair_ts = pd.Timestamp(target_date)
    replacement = pd.DataFrame(
        [{
            "Open": safe_float(repair_row["Open"]),
            "High": safe_float(repair_row["High"]),
            "Low": safe_float(repair_row["Low"]),
            "Close": safe_float(repair_row["Close"]),
            "Volume": safe_float(repair_row["Volume"]),
        }],
        index=[repair_ts],
    )

    # Remove any duplicate date, append repaired candle, and preserve ordering.
    keep = [
        pd.Timestamp(x).date() != target_date
        for x in frame.index
    ]
    frame = frame.loc[keep]
    frame = pd.concat([frame, replacement]).sort_index()

    return frame, {
        "target_date": target_date.isoformat(),
        "source": "INTRADAY_AGGREGATED",
        "repaired": True,
        "last_date": target_date.isoformat(),
    }


def chart_candles_from_daily_df(daily_df, limit=None):
    """
    Serialize completed daily OHLCV bars already downloaded by the engine.

    Full universe scans only run after the IDX final-scan gate opens, so the
    last daily bar used here is a completed bar. No browser-side Yahoo request
    is required later.
    """
    limit = max(60, int(limit or CHART_LOOKBACK_BARS))
    frame = daily_df.tail(limit).copy()

    candles = []
    for idx, row in frame.iterrows():
        o = safe_float(row.get("Open"))
        h = safe_float(row.get("High"))
        l = safe_float(row.get("Low"))
        c = safe_float(row.get("Close"))
        v = safe_float(row.get("Volume"))

        if None in (o, h, l, c):
            continue

        ts = pd.Timestamp(idx)
        if ts.tzinfo is not None:
            ts = ts.tz_convert(JAKARTA_TZ)

        candles.append({
            "time": ts.date().isoformat(),
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": int(v) if v is not None else 0,
        })

    return candles


def upsert_chart_data(ticker, daily_df, result):
    """
    Persist chart data only for active HANZ signal states.
    One compact JSON row per ticker keeps dashboard reads fast and avoids CORS.
    """
    state = str(result.get("state") or "")
    if state not in CHART_STATES:
        return {"stored": False, "reason": "inactive_state"}

    repaired_df, freshness = ensure_latest_completed_daily_bar(
        ticker,
        daily_df,
    )

    candles = chart_candles_from_daily_df(repaired_df)
    if len(candles) < 60:
        raise RuntimeError(
            f"Insufficient chart candles for {clean_ticker(ticker)}"
        )

    if candles[-1]["time"] != freshness["target_date"]:
        raise RuntimeError(
            f"Chart freshness check failed for {clean_ticker(ticker)}: "
            f"last={candles[-1]['time']} target={freshness['target_date']}"
        )

    payload = {
        "ticker": clean_ticker(ticker),
        "state": state,
        "source_bar_at": candles[-1]["time"],
        "candles": candles,
        "updated_at": now_iso(),
    }

    supabase_request(
        "POST",
        "hanz_swing_chart_data?on_conflict=ticker",
        payload,
        prefer="resolution=merge-duplicates,return=minimal",
    )

    return {
        "stored": True,
        "bars": len(candles),
        "source_bar_at": candles[-1]["time"],
        "target_date": freshness["target_date"],
        "bar_source": freshness["source"],
        "repaired": freshness["repaired"],
    }


def upsert_monitor(
    ticker,
    daily,
    weekly,
    result,
    levels,
    discount,
    fundamental,
    risk_validation,
):
    payload = {
        "ticker": clean_ticker(ticker),
        "state": result["state"],
        "score": result["score"],
        "price": daily["price"],
        "daily_trend": result["daily_trend"],
        "weekly_trend": result["weekly_trend"],
        "daily_rsi": daily["rsi14"],
        "weekly_rsi": weekly["rsi14"],
        "daily_rvol": daily["rvol20"],
        "breakout": result["breakout"],
        "breakout_level": daily["prior_high20"],
        "entry_price": levels.get("entry_price"),
        "entry_low": levels.get("entry_low"),
        "entry_high": levels.get("entry_high"),
        "entry_status": levels.get("entry_status"),
        "entry_note": levels.get("entry_note"),
        "stop_loss": levels["stop_loss"],
        "target_1": levels["target_1"],
        "target_2": levels["target_2"],
        "rr_target_1": levels.get("rr_target_1"),
        "rr_target_2": levels.get("rr_target_2"),
        "target_mode": levels.get("target_mode"),
        "analyst_target_mean": discount.get("analyst_target_mean"),
        "analyst_target_median": discount.get("analyst_target_median"),
        "analyst_target_low": discount.get("analyst_target_low"),
        "analyst_target_high": discount.get("analyst_target_high"),
        "analyst_upside_pct": discount.get("analyst_upside_pct"),
        "target_discount_pct": discount.get("target_discount_pct"),
        "week52_high": discount.get("week52_high"),
        "week52_low": discount.get("week52_low"),
        "week52_discount_pct": discount.get("week52_discount_pct"),
        "week52_position_pct": discount.get("week52_position_pct"),
        "discount_score": discount.get("discount_score"),
        "discount_label": discount.get("discount_label"),
        "discount_confidence": discount.get("discount_confidence"),
        "discount_reason": discount.get("discount_reason"),
        "fundamental_score": discount.get("fundamental_score"),
        "fundamental_label": discount.get("fundamental_label"),
        "fundamental_confidence": discount.get("fundamental_confidence"),
        "fundamental_coverage_pct": fundamental.get("fundamental_coverage_pct"),
        "fundamental_reason": fundamental.get("fundamental_reason"),
        "sector": fundamental.get("sector"),
        "industry": fundamental.get("industry"),
        "revenue_growth_pct": fundamental.get("revenue_growth_pct"),
        "net_income_growth_pct": fundamental.get("net_income_growth_pct"),
        "roe_pct": fundamental.get("roe_pct"),
        "roa_pct": fundamental.get("roa_pct"),
        "debt_to_equity": fundamental.get("debt_to_equity"),
        "operating_cash_flow": fundamental.get("operating_cash_flow"),
        "free_cash_flow": fundamental.get("free_cash_flow"),
        "net_margin_pct": fundamental.get("net_margin_pct"),
        "operating_margin_pct": fundamental.get("operating_margin_pct"),
        "pe_ratio": fundamental.get("pe_ratio"),
        "pb_ratio": fundamental.get("pb_ratio"),
        "market_regime": risk_validation.get("market_regime"),
        "risk_gate": risk_validation.get("gate"),
        "risk_score": risk_validation.get("score"),
        "risk_validation": risk_validation,
        "evidence": "; ".join(
            result["evidence"]
        ),
        "daily_bar_at": daily["bar_at"],
        "weekly_bar_at": weekly["bar_at"],
        "updated_at": now_iso(),
    }

    supabase_request(
        "POST",
        "hanz_swing_signal_monitor"
        "?on_conflict=ticker",
        payload,
        prefer=(
            "resolution=merge-duplicates,"
            "return=minimal"
        ),
    )


def insert_swing_signal(
    ticker,
    daily,
    result,
    levels,
):
    # Log only actionable confirmed BUY transitions.
    signal_type = (
        "EARLY_CONFIRMED_BUY"
        if result.get("state") == "EARLY_CONFIRMED_BUY"
        else "SWING_BUY"
    )
    ticker_encoded = urllib.parse.quote(
        clean_ticker(ticker), safe=""
    )

    existing = supabase_request(
        "GET",
        "hanz_swing_signals"
        f"?ticker=eq.{ticker_encoded}"
        f"&signal_type=eq.{signal_type}"
        "&select=id,created_at"
        "&order=created_at.desc"
        "&limit=1",
    ) or []

    # One SWING_BUY record per ticker per calendar day.
    if existing:
        created = str(
            existing[0].get("created_at")
            or ""
        )[:10]
        if created == utc_now().date().isoformat():
            return

    payload = {
        "ticker": clean_ticker(ticker),
        "signal_type": signal_type,
        "price": daily["price"],
        "entry_price": levels.get("entry_price"),
        "entry_low": levels.get("entry_low"),
        "entry_high": levels.get("entry_high"),
        "entry_status": levels.get("entry_status"),
        "score": result["score"],
        "stop_loss": levels["stop_loss"],
        "target_1": levels["target_1"],
        "target_2": levels["target_2"],
        "rr_target_1": levels.get("rr_target_1"),
        "rr_target_2": levels.get("rr_target_2"),
        "target_mode": levels.get("target_mode"),
        "reason": "; ".join(
            result["evidence"]
        ),
        "created_at": now_iso(),
    }

    supabase_request(
        "POST",
        "hanz_swing_signals",
        payload,
        prefer="return=minimal",
    )



def scan_predictive_radar_symbol(ticker):
    """
    Intraday predictive radar.

    Writes INTERNAL radar states to the monitor table so the next completed
    daily bar can reconfirm them. It never inserts a signal, sends a push,
    or creates a user-facing BUY.
    """
    daily_df_raw = download_frame(
        ticker,
        DAILY_INTERVAL,
        DAILY_PERIOD,
    )
    daily_df = _completed_daily_frame_for_radar(daily_df_raw)

    weekly_df = download_frame(
        ticker,
        WEEKLY_INTERVAL,
        WEEKLY_PERIOD,
    )

    daily = daily_metrics(daily_df)
    weekly = weekly_metrics(weekly_df)
    prior_monitor = fetch_prior_monitor(ticker)
    prior_state = str((prior_monitor or {}).get("state") or "").upper()

    # Never let the internal radar overwrite an already confirmed BUY or a
    # safety-broken state during the live session.
    if prior_state in {"SWING_BUY", "MOMENTUM_BROKEN"}:
        return "PRESERVE_ACTIVE"

    baseline = early_signal_score(daily, weekly)
    if (
        int(baseline.get("score") or 0) < RADAR_BASE_MIN_SCORE
        and not prior_state.startswith("RADAR_")
        and prior_state not in {"EARLY_WATCH", "PRE_ALERT", "SETUP_READY"}
    ):
        return "NO_RADAR"

    snapshot = intraday_radar_snapshot(
        ticker,
        daily_df,
        daily,
    )
    radar = predictive_radar_signal(
        daily,
        weekly,
        snapshot,
    )

    base_result = swing_score(
        daily,
        weekly,
    )

    result = {
        **base_result,
        "state": radar["state"],
        "score": radar["score"],
        "early_score": baseline.get("score", 0),
        "raw_buy_gate": False,
        "reconfirmed": False,
        "evidence": radar["evidence"],
    }

    # Use live price only for provisional internal risk/entry diagnostics.
    # daily_bar_at remains the last COMPLETED daily candle so post-close can
    # prove that a new completed candle exists.
    radar_daily = dict(daily)
    if safe_float(snapshot.get("price")) is not None:
        radar_daily["price"] = safe_float(snapshot.get("price"))
    if safe_float(snapshot.get("projected_rvol")) is not None:
        radar_daily["rvol20"] = safe_float(snapshot.get("projected_rvol"))
    if safe_float(snapshot.get("intraday_return_pct")) is not None:
        radar_daily["ret1_pct"] = safe_float(snapshot.get("intraday_return_pct"))
    if safe_float(snapshot.get("gap_pct")) is not None:
        radar_daily["gap_pct"] = safe_float(snapshot.get("gap_pct"))
    if safe_float(snapshot.get("day_range_pct")) is not None:
        radar_daily["day_range_pct"] = safe_float(snapshot.get("day_range_pct"))
    if safe_float(snapshot.get("breakout_distance_pct")) is not None:
        radar_daily["breakout_distance_pct"] = safe_float(
            snapshot.get("breakout_distance_pct")
        )

    fundamental = fundamental_intelligence_v1({})
    discount = discount_intelligence_v2(
        ticker,
        radar_daily,
        weekly,
        result,
        {},
        fundamental,
    )
    levels = risk_levels(
        radar_daily,
        result=result,
        discount=discount,
        fundamental=fundamental,
    )
    risk_validation = real_money_validation(
        ticker,
        radar_daily,
        result,
        levels,
        fundamental,
        _REAL_MONEY_CONTEXT,
    )
    risk_validation["radar_internal"] = True
    risk_validation["radar_state"] = radar["state"]
    risk_validation["radar_score"] = radar["score"]
    risk_validation["radar_armed"] = bool(radar.get("armed"))
    risk_validation["radar_snapshot"] = snapshot
    risk_validation["dashboard_eligible"] = False
    risk_validation["reconfirmation_required"] = True

    # If a previously armed radar loses the setup before close, clear it.
    # NO_SETUP is internal and is hidden by the dashboard.
    upsert_monitor(
        ticker,
        radar_daily,
        weekly,
        result,
        levels,
        discount,
        fundamental,
        risk_validation,
    )

    print(
        f"RADAR {clean_ticker(ticker)} "
        f"{radar['state']} score={radar['score']}/10 "
        f"base={baseline.get('score', 0)}/10 "
        f"price={snapshot.get('price')} "
        f"dist={snapshot.get('breakout_distance_pct')}% "
        f"pace={snapshot.get('projected_rvol')}x "
        f"ret={snapshot.get('intraday_return_pct')}% "
        f"30m={snapshot.get('last_30m_return_pct')}% "
        f"volacc={snapshot.get('intraday_volume_accel')}x "
        f"fresh={snapshot.get('fresh')} "
        f"INTERNAL_ONLY=TRUE",
        flush=True,
    )

    return radar["state"]


def _mover_reason(daily, direction, foreign_flow=None, insider=None, broker_flow=None):
    """Explain observed movement without claiming unverified causality."""
    reasons = []

    change = safe_float(daily.get("ret1_pct"))
    rvol = safe_float(daily.get("rvol20"))
    price = safe_float(daily.get("price"))
    ema20 = safe_float(daily.get("ema20"))
    prior_high20 = safe_float(daily.get("prior_high20"))
    prior_low20 = safe_float(daily.get("prior_low20"))
    gap = safe_float(daily.get("gap_pct"))

    if change is not None:
        reasons.append(f"price {'rose' if change >= 0 else 'fell'} {abs(change):.2f}% on the latest completed daily bar")

    if rvol is not None:
        if rvol >= 2.0:
            reasons.append(f"volume surged to {rvol:.2f}x the 20-day average")
        elif rvol >= 1.3:
            reasons.append(f"volume was elevated at {rvol:.2f}x the 20-day average")
        elif rvol <= 0.70:
            reasons.append(f"move occurred on relatively light volume ({rvol:.2f}x average)")

    if gap is not None and abs(gap) >= 1.5:
        reasons.append(f"session opened with a {gap:+.2f}% gap")

    if direction == "UP":
        if price is not None and prior_high20 is not None and price > prior_high20:
            reasons.append("price closed above the prior 20-day high")
        elif price is not None and ema20 is not None and price > ema20:
            reasons.append("price held above EMA20")
    else:
        if price is not None and prior_low20 is not None and price < prior_low20:
            reasons.append("price closed below the prior 20-day low")
        elif price is not None and ema20 is not None and price < ema20:
            reasons.append("price closed below EMA20")

    flow_notes = []
    ff = str((foreign_flow or {}).get("status") or "UNKNOWN").upper()
    bf = str((broker_flow or {}).get("status") or "UNKNOWN").upper()
    ins = str((insider or {}).get("status") or "UNKNOWN").upper()

    if ff not in {"UNKNOWN", "DISABLED", "NEUTRAL"}:
        flow_notes.append(f"foreign {ff.replace('_',' ').lower()}")
    if bf not in {"UNKNOWN", "DISABLED", "NEUTRAL"}:
        flow_notes.append(f"broker {bf.replace('BROKER_','').replace('_',' ').lower()}")
    if ins not in {"UNKNOWN", "DISABLED", "NEUTRAL"}:
        flow_notes.append(f"public insider {ins.replace('_',' ').lower()}")

    movement_reason = "; ".join(reasons[:4]) if reasons else "No strong technical explanation available."
    flow_reason = "; ".join(flow_notes) if flow_notes else "No verified flow catalyst available."

    return movement_reason, flow_reason


def collect_market_mover(ticker, daily_df, daily, foreign_flow, insider, broker_flow):
    if not MARKET_MOVERS_ENABLED:
        return

    try:
        change = safe_float(daily.get("ret1_pct"))
        price = safe_float(daily.get("price"))
        if change is None or price is None:
            return

        volume = safe_float(daily_df["Volume"].iloc[-1])
        avg_volume20 = safe_float(daily_df["Volume"].iloc[-20:].astype(float).mean()) if len(daily_df) >= 20 else None
        traded_value = (price * volume) if volume is not None else None
        prev_close = safe_float(daily_df["Close"].iloc[-2]) if len(daily_df) >= 2 else None

        bars = daily_df.iloc[-max(5, MARKET_MOVERS_CHART_BARS):]
        chart_points = []
        for idx, row in bars.iterrows():
            try:
                label = pd.Timestamp(idx).strftime("%d %b")
            except Exception:
                label = str(idx)[:10]
            chart_points.append({
                "date": label,
                "close": safe_float(row.get("Close")),
                "volume": safe_float(row.get("Volume")),
            })

        direction = "UP" if change >= 0 else "DOWN"
        movement_reason, flow_reason = _mover_reason(
            daily, direction, foreign_flow, insider, broker_flow
        )

        _MARKET_MOVER_ROWS.append({
            "ticker": clean_ticker(ticker),
            "direction": direction,
            "change_pct": safe_float(change),
            "price": price,
            "open": safe_float(daily.get("open")),
            "high": safe_float(daily.get("high")),
            "low": safe_float(daily.get("low")),
            "prev_close": prev_close,
            "volume": volume,
            "avg_volume20": avg_volume20,
            "rvol20": safe_float(daily.get("rvol20")),
            "traded_value": safe_float(traded_value),
            "chart_points": chart_points,
            "movement_reason": movement_reason,
            "flow_reason": flow_reason,
            "foreign_status": (foreign_flow or {}).get("status"),
            "broker_status": (broker_flow or {}).get("status"),
            "insider_status": (insider or {}).get("status"),
        })
    except Exception as exc:
        print(f"MARKET MOVER collect {ticker} skipped: {exc}", flush=True)


def publish_market_movers():
    if not MARKET_MOVERS_ENABLED:
        return {"published": 0, "enabled": False}

    valid = [r for r in _MARKET_MOVER_ROWS if safe_float(r.get("change_pct")) is not None]
    gainers = sorted(
        [r for r in valid if safe_float(r.get("change_pct")) >= 0],
        key=lambda r: (safe_float(r.get("change_pct")) or 0, safe_float(r.get("traded_value")) or 0),
        reverse=True,
    )[:MARKET_MOVERS_TOP_N]
    losers = sorted(
        [r for r in valid if safe_float(r.get("change_pct")) < 0],
        key=lambda r: (safe_float(r.get("change_pct")) or 0, -(safe_float(r.get("traded_value")) or 0)),
    )[:MARKET_MOVERS_TOP_N]

    payload = []
    for direction, rows in (("UP", gainers), ("DOWN", losers)):
        for rank, row in enumerate(rows, 1):
            item = dict(row)
            item["direction"] = direction
            item["rank"] = rank
            payload.append(item)

    try:
        # Current snapshot only; remove stale prior ranking then insert fresh Top-N.
        supabase_request("DELETE", "hanz_market_movers_current?rank=gte.1")
        if payload:
            supabase_request(
                "POST",
                "hanz_market_movers_current",
                payload=payload,
                prefer="return=minimal",
            )
        return {"published": len(payload), "gainers": len(gainers), "losers": len(losers)}
    except Exception as exc:
        print(f"MARKET MOVERS publish failed: {exc}", flush=True)
        return {"published": 0, "error": str(exc)}


def scan_symbol(ticker, maintenance_mode=False):
    daily_df = download_frame(
        ticker,
        DAILY_INTERVAL,
        DAILY_PERIOD,
    )

    weekly_df = download_frame(
        ticker,
        WEEKLY_INTERVAL,
        WEEKLY_PERIOD,
    )

    daily = daily_metrics(daily_df)
    weekly = weekly_metrics(weekly_df)

    base_result = swing_score(
        daily,
        weekly,
    )

    prior_monitor = fetch_prior_monitor(ticker)
    result = apply_early_state_and_reconfirmation(
        ticker,
        daily,
        weekly,
        base_result,
        prior_monitor,
    )

    company_intel = {
        "analyst": {},
        "fundamental": {},
    }

    if (
        result.get("state") in DISCOUNT_ANALYST_STATES
        or result.get("state") in FUNDAMENTAL_STATES
    ):
        company_intel = get_company_intelligence(
            ticker,
            include_analyst=(
                result.get("state")
                in DISCOUNT_ANALYST_STATES
            ),
            include_fundamental=(
                result.get("state")
                in FUNDAMENTAL_STATES
            ),
        )

        if FUNDAMENTAL_FETCH_DELAY_SECONDS > 0:
            time.sleep(
                FUNDAMENTAL_FETCH_DELAY_SECONDS
            )

    fundamental = fundamental_intelligence_v1(
        company_intel.get("fundamental")
    )

    discount = discount_intelligence_v2(
        ticker,
        daily,
        weekly,
        result,
        company_intel.get("analyst") or {},
        fundamental,
    )

    levels = risk_levels(
        daily,
        result=result,
        discount=discount,
        fundamental=fundamental,
    )

    risk_validation = real_money_validation(
        ticker,
        daily,
        result,
        levels,
        fundamental,
        _REAL_MONEY_CONTEXT,
    )
    foreign_flow = foreign_flow_snapshot(ticker)
    risk_validation = apply_foreign_flow_to_risk_validation(risk_validation, foreign_flow)
    insider = insider_disclosure_snapshot(ticker)
    risk_validation = apply_insider_to_risk_validation(risk_validation, insider)
    broker_flow = broker_flow_snapshot(ticker)
    risk_validation = apply_broker_flow_to_risk_validation(risk_validation, broker_flow)
    risk_validation["canonical_rank_score"] = canonical_rank_score(
        result, risk_validation
    )
    risk_validation["canonical_rank_version"] = CANONICAL_RANK_VERSION

    collect_market_mover(
        ticker,
        daily_df,
        daily,
        foreign_flow,
        insider,
        broker_flow,
    )

    # V8.8 OFF-MARKET CANDIDATE REFRESH
    #
    # Root cause fixed:
    # Earlier weekend/holiday maintenance recomputed the full universe but only
    # persisted MOMENTUM_BROKEN.  That meant a newly attractive Friday setup
    # (for example a fresh breakout/retest candidate) could not enter the monitor
    # table until the next trading-day post-close run.  The dashboard could
    # therefore collapse to a single old candidate even though several valid
    # completed-bar setups existed.
    #
    # Safe behavior now:
    # - Refresh ALL monitor states from the latest completed daily bar while IDX
    #   is closed, so Top-5 opportunity ranking is current on weekends/holidays.
    # - Never create a NEW actionable SWING_BUY off-market.  A symbol that would
    #   newly qualify as SWING_BUY is published as SETUP_READY instead.
    # - Existing previously-confirmed SWING_BUY may remain SWING_BUY so the
    #   dashboard can continue monitoring it; no signal/alert/order is created
    #   because maintenance_mode blocks execution side effects below.
    prior_state = str((prior_monitor or {}).get("state") or "").upper()
    maintenance_write = True
    if maintenance_mode and result.get("state") in BUY_STATES and prior_state not in BUY_STATES:
        result = dict(result)
        result["state"] = "SETUP_READY"
        result["reconfirmed"] = False
        result["final_action"] = "WAIT"
        result["evidence"] = list(result.get("evidence") or []) + [
            "OFF_MARKET: latest completed-bar setup refreshed; new BUY waits for next trading-session reconfirmation"
        ]
        # Recalculate the independent execution gate against the downgraded
        # display state so it cannot look actionable while the exchange is shut.
        risk_validation = real_money_validation(
            ticker, daily, result, levels, fundamental, _REAL_MONEY_CONTEXT
        )
        risk_validation = apply_foreign_flow_to_risk_validation(
            risk_validation, foreign_flow
        )
        risk_validation = apply_insider_to_risk_validation(
            risk_validation, insider
        )
        risk_validation = apply_broker_flow_to_risk_validation(
            risk_validation, broker_flow
        )
        risk_validation["canonical_rank_score"] = canonical_rank_score(
            result, risk_validation
        )
        risk_validation["canonical_rank_version"] = CANONICAL_RANK_VERSION

    if maintenance_write:
        upsert_monitor(
            ticker,
            daily,
            weekly,
            result,
            levels,
            discount,
            fundamental,
            risk_validation,
        )

    chart_summary = {"stored": False}
    if result.get("state") in CHART_STATES:
        try:
            chart_summary = upsert_chart_data(
                ticker,
                daily_df,
                result,
            )
        except Exception as exc:
            # Chart persistence must never break the signal engine.
            print(
                f"SWING CHART {clean_ticker(ticker)} failed: {exc}",
                flush=True,
            )

    if (
        not maintenance_mode
        and result["state"] in BUY_STATES
        and risk_validation.get("actionable")
    ):
        insert_swing_signal(
            ticker,
            daily,
            result,
            levels,
        )

    print(
        f"SWING {clean_ticker(ticker)} "
        f"{result['state']} "
        f"score={result['score']}/10 "
        f"early={result.get('early_score', 0)}/10 "
        f"raw_buy={result.get('raw_buy_gate', False)} "
        f"reconfirmed={result.get('reconfirmed', False)} "
        f"chart={chart_summary.get('stored', False)}"
        f"/{chart_summary.get('bars', 0)}bars"
        f"/{chart_summary.get('source_bar_at', '—')}"
        f"/{chart_summary.get('bar_source', '—')} "
        f"discount={discount['discount_score']}/100 "
        f"{discount['discount_label']} "
        f"fundamental={fundamental.get('fundamental_score')}/100 "
        f"{fundamental.get('fundamental_label')} "
        f"risk={risk_validation.get('gate')}"
        f"/{risk_validation.get('score')} "
        f"market={risk_validation.get('market_regime')} "
        f"liq={risk_validation.get('liquidity_grade')} "
        f"vol={risk_validation.get('volatility_status')} "
        f"atr={risk_validation.get('atr_pct')} "
        f"lots={risk_validation.get('suggested_lots')} "
        f"entry={levels.get('entry_low')}-{levels.get('entry_high')} "
        f"T1={levels.get('target_1')} "
        f"T2={levels.get('target_2')} "
        f"{levels.get('target_mode')}",
        flush=True,
    )

    return result["state"]



def backfill_active_chart_cache():
    """
    Keep chart cache available even when the market is closed.

    Only active HANZ signal rows are considered. A ticker is downloaded only
    when its chart cache is missing or older than the monitor's completed
    daily_bar_at. This makes manual after-hours runs useful without repeatedly
    hammering Yahoo/yfinance every scheduled hour.
    """
    state_filter = ",".join(sorted(CHART_STATES))
    monitor_rows = supabase_request(
        "GET",
        "hanz_swing_signal_monitor"
        f"?state=in.({state_filter})"
        "&select=ticker,state,daily_bar_at"
        "&order=score.desc",
    ) or []

    summary = {
        "active": len(monitor_rows),
        "backfilled": 0,
        "already_current": 0,
        "failed": 0,
    }

    for row in monitor_rows:
        ticker = clean_ticker(row.get("ticker"))
        state = str(row.get("state") or "")
        monitor_bar = str(row.get("daily_bar_at") or "")[:10]
        target_bar = latest_completed_idx_date().isoformat()

        if not ticker or state not in CHART_STATES:
            continue

        try:
            encoded = urllib.parse.quote(ticker, safe="")
            cached = supabase_request(
                "GET",
                "hanz_swing_chart_data"
                f"?ticker=eq.{encoded}"
                "&select=ticker,source_bar_at"
                "&limit=1",
            ) or []

            cached_bar = (
                str(cached[0].get("source_bar_at") or "")[:10]
                if cached else ""
            )

            # Cache is current only when it reaches the latest completed IDX
            # trading date. A stale monitor row must not allow an old chart cache
            # (for example Aug 14 when Aug 18 is completed) to be accepted.
            if cached_bar and cached_bar >= target_bar:
                summary["already_current"] += 1
                continue

            daily_df = download_frame(
                ticker,
                DAILY_INTERVAL,
                DAILY_PERIOD,
            )

            result = {"state": state}
            stored = upsert_chart_data(
                ticker,
                daily_df,
                result,
            )

            if stored.get("stored"):
                summary["backfilled"] += 1

        except Exception as exc:
            summary["failed"] += 1
            print(
                f"SWING CHART BACKFILL {ticker} failed: {exc}",
                flush=True,
            )

    return summary


def run_cycle():
    market = idx_market_session()
    now_wib = jakarta_now()

    previous_day = previous_idx_trading_day(
        now_wib.date()
    )
    next_day = next_idx_trading_day(
        now_wib.date()
    )

    print(
        "IDX MARKET GATE: "
        f"{market['state']} | "
        f"reason={market['reason']} | "
        f"WIB={now_wib.strftime('%Y-%m-%d %H:%M')} | "
        f"previous={previous_day} | "
        f"next={next_day}",
        flush=True,
    )

    # Chart cache maintenance is independent of BUY generation.
    # It is safe to run after hours because it uses completed daily candles
    # and only fills missing/stale chart cache rows.
    try:
        chart_cache_summary = backfill_active_chart_cache()
        print(
            "SWING CHART CACHE: "
            + json.dumps(chart_cache_summary),
            flush=True,
        )
    except Exception as exc:
        print(
            f"SWING CHART CACHE unavailable: {exc}",
            flush=True,
        )

    if not market["is_trading_day"]:
        # CLOSED-MARKET COMPLETED-BAR REFRESH (V8.8)
        # Recalculate the ENTIRE enabled universe from the latest completed
        # candles and refresh monitor states used by the dashboard.  This keeps
        # weekend/holiday Top-5 candidates current.  It still cannot create a
        # new actionable BUY, portfolio trigger, alert, push, or signal row.
        global _REAL_MONEY_CONTEXT
        _REAL_MONEY_CONTEXT = build_real_money_context()

        universe = fetch_universe()
        _MARKET_MOVER_ROWS.clear()

        maintenance_counts = {
            "SWING_BUY_EXISTING": 0,
            "SETUP_READY": 0,
            "PRE_ALERT": 0,
            "EARLY_WATCH": 0,
            "MOMENTUM_BROKEN": 0,
            "NO_SETUP": 0,
            "OTHER": 0,
            "ERROR": 0,
        }

        print(
            f"SWING CLOSED-MARKET REFRESH universe: {len(universe)} | "
            "candidate-refresh=ON | new BUY=BLOCKED | portfolio/alert/push=BLOCKED",
            flush=True,
        )

        for ticker in universe:
            try:
                state = scan_symbol(ticker, maintenance_mode=True)
                if state in BUY_STATES:
                    maintenance_counts["SWING_BUY_EXISTING"] += 1
                elif state in maintenance_counts:
                    maintenance_counts[state] += 1
                else:
                    maintenance_counts["OTHER"] += 1
            except Exception as exc:
                maintenance_counts["ERROR"] += 1
                print(
                    f"SWING MAINTENANCE {ticker} failed: {exc}",
                    flush=True,
                )

        print(
            "SWING CLOSED-MARKET REFRESH complete: "
            + json.dumps(maintenance_counts)
            + " | Monitor refreshed from completed bars; no new BUY signal, portfolio trigger, alert or push.",
            flush=True,
        )
        print(
            f"MARKET MOVERS collected: {len(_MARKET_MOVER_ROWS)}",
            flush=True,
        )
        movers_summary = publish_market_movers()
        print(
            "MARKET MOVERS: " + json.dumps(movers_summary, default=str),
            flush=True,
        )

        return

    # During active sessions / lunch:
    # 1) run INTERNAL predictive radar on the universe;
    # 2) monitor existing portfolio risk.
    # The radar can arm candidates early, but can NEVER create a user-facing BUY.
    # User-facing BUY still waits for post-close completed-bar reconfirmation.
    if not market["allow_final_scan"]:
        if market["allow_portfolio_monitor"]:
            _REAL_MONEY_CONTEXT = build_real_money_context()

            universe = fetch_universe()
            radar_counts = {
                "RADAR_ARMED": 0,
                "RADAR_PRE_ALERT": 0,
                "RADAR_WATCH": 0,
                "NO_SETUP": 0,
                "NO_RADAR": 0,
                "PRESERVE_ACTIVE": 0,
                "ERROR": 0,
            }

            print(
                f"HANZ PREDICTIVE RADAR universe: {len(universe)} | "
                "INTERNAL_ONLY=ON | dashboard=BLOCKED | "
                "new BUY=BLOCKED until completed-bar reconfirmation",
                flush=True,
            )

            for ticker in universe:
                try:
                    radar_state = scan_predictive_radar_symbol(ticker)
                    radar_counts[radar_state] = (
                        radar_counts.get(radar_state, 0) + 1
                    )
                except Exception as exc:
                    radar_counts["ERROR"] += 1
                    print(
                        f"RADAR {ticker} failed: {exc}",
                        flush=True,
                    )

            print(
                "HANZ PREDICTIVE RADAR complete: "
                + json.dumps(radar_counts)
                + " | no signal / alert / push generated",
                flush=True,
            )

            quote_summary = refresh_swing_buy_intraday_prices()
            print(
                "SWING intraday SWING_BUY price refresh complete: "
                + json.dumps(quote_summary)
                + f" | stale_guard={INTRADAY_STALE_MINUTES}m",
                flush=True,
            )

            portfolio_summary = monitor_swing_portfolio(
                allow_structural_exit=False
            )
            print(
                "SWING intraday portfolio monitor complete: "
                + json.dumps(portfolio_summary)
                + " | structural exits=DEFERRED_TO_POST_CLOSE",
                flush=True,
            )
        else:
            print(
                "SWING cycle skipped outside IDX operating window.",
                flush=True,
            )
        return

    _REAL_MONEY_CONTEXT = build_real_money_context()

    print(
        "HANZ REAL-MONEY CONTEXT: "
        + json.dumps(_REAL_MONEY_CONTEXT, default=str),
        flush=True,
    )

    universe = fetch_universe()

    print(
        f"SWING FINAL SCAN universe: {len(universe)}",
        flush=True,
    )

    _MARKET_MOVER_ROWS.clear()

    counts = {
        "SWING_BUY": 0,
        "MOMENTUM_BROKEN": 0,
        "SETUP_READY": 0,
        "PRE_ALERT": 0,
        "EARLY_WATCH": 0,
        "SWING_CONFIRMING": 0,
        "SWING_WATCH": 0,
        "NO_SETUP": 0,
        "ERROR": 0,
    }

    for ticker in universe:
        try:
            state = scan_symbol(ticker)
            counts[state] = (
                counts.get(state, 0) + 1
            )
        except Exception as exc:
            counts["ERROR"] += 1
            print(
                f"SWING {ticker} failed: {exc}",
                flush=True,
            )

    movers_summary = publish_market_movers()
    print(
        "MARKET MOVERS: " + json.dumps(movers_summary, default=str),
        flush=True,
    )

    portfolio_summary = monitor_swing_portfolio(
        allow_structural_exit=True
    )

    print(
        "SWING FINAL cycle complete: "
        + json.dumps(counts)
        + " | portfolio="
        + json.dumps(portfolio_summary),
        flush=True,
    )


def main():
    print(
        "HANZ SWING / WEEKLY ENGINE START — V10.8.3 CANONICAL RANK + MARKET MOVERS + BROKER/INSIDER/FOREIGN FLOW",
        flush=True,
    )

    print(
        f"Daily={DAILY_INTERVAL}/{DAILY_PERIOD} | "
        f"Weekly={WEEKLY_INTERVAL}/{WEEKLY_PERIOD} | "
        f"Cycle={SWING_INTERVAL}s | "
        f"Portfolio monitor=ON | "
        f"IDX calendar gate=ON (Asia/Jakarta) | "
        f"Predictive radar=INTERNAL_INTRADAY | Dashboard=RECONFIRMED_ONLY | "
        f"Reconfirm BUY=NEW COMPLETED DAILY BAR | "
        f"Chart backend=SUPABASE/{CHART_LOOKBACK_BARS} completed bars | "
        f"Real-money guard={'ON' if RISK_LIVE_GATE_ENABLED else 'OFF'} | "
        f"Intraday fallback=ON | "
        f"Risk/trade={RISK_PER_TRADE_PCT:.2f}% | "
        f"Portfolio risk cap={MAX_PORTFOLIO_RISK_PCT:.2f}% | "
        f"Costs={'CONFIGURED' if (BUY_FEE_PCT >= 0 and SELL_FEE_PCT >= 0 and SLIPPAGE_PCT >= 0) else 'PENDING'} | "
        f"Trailing={TRAILING_ATR_MULTIPLIER_T1:.1f}x/"
        f"{TRAILING_ATR_MULTIPLIER_T2:.1f}x ATR | "
        f"Swing volatility=HIGH>={SWING_HIGH_ATR_PCT:.1f}%/"
        f"EXTREME>{SWING_EXTREME_ATR_PCT:.1f}% ATR | "
        f"Market benchmark={normalize_ticker(MARKET_REGIME_TICKER)}",
        flush=True,
    )

    while True:
        try:
            run_cycle()
        except Exception as exc:
            print(
                f"SWING cycle failed: {exc}",
                flush=True,
            )

        if RUN_ONCE:
            break

        print(
            f"SWING engine sleeping "
            f"{SWING_INTERVAL} seconds...",
            flush=True,
        )

        time.sleep(SWING_INTERVAL)


if __name__ == "__main__":
    main()
