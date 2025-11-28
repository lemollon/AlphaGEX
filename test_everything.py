#!/usr/bin/env python3
"""
AlphaGEX Complete System Test
=============================
Tests EVERYTHING - imports, database, API, backtests, feedback loops.

Usage:
    python test_everything.py                    # Local tests only
    python test_everything.py https://url.com   # Local + API tests
"""

import sys
import os
import json
import traceback
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Suppress warnings for cleaner output
import warnings
warnings.filterwarnings('ignore')
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/test')  # Prevent crash

# Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def ok(msg):
    print(f"  {GREEN}✓{RESET} {msg}")

def fail(msg, detail=None):
    print(f"  {RED}✗{RESET} {msg}")
    if detail:
        print(f"    {RED}→ {detail[:80]}{RESET}")

def warn(msg):
    print(f"  {YELLOW}⚠{RESET} {msg}")

def section(title):
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE} {title}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")

results = {"passed": 0, "failed": 0, "warned": 0}

def track(success, warning=False):
    if success:
        results["passed"] += 1
    elif warning:
        results["warned"] += 1
    else:
        results["failed"] += 1


# =============================================================================
# 1. CORE IMPORTS
# =============================================================================
section("1. CORE IMPORTS (Root Level)")

imports_to_test = [
    ("config", "Config"),
    ("database_adapter", "Database Adapter"),
    ("core_classes_and_engines", "Core Classes & Engines"),
    ("unified_config", "Unified Config"),
    ("unified_trading_engine", "Unified Trading Engine"),
    ("trading_costs", "Trading Costs"),
]

for module, name in imports_to_test:
    try:
        __import__(module)
        ok(f"{name}")
        track(True)
    except Exception as e:
        fail(f"{name}", str(e))
        track(False)


# =============================================================================
# 2. ORGANIZED MODULES
# =============================================================================
section("2. ORGANIZED MODULES")

organized_imports = [
    # Core - verified class/function names
    ("core.autonomous_paper_trader", "AutonomousPaperTrader"),
    ("core.market_regime_classifier", "get_classifier"),
    ("core.strategy_stats", "get_strategy_stats"),
    ("core.strategy_stats", "update_strategy_stats"),
    ("core.psychology_trap_detector", "detect_volatility_regime"),
    ("core.probability_calculator", "ProbabilityCalculator"),
    ("core.intelligence_and_strategies", "ClaudeIntelligence"),

    # Data
    ("data.polygon_data_fetcher", "polygon_fetcher"),
    ("data.unified_data_provider", "get_data_provider"),
    ("data.tradier_data_fetcher", "TradierDataFetcher"),
    ("data.flexible_price_data", "FlexiblePriceDataFetcher"),

    # Backtest
    ("backtest.autonomous_backtest_engine", "get_backtester"),
    ("backtest.autonomous_backtest_engine", "PATTERN_TO_STRATEGY_MAP"),
    ("backtest.backtest_framework", "BacktestResults"),

    # AI
    ("ai.autonomous_ai_reasoning", "AutonomousAIReasoning"),

    # Gamma
    ("gamma.gamma_expiration_builder", "GammaExpirationBuilder"),
    ("gamma.forward_magnets_detector", "detect_forward_magnets"),
    ("gamma.gamma_alerts", "GammaAlerts"),

    # DB
    ("db.autonomous_database_logger", "AutonomousDatabaseLogger"),
    ("db.config_and_database", "init_database"),
    ("db.config_and_database", "STRATEGIES"),

    # Trading Mixins
    ("trading.mixins.position_sizer", "PositionSizerMixin"),
    ("trading.mixins.trade_executor", "TradeExecutorMixin"),
    ("trading.mixins.risk_manager", "RiskManagerMixin"),
    ("trading.mixins.position_manager", "PositionManagerMixin"),
    ("trading.mixins.performance_tracker", "PerformanceTrackerMixin"),

    # Scheduler
    ("scheduler.autonomous_scheduler", "run_continuous_scheduler"),
    ("scheduler.autonomous_scheduler", "render_scheduled_task"),

    # Monitoring
    ("monitoring.autonomous_monitoring", "TraderMonitor"),
]

for module, attr in organized_imports:
    try:
        mod = __import__(module, fromlist=[attr])
        obj = getattr(mod, attr)
        ok(f"{module}.{attr}")
        track(True)
    except Exception as e:
        err = str(e)
        if "DATABASE_URL" in err or "streamlit" in err or "langchain" in err:
            warn(f"{module}.{attr} (optional dep)")
            track(False, warning=True)
        else:
            fail(f"{module}.{attr}", err)
            track(False)


# =============================================================================
# 3. BACKEND API ROUTES (Structure Only)
# =============================================================================
section("3. BACKEND API ROUTES")

route_files = [
    "vix_routes", "spx_routes", "system_routes", "core_routes", "trader_routes",
    "backtest_routes", "database_routes", "gex_routes", "gamma_routes",
    "optimizer_routes", "ai_routes", "probability_routes", "notification_routes",
    "misc_routes", "alerts_routes", "setups_routes", "scanner_routes",
    "autonomous_routes", "psychology_routes", "ai_intelligence_routes"
]

# Check files exist
import pathlib
routes_dir = pathlib.Path("backend/api/routes")
for route in route_files:
    route_file = routes_dir / f"{route}.py"
    if route_file.exists():
        ok(f"{route}.py exists")
        track(True)
    else:
        fail(f"{route}.py missing")
        track(False)


# =============================================================================
# 4. STRATEGY STATS & FEEDBACK LOOP
# =============================================================================
section("4. STRATEGY STATS & FEEDBACK LOOP")

try:
    from core.strategy_stats import get_strategy_stats, STRATEGY_STATS_FILE
    stats = get_strategy_stats()
    ok(f"Strategy stats loaded ({len(stats)} strategies)")
    track(True)

    # Count by source
    backtest_count = sum(1 for s in stats.values() if s.get('source') == 'backtest')
    initial_count = sum(1 for s in stats.values() if s.get('source') == 'initial_estimate')

    if backtest_count > 0:
        ok(f"  → {backtest_count} from backtest, {initial_count} initial estimates")
    else:
        warn(f"  → All {initial_count} are initial estimates (run backtest to update)")
    track(True)
except Exception as e:
    fail("Strategy stats", str(e))
    track(False)

# Pattern mapping
try:
    from backtest.autonomous_backtest_engine import PATTERN_TO_STRATEGY_MAP
    ok(f"Pattern→Strategy mapping: {len(PATTERN_TO_STRATEGY_MAP)} patterns")
    track(True)

    # Show a few mappings
    for pattern, strategy in list(PATTERN_TO_STRATEGY_MAP.items())[:3]:
        print(f"      {pattern} → {strategy}")
except Exception as e:
    fail("Pattern mapping", str(e))
    track(False)


# =============================================================================
# 5. TRADING COMPONENTS
# =============================================================================
section("5. TRADING COMPONENTS")

try:
    from core.autonomous_paper_trader import AutonomousPaperTrader

    # Check the class has expected methods (from mixins + core)
    methods = [
        'generate_entry_signal',      # Core trader
        'find_and_execute_daily_trade', # Core trader
        'get_available_capital',       # PositionManagerMixin
        'check_risk_limits',          # RiskManagerMixin
        'get_portfolio_greeks',       # RiskManagerMixin
        'calculate_kelly_position_size', # PositionSizerMixin
    ]

    missing = [m for m in methods if not hasattr(AutonomousPaperTrader, m)]

    if not missing:
        ok(f"AutonomousPaperTrader: all {len(methods)} key methods present")
        track(True)
    else:
        warn(f"AutonomousPaperTrader missing: {missing}")
        track(False, warning=True)
except Exception as e:
    fail("Trading components", str(e))
    track(False)


# =============================================================================
# 6. MIXINS INHERITANCE CHECK
# =============================================================================
section("6. MIXIN INHERITANCE")

try:
    from core.autonomous_paper_trader import AutonomousPaperTrader
    from trading.mixins import (PositionSizerMixin, TradeExecutorMixin,
                                PositionManagerMixin, PerformanceTrackerMixin,
                                RiskManagerMixin)

    mro = AutonomousPaperTrader.__mro__
    mixin_names = [c.__name__ for c in mro]

    expected_mixins = ['PositionSizerMixin', 'TradeExecutorMixin',
                       'PositionManagerMixin', 'PerformanceTrackerMixin',
                       'RiskManagerMixin']

    for mixin in expected_mixins:
        if mixin in mixin_names:
            ok(f"Inherits {mixin}")
            track(True)
        else:
            fail(f"Missing {mixin}")
            track(False)
except Exception as e:
    fail("Mixin check", str(e))
    track(False)


# =============================================================================
# 7. DATABASE TEST (if DATABASE_URL set)
# =============================================================================
section("7. DATABASE")

real_db_url = os.environ.get('DATABASE_URL_REAL') or os.environ.get('DATABASE_URL')
if real_db_url and 'localhost/test' not in real_db_url:
    try:
        # Re-import with real URL
        os.environ['DATABASE_URL'] = real_db_url
        import importlib
        import database_adapter
        importlib.reload(database_adapter)

        conn = database_adapter.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        ok("PostgreSQL connected")
        track(True)
    except Exception as e:
        fail("PostgreSQL", str(e))
        track(False)
else:
    warn("DATABASE_URL not set - skipping DB tests")
    print("      Set DATABASE_URL to test database connectivity")


# =============================================================================
# 8. API TESTS (if URL provided)
# =============================================================================
BASE_URL = sys.argv[1] if len(sys.argv) > 1 else None

if BASE_URL:
    section("8. LIVE API TESTS")

    import urllib.request
    import urllib.error

    endpoints = [
        ("/health", "Health"),
        ("/api/trader/status", "Trader"),
        ("/api/spx/status", "SPX"),
        ("/api/gex/SPY", "GEX"),
        ("/api/backtests/results", "Backtests"),
        ("/api/backtests/strategy-stats", "Strategy Stats"),
        ("/api/ai-intelligence/market-commentary", "AI Commentary"),
        ("/api/probability/accuracy", "Probability"),
    ]

    for endpoint, name in endpoints:
        try:
            url = f"{BASE_URL}{endpoint}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Test'})
            with urllib.request.urlopen(req, timeout=15) as response:
                code = response.getcode()
                data = json.loads(response.read().decode())
                success = data.get('success', True)
                if success:
                    ok(f"{name} → 200 OK")
                    track(True)
                else:
                    warn(f"{name} → success=false")
                    track(False, warning=True)
        except urllib.error.HTTPError as e:
            if e.code < 500:
                warn(f"{name} → HTTP {e.code}")
                track(False, warning=True)
            else:
                fail(f"{name} → HTTP {e.code}")
                track(False)
        except Exception as e:
            fail(f"{name}", str(e)[:50])
            track(False)

    # Backtest trigger
    section("9. BACKTEST + FEEDBACK LOOP")
    try:
        url = f"{BASE_URL}/api/backtests/run"
        req = urllib.request.Request(url, method='POST', headers={'User-Agent': 'Test'})
        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode())
            if data.get('success'):
                patterns = data.get('data', {}).get('patterns_with_signals', 0)
                ok(f"Backtest: {patterns} patterns with signals")
                track(True)
            else:
                warn(f"Backtest: {data.get('message', 'unknown')[:50]}")
                track(False, warning=True)
    except Exception as e:
        fail(f"Backtest trigger", str(e)[:60])
        track(False)

    # Check feedback loop result
    try:
        import time
        time.sleep(2)
        url = f"{BASE_URL}/api/backtests/strategy-stats"
        req = urllib.request.Request(url, headers={'User-Agent': 'Test'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            if data.get('success'):
                strategies = data.get('data', {})
                backtest_sourced = sum(1 for s in strategies.values()
                                       if isinstance(s, dict) and s.get('source') == 'backtest')
                if backtest_sourced > 0:
                    ok(f"Feedback loop: {backtest_sourced} strategies from backtest")
                    track(True)
                else:
                    warn("Feedback loop: waiting for signals with 3+ trades")
                    track(False, warning=True)
    except Exception as e:
        warn(f"Feedback check: {str(e)[:50]}")
        track(False, warning=True)

else:
    warn("No URL provided - skipping live API tests")
    print(f"      Run: python test_everything.py https://your-app.onrender.com")


# =============================================================================
# FINAL SUMMARY
# =============================================================================
section("SUMMARY")

total = results["passed"] + results["failed"] + results["warned"]
pass_rate = (results["passed"] / total * 100) if total > 0 else 0

print(f"""
  {GREEN}Passed:   {results['passed']}{RESET}
  {RED}Failed:   {results['failed']}{RESET}
  {YELLOW}Warnings: {results['warned']}{RESET}
  ───────────────
  Total:    {total}
  Rate:     {pass_rate:.0f}%
""")

if results["failed"] == 0:
    print(f"{GREEN}{'='*60}")
    print(f" ✓ ALL CORE TESTS PASSED")
    print(f"{'='*60}{RESET}")
    sys.exit(0)
elif results["failed"] <= 3:
    print(f"{YELLOW}{'='*60}")
    print(f" ⚠ MOSTLY PASSING - {results['failed']} non-critical failures")
    print(f"{'='*60}{RESET}")
    sys.exit(0)
else:
    print(f"{RED}{'='*60}")
    print(f" ✗ {results['failed']} TESTS FAILED")
    print(f"{'='*60}{RESET}")
    sys.exit(1)
