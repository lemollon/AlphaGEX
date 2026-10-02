# TTP + Trade Volatility Stock Backtest V1

This branch adds a conservative backtest harness for the proposed long-only intraday stock strategy.

## What it tests

- Universe: symbols actually stored by the AlphaGEX morning Trade Volatility/watchlist pipeline.
- Direction: bullish opening-range-breakout setups only.
- Entry window: 09:35–11:30 ET.
- Entry: close above the 5-minute opening-range high, above VWAP, with RVOL >= 1.5.
- Stop: lowest low of the five completed one-minute bars immediately before entry.
- Reject stop widths > 1.5%.
- Risk: 0.25% of buying power per trade by default.
- Profit taking: half at +1R, remainder at +2R, breakeven stop after +1R.
- Flat by 15:45 ET.
- Conservative same-bar assumption: stop is evaluated before target when both are touched.
- Configurable slippage.

## TTP-style evaluation model

The script supports MAX and FLEX assumptions:

- MAX: 6% target, 3% max loss, 1% daily pause, 20 positions, 30% best-position cap, 60 calendar days.
- FLEX: 6% target, 4% max loss, 2% daily pause, 10 positions, 50% best-position cap.

Before using this for a purchase decision, re-check the current TTP program terms because their parameters can change.

## Important data limitation

AlphaGEX began persistently storing the generalized Trade Volatility daily watchlist only recently. The script **does not invent older top-setups rankings** and does not backfill today's ranking onto old dates. It only tests dates that were genuinely stored.

That means early runs may correctly report that the sample is too small for meaningful Monte Carlo analysis.

## Run

From an environment that already has the AlphaGEX Render database and Polygon credentials:

```bash
python scripts/backtest_ttp_tv_stock_strategy.py --program max --account 25000
```

Optional:

```bash
python scripts/backtest_ttp_tv_stock_strategy.py \
  --program flex \
  --account 25000 \
  --risk-pct 0.25 \
  --min-rvol 1.5 \
  --trials 10000
```

Required environment variables:

- `DATABASE_URL`
- `POLYGON_API_KEY`

Outputs:

- `ttp_tv_stock_backtest_trades.csv`
- `ttp_tv_stock_backtest_summary.json`

## Decision threshold

Do not call the system proven from a handful of sessions. A practical minimum is 200–300 trades across multiple volatility regimes, followed by out-of-sample/paper validation.
