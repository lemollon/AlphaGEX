"""
VALOR Margin Management System — Post-Deploy Test Suite
=========================================================

12 tests covering:
1. Margin Config Integrity
2. Manager Initialization
3. Zone Detection Accuracy
4. Combined Portfolio Zone Thresholds
5. Pre-Trade Gate Logic
6. Liquidation Priority Order
7. Liquidation Actions Per Zone
8. Cooldown & Re-Entry Logic
9. No Hardcoded $1500
10. Existing Tracker Preserved
11. Frontend Build (separate — run via npm)
12. Scan Loop Integration

All tests use mock data — no DB, no real positions, no side effects.
"""

import sys
import os
import importlib
import importlib.util
import types
import ast
from datetime import datetime, timedelta

# =====================================================================
# Bootstrap: Load modules without full package chain
# =====================================================================

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

# Create minimal package hierarchy
trading_pkg = types.ModuleType('trading')
trading_valor_pkg = types.ModuleType('trading.valor')
sys.modules.setdefault('trading', trading_pkg)
sys.modules.setdefault('trading.valor', trading_valor_pkg)

# Load models
spec_m = importlib.util.spec_from_file_location(
    'trading.valor.models',
    os.path.join(PROJECT_ROOT, 'trading', 'valor', 'models.py'),
)
models_mod = importlib.util.module_from_spec(spec_m)
sys.modules['trading.valor.models'] = models_mod
trading_valor_pkg.models = models_mod
spec_m.loader.exec_module(models_mod)

# Load margin_manager
spec_mm = importlib.util.spec_from_file_location(
    'trading.valor.margin_manager',
    os.path.join(PROJECT_ROOT, 'trading', 'valor', 'margin_manager.py'),
)
mm = importlib.util.module_from_spec(spec_mm)
mm.__package__ = 'trading.valor'
sys.modules['trading.valor.margin_manager'] = mm
spec_mm.loader.exec_module(mm)


# =====================================================================
# Mock position helper
# =====================================================================

class MockPosition:
    """Simulates a FuturesPosition for margin tests."""
    def __init__(self, contracts=1, ticker='MES', entry_price=6000.0,
                 direction='LONG', position_id='mock'):
        self.contracts = contracts
        self.entry_price = entry_price
        self.direction = type('D', (), {'value': direction})()
        self.ticker = ticker
        self.position_id = position_id
        self.is_open = True
        self.status = type('S', (), {'value': 'OPEN'})()


# =====================================================================
# Test infrastructure
# =====================================================================

results = {}
all_checks = []

def check(test_num, desc, condition, expected=None, actual=None):
    """Record a check result."""
    passed = bool(condition)
    entry = {
        'test': test_num,
        'desc': desc,
        'passed': passed,
        'expected': expected,
        'actual': actual,
    }
    all_checks.append(entry)
    status = "PASS" if passed else "FAIL"
    detail = ""
    if not passed and expected is not None:
        detail = f" (expected={expected}, actual={actual})"
    print(f"    [{status}] {desc}{detail}")
    return passed


def run_test(test_num, name, fn):
    """Run a test and record the result."""
    print(f"\n{'='*60}")
    print(f"TEST {test_num}: {name}")
    print(f"{'='*60}")
    try:
        passed = fn()
        results[test_num] = ('PASS' if passed else 'FAIL', name)
    except Exception as e:
        print(f"    [FAIL] EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        results[test_num] = ('FAIL', name)


# =====================================================================
# TEST 1: Margin Config Integrity
# =====================================================================

def test_1_margin_config():
    """Verify all 6 instruments have correct margin rates."""
    # Load shared margin config directly
    config_path = os.path.join(PROJECT_ROOT, 'trading', 'shared', 'margin_config.py')
    spec = importlib.util.spec_from_file_location('shared_margin_config', config_path)
    cfg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cfg)

    EXPECTED = {
        "MES": {"initial": 2300.0, "maintenance": 2100.0},
        "MNQ": {"initial": 3300.0, "maintenance": 3000.0},
        "M2K": {"initial": 950.0,  "maintenance": 860.0},
        "RTY": {"initial": 950.0,  "maintenance": 860.0},
        "CL":  {"initial": 575.0,  "maintenance": 520.0},
        "NG":  {"initial": 575.0,  "maintenance": 520.0},
        "MGC": {"initial": 1870.0, "maintenance": 1700.0},
    }

    STALE_VALUES = {1500.0, 1320.0, 1350.0, 7000.0, 6300.0, 2500.0, 2250.0, 10000.0}

    all_pass = True
    specs = cfg.FUTURES_MARGIN_SPECS

    for ticker, expected in EXPECTED.items():
        if ticker not in specs:
            check(1, f"{ticker} exists in FUTURES_MARGIN_SPECS", False, "present", "missing")
            all_pass = False
            continue

        spec_data = specs[ticker]
        im = spec_data.get("initial_margin", 0)
        mm_val = spec_data.get("maintenance_margin", 0)

        ok_im = check(1, f"{ticker} initial_margin=${im}", im == expected["initial"],
                       expected["initial"], im)
        ok_mm = check(1, f"{ticker} maintenance_margin=${mm_val}", mm_val == expected["maintenance"],
                       expected["maintenance"], mm_val)

        if im in STALE_VALUES:
            check(1, f"{ticker} NOT using stale value ${im}", False, "non-stale", im)
            all_pass = False

        if not ok_im or not ok_mm:
            all_pass = False

    # Also check VALOR's own config
    for tk, req in mm.VALOR_MARGIN_REQUIREMENTS.items():
        exp = EXPECTED.get(tk, EXPECTED.get(tk))
        if exp:
            check(1, f"VALOR_MARGIN_REQUIREMENTS[{tk}] initial matches",
                  req["initial"] == exp["initial"], exp["initial"], req["initial"])

    return all_pass


# =====================================================================
# TEST 2: Manager Initialization
# =====================================================================

def test_2_initialization():
    mgr = mm.ValorMarginManager()

    all_pass = True
    all_pass &= check(2, "MarginManager created", mgr is not None)
    all_pass &= check(2, "6 instruments in VALOR_MARGIN_REQUIREMENTS",
                       len(mm.VALOR_MARGIN_REQUIREMENTS) == 6, 6, len(mm.VALOR_MARGIN_REQUIREMENTS))
    all_pass &= check(2, "Expected instruments",
                       set(mm.VALOR_MARGIN_REQUIREMENTS.keys()) == {'MES','MNQ','RTY','CL','NG','MGC'})

    # All start GREEN
    for tk in mm.VALOR_MARGIN_REQUIREMENTS:
        zone = mgr._previous_zones.get(tk)
        all_pass &= check(2, f"{tk} starts in GREEN", zone == mm.MarginZone.GREEN,
                          "GREEN", zone.value if zone else None)

    # No active cooldowns
    for tk in mm.VALOR_MARGIN_REQUIREMENTS:
        all_pass &= check(2, f"{tk} no cooldown", not mgr._is_in_cooldown(tk))

    # Liquidation counts at 0
    for tk in mm.VALOR_MARGIN_REQUIREMENTS:
        count = mgr._liquidation_count_today.get(tk, 0)
        all_pass &= check(2, f"{tk} liquidation_count_today=0", count == 0, 0, count)

    return all_pass


# =====================================================================
# TEST 3: Zone Detection Accuracy
# =====================================================================

def test_3_zone_detection():
    TEST_CASES = [
        (0.0,   "GREEN"),
        (0.10,  "GREEN"),
        (0.25,  "GREEN"),
        (0.499, "GREEN"),
        (0.50,  "YELLOW"),
        (0.501, "YELLOW"),
        (0.60,  "YELLOW"),
        (0.699, "YELLOW"),
        (0.70,  "ORANGE"),
        (0.75,  "ORANGE"),
        (0.799, "ORANGE"),
        (0.80,  "RED"),
        (0.85,  "RED"),
        (0.899, "RED"),
        (0.90,  "CRITICAL"),
        (0.95,  "CRITICAL"),
        (1.0,   "CRITICAL"),
    ]

    all_pass = True
    for util, expected in TEST_CASES:
        zone = mm.get_zone(util)
        ok = check(3, f"Utilization {util*100:.1f}% -> {expected}",
                   zone.value == expected, expected, zone.value)
        all_pass &= ok

    return all_pass


# =====================================================================
# TEST 4: Combined Portfolio Zone Thresholds
# =====================================================================

def test_4_combined_zones():
    COMBINED_TESTS = [
        (0.0,   "GREEN"),
        (0.399, "GREEN"),
        (0.40,  "YELLOW"),
        (0.549, "YELLOW"),
        (0.55,  "ORANGE"),
        (0.699, "ORANGE"),
        (0.70,  "RED"),
        (0.799, "RED"),
        (0.80,  "CRITICAL"),
        (0.95,  "CRITICAL"),
    ]

    all_pass = True
    for util, expected in COMBINED_TESTS:
        zone = mm.get_zone(util, mm.COMBINED_ZONE_THRESHOLDS)
        ok = check(4, f"Combined {util*100:.1f}% -> {expected}",
                   zone.value == expected, expected, zone.value)
        all_pass &= ok

    # Verify combined thresholds are stricter
    check(4, "Combined YELLOW starts at 40% (vs 50% per-instrument)",
          mm.COMBINED_ZONE_THRESHOLDS[mm.MarginZone.YELLOW][0] == 0.40)
    check(4, "Combined ORANGE starts at 55% (vs 70% per-instrument)",
          mm.COMBINED_ZONE_THRESHOLDS[mm.MarginZone.ORANGE][0] == 0.55)
    check(4, "Combined RED starts at 70% (vs 80% per-instrument)",
          mm.COMBINED_ZONE_THRESHOLDS[mm.MarginZone.RED][0] == 0.70)
    check(4, "Combined CRITICAL starts at 80% (vs 90% per-instrument)",
          mm.COMBINED_ZONE_THRESHOLDS[mm.MarginZone.CRITICAL][0] == 0.80)

    return all_pass


# =====================================================================
# TEST 5: Pre-Trade Gate Logic
# =====================================================================

def test_5_pretrade_gate():
    mgr = mm.ValorMarginManager()
    all_pass = True

    # Scenario A: GREEN zone, plenty of margin
    # 2 MES contracts => 2*2100 = $4200 margin, 4.2% of $100K
    positions_a = [MockPosition(contracts=2, ticker='MES')]
    ok, reason, adj = mgr.can_open_position('MES', 1, positions_a, 100000.0)
    all_pass &= check(5, "A: GREEN zone approved", ok, True, ok)
    all_pass &= check(5, "A: Full size (1 contract)", adj == 1, 1, adj)

    # Scenario B: GREEN near boundary
    # 22 contracts => 22*2100 = $46200, 46.2%. Adding 3 => 25*2100 = $52500 = 52.5%
    positions_b = [MockPosition(ticker='MES') for _ in range(22)]
    ok_b, reason_b, adj_b = mgr.can_open_position('MES', 3, positions_b, 100000.0)
    all_pass &= check(5, "B: GREEN near 50%, contracts reduced",
                       adj_b < 3, "<3", adj_b)

    # Scenario C: YELLOW zone, reduce 50%
    # 26 contracts => 26*2100 = $54600, 54.6%
    positions_c = [MockPosition(ticker='MES') for _ in range(26)]
    ok_c, reason_c, adj_c = mgr.can_open_position('MES', 4, positions_c, 100000.0)
    all_pass &= check(5, "C: YELLOW zone approved", ok_c, True, ok_c)
    all_pass &= check(5, "C: 50% reduction (4->2)", adj_c == 2, 2, adj_c)
    all_pass &= check(5, "C: Reason mentions YELLOW", "YELLOW" in reason_c.upper(),
                       "YELLOW in reason", reason_c[:80])

    # Scenario D: YELLOW zone, would push to ORANGE
    # 32 contracts => 32*2100 = $67200, 67.2%. Adding 2 reduced to 1 => 33*2100 = $69300 = 69.3%
    # But wait — 2//2 = 1. 33*2100 = $69300 / $100000 = 69.3% < 70%, so might be allowed.
    # Let's use 33 to get 69.3%, then adding even 1 reduced = still OK.
    # Use 34: 34*2100 = $71400 = 71.4% => already ORANGE!
    positions_d_orange = [MockPosition(ticker='MES') for _ in range(34)]
    ok_d, reason_d, adj_d = mgr.can_open_position('MES', 2, positions_d_orange, 100000.0)
    all_pass &= check(5, "D: ORANGE zone blocked", not ok_d, False, ok_d)

    # Scenario E: ORANGE zone blocked
    positions_e = [MockPosition(ticker='MES') for _ in range(36)]
    ok_e, reason_e, adj_e = mgr.can_open_position('MES', 1, positions_e, 100000.0)
    all_pass &= check(5, "E: ORANGE zone, 1 contract blocked", not ok_e, False, ok_e)

    # Scenario F: Insufficient free margin
    # CL: maint $520. Make utilization low but eat up all free margin.
    # 190 CL positions: 190*520 = $98,800 used. Free = $1,200.
    # But utilization = 98.8% = CRITICAL, so it's blocked by zone, not free margin.
    # Instead: equity = $1000, 0 positions, try to open 2 CL contracts (initial = 2*575 = $1150 > $1000)
    ok_f, reason_f, adj_f = mgr.can_open_position('CL', 2, [], 1000.0)
    all_pass &= check(5, "F: Insufficient free margin blocked", not ok_f, False, ok_f)
    all_pass &= check(5, "F: Reason mentions margin/insufficient",
                       "insufficient" in reason_f.lower() or "free margin" in reason_f.lower(),
                       "margin message", reason_f[:80])

    return all_pass


# =====================================================================
# TEST 6: Liquidation Priority Order
# =====================================================================

def test_6_liquidation_priority():
    mgr = mm.ValorMarginManager()
    all_pass = True

    # Create mock positions with known P&L (entry vs current=6000, LONG, MES $5/pt)
    # pos_A: entry=6080, 2 contracts => unrealized = (6000-6080)*5*1*2 = -$800
    # pos_B: entry=6040, 1 contract  => unrealized = (6000-6040)*5*1*1 = -$200
    # pos_C: entry=6000, 1 contract, SHORT => unrealized = (6000-6000)*5*-1*1 = $0 + direction
    #         entry=5940, SHORT: unrealized = (6000-5940)*5*(-1)*1 = -$300... need positive.
    #         entry=6060, SHORT: unrealized = (6000-6060)*5*(-1)*1 = +$300
    # pos_D: entry=6030, 1 contract, LONG => unrealized = (6000-6030)*5*1*1 = -$150
    # pos_E: entry=6080, 3 contracts, SHORT => unrealized = (6000-6080)*5*(-1)*3 = +$1200

    positions = [
        MockPosition(contracts=2, entry_price=6080.0, direction='LONG', position_id='pos_A'),
        MockPosition(contracts=1, entry_price=6040.0, direction='LONG', position_id='pos_B'),
        MockPosition(contracts=1, entry_price=6060.0, direction='SHORT', position_id='pos_C'),
        MockPosition(contracts=1, entry_price=6030.0, direction='LONG', position_id='pos_D'),
        MockPosition(contracts=3, entry_price=6080.0, direction='SHORT', position_id='pos_E'),
    ]

    # Expected return_on_margin (MES maint = $2100):
    # pos_A: unrealized=-$800, margin=2*2100=$4200 => rom = -800/4200 = -0.190 (WORST)
    # pos_B: unrealized=-$200, margin=1*2100=$2100 => rom = -200/2100 = -0.095
    # pos_D: unrealized=-$150, margin=1*2100=$2100 => rom = -150/2100 = -0.071
    # pos_C: unrealized=+$300, margin=1*2100=$2100 => rom = +300/2100 = +0.143
    # pos_E: unrealized=+$1200, margin=3*2100=$6300 => rom = +1200/6300 = +0.190 (BEST)

    scored = mgr._score_positions('MES', positions, {'MES': 6000.0})

    # Get order of position_ids
    order = [p.position_id for p, rom in scored]
    print(f"    Liquidation order: {order}")
    print(f"    Return on margin: {[f'{rom:.3f}' for _, rom in scored]}")

    all_pass &= check(6, "Worst position (pos_A) is first",
                       order[0] == 'pos_A', 'pos_A', order[0])
    all_pass &= check(6, "Best position (pos_E) is last",
                       order[-1] == 'pos_E', 'pos_E', order[-1])

    # All losers before all winners
    loser_ids = {'pos_A', 'pos_B', 'pos_D'}
    winner_ids = {'pos_C', 'pos_E'}
    last_loser_idx = max(i for i, pid in enumerate(order) if pid in loser_ids)
    first_winner_idx = min(i for i, pid in enumerate(order) if pid in winner_ids)
    all_pass &= check(6, "All losers before all winners",
                       last_loser_idx < first_winner_idx,
                       f"last_loser<first_winner", f"{last_loser_idx} vs {first_winner_idx}")

    return all_pass


# =====================================================================
# TEST 7: Liquidation Actions Per Zone
# =====================================================================

def test_7_liquidation_actions():
    mgr = mm.ValorMarginManager()
    all_pass = True

    def make_positions(n, ticker='MES'):
        return [MockPosition(ticker=ticker, position_id=f'p{i}') for i in range(n)]

    # GREEN zone: 10 contracts => 10*2100 = $21000, 21% of $100K
    pos_green = make_positions(10)
    liq_green = mgr.get_positions_to_liquidate('MES', pos_green, 100000.0, {'MES': 6000})
    all_pass &= check(7, "GREEN: 0 liquidations", len(liq_green) == 0, 0, len(liq_green))

    # YELLOW zone: 26 contracts => 26*2100 = $54600, 54.6%
    pos_yellow = make_positions(26)
    liq_yellow = mgr.get_positions_to_liquidate('MES', pos_yellow, 100000.0, {'MES': 6000})
    all_pass &= check(7, "YELLOW: 0 liquidations", len(liq_yellow) == 0, 0, len(liq_yellow))

    # ORANGE zone: 35 contracts => 35*2100 = $73500, 73.5%
    pos_orange = make_positions(35)
    liq_orange = mgr.get_positions_to_liquidate('MES', pos_orange, 100000.0, {'MES': 6000})
    all_pass &= check(7, "ORANGE: 1 liquidation", len(liq_orange) == 1, 1, len(liq_orange))

    # RED zone: 40 contracts => 40*2100 = $84000, 84%
    pos_red = make_positions(40)
    liq_red = mgr.get_positions_to_liquidate('MES', pos_red, 100000.0, {'MES': 6000})
    all_pass &= check(7, "RED: 2 liquidations", len(liq_red) == 2, 2, len(liq_red))

    # RED zone with only 1 position
    pos_red_1 = make_positions(1)
    # Need 1 position with huge margin: fake equity=$1000 => 1*2100/$1000 = 210% => CRITICAL
    # Instead: let's use NG where maint=$520. 2 positions at 1ct each => 2*520/$1200 = 86.7% = RED
    pos_red_ng = [MockPosition(ticker='NG', position_id='ng1')]
    liq_red_1 = mgr.get_positions_to_liquidate('NG', pos_red_ng, 600.0, {'NG': 3.0})
    # 1*520/600 = 86.7% = RED, but only 1 position available
    state = mgr.get_instrument_margin_state('NG', pos_red_ng, 600.0)
    if state['zone'] == mm.MarginZone.RED:
        all_pass &= check(7, "RED with 1 position: closes 1 (not error)",
                          len(liq_red_1) == 1, 1, len(liq_red_1))
    else:
        check(7, f"NG 1ct/$600 zone is {state['zone'].value} (expected RED)", False)

    # CRITICAL zone: 45 contracts => 45*2100 = $94500, 94.5%
    pos_critical = make_positions(45)
    liq_critical = mgr.get_positions_to_liquidate('MES', pos_critical, 100000.0, {'MES': 6000})
    all_pass &= check(7, "CRITICAL: ALL liquidated",
                       len(liq_critical) == 45, 45, len(liq_critical))

    return all_pass


# =====================================================================
# TEST 8: Cooldown & Re-Entry Logic
# =====================================================================

def test_8_cooldown():
    mgr = mm.ValorMarginManager()
    all_pass = True

    # 1. First liquidation: 30-min cooldown
    mgr._record_liquidation('CL')
    all_pass &= check(8, "1st event: CL in cooldown", mgr._is_in_cooldown('CL'))
    remaining = mgr._cooldown_remaining_minutes('CL')
    all_pass &= check(8, "1st event: ~30 min cooldown",
                       28 < remaining <= 31, "~30", f"{remaining:.1f}")
    all_pass &= check(8, "1st event: re_entry_reduced set",
                       mgr._re_entry_reduced['CL'])

    # Blocked during cooldown
    ok_cd, reason_cd, _ = mgr.can_open_position('CL', 1, [], 100000.0)
    all_pass &= check(8, "Blocked during cooldown", not ok_cd)
    all_pass &= check(8, "Reason mentions cooldown", "cooldown" in reason_cd.lower())

    # Simulate cooldown expired
    mgr._cooldown_until['CL'] = datetime.now(models_mod.CENTRAL_TZ) - timedelta(minutes=1)
    all_pass &= check(8, "After cooldown: no longer in cooldown",
                       not mgr._is_in_cooldown('CL'))

    # Re-entry should work but at 50% size
    ok_re, reason_re, adj_re = mgr.can_open_position('CL', 4, [], 100000.0)
    all_pass &= check(8, "Re-entry allowed after cooldown", ok_re)
    all_pass &= check(8, "Re-entry at 50% size (4->2)", adj_re == 2, 2, adj_re)

    # re_entry_reduced cleared after first re-entry
    all_pass &= check(8, "re_entry_reduced cleared", not mgr._re_entry_reduced['CL'])

    # 2. Second liquidation: 2-hour cooldown
    mgr._record_liquidation('CL')
    remaining2 = mgr._cooldown_remaining_minutes('CL')
    all_pass &= check(8, "2nd event: ~2 hour cooldown",
                       118 < remaining2 <= 121, "~120", f"{remaining2:.1f}")
    all_pass &= check(8, "2nd event: count=2",
                       mgr._liquidation_count_today['CL'] == 2, 2,
                       mgr._liquidation_count_today['CL'])

    # 3. Third liquidation: paused until midnight
    mgr._cooldown_until['CL'] = datetime.now(models_mod.CENTRAL_TZ) - timedelta(minutes=1)
    mgr._record_liquidation('CL')
    all_pass &= check(8, "3rd event: count=3",
                       mgr._liquidation_count_today['CL'] == 3, 3,
                       mgr._liquidation_count_today['CL'])

    # Should be blocked
    ok_3, reason_3, _ = mgr.can_open_position('CL', 1, [], 100000.0)
    all_pass &= check(8, "3rd event: CL blocked", not ok_3)

    # 4. CL cooldown does NOT affect MES
    all_pass &= check(8, "MES not in cooldown", not mgr._is_in_cooldown('MES'))
    ok_mes, _, _ = mgr.can_open_position('MES', 1, [], 100000.0)
    all_pass &= check(8, "MES can still trade", ok_mes)

    # 5. Verify daily reset
    mgr._liquidation_date = "1999-01-01"  # Force date mismatch
    mgr._record_liquidation('RTY')  # This should trigger daily reset
    all_pass &= check(8, "Daily reset: CL count reset to 0 after date change",
                       mgr._liquidation_count_today.get('CL', 0) == 0, 0,
                       mgr._liquidation_count_today.get('CL'))
    all_pass &= check(8, "Daily reset: RTY count = 1 (new event)",
                       mgr._liquidation_count_today.get('RTY', 0) == 1, 1,
                       mgr._liquidation_count_today.get('RTY'))

    return all_pass


# =====================================================================
# TEST 9: No Hardcoded $1500
# =====================================================================

def test_9_no_hardcoded():
    all_pass = True

    files_to_check = [
        os.path.join(PROJECT_ROOT, 'trading', 'valor', 'trader.py'),
        os.path.join(PROJECT_ROOT, 'trading', 'valor', 'margin_manager.py'),
    ]

    stale_patterns = [
        ("1500.0  # Approx MES margin", "old MES hardcoded"),
        ("margin_per_contract = 1500", "hardcoded 1500"),
        ("min_margin_per_contract = 1500", "executor hardcoded"),
    ]

    for fpath in files_to_check:
        fname = os.path.basename(fpath)
        with open(fpath) as f:
            content = f.read()

        for pattern, desc in stale_patterns:
            found = pattern in content
            all_pass &= check(9, f"{fname}: no '{desc}'", not found,
                              "not found", "FOUND" if found else "not found")

    # Verify trader.py uses get_margin_requirement
    trader_path = os.path.join(PROJECT_ROOT, 'trading', 'valor', 'trader.py')
    with open(trader_path) as f:
        trader_src = f.read()

    all_pass &= check(9, "trader.py imports get_margin_requirement",
                       "get_margin_requirement" in trader_src)
    all_pass &= check(9, "trader.py calls get_margin_requirement for open",
                       'req = get_margin_requirement(ticker)' in trader_src)
    all_pass &= check(9, "trader.py calls get_margin_requirement for close",
                       'req = get_margin_requirement(pos_ticker_m)' in trader_src)

    return all_pass


# =====================================================================
# TEST 10: Existing Tracker Preserved
# =====================================================================

def test_10_existing_tracker():
    all_pass = True

    # 1. MarginCalculator still loadable
    try:
        engine_path = os.path.join(PROJECT_ROOT, 'trading', 'shared', 'margin_engine.py')
        spec = importlib.util.spec_from_file_location('margin_engine', engine_path)
        engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine)
        all_pass &= check(10, "MarginCalculator imports OK", True)

        # Test calculate_futures_margin
        result = engine.MarginCalculator.calculate_futures_margin(
            entry_price=6000.0,
            current_price=6010.0,
            contracts=2,
            side="long",
            point_value=5.0,
            initial_margin_per_contract=2300.0,
            maintenance_margin_per_contract=2100.0,
            account_equity=100000.0,
        )
        all_pass &= check(10, "calculate_futures_margin works", result is not None)
        all_pass &= check(10, "Result has margin_used", "margin_used" in result)
        all_pass &= check(10, "Result has available_margin", "available_margin" in result)
        all_pass &= check(10, "Result has unrealized_pnl", "unrealized_pnl" in result)
        # Verify unrealized P&L: (6010-6000)*5*1*2 = $100
        all_pass &= check(10, "Unrealized P&L = $100",
                          result["unrealized_pnl"] == 100.0, 100.0, result["unrealized_pnl"])

        # Test aggregate_positions
        agg = engine.MarginCalculator.aggregate_positions([result], 100000.0, "stock_futures")
        all_pass &= check(10, "aggregate_positions works", agg is not None)
        all_pass &= check(10, "Aggregate has position_count", agg.get("position_count") == 1)
    except Exception as e:
        check(10, f"MarginCalculator: {e}", False)
        all_pass = False

    # 2. MarginAnalysis component still referenced in frontend
    valor_content_path = os.path.join(PROJECT_ROOT, 'frontend', 'src', 'app', 'valor', 'ValorContent.tsx')
    with open(valor_content_path) as f:
        fe_src = f.read()

    all_pass &= check(10, "MarginAnalysis imported in ValorContent",
                       "import MarginAnalysis" in fe_src)
    all_pass &= check(10, "MarginAnalysis rendered in ValorContent",
                       "MarginAnalysis botName" in fe_src)

    # 3. New margin zone panel is ALONGSIDE, not replacing
    all_pass &= check(10, "Margin Protection Zones panel exists",
                       "Margin Protection Zones" in fe_src)
    all_pass &= check(10, "Both MarginAnalysis AND zone panel present",
                       "MarginAnalysis" in fe_src and "marginZoneData" in fe_src)

    # 4. Verify API route file has both old and new endpoints
    routes_path = os.path.join(PROJECT_ROOT, 'backend', 'api', 'routes', 'valor_routes.py')
    with open(routes_path) as f:
        routes_src = f.read()

    all_pass &= check(10, "Original /api/valor/margin endpoint exists",
                       '"/api/valor/margin"' in routes_src or "'/api/valor/margin'" in routes_src)
    all_pass &= check(10, "New /api/valor/margin/zones endpoint exists",
                       '"/api/valor/margin/zones"' in routes_src)
    all_pass &= check(10, "New /api/valor/margin/events endpoint exists",
                       '"/api/valor/margin/events"' in routes_src)

    return all_pass


# =====================================================================
# TEST 11: Frontend Build (checks structure, actual build separate)
# =====================================================================

def test_11_frontend():
    all_pass = True

    # Verify ValorContent.tsx is syntactically valid by checking key imports
    valor_path = os.path.join(PROJECT_ROOT, 'frontend', 'src', 'app', 'valor', 'ValorContent.tsx')
    with open(valor_path) as f:
        content = f.read()

    all_pass &= check(11, "Shield imported from lucide-react", "Shield" in content)
    all_pass &= check(11, "ChevronDown imported", "ChevronDown" in content)
    all_pass &= check(11, "ChevronUp imported", "ChevronUp" in content)
    all_pass &= check(11, "marginZoneData state hook", "marginZoneData" in content)
    all_pass &= check(11, "marginEventsExpanded state", "marginEventsExpanded" in content)
    all_pass &= check(11, "Fetches /api/valor/margin/zones", "/api/valor/margin/zones" in content)
    all_pass &= check(11, "Zone color classes present",
                       "bg-green-500" in content and "bg-yellow-500" in content
                       and "bg-orange-500" in content and "bg-red-500" in content)
    all_pass &= check(11, "Zone boundary markers at 50/70/80/90%",
                       "left-[50%]" in content and "left-[70%]" in content
                       and "left-[80%]" in content and "left-[90%]" in content)
    all_pass &= check(11, "Events table in collapsible section",
                       "Margin Events" in content)
    all_pass &= check(11, "Cooldown timer display",
                       "remaining_minutes" in content)

    # Verify existing MarginAnalysis NOT removed
    all_pass &= check(11, "MarginAnalysis component still present",
                       "MarginAnalysis botName" in content)

    return all_pass


# =====================================================================
# TEST 12: Scan Loop Integration
# =====================================================================

def test_12_scan_integration():
    all_pass = True

    trader_path = os.path.join(PROJECT_ROOT, 'trading', 'valor', 'trader.py')
    with open(trader_path) as f:
        content = f.read()

    # GATE 6.5 is in the scan path
    all_pass &= check(12, "GATE 6.5 in scan path", "GATE 6.5" in content)
    all_pass &= check(12, "can_open_position called", "can_open_position" in content)
    all_pass &= check(12, "margin_manager imported", "margin_manager" in content)

    # Margin monitoring called per scan
    all_pass &= check(12, "_run_margin_monitoring in run_scan",
                       "_run_margin_monitoring" in content)

    # Margin manager initialized in __init__
    all_pass &= check(12, "margin_manager created in __init__",
                       "self.margin_manager = ValorMarginManager()" in content)

    # Liquidation hook exists
    all_pass &= check(12, "get_positions_to_liquidate called",
                       "get_positions_to_liquidate" in content)
    all_pass &= check(12, "execute_liquidations called",
                       "execute_liquidations" in content)

    # Combined portfolio check
    all_pass &= check(12, "get_combined_margin_state called",
                       "get_combined_margin_state" in content)
    all_pass &= check(12, "get_combined_liquidation_target called",
                       "get_combined_liquidation_target" in content)

    # Per-instrument margin rates used (not hardcoded)
    all_pass &= check(12, "get_margin_requirement used for open",
                       'req = get_margin_requirement(ticker)' in content)
    all_pass &= check(12, "get_margin_requirement used for close",
                       'req = get_margin_requirement(pos_ticker_m)' in content)

    return all_pass


# =====================================================================
# RUN ALL TESTS
# =====================================================================

if __name__ == '__main__':
    run_test(1,  "Margin Config Integrity",       test_1_margin_config)
    run_test(2,  "Manager Initialization",         test_2_initialization)
    run_test(3,  "Zone Detection Accuracy",        test_3_zone_detection)
    run_test(4,  "Combined Portfolio Zones",       test_4_combined_zones)
    run_test(5,  "Pre-Trade Gate Logic",           test_5_pretrade_gate)
    run_test(6,  "Liquidation Priority Order",     test_6_liquidation_priority)
    run_test(7,  "Liquidation Actions Per Zone",   test_7_liquidation_actions)
    run_test(8,  "Cooldown & Re-Entry Logic",      test_8_cooldown)
    run_test(9,  "No Hardcoded $1500",             test_9_no_hardcoded)
    run_test(10, "Existing Tracker Preserved",     test_10_existing_tracker)
    run_test(11, "Frontend Build (Structure)",      test_11_frontend)
    run_test(12, "Scan Loop Integration",          test_12_scan_integration)

    # Summary
    print("\n")
    print("+" + "="*58 + "+")
    print("|   VALOR MARGIN SYSTEM POST-DEPLOY TEST RESULTS           |")
    print("+" + "="*58 + "+")

    passed_count = sum(1 for s, _ in results.values() if s == 'PASS')
    failed_names = [name for s, name in results.values() if s != 'PASS']
    total = len(results)

    for num in sorted(results.keys()):
        status, name = results[num]
        icon = "PASS" if status == "PASS" else "FAIL"
        print(f"| Test {num:>2}: {name:<35} [{icon}]    |")

    print("+" + "-"*58 + "+")
    print(f"| OVERALL:  {passed_count}/{total} PASSED" + " " * (46 - len(f"{passed_count}/{total} PASSED")) + "|")
    if failed_names:
        print(f"| CRITICAL FAILURES: {', '.join(failed_names):<38} |")
    else:
        print(f"| CRITICAL FAILURES: None" + " " * 34 + "|")
    print("+" + "="*58 + "+")

    # Detailed check summary
    total_checks = len(all_checks)
    passed_checks = sum(1 for c in all_checks if c['passed'])
    failed_checks = [c for c in all_checks if not c['passed']]

    print(f"\nDetailed: {passed_checks}/{total_checks} individual checks passed")
    if failed_checks:
        print("\nFailed checks:")
        for c in failed_checks:
            print(f"  Test {c['test']}: {c['desc']}")
            if c['expected'] is not None:
                print(f"    Expected: {c['expected']}, Actual: {c['actual']}")

    sys.exit(0 if not failed_names else 1)
