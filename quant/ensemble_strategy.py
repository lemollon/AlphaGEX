"""
Ensemble Strategy Weighting

Instead of picking ONE strategy per day, combine signals from multiple
strategies with learned weights based on regime and historical performance.

Key Benefits:
1. Smoother P&L curve (diversification across signals)
2. Regime-aware weighting (different strategies work in different regimes)
3. Reduces whipsaw from single-strategy flip-flopping
4. Adapts over time as strategies' performance changes

Weight Calculation:
- Base weight = historical win rate * historical Sharpe
- Regime adjustment = strategy's performance in current regime
- Recency adjustment = more weight to recent performance

Final Signal:
- Probability-weighted combination of all strategy signals
- Only trade when ensemble confidence > threshold

Author: AlphaGEX Quant
Date: 2025-12-03
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json

# Database
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


class StrategySignal(Enum):
    """Possible strategy signals"""
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    NEUTRAL = "NEUTRAL"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


@dataclass
class IndividualSignal:
    """Signal from a single strategy"""
    strategy_name: str
    signal: StrategySignal
    confidence: float  # 0-100
    weight: float      # 0-1 (contribution to ensemble)
    reasoning: str


@dataclass
class EnsembleSignal:
    """Combined signal from all strategies"""
    timestamp: datetime
    symbol: str
    final_signal: StrategySignal
    confidence: float  # Weighted confidence
    bullish_weight: float   # Sum of bullish weights
    bearish_weight: float   # Sum of bearish weights
    neutral_weight: float   # Sum of neutral weights
    component_signals: List[IndividualSignal]
    should_trade: bool
    position_size_multiplier: float  # 0-1 based on conviction
    reasoning: str

    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'symbol': self.symbol,
            'final_signal': self.final_signal.value,
            'confidence': round(self.confidence, 1),
            'bullish_weight': round(self.bullish_weight, 3),
            'bearish_weight': round(self.bearish_weight, 3),
            'neutral_weight': round(self.neutral_weight, 3),
            'should_trade': self.should_trade,
            'position_size_multiplier': round(self.position_size_multiplier, 2),
            'component_count': len(self.component_signals),
            'reasoning': self.reasoning
        }


class StrategyPerformance:
    """Track individual strategy performance for weight calculation"""

    def __init__(self, strategy_name: str):
        self.strategy_name = strategy_name
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.total_pnl_pct = 0
        self.recent_trades: List[Dict] = []  # Last 20 trades
        self.regime_performance: Dict[str, Dict] = {}  # Regime -> {wins, losses, pnl}

    @property
    def win_rate(self) -> float:
        return (self.wins / self.total_trades * 100) if self.total_trades > 0 else 50

    @property
    def avg_pnl_pct(self) -> float:
        return self.total_pnl_pct / self.total_trades if self.total_trades > 0 else 0

    @property
    def sharpe_estimate(self) -> float:
        """Estimate Sharpe from recent trades"""
        if len(self.recent_trades) < 5:
            return 0

        pnls = [t['pnl_pct'] for t in self.recent_trades]
        avg = np.mean(pnls)
        std = np.std(pnls)
        return (avg / std * np.sqrt(252)) if std > 0 else 0

    def record_trade(self, pnl_pct: float, regime: str):
        """Record a trade result"""
        self.total_trades += 1
        self.total_pnl_pct += pnl_pct

        if pnl_pct > 0:
            self.wins += 1
        else:
            self.losses += 1

        # Update recent trades (keep last 20)
        self.recent_trades.append({
            'pnl_pct': pnl_pct,
            'regime': regime,
            'timestamp': datetime.now()
        })
        if len(self.recent_trades) > 20:
            self.recent_trades.pop(0)

        # Update regime-specific performance
        if regime not in self.regime_performance:
            self.regime_performance[regime] = {'wins': 0, 'losses': 0, 'total_pnl': 0}

        self.regime_performance[regime]['total_pnl'] += pnl_pct
        if pnl_pct > 0:
            self.regime_performance[regime]['wins'] += 1
        else:
            self.regime_performance[regime]['losses'] += 1

    def get_regime_win_rate(self, regime: str) -> float:
        """Get win rate for specific regime"""
        if regime not in self.regime_performance:
            return self.win_rate  # Fall back to overall

        perf = self.regime_performance[regime]
        total = perf['wins'] + perf['losses']
        return (perf['wins'] / total * 100) if total > 0 else self.win_rate

    def calculate_weight(self, current_regime: str, recency_weight: float = 0.3) -> float:
        """
        Calculate strategy weight based on performance.

        Weight = base_weight * regime_adjustment * recency_adjustment

        Args:
            current_regime: Current market regime
            recency_weight: How much to weight recent performance (0-1)

        Returns:
            Weight between 0-1
        """
        if self.total_trades < 5:
            return 0.1  # Minimum weight for unproven strategies

        # Base weight from historical performance
        # win_rate 50% -> 0.5, 70% -> 0.7
        base_weight = self.win_rate / 100

        # Sharpe adjustment (Sharpe 0 -> 1x, Sharpe 2 -> 1.5x)
        sharpe_adj = 1 + (min(self.sharpe_estimate, 3) / 6)

        # Regime adjustment
        regime_wr = self.get_regime_win_rate(current_regime)
        regime_adj = regime_wr / self.win_rate if self.win_rate > 0 else 1.0
        regime_adj = np.clip(regime_adj, 0.5, 1.5)  # Cap adjustment

        # Recency adjustment (recent trades weighted more)
        if len(self.recent_trades) >= 5:
            recent_wins = sum(1 for t in self.recent_trades[-5:] if t['pnl_pct'] > 0)
            recent_wr = recent_wins / 5
            recency_adj = recent_wr / (self.win_rate / 100) if self.win_rate > 0 else 1.0
            recency_adj = np.clip(recency_adj, 0.7, 1.3)
        else:
            recency_adj = 1.0

        # Combine adjustments
        weight = base_weight * sharpe_adj * regime_adj
        weight = weight * (1 - recency_weight) + weight * recency_adj * recency_weight

        # Normalize to 0-1
        return np.clip(weight, 0.05, 1.0)


class EnsembleStrategyWeighter:
    """
    Combines signals from multiple strategies into ensemble signal.

    Strategies included:
    1. GEX Regime Classifier (market_regime_classifier.py)
    2. Psychology Trap Detector
    3. RSI Multi-Timeframe
    4. Vol Surface Analysis
    5. ML Regime Classifier (new)

    Each strategy provides a signal with confidence.
    Ensemble combines them using learned weights.
    """

    # Minimum ensemble confidence to trade
    MIN_CONFIDENCE_TO_TRADE = 60

    # Available strategies
    STRATEGIES = [
        'GEX_REGIME',
        'PSYCHOLOGY_TRAP',
        'RSI_MULTI_TF',
        'VOL_SURFACE',
        'ML_CLASSIFIER'
    ]

    def __init__(self, symbol: str = "SPY"):
        self.symbol = symbol
        self.strategy_performance: Dict[str, StrategyPerformance] = {}
        self._initialize_performances()

    def _initialize_performances(self):
        """Initialize performance trackers for each strategy"""
        for strategy in self.STRATEGIES:
            self.strategy_performance[strategy] = StrategyPerformance(strategy)

        # Load historical performance from DB
        self._load_historical_performance()

    def _load_historical_performance(self):
        """Load historical performance from database"""
        if not DB_AVAILABLE:
            return

        try:
            conn = get_connection()
            c = conn.cursor()

            # Get recent trades by strategy
            c.execute("""
                SELECT strategy_name, pnl_percent, regime_at_entry
                FROM paper_trades
                WHERE symbol = %s
                  AND exit_date IS NOT NULL
                  AND entry_date >= NOW() - INTERVAL '180 days'
                ORDER BY entry_date
            """, (self.symbol,))

            for row in c.fetchall():
                strategy, pnl, regime = row
                # Map strategy name to our strategy categories
                category = self._map_strategy_to_category(strategy)
                if category and category in self.strategy_performance:
                    self.strategy_performance[category].record_trade(pnl or 0, regime or 'UNKNOWN')

            conn.close()
        except Exception as e:
            print(f"Could not load historical performance: {e}")

    def _map_strategy_to_category(self, strategy_name: str) -> Optional[str]:
        """Map specific strategy names to ensemble categories"""
        if not strategy_name:
            return None

        upper = strategy_name.upper()

        if any(s in upper for s in ['GEX', 'GAMMA', 'FLIP']):
            return 'GEX_REGIME'
        elif any(s in upper for s in ['PSYCHOLOGY', 'TRAP', 'LIBERATION']):
            return 'PSYCHOLOGY_TRAP'
        elif any(s in upper for s in ['RSI', 'MOMENTUM']):
            return 'RSI_MULTI_TF'
        elif any(s in upper for s in ['VOL', 'IV', 'SURFACE', 'SKEW']):
            return 'VOL_SURFACE'
        elif any(s in upper for s in ['ML', 'MACHINE', 'CLASSIFIER']):
            return 'ML_CLASSIFIER'

        return 'GEX_REGIME'  # Default

    def get_individual_signals(
        self,
        gex_data: Dict,
        psychology_data: Optional[Dict] = None,
        rsi_data: Optional[Dict] = None,
        vol_surface_data: Optional[Dict] = None,
        ml_prediction: Optional[Dict] = None,
        current_regime: str = "UNKNOWN"
    ) -> List[IndividualSignal]:
        """
        Get signals from each strategy component.

        Each returns a signal with confidence.
        """
        signals = []

        # 1. GEX Regime Signal
        if gex_data:
            gex_signal = self._get_gex_signal(gex_data)
            gex_weight = self.strategy_performance['GEX_REGIME'].calculate_weight(current_regime)
            signals.append(IndividualSignal(
                strategy_name='GEX_REGIME',
                signal=gex_signal['signal'],
                confidence=gex_signal['confidence'],
                weight=gex_weight,
                reasoning=gex_signal['reasoning']
            ))

        # 2. Psychology Trap Signal
        if psychology_data:
            psych_signal = self._get_psychology_signal(psychology_data)
            psych_weight = self.strategy_performance['PSYCHOLOGY_TRAP'].calculate_weight(current_regime)
            signals.append(IndividualSignal(
                strategy_name='PSYCHOLOGY_TRAP',
                signal=psych_signal['signal'],
                confidence=psych_signal['confidence'],
                weight=psych_weight,
                reasoning=psych_signal['reasoning']
            ))

        # 3. RSI Multi-Timeframe Signal
        if rsi_data:
            rsi_signal = self._get_rsi_signal(rsi_data)
            rsi_weight = self.strategy_performance['RSI_MULTI_TF'].calculate_weight(current_regime)
            signals.append(IndividualSignal(
                strategy_name='RSI_MULTI_TF',
                signal=rsi_signal['signal'],
                confidence=rsi_signal['confidence'],
                weight=rsi_weight,
                reasoning=rsi_signal['reasoning']
            ))

        # 4. Vol Surface Signal
        if vol_surface_data:
            vol_signal = self._get_vol_surface_signal(vol_surface_data)
            vol_weight = self.strategy_performance['VOL_SURFACE'].calculate_weight(current_regime)
            signals.append(IndividualSignal(
                strategy_name='VOL_SURFACE',
                signal=vol_signal['signal'],
                confidence=vol_signal['confidence'],
                weight=vol_weight,
                reasoning=vol_signal['reasoning']
            ))

        # 5. ML Classifier Signal
        if ml_prediction:
            ml_signal = self._get_ml_signal(ml_prediction)
            ml_weight = self.strategy_performance['ML_CLASSIFIER'].calculate_weight(current_regime)
            signals.append(IndividualSignal(
                strategy_name='ML_CLASSIFIER',
                signal=ml_signal['signal'],
                confidence=ml_signal['confidence'],
                weight=ml_weight,
                reasoning=ml_signal['reasoning']
            ))

        return signals

    def _get_gex_signal(self, gex_data: Dict) -> Dict:
        """Convert GEX data to signal"""
        action = gex_data.get('recommended_action', 'STAY_FLAT')
        confidence = gex_data.get('confidence', 50)

        if action == 'BUY_CALLS':
            signal = StrategySignal.BUY if confidence < 80 else StrategySignal.STRONG_BUY
        elif action == 'BUY_PUTS':
            signal = StrategySignal.SELL if confidence < 80 else StrategySignal.STRONG_SELL
        elif action == 'SELL_PREMIUM':
            signal = StrategySignal.NEUTRAL
        else:
            signal = StrategySignal.NEUTRAL

        return {
            'signal': signal,
            'confidence': confidence,
            'reasoning': gex_data.get('reasoning', '')[:100]
        }

    def _get_psychology_signal(self, psychology_data: Dict) -> Dict:
        """Convert psychology trap data to signal"""
        trap_type = psychology_data.get('trap_type', '')
        confidence = psychology_data.get('confidence', 50)

        if 'CAPITULATION' in trap_type.upper() or 'TRAPPED' in trap_type.upper():
            signal = StrategySignal.STRONG_BUY
        elif 'FALSE_FLOOR' in trap_type.upper():
            signal = StrategySignal.SELL
        elif 'LIBERATION' in trap_type.upper():
            bias = psychology_data.get('bias', 'neutral')
            signal = StrategySignal.STRONG_BUY if bias == 'bullish' else StrategySignal.STRONG_SELL
        else:
            signal = StrategySignal.NEUTRAL

        return {
            'signal': signal,
            'confidence': confidence,
            'reasoning': f"Psychology trap: {trap_type}"
        }

    def _get_rsi_signal(self, rsi_data: Dict) -> Dict:
        """Convert multi-timeframe RSI to signal"""
        aligned = rsi_data.get('aligned', False)
        direction = rsi_data.get('direction', 'neutral')
        confidence = rsi_data.get('confidence', 50)

        if aligned:
            if direction == 'oversold':
                signal = StrategySignal.STRONG_BUY
            elif direction == 'overbought':
                signal = StrategySignal.STRONG_SELL
            else:
                signal = StrategySignal.NEUTRAL
        else:
            signal = StrategySignal.NEUTRAL
            confidence = 30  # Low confidence when not aligned

        return {
            'signal': signal,
            'confidence': confidence,
            'reasoning': f"RSI {direction}, aligned: {aligned}"
        }

    def _get_vol_surface_signal(self, vol_surface_data: Dict) -> Dict:
        """Convert vol surface analysis to signal"""
        bias = vol_surface_data.get('directional_bias', 'neutral')
        should_sell = vol_surface_data.get('should_sell_premium', False)
        skew = vol_surface_data.get('skew_regime', '')

        if should_sell:
            signal = StrategySignal.NEUTRAL  # Premium selling = neutral on direction
            confidence = 70
        elif bias == 'bullish':
            signal = StrategySignal.BUY
            confidence = 65
        elif bias == 'bearish':
            signal = StrategySignal.SELL
            confidence = 65
        else:
            signal = StrategySignal.NEUTRAL
            confidence = 50

        return {
            'signal': signal,
            'confidence': confidence,
            'reasoning': f"Vol surface: {bias}, skew: {skew}"
        }

    def _get_ml_signal(self, ml_prediction: Dict) -> Dict:
        """Convert ML prediction to signal"""
        action = ml_prediction.get('predicted_action', 'STAY_FLAT')
        confidence = ml_prediction.get('confidence', 50)
        is_trained = ml_prediction.get('is_trained', False)

        if not is_trained:
            return {
                'signal': StrategySignal.NEUTRAL,
                'confidence': 30,
                'reasoning': 'ML model not trained'
            }

        if action in ['BUY_CALLS', 'STRONG_BUY']:
            signal = StrategySignal.STRONG_BUY if confidence > 75 else StrategySignal.BUY
        elif action in ['BUY_PUTS', 'STRONG_SELL']:
            signal = StrategySignal.STRONG_SELL if confidence > 75 else StrategySignal.SELL
        else:
            signal = StrategySignal.NEUTRAL

        return {
            'signal': signal,
            'confidence': confidence,
            'reasoning': f"ML: {action} @ {confidence:.0f}%"
        }

    def combine_signals(
        self,
        signals: List[IndividualSignal]
    ) -> EnsembleSignal:
        """
        Combine individual signals into ensemble signal.

        Uses weighted voting where:
        - Each signal contributes based on its weight * confidence
        - Final signal is direction with highest weighted vote
        - Ensemble confidence is weighted average
        """
        if not signals:
            return EnsembleSignal(
                timestamp=datetime.now(),
                symbol=self.symbol,
                final_signal=StrategySignal.NEUTRAL,
                confidence=0,
                bullish_weight=0,
                bearish_weight=0,
                neutral_weight=1.0,
                component_signals=[],
                should_trade=False,
                position_size_multiplier=0,
                reasoning="No signals available"
            )

        # Calculate weighted votes for each direction
        bullish_weight = 0.0
        bearish_weight = 0.0
        neutral_weight = 0.0
        total_weight = 0.0

        weighted_confidences = []
        reasons = []

        for sig in signals:
            vote_strength = sig.weight * (sig.confidence / 100)
            total_weight += sig.weight

            if sig.signal in [StrategySignal.STRONG_BUY, StrategySignal.BUY]:
                bullish_weight += vote_strength
                if sig.signal == StrategySignal.STRONG_BUY:
                    bullish_weight += vote_strength * 0.5  # Extra for strong
            elif sig.signal in [StrategySignal.STRONG_SELL, StrategySignal.SELL]:
                bearish_weight += vote_strength
                if sig.signal == StrategySignal.STRONG_SELL:
                    bearish_weight += vote_strength * 0.5
            else:
                neutral_weight += vote_strength

            weighted_confidences.append(sig.weight * sig.confidence)
            reasons.append(f"{sig.strategy_name}: {sig.signal.value} ({sig.confidence:.0f}%)")

        # Normalize weights
        if total_weight > 0:
            bullish_weight /= total_weight
            bearish_weight /= total_weight
            neutral_weight /= total_weight

        # Determine final signal
        max_weight = max(bullish_weight, bearish_weight, neutral_weight)

        if max_weight == bullish_weight:
            if bullish_weight > 0.7:
                final_signal = StrategySignal.STRONG_BUY
            else:
                final_signal = StrategySignal.BUY
        elif max_weight == bearish_weight:
            if bearish_weight > 0.7:
                final_signal = StrategySignal.STRONG_SELL
            else:
                final_signal = StrategySignal.SELL
        else:
            final_signal = StrategySignal.NEUTRAL

        # Calculate ensemble confidence
        if sum(s.weight for s in signals) > 0:
            ensemble_confidence = sum(weighted_confidences) / sum(s.weight for s in signals)
        else:
            ensemble_confidence = 50

        # Determine if we should trade
        should_trade = (
            ensemble_confidence >= self.MIN_CONFIDENCE_TO_TRADE and
            final_signal != StrategySignal.NEUTRAL and
            max_weight > 0.4  # At least 40% consensus
        )

        # Position size multiplier based on conviction
        # Higher consensus + higher confidence = larger position
        conviction = max_weight * (ensemble_confidence / 100)
        position_size_multiplier = np.clip(conviction, 0.25, 1.0)

        return EnsembleSignal(
            timestamp=datetime.now(),
            symbol=self.symbol,
            final_signal=final_signal,
            confidence=ensemble_confidence,
            bullish_weight=bullish_weight,
            bearish_weight=bearish_weight,
            neutral_weight=neutral_weight,
            component_signals=signals,
            should_trade=should_trade,
            position_size_multiplier=position_size_multiplier,
            reasoning=" | ".join(reasons)
        )

    def get_ensemble_signal(
        self,
        gex_data: Dict,
        psychology_data: Optional[Dict] = None,
        rsi_data: Optional[Dict] = None,
        vol_surface_data: Optional[Dict] = None,
        ml_prediction: Optional[Dict] = None,
        current_regime: str = "UNKNOWN"
    ) -> EnsembleSignal:
        """
        Main entry point: Get ensemble signal from all available data.
        """
        # Get individual signals
        signals = self.get_individual_signals(
            gex_data=gex_data,
            psychology_data=psychology_data,
            rsi_data=rsi_data,
            vol_surface_data=vol_surface_data,
            ml_prediction=ml_prediction,
            current_regime=current_regime
        )

        # Combine into ensemble
        ensemble = self.combine_signals(signals)

        return ensemble

    def record_trade_outcome(
        self,
        strategy_name: str,
        pnl_pct: float,
        regime: str
    ):
        """Record trade outcome to update strategy weights"""
        category = self._map_strategy_to_category(strategy_name)
        if category and category in self.strategy_performance:
            self.strategy_performance[category].record_trade(pnl_pct, regime)

    def get_strategy_weights(self, current_regime: str = "UNKNOWN") -> Dict[str, float]:
        """Get current weights for all strategies"""
        return {
            name: perf.calculate_weight(current_regime)
            for name, perf in self.strategy_performance.items()
        }


# Global instance
_ensemble_weighter: Optional[EnsembleStrategyWeighter] = None


def get_ensemble_weighter(symbol: str = "SPY") -> EnsembleStrategyWeighter:
    """Get or create ensemble weighter for symbol"""
    global _ensemble_weighter
    if _ensemble_weighter is None or _ensemble_weighter.symbol != symbol:
        _ensemble_weighter = EnsembleStrategyWeighter(symbol)
    return _ensemble_weighter


def get_ensemble_signal(
    symbol: str = "SPY",
    gex_data: Dict = None,
    psychology_data: Optional[Dict] = None,
    rsi_data: Optional[Dict] = None,
    vol_surface_data: Optional[Dict] = None,
    ml_prediction: Optional[Dict] = None,
    current_regime: str = "UNKNOWN"
) -> EnsembleSignal:
    """
    Convenience function to get ensemble signal.

    Example:
        signal = get_ensemble_signal(
            gex_data={'recommended_action': 'BUY_CALLS', 'confidence': 75},
            ml_prediction={'predicted_action': 'BUY_CALLS', 'confidence': 80},
            current_regime='NEGATIVE_GAMMA'
        )

        if signal.should_trade:
            print(f"Trade {signal.final_signal.value} with {signal.confidence:.0f}% confidence")
            print(f"Position size: {signal.position_size_multiplier:.0%} of normal")
    """
    weighter = get_ensemble_weighter(symbol)
    return weighter.get_ensemble_signal(
        gex_data=gex_data or {},
        psychology_data=psychology_data,
        rsi_data=rsi_data,
        vol_surface_data=vol_surface_data,
        ml_prediction=ml_prediction,
        current_regime=current_regime
    )


if __name__ == "__main__":
    print("Testing Ensemble Strategy Weighting...")

    # Test with sample data
    signal = get_ensemble_signal(
        symbol="SPY",
        gex_data={
            'recommended_action': 'BUY_CALLS',
            'confidence': 75,
            'reasoning': 'Negative gamma + below flip'
        },
        psychology_data={
            'trap_type': 'DEALER_CAPITULATION',
            'confidence': 85,
            'bias': 'bullish'
        },
        rsi_data={
            'aligned': True,
            'direction': 'oversold',
            'confidence': 70
        },
        ml_prediction={
            'predicted_action': 'BUY_CALLS',
            'confidence': 72,
            'is_trained': True
        },
        current_regime='NEGATIVE_GAMMA'
    )

    print(f"\nEnsemble Signal:")
    print(f"  Final: {signal.final_signal.value}")
    print(f"  Confidence: {signal.confidence:.1f}%")
    print(f"  Should Trade: {signal.should_trade}")
    print(f"  Position Size: {signal.position_size_multiplier:.0%}")
    print(f"\nWeight Distribution:")
    print(f"  Bullish: {signal.bullish_weight:.1%}")
    print(f"  Bearish: {signal.bearish_weight:.1%}")
    print(f"  Neutral: {signal.neutral_weight:.1%}")
    print(f"\nComponent Signals:")
    for comp in signal.component_signals:
        print(f"  {comp.strategy_name}: {comp.signal.value} ({comp.confidence:.0f}%) weight={comp.weight:.2f}")
