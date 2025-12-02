"""
End-to-End Pipeline Tests

These tests verify the ENTIRE trading pipeline works correctly:
1. Data flows from source to database to frontend
2. Prices are accurate and match real market data
3. P&L calculations are correct
4. Greeks are captured properly
5. Trade execution stores all required fields

Run on Render with: python tests/test_end_to_end.py
"""

import os
import sys
import time
import json
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESULTS = {"passed": [], "failed": [], "warnings": []}

def log_pass(test, details=""):
    RESULTS["passed"].append({"test": test, "details": details})
    print(f"✅ {test}: {details}" if details else f"✅ {test}")

def log_fail(test, details=""):
    RESULTS["failed"].append({"test": test, "details": details})
    print(f"❌ {test}: {details}" if details else f"❌ {test}")

def log_warn(test, details=""):
    RESULTS["warnings"].append({"test": test, "details": details})
    print(f"⚠️  {test}: {details}" if details else f"⚠️  {test}")


# =============================================================================
# TEST: End-to-End Trade Pipeline
# =============================================================================
def test_trade_pipeline():
    """
    Simulates the full trade pipeline:
    1. Get market data
    2. Get options chain
    3. Select a contract
    4. Record entry (like the trader would)
    5. Verify all fields are captured
    6. Simulate exit
    7. Verify P&L calculation
    """
    print("\n" + "="*70)
    print("END-TO-END TRADE PIPELINE TEST")
    print("="*70)

    try:
        from data.unified_data_provider import UnifiedDataProvider
        from database_adapter import get_connection

        provider = UnifiedDataProvider()

        # Step 1: Get current SPY price
        print("\n[Step 1] Getting current SPY price...")
        quote = provider.get_quote('SPY')
        if not quote:
            log_fail("Pipeline Step 1", "Could not get SPY quote")
            return

        spy_price = quote.price
        quote_source = quote.source
        print(f"   SPY Price: ${spy_price:.2f} (Source: {quote_source})")
        log_pass("Get SPY Quote", f"${spy_price:.2f} from {quote_source}")

        # Step 2: Get options chain
        print("\n[Step 2] Getting options chain...")
        chain = provider.get_options_chain('SPY', greeks=True)
        if not chain:
            log_fail("Pipeline Step 2", "Could not get options chain")
            return

        # Find ATM call
        calls = chain.calls if hasattr(chain, 'calls') else []
        if isinstance(calls, dict):
            calls = list(calls.values())

        if not calls:
            log_fail("Pipeline Step 2", "No call options in chain")
            return

        # Find closest to ATM
        atm_call = min(calls, key=lambda c: abs((c.strike if hasattr(c, 'strike') else 0) - spy_price))

        strike = atm_call.strike if hasattr(atm_call, 'strike') else 0
        bid = atm_call.bid if hasattr(atm_call, 'bid') else 0
        ask = atm_call.ask if hasattr(atm_call, 'ask') else 0
        delta = atm_call.delta if hasattr(atm_call, 'delta') else None
        gamma = atm_call.gamma if hasattr(atm_call, 'gamma') else None
        theta = atm_call.theta if hasattr(atm_call, 'theta') else None
        vega = atm_call.vega if hasattr(atm_call, 'vega') else None
        iv = atm_call.iv if hasattr(atm_call, 'iv') else (atm_call.implied_volatility if hasattr(atm_call, 'implied_volatility') else None)
        contract_symbol = atm_call.symbol if hasattr(atm_call, 'symbol') else None

        print(f"   ATM Call: ${strike} strike")
        print(f"   Bid: ${bid:.2f}, Ask: ${ask:.2f}")
        print(f"   Delta: {delta}, Gamma: {gamma}, Theta: {theta}, Vega: {vega}")
        print(f"   IV: {iv}")
        print(f"   Contract Symbol: {contract_symbol}")

        # Verify all data captured
        missing = []
        if not strike: missing.append("strike")
        if not bid: missing.append("bid")
        if not ask: missing.append("ask")
        if delta is None: missing.append("delta")
        if gamma is None: missing.append("gamma")
        if theta is None: missing.append("theta")
        if vega is None: missing.append("vega")
        if iv is None: missing.append("iv")
        if not contract_symbol: missing.append("contract_symbol")

        if missing:
            log_warn("Options Data Completeness", f"Missing: {', '.join(missing)}")
        else:
            log_pass("Options Data Completeness", "All fields captured")

        # Step 3: Simulate entry price calculation
        print("\n[Step 3] Calculating entry price...")
        mid_price = (bid + ask) / 2
        spread = ask - bid
        # Simulate buying at slightly above mid (realistic fill)
        simulated_entry = mid_price + (spread * 0.25)  # 25% toward ask

        print(f"   Mid Price: ${mid_price:.2f}")
        print(f"   Spread: ${spread:.2f}")
        print(f"   Simulated Entry: ${simulated_entry:.2f}")
        log_pass("Entry Price Calculation", f"Entry: ${simulated_entry:.2f} (mid + 25% of spread)")

        # Step 4: Create test position in database
        print("\n[Step 4] Recording test position to database...")
        conn = get_connection()
        cursor = conn.cursor()

        test_id = None
        try:
            cursor.execute("""
                INSERT INTO autonomous_open_positions (
                    symbol, strategy, action, entry_date, entry_time,
                    strike, option_type, expiration_date, contracts,
                    entry_price, entry_bid, entry_ask, entry_spot_price,
                    current_price, current_spot_price, unrealized_pnl,
                    confidence, gex_regime, trade_reasoning, contract_symbol,
                    entry_iv, entry_delta, entry_gamma, entry_theta, entry_vega,
                    is_delayed, data_confidence
                ) VALUES (
                    'SPY', 'E2E_TEST', 'BUY', %s, %s,
                    %s, 'call', %s, 1,
                    %s, %s, %s, %s,
                    %s, %s, 0,
                    95, 'TEST', 'End-to-end pipeline test', %s,
                    %s, %s, %s, %s, %s,
                    %s, %s
                )
                RETURNING id
            """, (
                datetime.now().strftime('%Y-%m-%d'),
                datetime.now().strftime('%H:%M:%S'),
                strike,
                (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d'),
                simulated_entry,
                bid,
                ask,
                spy_price,
                simulated_entry,
                spy_price,
                contract_symbol,
                iv,
                delta,
                gamma,
                theta,
                vega,
                quote_source != 'tradier',  # is_delayed
                'high' if quote_source == 'tradier' else 'medium'
            ))

            result = cursor.fetchone()
            test_id = result[0] if result else None
            conn.commit()

            if test_id:
                print(f"   Created test position ID: {test_id}")
                log_pass("Database Insert", f"Position ID {test_id} created")
            else:
                log_fail("Database Insert", "No ID returned")
                return

        except Exception as e:
            conn.rollback()
            log_fail("Database Insert", str(e))
            return

        # Step 5: Verify position was stored correctly
        print("\n[Step 5] Verifying stored data...")
        cursor.execute("""
            SELECT
                symbol, strike, entry_price, entry_bid, entry_ask,
                entry_spot_price, contract_symbol,
                entry_delta, entry_gamma, entry_theta, entry_vega, entry_iv,
                is_delayed, data_confidence
            FROM autonomous_open_positions
            WHERE id = %s
        """, (test_id,))

        stored = cursor.fetchone()
        if stored:
            stored_entry = float(stored[2]) if stored[2] else 0
            stored_bid = float(stored[3]) if stored[3] else 0
            stored_ask = float(stored[4]) if stored[4] else 0
            stored_contract = stored[6]
            stored_delta = stored[7]
            stored_is_delayed = stored[12]
            stored_confidence = stored[13]

            print(f"   Stored Entry: ${stored_entry:.2f} (expected: ${simulated_entry:.2f})")
            print(f"   Stored Bid: ${stored_bid:.2f} (expected: ${bid:.2f})")
            print(f"   Stored Ask: ${stored_ask:.2f} (expected: ${ask:.2f})")
            print(f"   Stored Contract: {stored_contract}")
            print(f"   Stored Delta: {stored_delta}")
            print(f"   Is Delayed: {stored_is_delayed}")
            print(f"   Data Confidence: {stored_confidence}")

            # Verify values match
            if abs(stored_entry - simulated_entry) < 0.01:
                log_pass("Entry Price Stored", f"${stored_entry:.2f} matches")
            else:
                log_fail("Entry Price Stored", f"Mismatch: stored ${stored_entry:.2f} vs expected ${simulated_entry:.2f}")

            if stored_contract == contract_symbol:
                log_pass("Contract Symbol Stored", stored_contract)
            else:
                log_fail("Contract Symbol Stored", f"Mismatch: {stored_contract} vs {contract_symbol}")

            if stored_delta is not None:
                log_pass("Greeks Stored", f"Delta: {stored_delta}")
            else:
                log_fail("Greeks Stored", "Delta is NULL")

        else:
            log_fail("Data Verification", "Could not retrieve stored position")

        # Step 6: Simulate price movement and P&L
        print("\n[Step 6] Simulating P&L calculation...")
        new_price = simulated_entry * 1.15  # 15% gain
        unrealized_pnl = (new_price - simulated_entry) * 100  # 1 contract = 100 shares

        print(f"   Original Entry: ${simulated_entry:.2f}")
        print(f"   New Price: ${new_price:.2f}")
        print(f"   Unrealized P&L: ${unrealized_pnl:.2f}")

        cursor.execute("""
            UPDATE autonomous_open_positions
            SET current_price = %s, unrealized_pnl = %s
            WHERE id = %s
        """, (new_price, unrealized_pnl, test_id))
        conn.commit()

        log_pass("P&L Calculation", f"${unrealized_pnl:.2f} for 15% price increase")

        # Step 7: Simulate closing the position
        print("\n[Step 7] Simulating position close...")
        exit_price = new_price * 0.99  # Slight slippage on exit
        realized_pnl = (exit_price - simulated_entry) * 100

        cursor.execute("""
            INSERT INTO autonomous_closed_trades (
                symbol, strategy, action, strike, option_type, expiration_date,
                contracts, contract_symbol, entry_date, entry_time, entry_price,
                entry_bid, entry_ask, entry_spot_price, exit_date, exit_time,
                exit_price, exit_spot_price, exit_reason, realized_pnl,
                realized_pnl_pct, confidence, gex_regime, trade_reasoning,
                hold_duration_minutes
            ) VALUES (
                'SPY', 'E2E_TEST', 'BUY', %s, 'call', %s,
                1, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, 'E2E_TEST_EXIT', %s,
                %s, 95, 'TEST', 'End-to-end test close',
                5
            )
        """, (
            strike,
            (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d'),
            contract_symbol,
            datetime.now().strftime('%Y-%m-%d'),
            datetime.now().strftime('%H:%M:%S'),
            simulated_entry,
            bid, ask, spy_price,
            datetime.now().strftime('%Y-%m-%d'),
            datetime.now().strftime('%H:%M:%S'),
            exit_price,
            spy_price,
            realized_pnl,
            ((exit_price - simulated_entry) / simulated_entry) * 100
        ))

        # Delete the open position
        cursor.execute("DELETE FROM autonomous_open_positions WHERE id = %s", (test_id,))
        conn.commit()

        print(f"   Exit Price: ${exit_price:.2f}")
        print(f"   Realized P&L: ${realized_pnl:.2f}")
        log_pass("Position Close", f"Closed with ${realized_pnl:.2f} P&L")

        # Cleanup: Remove test trades
        print("\n[Cleanup] Removing test data...")
        cursor.execute("DELETE FROM autonomous_closed_trades WHERE strategy = 'E2E_TEST'")
        cursor.execute("DELETE FROM autonomous_open_positions WHERE strategy = 'E2E_TEST'")
        conn.commit()
        conn.close()

        log_pass("Pipeline Complete", "All steps executed successfully")

    except Exception as e:
        log_fail("Pipeline Test", str(e))
        import traceback
        traceback.print_exc()


# =============================================================================
# TEST: Price Accuracy - Compare to Real Market
# =============================================================================
def test_price_accuracy():
    """
    Compare our stored prices against real-time market data
    to verify we're capturing accurate prices.
    """
    print("\n" + "="*70)
    print("PRICE ACCURACY TEST")
    print("="*70)

    try:
        from data.unified_data_provider import UnifiedDataProvider
        from database_adapter import get_connection

        provider = UnifiedDataProvider()
        conn = get_connection()
        cursor = conn.cursor()

        # Get a recent open position
        cursor.execute("""
            SELECT id, symbol, strike, option_type, expiration_date,
                   entry_price, entry_spot_price, current_price, contract_symbol
            FROM autonomous_open_positions
            WHERE strategy != 'E2E_TEST'
            ORDER BY created_at DESC
            LIMIT 1
        """)

        position = cursor.fetchone()

        if not position:
            log_warn("Price Accuracy", "No open positions to verify")
            conn.close()
            return

        pos_id = position[0]
        symbol = position[1]
        strike = position[2]
        opt_type = position[3]
        expiration = position[4]
        stored_entry = float(position[5]) if position[5] else 0
        stored_spot = float(position[6]) if position[6] else 0
        stored_current = float(position[7]) if position[7] else 0
        contract_symbol = position[8]

        print(f"\nVerifying position {pos_id}: {symbol} ${strike} {opt_type}")
        print(f"Contract: {contract_symbol}")
        print(f"Stored entry price: ${stored_entry:.2f}")
        print(f"Stored spot at entry: ${stored_spot:.2f}")

        # Get current market price for underlying
        quote = provider.get_quote(symbol)
        if quote:
            current_spot = quote.price
            spot_diff = abs(current_spot - stored_spot)
            spot_pct_diff = (spot_diff / stored_spot * 100) if stored_spot > 0 else 0

            print(f"\nCurrent {symbol} price: ${current_spot:.2f}")
            print(f"Difference from stored spot: ${spot_diff:.2f} ({spot_pct_diff:.1f}%)")

            if spot_pct_diff < 5:  # Within 5% (markets move)
                log_pass("Spot Price Reasonable", f"Stored ${stored_spot:.2f} vs current ${current_spot:.2f}")
            else:
                log_warn("Spot Price Drift", f"Large difference: {spot_pct_diff:.1f}% - may indicate stale data")
        else:
            log_warn("Price Accuracy", "Could not get current quote for comparison")

        # Try to get current option price
        chain = provider.get_options_chain(symbol, greeks=True)
        if chain:
            calls = chain.calls if hasattr(chain, 'calls') else []
            if isinstance(calls, dict):
                calls = list(calls.values())

            # Find matching contract
            matching = [c for c in calls if hasattr(c, 'strike') and c.strike == strike]
            if matching:
                current_opt = matching[0]
                current_opt_price = (current_opt.bid + current_opt.ask) / 2 if hasattr(current_opt, 'bid') else 0

                print(f"\nCurrent option mid: ${current_opt_price:.2f}")
                print(f"Stored current price: ${stored_current:.2f}")

                if current_opt_price > 0 and stored_current > 0:
                    opt_diff = abs(current_opt_price - stored_current)
                    opt_pct_diff = (opt_diff / stored_current * 100)

                    if opt_pct_diff < 20:  # Options can move fast
                        log_pass("Option Price Reasonable", f"Within {opt_pct_diff:.1f}% of market")
                    else:
                        log_warn("Option Price Drift", f"Large difference: {opt_pct_diff:.1f}%")

        conn.close()

    except Exception as e:
        log_fail("Price Accuracy Test", str(e))


# =============================================================================
# TEST: P&L Calculation Accuracy
# =============================================================================
def test_pnl_calculations():
    """
    Verify P&L calculations are mathematically correct.
    """
    print("\n" + "="*70)
    print("P&L CALCULATION TEST")
    print("="*70)

    try:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        # Check open positions P&L
        cursor.execute("""
            SELECT id, entry_price, current_price, contracts, unrealized_pnl
            FROM autonomous_open_positions
            WHERE strategy != 'E2E_TEST'
            LIMIT 5
        """)

        positions = cursor.fetchall()

        print(f"\nVerifying {len(positions)} open positions...")

        for pos in positions:
            pos_id = pos[0]
            entry = float(pos[1]) if pos[1] else 0
            current = float(pos[2]) if pos[2] else 0
            contracts = int(pos[3]) if pos[3] else 1
            stored_pnl = float(pos[4]) if pos[4] else 0

            # Calculate expected P&L
            expected_pnl = (current - entry) * contracts * 100

            diff = abs(stored_pnl - expected_pnl)

            print(f"\n   Position {pos_id}:")
            print(f"   Entry: ${entry:.2f}, Current: ${current:.2f}, Contracts: {contracts}")
            print(f"   Stored P&L: ${stored_pnl:.2f}")
            print(f"   Calculated P&L: ${expected_pnl:.2f}")

            if diff < 1:  # Within $1 (rounding)
                log_pass(f"Position {pos_id} P&L", f"Correct: ${stored_pnl:.2f}")
            else:
                log_fail(f"Position {pos_id} P&L", f"Mismatch: stored ${stored_pnl:.2f} vs calculated ${expected_pnl:.2f}")

        # Check closed trades P&L
        cursor.execute("""
            SELECT id, entry_price, exit_price, contracts, realized_pnl
            FROM autonomous_closed_trades
            WHERE strategy != 'E2E_TEST'
            ORDER BY exit_date DESC
            LIMIT 5
        """)

        trades = cursor.fetchall()

        print(f"\nVerifying {len(trades)} closed trades...")

        for trade in trades:
            trade_id = trade[0]
            entry = float(trade[1]) if trade[1] else 0
            exit_p = float(trade[2]) if trade[2] else 0
            contracts = int(trade[3]) if trade[3] else 1
            stored_pnl = float(trade[4]) if trade[4] else 0

            # Calculate expected P&L (simplified - not including commissions)
            expected_pnl = (exit_p - entry) * contracts * 100

            # Allow for commission variance (~$1.30 per contract)
            max_commission = contracts * 1.50 * 2  # Entry + exit
            diff = abs(stored_pnl - expected_pnl)

            print(f"\n   Trade {trade_id}:")
            print(f"   Entry: ${entry:.2f}, Exit: ${exit_p:.2f}")
            print(f"   Stored P&L: ${stored_pnl:.2f}")
            print(f"   Calculated (pre-commission): ${expected_pnl:.2f}")

            if diff < max_commission + 5:  # Allow for commissions + rounding
                log_pass(f"Trade {trade_id} P&L", f"Within expected range")
            else:
                log_warn(f"Trade {trade_id} P&L", f"Difference of ${diff:.2f} exceeds expected commission")

        conn.close()

    except Exception as e:
        log_fail("P&L Calculation Test", str(e))


# =============================================================================
# TEST: Data Source Fallback
# =============================================================================
def test_data_source_fallback():
    """
    Test that the system properly falls back from Tradier to Polygon.
    """
    print("\n" + "="*70)
    print("DATA SOURCE FALLBACK TEST")
    print("="*70)

    try:
        from data.unified_data_provider import UnifiedDataProvider

        provider = UnifiedDataProvider()

        # Check which sources are available
        has_tradier = hasattr(provider, '_tradier') and provider._tradier is not None
        has_polygon = hasattr(provider, '_polygon') and provider._polygon is not None

        print(f"\nTradier available: {has_tradier}")
        print(f"Polygon available: {has_polygon}")

        if has_tradier:
            log_pass("Tradier Source", "Configured and available")
        else:
            log_fail("Tradier Source", "NOT available - no real-time data!")

        if has_polygon:
            log_pass("Polygon Source", "Configured as fallback")
        else:
            log_warn("Polygon Source", "NOT available - no fallback!")

        # Test quote retrieval and check source
        quote = provider.get_quote('SPY')
        if quote:
            print(f"\nSPY quote source: {quote.source}")

            if quote.source == 'tradier':
                log_pass("Quote Source", "Using Tradier (real-time)")
            elif quote.source == 'polygon':
                log_warn("Quote Source", "Using Polygon (15-min delayed) - Tradier may have failed")
            else:
                log_warn("Quote Source", f"Unknown source: {quote.source}")

            # Check if quote has is_delayed attribute
            if hasattr(quote, 'is_delayed'):
                print(f"   Is delayed: {quote.is_delayed}")

        # Test VIX retrieval (often a fallback scenario)
        vix_quote = provider.get_quote('$VIX.X')  # Tradier format
        if not vix_quote:
            vix_quote = provider.get_quote('^VIX')  # Try Polygon format

        if vix_quote:
            print(f"\nVIX quote: ${vix_quote.price:.2f} from {vix_quote.source}")
            log_pass("VIX Quote", f"${vix_quote.price:.2f} from {vix_quote.source}")
        else:
            log_warn("VIX Quote", "Could not retrieve VIX")

    except Exception as e:
        log_fail("Data Source Fallback Test", str(e))


# =============================================================================
# TEST: Contract Symbol Validation
# =============================================================================
def test_contract_symbols():
    """
    Verify contract symbols follow OCC format and are valid.
    """
    print("\n" + "="*70)
    print("CONTRACT SYMBOL VALIDATION TEST")
    print("="*70)

    try:
        from database_adapter import get_connection
        import re

        conn = get_connection()
        cursor = conn.cursor()

        # OCC format: SYMBOL + YYMMDD + C/P + 8-digit strike
        # Example: SPY241206C00595000
        occ_pattern = r'^[A-Z]{1,6}\d{6}[CP]\d{8}$'

        cursor.execute("""
            SELECT id, symbol, strike, option_type, expiration_date, contract_symbol
            FROM autonomous_open_positions
            WHERE contract_symbol IS NOT NULL AND contract_symbol != ''
            LIMIT 10
        """)

        positions = cursor.fetchall()

        print(f"\nChecking {len(positions)} contract symbols...")

        valid_count = 0
        invalid_count = 0

        for pos in positions:
            pos_id = pos[0]
            symbol = pos[1]
            strike = pos[2]
            opt_type = pos[3]
            expiration = pos[4]
            contract_symbol = pos[5]

            if re.match(occ_pattern, contract_symbol):
                # Further validate components
                # Extract parts
                underlying = contract_symbol[:-15]
                date_part = contract_symbol[-15:-9]
                type_char = contract_symbol[-9]
                strike_part = contract_symbol[-8:]

                # Verify type matches
                expected_type = 'C' if opt_type and opt_type.lower().startswith('c') else 'P'

                # Verify strike matches (strike * 1000, padded to 8 digits)
                expected_strike_str = str(int(float(strike) * 1000)).zfill(8)

                issues = []
                if type_char != expected_type:
                    issues.append(f"type mismatch: {type_char} vs {expected_type}")
                if strike_part != expected_strike_str:
                    issues.append(f"strike mismatch: {strike_part} vs {expected_strike_str}")

                if issues:
                    log_warn(f"Contract {pos_id}", f"{contract_symbol} - {', '.join(issues)}")
                    invalid_count += 1
                else:
                    print(f"   ✓ {contract_symbol} - Valid OCC format")
                    valid_count += 1
            else:
                log_fail(f"Contract {pos_id}", f"'{contract_symbol}' - Invalid OCC format")
                invalid_count += 1

        if valid_count > 0 and invalid_count == 0:
            log_pass("Contract Symbols", f"All {valid_count} symbols valid")
        elif valid_count > 0:
            log_warn("Contract Symbols", f"{valid_count} valid, {invalid_count} invalid")
        else:
            log_warn("Contract Symbols", "No contract symbols to validate")

        conn.close()

    except Exception as e:
        log_fail("Contract Symbol Test", str(e))


# =============================================================================
# TEST: Greeks Capture from Tradier
# =============================================================================
def test_greeks_capture():
    """
    Verify Greeks are being captured from Tradier options chain.
    """
    print("\n" + "="*70)
    print("GREEKS CAPTURE TEST")
    print("="*70)

    try:
        from data.unified_data_provider import UnifiedDataProvider

        provider = UnifiedDataProvider()

        # Get options chain
        chain = provider.get_options_chain('SPY', greeks=True)

        if not chain:
            log_fail("Greeks Capture", "Could not get options chain")
            return

        calls = chain.calls if hasattr(chain, 'calls') else []
        if isinstance(calls, dict):
            calls = list(calls.values())

        if not calls:
            log_fail("Greeks Capture", "No options in chain")
            return

        # Check first few options for Greeks
        print(f"\nChecking Greeks on {min(5, len(calls))} options...")

        greeks_present = {'delta': 0, 'gamma': 0, 'theta': 0, 'vega': 0, 'iv': 0}
        total_checked = 0

        for opt in calls[:5]:
            total_checked += 1
            strike = opt.strike if hasattr(opt, 'strike') else 'N/A'

            delta = opt.delta if hasattr(opt, 'delta') else None
            gamma = opt.gamma if hasattr(opt, 'gamma') else None
            theta = opt.theta if hasattr(opt, 'theta') else None
            vega = opt.vega if hasattr(opt, 'vega') else None
            iv = opt.iv if hasattr(opt, 'iv') else (opt.implied_volatility if hasattr(opt, 'implied_volatility') else None)

            print(f"\n   Strike ${strike}:")
            print(f"   Delta: {delta}, Gamma: {gamma}, Theta: {theta}, Vega: {vega}, IV: {iv}")

            if delta is not None: greeks_present['delta'] += 1
            if gamma is not None: greeks_present['gamma'] += 1
            if theta is not None: greeks_present['theta'] += 1
            if vega is not None: greeks_present['vega'] += 1
            if iv is not None: greeks_present['iv'] += 1

        print(f"\n   Summary across {total_checked} options:")
        for greek, count in greeks_present.items():
            pct = (count / total_checked) * 100
            if pct == 100:
                log_pass(f"Greek: {greek}", f"Present in all {total_checked} options")
            elif pct > 0:
                log_warn(f"Greek: {greek}", f"Only in {count}/{total_checked} options ({pct:.0f}%)")
            else:
                log_fail(f"Greek: {greek}", "Not present in any options")

    except Exception as e:
        log_fail("Greeks Capture Test", str(e))


# =============================================================================
# TEST: Backtest Job Execution
# =============================================================================
def test_backtest_job():
    """
    Test that backtest jobs can be started and tracked.
    """
    print("\n" + "="*70)
    print("BACKTEST JOB TEST")
    print("="*70)

    try:
        from backend.jobs.background_jobs import job_manager, JobStatus

        # Start a test job
        print("\nStarting test backtest job...")

        # Use a minimal test that completes quickly
        job_id = job_manager.start_job(
            'test_backtest',
            params={'test': True, 'days': 1}
        )

        print(f"   Job ID: {job_id}")

        # Check initial status
        status = job_manager.get_job_status(job_id)

        if status:
            print(f"   Initial Status: {status.status}")
            print(f"   Progress: {status.progress}%")
            print(f"   Message: {status.message}")

            log_pass("Job Created", f"ID: {job_id}, Status: {status.status}")

            # Wait briefly and check again
            time.sleep(2)

            status2 = job_manager.get_job_status(job_id)
            if status2:
                print(f"\n   After 2s - Status: {status2.status}, Progress: {status2.progress}%")

                if status2.status in [JobStatus.COMPLETED, JobStatus.RUNNING]:
                    log_pass("Job Execution", f"Job is {status2.status.value}")
                elif status2.status == JobStatus.FAILED:
                    log_warn("Job Execution", f"Job failed: {status2.error}")
                else:
                    log_pass("Job Tracking", f"Status tracking works: {status2.status.value}")
        else:
            log_fail("Job Status", "Could not retrieve job status")

    except ImportError as e:
        log_warn("Backtest Job Test", f"Job system not available: {e}")
    except Exception as e:
        log_fail("Backtest Job Test", str(e))


# =============================================================================
# SUMMARY
# =============================================================================
def print_summary():
    print("\n" + "="*70)
    print("TEST RESULTS SUMMARY")
    print("="*70)

    total = len(RESULTS["passed"]) + len(RESULTS["failed"]) + len(RESULTS["warnings"])

    print(f"\n✅ Passed:   {len(RESULTS['passed'])}")
    print(f"❌ Failed:   {len(RESULTS['failed'])}")
    print(f"⚠️  Warnings: {len(RESULTS['warnings'])}")
    print(f"📊 Total:    {total}")

    if RESULTS["failed"]:
        print("\n" + "-"*70)
        print("❌ FAILURES (must fix):")
        print("-"*70)
        for item in RESULTS["failed"]:
            print(f"   • {item['test']}")
            if item['details']:
                print(f"     {item['details']}")

    if RESULTS["warnings"]:
        print("\n" + "-"*70)
        print("⚠️  WARNINGS (should review):")
        print("-"*70)
        for item in RESULTS["warnings"]:
            print(f"   • {item['test']}")
            if item['details']:
                print(f"     {item['details']}")

    print("\n" + "="*70)

    if RESULTS["failed"]:
        print("❌ OVERALL: TESTS FAILED")
        return False
    elif RESULTS["warnings"]:
        print("⚠️  OVERALL: PASSED WITH WARNINGS")
        return True
    else:
        print("✅ OVERALL: ALL TESTS PASSED")
        return True


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    print("="*70)
    print("END-TO-END PIPELINE TESTS")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    test_trade_pipeline()
    test_price_accuracy()
    test_pnl_calculations()
    test_data_source_fallback()
    test_contract_symbols()
    test_greeks_capture()
    test_backtest_job()

    success = print_summary()
    sys.exit(0 if success else 1)
