"""
psychology_trap_detector.py - Complete Psychology Trap Detection System

This module implements the comprehensive Alpha GEX Psychology Trap Detection System
with multi-timeframe RSI analysis, gamma expiration tracking, and forward GEX magnets.

Layers:
1. Multi-timeframe RSI Analysis
2. Current Gamma Wall Detection
3. Gamma Expiration Timeline Analysis
4. Forward GEX Magnet Detection
5. Complete Regime Detection

Author: AlphaGEX Team
Date: 2025-11-07
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import sqlite3
from config_and_database import DB_PATH

# Import Polygon.io helper instead of yfinance
try:
    from polygon_helper import fetch_vix_data as polygon_fetch_vix_data
    POLYGON_AVAILABLE = True
except ImportError:
    POLYGON_AVAILABLE = False
    print("⚠️ polygon_helper.py not available - VIX data will use defaults")

# ============================================================================
# NEW LAYER 0: VIX AND VOLATILITY REGIME DETECTION
# ============================================================================

def fetch_vix_data() -> Dict:
    """
    Fetch VIX (Volatility Index) data from Polygon.io

    Returns:
        {
            'current': float,  # Current VIX level
            'previous_close': float,  # Yesterday's close
            'change_pct': float,  # % change from previous close
            'intraday_high': float,  # Today's high
            'intraday_low': float,  # Today's low
            'ma_20': float,  # 20-day moving average
            'spike_detected': bool  # True if VIX spiked >20%
        }
    """
    if POLYGON_AVAILABLE:
        try:
            return polygon_fetch_vix_data()
        except Exception as e:
            print(f"Error fetching VIX data from Polygon.io: {e}")
            return get_default_vix_data()
    else:
        return get_default_vix_data()


def get_default_vix_data() -> Dict:
    """Return default VIX data when fetch fails"""
    return {
        'current': 15.0,
        'previous_close': 15.0,
        'change_pct': 0.0,
        'intraday_high': 15.5,
        'intraday_low': 14.5,
        'ma_20': 15.0,
        'spike_detected': False
    }


def detect_volatility_regime(vix_data: Dict, net_gamma: float, zero_gamma_level: float, current_price: float) -> Dict:
    """
    Determine volatility regime based on VIX and gamma positioning

    Args:
        vix_data: VIX data from fetch_vix_data()
        net_gamma: Net gamma exposure (positive = long, negative = short)
        zero_gamma_level: Strike where net gamma crosses zero (flip point)
        current_price: Current spot price

    Returns:
        {
            'regime': str,  # 'EXPLOSIVE_VOLATILITY', 'NEGATIVE_GAMMA_RISK', 'COMPRESSION_PIN', 'POSITIVE_GAMMA_STABLE'
            'risk_level': str,  # 'extreme', 'high', 'medium', 'low'
            'description': str,
            'at_flip_point': bool,  # True if price near zero gamma level
            'flip_point_distance_pct': float
        }
    """
    # Handle None values safely
    vix_current = vix_data.get('current') if vix_data else None
    vix_spike = vix_data.get('spike_detected', False) if vix_data else False
    vix_change_pct = vix_data.get('change_pct', 0) if vix_data else 0

    # Ensure vix_current is not None
    if vix_current is None:
        vix_current = 15.0  # Default VIX value

    # Ensure zero_gamma_level and current_price are not None
    if zero_gamma_level is None:
        zero_gamma_level = 0
    if current_price is None or current_price <= 0:
        current_price = 500.0  # Reasonable default for SPY

    # Calculate distance from flip point
    flip_distance_pct = abs(current_price - zero_gamma_level) / current_price * 100 if zero_gamma_level > 0 else 100
    at_flip_point = flip_distance_pct < 0.5  # Within 0.5%

    # NEGATIVE GAMMA ENVIRONMENT (dealers amplify moves)
    if net_gamma < 0:
        if vix_spike or vix_change_pct > 20:
            return {
                'regime': 'EXPLOSIVE_VOLATILITY',
                'risk_level': 'extreme',
                'description': f'VIX spiked {vix_change_pct:.1f}% + short gamma = dealer amplification active. Small moves become explosive.',
                'at_flip_point': at_flip_point,
                'flip_point_distance_pct': flip_distance_pct
            }
        elif at_flip_point:
            return {
                'regime': 'FLIP_POINT_CRITICAL',
                'risk_level': 'extreme',
                'description': f'Price at zero gamma level (${zero_gamma_level:.2f}). Crossing triggers dealer hedge flip = explosive move.',
                'at_flip_point': at_flip_point,
                'flip_point_distance_pct': flip_distance_pct
            }
        else:
            return {
                'regime': 'NEGATIVE_GAMMA_RISK',
                'risk_level': 'high',
                'description': 'Short gamma regime: Dealers amplify moves. Momentum dominates over mean reversion.',
                'at_flip_point': at_flip_point,
                'flip_point_distance_pct': flip_distance_pct
            }

    # POSITIVE GAMMA ENVIRONMENT (dealers dampen moves)
    else:
        if vix_current < 15 and vix_change_pct < -5:
            return {
                'regime': 'COMPRESSION_PIN',
                'risk_level': 'low',
                'description': 'VIX compressing + long gamma = dealers pin price. Expect tight range.',
                'at_flip_point': at_flip_point,
                'flip_point_distance_pct': flip_distance_pct
            }
        else:
            return {
                'regime': 'POSITIVE_GAMMA_STABLE',
                'risk_level': 'medium',
                'description': 'Long gamma regime: Dealers dampen moves. Mean reversion works.',
                'at_flip_point': at_flip_point,
                'flip_point_distance_pct': flip_distance_pct
            }


def calculate_volume_confirmation(price_data: Dict, volume_ratio: float) -> Dict:
    """
    Analyze volume patterns to confirm or reject RSI extremes

    Args:
        price_data: Multi-timeframe price data
        volume_ratio: Current volume / 20-day average

    Returns:
        {
            'volume_expanding': bool,  # True if volume increasing
            'volume_surge': bool,  # True if volume >150% average
            'volume_declining': bool,  # True if volume <70% average
            'confirmation_strength': str,  # 'strong', 'moderate', 'weak'
            'interpretation': str
        }
    """
    # Get daily volume data
    daily_data = price_data.get('1d', [])
    if len(daily_data) < 10:
        return {
            'volume_expanding': False,
            'volume_surge': False,
            'volume_declining': False,
            'confirmation_strength': 'weak',
            'interpretation': 'Insufficient volume data'
        }

    # Calculate volume trend (last 5 days vs previous 5 days)
    recent_vol = np.mean([bar['volume'] for bar in daily_data[-5:]])
    prior_vol = np.mean([bar['volume'] for bar in daily_data[-10:-5]])

    vol_trend_pct = ((recent_vol - prior_vol) / prior_vol * 100) if prior_vol > 0 else 0

    volume_expanding = vol_trend_pct > 15  # Volume increasing >15%
    volume_surge = volume_ratio > 2.0  # Current vol >200% average (2x minimum for dealer activity)
    volume_declining = volume_ratio < 0.7  # Current vol <70% average

    # Determine confirmation strength
    if volume_surge and volume_expanding:
        confirmation = 'strong'
        interpretation = 'Volume surge 2x+ average + expansion = genuine dealer activity confirmed'
    elif volume_ratio > 1.5 and volume_expanding:
        confirmation = 'moderate'
        interpretation = 'Above-average volume but needs 2x for full confirmation'
    elif volume_declining:
        confirmation = 'weak'
        interpretation = 'Volume declining = exhaustion/reversal likely'
    else:
        confirmation = 'neutral'
        interpretation = 'Average volume = no clear dealer confirmation (need 2x minimum)'

    return {
        'volume_expanding': volume_expanding,
        'volume_surge': volume_surge,
        'volume_declining': volume_declining,
        'confirmation_strength': confirmation,
        'interpretation': interpretation,
        'volume_trend_pct': vol_trend_pct
    }


def analyze_dealer_feedback_loop_mechanics(
    strike_data: pd.DataFrame,
    current_price: float,
    net_gex: float,
    price_momentum: float,
    volume_ratio: float,
    strike_volume_data: Optional[Dict] = None
) -> Dict:
    """
    DETAILED ANALYSIS: Why dealer hedging creates feedback loops at specific strikes

    This function explains the MECHANICS of how dealer hedging amplifies moves:
    - Which strikes have the most dealer activity
    - How much buying/selling is happening at those strikes
    - WHY dealers must hedge in the direction of the move
    - What creates the feedback loop amplification

    Args:
        strike_data: DataFrame with columns ['strike', 'gex', 'open_interest', 'volume']
        current_price: Current SPY price
        net_gex: Net gamma exposure (positive = long, negative = short)
        price_momentum: Price % change (positive = upward, negative = downward)
        volume_ratio: Current volume / 20-day average
        strike_volume_data: Optional dict with volume/OI analysis at each strike

    Returns:
        {
            'feedback_loop_active': bool,
            'loop_strength': str,  # 'extreme', 'strong', 'moderate', 'weak', 'none'
            'direction': str,  # 'bullish', 'bearish', 'neutral'
            'mechanics_explanation': str,  # Detailed WHY
            'critical_strikes': List[Dict],  # Strikes where most activity is happening
            'dealer_hedging_pressure': float,  # Estimated hedging flow in $ millions
            'amplification_factor': float,  # How much dealers amplify the move (1.0 = no amplification)
            'volume_at_high_oi_strikes': Dict,  # Volume activity at key strikes
            'supporting_evidence': List[str]
        }
    """
    result = {
        'feedback_loop_active': False,
        'loop_strength': 'none',
        'direction': 'neutral',
        'mechanics_explanation': '',
        'critical_strikes': [],
        'dealer_hedging_pressure': 0.0,
        'amplification_factor': 1.0,
        'volume_at_high_oi_strikes': {},
        'supporting_evidence': []
    }

    if strike_data.empty:
        result['mechanics_explanation'] = 'Insufficient strike data for analysis'
        return result

    # STEP 1: Identify high OI strikes (top 20% by open interest)
    strike_data = strike_data.copy()
    strike_data['oi_percentile'] = strike_data['open_interest'].rank(pct=True) * 100
    high_oi_strikes = strike_data[strike_data['oi_percentile'] >= 80].copy()

    if high_oi_strikes.empty:
        result['mechanics_explanation'] = 'No high open interest strikes found'
        return result

    # STEP 2: Calculate volume/OI ratio at each high OI strike
    high_oi_strikes['volume_oi_ratio'] = high_oi_strikes['volume'] / (high_oi_strikes['open_interest'] + 1)
    high_oi_strikes['distance_from_spot'] = ((high_oi_strikes['strike'] - current_price) / current_price) * 100

    # STEP 3: Identify strikes with UNUSUAL VOLUME (volume > 2x OI = active dealer hedging)
    active_hedging_strikes = high_oi_strikes[high_oi_strikes['volume_oi_ratio'] > 2.0].copy()

    # STEP 4: Determine dealer positioning and hedging direction
    dealer_position = 'SHORT_GAMMA' if net_gex < -0.5e9 else 'LONG_GAMMA' if net_gex > 0.5e9 else 'NEUTRAL'
    price_direction = 'UP' if price_momentum > 0 else 'DOWN' if price_momentum < 0 else 'FLAT'

    # STEP 5: Calculate dealer hedging pressure
    # When dealers are short gamma, they must hedge by buying when price goes up
    # Hedging pressure = GEX * price move * volume confirmation
    hedging_pressure_millions = 0.0
    amplification = 1.0

    if dealer_position == 'SHORT_GAMMA' and abs(price_momentum) > 0.3:
        # Dealers must hedge in SAME direction as price move
        # This AMPLIFIES the move (feedback loop)
        base_pressure = abs(net_gex / 1e9) * abs(price_momentum) * 100  # In millions
        volume_multiplier = min(volume_ratio / 2.0, 2.0)  # Volume enhances pressure (cap at 2x)
        hedging_pressure_millions = base_pressure * volume_multiplier
        amplification = 1.0 + (volume_ratio - 1.0) * 0.5  # Each 1x volume adds 0.5x amplification

        result['feedback_loop_active'] = True
        result['direction'] = 'bullish' if price_direction == 'UP' else 'bearish'

    elif dealer_position == 'LONG_GAMMA' and abs(price_momentum) > 0.3:
        # Dealers hedge in OPPOSITE direction (dampens moves)
        # No feedback loop - mean reversion
        hedging_pressure_millions = abs(net_gex / 1e9) * abs(price_momentum) * 50
        amplification = 0.7  # Dealers DAMPEN moves by 30%
        result['direction'] = 'mean_reversion'

    result['dealer_hedging_pressure'] = hedging_pressure_millions
    result['amplification_factor'] = amplification

    # STEP 6: Analyze volume at high OI strikes to see WHERE hedging is happening
    critical_strikes = []
    for idx, row in active_hedging_strikes.iterrows():
        strike_info = {
            'strike': row['strike'],
            'open_interest': int(row['open_interest']),
            'volume': int(row['volume']),
            'volume_oi_ratio': row['volume_oi_ratio'],
            'distance_pct': row['distance_from_spot'],
            'gex': row['gex'] if 'gex' in row else 0,
            'interpretation': ''
        }

        # Interpret what's happening at this strike
        if row['volume_oi_ratio'] > 5.0:
            strike_info['interpretation'] = 'EXTREME hedging activity - dealers actively adjusting positions'
        elif row['volume_oi_ratio'] > 3.0:
            strike_info['interpretation'] = 'Heavy hedging - significant dealer rebalancing'
        elif row['volume_oi_ratio'] > 2.0:
            strike_info['interpretation'] = 'Moderate hedging - dealers responding to price move'

        critical_strikes.append(strike_info)

    # Sort by volume/OI ratio (most active hedging first)
    critical_strikes.sort(key=lambda x: x['volume_oi_ratio'], reverse=True)
    result['critical_strikes'] = critical_strikes[:5]  # Top 5 most active

    # STEP 7: Determine feedback loop strength
    if result['feedback_loop_active']:
        if volume_ratio >= 2.0 and amplification > 1.5 and len(critical_strikes) >= 3:
            result['loop_strength'] = 'extreme'
        elif volume_ratio >= 1.8 and amplification > 1.3 and len(critical_strikes) >= 2:
            result['loop_strength'] = 'strong'
        elif volume_ratio >= 1.5 and amplification > 1.2:
            result['loop_strength'] = 'moderate'
        else:
            result['loop_strength'] = 'weak'

    # STEP 8: Generate detailed mechanics explanation
    if result['feedback_loop_active']:
        direction_word = "UP" if price_direction == "UP" else "DOWN"
        hedge_direction = "BUY" if price_direction == "UP" else "SELL"

        mechanics = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              DEALER HEDGING FEEDBACK LOOP - MECHANICS EXPLAINED              ║
╚══════════════════════════════════════════════════════════════════════════════╝

📊 CURRENT SITUATION:
   • Dealer Position: {dealer_position} (Net GEX: ${net_gex/1e9:.2f}B)
   • Price Movement: {direction_word} {abs(price_momentum):.2f}%
   • Volume: {volume_ratio:.2f}x average ({"✅ SURGE - confirms real move" if volume_ratio >= 2.0 else "⚠️ Needs 2x for confirmation"})
   • Active Hedging Strikes: {len(critical_strikes)} strikes showing unusual volume

🔄 WHY THE FEEDBACK LOOP EXISTS:

1️⃣  DEALERS ARE SHORT GAMMA
   → They sold options to market participants
   → They are now EXPOSED to large price moves
   → They MUST hedge to stay delta-neutral

2️⃣  PRICE MOVES {direction_word}
   → Their short gamma position loses money
   → Delta exposure increases as price moves
   → They must {hedge_direction} SPY to hedge

3️⃣  DEALER {hedge_direction}ING PUSHES PRICE {direction_word}
   → Estimated hedging flow: ${hedging_pressure_millions:.1f}M
   → This creates MORE {direction_word}ward pressure
   → Price accelerates in same direction

4️⃣  ACCELERATION TRIGGERS MORE HEDGING
   → As price continues {direction_word}, dealers need to {hedge_direction} MORE
   → This creates a FEEDBACK LOOP
   → Move amplified by {(amplification - 1) * 100:.0f}% due to dealer hedging

📍 WHERE THE HEDGING IS HAPPENING (Top Active Strikes):
"""

        for i, strike in enumerate(result['critical_strikes'][:3], 1):
            mechanics += f"""
   {i}. Strike ${strike['strike']:.2f} ({strike['distance_pct']:+.1f}% from spot)
      → Open Interest: {strike['open_interest']:,} contracts
      → Today's Volume: {strike['volume']:,} contracts
      → Volume/OI Ratio: {strike['volume_oi_ratio']:.2f}x
      → {strike['interpretation']}
"""

        mechanics += f"""
⚡ AMPLIFICATION ANALYSIS:
   • Base move: {abs(price_momentum):.2f}%
   • Dealer amplification factor: {amplification:.2f}x
   • Effective move with hedging: {abs(price_momentum) * amplification:.2f}%

🎯 WHAT THIS MEANS FOR TRADING:
   • Trade WITH the feedback loop, not against it
   • {hedge_direction} pressure will continue until:
     - Volume drops below 2x average (hedging exhaustion)
     - RSI hits extreme (>80 or <20)
     - Price hits major gamma wall (resistance/support)
   • This is a {result['loop_strength'].upper()} feedback loop
   • Expected duration: 2-4 hours typically

⚠️  RISK: Loop can REVERSE quickly if volume dries up or gamma flip is hit
"""

        result['mechanics_explanation'] = mechanics

        # Add supporting evidence
        result['supporting_evidence'].append(f"Net GEX ${net_gex/1e9:.2f}B indicates {dealer_position}")
        result['supporting_evidence'].append(f"Price moving {direction_word} {abs(price_momentum):.2f}%")
        result['supporting_evidence'].append(f"Volume {volume_ratio:.2f}x average confirms dealer activity")
        result['supporting_evidence'].append(f"{len(critical_strikes)} strikes showing volume/OI > 2.0x")
        result['supporting_evidence'].append(f"Estimated hedging pressure: ${hedging_pressure_millions:.1f}M")

    else:
        result['mechanics_explanation'] = f"""
No active feedback loop detected.

Current conditions:
• Dealer Position: {dealer_position} (Net GEX: ${net_gex/1e9:.2f}B)
• Price Movement: {price_direction} {abs(price_momentum):.2f}%
• Volume: {volume_ratio:.2f}x average

{"→ Dealers are LONG gamma - they DAMPEN moves, not amplify them" if dealer_position == 'LONG_GAMMA' else ""}
{"→ Price momentum too weak to trigger dealer hedging" if abs(price_momentum) < 0.3 else ""}
{"→ Volume too low to confirm dealer activity" if volume_ratio < 1.5 else ""}
"""

    return result


def calculate_breakout_rejection_probability(
    current_price: float,
    resistance_strike: float,
    support_strike: float,
    net_gex: float,
    strike_gex: float,
    volume_ratio: float,
    rsi_score: float,
    price_momentum: float,
    dealer_hedging_pressure: float,
    distance_to_gamma_flip: float
) -> Dict:
    """
    Calculate probability of breaking through resistance/support vs rejecting

    TRANSPARENT LOGIC showing all factors that influence breakout/rejection:
    - Volume confirmation (2x minimum for real moves)
    - GEX concentration at the level
    - Price momentum strength
    - Dealer hedging pressure
    - RSI positioning
    - Distance to gamma flip point

    Args:
        current_price: Current SPY price
        resistance_strike: Resistance level (call wall or gamma flip)
        support_strike: Support level (put wall or gamma flip)
        net_gex: Net gamma exposure
        strike_gex: GEX at the specific strike being tested
        volume_ratio: Current volume / 20-day average
        rsi_score: RSI score (-100 to +100)
        price_momentum: Recent price % change
        dealer_hedging_pressure: Estimated dealer hedging flow ($ millions)
        distance_to_gamma_flip: Distance to gamma flip (%)

    Returns:
        {
            'level_type': str,  # 'resistance' or 'support'
            'level_price': float,
            'breakout_probability': float,  # 0-100
            'rejection_probability': float,  # 0-100
            'confidence': str,  # 'high', 'medium', 'low'
            'logic_breakdown': Dict,  # Transparent scoring for each factor
            'recommendation': str,
            'key_factors': List[str]
        }
    """
    # Determine if testing resistance or support
    distance_to_resistance = ((resistance_strike - current_price) / current_price) * 100
    distance_to_support = ((current_price - support_strike) / current_price) * 100

    if abs(distance_to_resistance) < abs(distance_to_support):
        level_type = 'resistance'
        level_price = resistance_strike
        distance_pct = distance_to_resistance
    else:
        level_type = 'support'
        level_price = support_strike
        distance_pct = -distance_to_support

    # Initialize scoring system (0-100 for each factor)
    logic_breakdown = {}
    breakout_score = 50  # Start neutral

    # FACTOR 1: Volume Confirmation (30 points max)
    # Need 2x volume minimum for real breakouts
    if volume_ratio >= 2.5:
        volume_score = 30
        volume_explanation = f"✅ Extreme volume {volume_ratio:.2f}x confirms strong momentum"
    elif volume_ratio >= 2.0:
        volume_score = 25
        volume_explanation = f"✅ Strong volume {volume_ratio:.2f}x supports breakout"
    elif volume_ratio >= 1.5:
        volume_score = 15
        volume_explanation = f"⚠️ Moderate volume {volume_ratio:.2f}x - needs more confirmation"
    elif volume_ratio >= 1.0:
        volume_score = 5
        volume_explanation = f"⚠️ Average volume {volume_ratio:.2f}x - weak confirmation"
    else:
        volume_score = -10
        volume_explanation = f"❌ Below average volume {volume_ratio:.2f}x - likely rejection"

    logic_breakdown['volume'] = {
        'score': volume_score,
        'weight': 30,
        'explanation': volume_explanation
    }
    breakout_score += (volume_score - 15)  # Adjust from neutral

    # FACTOR 2: GEX Wall Strength (25 points max)
    # Strong GEX concentration makes breakouts harder
    wall_strength_pct = abs(strike_gex) / max(abs(net_gex), 1e9) * 100 if net_gex != 0 else 0

    if wall_strength_pct > 40:
        gex_score = -20
        gex_explanation = f"❌ MASSIVE gamma wall ({wall_strength_pct:.0f}% of total GEX) - very hard to break"
    elif wall_strength_pct > 25:
        gex_score = -10
        gex_explanation = f"⚠️ Strong gamma wall ({wall_strength_pct:.0f}% of total GEX) - likely rejection"
    elif wall_strength_pct > 15:
        gex_score = 0
        gex_explanation = f"⚠️ Moderate gamma wall ({wall_strength_pct:.0f}% of total GEX) - uncertain"
    else:
        gex_score = 15
        gex_explanation = f"✅ Weak gamma wall ({wall_strength_pct:.0f}% of total GEX) - can break through"

    logic_breakdown['gex_wall_strength'] = {
        'score': gex_score,
        'weight': 25,
        'explanation': gex_explanation
    }
    breakout_score += gex_score

    # FACTOR 3: Price Momentum (20 points max)
    if level_type == 'resistance':
        # Need upward momentum to break resistance
        if price_momentum > 1.0:
            momentum_score = 20
            momentum_explanation = f"✅ Strong upward momentum {price_momentum:+.2f}%"
        elif price_momentum > 0.5:
            momentum_score = 10
            momentum_explanation = f"✅ Positive momentum {price_momentum:+.2f}%"
        elif price_momentum > 0:
            momentum_score = 5
            momentum_explanation = f"⚠️ Weak momentum {price_momentum:+.2f}%"
        else:
            momentum_score = -15
            momentum_explanation = f"❌ Negative momentum {price_momentum:+.2f}% - will reject"
    else:
        # Need downward momentum to break support
        if price_momentum < -1.0:
            momentum_score = 20
            momentum_explanation = f"✅ Strong downward momentum {price_momentum:+.2f}%"
        elif price_momentum < -0.5:
            momentum_score = 10
            momentum_explanation = f"✅ Negative momentum {price_momentum:+.2f}%"
        elif price_momentum < 0:
            momentum_score = 5
            momentum_explanation = f"⚠️ Weak momentum {price_momentum:+.2f}%"
        else:
            momentum_score = -15
            momentum_explanation = f"❌ Positive momentum {price_momentum:+.2f}% - will bounce"

    logic_breakdown['price_momentum'] = {
        'score': momentum_score,
        'weight': 20,
        'explanation': momentum_explanation
    }
    breakout_score += (momentum_score - 10)

    # FACTOR 4: Dealer Hedging Pressure (15 points max)
    if dealer_hedging_pressure > 100:
        hedging_score = 15
        hedging_explanation = f"✅ Massive dealer hedging ${dealer_hedging_pressure:.0f}M pushing price"
    elif dealer_hedging_pressure > 50:
        hedging_score = 10
        hedging_explanation = f"✅ Strong dealer hedging ${dealer_hedging_pressure:.0f}M"
    elif dealer_hedging_pressure > 20:
        hedging_score = 5
        hedging_explanation = f"⚠️ Moderate dealer hedging ${dealer_hedging_pressure:.0f}M"
    else:
        hedging_score = 0
        hedging_explanation = f"⚠️ Minimal dealer hedging ${dealer_hedging_pressure:.0f}M"

    logic_breakdown['dealer_hedging'] = {
        'score': hedging_score,
        'weight': 15,
        'explanation': hedging_explanation
    }
    breakout_score += (hedging_score - 7)

    # FACTOR 5: RSI Positioning (10 points max)
    if level_type == 'resistance':
        # High RSI at resistance = more likely to reject
        if rsi_score > 70:
            rsi_score_points = -10
            rsi_explanation = f"❌ Overbought RSI {rsi_score:.0f} - likely rejection"
        elif rsi_score > 50:
            rsi_score_points = -5
            rsi_explanation = f"⚠️ Elevated RSI {rsi_score:.0f}"
        else:
            rsi_score_points = 10
            rsi_explanation = f"✅ Not overbought RSI {rsi_score:.0f} - can break"
    else:
        # Low RSI at support = more likely to break down
        if rsi_score < -70:
            rsi_score_points = -10
            rsi_explanation = f"❌ Oversold RSI {rsi_score:.0f} - likely bounce"
        elif rsi_score < -50:
            rsi_score_points = -5
            rsi_explanation = f"⚠️ Low RSI {rsi_score:.0f}"
        else:
            rsi_score_points = 10
            rsi_explanation = f"✅ Not oversold RSI {rsi_score:.0f} - can break"

    logic_breakdown['rsi'] = {
        'score': rsi_score_points,
        'weight': 10,
        'explanation': rsi_explanation
    }
    breakout_score += rsi_score_points

    # Normalize to 0-100 range
    breakout_probability = max(0, min(100, breakout_score))
    rejection_probability = 100 - breakout_probability

    # Determine confidence based on consensus of factors
    strong_factors = sum(1 for factor in logic_breakdown.values() if abs(factor['score']) > factor['weight'] * 0.6)
    if strong_factors >= 3:
        confidence = 'high'
    elif strong_factors >= 2:
        confidence = 'medium'
    else:
        confidence = 'low'

    # Generate recommendation
    if breakout_probability > 65:
        recommendation = f"LIKELY BREAKOUT through ${level_price:.2f} {level_type}"
    elif breakout_probability < 35:
        recommendation = f"LIKELY REJECTION at ${level_price:.2f} {level_type}"
    else:
        recommendation = f"UNCERTAIN - {level_type} at ${level_price:.2f} is a coin flip"

    # Identify key factors driving the probability
    key_factors = []
    for factor_name, factor_data in logic_breakdown.items():
        if abs(factor_data['score']) > factor_data['weight'] * 0.5:
            key_factors.append(factor_data['explanation'])

    return {
        'level_type': level_type,
        'level_price': level_price,
        'distance_pct': distance_pct,
        'breakout_probability': round(breakout_probability, 1),
        'rejection_probability': round(rejection_probability, 1),
        'confidence': confidence,
        'logic_breakdown': logic_breakdown,
        'recommendation': recommendation,
        'key_factors': key_factors,
        'total_score': breakout_score
    }


# ============================================================================
# LAYER 1: MULTI-TIMEFRAME RSI ANALYSIS
# ============================================================================

def calculate_rsi(prices: np.ndarray, period: int = 14) -> float:
    """
    Calculate RSI (Relative Strength Index) for given price series

    Args:
        prices: Array of closing prices
        period: RSI period (default 14)

    Returns:
        RSI value (0-100), or 50.0 (neutral) if calculation fails
    """
    try:
        # Validate input
        if prices is None or len(prices) < period + 1:
            return 50.0  # Default neutral if not enough data

        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # Calculate initial averages
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])

        # Smooth using Wilder's method
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        # Final safety check: ensure result is valid float
        result = float(rsi)
        if np.isnan(result) or np.isinf(result):
            return 50.0

        return result
    except Exception as e:
        # If ANY error occurs in RSI calculation, return neutral default
        print(f"⚠️ RSI calculation error: {e}, returning default 50.0")
        return 50.0


def calculate_mtf_rsi_score(price_data: Dict[str, List[Dict]]) -> Dict:
    """
    Calculate RSI across all timeframes with weighted scoring

    Args:
        price_data: Dictionary with timeframe keys ('5m', '15m', '1h', '4h', '1d')
                   Each value is list of dicts with 'close', 'high', 'low', 'volume'

    Returns:
        {
            'score': float (-100 to +100),
            'individual_rsi': dict,
            'aligned_count': dict,
            'coiling_detected': bool
        }
    """
    timeframes = ['5m', '15m', '1h', '4h', '1d']
    weights = {
        '5m': 0.10,
        '15m': 0.15,
        '1h': 0.20,
        '4h': 0.25,
        '1d': 0.30
    }

    rsi_values = {}
    weighted_score = 0

    for tf in timeframes:
        if tf not in price_data or not price_data[tf]:
            rsi_values[tf] = 50.0
            continue

        prices = np.array([bar['close'] for bar in price_data[tf]])
        rsi = calculate_rsi(prices, period=14)

        # Safety check: if RSI is None for any reason, use default 50.0
        if rsi is None:
            rsi = 50.0

        rsi_values[tf] = rsi

        # Normalize to -100 to +100 scale
        normalized = (rsi - 50) * 2
        weighted_score += normalized * weights[tf]

    # Count aligned extremes (handle None values safely)
    overbought_count = sum(1 for v in rsi_values.values() if v is not None and v > 70)
    oversold_count = sum(1 for v in rsi_values.values() if v is not None and v < 30)
    extreme_ob_count = sum(1 for v in rsi_values.values() if v is not None and v > 80)
    extreme_os_count = sum(1 for v in rsi_values.values() if v is not None and v < 20)

    # Detect coiling (RSI extreme but low volatility)
    coiling = detect_coiling(price_data, rsi_values)

    return {
        'score': weighted_score,
        'individual_rsi': rsi_values,
        'aligned_count': {
            'overbought': overbought_count,
            'oversold': oversold_count,
            'extreme_overbought': extreme_ob_count,
            'extreme_oversold': extreme_os_count
        },
        'coiling_detected': coiling
    }


def detect_coiling(price_data: Dict, rsi_values: Dict) -> bool:
    """
    Detect when RSI is extreme but price is compressed (pre-breakout signal)

    Args:
        price_data: Price data for all timeframes
        rsi_values: RSI values for all timeframes

    Returns:
        True if coiling detected, False otherwise
    """
    # Check if RSI extreme on 3+ timeframes (handle None values safely)
    rsi_extreme = any([
        sum(1 for v in rsi_values.values() if v is not None and v > 70) >= 3,
        sum(1 for v in rsi_values.values() if v is not None and v < 30) >= 3
    ])

    if not rsi_extreme:
        return False

    # Check if recent price action is tight (ATR declining)
    if '1d' not in price_data or len(price_data['1d']) < 20:
        return False

    daily_data = price_data['1d'][-20:]

    recent_atr = np.mean([bar['high'] - bar['low'] for bar in daily_data[-5:]])
    longer_atr = np.mean([bar['high'] - bar['low'] for bar in daily_data])

    # Coiling if ATR contracted by >30%
    return recent_atr < (longer_atr * 0.7)


# ============================================================================
# LAYER 2: CURRENT GAMMA WALL ANALYSIS
# ============================================================================

def analyze_current_gamma_walls(current_price: float, gamma_data: Dict) -> Dict:
    """
    Identify nearest gamma walls from CURRENT structure
    (aggregated across all expirations)

    Args:
        current_price: Current SPY price
        gamma_data: Gamma exposure data with expirations

    Returns:
        {
            'call_wall': dict,
            'put_wall': dict,
            'net_gamma_regime': str,
            'all_walls': dict
        }
    """
    # Aggregate gamma across all expirations
    all_call_strikes = {}
    all_put_strikes = {}

    for exp in gamma_data.get('expirations', []):
        for call in exp.get('call_strikes', []):
            strike = call.get('strike')
            # Skip None or invalid strikes
            if strike is None or not isinstance(strike, (int, float)):
                continue
            if strike not in all_call_strikes:
                all_call_strikes[strike] = 0
            all_call_strikes[strike] += call.get('gamma_exposure', 0)

        for put in exp.get('put_strikes', []):
            strike = put.get('strike')
            # Skip None or invalid strikes
            if strike is None or not isinstance(strike, (int, float)):
                continue
            if strike not in all_put_strikes:
                all_put_strikes[strike] = 0
            all_put_strikes[strike] += put.get('gamma_exposure', 0)

    # Validate current_price
    if current_price is None or current_price <= 0:
        # Return empty result if current_price is invalid
        return {
            'call_wall': None,
            'put_wall': None,
            'net_gamma_regime': 'short' if gamma_data.get('net_gamma', 0) < 0 else 'long',
            'net_gamma': gamma_data.get('net_gamma', 0),
            'all_walls': {'calls': [], 'puts': []}
        }

    # Find significant walls (top 20% by absolute gamma)
    if all_call_strikes:
        call_wall_threshold = np.percentile(
            [abs(v) for v in all_call_strikes.values()], 80
        )
    else:
        call_wall_threshold = 0

    if all_put_strikes:
        put_wall_threshold = np.percentile(
            [abs(v) for v in all_put_strikes.values()], 80
        )
    else:
        put_wall_threshold = 0

    significant_calls = [
        {'strike': k, 'gamma': v}
        for k, v in all_call_strikes.items()
        if k is not None and abs(v) >= call_wall_threshold and k > current_price
    ]

    significant_puts = [
        {'strike': k, 'gamma': v}
        for k, v in all_put_strikes.items()
        if k is not None and abs(v) >= put_wall_threshold and k < current_price
    ]

    # Find nearest walls
    nearest_call = min(
        significant_calls,
        key=lambda x: abs(x['strike'] - current_price)
    ) if significant_calls else None

    nearest_put = min(
        significant_puts,
        key=lambda x: abs(x['strike'] - current_price)
    ) if significant_puts else None

    # Format result
    result = {
        'call_wall': {
            'strike': nearest_call['strike'] if nearest_call else None,
            'distance_pct': ((nearest_call['strike'] - current_price) / current_price * 100)
                           if (nearest_call and current_price and current_price != 0) else None,
            'strength': abs(nearest_call['gamma']) if nearest_call else 0,
            'dealer_position': 'short_gamma' if (nearest_call and nearest_call['gamma'] < 0) else 'long_gamma'
        } if nearest_call else None,

        'put_wall': {
            'strike': nearest_put['strike'] if nearest_put else None,
            'distance_pct': ((current_price - nearest_put['strike']) / current_price * 100)
                           if (nearest_put and current_price and current_price != 0) else None,
            'strength': abs(nearest_put['gamma']) if nearest_put else 0,
            'dealer_position': 'short_gamma' if (nearest_put and nearest_put['gamma'] < 0) else 'long_gamma'
        } if nearest_put else None,

        'net_gamma_regime': 'short' if gamma_data.get('net_gamma', 0) < 0 else 'long',
        'net_gamma': gamma_data.get('net_gamma', 0),

        'all_walls': {
            'calls': sorted(significant_calls, key=lambda x: x['strike']),
            'puts': sorted(significant_puts, key=lambda x: x['strike'], reverse=True)
        }
    }

    return result


# ============================================================================
# LAYER 3: GAMMA EXPIRATION ANALYSIS
# ============================================================================

def analyze_gamma_expiration(gamma_data: Dict, current_price: float) -> Dict:
    """
    Analyze which gamma expires when and how landscape changes

    Args:
        gamma_data: Full gamma data with expiration breakdown
        current_price: Current SPY price

    Returns:
        Complete expiration analysis with liberation/false floor candidates
    """
    expiration_timeline = []
    gamma_by_dte = {}

    # Sort expirations by date
    sorted_expirations = sorted(
        gamma_data.get('expirations', []),
        key=lambda x: x['expiration_date']
    )

    for exp in sorted_expirations:
        dte = exp['dte']
        exp_type = exp['expiration_type']

        # Calculate gamma at key strikes for this expiration
        strikes_analysis = []
        all_strikes = {}

        for call in exp.get('call_strikes', []):
            strike = call.get('strike')
            # Skip None or invalid strikes
            if strike is None or not isinstance(strike, (int, float)):
                continue
            if strike not in all_strikes:
                all_strikes[strike] = {'call_gamma': 0, 'put_gamma': 0}
            all_strikes[strike]['call_gamma'] += call.get('gamma_exposure', 0)

        for put in exp.get('put_strikes', []):
            strike = put.get('strike')
            # Skip None or invalid strikes
            if strike is None or not isinstance(strike, (int, float)):
                continue
            if strike not in all_strikes:
                all_strikes[strike] = {'call_gamma': 0, 'put_gamma': 0}
            all_strikes[strike]['put_gamma'] += put.get('gamma_exposure', 0)

        # Find significant strikes for this expiration
        for strike, gammas in all_strikes.items():
            total_gamma = abs(gammas['call_gamma']) + abs(gammas['put_gamma'])

            if total_gamma > 0 and strike is not None:
                # Calculate distance_pct safely
                if current_price and current_price > 0:
                    distance_pct = (strike - current_price) / current_price * 100
                else:
                    distance_pct = 0

                strikes_analysis.append({
                    'strike': strike,
                    'call_gamma': gammas['call_gamma'],
                    'put_gamma': gammas['put_gamma'],
                    'total_gamma': total_gamma,
                    'net_gamma': gammas['call_gamma'] + gammas['put_gamma'],
                    'distance_pct': distance_pct
                })

        # Sort by gamma strength
        strikes_analysis.sort(key=lambda x: x['total_gamma'], reverse=True)

        expiration_timeline.append({
            'expiration_date': exp['expiration_date'],
            'dte': dte,
            'type': exp_type,
            'strikes': strikes_analysis[:10],  # Top 10 strikes
            'total_gamma_expiring': sum(s['total_gamma'] for s in strikes_analysis)
        })

        # Bucket by DTE categories
        if dte == 0:
            dte_bucket = '0dte'
        elif dte <= 2:
            dte_bucket = '0-2dte'
        elif dte <= 7:
            dte_bucket = 'this_week'
        elif dte <= 14:
            dte_bucket = 'next_week'
        elif dte <= 30:
            dte_bucket = 'this_month'
        else:
            dte_bucket = 'beyond'

        if dte_bucket not in gamma_by_dte:
            gamma_by_dte[dte_bucket] = {
                'total_gamma': 0,
                'expirations': []
            }

        gamma_by_dte[dte_bucket]['total_gamma'] += sum(
            s['total_gamma'] for s in strikes_analysis
        )
        gamma_by_dte[dte_bucket]['expirations'].append(exp['expiration_date'])

    # Calculate additional metrics
    expiration_impact = calculate_expiration_impact(expiration_timeline, current_price)
    gamma_persistence = calculate_gamma_persistence(expiration_timeline, current_price)
    liberation_candidates = identify_liberation_setups(
        expiration_timeline, current_price, gamma_data
    )
    false_floor_candidates = identify_false_floors(
        expiration_timeline, current_price, gamma_data
    )

    return {
        'expiration_timeline': expiration_timeline,
        'gamma_by_dte': gamma_by_dte,
        'expiration_impact': expiration_impact,
        'gamma_persistence': gamma_persistence,
        'liberation_candidates': liberation_candidates,
        'false_floor_candidates': false_floor_candidates
    }


def calculate_expiration_impact(expiration_timeline: List[Dict], current_price: float) -> List[Dict]:
    """
    Calculate impact score for each upcoming expiration
    Impact = (Gamma Expiring) × (Proximity to Price) × (DTE Weight)
    """
    impacts = []

    for exp in expiration_timeline:
        if exp['dte'] > 30:
            continue

        # DTE weighting
        if exp['dte'] == 0:
            dte_weight = 5.0
        elif exp['dte'] <= 2:
            dte_weight = 3.0
        elif exp['dte'] <= 7:
            dte_weight = 2.0
        elif exp['dte'] <= 14:
            dte_weight = 1.5
        else:
            dte_weight = 1.0

        # Find strikes near current price (within 5%)
        near_price_gamma = sum(
            s['total_gamma']
            for s in exp['strikes']
            if abs(s['distance_pct']) < 5
        )

        # Calculate impact
        impact_score = near_price_gamma * dte_weight / 1e9  # Normalize to billions

        impacts.append({
            'expiration_date': exp['expiration_date'],
            'dte': exp['dte'],
            'type': exp['type'],
            'impact_score': impact_score,
            'gamma_near_price': near_price_gamma,
            'interpretation': interpret_impact(impact_score)
        })

    return sorted(impacts, key=lambda x: x['impact_score'], reverse=True)


def interpret_impact(score: float) -> str:
    """Translate impact score to human-readable interpretation"""
    if score > 100:
        return 'EXTREME - Major market structure change expected'
    elif score > 50:
        return 'HIGH - Significant impact on price dynamics'
    elif score > 20:
        return 'MODERATE - Noticeable shift in behavior'
    elif score > 5:
        return 'LOW - Minor effect'
    else:
        return 'MINIMAL - Negligible impact'


def calculate_gamma_persistence(expiration_timeline: List[Dict], current_price: float) -> Dict:
    """
    Calculate how much gamma remains at each strike after each expiration
    """
    # Get all unique strikes
    all_strikes = set()
    for exp in expiration_timeline:
        for s in exp['strikes']:
            all_strikes.add(s['strike'])

    persistence_by_strike = {}

    for strike in all_strikes:
        # Calculate total current gamma at this strike
        total_gamma_now = sum(
            sum(s['total_gamma'] for s in exp['strikes'] if s['strike'] == strike)
            for exp in expiration_timeline
        )

        if total_gamma_now == 0:
            continue

        # Simulate gamma after each expiration
        gamma_timeline = [{'date': 'now', 'gamma': total_gamma_now, 'persistence': 1.0}]

        remaining_expirations = sorted(expiration_timeline, key=lambda x: x['dte'])
        cumulative_expired = 0

        for exp in remaining_expirations:
            gamma_expiring = sum(
                s['total_gamma'] for s in exp['strikes'] if s['strike'] == strike
            )
            cumulative_expired += gamma_expiring
            remaining_gamma = total_gamma_now - cumulative_expired
            persistence_ratio = remaining_gamma / total_gamma_now if total_gamma_now > 0 else 0

            gamma_timeline.append({
                'date': exp['expiration_date'],
                'dte': exp['dte'],
                'gamma': remaining_gamma,
                'persistence': persistence_ratio,
                'gamma_expired': cumulative_expired
            })

        persistence_by_strike[strike] = {
            'current_gamma': total_gamma_now,
            'timeline': gamma_timeline,
            'distance_from_price': (strike - current_price) / current_price * 100
        }

    # Find strikes with high decay
    high_decay_strikes = {
        strike: data
        for strike, data in persistence_by_strike.items()
        if any(t['persistence'] < 0.3 and t.get('dte', 999) <= 7 for t in data['timeline'])
    }

    return {
        'by_strike': persistence_by_strike,
        'high_decay_strikes': high_decay_strikes
    }


def identify_liberation_setups(expiration_timeline: List[Dict], current_price: float,
                                gamma_data: Dict) -> List[Dict]:
    """
    Identify strikes where gamma walls will disappear soon (liberation trade)

    Criteria:
    - Significant gamma wall currently exists
    - >70% of that gamma expires within 5 days
    - Price is pinned near that wall
    """
    liberation_setups = []

    # Get current walls
    current_walls = analyze_current_gamma_walls(current_price, gamma_data)

    # Check call wall liberation
    if current_walls['call_wall']:
        call_strike = current_walls['call_wall']['strike']
        distance = current_walls['call_wall']['distance_pct']

        # Is price near this wall? (within 3%)
        if distance is not None and 0 < distance < 3:
            gamma_expiring_soon = 0
            gamma_persisting = 0

            for exp in expiration_timeline:
                if exp['dte'] <= 5:
                    gamma_at_strike = sum(
                        abs(s['call_gamma']) for s in exp['strikes']
                        if s['strike'] == call_strike
                    )
                    gamma_expiring_soon += gamma_at_strike
                else:
                    gamma_at_strike = sum(
                        abs(s['call_gamma']) for s in exp['strikes']
                        if s['strike'] == call_strike
                    )
                    gamma_persisting += gamma_at_strike

            total_gamma = gamma_expiring_soon + gamma_persisting
            expiry_ratio = gamma_expiring_soon / total_gamma if total_gamma > 0 else 0

            if expiry_ratio > 0.7:
                nearest_exp = next((exp for exp in expiration_timeline if exp['dte'] <= 5), None)
                if nearest_exp:
                    liberation_setups.append({
                        'type': 'call_wall_liberation',
                        'strike': call_strike,
                        'current_distance_pct': distance,
                        'gamma_expiring': gamma_expiring_soon,
                        'gamma_persisting': gamma_persisting,
                        'expiry_ratio': expiry_ratio,
                        'liberation_date': nearest_exp['expiration_date'],
                        'dte': nearest_exp['dte'],
                        'signal': f'Liberation setup: {expiry_ratio:.0%} of call wall at ${call_strike} expires in {nearest_exp["dte"]} days. Breakout likely post-expiration.'
                    })

    # Check put wall liberation (less common)
    if current_walls['put_wall']:
        put_strike = current_walls['put_wall']['strike']
        distance = current_walls['put_wall']['distance_pct']

        if distance is not None and 0 < distance < 3:
            gamma_expiring_soon = 0
            gamma_persisting = 0

            for exp in expiration_timeline:
                if exp['dte'] <= 5:
                    gamma_at_strike = sum(
                        abs(s['put_gamma']) for s in exp['strikes']
                        if s['strike'] == put_strike
                    )
                    gamma_expiring_soon += gamma_at_strike
                else:
                    gamma_at_strike = sum(
                        abs(s['put_gamma']) for s in exp['strikes']
                        if s['strike'] == put_strike
                    )
                    gamma_persisting += gamma_at_strike

            total_gamma = gamma_expiring_soon + gamma_persisting
            expiry_ratio = gamma_expiring_soon / total_gamma if total_gamma > 0 else 0

            if expiry_ratio > 0.7:
                nearest_exp = next((exp for exp in expiration_timeline if exp['dte'] <= 5), None)
                if nearest_exp:
                    liberation_setups.append({
                        'type': 'put_wall_liberation',
                        'strike': put_strike,
                        'current_distance_pct': distance,
                        'gamma_expiring': gamma_expiring_soon,
                        'gamma_persisting': gamma_persisting,
                        'expiry_ratio': expiry_ratio,
                        'liberation_date': nearest_exp['expiration_date'],
                        'dte': nearest_exp['dte'],
                        'signal': f'Support removal: {expiry_ratio:.0%} of put wall at ${put_strike} expires in {nearest_exp["dte"]} days. Breakdown risk increases post-expiration.'
                    })

    return liberation_setups


def identify_false_floors(expiration_timeline: List[Dict], current_price: float,
                          gamma_data: Dict) -> List[Dict]:
    """
    Identify put walls that provide temporary support but expire soon

    Criteria:
    - Significant put wall below price
    - >60% of that gamma expires within 5 days
    - Next week's structure shows minimal support
    """
    false_floors = []

    current_walls = analyze_current_gamma_walls(current_price, gamma_data)

    if not current_walls['put_wall']:
        return false_floors

    put_strike = current_walls['put_wall']['strike']
    distance = current_walls['put_wall']['distance_pct']

    # Only consider if put wall is close (within 5%)
    if distance is None or not (0 < distance < 5):
        return false_floors

    # Calculate expiring vs persisting gamma
    gamma_expiring_soon = 0
    gamma_persisting = 0
    gamma_next_week = 0

    for exp in expiration_timeline:
        gamma_at_strike = sum(
            abs(s['put_gamma']) for s in exp['strikes']
            if s['strike'] == put_strike
        )

        if exp['dte'] <= 5:
            gamma_expiring_soon += gamma_at_strike
        elif exp['dte'] <= 14:
            gamma_next_week += gamma_at_strike
        else:
            gamma_persisting += gamma_at_strike

    total_gamma = gamma_expiring_soon + gamma_persisting + gamma_next_week
    expiry_ratio = gamma_expiring_soon / total_gamma if total_gamma > 0 else 0
    next_week_ratio = gamma_next_week / total_gamma if total_gamma > 0 else 0

    # False floor if >60% expires and next week is weak
    if expiry_ratio > 0.6 and next_week_ratio < 0.3:
        nearest_exp = next((exp for exp in expiration_timeline if exp['dte'] <= 5), None)
        if nearest_exp:
            false_floors.append({
                'strike': put_strike,
                'current_distance_pct': distance,
                'gamma_expiring': gamma_expiring_soon,
                'gamma_next_week': gamma_next_week,
                'gamma_persisting': gamma_persisting,
                'expiry_ratio': expiry_ratio,
                'next_week_support_ratio': next_week_ratio,
                'expiration_date': nearest_exp['expiration_date'],
                'dte': nearest_exp['dte'],
                'signal': f'False floor alert: ${put_strike} support is {expiry_ratio:.0%} temporary (expires in {nearest_exp["dte"]} days). Next week support drops to {next_week_ratio:.0%}. Trap for complacent bulls.'
            })

    return false_floors


# ============================================================================
# LAYER 4: FORWARD GEX ANALYSIS (Monthly OPEX Magnets)
# ============================================================================

def analyze_forward_gex(gamma_data: Dict, current_price: float) -> Optional[Dict]:
    """
    Analyze where gamma is BUILDING for future expirations
    Identifies magnets and destinations
    """
    # Focus on monthly and beyond
    monthly_expirations = [
        exp for exp in gamma_data.get('expirations', [])
        if exp.get('expiration_type') in ['monthly', 'quarterly'] and exp.get('dte', 0) >= 7
    ]

    if not monthly_expirations:
        return None

    # Aggregate gamma for monthly strikes
    monthly_strikes = {}

    for exp in monthly_expirations:
        for call in exp.get('call_strikes', []):
            strike = call.get('strike')
            # Skip None or invalid strikes
            if strike is None or not isinstance(strike, (int, float)):
                continue
            if strike not in monthly_strikes:
                monthly_strikes[strike] = {
                    'call_gamma': 0,
                    'put_gamma': 0,
                    'call_oi': 0,
                    'put_oi': 0
                }
            monthly_strikes[strike]['call_gamma'] += call.get('gamma_exposure', 0)
            monthly_strikes[strike]['call_oi'] += call.get('open_interest', 0)

        for put in exp.get('put_strikes', []):
            strike = put.get('strike')
            # Skip None or invalid strikes
            if strike is None or not isinstance(strike, (int, float)):
                continue
            if strike not in monthly_strikes:
                monthly_strikes[strike] = {
                    'call_gamma': 0,
                    'put_gamma': 0,
                    'call_oi': 0,
                    'put_oi': 0
                }
            monthly_strikes[strike]['put_gamma'] += put.get('gamma_exposure', 0)
            monthly_strikes[strike]['put_oi'] += put.get('open_interest', 0)

    # Validate current_price
    if not current_price or current_price <= 0:
        return None

    # Calculate magnet strength for each strike
    magnet_strength = {}

    for strike, data in monthly_strikes.items():
        if strike is None:
            continue
        total_gamma = abs(data['call_gamma']) + abs(data['put_gamma'])
        distance_pct = abs(strike - current_price) / current_price * 100

        # Get DTE for this strike
        dte = min(exp['dte'] for exp in monthly_expirations)

        # DTE multiplier
        if dte <= 7:
            dte_multiplier = 2.0
        elif dte <= 14:
            dte_multiplier = 1.5
        elif dte <= 21:
            dte_multiplier = 1.2
        else:
            dte_multiplier = 1.0

        # Monthly weight
        monthly_multiplier = 2.0

        # OI factor
        oi_factor = (data['call_oi'] + data['put_oi']) / 10000  # Normalize

        # Calculate magnet strength
        strength_score = (total_gamma / 1e9) * oi_factor * dte_multiplier * monthly_multiplier

        magnet_strength[strike] = {
            'strength_score': strength_score,
            'total_gamma': total_gamma,
            'distance_pct': distance_pct,
            'dte': dte,
            'direction': 'above' if strike > current_price else 'below',
            'interpretation': interpret_magnet_strength(strength_score)
        }

    # Sort by strength
    sorted_magnets = sorted(
        [{'strike': k, **v} for k, v in magnet_strength.items()],
        key=lambda x: x['strength_score'],
        reverse=True
    )

    # Identify strongest above and below
    strongest_above = next(
        (m for m in sorted_magnets if m['direction'] == 'above'),
        None
    )
    strongest_below = next(
        (m for m in sorted_magnets if m['direction'] == 'below'),
        None
    )

    # Calculate path of least resistance
    polr = calculate_path_of_least_resistance(
        magnet_strength, current_price, gamma_data
    )

    return {
        'monthly_strikes': monthly_strikes,
        'magnet_strength': magnet_strength,
        'sorted_magnets': sorted_magnets[:10],
        'strongest_above': strongest_above,
        'strongest_below': strongest_below,
        'path_of_least_resistance': polr
    }


def interpret_magnet_strength(score: float) -> str:
    """Translate magnet score to interpretation"""
    if score > 80:
        return 'GRAVITATIONAL FIELD - Market will react strongly'
    elif score > 50:
        return 'STRONG MAGNET - High probability destination'
    elif score > 20:
        return 'MODERATE MAGNET - Factor into analysis'
    else:
        return 'WEAK - Minimal pull'


def calculate_path_of_least_resistance(magnet_strength: Dict, current_price: float,
                                       gamma_data: Dict) -> Dict:
    """
    Determine directional bias based on forward gamma structure
    """
    # Compare gamma above vs below
    strength_above = sum(
        data['strength_score']
        for strike, data in magnet_strength.items()
        if strike > current_price
    )

    strength_below = sum(
        data['strength_score']
        for strike, data in magnet_strength.items()
        if strike < current_price
    )

    net_gamma = gamma_data.get('net_gamma', 0)

    # Determine path
    if strength_above > strength_below * 1.5:
        direction = 'bullish'
        confidence = min(100, (strength_above / (strength_below + 0.01)) * 30)
        explanation = f'Forward magnets {strength_above / (strength_below + 0.01):.1f}x stronger above price'
    elif strength_below > strength_above * 1.5:
        direction = 'bearish'
        confidence = min(100, (strength_below / (strength_above + 0.01)) * 30)
        explanation = f'Forward magnets {strength_below / (strength_above + 0.01):.1f}x stronger below price'
    else:
        direction = 'neutral'
        confidence = 50
        explanation = 'Balanced gamma structure above and below'

    return {
        'direction': direction,
        'confidence': confidence,
        'explanation': explanation,
        'strength_above': strength_above,
        'strength_below': strength_below,
        'net_gamma_regime': 'short' if net_gamma < 0 else 'long'
    }


# ============================================================================
# LAYER 5: COMPLETE REGIME DETECTION (ALL LAYERS COMBINED)
# ============================================================================

def detect_market_regime_complete(
    rsi_analysis: Dict,
    current_walls: Dict,
    expiration_analysis: Dict,
    forward_gex: Optional[Dict],
    volume_ratio: float,
    net_gamma: float,
    vix_data: Optional[Dict] = None,
    zero_gamma_level: float = 0,
    price_data: Optional[Dict] = None,
    current_price: float = 0
) -> Dict:
    """
    MASTER FUNCTION: Combines all layers to detect regime

    Detects:
    1. Gamma Squeeze Cascade (VIX spike + short gamma)
    2. Post-OPEX Regime Flip (gamma structure changing)
    3. Liberation setups (walls expiring)
    4. False floor setups (support disappearing)
    5. 0DTE pin compression plays
    6. Forward destination trades
    7. Original scenarios (pin, rocket, trampoline, trapdoor)
    8. Mean reversion zones

    Returns comprehensive regime analysis
    """
    regime = {
        'primary_type': None,
        'secondary_type': None,
        'confidence': 0,
        'description': '',
        'detailed_explanation': '',
        'trade_direction': None,
        'risk_level': 'medium',
        'timeline': None,
        'price_targets': {},
        'psychology_trap': '',
        'supporting_factors': []
    }

    # Unpack data
    rsi_score = rsi_analysis['score']
    aligned = rsi_analysis['aligned_count']
    coiling = rsi_analysis['coiling_detected']

    call_wall = current_walls.get('call_wall')
    put_wall = current_walls.get('put_wall')

    liberation_setups = expiration_analysis.get('liberation_candidates', [])
    false_floors = expiration_analysis.get('false_floor_candidates', [])

    # Check for 0DTE pin
    has_0dte_pin = check_0dte_pin(expiration_analysis)

    # Get volatility regime if VIX data provided
    vol_regime = None
    if vix_data:
        vol_regime = detect_volatility_regime(vix_data, net_gamma, zero_gamma_level, current_price)

    # Get volume confirmation if price data provided
    vol_confirm = None
    if price_data:
        vol_confirm = calculate_volume_confirmation(price_data, volume_ratio)

    # ========================================
    # SCENARIO 0A: GAMMA SQUEEZE CASCADE (HIGHEST PRIORITY)
    # ========================================
    if vol_regime and vol_regime['regime'] == 'EXPLOSIVE_VOLATILITY':
        # VIX spiked + short gamma + volume surge
        if vol_confirm and vol_confirm['volume_surge'] and abs(rsi_score) < 50:
            # Not already at extreme - room to run
            direction = 'bullish' if rsi_score > 0 else 'bearish' if rsi_score < 0 else 'unknown'

            regime['primary_type'] = 'GAMMA_SQUEEZE_CASCADE'
            regime['confidence'] = 95
            regime['description'] = f'VIX spike + short gamma + volume surge = Dealer amplification active'
            regime['detailed_explanation'] = f"""
GAMMA SQUEEZE CASCADE DETECTED

Current Situation:
- VIX: {vix_data['current']:.1f} (Change: {vix_data['change_pct']:+.1f}%)
- Net Gamma: ${net_gamma/1e9:.1f}B (SHORT - dealers amplify moves)
- Volume: {volume_ratio:.1f}x average (SURGING)
- RSI: {rsi_score:.0f} (Not yet extreme - room to run)

What's Happening:
1. Dealers are SHORT gamma → they must CHASE price moves
2. VIX spike triggers re-hedging → feedback loop begins
3. Small moves become EXPLOSIVE (2-4 hour phenomenon)
4. Direction: {direction.upper()}

This is the most dangerous/profitable regime. Moves accelerate rapidly.
"""
            regime['trade_direction'] = direction
            regime['risk_level'] = 'extreme'
            regime['timeline'] = '2-4 hours typically'
            regime['psychology_trap'] = 'Traders try to fade the move thinking "too fast", but dealer hedging amplifies it further'
            regime['supporting_factors'] = [
                f'VIX spiked {vix_data["change_pct"]:+.1f}%',
                f'Short gamma ${abs(net_gamma)/1e9:.1f}B',
                f'Volume surge {volume_ratio:.1f}x'
            ]
            return regime

    # ========================================
    # SCENARIO 0B: FLIP POINT CRITICAL
    # ========================================
    if vol_regime and vol_regime['at_flip_point']:
        regime['primary_type'] = 'FLIP_POINT_CRITICAL'
        regime['confidence'] = 90
        regime['description'] = f'Price at zero gamma level ${zero_gamma_level:.2f} - hedge flip imminent'
        regime['detailed_explanation'] = f"""
ZERO GAMMA LEVEL CROSSOVER CRITICAL

Current Situation:
- Price: ${current_price:.2f}
- Zero Gamma Level: ${zero_gamma_level:.2f}
- Distance: {vol_regime['flip_point_distance_pct']:.2f}% (CRITICAL!)
- Net Gamma: ${net_gamma/1e9:.1f}B

What's Happening:
When price crosses the zero gamma level, dealers FLIP from one hedging regime to another:
- Below flip point: One type of hedging
- Above flip point: OPPOSITE hedging
- At the flip point: MAXIMUM VOLATILITY

This is where explosive moves originate. Direction unclear but MAGNITUDE will be large.
"""
        regime['trade_direction'] = 'volatile'
        regime['risk_level'] = 'extreme'
        regime['timeline'] = 'Imminent - hours not days'
        regime['psychology_trap'] = 'Traders don\'t see this level, get caught in explosive move when crossing occurs'
        regime['supporting_factors'] = [
            f'Within {vol_regime["flip_point_distance_pct"]:.2f}% of flip point',
            'Maximum dealer hedging sensitivity',
            'Explosive breakout zone'
        ]
        return regime

    # ========================================
    # SCENARIO 0C: POST-OPEX REGIME FLIP
    # ========================================
    # Check if major expiration coming up with significant gamma expiring
    gamma_by_dte = expiration_analysis.get('gamma_by_dte', {})
    this_week_gamma = gamma_by_dte.get('this_week', {}).get('total_gamma', 0)
    next_week_gamma = gamma_by_dte.get('next_week', {}).get('total_gamma', 0)

    # If >50% of gamma expires this week, check for regime flip
    total_gamma = abs(net_gamma)
    if total_gamma > 0:
        expiring_ratio = this_week_gamma / total_gamma

        # Check if net gamma will flip sign after expiration
        if expiring_ratio > 0.5:
            # Simple heuristic: if currently strong directional gamma that's expiring
            currently_strong = abs(net_gamma) > 1e9  # >$1B

            if currently_strong:
                # Determine old and new regime characteristics
                is_long_gamma_now = net_gamma > 0
                gamma_reduction_pct = (this_week_gamma / total_gamma * 100) if total_gamma > 0 else 0
                remaining_gamma = next_week_gamma / 1e9

                # Calculate estimated new regime
                new_gamma_sign = "Long" if remaining_gamma > 0.5 else "Short" if remaining_gamma < -0.5 else "Neutral"

                regime['primary_type'] = 'POST_OPEX_REGIME_FLIP'
                regime['confidence'] = 75
                regime['description'] = f'{expiring_ratio:.0%} of gamma expires this week - market character will change'
                regime['detailed_explanation'] = f"""
POST-OPEX REGIME FLIP APPROACHING - PREPARE FOR MARKET PERSONALITY CHANGE

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 CURRENT GAMMA STRUCTURE (BEFORE OPEX)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Net Gamma: ${net_gamma/1e9:.1f}B ({'LONG GAMMA' if is_long_gamma_now else 'SHORT GAMMA'})
Expires This Week: ${this_week_gamma/1e9:.1f}B ({gamma_reduction_pct:.0f}% of total)
Remains Next Week: ${next_week_gamma/1e9:.1f}B

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 OLD REGIME CHARACTERISTICS (THIS WEEK - BEFORE OPEX)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Regime Type: {'LONG GAMMA - Dealer Dampening' if is_long_gamma_now else 'SHORT GAMMA - Dealer Amplification'}

Market Behavior:
{'''• Price ACTION: Choppy, range-bound, mean-reverting
• Volatility: Compressed, low intraday ranges
• Dealer Hedging: Dealers STABILIZE price movements
• Breakouts: Tend to fail quickly, snap back to center
• RSI: Oscillates frequently between 30-70
• Volume: Lower volume moves get absorbed
• Best Times: Sideways grinding, pin near strikes''' if is_long_gamma_now else '''• Price ACTION: Trending, momentum-driven, gap moves
• Volatility: Expanded, large intraday swings
• Dealer Hedging: Dealers AMPLIFY price movements
• Breakouts: Tend to extend, follow-through strong
• RSI: Can stay extreme (>70 or <30) for days
• Volume: Accelerates moves, feedback loops
• Best Times: Strong directional trends, squeeze conditions'''}

What WORKED This Week:
{'''✅ MEAN REVERSION STRATEGIES (70-80% win rate):
   • Sell premium when RSI hits 65-70 (calls) or 30-35 (puts)
   • Iron Condors: Wide wings (0.10-0.15 delta)
   • Credit Spreads: 0.20 delta short strike, +$1 wide
   • Entry: When price touches GEX walls
   • Exit: 50% profit or 2-3 days (theta decay)
   • Position Size: 3-5% per spread
   • Win Rate: 70-80% (gamma protects you)

✅ SCALPING OSCILLATIONS (60-70% win rate):
   • Buy ATM straddles when price is dead center
   • Sell when price moves 0.5% either direction
   • Hold time: 30 minutes to 2 hours
   • Works best: 10am-2pm ET

✅ 0DTE CALENDAR SPREADS:
   • Sell 0DTE options, buy 1-2 DTE
   • Strike: ATM or near pin level
   • Theta decay accelerates afternoon
   • Exit: By 3:30pm to avoid gamma risk''' if is_long_gamma_now else '''✅ MOMENTUM/BREAKOUT STRATEGIES (65-75% win rate):
   • Buy breakouts above resistance (0.40-0.50 delta calls)
   • Buy dips near flip point (0.40-0.50 delta puts)
   • Directional spreads: Debit spreads, not credit
   • Entry: After confirmation (volume surge + follow-through)
   • Exit: Trail stops, let winners run
   • Position Size: 2-3% per trade (vol is high!)
   • Win Rate: 65-75% IF you follow trend

✅ VOLATILITY EXPANSION PLAYS (70-80% win rate):
   • Long ATM straddles into known events
   • Long gamma during gap openings
   • Buy dips aggressively (dealers chase you)
   • Hold time: Several hours to days

✅ TREND CONTINUATION:
   • Add to winners (pyramid)
   • Use wide stops (volatility is high)
   • Target: 2-3x risk/reward
   • Works best: Morning gap continuation'''}

What FAILED This Week:
{'''❌ Buying breakouts (dealers sell into strength)
❌ Holding overnight directional positions
❌ Wide stop losses (get chopped out)
❌ Fighting the range (trying to force trends)
❌ Naked options (theta crushes you)''' if is_long_gamma_now else '''❌ Selling premium (gamma squeezes you)
❌ Fading moves (dealer amplification runs you over)
❌ Tight stops (volatility whipsaws you out)
❌ Iron condors (wings get tested frequently)
❌ Mean reversion (trends extend beyond logic)'''}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🟢 NEW REGIME CHARACTERISTICS (NEXT WEEK - AFTER OPEX)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Estimated Regime: {new_gamma_sign} GAMMA ({remaining_gamma:+.1f}B estimated)
Regime Type: {'''LONG GAMMA - Dealer Dampening''' if new_gamma_sign == 'Long' else '''SHORT GAMMA - Dealer Amplification''' if new_gamma_sign == 'Short' else '''NEUTRAL - Mixed Behavior'''}

Expected Market Behavior:
{'''• Price ACTION: Will become CHOPPY and range-bound
• Volatility: Will COMPRESS significantly
• Dealer Hedging: Dealers will STABILIZE moves
• Breakouts: Will likely FAIL and snap back
• RSI: Will oscillate more frequently
• Volume: Lower volume will matter less
• Environment: Range trading, mean reversion dominant''' if new_gamma_sign == 'Long' else '''• Price ACTION: Will become TRENDING and momentum-driven
• Volatility: Will EXPAND significantly
• Dealer Hedging: Dealers will AMPLIFY moves
• Breakouts: Will have FOLLOW-THROUGH
• RSI: Can stay extreme for extended periods
• Volume: Will accelerate directional moves
• Environment: Momentum trading, trend following dominant''' if new_gamma_sign == 'Short' else '''• Price ACTION: Mixed, depends on positioning
• Volatility: Moderate, watch for regime shifts
• Dealer Hedging: Minimal impact either way
• Breakouts: Test carefully, wait for confirmation
• RSI: Standard interpretation applies
• Volume: More important for confirmation
• Environment: Technical analysis more reliable'''}

What Will WORK Next Week:
{'''✅ PREMIUM SELLING STRATEGIES (Target 70-80% win rate):

   1. IRON CONDORS (Recommended)
      • Short Strikes: 0.20 delta (closer to money in low vol)
      • Long Strikes: +$2 width ($1 in low IV)
      • Expiration: Friday (5-7 DTE optimal)
      • Entry: Monday or Tuesday morning
      • Exit: 50% profit or Thursday 3pm
      • Size: 3-5% account risk per spread
      • Probability: ~75% profit
      • Example: SPY at $575
        - Sell $577 call / Buy $579 call
        - Sell $573 put / Buy $571 put
        - Credit: $0.50-0.70
        - Max profit: $50-70 per spread
        - Max loss: $130-150 per spread

   2. CREDIT SPREADS (Safer)
      • Direction: Counter to any small trend
      • Short Strike: 0.25 delta
      • Width: +$1 to +$1.50
      • Expiration: 5-7 DTE
      • Entry: When RSI touches 60 or 40
      • Exit: 60% profit or 3-4 days
      • Size: 2-4% per spread
      • Probability: ~70% profit

   3. STRADDLE SELLING (Advanced)
      • Strike: ATM (current price)
      • Expiration: 7-10 DTE
      • Entry: VIX > 15, market dead center
      • Exit: 50% profit OR price moves 2%
      • Size: 1-2% (defined risk version)
      • Probability: ~65% profit
      • Hedge: Buy further OTM protection

   4. CALENDAR SPREADS (Theta farmers)
      • Sell: Weekly (3-5 DTE)
      • Buy: Next week (10-12 DTE)
      • Strike: ATM or pin level
      • Entry: Monday-Wednesday
      • Exit: Friday close (avoid gamma risk)
      • Size: 2-3% per spread

   Time Management:
   • Best entry: Monday 10am-11am
   • Avoid: Friday morning (gamma increases)
   • Exit before: Thursday 3pm (de-risk)''' if new_gamma_sign == 'Long' else '''✅ DIRECTIONAL/MOMENTUM STRATEGIES (Target 65-75% win rate):

   1. TREND FOLLOWING (Recommended)
      • Direction: WITH the prevailing trend
      • Strikes: 0.40-0.50 delta (first OTM)
      • Expiration: 2-3 weeks (14-21 DTE)
      • Entry: After confirmed breakout + volume
      • Exit: Trail stop 25% below entry OR target hit
      • Size: 2-3% per trade
      • Probability: ~70% IF trend confirmed
      • Example: SPY trending up
        - Buy $580 calls (0.45 delta)
        - Entry: After break above $577 on volume
        - Target: $585 (+$5 move)
        - Stop: $575 (-$2 move)
        - Risk: $200 per contract
        - Reward: $500 per contract (2.5:1)

   2. DEBIT SPREADS (Defined risk momentum)
      • Buy: 0.50 delta (ATM)
      • Sell: 0.25 delta (OTM)
      • Width: $3-5 depending on price
      • Expiration: 14-21 DTE
      • Entry: Pullback to support/resistance
      • Exit: 100-150% profit OR stop hit
      • Size: 3-4% per spread
      • Probability: ~65% profit
      • Example: Bullish setup
        - Buy $575 call
        - Sell $580 call
        - Debit: $2.50
        - Max profit: $2.50 (100% gain)
        - Max loss: $2.50

   3. ATM STRADDLES (Volatility expansion)
      • Strike: ATM (current price)
      • Expiration: 7-14 DTE
      • Entry: Before known catalyst OR at flip point
      • Exit: When one side reaches 50-75% profit
      • Size: 1-2% (premium is expensive!)
      • Probability: ~60% profit
      • Works best: VIX rising environment

   4. BREAKOUT BUYING (Pure directional)
      • Strike: 0.30-0.40 delta
      • Expiration: 2-4 weeks
      • Entry: Break of key level + volume surge
      • Exit: Trail stop OR 2-3x gain
      • Size: 2-3% per trade
      • Add: On continuation (pyramid)

   Risk Management:
   • Stop loss: 30-40% (vol is high)
   • Position sizing: SMALLER than usual
   • Scaling: Add to winners, cut losers fast
   • Time: Hold winners for days/weeks''' if new_gamma_sign == 'Short' else '''✅ BALANCED/TECHNICAL STRATEGIES:

   • Use standard technical analysis
   • Wait for clear signals before entry
   • Smaller position sizes (2-3%)
   • Quick profit taking (25-50%)
   • Both credit and debit spreads viable
   • Focus on high-probability setups only
   • Probability: ~60% (lower in neutral regime)'''}

What Will FAIL Next Week:
{'''❌ Trend following (ranges will chop you)
❌ Breakout buying (fakeouts increase)
❌ Holding overnight directional (gaps fade)
❌ Wide stops (will get hit in chop)
❌ Naked long options (theta decay accelerates)
❌ Fighting the pin (dealers defend strikes)''' if new_gamma_sign == 'Long' else '''❌ Selling naked premium (gamma squeezes)
❌ Iron condors (wings will be tested)
❌ Tight stops (volatility whipsaws)
❌ Fading strong moves (amplification continues)
❌ Mean reversion (trends persist longer)
❌ Short-dated options (gamma risk too high)''' if new_gamma_sign == 'Short' else '''❌ Overleveraging (regime unclear)
❌ Stubborn holding (be nimble)
❌ Pattern-based trading (less reliable)'''}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ THE PSYCHOLOGY TRAP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

What Traders Do WRONG:
1. Continue using old regime strategies after OPEX
2. Expect same price behavior that worked last week
3. Keep same position sizes despite regime change
4. Ignore the gamma structure shift
5. Get angry when "it's not working anymore"

The REALITY:
• RSI 70 meant "sell" last week → might mean "beginning of trend" next week
• Breakouts that failed last week → might follow through next week
• Strategies that won 75% → might win only 25% next week
• Your edge CHANGED when gamma expired

How to AVOID the Trap:
1. WAIT 1-2 days after OPEX to assess new regime
2. TEST small positions before going full size
3. Adjust strategy based on observed behavior (not assumptions)
4. Track what works THIS week, not last week
5. Be willing to admit the regime changed and adapt

CRITICAL: The market doesn't care about your last week's P&L.
The gamma that created your edge is GONE. New structure = new strategies.
"""
                regime['trade_direction'] = 'regime_dependent'
                regime['risk_level'] = 'high'
                regime['timeline'] = f'Regime flip within {min([exp["dte"] for exp in expiration_analysis.get("expiration_timeline", [])] or [5])} days'
                regime['psychology_trap'] = 'Trading the old regime after gamma structure has shifted - using strategies that no longer have edge'
                regime['supporting_factors'] = [
                    f'{expiring_ratio:.0%} of gamma expires soon',
                    'Major structural shift approaching',
                    'Market personality change imminent',
                    f'Old regime: {"Long gamma dampening" if is_long_gamma_now else "Short gamma amplification"}',
                    f'New regime: {new_gamma_sign} gamma behavior expected'
                ]
                return regime

    # ========================================
    # SCENARIO 1: Liberation Trade
    # ========================================
    if liberation_setups:
        for setup in liberation_setups:
            if setup['type'] == 'call_wall_liberation':
                if aligned['overbought'] >= 3 and coiling:
                    regime['primary_type'] = 'LIBERATION_TRADE'
                    regime['confidence'] = min(100, setup['expiry_ratio'] * 100 + 20)
                    regime['description'] = f"Call wall liberation setup at ${setup['strike']}"
                    regime['detailed_explanation'] = f"""{setup['signal']}

Current situation:
- Price pinned near ${setup['strike']} (within {setup['current_distance_pct']:.1f}%)
- RSI coiling extreme on {aligned['overbought']} timeframes
- {setup['expiry_ratio']:.0%} of gamma expires in {setup['dte']} days
- Energy building for breakout post-expiration

Forward view: {forward_gex['strongest_above']['interpretation'] if forward_gex and forward_gex.get('strongest_above') else 'Open space above'}"""

                    regime['trade_direction'] = 'bullish_post_expiration'
                    regime['risk_level'] = 'medium'
                    regime['timeline'] = f"Liberation expected {setup['dte']} days"
                    regime['price_targets'] = {
                        'current': setup['strike'],
                        'post_liberation': forward_gex['strongest_above']['strike'] if forward_gex and forward_gex.get('strongest_above') else setup['strike'] * 1.05
                    }
                    regime['psychology_trap'] = f"Newbies short 'overbought' at ${setup['strike']}, not realizing wall expires in {setup['dte']} days"
                    regime['supporting_factors'] = [
                        'RSI coiling - energy building',
                        f'{setup["expiry_ratio"]:.0%} gamma expires soon'
                    ]
                    return regime

    # ========================================
    # SCENARIO 2: False Floor
    # ========================================
    if false_floors:
        for setup in false_floors:
            if aligned['oversold'] < 2:
                regime['primary_type'] = 'FALSE_FLOOR'
                regime['confidence'] = min(100, setup['expiry_ratio'] * 80 + 20)
                regime['description'] = f"False floor at ${setup['strike']} - temporary support expiring"
                regime['detailed_explanation'] = f"""{setup['signal']}

Current situation:
- Price {setup['current_distance_pct']:.1f}% above put wall at ${setup['strike']}
- {setup['expiry_ratio']:.0%} expires in {setup['dte']} days
- Next week support: {setup['next_week_support_ratio']:.0%}
- RSI NOT oversold (complacency)"""

                regime['trade_direction'] = 'bearish_post_expiration'
                regime['risk_level'] = 'high'
                regime['timeline'] = f"Support removal in {setup['dte']} days"
                regime['psychology_trap'] = f"Bulls feel safe at ${setup['strike']}, but {setup['expiry_ratio']:.0%} expires soon"
                regime['supporting_factors'] = [
                    'Temporary support',
                    'Weak forward structure',
                    'Complacency'
                ]
                return regime

    # ========================================
    # SCENARIO 3: 0DTE Pin
    # ========================================
    if has_0dte_pin and coiling:
        regime['primary_type'] = 'ZERO_DTE_PIN'
        regime['confidence'] = 75
        regime['description'] = '0DTE gamma pin - volatility compressed'
        regime['detailed_explanation'] = f"""Massive 0DTE gamma creating pin TODAY.

0DTE gamma: ${has_0dte_pin['total_gamma'] / 1e9:.1f}B
Pin range: ${has_0dte_pin['pin_range'][0]:.0f}-${has_0dte_pin['pin_range'][1]:.0f}
RSI coiling on {aligned['overbought'] + aligned['oversold']} timeframes

Today: Pin until 4PM ET
Tomorrow: Price free to move"""

        regime['trade_direction'] = 'expansion_tomorrow'
        regime['risk_level'] = 'medium'
        regime['timeline'] = 'Compressed today, expansion tomorrow'
        regime['psychology_trap'] = 'Market looks dead but compression resolves violently tomorrow'
        regime['supporting_factors'] = ['0DTE pin', 'RSI coiling']
        return regime

    # ========================================
    # SCENARIO 4: Forward Destination Trade
    # ========================================
    if forward_gex and forward_gex.get('strongest_above'):
        magnet = forward_gex['strongest_above']

        if (aligned['overbought'] >= 3 and
            magnet['strength_score'] > 50 and
            call_wall and call_wall.get('distance_pct', 999) < 3):

            regime['primary_type'] = 'DESTINATION_TRADE'
            regime['confidence'] = min(100, magnet['strength_score'])
            regime['description'] = f"Market pulled toward ${magnet['strike']} monthly magnet"
            regime['detailed_explanation'] = f"""Forward destination detected.

Current: ${current_price:.2f}
RSI extreme on {aligned['overbought']} timeframes
Call wall at ${call_wall['strike']}

Forward magnet:
- Strike: ${magnet['strike']}
- Distance: {magnet['distance_pct']:.1f}%
- Strength: {magnet['strength_score']:.0f} ({magnet['interpretation']})
- Timeline: {magnet['dte']} days"""

            regime['trade_direction'] = 'bullish'
            regime['risk_level'] = 'medium'
            regime['timeline'] = f"{magnet['dte']} days to destination"
            regime['price_targets'] = {
                'current': call_wall['strike'],
                'destination': magnet['strike']
            }
            regime['psychology_trap'] = f"Newbies short 'overbought' not seeing ${magnet['strike']} magnet pulling price"
            regime['supporting_factors'] = [
                f"Monthly magnet: {magnet['strength_score']:.0f}",
                f"RSI extreme on {aligned['overbought']} TFs"
            ]
            return regime

    # ========================================
    # ORIGINAL SCENARIOS
    # ========================================

    # Pin at Call Wall
    if (rsi_score > 50 and aligned['overbought'] >= 3 and
        call_wall and call_wall.get('distance_pct', 999) < 2 and
        net_gamma < 0):

        regime['primary_type'] = 'PIN_AT_CALL_WALL'
        regime['confidence'] = min(100, aligned['overbought'] * 20)
        regime['description'] = f"RSI extreme, dealers buying into call wall ${call_wall['strike']}"
        regime['trade_direction'] = 'neutral'
        regime['risk_level'] = 'high'
        regime['psychology_trap'] = 'Perfect short for newbies, but dealer buying creates magnet'
        return regime

    # Explosive Continuation
    elif (rsi_score > 50 and aligned['overbought'] >= 3 and
          call_wall and call_wall.get('distance_pct', 999) < -0.5 and
          volume_ratio > 1.2 and net_gamma < 0):

        regime['primary_type'] = 'EXPLOSIVE_CONTINUATION'
        regime['confidence'] = min(100, aligned['overbought'] * 15 + volume_ratio * 30)
        regime['description'] = 'Broke call wall with volume - dealers chasing'
        regime['trade_direction'] = 'bullish'
        regime['risk_level'] = 'medium'
        regime['psychology_trap'] = 'Newbies short overbought but momentum has destination'
        return regime

    # Pin at Put Wall
    elif (rsi_score < -50 and aligned['oversold'] >= 3 and
          put_wall and put_wall.get('distance_pct', 999) < 2 and
          net_gamma < 0):

        regime['primary_type'] = 'PIN_AT_PUT_WALL'
        regime['confidence'] = min(100, aligned['oversold'] * 20)
        regime['description'] = f"Oversold at put wall ${put_wall['strike']} - trampoline"
        regime['trade_direction'] = 'bullish'
        regime['risk_level'] = 'medium'
        regime['psychology_trap'] = 'Bears hold shorts expecting breakdown, get squeezed'
        return regime

    # Capitulation Cascade
    elif (rsi_score < -50 and aligned['oversold'] >= 3 and
          put_wall and put_wall.get('distance_pct', 999) < -0.5 and
          volume_ratio > 2.0):

        regime['primary_type'] = 'CAPITULATION_CASCADE'
        regime['confidence'] = min(100, aligned['oversold'] * 15 + volume_ratio * 35)
        regime['description'] = 'Broke put wall with volume - potential capitulation'
        regime['trade_direction'] = 'watch'
        regime['risk_level'] = 'extreme'
        regime['psychology_trap'] = 'Both sides trapped - cascade or violent reversal'
        return regime

    # Mean Reversion Zone
    elif ((rsi_score > 60 or rsi_score < -60) and net_gamma > 0):
        regime['primary_type'] = 'MEAN_REVERSION_ZONE'
        regime['confidence'] = min(100, abs(rsi_score) + 20)
        regime['description'] = 'Long gamma regime - RSI extremes matter'
        regime['trade_direction'] = 'fade' if rsi_score > 0 else 'buy'
        regime['risk_level'] = 'low'
        regime['psychology_trap'] = 'Market behaves rationally - fade extremes works'
        return regime

    # Short Gamma Momentum (NEW - makes NEGATIVE_GAMMA actionable)
    elif (net_gamma < -500_000_000 and abs(rsi_score) < 50):
        # Significant short gamma + not yet at extremes = tradeable momentum
        # Use VIX regime to determine risk level
        vix_risk = vol_regime['risk_level'] if vol_regime else 'medium'

        # Determine direction bias from RSI
        if rsi_score > 10:
            direction = 'bullish'
            bias_desc = 'upside bias'
        elif rsi_score < -10:
            direction = 'bearish'
            bias_desc = 'downside bias'
        else:
            direction = 'momentum'
            bias_desc = 'directional breakout'

        regime['primary_type'] = 'SHORT_GAMMA_MOMENTUM'
        regime['confidence'] = 65 + int(abs(net_gamma) / 1e9 * 5)  # Higher gamma = higher confidence
        regime['description'] = f'Dealers short ${abs(net_gamma)/1e9:.1f}B gamma - amplification mode with {bias_desc}'
        regime['detailed_explanation'] = f"""
SHORT GAMMA MOMENTUM REGIME

Current Situation:
- Net Gamma: ${net_gamma/1e9:.1f}B (SHORT - dealers amplify moves)
- RSI: {rsi_score:.0f} (Room to run - not yet extreme)
- Volume: {volume_ratio:.1f}x average
- VIX Risk: {vix_risk}

Dealer Mechanics:
When dealers are net SHORT gamma, they must HEDGE in the direction of price movement:
- Price moves UP → Dealers must BUY → Pushes price HIGHER
- Price moves DOWN → Dealers must SELL → Pushes price LOWER

This creates AMPLIFICATION - small moves become bigger moves.

Trading Strategy:
1. MOMENTUM is your friend - don't fade moves in short gamma
2. Breakouts have FOLLOW-THROUGH (dealers chase)
3. Use wider stops - volatility is higher
4. Trade WITH the trend, not against it
5. Watch for volume confirmation (need 2x+ for conviction)

Best Setups:
- Buy breakouts above resistance on volume
- Use 0.4-0.5 delta options (first OTM strike)
- Trail stops - let winners run
- Exit if RSI hits extreme (>75 or <25)

Risk:
- Moves can reverse just as quickly (dealer hedging works both ways)
- Avoid overnight holds unless strong trend
- {vix_risk} volatility environment
"""
        regime['trade_direction'] = direction
        regime['risk_level'] = vix_risk
        regime['timeline'] = 'Intraday to 2-3 days'
        regime['psychology_trap'] = 'Traders try to fade "overbought/oversold" but dealer amplification extends moves beyond logic'
        regime['supporting_factors'] = [
            f'Short gamma ${abs(net_gamma)/1e9:.1f}B',
            f'RSI {rsi_score:.0f} (not extreme)',
            f'Volume {volume_ratio:.1f}x',
            'Dealer amplification active'
        ]

        # Add price targets if walls exist
        if call_wall and call_wall.get('strike'):
            regime['price_targets'] = {
                'resistance': call_wall['strike'],
                'support': put_wall['strike'] if put_wall and put_wall.get('strike') else current_price * 0.97
            }

        return regime

    # Default: Neutral
    else:
        regime['primary_type'] = 'NEUTRAL'
        regime['confidence'] = 50
        regime['description'] = 'No clear regime pattern detected'
        return regime


def check_0dte_pin(expiration_analysis: Dict) -> Optional[Dict]:
    """Check if significant 0DTE gamma is creating pin effect"""
    dte_buckets = expiration_analysis.get('gamma_by_dte', {})

    zero_dte_gamma = dte_buckets.get('0dte', {}).get('total_gamma', 0)
    next_week_gamma = dte_buckets.get('next_week', {}).get('total_gamma', 1)

    # If 0DTE is >50% of next week's gamma, it's significant
    if zero_dte_gamma > next_week_gamma * 0.5:
        timeline = expiration_analysis.get('expiration_timeline', [])
        zero_dte_exp = next((exp for exp in timeline if exp['dte'] == 0), None)

        if zero_dte_exp:
            strikes = sorted([s['strike'] for s in zero_dte_exp['strikes'][:5]])
            return {
                'total_gamma': zero_dte_gamma,
                'pin_range': (min(strikes), max(strikes))
            }

    return None


# ============================================================================
# MASTER ANALYSIS FUNCTION
# ============================================================================

def analyze_current_market_complete(
    current_price: float,
    price_data: Dict[str, List[Dict]],
    gamma_data: Dict,
    volume_ratio: float
) -> Dict:
    """
    MASTER FUNCTION - Complete market analysis with all layers

    Args:
        current_price: Current SPY price
        price_data: OHLCV data for all timeframes
        gamma_data: Complete gamma exposure data with expirations
        volume_ratio: Current volume / 20-day average volume

    Returns:
        Complete analysis with regime, signals, and visualizations
    """
    timestamp = datetime.now()

    # Layer 0: VIX and Volatility Analysis (NEW)
    vix_data = fetch_vix_data()
    zero_gamma_level = gamma_data.get('flip_point', 0)

    # Layer 1: RSI Analysis
    rsi_analysis = calculate_mtf_rsi_score(price_data)

    # Layer 2: Current Gamma Walls
    current_walls = analyze_current_gamma_walls(current_price, gamma_data)

    # Layer 3: Gamma Expiration Analysis
    expiration_analysis = analyze_gamma_expiration(gamma_data, current_price)

    # Layer 4: Forward GEX / Monthly Magnets
    forward_gex = analyze_forward_gex(gamma_data, current_price)

    # Layer 5: Complete Regime Detection (with NEW parameters)
    regime = detect_market_regime_complete(
        rsi_analysis,
        current_walls,
        expiration_analysis,
        forward_gex,
        volume_ratio,
        gamma_data.get('net_gamma', 0),
        vix_data=vix_data,
        zero_gamma_level=zero_gamma_level,
        price_data=price_data,
        current_price=current_price
    )

    # Determine alert level
    alert_level = determine_alert_level(regime, expiration_analysis)

    # Calculate volatility regime for display
    volatility_regime = detect_volatility_regime(vix_data, gamma_data.get('net_gamma', 0), zero_gamma_level, current_price)

    return {
        'timestamp': timestamp.isoformat(),
        'spy_price': current_price,

        # Core analysis
        'regime': regime,
        'rsi_analysis': rsi_analysis,
        'current_walls': current_walls,
        'expiration_analysis': expiration_analysis,
        'forward_gex': forward_gex,
        'volume_ratio': volume_ratio,

        # NEW: VIX and volatility data
        'vix_data': vix_data,
        'zero_gamma_level': zero_gamma_level,
        'volatility_regime': volatility_regime,

        # Alert
        'alert_level': alert_level
    }


def determine_alert_level(regime: Dict, expiration_analysis: Dict) -> Dict:
    """Determine if situation warrants user alert"""
    confidence = regime['confidence']
    risk = regime['risk_level']

    # Check if liberation/false floor imminent
    urgent_expiration = False
    if expiration_analysis.get('liberation_candidates'):
        for setup in expiration_analysis['liberation_candidates']:
            if setup.get('dte', 999) <= 2:
                urgent_expiration = True

    if expiration_analysis.get('false_floor_candidates'):
        for setup in expiration_analysis['false_floor_candidates']:
            if setup.get('dte', 999) <= 2:
                urgent_expiration = True

    # Determine level
    if (confidence > 80 and risk in ['high', 'extreme']) or urgent_expiration:
        return {
            'level': 'CRITICAL',
            'reason': 'High confidence + high risk or imminent expiration event'
        }
    elif confidence > 70:
        return {
            'level': 'HIGH',
            'reason': 'Strong signal detected'
        }
    elif confidence > 50:
        return {
            'level': 'MEDIUM',
            'reason': 'Moderate signal'
        }
    else:
        return {
            'level': 'LOW',
            'reason': 'Weak or unclear signal'
        }


# ============================================================================
# DATABASE PERSISTENCE FUNCTIONS
# ============================================================================

def save_regime_signal_to_db(analysis: Dict) -> int:
    """Save regime analysis to database"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    regime = analysis['regime']
    rsi = analysis['rsi_analysis']
    walls = analysis['current_walls']
    exp = analysis['expiration_analysis']
    fwd = analysis.get('forward_gex')

    # Extract liberation setup
    lib_setup = exp.get('liberation_candidates', [{}])[0] if exp.get('liberation_candidates') else {}
    false_floor = exp.get('false_floor_candidates', [{}])[0] if exp.get('false_floor_candidates') else {}

    # Extract VIX data
    vix = analysis.get('vix_data', {})
    vol_regime = analysis.get('volatility_regime', {})

    try:
        c.execute('''
            INSERT INTO regime_signals (
                timestamp, spy_price, primary_regime_type, secondary_regime_type,
                confidence_score, trade_direction, risk_level, description,
                detailed_explanation, psychology_trap,
                rsi_5m, rsi_15m, rsi_1h, rsi_4h, rsi_1d, rsi_score,
                rsi_aligned_overbought, rsi_aligned_oversold, rsi_coiling,
                nearest_call_wall, call_wall_distance_pct, call_wall_strength,
                nearest_put_wall, put_wall_distance_pct, put_wall_strength,
                net_gamma, net_gamma_regime,
                zero_dte_gamma, gamma_expiring_this_week, gamma_expiring_next_week,
                liberation_setup_detected, liberation_target_strike, liberation_expiry_date,
                false_floor_detected, false_floor_strike, false_floor_expiry_date,
                monthly_magnet_above, monthly_magnet_above_strength,
                monthly_magnet_below, monthly_magnet_below_strength,
                path_of_least_resistance, polr_confidence,
                volume_ratio, target_price_near, target_price_far, target_timeline_days,
                vix_current, vix_change_pct, vix_spike_detected,
                zero_gamma_level, volatility_regime, at_flip_point
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            analysis['timestamp'], analysis['spy_price'],
            regime['primary_type'], regime.get('secondary_type'),
            regime['confidence'], regime['trade_direction'], regime['risk_level'],
            regime['description'], regime['detailed_explanation'], regime['psychology_trap'],
            rsi['individual_rsi'].get('5m'), rsi['individual_rsi'].get('15m'),
            rsi['individual_rsi'].get('1h'), rsi['individual_rsi'].get('4h'),
            rsi['individual_rsi'].get('1d'), rsi['score'],
            rsi['aligned_count']['overbought'], rsi['aligned_count']['oversold'],
            1 if rsi['coiling_detected'] else 0,
            walls.get('call_wall', {}).get('strike') if walls.get('call_wall') else None,
            walls.get('call_wall', {}).get('distance_pct') if walls.get('call_wall') else None,
            walls.get('call_wall', {}).get('strength') if walls.get('call_wall') else None,
            walls.get('put_wall', {}).get('strike') if walls.get('put_wall') else None,
            walls.get('put_wall', {}).get('distance_pct') if walls.get('put_wall') else None,
            walls.get('put_wall', {}).get('strength') if walls.get('put_wall') else None,
            walls.get('net_gamma'), walls.get('net_gamma_regime'),
            exp['gamma_by_dte'].get('0dte', {}).get('total_gamma'),
            exp['gamma_by_dte'].get('this_week', {}).get('total_gamma'),
            exp['gamma_by_dte'].get('next_week', {}).get('total_gamma'),
            1 if lib_setup else 0,
            lib_setup.get('strike'), lib_setup.get('liberation_date'),
            1 if false_floor else 0,
            false_floor.get('strike'), false_floor.get('expiration_date'),
            fwd.get('strongest_above', {}).get('strike') if fwd else None,
            fwd.get('strongest_above', {}).get('strength_score') if fwd else None,
            fwd.get('strongest_below', {}).get('strike') if fwd else None,
            fwd.get('strongest_below', {}).get('strength_score') if fwd else None,
            fwd.get('path_of_least_resistance', {}).get('direction') if fwd else None,
            fwd.get('path_of_least_resistance', {}).get('confidence') if fwd else None,
            analysis['volume_ratio'],
            regime.get('price_targets', {}).get('current'),
            regime.get('price_targets', {}).get('destination'),
            regime.get('price_targets', {}).get('timeline_days'),
            vix.get('current'), vix.get('change_pct'),
            1 if vix.get('spike_detected') else 0,
            analysis.get('zero_gamma_level'),
            vol_regime.get('regime'),
            1 if vol_regime.get('at_flip_point') else 0
        ))
    except sqlite3.OperationalError as e:
        # If columns don't exist yet, try without VIX fields (backward compatibility)
        print(f"Warning: Database schema may need updating for VIX fields: {e}")
        c.execute('''
            INSERT INTO regime_signals (
                timestamp, spy_price, primary_regime_type, secondary_regime_type,
                confidence_score, trade_direction, risk_level, description,
                detailed_explanation, psychology_trap,
                rsi_5m, rsi_15m, rsi_1h, rsi_4h, rsi_1d, rsi_score,
                rsi_aligned_overbought, rsi_aligned_oversold, rsi_coiling,
                nearest_call_wall, call_wall_distance_pct, call_wall_strength,
                nearest_put_wall, put_wall_distance_pct, put_wall_strength,
                net_gamma, net_gamma_regime,
                zero_dte_gamma, gamma_expiring_this_week, gamma_expiring_next_week,
                liberation_setup_detected, liberation_target_strike, liberation_expiry_date,
                false_floor_detected, false_floor_strike, false_floor_expiry_date,
                monthly_magnet_above, monthly_magnet_above_strength,
                monthly_magnet_below, monthly_magnet_below_strength,
                path_of_least_resistance, polr_confidence,
                volume_ratio, target_price_near, target_price_far, target_timeline_days
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            analysis['timestamp'], analysis['spy_price'],
            regime['primary_type'], regime.get('secondary_type'),
            regime['confidence'], regime['trade_direction'], regime['risk_level'],
            regime['description'], regime['detailed_explanation'], regime['psychology_trap'],
            rsi['individual_rsi'].get('5m'), rsi['individual_rsi'].get('15m'),
            rsi['individual_rsi'].get('1h'), rsi['individual_rsi'].get('4h'),
            rsi['individual_rsi'].get('1d'), rsi['score'],
            rsi['aligned_count']['overbought'], rsi['aligned_count']['oversold'],
            1 if rsi['coiling_detected'] else 0,
            walls.get('call_wall', {}).get('strike') if walls.get('call_wall') else None,
            walls.get('call_wall', {}).get('distance_pct') if walls.get('call_wall') else None,
            walls.get('call_wall', {}).get('strength') if walls.get('call_wall') else None,
            walls.get('put_wall', {}).get('strike') if walls.get('put_wall') else None,
            walls.get('put_wall', {}).get('distance_pct') if walls.get('put_wall') else None,
            walls.get('put_wall', {}).get('strength') if walls.get('put_wall') else None,
            walls.get('net_gamma'), walls.get('net_gamma_regime'),
            exp['gamma_by_dte'].get('0dte', {}).get('total_gamma'),
            exp['gamma_by_dte'].get('this_week', {}).get('total_gamma'),
            exp['gamma_by_dte'].get('next_week', {}).get('total_gamma'),
            1 if lib_setup else 0,
            lib_setup.get('strike'), lib_setup.get('liberation_date'),
            1 if false_floor else 0,
            false_floor.get('strike'), false_floor.get('expiration_date'),
            fwd.get('strongest_above', {}).get('strike') if fwd else None,
            fwd.get('strongest_above', {}).get('strength_score') if fwd else None,
            fwd.get('strongest_below', {}).get('strike') if fwd else None,
            fwd.get('strongest_below', {}).get('strength_score') if fwd else None,
            fwd.get('path_of_least_resistance', {}).get('direction') if fwd else None,
            fwd.get('path_of_least_resistance', {}).get('confidence') if fwd else None,
            analysis['volume_ratio'],
            regime.get('price_targets', {}).get('current'),
            regime.get('price_targets', {}).get('destination'),
            regime.get('price_targets', {}).get('timeline_days')
        ))

    signal_id = c.lastrowid
    conn.commit()
    conn.close()

    return signal_id
