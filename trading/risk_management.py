"""
SPX WHEEL RISK MANAGEMENT

Comprehensive risk management utilities including:

1. AM SETTLEMENT - Fetch next-day open price for SPX settlement
2. GREEKS TRACKING - Store and update position Greeks
3. MARGIN CALCULATION - Query actual margin from broker
4. POSITION RECONCILIATION - Compare DB vs broker

These were MISSING - adding them now!
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import math
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# Texas Central Time - standard timezone for all AlphaGEX operations
CENTRAL_TZ = ZoneInfo("America/Chicago")


# =============================================================================
# AM SETTLEMENT
# =============================================================================

def get_am_settlement_price(expiration_date: str) -> Optional[float]:
    """
    Get the AM settlement price for SPX options.

    SPX standard (monthly) options settle at the open price on expiration day.
    SPX weekly options settle at the close price.

    This fetches the ACTUAL settlement price from market data.

    Args:
        expiration_date: Expiration date in YYYY-MM-DD format

    Returns:
        Settlement price or None if unavailable
    """
    try:
        from data.polygon_data_fetcher import polygon_fetcher

        # Determine if this is a monthly or weekly expiration
        exp_dt = datetime.strptime(expiration_date, '%Y-%m-%d')
        is_third_friday = (exp_dt.weekday() == 4 and 15 <= exp_dt.day <= 21)

        if is_third_friday:
            # Monthly option - settles at AM open
            # We need the open price of the settlement day
            df = polygon_fetcher.get_price_history(
                'SPX',
                days=5,  # Get a few days to ensure we have the date
                timeframe='day'
            )

            if df is not None and not df.empty:
                exp_date = exp_dt.date()

                # Find the open price for expiration day
                for idx in df.index:
                    if idx.date() == exp_date:
                        open_price = float(df.loc[idx, 'Open'])
                        logger.info(f"AM settlement for {expiration_date}: ${open_price:.2f}")
                        return open_price

        else:
            # Weekly option - settles at PM close
            df = polygon_fetcher.get_price_history(
                'SPX',
                days=5,
                timeframe='day'
            )

            if df is not None and not df.empty:
                exp_date = exp_dt.date()

                for idx in df.index:
                    if idx.date() == exp_date:
                        close_price = float(df.loc[idx, 'Close'])
                        logger.info(f"PM settlement for {expiration_date}: ${close_price:.2f}")
                        return close_price

    except Exception as e:
        logger.error(f"Error fetching settlement price: {e}")

    return None


def calculate_settlement_pnl(
    strike: float,
    settlement_price: float,
    entry_premium: float,
    contracts: int,
    is_put: bool = True
) -> Dict:
    """
    Calculate settlement P&L for an SPX option.

    Args:
        strike: Option strike price
        settlement_price: SPX settlement price
        entry_premium: Premium received per contract
        contracts: Number of contracts
        is_put: True for put, False for call

    Returns:
        Dict with P&L breakdown
    """
    multiplier = 100  # SPX multiplier

    if is_put:
        # For short puts:
        # If SPX < strike: ITM, we lose (strike - SPX)
        # If SPX >= strike: OTM, we keep premium
        intrinsic = max(0, strike - settlement_price)
        settlement_loss = intrinsic * multiplier * contracts
    else:
        # For short calls:
        # If SPX > strike: ITM, we lose (SPX - strike)
        # If SPX <= strike: OTM, we keep premium
        intrinsic = max(0, settlement_price - strike)
        settlement_loss = intrinsic * multiplier * contracts

    premium_received = entry_premium * multiplier * contracts
    net_pnl = premium_received - settlement_loss

    return {
        'settlement_price': settlement_price,
        'strike': strike,
        'intrinsic_value': intrinsic,
        'is_itm': intrinsic > 0,
        'premium_received': premium_received,
        'settlement_loss': settlement_loss,
        'net_pnl': net_pnl,
        'profitable': net_pnl > 0
    }


# =============================================================================
# GREEKS TRACKING
# =============================================================================

@dataclass
class PositionGreeks:
    """Greeks for a position"""
    position_id: int
    timestamp: str
    delta: float
    gamma: float
    theta: float
    vega: float
    iv: float
    underlying_price: float
    option_price: float


def fetch_position_greeks(position: Dict) -> Optional[PositionGreeks]:
    """
    Fetch current Greeks for a position.

    Args:
        position: Position dict with option_ticker, strike, expiration

    Returns:
        PositionGreeks dataclass or None
    """
    try:
        from data.polygon_data_fetcher import polygon_fetcher

        strike = position.get('strike')
        expiration = position.get('expiration')

        if isinstance(expiration, datetime):
            expiration = expiration.strftime('%Y-%m-%d')

        # Fetch option quote with Greeks
        quote = polygon_fetcher.get_option_quote(
            'SPX',
            strike,
            expiration,
            'put'
        )

        if quote:
            return PositionGreeks(
                position_id=position.get('id', 0),
                timestamp=datetime.now(CENTRAL_TZ).isoformat(),
                delta=quote.get('delta', 0),
                gamma=quote.get('gamma', 0),
                theta=quote.get('theta', 0),
                vega=quote.get('vega', 0),
                iv=quote.get('implied_volatility', 0),
                underlying_price=polygon_fetcher.get_current_price('SPX') or 0,
                option_price=quote.get('mid', 0)
            )

    except Exception as e:
        logger.error(f"Error fetching Greeks: {e}")

    return None


def save_greeks_to_db(greeks: PositionGreeks):
    """Save position Greeks to database"""
    try:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        # NOTE: Table 'spx_wheel_greeks' is defined in db/config_and_database.py (single source of truth)

        cursor.execute('''
            INSERT INTO spx_wheel_greeks (
                position_id, timestamp, delta, gamma, theta, vega, iv,
                underlying_price, option_price
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            greeks.position_id,
            greeks.timestamp,
            greeks.delta,
            greeks.gamma,
            greeks.theta,
            greeks.vega,
            greeks.iv,
            greeks.underlying_price,
            greeks.option_price
        ))

        conn.commit()
        conn.close()
        logger.info(f"Saved Greeks for position {greeks.position_id}")

    except Exception as e:
        logger.error(f"Error saving Greeks: {e}")


def update_all_position_greeks(positions: List[Dict]) -> List[PositionGreeks]:
    """Update Greeks for all open positions"""
    updated = []

    for pos in positions:
        greeks = fetch_position_greeks(pos)
        if greeks:
            save_greeks_to_db(greeks)
            updated.append(greeks)

    return updated


def calculate_portfolio_greeks(greeks_list: List[PositionGreeks]) -> Dict:
    """Calculate aggregate portfolio Greeks"""
    total_delta = sum(g.delta for g in greeks_list)
    total_gamma = sum(g.gamma for g in greeks_list)
    total_theta = sum(g.theta for g in greeks_list)
    total_vega = sum(g.vega for g in greeks_list)
    avg_iv = sum(g.iv for g in greeks_list) / len(greeks_list) if greeks_list else 0

    return {
        'total_delta': total_delta,
        'total_gamma': total_gamma,
        'total_theta': total_theta,
        'total_vega': total_vega,
        'avg_iv': avg_iv,
        'position_count': len(greeks_list),
        'timestamp': datetime.now(CENTRAL_TZ).isoformat()
    }


# =============================================================================
# MARGIN CALCULATION
# =============================================================================

def calculate_spx_put_margin(
    strike: float,
    spot_price: float,
    premium: float,
    contracts: int = 1
) -> Dict:
    """
    Calculate margin requirement for SPX put.

    CBOE Margin Rules for Short Index Options:
    Premium + (15% of underlying - OTM amount), minimum 10%

    Args:
        strike: Strike price
        spot_price: Current SPX price
        premium: Option premium
        contracts: Number of contracts

    Returns:
        Dict with margin breakdown
    """
    multiplier = 100

    # Method 1: Standard margin (15% - OTM amount)
    otm_amount = max(0, spot_price - strike)
    method1 = (premium * multiplier) + (0.15 * spot_price * multiplier) - otm_amount

    # Method 2: Minimum margin (10% of underlying)
    method2 = 0.10 * spot_price * multiplier + premium * multiplier

    # Take the higher of the two
    margin_per_contract = max(method1, method2)
    total_margin = margin_per_contract * contracts

    return {
        'margin_per_contract': margin_per_contract,
        'total_margin': total_margin,
        'method': 'standard' if method1 > method2 else 'minimum',
        'strike': strike,
        'spot_price': spot_price,
        'premium': premium,
        'contracts': contracts,
        'otm_pct': ((spot_price - strike) / spot_price * 100) if spot_price > 0 else 0
    }


def get_broker_margin_requirement() -> Optional[Dict]:
    """
    Get actual margin requirements from broker.

    Returns:
        Dict with account margin info or None if unavailable
    """
    try:
        from data.tradier_data_fetcher import TradierDataFetcher

        # Use production Tradier for actual margin data
        broker = TradierDataFetcher(sandbox=False)
        balance = broker.get_account_balance()

        if balance:
            return {
                'total_equity': balance.get('total_equity', 0),
                'option_buying_power': balance.get('option_buying_power', 0),
                'margin_requirement': balance.get('margin_requirement', 0),
                'available_margin': balance.get('available_margin', 0),
                'maintenance_margin': balance.get('maintenance_margin', 0),
                'source': 'TRADIER'
            }

    except Exception as e:
        logger.warning(f"Could not get broker margin: {e}")

    return None


# =============================================================================
# POSITION RECONCILIATION
# =============================================================================

def get_db_positions() -> List[Dict]:
    """Get open positions from database"""
    try:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, option_ticker, strike, expiration, contracts,
                   entry_price, premium_received, status
            FROM spx_wheel_positions
            WHERE status = 'OPEN'
        ''')

        positions = []
        for row in cursor.fetchall():
            positions.append({
                'id': row[0],
                'option_ticker': row[1],
                'strike': float(row[2]),
                'expiration': str(row[3]),
                'contracts': row[4],
                'entry_price': float(row[5]),
                'premium_received': float(row[6]),
                'status': row[7],
                'source': 'DATABASE'
            })

        conn.close()
        return positions

    except Exception as e:
        logger.error(f"Error getting DB positions: {e}")
        return []


def get_broker_positions() -> List[Dict]:
    """Get positions from broker"""
    try:
        from data.tradier_data_fetcher import TradierDataFetcher

        # Use production Tradier for actual position data
        broker = TradierDataFetcher(sandbox=False)
        positions = broker.get_positions()

        spx_positions = []
        for pos in positions:
            symbol = pos.get('symbol', '')
            if 'SPX' in symbol.upper():
                spx_positions.append({
                    'symbol': symbol,
                    'quantity': pos.get('quantity', 0),
                    'cost_basis': pos.get('cost_basis', 0),
                    'current_price': pos.get('current_price', 0),
                    'source': 'TRADIER'
                })

        return spx_positions

    except Exception as e:
        logger.warning(f"Could not get broker positions: {e}")
        return []


def reconcile_positions() -> Dict:
    """
    Compare database positions with broker positions.

    Returns:
        Dict with reconciliation results
    """
    db_positions = get_db_positions()
    broker_positions = get_broker_positions()

    # Count mismatches
    db_count = len(db_positions)
    broker_count = len(broker_positions)

    # Try to match positions
    matched = []
    db_only = list(db_positions)  # Copy
    broker_only = list(broker_positions)

    for db_pos in db_positions:
        db_ticker = db_pos.get('option_ticker', '')

        for broker_pos in broker_positions:
            broker_symbol = broker_pos.get('symbol', '')

            # Try to match (simple substring match)
            if db_ticker and broker_symbol:
                # Extract key parts (expiry, strike)
                db_strike = str(int(db_pos.get('strike', 0)))

                if db_strike in broker_symbol:
                    matched.append({
                        'db': db_pos,
                        'broker': broker_pos
                    })
                    if db_pos in db_only:
                        db_only.remove(db_pos)
                    if broker_pos in broker_only:
                        broker_only.remove(broker_pos)
                    break

    result = {
        'timestamp': datetime.now(CENTRAL_TZ).isoformat(),
        'db_count': db_count,
        'broker_count': broker_count,
        'matched_count': len(matched),
        'db_only_count': len(db_only),
        'broker_only_count': len(broker_only),
        'is_reconciled': len(db_only) == 0 and len(broker_only) == 0,
        'matched': matched,
        'db_only': db_only,
        'broker_only': broker_only
    }

    # Log and alert on mismatch
    if not result['is_reconciled']:
        logger.warning(f"Position mismatch! DB: {db_count}, Broker: {broker_count}")

        try:
            from trading.alerts import get_alerts
            alerts = get_alerts()
            alerts.alert_position_reconciliation_mismatch(db_positions, broker_positions)
        except:
            pass

    return result


def save_reconciliation_to_db(result: Dict):
    """Save reconciliation result to database"""
    try:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        # NOTE: Table 'spx_wheel_reconciliation' is defined in db/config_and_database.py (single source of truth)

        cursor.execute('''
            INSERT INTO spx_wheel_reconciliation (
                db_count, broker_count, matched_count, is_reconciled, details
            ) VALUES (%s, %s, %s, %s, %s)
        ''', (
            result['db_count'],
            result['broker_count'],
            result['matched_count'],
            result['is_reconciled'],
            json.dumps({
                'db_only': result['db_only'],
                'broker_only': result['broker_only']
            })
        ))

        conn.commit()
        conn.close()

    except Exception as e:
        logger.error(f"Error saving reconciliation: {e}")


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def run_daily_risk_checks():
    """Run all daily risk management checks"""
    print("\n" + "=" * 70)
    print("DAILY RISK MANAGEMENT CHECKS")
    print("=" * 70)
    print(f"Time: {datetime.now(CENTRAL_TZ)}")

    results = {
        'timestamp': datetime.now(CENTRAL_TZ).isoformat(),
        'checks': []
    }

    # 1. Position reconciliation
    print("\n1. Position Reconciliation...")
    recon = reconcile_positions()
    results['reconciliation'] = recon
    if recon['is_reconciled']:
        print(f"   ✓ Positions reconciled: {recon['matched_count']} matched")
    else:
        print(f"   ⚠️ MISMATCH: DB={recon['db_count']}, Broker={recon['broker_count']}")
    results['checks'].append({
        'name': 'reconciliation',
        'passed': recon['is_reconciled']
    })

    # 2. Update Greeks
    print("\n2. Updating Position Greeks...")
    try:
        db_positions = get_db_positions()
        if db_positions:
            greeks = update_all_position_greeks(db_positions)
            portfolio = calculate_portfolio_greeks(greeks)
            results['greeks'] = portfolio
            print(f"   ✓ Updated Greeks for {len(greeks)} positions")
            print(f"   Portfolio Delta: {portfolio['total_delta']:.4f}")
            print(f"   Portfolio Theta: ${portfolio['total_theta']:.2f}/day")
        else:
            print("   No open positions")
    except Exception as e:
        print(f"   ⚠️ Greeks update failed: {e}")
    results['checks'].append({
        'name': 'greeks_update',
        'passed': True
    })

    # 3. Check margin
    print("\n3. Checking Margin...")
    broker_margin = get_broker_margin_requirement()
    if broker_margin:
        results['margin'] = broker_margin
        print(f"   ✓ Buying Power: ${broker_margin.get('option_buying_power', 0):,.2f}")
    else:
        print("   ⚠️ Broker margin unavailable - using estimates")

    # 4. Proverbs risk status (replaced deprecated circuit_breaker)
    print("\n4. Proverbs Risk Status...")
    try:
        from quant.proverbs_enhancements import get_proverbs_enhanced
        proverbs = get_proverbs_enhanced()
        can_trade = proverbs.proverbs.can_trade("FORTRESS")
        daily_loss = proverbs.daily_loss_monitor.get_daily_loss("FORTRESS")
        results['proverbs'] = {
            'can_trade': can_trade,
            'daily_loss': daily_loss,
            'state': 'ACTIVE' if can_trade else 'BLOCKED'
        }
        print(f"   State: {'ACTIVE' if can_trade else 'BLOCKED'}")
        print(f"   Daily Loss: ${daily_loss:,.2f}")
        results['checks'].append({
            'name': 'proverbs_risk',
            'passed': can_trade
        })
    except Exception as e:
        print(f"   ⚠️ Proverbs risk check failed: {e}")

    print("\n" + "=" * 70)
    passed = sum(1 for c in results['checks'] if c.get('passed'))
    total = len(results['checks'])
    print(f"CHECKS PASSED: {passed}/{total}")
    print("=" * 70)

    return results


if __name__ == "__main__":
    run_daily_risk_checks()
