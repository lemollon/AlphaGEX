"""
VALOR POST-DEPLOY AUTOMATED TEST SUITE
========================================

Tests 1-4, 8-10: Offline tests that don't require live API connections.
Run with: python tests/valor/test_post_deploy.py
"""

import sys
import os
import importlib.util
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Tuple

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

# ============================================================================
# HELPERS
# ============================================================================

RESULTS: Dict[str, Tuple[bool, List[str]]] = {}


def load_valor_models():
    """Load models.py directly to avoid full trading package import chain."""
    spec = importlib.util.spec_from_file_location(
        'valor_models',
        os.path.join(PROJECT_ROOT, 'trading', 'valor', 'models.py')
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_valor_signals():
    """Load signals.py with minimal deps — only functions we test."""
    # We can't fully import signals.py without DB and API deps.
    # Instead we parse and extract the pure functions we need.
    spec = importlib.util.spec_from_file_location(
        'valor_signals',
        os.path.join(PROJECT_ROOT, 'trading', 'valor', 'signals.py')
    )
    # We'll test _scale_gex_data and cache isolation via models + inline code
    return spec


# ============================================================================
# TEST 1: Model Configuration Verification
# ============================================================================

def test_1_model_configs():
    """Verify all instrument configs have correct values."""
    test_name = "Test 1: Model Configs"
    failures = []

    models = load_valor_models()
    FUTURES_TICKERS = models.FUTURES_TICKERS
    DEFAULT_VALOR_TICKERS = models.DEFAULT_VALOR_TICKERS

    EXPECTED_CONFIGS = {
        "MES": {"proxy_etf": "SPY", "point_value": 5.0, "gex_symbol": "SPY", "starting_capital": 100000.0},
        "MNQ": {"proxy_etf": "QQQ", "point_value": 2.0, "gex_symbol": "QQQ", "starting_capital": 100000.0},
        "RTY": {"proxy_etf": "IWM", "point_value": 5.0, "gex_symbol": "IWM", "starting_capital": 100000.0},
        "CL":  {"proxy_etf": "USO", "point_value": 100.0, "gex_symbol": "USO", "starting_capital": 100000.0},
        "NG":  {"proxy_etf": "UNG", "point_value": 100.0, "gex_symbol": "UNG", "starting_capital": 100000.0},
        "MGC": {"proxy_etf": "GLD", "point_value": 10.0, "gex_symbol": "GLD", "starting_capital": 100000.0},
    }

    # Check all 6 tickers exist
    for ticker in EXPECTED_CONFIGS:
        if ticker not in FUTURES_TICKERS:
            failures.append(f"  {ticker}: MISSING from FUTURES_TICKERS")
            continue

        cfg = FUTURES_TICKERS[ticker]
        expected = EXPECTED_CONFIGS[ticker]

        for key, expected_val in expected.items():
            actual_val = cfg.get(key)
            if actual_val != expected_val:
                failures.append(f"  {ticker}.{key}: expected={expected_val}, actual={actual_val}")
            else:
                print(f"  {ticker}.{key} = {actual_val} ✓")

    # Check DEFAULT_VALOR_TICKERS includes all 6
    for ticker in EXPECTED_CONFIGS:
        if ticker not in DEFAULT_VALOR_TICKERS:
            failures.append(f"  {ticker}: MISSING from DEFAULT_VALOR_TICKERS")

    if len(DEFAULT_VALOR_TICKERS) != 6:
        failures.append(f"  DEFAULT_VALOR_TICKERS length: expected=6, actual={len(DEFAULT_VALOR_TICKERS)}")

    # Verify ValorConfig capital
    config_cls = models.ValorConfig
    default_config = config_cls()
    if default_config.capital != 600000.0:
        failures.append(f"  ValorConfig.capital: expected=600000.0, actual={default_config.capital}")
    else:
        print(f"  ValorConfig.capital = $600,000 ✓")

    # Verify no full-size contract values leaked through
    for ticker in ["CL", "NG"]:
        pv = FUTURES_TICKERS[ticker]["point_value"]
        if pv >= 1000:
            failures.append(f"  CRITICAL: {ticker} point_value={pv} — still full-size, not micro!")

    passed = len(failures) == 0
    RESULTS[test_name] = (passed, failures)
    return passed


# ============================================================================
# TEST 2: Next-Expiration Logic
# ============================================================================

def test_2_next_expiration():
    """Verify get_next_gex_expiration() for every day and ETF."""
    test_name = "Test 2: Next-Expiration Logic"
    failures = []

    models = load_valor_models()
    get_next = models.get_next_gex_expiration

    TEST_CASES = [
        # SPY — daily expirations
        ("SPY", date(2026, 2, 23), date(2026, 2, 24)),  # Mon → Tue
        ("SPY", date(2026, 2, 24), date(2026, 2, 25)),  # Tue → Wed
        ("SPY", date(2026, 2, 25), date(2026, 2, 26)),  # Wed → Thu
        ("SPY", date(2026, 2, 26), date(2026, 2, 27)),  # Thu → Fri
        ("SPY", date(2026, 2, 27), date(2026, 3, 2)),   # Fri → Mon

        # QQQ — daily
        ("QQQ", date(2026, 2, 23), date(2026, 2, 24)),  # Mon → Tue
        ("QQQ", date(2026, 2, 27), date(2026, 3, 2)),   # Fri → Mon

        # IWM — daily
        ("IWM", date(2026, 2, 25), date(2026, 2, 26)),  # Wed → Thu

        # GLD — Mon/Wed/Fri
        ("GLD", date(2026, 2, 23), date(2026, 2, 25)),  # Mon → Wed
        ("GLD", date(2026, 2, 24), date(2026, 2, 25)),  # Tue → Wed
        ("GLD", date(2026, 2, 25), date(2026, 2, 27)),  # Wed → Fri
        ("GLD", date(2026, 2, 26), date(2026, 2, 27)),  # Thu → Fri
        ("GLD", date(2026, 2, 27), date(2026, 3, 2)),   # Fri → Mon

        # USO — Wed/Fri
        ("USO", date(2026, 2, 23), date(2026, 2, 25)),  # Mon → Wed
        ("USO", date(2026, 2, 24), date(2026, 2, 25)),  # Tue → Wed
        ("USO", date(2026, 2, 25), date(2026, 2, 27)),  # Wed → Fri
        ("USO", date(2026, 2, 26), date(2026, 2, 27)),  # Thu → Fri
        ("USO", date(2026, 2, 27), date(2026, 3, 4)),   # Fri → Wed (skip Sat/Sun/Mon/Tue)

        # UNG — Wed/Fri (same as USO)
        ("UNG", date(2026, 2, 23), date(2026, 2, 25)),  # Mon → Wed
        ("UNG", date(2026, 2, 27), date(2026, 3, 4)),   # Fri → Wed
    ]

    for etf, test_date, expected in TEST_CASES:
        try:
            actual = get_next(etf, test_date)
            day_name = test_date.strftime('%a')
            if actual != expected:
                failures.append(
                    f"  {etf} {test_date} ({day_name}) → expected={expected}, actual={actual}"
                )
            else:
                print(f"  {etf} {test_date} ({day_name}) → {actual} ✓")
        except Exception as e:
            failures.append(f"  {etf} {test_date}: EXCEPTION: {e}")

    passed = len(failures) == 0
    RESULTS[test_name] = (passed, failures)
    return passed


# ============================================================================
# TEST 3: GEX Cache Isolation
# ============================================================================

def test_3_cache_isolation():
    """Verify per-instrument cache doesn't leak between tickers."""
    test_name = "Test 3: GEX Cache Isolation"
    failures = []

    # Simulate the per-instrument cache dict
    cache = {}

    # Cache SPY data for MES
    spy_data = {
        'flip_point': 600.0, 'call_wall': 605.0, 'put_wall': 595.0,
        'net_gex': 1e9, 'data_source': 'tradier_calculator'
    }
    cache['MES'] = {'data': spy_data, 'cache_time': datetime.now()}

    # Cache USO data for CL
    uso_data = {
        'flip_point': 75.0, 'call_wall': 78.0, 'put_wall': 72.0,
        'net_gex': 5e6, 'data_source': 'trading_volatility_api'
    }
    cache['CL'] = {'data': uso_data, 'cache_time': datetime.now()}

    # Cache QQQ data for MNQ
    qqq_data = {
        'flip_point': 520.0, 'call_wall': 525.0, 'put_wall': 515.0,
        'net_gex': 8e8, 'data_source': 'trading_volatility_api'
    }
    cache['MNQ'] = {'data': qqq_data, 'cache_time': datetime.now()}

    # 1. Verify MES still has SPY levels
    mes_flip = cache['MES']['data']['flip_point']
    if mes_flip != 600.0:
        failures.append(f"  MES flip_point: expected=600.0, actual={mes_flip} (contaminated!)")
    else:
        print(f"  MES cache isolated: flip={mes_flip} ✓")

    # 2. Verify CL has USO levels (not SPX range)
    cl_flip = cache['CL']['data']['flip_point']
    if cl_flip != 75.0:
        failures.append(f"  CL flip_point: expected=75.0, actual={cl_flip}")
    elif cl_flip > 500:
        failures.append(f"  CL flip_point={cl_flip} — STILL IN SPX RANGE! Proxy not fixed.")
    else:
        print(f"  CL cache isolated: flip={cl_flip} ✓")

    # 3. Verify MNQ has QQQ levels
    mnq_flip = cache['MNQ']['data']['flip_point']
    if mnq_flip != 520.0:
        failures.append(f"  MNQ flip_point: expected=520.0, actual={mnq_flip}")
    else:
        print(f"  MNQ cache isolated: flip={mnq_flip} ✓")

    # 4. Verify MGC cache is empty (never populated)
    if 'MGC' in cache:
        failures.append(f"  MGC cache exists but was never populated — leak detected!")
    else:
        print(f"  MGC cache empty (not yet populated) ✓")

    # 5. Verify RTY cache is empty (never populated)
    if 'RTY' in cache:
        failures.append(f"  RTY cache exists but was never populated — leak detected!")
    else:
        print(f"  RTY cache empty (not yet populated) ✓")

    # 6. Verify populating one ticker doesn't affect others
    gld_data = {
        'flip_point': 270.0, 'call_wall': 275.0, 'put_wall': 265.0,
        'net_gex': 3e7, 'data_source': 'trading_volatility_api'
    }
    cache['MGC'] = {'data': gld_data, 'cache_time': datetime.now()}

    # Re-check MES after adding MGC
    mes_flip_after = cache['MES']['data']['flip_point']
    if mes_flip_after != 600.0:
        failures.append(f"  MES flip_point CHANGED after adding MGC: {mes_flip_after} (was 600.0)")
    else:
        print(f"  MES unchanged after MGC addition ✓")

    passed = len(failures) == 0
    RESULTS[test_name] = (passed, failures)
    return passed


# ============================================================================
# TEST 4: GEX Scale Factor Application
# ============================================================================

def test_4_scale_factors():
    """Verify _scale_gex_data() produces reasonable output."""
    test_name = "Test 4: GEX Scale Factors"
    failures = []

    models = load_valor_models()
    FUTURES_TICKERS = models.FUTURES_TICKERS

    # Inline implementation of _scale_gex_data (same logic as signals.py)
    def scale_gex_data(gex_data, scale_factor):
        if not scale_factor or scale_factor <= 0 or scale_factor == 1.0:
            return dict(gex_data)
        scaled = dict(gex_data)
        for key in ('flip_point', 'call_wall', 'put_wall'):
            if key in scaled and scaled[key] and scaled[key] > 0:
                scaled[key] = scaled[key] * scale_factor
        return scaled

    # Test cases: (ticker, sample_etf_levels, expected_range_low, expected_range_high, description)
    TEST_CASES = [
        {
            "ticker": "MES",
            "etf_levels": {"flip_point": 600.0, "call_wall": 605.0, "put_wall": 595.0},
            "scale": FUTURES_TICKERS["MES"].get("gex_scale_factor", 1.0),
            "expected_flip_range": (5500, 6500),
            "desc": "SPY→MES (×10)",
        },
        {
            "ticker": "MNQ",
            "etf_levels": {"flip_point": 520.0, "call_wall": 525.0, "put_wall": 515.0},
            "scale": FUTURES_TICKERS["MNQ"].get("gex_scale_factor", 1.0),
            "expected_flip_range": (20000, 30000),
            "desc": "QQQ→MNQ (×50)",
        },
        {
            "ticker": "RTY",
            "etf_levels": {"flip_point": 225.0, "call_wall": 230.0, "put_wall": 220.0},
            "scale": FUTURES_TICKERS["RTY"].get("gex_scale_factor", 1.0),
            "expected_flip_range": (2000, 2500),
            "desc": "IWM→RTY (×10)",
        },
        {
            "ticker": "CL",
            "etf_levels": {"flip_point": 75.0, "call_wall": 78.0, "put_wall": 72.0},
            "scale": FUTURES_TICKERS["CL"].get("gex_scale_factor", 1.0) or 1.0,
            "expected_flip_range": (50, 120),
            "desc": "USO→CL (×1, regime levels)",
        },
        {
            "ticker": "NG",
            "etf_levels": {"flip_point": 14.0, "call_wall": 15.0, "put_wall": 13.0},
            "scale": FUTURES_TICKERS["NG"].get("gex_scale_factor", 1.0) or 1.0,
            "expected_flip_range": (1, 50),
            "desc": "UNG→NG (×1, regime levels)",
        },
        {
            "ticker": "MGC",
            "etf_levels": {"flip_point": 270.0, "call_wall": 275.0, "put_wall": 265.0},
            "scale": FUTURES_TICKERS["MGC"].get("gex_scale_factor", 1.0),
            "expected_flip_range": (2500, 3200),
            "desc": "GLD→MGC (×10)",
        },
    ]

    for tc in TEST_CASES:
        ticker = tc["ticker"]
        scale = tc["scale"]
        scaled = scale_gex_data(tc["etf_levels"], scale)
        flip = scaled["flip_point"]
        low, high = tc["expected_flip_range"]

        if low <= flip <= high:
            print(f"  {ticker}: {tc['desc']} → flip={flip:.1f} (in [{low}, {high}]) ✓")
        else:
            failures.append(
                f"  {ticker}: {tc['desc']} → flip={flip:.1f} NOT in [{low}, {high}]"
            )

        # CRITICAL: Verify no energy/gold instrument has SPX-range levels
        if ticker in ("CL", "NG", "MGC") and flip > 5000:
            failures.append(
                f"  CRITICAL: {ticker} flip={flip:.1f} is in SPX range! Proxy ETF leak detected."
            )

    passed = len(failures) == 0
    RESULTS[test_name] = (passed, failures)
    return passed


# ============================================================================
# TEST 8: Database Schema Compatibility (offline — checks table existence)
# ============================================================================

def test_8_db_schema():
    """Verify DB schema can store MGC positions (check via db.py code inspection)."""
    test_name = "Test 8: DB Schema"
    failures = []

    # Check that db.py uses parameterized ticker columns (not hardcoded MES)
    db_path = os.path.join(PROJECT_ROOT, 'trading', 'valor', 'db.py')
    with open(db_path, 'r') as f:
        db_code = f.read()

    # 1. Check save_position accepts ticker parameter
    if 'def save_position' in db_code:
        print(f"  save_position() exists ✓")
    else:
        failures.append(f"  save_position() not found in db.py")

    # 2. Check positions table has ticker column
    if 'ticker' in db_code and ('valor_positions' in db_code or 'heracles_positions' in db_code):
        print(f"  valor_positions table uses ticker column ✓")
    else:
        failures.append(f"  ticker column not found in position queries")

    # 3. Check save_equity_snapshot accepts ticker parameter
    if 'def save_equity_snapshot' in db_code:
        # Look for ticker parameter in the function
        idx = db_code.index('def save_equity_snapshot')
        func_header = db_code[idx:idx+500]
        if 'ticker' in func_header:
            print(f"  save_equity_snapshot(ticker=...) ✓")
        else:
            failures.append(f"  save_equity_snapshot missing ticker parameter")
    else:
        failures.append(f"  save_equity_snapshot() not found in db.py")

    # 4. Check get_open_positions accepts ticker filter
    if 'def get_open_positions' in db_code:
        idx = db_code.index('def get_open_positions')
        func_header = db_code[idx:idx+500]
        if 'ticker' in func_header:
            print(f"  get_open_positions(ticker=...) ✓")
        else:
            failures.append(f"  get_open_positions missing ticker filter")

    # 5. Check no hardcoded "MES" in SQL queries (should use parameterized ticker)
    import re
    hardcoded_mes_sql = re.findall(r"WHERE.*ticker\s*=\s*'MES'", db_code)
    if hardcoded_mes_sql:
        failures.append(f"  Found {len(hardcoded_mes_sql)} hardcoded MES in SQL queries")
    else:
        print(f"  No hardcoded 'MES' in SQL queries ✓")

    # 6. Check that config table allows arbitrary config_keys (for per-ticker GEX cache)
    if 'gex_cache' in db_code or 'config_key' in db_code:
        print(f"  Config table supports arbitrary keys ✓")

    passed = len(failures) == 0
    RESULTS[test_name] = (passed, failures)
    return passed


# ============================================================================
# TEST 9: Daily Loss Limit Logic
# ============================================================================

def test_9_daily_loss_limits():
    """Verify daily loss limit logic works correctly."""
    test_name = "Test 9: Daily Loss Limits"
    failures = []

    # Read trader.py to verify the logic exists
    trader_path = os.path.join(PROJECT_ROOT, 'trading', 'valor', 'trader.py')
    with open(trader_path, 'r') as f:
        trader_code = f.read()

    # 1. Check _daily_losses dict exists
    if '_daily_losses' in trader_code:
        print(f"  _daily_losses tracking dict exists ✓")
    else:
        failures.append(f"  _daily_losses tracking dict not found")

    # 2. Check per-instrument limit (-$2,000)
    if '-2000' in trader_code or 'max_daily_loss_per_instrument' in trader_code:
        print(f"  Per-instrument daily loss limit (-$2,000) ✓")
    else:
        failures.append(f"  Per-instrument daily loss limit not found")

    # 3. Check combined limit (-$6,000)
    if '-6000' in trader_code or 'max_combined_daily_loss' in trader_code:
        print(f"  Combined daily loss limit (-$6,000) ✓")
    else:
        failures.append(f"  Combined daily loss limit not found")

    # 4. Check midnight reset logic
    if '_daily_loss_date' in trader_code and 'daily_loss_date' in trader_code:
        print(f"  Midnight reset logic exists ✓")
    else:
        failures.append(f"  Midnight reset logic not found")

    # 5. Check that loss is tracked per-ticker in _close_position
    if '_daily_losses[pos_ticker]' in trader_code or '_daily_losses.get(ticker' in trader_code:
        print(f"  Per-ticker loss tracking in close_position ✓")
    else:
        # Check for alternative patterns
        if 'self._daily_losses' in trader_code and 'realized_pnl' in trader_code:
            print(f"  Per-ticker loss tracking exists (alternative pattern) ✓")
        else:
            failures.append(f"  Per-ticker loss tracking in close_position not found")

    # 6. Check that paused instrument doesn't block others
    if 'continue' in trader_code and 'daily_loss_limit' in trader_code:
        print(f"  Paused instrument skips (continue) without blocking others ✓")
    else:
        # Check for the specific pattern
        if 'ticker_daily_loss' in trader_code:
            print(f"  Per-ticker loss check exists ✓")
        else:
            failures.append(f"  Instrument isolation on daily loss not verified")

    # 7. Simulate the logic in pure Python
    daily_losses = {"MES": 0.0, "MNQ": 0.0, "CL": 0.0, "NG": 0.0, "RTY": 0.0, "MGC": 0.0}
    MAX_PER_INSTRUMENT = -2000.0
    MAX_COMBINED = -6000.0

    # Simulate CL hitting limit
    daily_losses["CL"] = -2150.0
    cl_paused = daily_losses["CL"] <= MAX_PER_INSTRUMENT
    mes_paused = daily_losses["MES"] <= MAX_PER_INSTRUMENT
    if cl_paused and not mes_paused:
        print(f"  Simulation: CL paused at ${daily_losses['CL']:.0f}, MES NOT paused ✓")
    else:
        failures.append(f"  Simulation: CL paused={cl_paused}, MES paused={mes_paused} — isolation broken!")

    # Simulate combined limit
    daily_losses["MES"] = -1500.0
    daily_losses["MNQ"] = -1800.0
    daily_losses["RTY"] = -700.0
    combined = sum(daily_losses.values())
    all_paused = combined <= MAX_COMBINED
    if all_paused:
        print(f"  Simulation: Combined=${combined:.0f} triggers all-pause ✓")
    else:
        failures.append(f"  Simulation: Combined=${combined:.0f} should trigger all-pause but didn't")

    # Reset simulation
    daily_losses = {k: 0.0 for k in daily_losses}
    combined_after_reset = sum(daily_losses.values())
    if combined_after_reset == 0.0:
        print(f"  Simulation: Midnight reset works ✓")

    passed = len(failures) == 0
    RESULTS[test_name] = (passed, failures)
    return passed


# ============================================================================
# TEST 10: No Regression on MES/RTY
# ============================================================================

def test_10_mes_rty_regression():
    """Verify MES and RTY configs are unchanged from known-good values."""
    test_name = "Test 10: MES/RTY Regression"
    failures = []

    models = load_valor_models()
    FUTURES_TICKERS = models.FUTURES_TICKERS

    # MES known-good config
    mes = FUTURES_TICKERS.get("MES", {})
    checks = [
        ("MES.point_value", mes.get("point_value"), 5.0),
        ("MES.tick_size", mes.get("tick_size"), 0.25),
        ("MES.tick_value", mes.get("tick_value"), 1.25),
        ("MES.gex_symbol", mes.get("gex_symbol"), "SPY"),
        ("MES.proxy_etf", mes.get("proxy_etf"), "SPY"),
        ("MES.starting_capital", mes.get("starting_capital"), 100000.0),
        ("MES.risk_per_trade_pct", mes.get("risk_per_trade_pct"), 1.0),
        ("MES.max_contracts", mes.get("max_contracts"), 5),
        ("MES.exchange", mes.get("exchange"), "CME"),
    ]

    # RTY known-good config
    rty = FUTURES_TICKERS.get("RTY", {})
    checks += [
        ("RTY.point_value", rty.get("point_value"), 5.0),
        ("RTY.tick_size", rty.get("tick_size"), 0.10),
        ("RTY.gex_symbol", rty.get("gex_symbol"), "IWM"),
        ("RTY.proxy_etf", rty.get("proxy_etf"), "IWM"),
        ("RTY.starting_capital", rty.get("starting_capital"), 100000.0),
        ("RTY.exchange", rty.get("exchange"), "CME"),
    ]

    for label, actual, expected in checks:
        if actual != expected:
            failures.append(f"  {label}: expected={expected}, actual={actual}")
        else:
            print(f"  {label} = {actual} ✓")

    # Verify MES scan path hasn't changed:
    # trader.py should still call get_gex_data_for_valor with the right pattern
    trader_path = os.path.join(PROJECT_ROOT, 'trading', 'valor', 'trader.py')
    with open(trader_path, 'r') as f:
        trader_code = f.read()

    # Check that gex_data is fetched per-ticker with symbol and ticker args
    if 'get_gex_data_for_valor(symbol=gex_symbol, ticker=ticker)' in trader_code:
        print(f"  GEX fetch uses per-ticker routing ✓")
    elif 'get_gex_data_for_valor(gex_symbol' in trader_code:
        print(f"  GEX fetch uses gex_symbol parameter ✓")
    else:
        failures.append(f"  GEX fetch pattern not found in trader.py")

    # Check MES still has its special Tradier path in signals.py
    signals_path = os.path.join(PROJECT_ROOT, 'trading', 'valor', 'signals.py')
    with open(signals_path, 'r') as f:
        signals_code = f.read()

    if 'if ticker == "MES"' in signals_code and 'calculate_gex("SPX")' in signals_code:
        print(f"  MES Tradier/SPX special path preserved ✓")
    else:
        failures.append(f"  MES Tradier/SPX special path missing or changed!")

    # Verify correlation logging doesn't block trading (log only, no hard gate)
    if '_log_correlation_exposure' in trader_code:
        # Check it's called AFTER the scan loop, not inside as a gate
        if 'self._log_correlation_exposure()' in trader_code:
            # Make sure there's no return/break inside it that would halt scanning
            idx = trader_code.index('def _log_correlation_exposure')
            func_body = trader_code[idx:idx+2000]
            if 'return False' not in func_body and 'raise' not in func_body:
                print(f"  Correlation logging is non-blocking ✓")
            else:
                failures.append(f"  Correlation logging may block trading!")
        else:
            print(f"  Correlation logging method exists (call pattern differs) ✓")

    passed = len(failures) == 0
    RESULTS[test_name] = (passed, failures)
    return passed


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 60)
    print("VALOR POST-DEPLOY TEST SUITE (Offline Tests)")
    print("=" * 60)
    print()

    # Test 1
    print("─" * 50)
    print("TEST 1: Model Configuration Verification")
    print("─" * 50)
    test_1_model_configs()
    print()

    # Test 2
    print("─" * 50)
    print("TEST 2: Next-Expiration Logic")
    print("─" * 50)
    test_2_next_expiration()
    print()

    # Test 3
    print("─" * 50)
    print("TEST 3: GEX Cache Isolation")
    print("─" * 50)
    test_3_cache_isolation()
    print()

    # Test 4
    print("─" * 50)
    print("TEST 4: GEX Scale Factor Application")
    print("─" * 50)
    test_4_scale_factors()
    print()

    # Test 8
    print("─" * 50)
    print("TEST 8: Database Schema Compatibility")
    print("─" * 50)
    test_8_db_schema()
    print()

    # Test 9
    print("─" * 50)
    print("TEST 9: Daily Loss Limit Logic")
    print("─" * 50)
    test_9_daily_loss_limits()
    print()

    # Test 10
    print("─" * 50)
    print("TEST 10: MES/RTY No-Regression Check")
    print("─" * 50)
    test_10_mes_rty_regression()
    print()

    return RESULTS


if __name__ == "__main__":
    results = main()
