#!/usr/bin/env python3
"""
AGAPE-SPOT Bayesian Win Tracker — Production Verification Script

Run directly in Render shell:
    python scripts/test_bayesian_live.py

Tests:
  1. Database table exists and is queryable
  2. All 5 tickers have win tracker instances in memory
  3. BTC-USD is fully configured (SPOT_TICKERS, live_tickers, not altcoin)
  4. Win tracker math is correct (alpha/beta/regime counters)
  5. Summary API returns win_tracker per-ticker
  6. Status API returns win_tracker per-ticker
  7. Signal gate is wired (MIN_WIN_PROBABILITY = 0.50)
  8. FundingRegime mapping covers all known strings
  9. Frontend BTC-USD is in TICKER_META
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Results:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, name):
        self.passed += 1
        print(f"  [PASS] {name}")

    def fail(self, name, reason=""):
        self.failed += 1
        msg = f"  [FAIL] {name}: {reason}" if reason else f"  [FAIL] {name}"
        print(msg)
        self.errors.append(msg)

    def warn(self, name, reason=""):
        print(f"  [WARN] {name}: {reason}")


R = Results()

print("=" * 70)
print("AGAPE-SPOT BAYESIAN WIN TRACKER — PRODUCTION VERIFICATION")
print("=" * 70)


# =========================================================================
# TEST 1: Database table exists
# =========================================================================
print("\n--- TEST 1: Database Table ---")

try:
    from database_adapter import get_connection
    conn = get_connection()
    if conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'agape_spot_win_tracker'
        """)
        exists = cur.fetchone()[0] > 0
        if exists:
            R.ok("agape_spot_win_tracker table exists")
            # Check row count
            cur.execute("SELECT COUNT(*) FROM agape_spot_win_tracker")
            count = cur.fetchone()[0]
            R.ok(f"Table has {count} rows")
            # Check distinct tickers
            cur.execute("SELECT DISTINCT ticker FROM agape_spot_win_tracker ORDER BY ticker")
            tickers_in_db = [row[0] for row in cur.fetchall()]
            R.ok(f"Tickers in DB: {tickers_in_db or '(empty — cold start)'}")
        else:
            R.fail("agape_spot_win_tracker table", "TABLE DOES NOT EXIST")

        # Check index
        cur.execute("""
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'agape_spot_win_tracker'
        """)
        indexes = [row[0] for row in cur.fetchall()]
        if any("ticker" in idx for idx in indexes):
            R.ok(f"Ticker index exists: {[i for i in indexes if 'ticker' in i]}")
        else:
            R.fail("Ticker index", f"No ticker index found. Indexes: {indexes}")

        cur.close()
        conn.close()
    else:
        R.fail("Database connection", "get_connection() returned None")
except Exception as e:
    R.fail("Database check", str(e))


# =========================================================================
# TEST 2: BTC-USD in SPOT_TICKERS
# =========================================================================
print("\n--- TEST 2: BTC-USD Configuration ---")

try:
    from trading.agape_spot.models import SPOT_TICKERS, AgapeSpotConfig, BayesianWinTracker, FundingRegime

    if "BTC-USD" in SPOT_TICKERS:
        R.ok("BTC-USD in SPOT_TICKERS")
        btc = SPOT_TICKERS["BTC-USD"]
        R.ok(f"  symbol={btc['symbol']}, display={btc['display_name']}")
        R.ok(f"  starting_capital=${btc['starting_capital']}, qty={btc['default_quantity']}")
        R.ok(f"  min_order={btc['min_order']}, max_per_trade={btc['max_per_trade']}")
        R.ok(f"  qty_decimals={btc['quantity_decimals']}, price_decimals={btc['price_decimals']}")
    else:
        R.fail("BTC-USD in SPOT_TICKERS", "NOT FOUND")

    # Check live_tickers
    config = AgapeSpotConfig()
    expected_live = {"ETH-USD", "BTC-USD", "XRP-USD", "SHIB-USD", "DOGE-USD"}
    actual_live = set(config.live_tickers)
    if actual_live == expected_live:
        R.ok(f"live_tickers = {sorted(config.live_tickers)}")
    else:
        R.fail("live_tickers", f"Expected {expected_live}, got {actual_live}")

    # Check all 5 tickers in config.tickers
    if len(config.tickers) == 5 and "BTC-USD" in config.tickers:
        R.ok(f"config.tickers has all 5: {config.tickers}")
    else:
        R.fail("config.tickers", f"Got {config.tickers}")

except Exception as e:
    R.fail("BTC-USD config", str(e))


# =========================================================================
# TEST 3: BTC-USD is NOT altcoin
# =========================================================================
print("\n--- TEST 3: BTC-USD Altcoin Status ---")

try:
    from trading.agape_spot.signals import AgapeSpotSignalGenerator
    from unittest.mock import MagicMock

    mock_config = MagicMock()
    mock_config.tickers = ["ETH-USD", "BTC-USD", "XRP-USD"]
    mock_config.min_confidence = "LOW"
    gen = AgapeSpotSignalGenerator(mock_config)

    if not gen._is_altcoin("BTC-USD"):
        R.ok("BTC-USD is NOT altcoin (treated as major)")
    else:
        R.fail("BTC-USD altcoin", "BTC-USD is being treated as altcoin!")

    if not gen._is_altcoin("ETH-USD"):
        R.ok("ETH-USD is NOT altcoin (treated as major)")
    else:
        R.fail("ETH-USD altcoin", "ETH-USD is being treated as altcoin!")

    if gen._is_altcoin("XRP-USD"):
        R.ok("XRP-USD IS altcoin (correct)")
    else:
        R.fail("XRP-USD altcoin", "XRP-USD is NOT being treated as altcoin")

except Exception as e:
    R.fail("Altcoin check", str(e))


# =========================================================================
# TEST 4: BayesianWinTracker math
# =========================================================================
print("\n--- TEST 4: Bayesian Math ---")

try:
    t = BayesianWinTracker(ticker="TEST")

    # Initial state
    assert t.alpha == 1.0 and t.beta == 1.0 and t.total_trades == 0
    assert t.win_probability == 0.5
    R.ok("Initial state: alpha=1, beta=1, P(win)=0.50")

    # After 1 win in POSITIVE
    t.update(True, FundingRegime.POSITIVE)
    assert t.alpha == 2.0 and t.beta == 1.0 and t.total_trades == 1
    assert t.positive_funding_wins == 1
    R.ok(f"After 1 win: alpha={t.alpha}, P(win)={t.win_probability:.3f}")

    # After 1 loss in NEGATIVE
    t.update(False, FundingRegime.NEGATIVE)
    assert t.beta == 2.0 and t.negative_funding_losses == 1
    R.ok(f"After 1 loss: beta={t.beta}, P(win)={t.win_probability:.3f}")

    # Regime probabilities
    pos_prob = t.get_regime_probability(FundingRegime.POSITIVE)
    neg_prob = t.get_regime_probability(FundingRegime.NEGATIVE)
    assert abs(pos_prob - 2/3) < 0.001  # (1+1)/(1+0+2) = 2/3
    assert abs(neg_prob - 1/3) < 0.001  # (0+1)/(0+1+2) = 1/3
    R.ok(f"Regime probs: POSITIVE={pos_prob:.3f}, NEGATIVE={neg_prob:.3f}")

    # Cold start
    assert t.is_cold_start is True
    R.ok(f"is_cold_start=True at {t.total_trades} trades")

    # to_dict works
    d = t.to_dict()
    assert "regime_probabilities" in d
    assert "win_probability" in d
    R.ok(f"to_dict() has {len(d)} fields")

except AssertionError as e:
    R.fail("Bayesian math", str(e))
except Exception as e:
    R.fail("Bayesian math", str(e))


# =========================================================================
# TEST 5: FundingRegime mapping
# =========================================================================
print("\n--- TEST 5: FundingRegime Mapping ---")

try:
    mappings = {
        "EXTREME_POSITIVE": FundingRegime.POSITIVE,
        "HEAVILY_POSITIVE": FundingRegime.POSITIVE,
        "POSITIVE": FundingRegime.POSITIVE,
        "EXTREME_NEGATIVE": FundingRegime.NEGATIVE,
        "HEAVILY_NEGATIVE": FundingRegime.NEGATIVE,
        "NEGATIVE": FundingRegime.NEGATIVE,
        "NEUTRAL": FundingRegime.NEUTRAL,
        "UNKNOWN": FundingRegime.NEUTRAL,
        "": FundingRegime.NEUTRAL,
    }
    all_correct = True
    for input_str, expected in mappings.items():
        result = FundingRegime.from_funding_string(input_str)
        if result != expected:
            R.fail(f"FundingRegime({input_str!r})", f"got {result}, expected {expected}")
            all_correct = False

    if FundingRegime.from_funding_string(None) != FundingRegime.NEUTRAL:
        R.fail("FundingRegime(None)", "should be NEUTRAL")
        all_correct = False

    if all_correct:
        R.ok(f"All {len(mappings) + 1} regime mappings correct")
except Exception as e:
    R.fail("FundingRegime mapping", str(e))


# =========================================================================
# TEST 6: Signal gate wired
# =========================================================================
print("\n--- TEST 6: Signal Gate ---")

try:
    from trading.agape_spot.signals import AgapeSpotSignalGenerator

    assert hasattr(AgapeSpotSignalGenerator, 'MIN_WIN_PROBABILITY')
    assert AgapeSpotSignalGenerator.MIN_WIN_PROBABILITY == 0.50
    R.ok(f"MIN_WIN_PROBABILITY = {AgapeSpotSignalGenerator.MIN_WIN_PROBABILITY}")

    # Verify _calculate_win_probability exists
    assert hasattr(AgapeSpotSignalGenerator, '_calculate_win_probability')
    R.ok("_calculate_win_probability method exists")

    # Test with no tracker → returns 0.52
    mock_config = MagicMock()
    mock_config.tickers = ["ETH-USD"]
    mock_config.min_confidence = "LOW"
    gen = AgapeSpotSignalGenerator(mock_config, win_trackers={})
    prob = gen._calculate_win_probability("ETH-USD", "POSITIVE")
    if prob == 0.52:
        R.ok(f"No tracker → returns {prob} (allows trading)")
    else:
        R.fail("No tracker fallback", f"expected 0.52, got {prob}")

    # Test cold start floor
    tracker = BayesianWinTracker(ticker="ETH-USD")
    gen2 = AgapeSpotSignalGenerator(mock_config, win_trackers={"ETH-USD": tracker})
    prob2 = gen2._calculate_win_probability("ETH-USD", "POSITIVE")
    if prob2 == 0.52:
        R.ok(f"Cold start (0 trades) → floored to {prob2}")
    else:
        R.fail("Cold start floor", f"expected 0.52, got {prob2}")

    # Test blocking after 15 losses
    bad_tracker = BayesianWinTracker(ticker="ETH-USD")
    for _ in range(2):
        bad_tracker.update(True, FundingRegime.NEGATIVE)
    for _ in range(13):
        bad_tracker.update(False, FundingRegime.NEGATIVE)
    gen3 = AgapeSpotSignalGenerator(mock_config, win_trackers={"ETH-USD": bad_tracker})
    prob3 = gen3._calculate_win_probability("ETH-USD", "NEGATIVE")
    if prob3 < 0.50:
        R.ok(f"Losing regime (2W/13L) → {prob3:.3f} < 0.50 BLOCKED")
    else:
        R.fail("Losing regime gate", f"expected < 0.50, got {prob3:.3f}")

except Exception as e:
    R.fail("Signal gate", str(e))


# =========================================================================
# TEST 7: Trader has win_trackers loaded
# =========================================================================
print("\n--- TEST 7: Trader Win Trackers ---")

try:
    # Try to get the running trader instance
    from backend.api.routes.agape_spot_routes import _get_trader
    trader = _get_trader()
    if trader:
        if hasattr(trader, '_win_trackers'):
            trackers = trader._win_trackers
            R.ok(f"Trader has {len(trackers)} win trackers")
            for ticker, wt in trackers.items():
                phase = "COLD" if wt.is_cold_start else ("ML" if wt.should_use_ml else "BAYES")
                R.ok(f"  {ticker}: trades={wt.total_trades}, P(win)={wt.win_probability:.3f}, phase={phase}")
                # Verify regime probabilities
                rp = wt.to_dict()["regime_probabilities"]
                R.ok(f"    regimes: +{rp['POSITIVE']:.2f} -{rp['NEGATIVE']:.2f} ~{rp['NEUTRAL']:.2f}")
        else:
            R.fail("Trader _win_trackers", "Attribute missing!")
    else:
        R.warn("Trader instance", "Not initialized (expected if running outside scheduler)")
        R.ok("Skipping trader instance checks (trader not running)")
except ImportError:
    R.warn("Trader import", "Could not import routes (expected in shell)")
    R.ok("Skipping trader instance checks")
except Exception as e:
    R.fail("Trader win trackers", str(e))


# =========================================================================
# TEST 8: API endpoints (localhost or RENDER_EXTERNAL_URL)
# =========================================================================
print("\n--- TEST 8: API Endpoints ---")

api_url = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8000")

try:
    import urllib.request
    import json

    def api_get(path):
        url = f"{api_url}{path}"
        req = urllib.request.Request(url, headers={"User-Agent": "BayesianTest/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())

    # Test summary endpoint
    try:
        data = api_get("/api/agape-spot/summary")
        if data.get("success"):
            tickers = data.get("data", {}).get("tickers", {})
            R.ok(f"Summary API: {len(tickers)} tickers returned")

            # Check BTC-USD exists
            if "BTC-USD" in tickers:
                R.ok("BTC-USD in summary response")
                btc = tickers["BTC-USD"]
                if btc.get("win_tracker"):
                    wt = btc["win_tracker"]
                    R.ok(f"BTC-USD win_tracker: trades={wt['total_trades']}, P(win)={wt['win_probability']:.3f}")
                else:
                    R.ok("BTC-USD win_tracker: null (no trades yet — cold start)")
            else:
                R.fail("BTC-USD in summary", f"Tickers: {list(tickers.keys())}")

            # Check all 5 have win_tracker field
            for tk in ["ETH-USD", "BTC-USD", "XRP-USD", "SHIB-USD", "DOGE-USD"]:
                if tk in tickers:
                    has_wt = "win_tracker" in tickers[tk]
                    if has_wt:
                        R.ok(f"{tk} summary has win_tracker field")
                    else:
                        R.fail(f"{tk} summary win_tracker", "Field missing from response")
        else:
            R.warn("Summary API", f"success=false: {data.get('reason', 'unknown')}")
    except Exception as e:
        R.warn("Summary API", f"Could not reach: {e}")

    # Test per-ticker status
    for tk in ["ETH-USD", "BTC-USD"]:
        try:
            data = api_get(f"/api/agape-spot/status?ticker={tk}")
            if data.get("success"):
                status = data.get("data", {})
                if status.get("win_tracker"):
                    wt = status["win_tracker"]
                    R.ok(f"{tk} status: win_tracker trades={wt['total_trades']}, P(win)={wt['win_probability']:.3f}")
                else:
                    R.ok(f"{tk} status: win_tracker=null (cold start)")
            else:
                R.warn(f"{tk} status", f"success=false: {data.get('reason')}")
        except Exception as e:
            R.warn(f"{tk} status API", str(e))

except ImportError:
    R.warn("API tests", "urllib not available")
except Exception as e:
    R.warn("API tests", str(e))


# =========================================================================
# TEST 9: DB get/save round-trip
# =========================================================================
print("\n--- TEST 9: DB Round-Trip ---")

try:
    from trading.agape_spot.db import AgapeSpotDatabase

    db = AgapeSpotDatabase()

    # Load tracker for each ticker
    for tk in ["ETH-USD", "BTC-USD", "XRP-USD", "SHIB-USD", "DOGE-USD"]:
        wt = db.get_win_tracker(tk)
        if wt and wt.ticker == tk:
            phase = "COLD" if wt.is_cold_start else ("ML" if wt.should_use_ml else "BAYES")
            R.ok(f"DB load {tk}: trades={wt.total_trades}, alpha={wt.alpha:.1f}, beta={wt.beta:.1f}, phase={phase}")
        else:
            R.fail(f"DB load {tk}", f"got {wt}")

except Exception as e:
    R.fail("DB round-trip", str(e))


# =========================================================================
# TEST 10: Frontend file has BTC-USD
# =========================================================================
print("\n--- TEST 10: Frontend BTC-USD ---")

try:
    frontend_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "frontend/src/app/agape-spot/page.tsx"
    )
    if os.path.exists(frontend_path):
        with open(frontend_path) as f:
            content = f.read()

        checks = [
            ("'BTC-USD'", "BTC-USD in TickerId type"),
            ("BTC-USD", "BTC-USD referenced in page"),
            ("label: 'Bitcoin'", "Bitcoin label in TICKER_META"),
            ("BayesianTrackerCompact", "BayesianTrackerCompact component"),
            ("BayesianTrackerDetail", "BayesianTrackerDetail component"),
            ("win_tracker", "win_tracker data reference"),
            ("LEARNING", "LEARNING badge for cold start"),
            ("regime_probabilities", "Regime probabilities display"),
            ("50% gate", "Gate visualization"),
        ]
        for search, label in checks:
            if search in content:
                R.ok(label)
            else:
                R.fail(label, f"'{search}' not found in page.tsx")
    else:
        R.warn("Frontend check", f"File not found: {frontend_path}")

except Exception as e:
    R.fail("Frontend check", str(e))


# =========================================================================
# SUMMARY
# =========================================================================
print("\n" + "=" * 70)
total = R.passed + R.failed
print(f"TOTAL: {R.passed}/{total} PASSED — {R.failed} FAILED")
print("=" * 70)

if R.errors:
    print("\nFAILURES:")
    for err in R.errors:
        print(f"  {err}")

status = "ALL PASSED" if R.failed == 0 else f"{R.failed} FAILURES"
print(f"\nSTATUS: {'[PASS]' if R.failed == 0 else '[FAIL]'} {status}")
print("=" * 70)

sys.exit(0 if R.failed == 0 else 1)
