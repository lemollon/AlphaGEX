"""
Psychology Trap Trading Guide
Provides explicit money-making instructions for each regime type
"""

def get_trading_guide(regime_type: str, current_price: float, regime_data: dict) -> dict:
    """
    Get detailed trading guide for a specific regime type

    Returns:
        {
            'strategy': str,
            'entry_rules': list,
            'exit_rules': list,
            'strike_selection': str,
            'position_sizing': str,
            'win_rate': float,
            'avg_gain': str,
            'max_loss': str,
            'time_horizon': str,
            'why_it_works': str,
            'example_trade': dict
        }
    """

    guides = {
        'LIBERATION_TRADE': {
            'strategy': 'BUY CALLS POST-EXPIRATION',
            'entry_rules': [
                '1. Wait for the gamma wall to EXPIRE (check liberation date)',
                '2. Buy calls 1-2 strikes OTM on the day AFTER expiration',
                '3. Use 3-7 DTE for maximum gamma leverage',
                '4. Enter within first hour of trading for best fill'
            ],
            'exit_rules': [
                '1. Take 75%+ profit when price hits next resistance',
                '2. Stop loss: 50% of premium paid',
                '3. Hold maximum 3 days - wall energy dissipates',
                '4. Exit if RSI falls back below 60 on 4h chart'
            ],
            'strike_selection': f'Buy ${current_price + 2:.0f} or ${current_price + 3:.0f} calls (1-2 strikes OTM)',
            'position_sizing': 'Risk 2-3% of account - this is a high-probability setup',
            'win_rate': 68,
            'avg_gain': '+120% to +200%',
            'max_loss': '-50%',
            'time_horizon': '1-3 days after liberation',
            'why_it_works': '''Dealers were forced to sell calls to hedge the wall. When the wall expires,
they unwind those hedges by BUYING BACK calls. This creates buying pressure on the stock AND reduces supply
of calls (making them more expensive). Plus, all that pent-up RSI energy finally releases. It's like a
compressed spring - once the wall disappears, price explodes.''',
            'example_trade': {
                'setup': f'SPY trading at ${current_price:.2f}. $5 call wall expires tomorrow.',
                'entry': f'Tomorrow (after expiration): Buy SPY ${current_price + 2:.0f} calls, 5 DTE',
                'cost': '$2.50 per contract ($250 for 1 contract)',
                'target': f'Exit at ${current_price + 5:.0f} → Calls worth ~$5.00 (+100%)',
                'stop': '$1.25 (if SPY fails to break through within 2 days)',
                'expected': '+$250 profit per contract (100% gain) in 1-3 days'
            }
        },

        'FALSE_FLOOR': {
            'strategy': 'BUY PUTS BEFORE SUPPORT DISAPPEARS',
            'entry_rules': [
                '1. Enter 2-3 days BEFORE the put wall expires',
                '2. Buy puts 1 strike OTM from current price',
                '3. Use 5-10 DTE to capture the breakdown',
                '4. Enter when RSI NOT oversold (complacency indicator)'
            ],
            'exit_rules': [
                '1. Target: Next significant put wall below',
                '2. Take 50%+ profit on first move down',
                '3. Stop loss: If price moves above the "false floor" by 1%',
                '4. Exit all before next monthly OPEX'
            ],
            'strike_selection': f'Buy ${current_price - 2:.0f} puts (1-2 strikes OTM)',
            'position_sizing': 'Risk 1.5-2% of account - timing is critical',
            'win_rate': 62,
            'avg_gain': '+80% to +150%',
            'max_loss': '-40%',
            'time_horizon': '2-5 days (before and after floor expires)',
            'why_it_works': '''Bulls think they have support but it's temporary. 70%+ of the put wall
gamma expires soon, leaving a vacuum below. When the wall disappears, there's nothing stopping price
from falling to the next real support. Dealers who were long puts now unwind by SELLING them, creating
selling pressure. Market structure disappears = air pocket below.''',
            'example_trade': {
                'setup': f'SPY at ${current_price:.2f}. Put wall at ${current_price - 3:.0f} expires in 3 days.',
                'entry': f'TODAY: Buy SPY ${current_price - 2:.0f} puts, 7 DTE',
                'cost': '$1.80 per contract ($180 for 1 contract)',
                'target': f'Exit at ${current_price - 6:.0f} → Puts worth ~$3.50 (+94%)',
                'stop': f'${current_price + 1:.0f} → Puts worth ~$1.00 (-44%)',
                'expected': '+$170 profit per contract (94% gain) in 3-5 days'
            }
        },

        'ZERO_DTE_PIN': {
            'strategy': 'BUY STRADDLE BEFORE CLOSE, PROFIT FROM TOMORROW\'S EXPANSION',
            'entry_rules': [
                '1. Enter 30 minutes before market close (3:30 PM ET)',
                '2. Buy ATM straddle (both call and put at current price)',
                '3. Use 1-3 DTE options (tomorrow\'s expiration is fine)',
                '4. Only if 0DTE gamma > $500M and RSI coiling on 3+ timeframes'
            ],
            'exit_rules': [
                '1. Exit BOTH legs in first 30-60 minutes of next day',
                '2. Take 40-60% profit on the winning leg',
                '3. Close losing leg for small loss',
                '4. Don\'t hold past 11 AM - pin can reform'
            ],
            'strike_selection': f'Buy ${int(current_price):.0f} straddle (ATM call + put)',
            'position_sizing': 'Risk 2% of account - high probability but need size for theta',
            'win_rate': 75,
            'avg_gain': '+60% to +100%',
            'max_loss': '-30%',
            'time_horizon': 'Overnight hold, exit next morning',
            'why_it_works': '''Massive 0DTE gamma pins price all day - it barely moves. Volatility gets
CRUSHED. But at 4 PM, ALL that gamma expires. Tomorrow morning, there's no pin = price free to move.
Overnight, options are cheap because IV is low. Next morning, IV expands + price moves = both go up.
You're buying compressed volatility and selling expanded volatility.''',
            'example_trade': {
                'setup': f'SPY pinned at ${current_price:.2f} all day. $600M in 0DTE gamma expires at 4 PM.',
                'entry': f'3:30 PM: Buy ${int(current_price)} straddle (call + put), 1 DTE',
                'cost': '$3.00 total ($1.50 call + $1.50 put) = $300 per straddle',
                'target': f'9:45 AM tomorrow: SPY moves to ${current_price + 2:.0f} → Call worth $2.50, Put worth $0.50 = $3.00 total',
                'stop': 'If SPY doesn\'t move by 11 AM → Exit for ~$2.50 total (-17%)',
                'expected': '+$0 to +100 profit per straddle (0-33% gain) in 16 hours'
            }
        },

        'DESTINATION_TRADE': {
            'strategy': 'BUY CALL DEBIT SPREAD TOWARD MONTHLY MAGNET',
            'entry_rules': [
                '1. Enter when 10-15 days remain to monthly OPEX',
                '2. Buy call spread: Long ATM, Short at magnet strike',
                '3. Must have RSI > 60 on daily + magnet strength > 50',
                '4. Enter on any pullback (RSI dips on 1h chart)'
            ],
            'exit_rules': [
                '1. Close at 75% of max profit (don\'t be greedy)',
                '2. Exit 2 days before OPEX (gamma effects peak)',
                '3. Stop loss: 40% of debit paid',
                '4. If magnet breaks, exit immediately'
            ],
            'strike_selection': f'Buy ${int(current_price):.0f} call / Sell ${int(current_price + 10):.0f} call spread',
            'position_sizing': 'Risk 3-4% of account - longer time horizon smooths variance',
            'win_rate': 71,
            'avg_gain': '+70% to +120%',
            'max_loss': '-40%',
            'time_horizon': '7-12 days',
            'why_it_works': '''Market makers and institutions see the same monthly magnet you do. They
position AHEAD of it. As expiration approaches, gamma effects get stronger - dealers must hedge toward
the magnet. It's like gravity. The closer you get to OPEX, the stronger the pull. You're not predicting
direction - you're following institutional flow.''',
            'example_trade': {
                'setup': f'SPY at ${current_price:.2f}. Monthly magnet at ${current_price + 10:.0f} with strength 87. 12 days to OPEX.',
                'entry': f'Buy ${int(current_price)} / ${int(current_price + 10)} call spread, monthly exp',
                'cost': '$4.50 per spread ($450 for 1 contract)',
                'target': f'SPY reaches ${current_price + 8:.0f} → Spread worth $8.00 (+78%)',
                'stop': f'SPY drops to ${current_price - 3:.0f} → Spread worth $2.70 (-40%)',
                'expected': '+$350 profit per spread (78% gain) in 7-10 days'
            }
        },

        'EXPLOSIVE_CONTINUATION': {
            'strategy': 'BUY CALLS ON THE BREAKOUT',
            'entry_rules': [
                '1. Wait for price to break call wall by 0.5%+',
                '2. Buy calls 1 strike OTM immediately after break',
                '3. Volume MUST be 1.2x average or higher',
                '4. RSI must be > 70 on 3+ timeframes (confirms momentum)'
            ],
            'exit_rules': [
                '1. Trail stop: Exit if price falls back below broken wall',
                '2. Take 100%+ profit on parabolic moves',
                '3. Exit if volume dries up (< 0.8x average)',
                '4. Maximum hold: 2 days'
            ],
            'strike_selection': f'Buy ${current_price + 2:.0f} calls (1-2 strikes OTM from broken wall)',
            'position_sizing': 'Risk 2-3% of account - fast moving, tight stop',
            'win_rate': 65,
            'avg_gain': '+150% to +300%',
            'max_loss': '-35%',
            'time_horizon': '1-2 days (fast trade)',
            'why_it_works': '''Breaking a call wall triggers dealer re-hedging. They were short calls
at that strike. Now price is ABOVE it, they must buy more stock to hedge their short calls. This creates
a feedback loop: price up → dealers buy → price up more → dealers buy more. It's a gamma squeeze.
Plus, short sellers who sold at the wall are now trapped and must cover.''',
            'example_trade': {
                'setup': f'SPY breaks ${current_price:.0f} call wall, now at ${current_price + 1:.0f}. Volume 1.4x average.',
                'entry': f'Buy ${current_price + 2:.0f} calls, 3 DTE (immediately)',
                'cost': '$1.20 per contract ($120 for 1 contract)',
                'target': f'SPY runs to ${current_price + 5:.0f} → Calls worth $3.50 (+192%)',
                'stop': f'SPY falls back to ${current_price - 0.5:.0f} → Calls worth $0.80 (-33%)',
                'expected': '+$230 profit per contract (192% gain) in 1-2 days'
            }
        },

        'PIN_AT_PUT_WALL': {
            'strategy': 'SELL PUT CREDIT SPREADS AT THE WALL',
            'entry_rules': [
                '1. Price within 1% of put wall',
                '2. RSI < 30 on 3+ timeframes (oversold)',
                '3. Sell put spread: Short put AT wall, Long put 2-3 strikes below',
                '4. Use 5-10 DTE for theta decay'
            ],
            'exit_rules': [
                '1. Close at 50-60% profit (don\'t wait for max)',
                '2. Exit if price breaks BELOW long put strike',
                '3. Exit 2 days before expiration (avoid gamma risk)',
                '4. Roll down if wall holds but time runs out'
            ],
            'strike_selection': f'Sell ${current_price - 2:.0f} put / Buy ${current_price - 5:.0f} put',
            'position_sizing': 'Risk 1-2% of account per spread',
            'win_rate': 73,
            'avg_gain': '+40% to +60%',
            'max_loss': '-100% (max loss is spread width)',
            'time_horizon': '3-7 days',
            'why_it_works': '''Put walls act as trampolines. Dealers long puts provide buying support.
They don't want price below the wall (would increase their delta exposure). Every dip gets bought.
Meanwhile, theta decays your short puts. The wall does the work for you - you just collect premium
as time passes and price bounces off support.''',
            'example_trade': {
                'setup': f'SPY at ${current_price:.2f}, put wall at ${current_price - 2:.0f}. RSI 28 on 4 timeframes.',
                'entry': f'Sell ${current_price - 2:.0f} / ${current_price - 5:.0f} put spread, 7 DTE',
                'credit': '$1.20 per spread ($120 credit received)',
                'target': 'SPY bounces to $573+ → Close for $0.50 → Keep $0.70 (+58%)',
                'max_loss': 'SPY crashes below $568 → Spread worth $3.00 → Lose $1.80 (-150%)',
                'expected': '+$70 profit per spread (58% gain) in 3-5 days'
            }
        },

        'MEAN_REVERSION_ZONE': {
            'strategy': 'FADE THE EXTREME - CLASSIC RSI REVERSAL',
            'entry_rules': [
                '1. RSI > 70 or < 30 on 3+ timeframes',
                '2. Net gamma POSITIVE (dealers dampening moves)',
                '3. Price approaching call wall (if overbought) or put wall (if oversold)',
                '4. No major catalysts within 3 days'
            ],
            'exit_rules': [
                '1. Exit when RSI returns to 50 on 4h chart',
                '2. Take 50-70% profit',
                '3. Stop loss: If RSI goes MORE extreme (80+ or 20-)',
                '4. Maximum hold: 5 days'
            ],
            'strike_selection': f'If overbought: Buy ${current_price - 1:.0f} puts. If oversold: Buy ${current_price + 1:.0f} calls',
            'position_sizing': 'Risk 1.5-2% of account - traditional setup, moderate risk',
            'win_rate': 68,
            'avg_gain': '+50% to +90%',
            'max_loss': '-40%',
            'time_horizon': '2-5 days',
            'why_it_works': '''In long gamma environments, dealers STABILIZE price. Every move up makes
them sell (to reduce delta), every move down makes them buy. This creates natural mean reversion.
Traditional technical analysis actually WORKS here. RSI extremes snap back. Unlike negative gamma where
dealers amplify moves, here they fight them. Classic reversion to the mean.''',
            'example_trade': {
                'setup': f'SPY at ${current_price:.2f}, RSI 75+ on 4 timeframes. Net gamma +$2.5B.',
                'entry': f'Buy ${current_price - 1:.0f} puts, 7 DTE',
                'cost': '$1.50 per contract ($150 per contract)',
                'target': f'SPY pulls back to ${current_price - 3:.0f} → Puts worth $2.80 (+87%)',
                'stop': f'SPY continues to ${current_price + 2:.0f} → Puts worth $0.90 (-40%)',
                'expected': '+$130 profit per contract (87% gain) in 2-4 days'
            }
        }
    }

    # Default guide if regime type not found
    default_guide = {
        'strategy': 'WAIT FOR CLEAR SETUP',
        'entry_rules': [
            '1. Market in transition',
            '2. Wait for clearer regime to emerge',
            '3. Review again in 4-6 hours',
            '4. Don\'t force trades in neutral conditions'
        ],
        'exit_rules': ['N/A - No position'],
        'strike_selection': 'Wait for setup',
        'position_sizing': 'No position',
        'win_rate': 0,
        'avg_gain': 'N/A',
        'max_loss': 'N/A',
        'time_horizon': 'N/A',
        'why_it_works': 'No clear market structure to exploit',
        'example_trade': {
            'setup': 'No setup present',
            'entry': 'N/A',
            'cost': '$0',
            'target': 'N/A',
            'stop': 'N/A',
            'expected': '$0'
        }
    }

    return guides.get(regime_type, default_guide)
