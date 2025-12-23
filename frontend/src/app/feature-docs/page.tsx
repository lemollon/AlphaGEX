'use client'

import { useState, useMemo } from 'react'
import {
  Search, Filter, ChevronDown, ChevronUp, Copy, Check,
  Calculator, TrendingUp, Activity, Zap, Target, BarChart3,
  Brain, Shield, Percent, Clock, Layers, GitBranch,
  FileCode, BookOpen, Hash, ArrowUpDown
} from 'lucide-react'
import Navigation from '@/components/Navigation'

// ============================================================================
// CALCULATION DATA - All 268 calculations organized by category
// ============================================================================

interface Calculation {
  id: number
  name: string
  formula: string
  purpose: string
  file: string
  category: string
}

const CALCULATIONS: Calculation[] = [
  // ==================== GEX CALCULATIONS (18) ====================
  { id: 1, name: 'Net GEX', formula: 'GEX = gamma × OI × 100 × spot²', purpose: 'Quantifies market maker gamma positioning. Positive = mean reversion, Negative = trending moves', file: 'data/gex_calculator.py', category: 'GEX' },
  { id: 2, name: 'Call Wall', formula: 'Strike with highest call gamma ≥ spot (must be ≥0.5% away)', purpose: 'Identifies gamma-induced resistance where market makers defend', file: 'data/gex_calculator.py', category: 'GEX' },
  { id: 3, name: 'Put Wall', formula: 'Strike with highest put gamma ≤ spot (must be ≥0.5% away)', purpose: 'Identifies gamma-induced support where market makers defend', file: 'data/gex_calculator.py', category: 'GEX' },
  { id: 4, name: 'Gamma Flip Point', formula: 'flip = prev_strike + (strike - prev_strike) × (-prev_net) / (net - prev_net)', purpose: 'Price level where MM hedging behavior changes from long-gamma to short-gamma', file: 'data/gex_calculator.py', category: 'GEX' },
  { id: 5, name: 'Max Pain', formula: 'For each strike: total_pain = Σ(max(0, test - call_strike) × call_OI) + Σ(max(0, put_strike - test) × put_OI); max_pain = argmin(total_pain)', purpose: 'Strike where option holder loss is minimized; acts as price magnet at expiration', file: 'data/gex_calculator.py', category: 'GEX' },
  { id: 6, name: 'Distance to Flip %', formula: '(spot - flip_point) / spot × 100', purpose: 'Measure how far price is from the gamma flip point', file: 'quant/kronos_gex_calculator.py', category: 'GEX' },
  { id: 7, name: 'GEX Normalized', formula: 'gex_normalized = net_gex / spot²', purpose: 'Scale-independent GEX for comparison across different stock prices', file: 'quant/kronos_gex_calculator.py', category: 'GEX' },
  { id: 8, name: 'Wall Strength %', formula: 'wall_strength_pct = strike_gex / net_gex × 100', purpose: 'Measures how strong a particular gamma wall is', file: 'core/psychology_trap_detector.py', category: 'GEX' },
  { id: 9, name: 'GEX Ratio', formula: '|put_gex| / |call_gex|', purpose: 'Directional bias signal based on put/call gamma imbalance', file: 'quant/gex_probability_models.py', category: 'GEX' },
  { id: 10, name: 'GEX Ratio Log', formula: 'log(gex_ratio) clamped to [0.1, 10]', purpose: 'ML-friendly scaling of GEX ratio', file: 'quant/gex_probability_models.py', category: 'GEX' },
  { id: 11, name: 'Cumulative GEX', formula: 'cumsum(gex by strike)', purpose: 'Running gamma total across strikes', file: 'core_classes_and_engines.py', category: 'GEX' },
  { id: 12, name: 'GEX % at Strike', formula: '|strike_gex| / total_abs_gex × 100', purpose: 'Strike concentration of gamma exposure', file: 'core_classes_and_engines.py', category: 'GEX' },
  { id: 13, name: 'Gamma Imbalance %', formula: '(call_gex - put_gex) / total × 100', purpose: 'Directional gamma imbalance percentage', file: 'quant/gex_signal_integration.py', category: 'GEX' },
  { id: 14, name: 'Top Magnet Concentration', formula: '|magnet1_gamma + magnet2_gamma| / total_gamma', purpose: 'How much gamma is concentrated in top magnets', file: 'quant/gex_probability_models.py', category: 'GEX' },
  { id: 15, name: 'Wall Spread %', formula: '(call_wall - put_wall) / spot × 100', purpose: 'Width of the pin zone between walls', file: 'quant/gex_probability_models.py', category: 'GEX' },
  { id: 16, name: 'OI Percentile', formula: 'rank(open_interest) × 100', purpose: 'Identifies high OI strikes', file: 'core_classes_and_engines.py', category: 'GEX' },
  { id: 17, name: 'GEX Change 1d', formula: 'net_gamma_normalized.diff()', purpose: 'Day-over-day gamma change', file: 'quant/gex_probability_models.py', category: 'GEX' },
  { id: 18, name: 'GEX Change 3d', formula: 'rolling(3).mean().diff()', purpose: '3-day gamma momentum', file: 'quant/gex_probability_models.py', category: 'GEX' },

  // ==================== OPTIONS GREEKS (18) ====================
  { id: 19, name: 'd1', formula: 'd1 = [ln(S/K) + (r + σ²/2)T] / (σ√T)', purpose: 'Key intermediate value for Black-Scholes calculations', file: 'quant/iv_solver.py', category: 'Greeks' },
  { id: 20, name: 'd2', formula: 'd2 = d1 - σ√T', purpose: 'Key intermediate value for Black-Scholes calculations', file: 'quant/iv_solver.py', category: 'Greeks' },
  { id: 21, name: 'Call Price (BS)', formula: 'C = S·N(d1) - K·e^(-rT)·N(d2)', purpose: 'Black-Scholes call option valuation', file: 'quant/iv_solver.py', category: 'Greeks' },
  { id: 22, name: 'Put Price (BS)', formula: 'P = K·e^(-rT)·N(-d2) - S·N(-d1)', purpose: 'Black-Scholes put option valuation', file: 'quant/iv_solver.py', category: 'Greeks' },
  { id: 23, name: 'Delta (Call)', formula: 'Delta = N(d1)', purpose: 'Call option price sensitivity to underlying price', file: 'quant/iv_solver.py', category: 'Greeks' },
  { id: 24, name: 'Delta (Put)', formula: 'Delta = N(d1) - 1', purpose: 'Put option price sensitivity to underlying price', file: 'quant/iv_solver.py', category: 'Greeks' },
  { id: 25, name: 'Gamma', formula: 'Gamma = N\'(d1) / (S × σ × √T)', purpose: 'Rate of change of delta (acceleration)', file: 'quant/iv_solver.py', category: 'Greeks' },
  { id: 26, name: 'Vega', formula: 'Vega = S × N\'(d1) × √T / 100', purpose: 'Option price sensitivity to volatility (per 1% change)', file: 'quant/iv_solver.py', category: 'Greeks' },
  { id: 27, name: 'Theta (Call)', formula: 'Theta = (-(S×N\'(d1)×σ)/(2×√T) - r×K×e^(-rT)×N(d2)) / 365', purpose: 'Call option time decay per day', file: 'quant/iv_solver.py', category: 'Greeks' },
  { id: 28, name: 'Theta (Put)', formula: 'Theta = (-(S×N\'(d1)×σ)/(2×√T) + r×K×e^(-rT)×N(-d2)) / 365', purpose: 'Put option time decay per day', file: 'quant/iv_solver.py', category: 'Greeks' },
  { id: 29, name: 'Implied Volatility', formula: 'Newton-Raphson: IV_new = IV - (BS_price - target) / vega', purpose: 'Solve for IV from market option prices', file: 'quant/iv_solver.py', category: 'Greeks' },
  { id: 30, name: 'Intrinsic Value (Call)', formula: 'max(0, S - K)', purpose: 'In-the-money amount for calls', file: 'quant/iv_solver.py', category: 'Greeks' },
  { id: 31, name: 'Intrinsic Value (Put)', formula: 'max(0, K - S)', purpose: 'In-the-money amount for puts', file: 'quant/iv_solver.py', category: 'Greeks' },
  { id: 32, name: 'Vanna', formula: 'vega × gamma × OI × 100', purpose: 'Cross-greek: sensitivity of delta to volatility', file: 'core_classes_and_engines.py', category: 'Greeks' },
  { id: 33, name: 'Charm', formula: 'daily_charm = total_gex / dte', purpose: 'Rate of delta decay over time', file: 'core_classes_and_engines.py', category: 'Greeks' },
  { id: 34, name: 'Weekend Charm', formula: 'weekend_charm = daily_charm × 2.5', purpose: 'Extended theta decay over weekends', file: 'core_classes_and_engines.py', category: 'Greeks' },
  { id: 35, name: 'Time Factor', formula: '1 / √(max(dte, 0.5))', purpose: 'Gamma time scaling factor', file: 'core_classes_and_engines.py', category: 'Greeks' },
  { id: 36, name: 'Vol Factor', formula: '1 / max(iv, 0.1)', purpose: 'Gamma volatility scaling factor', file: 'core_classes_and_engines.py', category: 'Greeks' },

  // ==================== RSI & TECHNICAL (15) ====================
  { id: 37, name: 'RSI (14-period)', formula: 'RS = avg_gain / avg_loss; RSI = 100 - 100/(1+RS)', purpose: 'Momentum oscillator (0-100 scale)', file: 'core/psychology_trap_detector.py', category: 'Technical' },
  { id: 38, name: 'Multi-TF RSI Score', formula: 'Weighted: 5m(0.10) + 15m(0.15) + 1h(0.20) + 4h(0.25) + 1d(0.30)', purpose: 'Unified momentum score across timeframes (-100 to +100)', file: 'core/psychology_trap_detector.py', category: 'Technical' },
  { id: 39, name: 'Aligned Overbought', formula: 'Count(RSI > 70) across all timeframes', purpose: 'Multi-timeframe overbought confirmation', file: 'core/psychology_trap_detector.py', category: 'Technical' },
  { id: 40, name: 'Aligned Oversold', formula: 'Count(RSI < 30) across all timeframes', purpose: 'Multi-timeframe oversold confirmation', file: 'core/psychology_trap_detector.py', category: 'Technical' },
  { id: 41, name: 'Extreme RSI Count', formula: 'Count(RSI > 80 OR RSI < 20)', purpose: 'Strong exhaustion signal detection', file: 'core/psychology_trap_detector.py', category: 'Technical' },
  { id: 42, name: 'Coiling Detection', formula: 'recent_ATR < longer_ATR × 0.7 when RSI extreme on 3+ timeframes', purpose: 'Pre-breakout compression detection', file: 'core/psychology_trap_detector.py', category: 'Technical' },
  { id: 43, name: 'ATR (Average True Range)', formula: 'mean(high - low) over period', purpose: 'Volatility measurement', file: 'core/psychology_trap_detector.py', category: 'Technical' },
  { id: 44, name: 'SMA 20', formula: 'close.rolling(20).mean()', purpose: '20-day simple moving average', file: 'backtest/premium_portfolio_backtest.py', category: 'Technical' },
  { id: 45, name: 'SMA 50', formula: 'close.rolling(50).mean()', purpose: '50-day simple moving average', file: 'backtest/premium_portfolio_backtest.py', category: 'Technical' },
  { id: 46, name: 'MACD Signal', formula: 'EMA(12) - EMA(26) vs Signal(9)', purpose: 'Trend classification indicator', file: 'core/apollo_ml_engine.py', category: 'Technical' },
  { id: 47, name: 'Bollinger %B', formula: '(price - lower_band) / (upper_band - lower_band)', purpose: 'Position within Bollinger Bands (0-1)', file: 'core/apollo_ml_engine.py', category: 'Technical' },
  { id: 48, name: 'ATR Percentile', formula: 'percentile_rank(ATR, history)', purpose: 'Relative volatility vs history', file: 'core/apollo_ml_engine.py', category: 'Technical' },
  { id: 49, name: 'Volume Ratio', formula: 'current_volume / 20day_avg_volume', purpose: 'Relative volume indicator', file: 'core/apollo_ml_engine.py', category: 'Technical' },
  { id: 50, name: 'OI Change %', formula: '(current_OI - prev_OI) / prev_OI × 100', purpose: 'Day-over-day open interest change', file: 'core/apollo_ml_engine.py', category: 'Technical' },
  { id: 51, name: 'Price Momentum', formula: 'np.diff(np.log(closes))', purpose: 'Log returns for momentum calculation', file: 'core/autonomous_paper_trader.py', category: 'Technical' },

  // ==================== TRADING COSTS (12) ====================
  { id: 52, name: 'Mid Price', formula: '(bid + ask) / 2', purpose: 'Fair value estimate between bid and ask', file: 'trading_costs.py', category: 'Costs' },
  { id: 53, name: 'Spread %', formula: '(ask - bid) / mid × 100', purpose: 'Bid-ask spread as percentage (liquidity measure)', file: 'trading_costs.py', category: 'Costs' },
  { id: 54, name: 'Slippage from Spread', formula: 'spread × (1 - spread_capture_pct)', purpose: 'Execution price impact from spread', file: 'trading_costs.py', category: 'Costs' },
  { id: 55, name: 'Market Impact', formula: 'min(contracts × bp_per_contract, max_bp) / 10000', purpose: 'Size-dependent slippage', file: 'trading_costs.py', category: 'Costs' },
  { id: 56, name: 'Commission', formula: 'max(contracts × rate, min_commission)', purpose: 'Trading commission calculation', file: 'trading_costs.py', category: 'Costs' },
  { id: 57, name: 'Regulatory Fees', formula: 'contracts × reg_fee', purpose: 'Additional regulatory fees', file: 'trading_costs.py', category: 'Costs' },
  { id: 58, name: 'Round-Trip P&L', formula: 'gross_pnl - entry_commission - exit_commission', purpose: 'True P&L after all costs', file: 'trading_costs.py', category: 'Costs' },
  { id: 59, name: 'Cost Drag %', formula: '(theoretical_pnl - net_pnl) / |theoretical_pnl| × 100', purpose: 'How much costs reduce profit', file: 'trading_costs.py', category: 'Costs' },
  { id: 60, name: 'Bid/Ask Spread Estimate', formula: 'ATM: 1.5%, Slightly OTM: 2%, More OTM: 3%, Deep OTM: 5%', purpose: 'Liquidity estimate by moneyness', file: 'backend/enhanced_probability_calculator.py', category: 'Costs' },
  { id: 61, name: 'Dollar Volume', formula: 'volume × last_price × 100', purpose: 'Trade size in dollars', file: 'various', category: 'Costs' },
  { id: 62, name: 'Transaction Costs', formula: 'slippage + commission × 2', purpose: 'Total round-trip transaction costs', file: 'backtest/backtest_framework.py', category: 'Costs' },
  { id: 63, name: 'Net P&L', formula: 'gross_pnl - transaction_costs', purpose: 'Profit after all transaction costs', file: 'backtest/backtest_framework.py', category: 'Costs' },

  // ==================== KELLY & POSITION SIZING (15) ====================
  { id: 64, name: 'Kelly Fraction', formula: 'f* = (b×p - q) / b where b=avg_win/avg_loss, p=win_rate, q=1-p', purpose: 'Theoretically optimal position size', file: 'quant/monte_carlo_kelly.py', category: 'Kelly' },
  { id: 65, name: 'Half Kelly', formula: 'f = 0.5 × kelly_fraction', purpose: 'Conservative position sizing (50% of optimal)', file: 'quant/monte_carlo_kelly.py', category: 'Kelly' },
  { id: 66, name: 'Quarter Kelly', formula: 'f = 0.25 × kelly_fraction', purpose: 'Ultra-conservative sizing (25% of optimal)', file: 'quant/monte_carlo_kelly.py', category: 'Kelly' },
  { id: 67, name: 'Win Rate Uncertainty', formula: 'std = √(p × (1-p) / n)', purpose: 'Confidence interval for win rate estimate', file: 'quant/monte_carlo_kelly.py', category: 'Kelly' },
  { id: 68, name: 'Safe Kelly (Monte Carlo)', formula: '10,000 paths × 200 trades, binary search for 95% survival', purpose: 'Robust position size that survives uncertainty', file: 'quant/monte_carlo_kelly.py', category: 'Kelly' },
  { id: 69, name: 'Probability of Ruin', formula: 'count(equity < 25%) / num_simulations', purpose: 'Risk of total loss', file: 'quant/monte_carlo_kelly.py', category: 'Kelly' },
  { id: 70, name: '50% Drawdown Probability', formula: 'count(max_dd >= 50%) / num_simulations', purpose: 'Risk of large drawdown', file: 'quant/monte_carlo_kelly.py', category: 'Kelly' },
  { id: 71, name: 'VaR 95%', formula: 'percentile(final_equities, 5)', purpose: 'Worst 5% loss scenario', file: 'quant/monte_carlo_kelly.py', category: 'Kelly' },
  { id: 72, name: 'CVaR (Expected Shortfall)', formula: 'mean(losses in worst 5%)', purpose: 'Average loss in tail scenarios', file: 'quant/monte_carlo_kelly.py', category: 'Kelly' },
  { id: 73, name: 'Confidence-Adjusted Size', formula: 'adjusted_risk = base_risk × (confidence / 100)', purpose: 'Scale position by trade confidence', file: 'core/position_sizing.py', category: 'Kelly' },
  { id: 74, name: 'Risk per Contract', formula: '|entry - stop| × 100', purpose: 'Dollar risk per contract', file: 'core/position_sizing.py', category: 'Kelly' },
  { id: 75, name: 'Contract Count', formula: 'risk_dollars / risk_per_contract', purpose: 'Number of contracts to trade', file: 'core/position_sizing.py', category: 'Kelly' },
  { id: 76, name: 'Payoff Ratio', formula: 'avg_win / avg_loss', purpose: 'Reward-to-risk ratio', file: 'various', category: 'Kelly' },
  { id: 77, name: 'Shrinkage Factor', formula: '√(sample_size / 100)', purpose: 'Adjustment for sample size uncertainty', file: 'quant/monte_carlo_kelly.py', category: 'Kelly' },
  { id: 78, name: 'Position Size Multiplier', formula: 'Normal: 1.0, Elevated: 0.75, High: 0.50, Extreme: 0.25', purpose: 'VIX-based position reduction', file: 'core/vix_hedge_manager.py', category: 'Kelly' },

  // ==================== PROBABILITY (12) ====================
  { id: 79, name: 'GEX-Based Probability', formula: 'net_gex > 1B: (75%, 15%, 10%); > 0: (65%, 20%, 15%); > -1B: (50%, 25%, 25%); else: (35%, 35%, 30%)', purpose: 'Direction prediction based on GEX thresholds', file: 'core/probability_calculator.py', category: 'Probability' },
  { id: 80, name: 'VIX Adjustment', formula: 'VIX<15: 1.2, VIX<20: 1.0, VIX<30: 0.8, else: 0.6', purpose: 'Adjust probability confidence by volatility', file: 'core/probability_calculator.py', category: 'Probability' },
  { id: 81, name: 'Psychology Adjustment', formula: 'FOMO>80: 0.7, Fear>80: 0.75, Balanced(40-60): 1.1', purpose: 'Adjust for sentiment extremes', file: 'core/probability_calculator.py', category: 'Probability' },
  { id: 82, name: 'MM State Adjustment', formula: 'DEFENDING: 1.15, NEUTRAL: 1.0, SQUEEZING: 0.8, PANICKING: 0.6', purpose: 'Adjust for market maker behavior', file: 'core/probability_calculator.py', category: 'Probability' },
  { id: 83, name: 'Combined Probability', formula: 'final = base × (w_gex + w_vol×adj + w_psych×adj + ...) / total_weight, clamped [0.10, 0.95]', purpose: 'Weighted integration of all signals', file: 'core/probability_calculator.py', category: 'Probability' },
  { id: 84, name: 'Probability Calibration', formula: 'Auto-adjust weights based on historical accuracy', purpose: 'Self-learning weight adjustment', file: 'core/probability_calculator.py', category: 'Probability' },
  { id: 85, name: 'Historical Pattern Match', formula: 'Match current GEX within 30% of historical setups', purpose: 'Pattern confidence from history', file: 'core/probability_calculator.py', category: 'Probability' },
  { id: 86, name: 'Expected Value', formula: 'E = (win_rate × avg_win) - ((1-win_rate) × avg_loss)', purpose: 'Expected profit per trade', file: 'core/probability_calculator.py', category: 'Probability' },
  { id: 87, name: 'Risk/Reward Ratio', formula: '|target - entry| / |stop - entry|', purpose: 'Potential reward vs risk', file: 'various', category: 'Probability' },
  { id: 88, name: 'Confidence Score', formula: 'min(base + adjustment, max_confidence)', purpose: 'Overall confidence 0-100', file: 'various', category: 'Probability' },
  { id: 89, name: 'Z-Score Settlement', formula: 'random.gauss(0, 1) clamped [-3, 3]', purpose: 'Simulated settlement price distribution', file: 'backtest/zero_dte_bull_put_spread.py', category: 'Probability' },
  { id: 90, name: 'Hybrid Probability', formula: 'ML prediction + gamma-weighted distance', purpose: 'Combined ML and rule-based probability', file: 'core/argus_engine.py', category: 'Probability' },

  // ==================== REGIME CLASSIFICATION (14) ====================
  { id: 91, name: 'IV Rank', formula: '(current_IV - 52wk_low) / (52wk_high - 52wk_low) × 100', purpose: 'IV relative to 52-week range (0-100)', file: 'core/market_regime_classifier.py', category: 'Regime' },
  { id: 92, name: 'IV Percentile', formula: '% of days where IV was lower than current', purpose: 'Historical IV context', file: 'core/market_regime_classifier.py', category: 'Regime' },
  { id: 93, name: 'IV/HV Ratio', formula: 'current_IV / historical_volatility', purpose: 'Implied vs realized volatility (>1 = overpriced)', file: 'core/market_regime_classifier.py', category: 'Regime' },
  { id: 94, name: 'Gamma Regime', formula: '<-2B: STRONG_NEG, -2B to -0.5B: NEG, ±0.5B: NEUTRAL, 0.5B to 2B: POS, >2B: STRONG_POS', purpose: 'Market maker gamma positioning classification', file: 'core/market_regime_classifier.py', category: 'Regime' },
  { id: 95, name: 'VIX Regime', formula: '<12: VERY_LOW, 12-15: LOW, 15-20: NORMAL, 20-25: ELEVATED, 25-35: HIGH, >35: EXTREME', purpose: 'Market fear level classification', file: 'core/vix_hedge_manager.py', category: 'Regime' },
  { id: 96, name: 'Volatility Regime', formula: 'Combined VIX + gamma + price classification', purpose: 'Overall market volatility state', file: 'core/psychology_trap_detector.py', category: 'Regime' },
  { id: 97, name: 'Trend Regime', formula: 'Price relative to moving averages', purpose: 'Directional bias classification', file: 'core/market_regime_classifier.py', category: 'Regime' },
  { id: 98, name: 'Vol Term Structure', formula: '(back_month_IV - front_month_IV) / DTE_difference', purpose: 'Contango vs backwardation detection', file: 'core/market_regime_classifier.py', category: 'Regime' },
  { id: 99, name: 'Distance to Flip', formula: '(spot - flip_point) / spot × 100', purpose: 'Proximity to regime change level', file: 'core/market_regime_classifier.py', category: 'Regime' },
  { id: 100, name: 'Trending Bias', formula: 'distance > 1% from flip point', purpose: 'Directional trend signal', file: 'core/market_regime_classifier.py', category: 'Regime' },
  { id: 101, name: 'Volatility Expectation', formula: 'Based on net_gex thresholds', purpose: 'Expected volatility from gamma regime', file: 'core/market_regime_classifier.py', category: 'Regime' },
  { id: 102, name: 'Regime Confidence', formula: 'min(70 + |net_gex/1e9| × 5, 95)', purpose: 'Confidence in regime classification', file: 'core/market_regime_classifier.py', category: 'Regime' },
  { id: 103, name: 'GEX Percentile', formula: 'rolling(60).apply(percentile_rank)', purpose: '60-day rolling GEX percentile', file: 'quant/ml_regime_classifier.py', category: 'Regime' },
  { id: 104, name: 'VIX Percentile (Rolling)', formula: 'rolling(60).apply(percentile_rank)', purpose: '60-day rolling VIX percentile', file: 'quant/ml_regime_classifier.py', category: 'Regime' },

  // ==================== PSYCHOLOGY TRAP (14) ====================
  { id: 105, name: 'VIX Spike Detection', formula: 'vix_change_pct > 20%', purpose: 'Detect explosive volatility events', file: 'core/psychology_trap_detector.py', category: 'Psychology' },
  { id: 106, name: 'Volume Confirmation', formula: 'volume_ratio >= 2.0', purpose: 'Confirm dealer activity with volume', file: 'core/psychology_trap_detector.py', category: 'Psychology' },
  { id: 107, name: 'Volume Expanding', formula: 'recent_vol > prior_vol × 1.15', purpose: 'Detect momentum building', file: 'core/psychology_trap_detector.py', category: 'Psychology' },
  { id: 108, name: 'Dealer Hedging Pressure', formula: '|net_gex/1e9| × |price_momentum| × 100 × volume_mult', purpose: 'Hedging flow in millions of dollars', file: 'core/psychology_trap_detector.py', category: 'Psychology' },
  { id: 109, name: 'Amplification Factor', formula: '1.0 + (volume_ratio - 1.0) × 0.5', purpose: 'How much dealers amplify the move', file: 'core/psychology_trap_detector.py', category: 'Psychology' },
  { id: 110, name: 'Feedback Loop Strength', formula: 'volume >= 2.0 & amp > 1.5 & 3+ active strikes = EXTREME', purpose: 'Dealer feedback loop classification', file: 'core/psychology_trap_detector.py', category: 'Psychology' },
  { id: 111, name: 'Breakout Score', formula: 'Volume(30pts) + GEX_Wall(25pts) + Momentum(20pts) + Hedging(15pts) + RSI(10pts)', purpose: 'Breakout vs rejection probability', file: 'core/psychology_trap_detector.py', category: 'Psychology' },
  { id: 112, name: 'Liberation Setup', formula: 'Pattern: trapped positions releasing', purpose: 'Capitulation/reversal signal', file: 'core/psychology_trap_detector.py', category: 'Psychology' },
  { id: 113, name: 'False Floor Detection', formula: 'Deceptive support level identification', purpose: 'Avoid buying false bottoms', file: 'core/psychology_trap_detector.py', category: 'Psychology' },
  { id: 114, name: 'Monthly Magnet', formula: 'High-gamma strikes on monthly options', purpose: 'Monthly expiration target levels', file: 'core/psychology_trap_detector.py', category: 'Psychology' },
  { id: 115, name: 'Near Put Wall', formula: '|distance_to_put_wall_pct| <= 1.5%', purpose: 'Proximity to put wall (support)', file: 'core/psychology_trap_detector.py', category: 'Psychology' },
  { id: 116, name: 'Near Call Wall', formula: '|distance_to_call_wall_pct| <= 1.5%', purpose: 'Proximity to call wall (resistance)', file: 'core/psychology_trap_detector.py', category: 'Psychology' },
  { id: 117, name: 'GEX Asymmetry Strong', formula: 'gex_ratio >= 1.5 OR gex_ratio <= 0.67', purpose: 'Strong directional gamma imbalance', file: 'core/psychology_trap_detector.py', category: 'Psychology' },
  { id: 118, name: 'Hedging Intensity', formula: 'volume / OI ratio at high OI strikes', purpose: 'Dealer hedging activity level', file: 'core/psychology_trap_detector.py', category: 'Psychology' },

  // ==================== RISK METRICS (20) ====================
  { id: 119, name: 'Sharpe Ratio', formula: '(avg_return - risk_free) / std_dev × √252', purpose: 'Risk-adjusted return (>1 good, >2 excellent)', file: 'core/backtest_report.py', category: 'Risk' },
  { id: 120, name: 'Sortino Ratio', formula: 'avg_return / downside_std × √252', purpose: 'Downside risk-adjusted return', file: 'core/backtest_report.py', category: 'Risk' },
  { id: 121, name: 'Calmar Ratio', formula: 'annual_return / max_drawdown', purpose: 'Return relative to worst drawdown', file: 'core/backtest_report.py', category: 'Risk' },
  { id: 122, name: 'Maximum Drawdown', formula: 'max(peak - current) over equity curve', purpose: 'Largest portfolio decline', file: 'core/backtest_report.py', category: 'Risk' },
  { id: 123, name: 'Maximum Drawdown %', formula: 'max_dd / peak × 100', purpose: 'Relative maximum drawdown', file: 'core/backtest_report.py', category: 'Risk' },
  { id: 124, name: 'Absolute Drawdown', formula: 'initial_capital - min(equity)', purpose: 'Maximum drop from starting capital', file: 'core/backtest_report.py', category: 'Risk' },
  { id: 125, name: 'Profit Factor', formula: 'Σ(winning_trades) / Σ(losing_trades)', purpose: 'Total wins vs losses (>1.5 good, >2 excellent)', file: 'core/backtest_report.py', category: 'Risk' },
  { id: 126, name: 'Expected Payoff', formula: 'total_pnl / total_trades', purpose: 'Average profit per trade', file: 'core/backtest_report.py', category: 'Risk' },
  { id: 127, name: 'Expectancy', formula: '(win_rate × avg_win) - ((1-win_rate) × avg_loss)', purpose: 'Expected dollar per trade', file: 'core/backtest_report.py', category: 'Risk' },
  { id: 128, name: 'Recovery Factor', formula: 'net_profit / max_drawdown', purpose: 'How quickly profits recover from drawdown', file: 'core/backtest_report.py', category: 'Risk' },
  { id: 129, name: 'Daily Loss Limit', formula: '(start_day_value - current_value) / start_day_value × 100', purpose: 'Stop trading if daily loss > 5%', file: 'core/autonomous_risk_manager.py', category: 'Risk' },
  { id: 130, name: 'Max Consecutive Wins', formula: 'Track longest winning streak', purpose: 'Streak analysis', file: 'core/backtest_report.py', category: 'Risk' },
  { id: 131, name: 'Max Consecutive Losses', formula: 'Track longest losing streak', purpose: 'Streak analysis for risk', file: 'core/backtest_report.py', category: 'Risk' },
  { id: 132, name: 'Win Rate', formula: 'winning_trades / total_trades × 100', purpose: 'Percentage of winning trades', file: 'various', category: 'Risk' },
  { id: 133, name: 'Average Win', formula: 'Σ(winning_pnl) / count(winners)', purpose: 'Typical profit on winners', file: 'various', category: 'Risk' },
  { id: 134, name: 'Average Loss', formula: 'Σ(losing_pnl) / count(losers)', purpose: 'Typical loss on losers', file: 'various', category: 'Risk' },
  { id: 135, name: 'Data Quality %', formula: 'real_data_points / (real + estimated) × 100', purpose: 'Backtest data reliability', file: 'backtest/strategy_report.py', category: 'Risk' },
  { id: 136, name: 'Trade Duration', formula: 'Σ(durations) / total_trades', purpose: 'Average holding time', file: 'backtest/strategy_report.py', category: 'Risk' },
  { id: 137, name: 'Annualized Return', formula: 'total_return × (365 / days)', purpose: 'Yearly equivalent return', file: 'validation/quant_validation.py', category: 'Risk' },
  { id: 138, name: 'Annualized Volatility', formula: 'std(returns) × √252', purpose: 'Yearly equivalent volatility', file: 'validation/quant_validation.py', category: 'Risk' },

  // ==================== VIX & VOLATILITY (16) ====================
  { id: 139, name: 'VIX Percentile', formula: 'percentileofscore(vix_history, current_vix)', purpose: 'Where VIX sits vs history', file: 'data/polygon_data_fetcher.py', category: 'Volatility' },
  { id: 140, name: 'Realized Volatility', formula: 'std(log_returns) × √252 × 100', purpose: 'Historical volatility (annualized)', file: 'core/vix_hedge_manager.py', category: 'Volatility' },
  { id: 141, name: 'IV-RV Spread', formula: 'current_IV - realized_volatility', purpose: 'Volatility risk premium (IV overpricing)', file: 'core/vix_hedge_manager.py', category: 'Volatility' },
  { id: 142, name: 'VIX Term Structure', formula: 'M1 vs M2 futures spread', purpose: 'Contango vs backwardation detection', file: 'core/vix_hedge_manager.py', category: 'Volatility' },
  { id: 143, name: 'Contango Estimate', formula: 'VIX<15: 7%, 15-20: 5%, 20-25: 2%, >35: -2%', purpose: 'Dynamic term structure estimate', file: 'core/vix_hedge_manager.py', category: 'Volatility' },
  { id: 144, name: 'VIX Stress Level', formula: '4 tiers: normal, elevated, high, extreme', purpose: 'Position size multiplier selection', file: 'core/vix_hedge_manager.py', category: 'Volatility' },
  { id: 145, name: '25-Delta Skew', formula: 'put_IV_25delta - call_IV_25delta', purpose: 'Directional sentiment from options', file: 'core/volatility_surface_integration.py', category: 'Volatility' },
  { id: 146, name: 'ATM IV from VIX', formula: '(vix / 100) × 0.8 with term adjustment', purpose: 'Estimate ATM IV from VIX level', file: 'backend/enhanced_probability_calculator.py', category: 'Volatility' },
  { id: 147, name: 'Term Adjustment', formula: '0DTE: 1.15×, 5-14 DTE: 1.05×, else: 1.0×', purpose: 'DTE-based IV scaling', file: 'backend/enhanced_probability_calculator.py', category: 'Volatility' },
  { id: 148, name: 'Historical Vol (20d)', formula: 'returns.rolling(20).std() × √252', purpose: '20-day rolling volatility', file: 'data/polygon_data_fetcher.py', category: 'Volatility' },
  { id: 149, name: 'Log Returns', formula: 'np.log(close / close.shift(1))', purpose: 'Log-transformed returns for vol calc', file: 'various', category: 'Volatility' },
  { id: 150, name: 'SVI Vol Surface', formula: 'w(k) = a + b × (ρ × (k-m) + √((k-m)² + σ²))', purpose: 'Volatility surface parameterization', file: 'utils/volatility_surface.py', category: 'Volatility' },
  { id: 151, name: 'VIX 20-Day MA', formula: 'vix.rolling(20).mean()', purpose: 'VIX trend context', file: 'various', category: 'Volatility' },
  { id: 152, name: 'VVIX', formula: 'Volatility of VIX index', purpose: 'VIX timing signal', file: 'core/apollo_ml_engine.py', category: 'Volatility' },
  { id: 153, name: 'IV Rank 30d', formula: 'Rolling 30-day IV percentile', purpose: 'Short-term IV context', file: 'trading/ares_iron_condor.py', category: 'Volatility' },
  { id: 154, name: 'Contango/Backwardation', formula: 'front_IV vs back_IV comparison', purpose: 'Term structure classification', file: 'core/vix_hedge_manager.py', category: 'Volatility' },

  // ==================== BACKTEST SPECIFIC (30) ====================
  { id: 155, name: 'Expected Move', formula: 'price × (iv/100) × √(dte/365)', purpose: 'Expected price range for DTE', file: 'various', category: 'Backtest' },
  { id: 156, name: 'Put Spread Credit', formula: '(short_put_bid + long_put_ask) / 2', purpose: 'Bull put spread premium received', file: 'backtest/zero_dte_iron_condor.py', category: 'Backtest' },
  { id: 157, name: 'Call Spread Credit', formula: '(short_call_bid + long_call_ask) / 2', purpose: 'Bear call spread premium received', file: 'backtest/zero_dte_iron_condor.py', category: 'Backtest' },
  { id: 158, name: 'Iron Condor Credit', formula: 'put_spread_credit + call_spread_credit', purpose: 'Total IC premium received', file: 'backtest/zero_dte_iron_condor.py', category: 'Backtest' },
  { id: 159, name: 'Put Settlement', formula: 'max(0, short_strike - settlement_price)', purpose: 'Put spread settlement value', file: 'backtest/zero_dte_iron_condor.py', category: 'Backtest' },
  { id: 160, name: 'Call Settlement', formula: 'max(0, settlement_price - short_strike)', purpose: 'Call spread settlement value', file: 'backtest/zero_dte_iron_condor.py', category: 'Backtest' },
  { id: 161, name: 'Spread Max Loss', formula: 'spread_width - credit_received', purpose: 'Maximum loss on spread', file: 'backtest/zero_dte_iron_condor.py', category: 'Backtest' },
  { id: 162, name: 'Strike Distance', formula: 'price × (iv/100) × √(days/365) × sd_multiplier', purpose: 'SD-based strike selection', file: 'backtest/zero_dte_hybrid_fixed.py', category: 'Backtest' },
  { id: 163, name: 'GEX Walls from Options', formula: 'Calculate call/put walls from options chain', purpose: 'Dynamic wall calculation in backtest', file: 'backtest/zero_dte_hybrid_fixed.py', category: 'Backtest' },
  { id: 164, name: 'Put Premium Estimate', formula: 'Black-Scholes with IV adjustments', purpose: 'CSP premium estimation', file: 'backtest/wheel_backtest.py', category: 'Backtest' },
  { id: 165, name: 'Call Premium Estimate', formula: 'Black-Scholes with IV adjustments', purpose: 'CC premium estimation', file: 'backtest/wheel_backtest.py', category: 'Backtest' },
  { id: 166, name: 'Historical Vol (Rolling)', formula: 'returns.rolling(lookback).std() × √252', purpose: 'Rolling volatility for backtest', file: 'backtest/wheel_backtest.py', category: 'Backtest' },
  { id: 167, name: 'Bull Put Spread', formula: 'Short higher put - Long lower put', purpose: 'Bullish credit spread', file: 'various', category: 'Backtest' },
  { id: 168, name: 'Bear Call Spread', formula: 'Short lower call - Long higher call', purpose: 'Bearish credit spread', file: 'various', category: 'Backtest' },
  { id: 169, name: 'Iron Butterfly', formula: 'ATM short straddle + OTM wings', purpose: 'Neutral premium strategy', file: 'backtest/zero_dte_hybrid_fixed.py', category: 'Backtest' },
  { id: 170, name: 'Diagonal Spread', formula: 'Different strikes + different expirations', purpose: 'Time spread strategy', file: 'backtest/zero_dte_hybrid_fixed.py', category: 'Backtest' },
  { id: 171, name: 'Apache Directional', formula: 'GEX-based directional spread selection', purpose: 'Directional play based on GEX', file: 'backtest/zero_dte_hybrid_fixed.py', category: 'Backtest' },
  { id: 172, name: 'GEX Protected IC', formula: 'Iron condor with GEX-based wing placement', purpose: 'GEX-informed IC construction', file: 'backtest/zero_dte_hybrid_fixed.py', category: 'Backtest' },
  { id: 173, name: 'Flip Point Breakout', formula: 'Price crosses above flip point', purpose: 'Bullish breakout signal', file: 'backtest/backtest_gex_strategies.py', category: 'Backtest' },
  { id: 174, name: 'Flip Point Breakdown', formula: 'Price crosses below flip point', purpose: 'Bearish breakdown signal', file: 'backtest/backtest_gex_strategies.py', category: 'Backtest' },
  { id: 175, name: 'Call Wall Rejection', formula: 'Price rejected at call wall level', purpose: 'Resistance rejection signal', file: 'backtest/backtest_gex_strategies.py', category: 'Backtest' },
  { id: 176, name: 'Put Wall Bounce', formula: 'Price bounces at put wall level', purpose: 'Support bounce signal', file: 'backtest/backtest_gex_strategies.py', category: 'Backtest' },
  { id: 177, name: 'Negative GEX Squeeze', formula: 'Short gamma squeeze detection', purpose: 'Explosive move potential', file: 'backtest/backtest_gex_strategies.py', category: 'Backtest' },
  { id: 178, name: 'Time Factor (Backtest)', formula: '√(dte / 365)', purpose: 'Time scaling for premium', file: 'various', category: 'Backtest' },
  { id: 179, name: 'Equity Compound', formula: 'equity += pnl (daily reinvestment)', purpose: 'Compounding in backtest', file: 'backtest/zero_dte_aggressive.py', category: 'Backtest' },
  { id: 180, name: 'Tier Transitions', formula: 'Track scaling tier changes', purpose: 'Position scaling management', file: 'backtest/zero_dte_hybrid_scaling.py', category: 'Backtest' },
  { id: 181, name: 'Backtest Metrics', formula: 'Win rate, profit factor, Sharpe, etc.', purpose: 'Strategy performance summary', file: 'backtest/backtest_framework.py', category: 'Backtest' },
  { id: 182, name: 'Walk-Forward Windows', formula: 'Train window + test window splits', purpose: 'Prevent overfitting validation', file: 'quant/walk_forward_optimizer.py', category: 'Backtest' },
  { id: 183, name: 'IS/OOS Degradation', formula: '(in_sample - out_of_sample) / in_sample × 100', purpose: 'Strategy robustness measure', file: 'quant/walk_forward_optimizer.py', category: 'Backtest' },
  { id: 184, name: 'VRP Edge Metrics', formula: 'IV - RV spread tracking', purpose: 'Volatility risk premium edge', file: 'backtest/zero_dte_vrp_strategy.py', category: 'Backtest' },

  // ==================== ARES IRON CONDOR (10) ====================
  { id: 185, name: 'ARES Expected Move', formula: 'Based on VIX level and DTE', purpose: 'Strike distance for ARES IC', file: 'trading/ares_iron_condor.py', category: 'ARES' },
  { id: 186, name: '1 SD Strike', formula: 'spot ± expected_move × 0.5', purpose: 'Standard deviation-based strikes', file: 'trading/ares_iron_condor.py', category: 'ARES' },
  { id: 187, name: 'Max Loss per Spread', formula: '(spread_width - credit) × 100', purpose: 'ARES risk per spread', file: 'trading/ares_iron_condor.py', category: 'ARES' },
  { id: 188, name: 'Contracts from Risk', formula: '(capital × risk_pct) / max_loss', purpose: 'ARES position sizing', file: 'trading/ares_iron_condor.py', category: 'ARES' },
  { id: 189, name: 'VIX Percentile 30d', formula: 'Rolling 30-day VIX percentile', purpose: 'ARES entry filter', file: 'trading/ares_iron_condor.py', category: 'ARES' },
  { id: 190, name: 'Brier Score', formula: 'mean((predicted_prob - actual_outcome)²)', purpose: 'Probability forecast accuracy', file: 'trading/ares_iron_condor.py', category: 'ARES' },
  { id: 191, name: 'Daily Return Target', formula: '~0.5% per day × 20 days = 10% monthly', purpose: 'ARES compounding target', file: 'trading/ares_iron_condor.py', category: 'ARES' },
  { id: 192, name: 'Risk Per Trade', formula: '10% Kelly (aggressive)', purpose: 'ARES aggressive position sizing', file: 'trading/ares_iron_condor.py', category: 'ARES' },
  { id: 193, name: 'Daily Compounding', formula: 'equity = equity × (1 + daily_return)', purpose: 'ARES equity growth', file: 'trading/ares_iron_condor.py', category: 'ARES' },
  { id: 194, name: 'Session Tracking', formula: 'Track trade session metrics', purpose: 'ARES performance monitoring', file: 'trading/ares_iron_condor.py', category: 'ARES' },

  // ==================== ATHENA DIRECTIONAL (10) ====================
  { id: 195, name: 'Wall Filter', formula: 'Trade only within 1% of relevant GEX wall', purpose: 'ATHENA entry filter', file: 'trading/athena_directional_spreads.py', category: 'ATHENA' },
  { id: 196, name: 'R:R Ratio Filter', formula: 'max_profit / max_loss >= 1.5', purpose: 'ATHENA risk/reward minimum', file: 'trading/athena_directional_spreads.py', category: 'ATHENA' },
  { id: 197, name: 'Scale-Out 1', formula: '50% profit → exit 30% of contracts', purpose: 'First profit target', file: 'trading/athena_directional_spreads.py', category: 'ATHENA' },
  { id: 198, name: 'Scale-Out 2', formula: '75% profit → exit 30% of contracts', purpose: 'Second profit target', file: 'trading/athena_directional_spreads.py', category: 'ATHENA' },
  { id: 199, name: 'Trailing Stop', formula: 'Keep 50% of gains, trail 1.5× ATR', purpose: 'Protect profits on runners', file: 'trading/athena_directional_spreads.py', category: 'ATHENA' },
  { id: 200, name: 'Profit Threshold', formula: '40% of max profit before trailing', purpose: 'Let profits develop', file: 'trading/athena_directional_spreads.py', category: 'ATHENA' },
  { id: 201, name: 'Bull Call Spread', formula: 'Buy ATM call, Sell OTM call', purpose: 'ATHENA bullish position', file: 'trading/athena_directional_spreads.py', category: 'ATHENA' },
  { id: 202, name: 'Bear Call Spread', formula: 'Sell ATM call, Buy OTM call', purpose: 'ATHENA bearish position', file: 'trading/athena_directional_spreads.py', category: 'ATHENA' },
  { id: 203, name: 'Risk Adjusted Score', formula: 'Combined signal score 0-100', purpose: 'ATHENA trade quality', file: 'quant/gex_signal_integration.py', category: 'ATHENA' },
  { id: 204, name: 'Overall Conviction', formula: 'Weighted combination of all signals', purpose: 'ATHENA confidence score', file: 'quant/gex_signal_integration.py', category: 'ATHENA' },

  // ==================== GAMMA EXPIRATION (10) ====================
  { id: 205, name: 'DTE Bucket', formula: '0DTE, 1-2, 3-5, 7-10, 11-21, 30+, 45+', purpose: 'Expiration grouping', file: 'gamma/gamma_expiration_timeline.py', category: 'Gamma Exp' },
  { id: 206, name: 'Gamma % of Total', formula: 'bucket_gamma / total_gamma × 100', purpose: 'Gamma concentration by expiry', file: 'gamma/gamma_expiration_timeline.py', category: 'Gamma Exp' },
  { id: 207, name: 'ATM Gamma', formula: 'Sum of gamma for strikes within 2% of spot', purpose: 'Near-money gamma exposure', file: 'gamma/gamma_expiration_timeline.py', category: 'Gamma Exp' },
  { id: 208, name: 'Max Gamma Strike', formula: 'Strike with highest |gamma| in bucket', purpose: 'Key gamma level by expiry', file: 'gamma/gamma_expiration_timeline.py', category: 'Gamma Exp' },
  { id: 209, name: 'Call/Put Gamma Split', formula: 'Separate call vs put gamma by DTE', purpose: 'Directional gamma by expiry', file: 'gamma/gamma_expiration_timeline.py', category: 'Gamma Exp' },
  { id: 210, name: 'Gamma Decay Pattern', formula: 'How gamma shifts as DTE decreases', purpose: 'Dealer hedging behavior', file: 'gamma/gamma_expiration_timeline.py', category: 'Gamma Exp' },
  { id: 211, name: 'Daily Impact Score', formula: 'Based on gamma concentration', purpose: 'Trading impact by day', file: 'gamma/gamma_expiration_builder.py', category: 'Gamma Exp' },
  { id: 212, name: 'Weekly Evolution', formula: 'Week-over-week gamma change', purpose: 'Gamma trend analysis', file: 'gamma/gamma_expiration_builder.py', category: 'Gamma Exp' },
  { id: 213, name: 'Gamma Decay %', formula: 'Day-over-day gamma percentage change', purpose: 'Gamma decay tracking', file: 'gamma/gamma_correlation_tracker.py', category: 'Gamma Exp' },
  { id: 214, name: 'Actual Price Move %', formula: 'Next day realized price change', purpose: 'Gamma prediction validation', file: 'gamma/gamma_correlation_tracker.py', category: 'Gamma Exp' },

  // ==================== ML FEATURES (18) ====================
  { id: 215, name: '24 Apollo Features', formula: 'Price, GEX, VIX, Greeks, Technical indicators', purpose: 'APOLLO ML model input features', file: 'core/apollo_ml_engine.py', category: 'ML' },
  { id: 216, name: '15 Prometheus Features', formula: 'DTE, Delta, IV, IV Rank, VIX, VIX Percentile, etc.', purpose: 'PROMETHEUS ML model features', file: 'trading/prometheus_ml.py', category: 'ML' },
  { id: 217, name: '14 Pattern Learner Features', formula: 'RSI (5 TF), Net Gamma, Wall Distance, etc.', purpose: 'Pattern recognition features', file: 'ai/autonomous_ml_pattern_learner.py', category: 'ML' },
  { id: 218, name: 'Direction Probability', formula: 'ML classifier output: UP/DOWN/FLAT', purpose: 'Directional prediction', file: 'quant/gex_probability_models.py', category: 'ML' },
  { id: 219, name: 'Flip Gravity', formula: 'Probability price gravitates to flip point', purpose: 'Mean reversion probability', file: 'quant/gex_probability_models.py', category: 'ML' },
  { id: 220, name: 'Magnet Attraction', formula: 'Probability price reaches nearest magnet', purpose: 'Price target probability', file: 'quant/gex_probability_models.py', category: 'ML' },
  { id: 221, name: 'Expected Volatility', formula: 'ML-predicted price range percentage', purpose: 'Volatility forecast', file: 'quant/gex_probability_models.py', category: 'ML' },
  { id: 222, name: 'Pin Zone Probability', formula: 'Probability of staying between magnets', purpose: 'Range-bound probability', file: 'quant/gex_probability_models.py', category: 'ML' },
  { id: 223, name: 'Oracle Win Probability', formula: 'Aggregated GEX + ML + VIX signals', purpose: 'Trade success probability', file: 'quant/oracle_advisor.py', category: 'ML' },
  { id: 224, name: 'Confidence Score', formula: '0-100 scale based on signal agreement', purpose: 'Overall decision confidence', file: 'various', category: 'ML' },
  { id: 225, name: 'Claude AI Adjustment', formula: '-0.10 to +0.10 confidence adjustment', purpose: 'AI-based confidence modifier', file: 'various', category: 'ML' },
  { id: 226, name: 'Liberation Accuracy', formula: 'price_change >= 0.3% = BULLISH correct', purpose: 'Liberation signal validation', file: 'gamma/liberation_outcomes_tracker.py', category: 'ML' },
  { id: 227, name: 'Target Hit', formula: 'price >= target (bullish) or <= target (bearish)', purpose: 'Trade target success', file: 'gamma/liberation_outcomes_tracker.py', category: 'ML' },
  { id: 228, name: '7-Day Win Rate', formula: 'correct / total × 100 by signal_type', purpose: 'Rolling system accuracy', file: 'gamma/liberation_outcomes_tracker.py', category: 'ML' },
  { id: 229, name: 'Recommendation Score', formula: 'STRONG_TRADE, TRADE, NEUTRAL, CAUTION, SKIP', purpose: 'Trade recommendation tier', file: 'trading/prometheus_ml.py', category: 'ML' },
  { id: 230, name: 'Feature Normalization', formula: 'StandardScaler: (x - mean) / std', purpose: 'ML feature preprocessing', file: 'various', category: 'ML' },
  { id: 231, name: 'XGBoost Predictions', formula: 'Ensemble gradient boosting classifier', purpose: 'ML model prediction', file: 'quant/gex_probability_models.py', category: 'ML' },
  { id: 232, name: 'Cross-Validation Score', formula: 'TimeSeriesSplit accuracy average', purpose: 'Model validation metric', file: 'quant/gex_probability_models.py', category: 'ML' },

  // ==================== WHEEL STRATEGY (8) ====================
  { id: 233, name: 'Net Premium', formula: '(premium_received - premium_paid) × contracts × 100', purpose: 'Wheel cycle profit', file: 'trading/wheel_strategy.py', category: 'Wheel' },
  { id: 234, name: 'Cost Basis Adjustment', formula: 'Include all premiums collected in cost basis', purpose: 'True cost calculation', file: 'trading/wheel_strategy.py', category: 'Wheel' },
  { id: 235, name: 'Assignment Impact', formula: 'strike_price × shares_assigned', purpose: 'Assignment cost', file: 'trading/wheel_strategy.py', category: 'Wheel' },
  { id: 236, name: 'Premium Yield %', formula: 'premium / strike × 100', purpose: 'Return on capital per trade', file: 'trading/wheel_strategy.py', category: 'Wheel' },
  { id: 237, name: 'Annualized Return', formula: 'yield × (365 / dte)', purpose: 'Yearly equivalent return', file: 'trading/wheel_strategy.py', category: 'Wheel' },
  { id: 238, name: 'Roll Credit', formula: 'new_premium - old_premium_cost', purpose: 'Profit from rolling position', file: 'trading/wheel_strategy.py', category: 'Wheel' },
  { id: 239, name: 'ML Score (Wheel)', formula: 'PROMETHEUS prediction for wheel trades', purpose: 'ML-assisted wheel decisions', file: 'trading/spx_wheel_ml.py', category: 'Wheel' },
  { id: 240, name: 'Outcome Tracking', formula: 'Win/loss tracking by ML score', purpose: 'ML feedback loop', file: 'trading/prometheus_outcome_tracker.py', category: 'Wheel' },

  // ==================== ENSEMBLE STRATEGY (10) ====================
  { id: 241, name: 'Strategy Win Rate', formula: 'wins / total_trades × 100', purpose: 'Individual strategy performance', file: 'quant/ensemble_strategy.py', category: 'Ensemble' },
  { id: 242, name: 'Sharpe Estimate', formula: '(mean(pnl) / std(pnl)) × √252', purpose: 'Strategy risk-adjusted return', file: 'quant/ensemble_strategy.py', category: 'Ensemble' },
  { id: 243, name: 'Base Weight', formula: 'win_rate / 100', purpose: 'Starting weight from win rate', file: 'quant/ensemble_strategy.py', category: 'Ensemble' },
  { id: 244, name: 'Sharpe Adjustment', formula: '1 + (min(sharpe, 3) / 6)', purpose: 'Sharpe-based weight modifier', file: 'quant/ensemble_strategy.py', category: 'Ensemble' },
  { id: 245, name: 'Regime Adjustment', formula: 'regime_wr / overall_wr, clamped [0.5, 1.5]', purpose: 'Regime-specific weight modifier', file: 'quant/ensemble_strategy.py', category: 'Ensemble' },
  { id: 246, name: 'Recency Adjustment', formula: 'Recent 5 trades win rate weighted', purpose: 'Recent performance modifier', file: 'quant/ensemble_strategy.py', category: 'Ensemble' },
  { id: 247, name: 'Ensemble Signal', formula: 'Weighted combination of all strategy signals', purpose: 'Combined trading signal', file: 'quant/ensemble_strategy.py', category: 'Ensemble' },
  { id: 248, name: 'Bullish Weight', formula: 'Sum of weights for bullish signals', purpose: 'Bullish vote strength', file: 'quant/ensemble_strategy.py', category: 'Ensemble' },
  { id: 249, name: 'Bearish Weight', formula: 'Sum of weights for bearish signals', purpose: 'Bearish vote strength', file: 'quant/ensemble_strategy.py', category: 'Ensemble' },
  { id: 250, name: 'Position Size Mult', formula: 'clip(conviction, 0.25, 1.0)', purpose: 'Conviction-based sizing', file: 'quant/ensemble_strategy.py', category: 'Ensemble' },

  // ==================== ARGUS 0DTE (8) ====================
  { id: 251, name: 'Net Gamma per Strike', formula: 'call_gamma × call_OI + put_gamma × put_OI', purpose: 'Strike-level gamma exposure', file: 'core/argus_engine.py', category: 'ARGUS' },
  { id: 252, name: 'ROC 1-Min', formula: 'Rate of change over 1 minute', purpose: 'Short-term gamma momentum', file: 'core/argus_engine.py', category: 'ARGUS' },
  { id: 253, name: 'ROC 5-Min', formula: 'Rate of change over 5 minutes', purpose: 'Medium-term gamma momentum', file: 'core/argus_engine.py', category: 'ARGUS' },
  { id: 254, name: 'Gamma Flip Detection', formula: 'Sign change in net gamma', purpose: 'Detect gamma flip events', file: 'core/argus_engine.py', category: 'ARGUS' },
  { id: 255, name: 'Pin Zone Probability', formula: 'Hybrid ML + gamma-weighted distance', purpose: 'Probability of price pinning', file: 'core/argus_engine.py', category: 'ARGUS' },
  { id: 256, name: 'Danger Zone Detection', formula: 'SPIKE: >15% 1min, BUILDING: >25% 5min, COLLAPSING: <-25% 5min', purpose: 'Identify dangerous gamma conditions', file: 'core/argus_engine.py', category: 'ARGUS' },
  { id: 257, name: 'Expected Move (0DTE)', formula: 'ATM_call_price + ATM_put_price', purpose: '0DTE expected move from straddle', file: 'core/argus_engine.py', category: 'ARGUS' },
  { id: 258, name: 'Market Status', formula: 'pre_market / open / after_hours / closed', purpose: 'Current market session', file: 'core/argus_engine.py', category: 'ARGUS' },

  // ==================== VALIDATION & STATS (10) ====================
  { id: 259, name: 'Accuracy Score', formula: 'correct_predictions / total_predictions × 100', purpose: 'Prediction accuracy percentage', file: 'validation/quant_validation.py', category: 'Validation' },
  { id: 260, name: 'T-Statistic', formula: 'Statistical significance of returns', purpose: 'Hypothesis test statistic', file: 'validation/quant_validation.py', category: 'Validation' },
  { id: 261, name: 'P-Value', formula: 'Probability of null hypothesis', purpose: 'Statistical significance level', file: 'validation/quant_validation.py', category: 'Validation' },
  { id: 262, name: 'Confidence Interval 95%', formula: 'mean ± 1.96 × std_err', purpose: '95% confidence bounds', file: 'validation/quant_validation.py', category: 'Validation' },
  { id: 263, name: 'Correlation', formula: 'Pearson correlation coefficient', purpose: 'Linear relationship strength', file: 'validation/quant_validation.py', category: 'Validation' },
  { id: 264, name: 'Mean Error %', formula: 'mean(|predicted - actual| / actual) × 100', purpose: 'Average prediction error', file: 'validation/quant_validation.py', category: 'Validation' },
  { id: 265, name: 'Precision/Recall/F1', formula: 'Classification metrics', purpose: 'ML model evaluation', file: 'quant/ml_regime_classifier.py', category: 'Validation' },
  { id: 266, name: 'R² Score', formula: '1 - SS_res / SS_tot', purpose: 'Regression goodness of fit', file: 'quant/gex_probability_models.py', category: 'Validation' },
  { id: 267, name: 'MAE', formula: 'mean(|predicted - actual|)', purpose: 'Mean absolute error', file: 'quant/gex_probability_models.py', category: 'Validation' },
  { id: 268, name: 'RMSE', formula: '√(mean((predicted - actual)²))', purpose: 'Root mean squared error', file: 'quant/gex_probability_models.py', category: 'Validation' },
]

// Category metadata with icons
const CATEGORIES = [
  { name: 'GEX', icon: Activity, color: 'text-purple-400', bgColor: 'bg-purple-500/20', count: 18 },
  { name: 'Greeks', icon: Calculator, color: 'text-blue-400', bgColor: 'bg-blue-500/20', count: 18 },
  { name: 'Technical', icon: TrendingUp, color: 'text-green-400', bgColor: 'bg-green-500/20', count: 15 },
  { name: 'Costs', icon: Hash, color: 'text-yellow-400', bgColor: 'bg-yellow-500/20', count: 12 },
  { name: 'Kelly', icon: Target, color: 'text-orange-400', bgColor: 'bg-orange-500/20', count: 15 },
  { name: 'Probability', icon: Percent, color: 'text-pink-400', bgColor: 'bg-pink-500/20', count: 12 },
  { name: 'Regime', icon: Layers, color: 'text-cyan-400', bgColor: 'bg-cyan-500/20', count: 14 },
  { name: 'Psychology', icon: Brain, color: 'text-red-400', bgColor: 'bg-red-500/20', count: 14 },
  { name: 'Risk', icon: Shield, color: 'text-emerald-400', bgColor: 'bg-emerald-500/20', count: 20 },
  { name: 'Volatility', icon: Zap, color: 'text-amber-400', bgColor: 'bg-amber-500/20', count: 16 },
  { name: 'Backtest', icon: Clock, color: 'text-indigo-400', bgColor: 'bg-indigo-500/20', count: 30 },
  { name: 'ARES', icon: Target, color: 'text-rose-400', bgColor: 'bg-rose-500/20', count: 10 },
  { name: 'ATHENA', icon: GitBranch, color: 'text-violet-400', bgColor: 'bg-violet-500/20', count: 10 },
  { name: 'Gamma Exp', icon: Clock, color: 'text-fuchsia-400', bgColor: 'bg-fuchsia-500/20', count: 10 },
  { name: 'ML', icon: Brain, color: 'text-sky-400', bgColor: 'bg-sky-500/20', count: 18 },
  { name: 'Wheel', icon: ArrowUpDown, color: 'text-lime-400', bgColor: 'bg-lime-500/20', count: 8 },
  { name: 'Ensemble', icon: Layers, color: 'text-teal-400', bgColor: 'bg-teal-500/20', count: 10 },
  { name: 'ARGUS', icon: Activity, color: 'text-orange-400', bgColor: 'bg-orange-500/20', count: 8 },
  { name: 'Validation', icon: Check, color: 'text-green-400', bgColor: 'bg-green-500/20', count: 10 },
]

export default function FeatureDocsPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set(['GEX']))
  const [copiedId, setCopiedId] = useState<number | null>(null)

  // Filter calculations based on search and category
  const filteredCalculations = useMemo(() => {
    return CALCULATIONS.filter(calc => {
      const matchesSearch = searchQuery === '' ||
        calc.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        calc.formula.toLowerCase().includes(searchQuery.toLowerCase()) ||
        calc.purpose.toLowerCase().includes(searchQuery.toLowerCase()) ||
        calc.file.toLowerCase().includes(searchQuery.toLowerCase())

      const matchesCategory = selectedCategory === null || calc.category === selectedCategory

      return matchesSearch && matchesCategory
    })
  }, [searchQuery, selectedCategory])

  // Group by category
  const groupedCalculations = useMemo(() => {
    const groups: { [key: string]: Calculation[] } = {}
    filteredCalculations.forEach(calc => {
      if (!groups[calc.category]) {
        groups[calc.category] = []
      }
      groups[calc.category].push(calc)
    })
    return groups
  }, [filteredCalculations])

  const toggleCategory = (category: string) => {
    const newExpanded = new Set(expandedCategories)
    if (newExpanded.has(category)) {
      newExpanded.delete(category)
    } else {
      newExpanded.add(category)
    }
    setExpandedCategories(newExpanded)
  }

  const expandAll = () => {
    setExpandedCategories(new Set(CATEGORIES.map(c => c.name)))
  }

  const collapseAll = () => {
    setExpandedCategories(new Set())
  }

  const copyFormula = (id: number, formula: string) => {
    navigator.clipboard.writeText(formula)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const getCategoryMeta = (name: string) => {
    return CATEGORIES.find(c => c.name === name) || CATEGORIES[0]
  }

  return (
    <div className="min-h-screen bg-[#0a0a0f]">
      <Navigation />

      <main className="container mx-auto px-4 py-8 max-w-7xl">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <BookOpen className="w-8 h-8 text-purple-400" />
            <h1 className="text-3xl font-bold text-white">Feature Documentation</h1>
          </div>
          <p className="text-gray-400">
            Complete reference of all 268 calculations and features in AlphaGEX
          </p>
        </div>

        {/* Stats Bar */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-[#12121a] border border-gray-800 rounded-lg p-4">
            <div className="text-2xl font-bold text-white">268</div>
            <div className="text-sm text-gray-400">Total Calculations</div>
          </div>
          <div className="bg-[#12121a] border border-gray-800 rounded-lg p-4">
            <div className="text-2xl font-bold text-white">19</div>
            <div className="text-sm text-gray-400">Categories</div>
          </div>
          <div className="bg-[#12121a] border border-gray-800 rounded-lg p-4">
            <div className="text-2xl font-bold text-white">{filteredCalculations.length}</div>
            <div className="text-sm text-gray-400">Showing</div>
          </div>
          <div className="bg-[#12121a] border border-gray-800 rounded-lg p-4">
            <div className="text-2xl font-bold text-white">92</div>
            <div className="text-sm text-gray-400">Source Files</div>
          </div>
        </div>

        {/* Search and Filters */}
        <div className="bg-[#12121a] border border-gray-800 rounded-lg p-4 mb-6">
          <div className="flex flex-col md:flex-row gap-4">
            {/* Search */}
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-500 w-5 h-5" />
              <input
                type="text"
                placeholder="Search by name, formula, purpose, or file..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2 bg-[#1a1a24] border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
            </div>

            {/* Category Filter */}
            <div className="flex items-center gap-2">
              <Filter className="w-5 h-5 text-gray-500" />
              <select
                value={selectedCategory || ''}
                onChange={(e) => setSelectedCategory(e.target.value || null)}
                className="px-4 py-2 bg-[#1a1a24] border border-gray-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
              >
                <option value="">All Categories</option>
                {CATEGORIES.map(cat => (
                  <option key={cat.name} value={cat.name}>{cat.name} ({cat.count})</option>
                ))}
              </select>
            </div>

            {/* Expand/Collapse */}
            <div className="flex gap-2">
              <button
                onClick={expandAll}
                className="px-4 py-2 bg-[#1a1a24] border border-gray-700 rounded-lg text-white hover:bg-[#2a2a34] transition-colors"
              >
                Expand All
              </button>
              <button
                onClick={collapseAll}
                className="px-4 py-2 bg-[#1a1a24] border border-gray-700 rounded-lg text-white hover:bg-[#2a2a34] transition-colors"
              >
                Collapse All
              </button>
            </div>
          </div>
        </div>

        {/* Category Quick Jump */}
        <div className="flex flex-wrap gap-2 mb-6">
          {CATEGORIES.map(cat => {
            const count = groupedCalculations[cat.name]?.length || 0
            if (count === 0 && selectedCategory !== cat.name) return null
            return (
              <button
                key={cat.name}
                onClick={() => {
                  setSelectedCategory(selectedCategory === cat.name ? null : cat.name)
                  if (!expandedCategories.has(cat.name)) {
                    toggleCategory(cat.name)
                  }
                }}
                className={`px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                  selectedCategory === cat.name
                    ? `${cat.bgColor} ${cat.color} ring-2 ring-current`
                    : 'bg-[#1a1a24] text-gray-400 hover:bg-[#2a2a34]'
                }`}
              >
                {cat.name} ({count})
              </button>
            )
          })}
        </div>

        {/* Calculations by Category */}
        <div className="space-y-4">
          {Object.entries(groupedCalculations).map(([category, calcs]) => {
            const meta = getCategoryMeta(category)
            const Icon = meta.icon
            const isExpanded = expandedCategories.has(category)

            return (
              <div key={category} className="bg-[#12121a] border border-gray-800 rounded-lg overflow-hidden">
                {/* Category Header */}
                <button
                  onClick={() => toggleCategory(category)}
                  className="w-full flex items-center justify-between p-4 hover:bg-[#1a1a24] transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${meta.bgColor}`}>
                      <Icon className={`w-5 h-5 ${meta.color}`} />
                    </div>
                    <div className="text-left">
                      <h2 className="text-lg font-semibold text-white">{category}</h2>
                      <p className="text-sm text-gray-500">{calcs.length} calculations</p>
                    </div>
                  </div>
                  {isExpanded ? (
                    <ChevronUp className="w-5 h-5 text-gray-400" />
                  ) : (
                    <ChevronDown className="w-5 h-5 text-gray-400" />
                  )}
                </button>

                {/* Calculations List */}
                {isExpanded && (
                  <div className="border-t border-gray-800">
                    <table className="w-full">
                      <thead className="bg-[#0a0a0f]">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-8">#</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Formula</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider hidden lg:table-cell">Purpose</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider hidden md:table-cell">File</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-12"></th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-800">
                        {calcs.map((calc) => (
                          <tr key={calc.id} className="hover:bg-[#1a1a24] transition-colors">
                            <td className="px-4 py-3 text-sm text-gray-500">{calc.id}</td>
                            <td className="px-4 py-3">
                              <span className="text-sm font-medium text-white">{calc.name}</span>
                            </td>
                            <td className="px-4 py-3">
                              <code className="text-xs text-purple-300 bg-purple-500/10 px-2 py-1 rounded font-mono break-all">
                                {calc.formula}
                              </code>
                            </td>
                            <td className="px-4 py-3 text-sm text-gray-400 hidden lg:table-cell max-w-xs">
                              {calc.purpose}
                            </td>
                            <td className="px-4 py-3 hidden md:table-cell">
                              <span className="text-xs text-gray-500 font-mono">{calc.file}</span>
                            </td>
                            <td className="px-4 py-3">
                              <button
                                onClick={() => copyFormula(calc.id, calc.formula)}
                                className="p-1.5 rounded hover:bg-gray-700 transition-colors"
                                title="Copy formula"
                              >
                                {copiedId === calc.id ? (
                                  <Check className="w-4 h-4 text-green-400" />
                                ) : (
                                  <Copy className="w-4 h-4 text-gray-500" />
                                )}
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Empty State */}
        {filteredCalculations.length === 0 && (
          <div className="bg-[#12121a] border border-gray-800 rounded-lg p-12 text-center">
            <Search className="w-12 h-12 text-gray-600 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-white mb-2">No calculations found</h3>
            <p className="text-gray-500">Try adjusting your search or filter criteria</p>
          </div>
        )}

        {/* Footer */}
        <div className="mt-8 text-center text-sm text-gray-500">
          <p>AlphaGEX Feature Documentation • Generated from codebase analysis</p>
          <p className="mt-1">268 calculations across 19 categories from 92 source files</p>
        </div>
      </main>
    </div>
  )
}
