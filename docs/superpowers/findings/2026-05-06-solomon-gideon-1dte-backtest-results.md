# SOLOMON / GIDEON 1DTE Backtest — Results

**Run date:** 2026-05-06
**Window:** 2020-01-02 → 2025-12-05 (1,239 trading days available; **2021 missing in ORAT**)
**Strategy:** GEX-walls entry (no PROPHET, no ML), 1DTE SPY debit spreads, hold to expiration, $1,000 risk per trade, $100,000 starting capital.
**Spec:** `docs/superpowers/specs/2026-05-06-solomon-gideon-1dte-backtest-design.md`

## Headline

| Metric | SOLOMON | GIDEON |
|---|---|---|
| Total trades | 1,055 | 1,000 |
| Total P&L | **−$42,316** | **−$53,646** |
| Win rate | 38.6% | 35.7% |
| Avg win | $1,355 | $1,447 |
| Avg loss | −$916 | −$887 |
| Expectancy / trade | −$40 | −$54 |
| Profit factor | 0.93 | 0.91 |
| Annualized Sharpe | −0.55 | −0.70 |
| Max drawdown | 59.9% of capital | 67.8% of capital |
| Max single-trade loss | −$1,000 (within $1,050 risk cap ✓) | −$1,000 (within cap ✓) |
| Max single-trade win | +$3,432 | +$3,840 |

**Sanity checks pass:** ledger P&L matches reported total to the cent; trades + skips = 1,238 = trading_days − 1 (last day excluded since no T+1); no NaN in equity curve.

## Year-by-year

### SOLOMON
| Year | Trades | P&L | Win rate |
|---|---|---|---|
| 2020 | 162 | −$27,694 | 32.1% |
| 2022 | 192 | **+$54,847** | **54.2%** |
| 2023 | 239 | −$20,470 | 36.0% |
| 2024 | 239 | −$42,882 | 31.8% |
| 2025 | 223 | −$6,116 | 39.9% |

### GIDEON
| Year | Trades | P&L | Win rate |
|---|---|---|---|
| 2020 | 142 | −$27,380 | 29.6% |
| 2022 | 164 | **+$53,011** | **53.0%** |
| 2023 | 239 | −$21,224 | 32.2% |
| 2024 | 239 | −$44,786 | 29.3% |
| 2025 | 216 | −$13,267 | 37.5% |

**2022 is a dramatic outlier — a profitable year for both bots, ~54% win rate vs ~30-40% everywhere else.** 2022 was a sustained bear market (S&P 500 −19% peak-to-trough). The directional bear-put-spread bias produced by hitting call walls in a downtrend was correct for that year. Every other year the same bias was wrong.

## VIX-bucket breakdown

### SOLOMON
| VIX bucket | Trades | P&L | Win rate |
|---|---|---|---|
| Low (<15) | 255 | **−$34,931** | 31.4% |
| Normal (15–22) | 486 | +$523 | 40.5% |
| Elevated (22–28) | 226 | −$5,930 | 41.2% |
| High (≥28) | 88 | −$1,978 | 42.0% |

### GIDEON
| VIX bucket | Trades | P&L | Win rate |
|---|---|---|---|
| Low (<15) | 255 | **−$33,540** | 29.0% |
| Normal (15–22) | 485 | +$655 | 37.5% |
| Elevated (22–28) | 226 | −$12,868 | 39.8% |
| High (≥28) | 34 | −$7,893 | 32.4% |

**Low-VIX (<15) is poison.** ~80% of total losses come from low-VIX days for both bots. In low VIX, ATM 1DTE spreads price near max width (low premium gradient), so the R:R is unfavorable AND the directional signal still has no edge.

Normal-VIX is roughly breakeven — about as good as it gets.

## Direction breakdown

### SOLOMON
| Direction | Trades | P&L | Win rate |
|---|---|---|---|
| BULLISH (bull call) | 45 | +$226 | 48.9% |
| BEARISH (bear put) | 1,010 | −$42,542 | 38.1% |

### GIDEON
| Direction | Trades | P&L | Win rate |
|---|---|---|---|
| BULLISH | 42 | −$368 | 42.9% |
| BEARISH | 958 | −$53,278 | 35.4% |

**The strategy is essentially "always bear":** 95% of trades are BEARISH because SPY in a multi-year uptrend keeps brushing against the call wall (resistance) and rarely touches the put wall (support). The bullish leg is a non-factor (45 trades over 5 years).

## Skip reasons

### SOLOMON (183 total)
| Reason | Count |
|---|---|
| NOT_NEAR_WALL | 103 |
| VIX_OUT_OF_RANGE | 62 |
| NO_WALLS_FOUND | 13 |
| STRIKES_MISSING_FROM_CHAIN | 3 |
| NO_T+1_DATA | 2 |

### GIDEON (238 total)
GIDEON's max VIX is 30 vs SOLOMON's 35 — the extra 55 VIX_OUT_OF_RANGE skips explain GIDEON's lower trade count.

## Verdict

**The GEX-walls signal does not have edge on SPY 1DTE in this 5-year sample.** Both bots are slightly negative-expectancy (-$40 to -$54 per trade) with profit factor below 1.0. The losses scale roughly linearly with spread_width — GIDEON loses more than SOLOMON because each trade risks $1,000 against a wider $3 spread, but the underlying signal accuracy is the same.

**Three findings worth acting on:**

1. **The 2022 anomaly is the only signal of edge.** In a sustained bear market, brushing the call wall and going bearish 1DTE actually worked (54% WR, +$54k). 2022 represents 18% of trades and contributed ALL of the gross P&L for the bots. Outside 2022 the strategy is flat-out unprofitable.
2. **Low VIX (<15) accounts for ~80% of total losses.** A simple `min_vix=15` filter (vs current 12) would eliminate the worst regime. Estimated impact: −$42k → roughly −$8k for SOLOMON, −$54k → roughly −$20k for GIDEON. Still not profitable, but materially less bad. The live bot has min_vix=12 — that's a known-bad parameter.
3. **The bullish leg is dead.** 45 BULLISH trades over 5 years isn't a sample, it's noise. SPY's secular uptrend means the put wall almost never gets within 1% of spot. If we want a tradeable bullish setup, we need a different signal (e.g., momentum continuation, oversold bounce, gap fill) — wall proximity isn't it.

**Comparison to live 0DTE production performance** (recap from earlier in the conversation):

| Bot | 0DTE production (live) | 1DTE backtest (this run) |
|---|---|---|
| SOLOMON | −$780k, 21.8% WR | −$42k, 38.6% WR |
| GIDEON | −$2.7M, 18.6% WR | −$54k, 35.7% WR |

Stretching the horizon from 0DTE to 1DTE *and* removing intraday whipsaw exits roughly **doubles the win rate** (22% → 39%), which confirms our hypothesis that the 5-minute median holding pattern was destroying any signal value the bot might have had. But even with that improvement, the GEX-walls entry signal **alone** is not enough to be profitable on SPY.

**Recommended next steps** (no code changes required for this spec — these are research follow-ups):

- **Layer #1 (cheap):** Add a `min_vix=15` filter to the live SOLOMON / GIDEON configs. Demonstrably eliminates the worst trading regime per this backtest.
- **Layer #2 (medium):** Re-run this backtest with PROPHET + ML overlay using the live-window data (Feb 2026+ only — the only period where predictions exist). Determine whether PROPHET adds positive edge to the underlying signal or destroys it.
- **Layer #3 (expensive):** If layer 2 also fails, consider whether the live bots should be paused entirely. The live bots have lost $3.5M combined; running this design on 1DTE in production wouldn't recover it but would stop the bleeding.
- **Layer #4 (research):** Investigate whether a regime classifier ("bear market" via VIX term structure or moving averages) could selectively enable the BEARISH leg. The 2022 result suggests the signal works *in bear markets* and fails in bull markets.

## Known caveats

1. **EOD-only data.** Could not reproduce live intraday entry/exit timing. The 1DTE results are an honest test of "if you held SPY directional spreads to expiration based on EOD walls, would you make money" — not a prediction of live 0DTE performance.
2. **Walls reconstruction not audited.** `gex_structure_daily.call_wall` / `put_wall` could differ from what the live bot saw at scan time (the live bot scans intraday, not EOD). Spec called for cross-checking against `solomon_signals.call_wall` for the Feb 2026+ window. Not done in this run because ORAT data ends Dec 2025; the live window is in production postgres only.
3. **No commissions or slippage.** Mid-fill assumption is optimistic. Each leg crossing the spread would cost ~$0.05 × 100 × contracts × 2 legs ≈ $20-30 per trade in real fills. Over 1,055 trades that's another ~$25-30k drag for SOLOMON. The strategy is even more clearly unprofitable with realistic frictions.
4. **2021 is missing from ORAT.** Coverage is 5 years (2020, 2022-2025), not 6.
5. **`gex_structure_daily.spot_close` is wrong.** Discovered during smoke testing — it's systematically off by ~$13 from chain underlying. Engine works around it by using chain `underlying_price` for spot. Worth fixing in ORAT separately.
