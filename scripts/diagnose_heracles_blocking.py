#!/usr/bin/env python3
"""
HERACLES Signal Blocking Diagnostic

This script checks ALL conditions that could prevent HERACLES from generating trades:
1. GEX data availability (flip_point > 0)
2. Loss streak pause
3. Direction tracker cooldown
4. Win probability threshold
5. Signal generation logic

Run on Render console:
  python /opt/render/project/src/scripts/diagnose_heracles_blocking.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Also try Render path
sys.path.insert(0, '/opt/render/project/src')

from datetime import datetime
import pytz

CENTRAL_TZ = pytz.timezone('America/Chicago')


def diagnose():
    """Run full diagnostic on HERACLES signal blocking."""
    print("=" * 70)
    print("HERACLES SIGNAL BLOCKING DIAGNOSTIC")
    print("=" * 70)

    now = datetime.now(CENTRAL_TZ)
    print(f"\nTime (CT): {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Hour: {now.hour}")

    # =========================================================================
    # CHECK 1: GEX Data
    # =========================================================================
    print("\n" + "=" * 70)
    print("CHECK 1: GEX Data Availability")
    print("=" * 70)

    try:
        from trading.heracles.signals import get_gex_data_for_heracles
        gex_data = get_gex_data_for_heracles("SPX")

        flip_point = gex_data.get('flip_point', 0)
        net_gex = gex_data.get('net_gex', 0)
        data_source = gex_data.get('data_source', 'unknown')

        print(f"  flip_point: {flip_point}")
        print(f"  net_gex: {net_gex:.2e}")
        print(f"  data_source: {data_source}")

        if flip_point > 0:
            print("  [PASS] Valid GEX data available")
        else:
            print("  [BLOCKING] flip_point <= 0 - No valid GEX data!")
            print("  HERACLES will SKIP all signals when flip_point is 0")
            return

        gamma_regime = "POSITIVE" if net_gex > 0 else "NEGATIVE" if net_gex < 0 else "NEUTRAL"
        print(f"  gamma_regime: {gamma_regime}")

    except Exception as e:
        print(f"  [ERROR] Failed to get GEX data: {e}")
        return

    # =========================================================================
    # CHECK 2: Trader State (Loss Streak, Consecutive Losses)
    # =========================================================================
    print("\n" + "=" * 70)
    print("CHECK 2: Trader State (Loss Streak)")
    print("=" * 70)

    try:
        from trading.heracles.trader import get_heracles_trader
        trader = get_heracles_trader()

        consecutive_losses = trader.consecutive_losses
        loss_streak_pause = trader.loss_streak_pause_until
        max_losses = trader.config.max_consecutive_losses
        pause_minutes = trader.config.loss_streak_pause_minutes

        print(f"  consecutive_losses: {consecutive_losses}")
        print(f"  max_consecutive_losses: {max_losses}")
        print(f"  loss_streak_pause_minutes: {pause_minutes}")

        if loss_streak_pause:
            if now < loss_streak_pause:
                remaining = (loss_streak_pause - now).total_seconds() / 60
                print(f"  loss_streak_pause_until: {loss_streak_pause.strftime('%H:%M:%S')}")
                print(f"  [BLOCKING] Trading paused! {remaining:.1f} minutes remaining")
            else:
                print(f"  loss_streak_pause_until: {loss_streak_pause.strftime('%H:%M:%S')} (EXPIRED)")
                print("  [PASS] Pause expired, trading should resume")
        else:
            print("  loss_streak_pause_until: None")
            print("  [PASS] No loss streak pause active")

    except Exception as e:
        print(f"  [ERROR] Failed to check trader state: {e}")

    # =========================================================================
    # CHECK 3: Direction Tracker (Cooldown)
    # =========================================================================
    print("\n" + "=" * 70)
    print("CHECK 3: Direction Tracker Cooldown")
    print("=" * 70)

    try:
        from trading.heracles.signals import get_direction_tracker
        tracker = get_direction_tracker()
        status = tracker.get_status()

        print(f"  current_scan: {status['current_scan']}")
        print(f"  long_cooldown_until: {status['long_cooldown_until']}")
        print(f"  short_cooldown_until: {status['short_cooldown_until']}")
        print(f"  long_consecutive_wins: {status['long_consecutive_wins']}")
        print(f"  short_consecutive_wins: {status['short_consecutive_wins']}")
        print(f"  last_direction: {status['last_direction']}")
        print(f"  last_result: {status['last_result']}")

        # Check if directions are in cooldown
        long_blocked = tracker.is_direction_cooled_down('LONG')
        short_blocked = tracker.is_direction_cooled_down('SHORT')

        if long_blocked:
            remaining = status['long_cooldown_until'] - status['current_scan']
            print(f"  [BLOCKING] LONG in cooldown ({remaining} scans remaining)")
        else:
            print("  [PASS] LONG not in cooldown")

        if short_blocked:
            remaining = status['short_cooldown_until'] - status['current_scan']
            print(f"  [BLOCKING] SHORT in cooldown ({remaining} scans remaining)")
        else:
            print("  [PASS] SHORT not in cooldown")

        # Get win rates
        long_wr = status['long_win_rate']
        short_wr = status['short_win_rate']
        print(f"  long_win_rate: {long_wr:.2%}" if long_wr else "  long_win_rate: No data")
        print(f"  short_win_rate: {short_wr:.2%}" if short_wr else "  short_win_rate: No data")

    except Exception as e:
        print(f"  [ERROR] Failed to check direction tracker: {e}")

    # =========================================================================
    # CHECK 4: Win Probability Configuration
    # =========================================================================
    print("\n" + "=" * 70)
    print("CHECK 4: Win Probability Configuration")
    print("=" * 70)

    try:
        from trading.heracles.db import HERACLESDatabase
        db = HERACLESDatabase()
        win_tracker = db.get_win_tracker()
        config = db.get_config()

        print(f"  min_win_probability: {config.min_win_probability:.2%}")
        print(f"  bayesian_win_probability: {win_tracker.win_probability:.2%}")
        print(f"  total_trades: {win_tracker.total_trades}")
        print(f"  positive_gamma_wins: {win_tracker.positive_gamma_wins}")
        print(f"  positive_gamma_losses: {win_tracker.positive_gamma_losses}")
        print(f"  negative_gamma_wins: {win_tracker.negative_gamma_wins}")
        print(f"  negative_gamma_losses: {win_tracker.negative_gamma_losses}")

        # Calculate regime-specific probabilities
        pos_prob = win_tracker.get_regime_probability(GammaRegime.POSITIVE)
        neg_prob = win_tracker.get_regime_probability(GammaRegime.NEGATIVE)

        print(f"  positive_gamma_probability: {pos_prob:.2%}")
        print(f"  negative_gamma_probability: {neg_prob:.2%}")

        if neg_prob < config.min_win_probability:
            print(f"  [WARNING] Negative gamma probability ({neg_prob:.2%}) < min ({config.min_win_probability:.2%})")
            print("  This could cause signals to be rejected in negative gamma regime")
        else:
            print("  [PASS] Win probability above threshold")

    except Exception as e:
        print(f"  [ERROR] Failed to check win probability: {e}")

    # =========================================================================
    # CHECK 5: Signal Generation Test
    # =========================================================================
    print("\n" + "=" * 70)
    print("CHECK 5: Signal Generation Test")
    print("=" * 70)

    try:
        from trading.heracles.signals import HERACLESSignalGenerator, GammaRegime
        from trading.heracles.models import HERACLESConfig
        from trading.heracles.db import HERACLESDatabase

        db = HERACLESDatabase()
        config = db.get_config()
        win_tracker = db.get_win_tracker()
        generator = HERACLESSignalGenerator(config, win_tracker)

        # Get current MES price
        from trading.heracles.executor import TastytradeExecutor
        executor = TastytradeExecutor(config)
        quote = executor.get_mes_quote()

        if quote:
            current_price = quote.get('last', 0)
            print(f"  current_price (MES): {current_price}")
        else:
            current_price = 6777.0  # Fallback from logs
            print(f"  current_price (fallback): {current_price}")

        # Get paper account balance
        paper_account = db.get_paper_account()
        account_balance = paper_account.get('current_balance', 100000) if paper_account else 100000
        print(f"  account_balance: ${account_balance:,.2f}")

        # Determine if overnight
        is_overnight = now.hour >= 17 or now.hour < 8
        print(f"  is_overnight: {is_overnight}")

        # VIX and ATR estimates
        vix = 15.0
        atr = 20.0
        print(f"  vix (estimated): {vix}")
        print(f"  atr (estimated): {atr}")

        print("\n  Calling generate_signal()...")

        signal = generator.generate_signal(
            current_price=current_price,
            gex_data=gex_data,
            vix=vix,
            atr=atr,
            account_balance=account_balance,
            is_overnight=is_overnight
        )

        if signal:
            print(f"\n  [SIGNAL GENERATED]")
            print(f"    direction: {signal.direction.value}")
            print(f"    confidence: {signal.confidence:.2%}")
            print(f"    win_probability: {signal.win_probability:.2%}")
            print(f"    contracts: {signal.contracts}")
            print(f"    entry_price: {signal.entry_price:.2f}")
            print(f"    stop_price: {signal.stop_price:.2f}")
            print(f"    source: {signal.source.value}")
            print(f"    reasoning: {signal.reasoning[:150]}...")

            if signal.is_valid:
                print(f"\n  [PASS] Signal is VALID and ready for execution")
            else:
                print(f"\n  [BLOCKING] Signal generated but NOT VALID!")
                print(f"    confidence >= 0.50: {signal.confidence >= 0.50}")
                print(f"    win_probability >= 0.50: {signal.win_probability >= 0.50}")
                print(f"    entry_price > 0: {signal.entry_price > 0}")
                print(f"    stop_price > 0: {signal.stop_price > 0}")
                print(f"    contracts >= 1: {signal.contracts >= 1}")
        else:
            print(f"\n  [BLOCKING] No signal generated!")
            print("  Check logs above for specific rejection reason")

            # Analyze why no signal
            distance_from_flip = current_price - flip_point
            distance_pct = (distance_from_flip / flip_point) * 100 if flip_point > 0 else 0

            print(f"\n  Analysis:")
            print(f"    distance_from_flip: {distance_from_flip:.2f} pts ({distance_pct:.2f}%)")
            print(f"    flip_point_proximity_pct config: {config.flip_point_proximity_pct}%")
            print(f"    breakout_atr_threshold config: {config.breakout_atr_threshold}")
            print(f"    breakout_threshold (atr * config): {atr * config.breakout_atr_threshold:.2f} pts")

    except Exception as e:
        import traceback
        print(f"  [ERROR] Signal generation failed: {e}")
        traceback.print_exc()

    # =========================================================================
    # CHECK 6: Open Positions
    # =========================================================================
    print("\n" + "=" * 70)
    print("CHECK 6: Open Positions")
    print("=" * 70)

    try:
        from trading.heracles.db import HERACLESDatabase
        db = HERACLESDatabase()
        positions = db.get_open_positions()

        print(f"  open_positions: {len(positions)}")
        print(f"  max_open_positions: {config.max_open_positions}")

        if len(positions) >= config.max_open_positions:
            print(f"  [BLOCKING] Max positions ({config.max_open_positions}) reached!")
        else:
            print(f"  [PASS] Room for {config.max_open_positions - len(positions)} more positions")

        for pos in positions:
            print(f"\n  Position: {pos.position_id}")
            print(f"    direction: {pos.direction.value}")
            print(f"    entry_price: {pos.entry_price:.2f}")
            print(f"    contracts: {pos.contracts}")
            print(f"    status: {pos.status.value}")

    except Exception as e:
        print(f"  [ERROR] Failed to check positions: {e}")

    # =========================================================================
    # CHECK 7: Market Hours
    # =========================================================================
    print("\n" + "=" * 70)
    print("CHECK 7: Market Hours")
    print("=" * 70)

    try:
        from trading.heracles.executor import TastytradeExecutor
        from trading.heracles.models import HERACLESConfig

        config = HERACLESConfig()
        executor = TastytradeExecutor(config)

        is_market_open = executor.is_market_open()

        print(f"  is_market_open: {is_market_open}")

        if not is_market_open:
            print("  [BLOCKING] Market is closed - no trading possible")
        else:
            print("  [PASS] Market is open for trading")

    except Exception as e:
        print(f"  [ERROR] Failed to check market hours: {e}")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 70)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 70)

    print("""
If signals are being blocked, the most common causes are:

1. LOSS STREAK PAUSE: Trading paused after 3+ consecutive losses
   - Wait for pause to expire (5 minutes default)
   - Or reset the consecutive_losses counter

2. DIRECTION TRACKER COOLDOWN: A direction is blocked after a loss
   - The opposite direction may still trade
   - Cooldown lasts 2 scans (2 minutes)

3. WIN PROBABILITY TOO LOW: Bayesian estimate < 50%
   - New bot with few trades has uncertain probability
   - Need more winning trades to increase estimate

4. NO SIGNAL CONDITIONS MET: Price is at flip point
   - Price must be > breakout threshold away from flip
   - Or near a wall for wall bounce signal

To force a trade for testing, you can:
1. Manually adjust the direction tracker cooldowns
2. Reset the loss streak counter
3. Lower the min_win_probability threshold temporarily
""")


# Import GammaRegime for diagnostic use
try:
    from trading.heracles.models import GammaRegime
except ImportError:
    print("Warning: Could not import GammaRegime")


if __name__ == "__main__":
    diagnose()
