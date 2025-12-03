"""
Position Sizer Mixin - Kelly Criterion Position Sizing

This module handles all position sizing calculations including:
- Kelly criterion calculations from backtest data
- Available capital tracking
- Strategy stats lookup for win rates
- Backtest validation for patterns
- VIX-based stress adjustments
- Confidence-based scaling
"""

import pandas as pd
import logging
from typing import Dict, Tuple
from database_adapter import get_connection

logger = logging.getLogger('autonomous_paper_trader.position_sizer')

# Import strategy stats if available
try:
    from core.strategy_stats import get_strategy_stats
    STRATEGY_STATS_AVAILABLE = True
except ImportError:
    STRATEGY_STATS_AVAILABLE = False
    logger.warning("Strategy Stats not available for position sizing")


class PositionSizerMixin:
    """
    Mixin class providing position sizing functionality.

    Requires the following attributes from the main class:
    - get_config(key): Method to get configuration values
    - _get_vix(): Method to get current VIX
    """

    def get_backtest_validation_for_pattern(self, pattern: str, min_trades: int = 5) -> Dict:
        """
        Get backtest validation for a pattern from historical backtest results.

        Similar to SPX institutional trader - uses backtest data to validate pattern.

        Args:
            pattern: The strategy/pattern name
            min_trades: Minimum trades required to consider "validated"

        Returns:
            {
                'is_validated': bool,
                'win_rate': float,
                'expectancy': float,
                'total_trades': int,
                'should_trade': bool,
                'reason': str,
                'source': str  # 'backtest' or 'live_trades' or 'none'
            }
        """
        conn = get_connection()
        c = conn.cursor()

        result = {
            'is_validated': False,
            'win_rate': 0.0,
            'expectancy': 0.0,
            'total_trades': 0,
            'should_trade': True,  # Default to allowing trade
            'reason': 'No historical data',
            'source': 'none'
        }

        try:
            # FIRST: Check backtest_results table for historical validation
            c.execute("""
                SELECT
                    strategy_name, total_trades, winning_trades,
                    win_rate, expectancy_pct, sharpe_ratio
                FROM backtest_results
                WHERE LOWER(strategy_name) LIKE LOWER(%s)
                ORDER BY timestamp DESC
                LIMIT 1
            """, (f'%{pattern}%',))

            row = c.fetchone()

            if row:
                result['source'] = 'backtest'
                result['total_trades'] = row[1] or 0
                result['win_rate'] = float(row[3]) if row[3] else 0.0
                result['expectancy'] = float(row[4]) if row[4] else 0.0

                if result['total_trades'] >= min_trades:
                    result['is_validated'] = True

                    # Check if pattern has positive expectancy
                    if result['expectancy'] < 0.0:  # MUST have non-negative expectancy
                        result['should_trade'] = False
                        result['reason'] = f"BLOCKED: Negative expectancy ({result['expectancy']:.1f}%)"
                    elif result['win_rate'] < 40.0:  # Win rate threshold
                        result['should_trade'] = False
                        result['reason'] = f"BLOCKED: Win rate too low ({result['win_rate']:.0f}% < 40%)"
                    else:
                        result['reason'] = f"Validated: {result['total_trades']} trades, {result['win_rate']:.0f}% win rate, {result['expectancy']:.1f}% expectancy"
                else:
                    result['reason'] = f"Insufficient data: only {result['total_trades']} trades (need {min_trades})"

                conn.close()
                return result

            # SECOND: Fall back to live trading results
            c.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                    AVG(realized_pnl_pct) as expectancy
                FROM autonomous_closed_trades
                WHERE LOWER(strategy) LIKE LOWER(%s)
            """, (f'%{pattern}%',))

            row = c.fetchone()

            if row and row[0] and row[0] > 0:
                result['source'] = 'live_trades'
                result['total_trades'] = row[0]
                result['win_rate'] = (row[1] / row[0] * 100) if row[0] > 0 else 0
                result['expectancy'] = float(row[2]) if row[2] else 0.0

                if result['total_trades'] >= min_trades:
                    result['is_validated'] = True

                    if result['expectancy'] < 0.0:
                        result['should_trade'] = False
                        result['reason'] = f"BLOCKED: Live trades show negative expectancy ({result['expectancy']:.1f}%)"
                    elif result['win_rate'] < 40.0:
                        result['should_trade'] = False
                        result['reason'] = f"BLOCKED: Live win rate too low ({result['win_rate']:.0f}% < 40%)"
                    else:
                        result['reason'] = f"Live validated: {result['total_trades']} trades, {result['win_rate']:.0f}% win rate, {result['expectancy']:.1f}% expectancy"
                else:
                    result['reason'] = f"Limited live data: {result['total_trades']} trades"

        except Exception as e:
            logger.warning(f"Error getting backtest validation for {pattern}: {e}")
            result['reason'] = f"Error querying history: {str(e)}"
        finally:
            conn.close()

        return result

    def get_strategy_stats_for_pattern(self, pattern: str) -> Dict:
        """
        Get strategy stats from centralized strategy_stats.json for Kelly position sizing.

        This connects the trader to the unified backtester system:
        1. Reads from strategy_stats.json (updated by backtests)
        2. Provides win rate, avg win/loss for Kelly calculation
        3. Enables backtest-informed position sizing

        Args:
            pattern: Strategy/pattern name to look up

        Returns:
            Dict with win_rate, avg_win, avg_loss, is_proven, source
        """
        if not STRATEGY_STATS_AVAILABLE:
            logger.debug(f"Strategy stats not available, using defaults for {pattern}")
            return {
                'win_rate': 0.55,
                'avg_win': 8.0,
                'avg_loss': 12.0,
                'expectancy': 0.0,
                'total_trades': 0,
                'is_proven': False,
                'source': 'default'
            }

        try:
            all_stats = get_strategy_stats()

            # Try exact match first
            pattern_upper = pattern.upper().replace(' ', '_')
            if pattern_upper in all_stats:
                stats = all_stats[pattern_upper]
                # Check for 0.0 values and use safe defaults
                avg_win = stats.get('avg_win', 0.0)
                avg_loss = stats.get('avg_loss', 0.0)
                if avg_win <= 0:
                    avg_win = 8.0  # Conservative default
                if avg_loss <= 0:
                    avg_loss = 12.0  # Conservative default
                return {
                    'win_rate': stats.get('win_rate', 0.55),
                    'avg_win': abs(avg_win),
                    'avg_loss': abs(avg_loss),
                    'expectancy': stats.get('expectancy', 0.0),
                    'total_trades': stats.get('total_trades', 0),
                    'is_proven': stats.get('total_trades', 0) >= 10,
                    'source': stats.get('source', 'backtest')
                }

            # Try fuzzy match
            for name, stats in all_stats.items():
                if pattern_upper in name or name in pattern_upper:
                    avg_win = stats.get('avg_win', 0.0)
                    avg_loss = stats.get('avg_loss', 0.0)
                    if avg_win <= 0:
                        avg_win = 8.0
                    if avg_loss <= 0:
                        avg_loss = 12.0
                    return {
                        'win_rate': stats.get('win_rate', 0.55),
                        'avg_win': abs(avg_win),
                        'avg_loss': abs(avg_loss),
                        'expectancy': stats.get('expectancy', 0.0),
                        'total_trades': stats.get('total_trades', 0),
                        'is_proven': stats.get('total_trades', 0) >= 10,
                        'source': stats.get('source', 'backtest')
                    }

            # No match - return conservative defaults
            logger.debug(f"No strategy_stats match for {pattern}, using defaults")
            return {
                'win_rate': 0.55,
                'avg_win': 8.0,
                'avg_loss': 12.0,
                'expectancy': 0.0,
                'total_trades': 0,
                'is_proven': False,
                'source': 'default'
            }

        except Exception as e:
            logger.warning(f"Error getting strategy stats for {pattern}: {e}")
            return {
                'win_rate': 0.55,
                'avg_win': 8.0,
                'avg_loss': 12.0,
                'expectancy': 0.0,
                'total_trades': 0,
                'is_proven': False,
                'source': 'error'
            }

    def calculate_kelly_position_size(
        self,
        strategy_name: str,
        entry_price: float,
        confidence: int = 70
    ) -> Tuple[int, Dict]:
        """
        Calculate position size using Kelly Criterion from backtest data.

        ENHANCED with Monte Carlo stress testing for safe Kelly sizing.

        This mirrors the SPX trader's Kelly-based sizing:
        1. Look up backtest stats for strategy
        2. Calculate Kelly fraction
        3. Run Monte Carlo stress test to find SAFE Kelly (not just optimal)
        4. Apply adjustments (half-Kelly for proven, quarter-Kelly for unproven)
        5. Return contracts and sizing details

        Args:
            strategy_name: Name of strategy for backtest lookup
            entry_price: Option entry price
            confidence: Trade confidence (0-100)

        Returns:
            (contracts, sizing_details)
        """
        # Get available capital
        available = self.get_available_capital()
        total_capital = float(self.get_config('capital'))

        # Get backtest params
        params = self.get_strategy_stats_for_pattern(strategy_name)
        win_rate = params['win_rate']
        avg_win = params['avg_win']
        avg_loss = params['avg_loss']
        is_proven = params['is_proven']
        sample_size = params.get('total_trades', 20)

        # Calculate Kelly
        if avg_loss <= 0:
            avg_loss = 12.0  # Conservative default
        risk_reward = avg_win / avg_loss

        # Kelly formula: W - (1-W)/R
        # CRITICAL: Negative Kelly means negative expected value - DO NOT TRADE
        if risk_reward <= 0:
            kelly = -1.0  # Invalid setup
            logger.warning(f"Invalid risk/reward ratio ({risk_reward:.2f}) - blocking trade")
        else:
            kelly = win_rate - ((1 - win_rate) / risk_reward)

        # ========================================================================
        # MONTE CARLO STRESS TEST (NEW - validates Kelly is actually safe)
        # ========================================================================
        mc_safe_kelly = None
        mc_prob_ruin = None
        mc_uncertainty = 'unknown'

        try:
            from quant.monte_carlo_kelly import get_safe_position_size
            mc_result = get_safe_position_size(
                win_rate=win_rate,
                avg_win=avg_win,
                avg_loss=avg_loss,
                sample_size=sample_size,
                account_size=total_capital,
                max_risk_pct=20.0
            )
            mc_safe_kelly = mc_result['kelly_safe'] / 100  # Convert from % to decimal
            mc_prob_ruin = mc_result['prob_ruin']
            mc_uncertainty = mc_result['uncertainty_level']

            # Use SAFE Kelly instead of optimal if available
            if mc_safe_kelly is not None and mc_safe_kelly > 0:
                # Cap raw kelly at safe kelly from Monte Carlo
                if kelly > mc_safe_kelly:
                    logger.warning(f"Monte Carlo: Capping Kelly from {kelly:.2%} to safe {mc_safe_kelly:.2%} "
                                 f"(prob_ruin={mc_prob_ruin:.1f}%, uncertainty={mc_uncertainty})")
                    kelly = mc_safe_kelly

            logger.info(f"Monte Carlo validation: optimal={mc_result['kelly_optimal']:.1f}%, "
                       f"safe={mc_result['kelly_safe']:.1f}%, prob_ruin={mc_prob_ruin:.1f}%")

        except ImportError:
            logger.debug("Monte Carlo Kelly not available - using standard Kelly")
        except Exception as e:
            logger.warning(f"Monte Carlo Kelly failed: {e} - using standard Kelly")

        # If Kelly is negative, expected value is negative - DO NOT TRADE
        if kelly <= 0:
            logger.warning(f"Kelly criterion negative ({kelly:.2%}) for {strategy_name} - "
                          f"WR={win_rate:.0%}, R/R={risk_reward:.2f} - BLOCKING TRADE")
            return 0, {
                'methodology': 'Kelly-Backtest-VIX (SPY)',
                'blocked': True,
                'block_reason': f'Negative Kelly ({kelly:.2%}) indicates negative expected value',
                'raw_kelly': kelly,
                'win_rate': win_rate,
                'risk_reward': risk_reward,
                'final_contracts': 0
            }

        # Apply Kelly fraction based on proven status
        if is_proven:
            base_kelly_fraction = 0.5  # Half-Kelly for proven
            adjustment_type = 'half-kelly'
        else:
            base_kelly_fraction = 0.25  # Quarter-Kelly for unproven
            adjustment_type = 'quarter-kelly'

        # REGIME CONFIDENCE ADJUSTMENT
        # High confidence (>=80%): Full Kelly fraction (1.0x)
        # Medium confidence (60-80%): 75% of Kelly fraction
        # Low confidence (<60%): 50% of Kelly fraction
        if confidence >= 80:
            confidence_factor = 1.0
            confidence_level = 'high'
        elif confidence >= 60:
            confidence_factor = 0.75
            confidence_level = 'medium'
        else:
            confidence_factor = 0.5
            confidence_level = 'low'

        # Apply confidence to base Kelly fraction
        adjusted_kelly = kelly * base_kelly_fraction * confidence_factor

        logger.info(f"Kelly confidence scaling: {confidence}% confidence ({confidence_level}) -> "
                   f"{adjustment_type} * {confidence_factor} = {adjusted_kelly:.2%}")

        # Cap Kelly at 20% for SPY (more conservative than SPX)
        # Minimum is 0.5% for very conservative plays
        final_kelly = max(0.005, min(0.20, adjusted_kelly))

        # Calculate position value
        max_position_value = available * final_kelly

        # VIX STRESS FACTOR: Real-time VIX-based position reduction
        # Trader VIX thresholds (22/28/35) are MORE CONSERVATIVE than
        # config thresholds (20/30/40). This is INTENTIONAL.
        current_vix = self._get_vix()
        vix_stress_factor = 1.0
        vix_stress_level = 'normal'

        if current_vix >= 35:
            vix_stress_factor = 0.25  # 75% reduction - extreme fear
            vix_stress_level = 'extreme'
            logger.warning(f"VIX EXTREME ({current_vix:.1f}): Position size reduced by 75%")
        elif current_vix >= 28:
            vix_stress_factor = 0.50  # 50% reduction - high stress
            vix_stress_level = 'high'
            logger.warning(f"VIX HIGH ({current_vix:.1f}): Position size reduced by 50%")
        elif current_vix >= 22:
            vix_stress_factor = 0.75  # 25% reduction - elevated
            vix_stress_level = 'elevated'
            logger.info(f"VIX ELEVATED ({current_vix:.1f}): Position size reduced by 25%")
        else:
            vix_stress_level = 'normal'
            logger.info(f"VIX NORMAL ({current_vix:.1f}): Standard position sizing")

        # Apply VIX stress
        position_value = max_position_value * vix_stress_factor

        # Cap at 25% of capital per position (SPY risk limit)
        position_value = min(position_value, total_capital * 0.25)

        # Calculate contracts
        cost_per_contract = entry_price * 100
        if cost_per_contract <= 0:
            contracts = 0
            raw_contracts = 0
        else:
            raw_contracts = int(position_value / cost_per_contract)
            # Cap at 10 contracts for SPY (liquidity constraint)
            contracts = min(raw_contracts, 10)

        sizing_details = {
            'methodology': 'Kelly-Backtest-MonteCarlo-VIX (SPY)',
            'available_capital': available,
            'kelly_pct': final_kelly * 100,
            'raw_kelly': kelly,
            'adjusted_kelly': adjusted_kelly,
            'adjustment_type': adjustment_type,
            'confidence': confidence,
            'confidence_level': confidence_level,
            'confidence_factor': confidence_factor,
            'vix_stress_factor': vix_stress_factor,
            'vix_stress_level': vix_stress_level,
            'current_vix': current_vix,
            'max_position_value': max_position_value,
            'final_position_value': position_value,
            'cost_per_contract': cost_per_contract,
            'raw_contracts': raw_contracts,
            'final_contracts': contracts,
            'backtest_params': params,
            # Monte Carlo stress test results (NEW)
            'monte_carlo': {
                'safe_kelly_pct': mc_safe_kelly * 100 if mc_safe_kelly else None,
                'prob_ruin_pct': mc_prob_ruin,
                'uncertainty_level': mc_uncertainty,
                'stress_tested': mc_safe_kelly is not None
            }
        }

        logger.info(f"Kelly sizing for {strategy_name}: {contracts} contracts "
                   f"(Kelly={final_kelly:.1%}, {adjustment_type}, "
                   f"WR={win_rate:.0%}, proven={is_proven})")

        return contracts, sizing_details

    def get_available_capital(self) -> float:
        """Calculate available capital (total minus positions in use)"""
        total_capital = float(self.get_config('capital'))

        # Get current open positions value
        conn = get_connection()
        query = """
            SELECT SUM(ABS(entry_price * contracts * 100)) as used
            FROM autonomous_open_positions
        """
        result = pd.read_sql_query(query, conn)
        conn.close()

        used = result.iloc[0]['used'] if not pd.isna(result.iloc[0]['used']) else 0
        return total_capital - used

    def is_signal_only_mode(self) -> bool:
        """Check if signal-only mode is enabled (no auto-execution)"""
        return self.get_config('signal_only') == 'true'

    def set_signal_only_mode(self, enabled: bool):
        """Enable or disable signal-only mode"""
        conn = get_connection()
        c = conn.cursor()
        c.execute("UPDATE autonomous_config SET value = %s WHERE key = 'signal_only'",
                  ('true' if enabled else 'false',))
        conn.commit()
        conn.close()
        print(f"Signal-only mode {'enabled' if enabled else 'disabled'}")

    def is_theoretical_pricing_enabled(self) -> bool:
        """Check if Black-Scholes theoretical pricing is enabled for delayed data"""
        return self.get_config('use_theoretical_pricing') == 'true'

    def set_theoretical_pricing(self, enabled: bool):
        """Enable or disable Black-Scholes theoretical pricing for delayed data"""
        conn = get_connection()
        c = conn.cursor()
        # Ensure the key exists first
        c.execute("SELECT value FROM autonomous_config WHERE key = 'use_theoretical_pricing'")
        if not c.fetchone():
            c.execute("INSERT INTO autonomous_config (key, value) VALUES ('use_theoretical_pricing', %s)",
                      ('true' if enabled else 'false',))
        else:
            c.execute("UPDATE autonomous_config SET value = %s WHERE key = 'use_theoretical_pricing'",
                      ('true' if enabled else 'false',))
        conn.commit()
        conn.close()
        status = 'ENABLED' if enabled else 'DISABLED'
        print(f"{status} Black-Scholes theoretical pricing for delayed option data")
