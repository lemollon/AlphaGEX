# AGAPE-SPOT Crypto Trading System

## Architecture
- **Location**: `trading/agape_spot/` (trader.py, signals.py, models.py, executor.py, db.py)
- **Routes**: `backend/api/routes/agape_spot_routes.py`
- **Exchange**: Coinbase Advanced Trade (spot only, no futures)
- **Tickers**: ETH-USD, BTC-USD, DOGE-USD, XRP-USD, SHIB-USD
- **Strategy**: Long-only spot crypto with Bayesian win tracking, funding regime gates, EWMA choppy market filter
- **Accounts**: `default` (main), `dedicated` (per-ticker), `paper` (shadow)

## Key Tables
- `agape_spot_positions` - All positions (open + closed): position_id, ticker, status, entry_price, close_price, quantity, realized_pnl, close_reason, account_label, funding_regime_at_entry, open_time, close_time, sell_fail_count, entry_fee_usd, exit_fee_usd
- `agape_spot_scan_activity` - Every scan cycle with outcome (TRADE, NO_TRADE, BLOCKED_BY_CAPACITY, etc.)
- `agape_spot_win_tracker` - Bayesian alpha/beta per ticker per funding regime
- `agape_spot_equity_snapshots` - Periodic equity snapshots with eth_price
- `agape_spot_ml_shadow` - ML prediction shadow logging (actual_outcome column, not actual_win)

## Profitability Analysis Scripts
- `scripts/analyze_agape_spot_profitability.py` - P1-P17 baseline queries
- `scripts/analyze_agape_spot_profitability_p2.py` - P18-P30 deep dive
- `scripts/analyze_agape_spot_postfix.py` - PF1-PF11 post-fix monitoring

## Feb 15 2026 Audit Findings (Pre-Fix Baseline)

**P&L Summary (pre-fix, live non-fallback only):**
| Ticker | Trades | P&L | WR | Avg Win | Avg Loss | EV/trade | Verdict |
|--------|--------|-----|-----|---------|----------|----------|---------|
| ETH-USD | 196 | +$188.05 | 58.2% | $7.99 | -$8.82 | +$0.96 | Profitable but loses $475 overnight |
| DOGE-USD | 303 | +$45.79 | 61.1% | $0.31 | -$0.09 | +$0.15 | Overtrading (42.6/day), fees eat profit |
| BTC-USD | 19 | +$0.24 | 52.6% | $0.06 | -$0.03 | +$0.02 | 17/19 expired MAX_HOLD, wrong timeout |
| XRP-USD | 117 | -$0.55 | 50.4% | $0.05 | -$0.06 | -$0.005 | Negative EV |
| SHIB-USD | 142 | -$0.64 | 48.6% | $0.07 | -$0.08 | -$0.007 | Negative EV |

**Critical Issues**: Fee blindness (3/777 trades had fees), ETH overnight drain (-$475), DOGE overtrading (42.6/day), position pileup (93 BTC), fallback pollution (359 BTC_fallback at 3.3% WR).

**Fixes Deployed Feb 15 2026**: F1-F12 (silent sell retry, pileup fix, EWMA gate, BTC tightened, bias split removed, momentum relaxed, orphan auto-sell, ETH max 3, DOGE funding gate, fallback cleanup, per-ticker max_hold, paper mirrors live).

**Post-Fix Monitoring**: Run `python scripts/analyze_agape_spot_postfix.py` every 48-72h. Fix cutoff: `2026-02-15 20:00:00+00`.

**Still Not Fixed**: Fee tracking in executor.py, no time-of-day restriction for ETH, XRP/SHIB should be disabled.
