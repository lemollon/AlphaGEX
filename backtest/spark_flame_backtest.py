#!/usr/bin/env python3
"""
SPARK (1DTE) & FLAME (2DTE) — SPY Iron Condor Backtester
=========================================================
Standalone backtest engine for SPY iron condors.
Data source: philippdubach SPY options parquet files.
VIX + SPY prices: yfinance.

Usage:
    # Single run (baseline config)
    python backtest/spark_flame_backtest.py --bot spark --start 2022-01-01 --end 2022-03-31

    # Full parameter sweep
    python backtest/spark_flame_backtest.py --bot both --sweep --export

    # Smoke test
    python backtest/spark_flame_backtest.py --bot spark --start 2022-01-01 --end 2022-03-31
"""

import argparse
import json
import os
import sys
from math import sqrt, floor
from datetime import datetime

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# BOT CONFIGS — exact live production parameters, do not change
# ---------------------------------------------------------------------------
BOT_CONFIGS = {
    "spark": {
        "dte": 1,
        "symbol": "SPY",
        "sd_multiplier": 1.2,
        "spread_width": 5,
        "min_credit": 0.05,
        "profit_target_pct": 30.0,
        "stop_loss_pct": 100.0,
        "vix_skip": 32.0,
        "buying_power_pct": 85.0,
        "max_contracts": 10,
        "account_size": 10000.0,
    },
    "flame": {
        "dte": 2,
        "symbol": "SPY",
        "sd_multiplier": 1.2,
        "spread_width": 5,
        "min_credit": 0.05,
        "profit_target_pct": 30.0,
        "stop_loss_pct": 100.0,
        "vix_skip": 32.0,
        "buying_power_pct": 85.0,
        "max_contracts": 10,
        "account_size": 10000.0,
    },
}

# ---------------------------------------------------------------------------
# COLUMN NORMALIZATION — auto-detect and map non-standard column names
# ---------------------------------------------------------------------------
COLUMN_ALIASES = {
    "date": ["date", "quote_date", "trade_date"],
    "expiration": ["expiration", "expiry", "expiration_date", "exp_date"],
    "strike": ["strike", "strike_price", "strikeprice"],
    "type": ["type", "option_type", "call_put", "cp_flag", "putcall"],
    "bid": ["bid", "bid_price"],
    "ask": ["ask", "ask_price"],
    "delta": ["delta", "greeks_delta"],
    "implied_volatility": ["implied_volatility", "iv", "impliedvol", "implied_vol"],
}

REQUIRED_COLUMNS = ["date", "expiration", "strike", "type", "bid", "ask"]


def _build_column_rename_map(actual_columns: list) -> dict:
    """Build a rename map from actual parquet columns to standard names."""
    actual_lower = {c.lower().strip(): c for c in actual_columns}
    rename_map = {}

    for standard_name, aliases in COLUMN_ALIASES.items():
        # Check if standard name already exists (exact match)
        if standard_name in actual_lower:
            if actual_lower[standard_name] != standard_name:
                rename_map[actual_lower[standard_name]] = standard_name
            continue
        # Try aliases
        for alias in aliases:
            if alias.lower() in actual_lower:
                rename_map[actual_lower[alias.lower()]] = standard_name
                break

    return rename_map


def _normalize_option_type(df: pd.DataFrame) -> tuple:
    """Normalize type column values to 'call'/'put'. Returns (df, dropped_count)."""
    type_map = {
        "c": "call", "call": "call", "C": "call", "CALL": "call",
        "p": "put", "put": "put", "P": "put", "PUT": "put",
    }
    original_len = len(df)
    df["type"] = df["type"].astype(str).str.strip().map(type_map)
    df = df.dropna(subset=["type"])
    dropped = original_len - len(df)
    return df, dropped


# ---------------------------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------------------------
_options_cache = {}


def load_options_data(parquet_path: str = "backtest/data/spy_options.parquet") -> pd.DataFrame:
    """
    Load and normalize philippdubach SPY options data.
    Auto-detects column names and normalizes them to standard names.
    """
    if parquet_path in _options_cache:
        return _options_cache[parquet_path]

    if not os.path.exists(parquet_path):
        # Try loading yearly files
        data_dir = os.path.dirname(parquet_path)
        yearly_files = sorted(
            f for f in os.listdir(data_dir)
            if f.startswith("spy_") and f.endswith(".parquet")
        ) if os.path.isdir(data_dir) else []

        if not yearly_files:
            print(f"ERROR: No parquet data found at {parquet_path} or as yearly files in {data_dir}")
            sys.exit(1)

        frames = []
        for yf in yearly_files:
            fp = os.path.join(data_dir, yf)
            size = os.path.getsize(fp)
            if size < 500:  # LFS pointer, not real data
                print(f"  SKIP {yf} ({size} bytes — LFS pointer, not real data)")
                continue
            frames.append(pd.read_parquet(fp))
            print(f"  Loaded {yf}")
        if not frames:
            print("ERROR: No valid parquet files found (all were LFS pointers)")
            sys.exit(1)
        df = pd.concat(frames, ignore_index=True)
    else:
        size = os.path.getsize(parquet_path)
        if size < 500:
            print(f"ERROR: {parquet_path} is only {size} bytes — likely an LFS pointer, not real data")
            sys.exit(1)
        df = pd.read_parquet(parquet_path)

    # Step 0C: Column name normalization
    rename_map = _build_column_rename_map(list(df.columns))
    if rename_map:
        df = df.rename(columns=rename_map)
    print(f"Column mapping OK: {rename_map if rename_map else '(no renames needed)'}")

    # Verify required columns
    actual_cols = set(df.columns)
    missing = [c for c in REQUIRED_COLUMNS if c not in actual_cols]
    if missing:
        print(f"COLUMN MAPPING FAILED — found: {list(df.columns)} — missing: {missing}")
        sys.exit(1)

    # Normalize type values
    df, dropped = _normalize_option_type(df)
    call_count = (df["type"] == "call").sum()
    put_count = (df["type"] == "put").sum()
    print(f"Type values normalized: {call_count:,} calls, {put_count:,} puts")
    if dropped > 0:
        print(f"Rows dropped (unknown type): {dropped}")

    # Normalize dates
    df["date"] = pd.to_datetime(df["date"])
    df["expiration"] = pd.to_datetime(df["expiration"])
    df["type"] = df["type"].str.lower().str.strip()
    df["dte_calc"] = (df["expiration"] - df["date"]).dt.days

    # Drop rows with null bid or ask or strike
    df = df.dropna(subset=["bid", "ask", "strike"])
    # Drop rows where bid > ask (bad data)
    df = df[df["ask"] >= df["bid"]]

    print(f"Options data loaded: {len(df):,} rows | "
          f"{df['date'].min().date()} → {df['date'].max().date()}")

    _options_cache[parquet_path] = df
    return df


def load_vix(start: str, end: str) -> pd.Series:
    """Download VIX via yfinance. Returns Series indexed by date."""
    import yfinance as yf
    vix = yf.Ticker("^VIX").history(start=start, end=end)
    vix.index = vix.index.tz_localize(None)
    return vix["Close"].rename("vix")


def load_spy_prices(start: str, end: str) -> pd.DataFrame:
    """Download SPY OHLC via yfinance."""
    import yfinance as yf
    spy = yf.Ticker("SPY").history(start=start, end=end)[["Open", "High", "Low", "Close"]]
    spy.index = spy.index.tz_localize(None)
    return spy


# ---------------------------------------------------------------------------
# CORE BACKTEST
# ---------------------------------------------------------------------------
def get_price(chain: pd.DataFrame, strike: float, opt_type: str, price_field: str):
    """Get option price from chain. Falls back to nearest strike within $1."""
    row = chain[(chain["strike"] == strike) & (chain["type"] == opt_type)]
    if row.empty:
        near = chain[chain["type"] == opt_type].copy()
        if near.empty:
            return None
        near["dist"] = abs(near["strike"] - strike)
        near = near.sort_values("dist")
        if near.iloc[0]["dist"] > 1.0:
            return None
        row = near.iloc[[0]]
    val = row.iloc[0][price_field]
    if pd.isna(val) or val <= 0:
        return None
    return float(val)


def run_backtest(
    bot: str,
    start: str,
    end: str,
    profit_target_pct: float = None,
    stop_loss_pct: float = None,
    parquet_path: str = "backtest/data/spy_options.parquet",
) -> dict:
    """
    Run a single backtest for bot (spark|flame) over the date range.
    profit_target_pct and stop_loss_pct override defaults when provided.
    """
    cfg = BOT_CONFIGS[bot].copy()
    if profit_target_pct is not None:
        cfg["profit_target_pct"] = profit_target_pct
    if stop_loss_pct is not None:
        cfg["stop_loss_pct"] = stop_loss_pct

    dte_target = cfg["dte"]
    options = load_options_data(parquet_path)
    options = options[(options["date"] >= start) & (options["date"] <= end)]
    vix = load_vix(start, end)
    spy = load_spy_prices(start, end)

    trading_days = sorted(options["date"].unique())

    account_balance = cfg["account_size"]
    trades = []
    skipped = {
        "VIX_TOO_HIGH": 0,
        "NO_EXPIRATION": 0,
        "MISSING_QUOTES": 0,
        "CREDIT_TOO_LOW": 0,
        "INSUFFICIENT_BP": 0,
        "ALREADY_TRADED": 0,
    }
    traded_dates = set()

    for trade_date in trading_days:
        date_str = pd.Timestamp(trade_date).strftime("%Y-%m-%d")

        if trade_date in traded_dates:
            skipped["ALREADY_TRADED"] += 1
            continue

        # VIX filter
        vix_val = vix.get(trade_date, None)
        if vix_val is None:
            try:
                vix_val = vix.asof(trade_date)
            except Exception:
                vix_val = None
        if vix_val is None or (hasattr(vix_val, "__float__") and np.isnan(float(vix_val))):
            skipped["VIX_TOO_HIGH"] += 1
            continue
        vix_val = float(vix_val)
        if vix_val >= cfg["vix_skip"]:
            skipped["VIX_TOO_HIGH"] += 1
            continue

        # SPY price
        try:
            spy_close = float(spy["Close"].asof(trade_date))
        except Exception:
            spy_close = None
        if spy_close is None or np.isnan(spy_close):
            skipped["MISSING_QUOTES"] += 1
            continue

        # Find target expiration
        day_chain = options[options["date"] == trade_date]
        exp_options = day_chain[day_chain["dte_calc"] == dte_target]

        if exp_options.empty:
            skipped["NO_EXPIRATION"] += 1
            continue

        exp_date = exp_options["expiration"].iloc[0]

        # Strike selection: 1.2 SD move from spot
        iv_approx = vix_val / 100.0
        sd = spy_close * cfg["sd_multiplier"] * iv_approx * sqrt(dte_target / 252.0)

        short_put_strike = round(spy_close - sd)
        short_call_strike = round(spy_close + sd)
        long_put_strike = short_put_strike - cfg["spread_width"]
        long_call_strike = short_call_strike + cfg["spread_width"]

        # Get bid/ask for all 4 legs
        sp_bid = get_price(exp_options, short_put_strike, "put", "bid")
        sc_bid = get_price(exp_options, short_call_strike, "call", "bid")
        lp_ask = get_price(exp_options, long_put_strike, "put", "ask")
        lc_ask = get_price(exp_options, long_call_strike, "call", "ask")

        if any(p is None for p in [sp_bid, sc_bid, lp_ask, lc_ask]):
            skipped["MISSING_QUOTES"] += 1
            continue

        net_credit = (sp_bid + sc_bid) - (lp_ask + lc_ask)
        if net_credit < cfg["min_credit"]:
            skipped["CREDIT_TOO_LOW"] += 1
            continue

        # Position sizing
        available_bp = account_balance * (cfg["buying_power_pct"] / 100.0)
        collateral_per_contract = (cfg["spread_width"] - net_credit) * 100.0
        if collateral_per_contract <= 0:
            skipped["CREDIT_TOO_LOW"] += 1
            continue
        contracts = min(floor(available_bp / collateral_per_contract), cfg["max_contracts"])
        if contracts < 1:
            skipped["INSUFFICIENT_BP"] += 1
            continue

        # Build position
        position = {
            "entry_date": date_str,
            "expiration_date": pd.Timestamp(exp_date).strftime("%Y-%m-%d"),
            "spy_at_entry": round(spy_close, 2),
            "vix_at_entry": round(vix_val, 2),
            "short_put": short_put_strike,
            "short_call": short_call_strike,
            "long_put": long_put_strike,
            "long_call": long_call_strike,
            "net_credit": round(net_credit, 4),
            "contracts": contracts,
            "collateral": round(collateral_per_contract * contracts, 2),
            "max_profit": round(net_credit * 100 * contracts, 2),
            "exit_date": None,
            "exit_reason": None,
            "realized_pnl": None,
        }

        # Simulate exit: check each subsequent day up to expiration
        pt_threshold = net_credit * (1 - cfg["profit_target_pct"] / 100.0)
        sl_threshold = net_credit * (1 + cfg["stop_loss_pct"] / 100.0)

        exit_found = False
        check_dates = sorted(
            options[
                (options["date"] > trade_date) & (options["date"] <= exp_date)
            ]["date"].unique()
        )

        for check_date in check_dates:
            check_chain = options[
                (options["date"] == check_date) & (options["expiration"] == exp_date)
            ]

            sp_ask_now = get_price(check_chain, short_put_strike, "put", "ask")
            sc_ask_now = get_price(check_chain, short_call_strike, "call", "ask")
            lp_bid_now = get_price(check_chain, long_put_strike, "put", "bid")
            lc_bid_now = get_price(check_chain, long_call_strike, "call", "bid")

            if any(p is None for p in [sp_ask_now, sc_ask_now, lp_bid_now, lc_bid_now]):
                continue

            current_cost = (sp_ask_now + sc_ask_now) - (lp_bid_now + lc_bid_now)

            # Profit target
            if current_cost <= pt_threshold:
                pnl = (net_credit - current_cost) * 100 * contracts
                position.update(
                    exit_date=pd.Timestamp(check_date).strftime("%Y-%m-%d"),
                    exit_reason="PROFIT_TARGET",
                    realized_pnl=round(pnl, 2),
                )
                exit_found = True
                break

            # Stop loss
            if current_cost >= sl_threshold:
                pnl = (net_credit - current_cost) * 100 * contracts
                position.update(
                    exit_date=pd.Timestamp(check_date).strftime("%Y-%m-%d"),
                    exit_reason="STOP_LOSS",
                    realized_pnl=round(pnl, 2),
                )
                exit_found = True
                break

        # Expiration settlement if no early exit
        if not exit_found:
            try:
                spy_exp_close = float(spy["Close"].asof(exp_date))
            except Exception:
                spy_exp_close = spy_close
            if np.isnan(spy_exp_close):
                spy_exp_close = spy_close

            short_put_intrinsic = max(0, short_put_strike - spy_exp_close)
            short_call_intrinsic = max(0, spy_exp_close - short_call_strike)
            long_put_intrinsic = max(0, long_put_strike - spy_exp_close)
            long_call_intrinsic = max(0, spy_exp_close - long_call_strike)

            settlement_cost = (
                (short_put_intrinsic + short_call_intrinsic)
                - (long_put_intrinsic + long_call_intrinsic)
            )
            pnl = (net_credit - settlement_cost) * 100 * contracts
            position.update(
                exit_date=pd.Timestamp(exp_date).strftime("%Y-%m-%d"),
                exit_reason="EXPIRATION",
                realized_pnl=round(pnl, 2),
            )

        account_balance += position["realized_pnl"]
        traded_dates.add(trade_date)
        trades.append(position)

    return build_results(bot, start, end, cfg, trades, skipped, cfg["account_size"], account_balance)


# ---------------------------------------------------------------------------
# RESULTS BUILDER
# ---------------------------------------------------------------------------
def build_results(
    bot: str,
    start: str,
    end: str,
    cfg: dict,
    trades: list,
    skipped: dict,
    starting_balance: float,
    final_balance: float,
) -> dict:
    """Compute all summary stats and return structured results dict."""
    if not trades:
        return {
            "bot": bot,
            "dte": cfg["dte"],
            "symbol": "SPY",
            "period": {"start": start, "end": end},
            "config": cfg,
            "summary": {
                "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                "win_rate": 0, "total_pnl": 0, "total_return_pct": 0,
                "avg_credit": 0, "avg_win": 0, "avg_loss": 0, "profit_factor": 0,
                "exit_reasons": {}, "days_skipped": skipped,
            },
            "risk": {
                "max_drawdown_pct": 0, "sharpe_ratio": 0, "sortino_ratio": 0,
                "worst_trade_pnl": 0, "best_trade_pnl": 0, "peak_margin_deployed": 0,
            },
            "equity_curve": [starting_balance],
            "trade_log": [],
        }

    wins = [t for t in trades if t["realized_pnl"] > 0]
    losses = [t for t in trades if t["realized_pnl"] <= 0]
    pnls = [t["realized_pnl"] for t in trades]

    # Equity curve
    equity = [starting_balance]
    for t in trades:
        equity.append(equity[-1] + t["realized_pnl"])
    equity = np.array(equity)

    # Max drawdown
    peak = np.maximum.accumulate(equity)
    drawdowns = (equity - peak) / peak * 100
    max_dd = abs(drawdowns.min())

    # Sharpe & Sortino (annualized)
    if len(pnls) > 1:
        daily_returns = np.diff(equity) / equity[:-1]
        std = daily_returns.std()
        sharpe = (daily_returns.mean() / std) * sqrt(252) if std > 0 else 0
        neg = daily_returns[daily_returns < 0]
        sortino = (
            (daily_returns.mean() / neg.std()) * sqrt(252)
            if len(neg) > 1 and neg.std() > 0
            else 0
        )
    else:
        sharpe = sortino = 0

    gross_profit = sum(t["realized_pnl"] for t in wins)
    gross_loss = abs(sum(t["realized_pnl"] for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    exit_reasons = {}
    for t in trades:
        exit_reasons[t["exit_reason"]] = exit_reasons.get(t["exit_reason"], 0) + 1

    return {
        "bot": bot,
        "dte": cfg["dte"],
        "symbol": "SPY",
        "period": {"start": start, "end": end},
        "config": cfg,
        "summary": {
            "total_trades": len(trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": round(len(wins) / len(trades) * 100, 2),
            "total_pnl": round(final_balance - starting_balance, 2),
            "total_return_pct": round(
                (final_balance - starting_balance) / starting_balance * 100, 2
            ),
            "avg_credit": round(np.mean([t["net_credit"] for t in trades]), 4),
            "avg_win": round(np.mean([t["realized_pnl"] for t in wins]), 2) if wins else 0,
            "avg_loss": round(np.mean([t["realized_pnl"] for t in losses]), 2) if losses else 0,
            "profit_factor": round(profit_factor, 3),
            "exit_reasons": exit_reasons,
            "days_skipped": skipped,
        },
        "risk": {
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "worst_trade_pnl": round(min(pnls), 2),
            "best_trade_pnl": round(max(pnls), 2),
            "peak_margin_deployed": round(max(t["collateral"] for t in trades), 2),
        },
        "equity_curve": [round(e, 2) for e in equity.tolist()],
        "trade_log": trades,
    }


# ---------------------------------------------------------------------------
# OUTPUT HELPERS
# ---------------------------------------------------------------------------
def print_summary(bot: str, result: dict):
    """Print formatted summary for a single backtest run."""
    s = result["summary"]
    r = result["risk"]
    cfg = result["config"]

    print(f"\n{'='*60}")
    print(f"{bot.upper()} ({cfg['dte']}DTE) — SPY Iron Condor Backtest")
    print(f"Period: {result['period']['start']} → {result['period']['end']}")
    print(f"Config: PT={cfg['profit_target_pct']}% / SL={cfg['stop_loss_pct']}%")
    print(f"{'='*60}")
    print(f"  Total Trades:      {s['total_trades']}")
    print(f"  Win Rate:          {s['win_rate']}%")
    print(f"  Total P&L:         ${s['total_pnl']:+,.2f}")
    print(f"  Total Return:      {s['total_return_pct']:+.1f}%")
    print(f"  Avg Credit:        ${s['avg_credit']:.4f}")
    print(f"  Avg Win:           ${s['avg_win']:+,.2f}")
    print(f"  Avg Loss:          ${s['avg_loss']:+,.2f}")
    print(f"  Profit Factor:     {s['profit_factor']:.3f}")
    print(f"  Max Drawdown:      {r['max_drawdown_pct']:.1f}%")
    print(f"  Sharpe Ratio:      {r['sharpe_ratio']:.3f}")
    print(f"  Sortino Ratio:     {r['sortino_ratio']:.3f}")
    print(f"  Best Trade:        ${r['best_trade_pnl']:+,.2f}")
    print(f"  Worst Trade:       ${r['worst_trade_pnl']:+,.2f}")
    print(f"  Peak Margin:       ${r['peak_margin_deployed']:,.2f}")
    print(f"  Exit Reasons:      {s['exit_reasons']}")
    print(f"  Days Skipped:      {s['days_skipped']}")
    print(f"{'='*60}")


def save_result(bot: str, result: dict, start: str, end: str):
    """Save result dict as JSON."""
    os.makedirs("backtest/results", exist_ok=True)
    out_path = f"backtest/results/{bot}_{start[:4]}_{end[:4]}.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"Results saved: {out_path}")


# ---------------------------------------------------------------------------
# PARAMETER SWEEP
# ---------------------------------------------------------------------------
PT_LEVELS = [20, 30, 50]
SL_LEVELS = [100, 150, 200]


def run_parameter_sweep(bot: str, start: str, end: str, export: bool,
                        parquet_path: str = "backtest/data/spy_options.parquet"):
    """Run full PT x SL parameter sweep (9 combinations)."""
    results = {}
    for pt in PT_LEVELS:
        for sl in SL_LEVELS:
            key = f"PT{pt}_SL{sl}"
            print(f"\n[{bot.upper()}] Running {key}...")
            r = run_backtest(
                bot, start, end,
                profit_target_pct=float(pt),
                stop_loss_pct=float(sl),
                parquet_path=parquet_path,
            )
            results[key] = r
            s = r["summary"]
            rk = r["risk"]
            print(
                f"  Trades:{s['total_trades']} WR:{s['win_rate']}% "
                f"Return:{s['total_return_pct']:+.1f}% "
                f"MaxDD:{rk['max_drawdown_pct']:.1f}% "
                f"Sharpe:{rk['sharpe_ratio']:.2f} PF:{s['profit_factor']:.2f}"
            )

    # Print sweep scorecard
    print(f"\n{'='*80}")
    print(f"{bot.upper()} PARAMETER SWEEP — {start[:4]}-{end[:4]}")
    print(
        f"{'PT':>6} {'SL':>6} {'Trades':>8} {'WR%':>7} {'Return%':>9} "
        f"{'MaxDD%':>8} {'Sharpe':>8} {'PF':>7}"
    )
    print("-" * 80)
    for pt in PT_LEVELS:
        for sl in SL_LEVELS:
            key = f"PT{pt}_SL{sl}"
            s = results[key]["summary"]
            rk = results[key]["risk"]
            print(
                f"{pt:>6} {sl:>6} {s['total_trades']:>8} "
                f"{s['win_rate']:>7.1f} {s['total_return_pct']:>+9.1f} "
                f"{rk['max_drawdown_pct']:>8.1f} "
                f"{rk['sharpe_ratio']:>8.2f} {s['profit_factor']:>7.2f}"
            )

    if export:
        os.makedirs("backtest/results", exist_ok=True)
        out_path = f"backtest/results/{bot}_sweep_{start[:4]}_{end[:4]}.json"
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nSweep results saved: {out_path}")

    return results


# ---------------------------------------------------------------------------
# CONSOLIDATED SCORECARD (both bots)
# ---------------------------------------------------------------------------
def print_consolidated_scorecard(spark_results: dict, flame_results: dict):
    """Print side-by-side comparison of SPARK vs FLAME."""
    baseline_key = "PT30_SL100"
    sr = spark_results.get(baseline_key, {})
    fr = flame_results.get(baseline_key, {})

    if not sr or not fr:
        print("WARNING: Baseline config (PT30/SL100) not found in sweep results")
        return

    ss, rs = sr["summary"], sr["risk"]
    fs, rf = fr["summary"], fr["risk"]

    print(f"\n{'='*71}")
    print(f"SPARK vs FLAME — SPY Iron Condor Backtest | {sr['period']['start'][:4]}"
          f"–{sr['period']['end'][:4]}")
    print(f"{'='*71}")
    print(f"BASELINE (30% PT / 100% SL — live config)\n")
    print(f"{'Metric':<22} {'SPARK (1DTE)':>18} {'FLAME (2DTE)':>18}")
    print("-" * 71)
    def fmt_dollar(val):
        return f"${val:+,.2f}"

    def fmt_pct(val):
        return f"{val:+.1f}%"

    def fmt_pct1(val):
        return f"{val:.1f}%"

    def fmt_credit(val):
        return f"${val:.4f}"

    print(f"{'Total Trades':<22} {ss['total_trades']:>18} {fs['total_trades']:>18}")
    print(f"{'Win Rate':<22} {ss['win_rate']:>17.1f}% {fs['win_rate']:>17.1f}%")
    print(f"{'Total P&L':<22} {fmt_dollar(ss['total_pnl']):>18} {fmt_dollar(fs['total_pnl']):>18}")
    print(f"{'Total Return':<22} {fmt_pct(ss['total_return_pct']):>18} {fmt_pct(fs['total_return_pct']):>18}")
    print(f"{'Max Drawdown':<22} {fmt_pct1(rs['max_drawdown_pct']):>18} {fmt_pct1(rf['max_drawdown_pct']):>18}")
    print(f"{'Sharpe Ratio':<22} {rs['sharpe_ratio']:>18.2f} {rf['sharpe_ratio']:>18.2f}")
    print(f"{'Sortino Ratio':<22} {rs['sortino_ratio']:>18.2f} {rf['sortino_ratio']:>18.2f}")
    print(f"{'Profit Factor':<22} {ss['profit_factor']:>18.2f} {fs['profit_factor']:>18.2f}")
    print(f"{'Avg Credit':<22} {fmt_credit(ss['avg_credit']):>18} {fmt_credit(fs['avg_credit']):>18}")
    print(f"{'Avg Win':<22} {fmt_dollar(ss['avg_win']):>18} {fmt_dollar(fs['avg_win']):>18}")
    print(f"{'Avg Loss':<22} {fmt_dollar(ss['avg_loss']):>18} {fmt_dollar(fs['avg_loss']):>18}")
    print(f"{'Worst Trade':<22} {fmt_dollar(rs['worst_trade_pnl']):>18} {fmt_dollar(rf['worst_trade_pnl']):>18}")

    vix_skipped_s = ss["days_skipped"].get("VIX_TOO_HIGH", 0)
    vix_skipped_f = fs["days_skipped"].get("VIX_TOO_HIGH", 0)
    data_skipped_s = (
        ss["days_skipped"].get("NO_EXPIRATION", 0)
        + ss["days_skipped"].get("MISSING_QUOTES", 0)
    )
    data_skipped_f = (
        fs["days_skipped"].get("NO_EXPIRATION", 0)
        + fs["days_skipped"].get("MISSING_QUOTES", 0)
    )
    print(f"{'Days Skipped (VIX)':<22} {vix_skipped_s:>18} {vix_skipped_f:>18}")
    print(f"{'Days Skipped (data)':<22} {data_skipped_s:>18} {data_skipped_f:>18}")

    # Best config from sweep (by Sharpe)
    print(f"\n{'='*71}")
    print("BEST CONFIG FROM SWEEP (by Sharpe):\n")
    for label, results_dict in [("SPARK", spark_results), ("FLAME", flame_results)]:
        best_key = max(
            results_dict,
            key=lambda k: results_dict[k]["risk"]["sharpe_ratio"],
        )
        best = results_dict[best_key]
        bs, br = best["summary"], best["risk"]
        pt = best["config"]["profit_target_pct"]
        sl = best["config"]["stop_loss_pct"]
        print(
            f"  {label} best:  PT={pt:.0f}% / SL={sl:.0f}%  ->  "
            f"Return: {bs['total_return_pct']:+.1f}%  "
            f"Sharpe: {br['sharpe_ratio']:.2f}  "
            f"MaxDD: {br['max_drawdown_pct']:.1f}%"
        )

    # Verdict
    spark_best_sharpe = max(r["risk"]["sharpe_ratio"] for r in spark_results.values())
    flame_best_sharpe = max(r["risk"]["sharpe_ratio"] for r in flame_results.values())
    winner = "SPARK (1DTE)" if spark_best_sharpe > flame_best_sharpe else "FLAME (2DTE)"
    print(f"\n  VERDICT: {winner} has the higher risk-adjusted return (Sharpe).")

    print(f"\n{'='*71}")
    print("KNOWN LIMITATIONS:")
    print("  1. EOD data only — SL checks at close, not intraday")
    print("  2. No PDT simulation — assumes one trade every eligible day")
    print("  3. Fill model — entry: sell at bid/buy at ask; no commission")
    print("  4. No GEX filter — live bots skip when GEX data is all zeros")
    print("  5. 2008-2012 liquidity — wider spreads, thinner books expected")
    print("  6. 1DTE availability — some dates have no 1DTE chain")
    print(f"{'='*71}")


# ---------------------------------------------------------------------------
# CLI ENTRY POINT
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="SPARK/FLAME SPY Iron Condor Backtester"
    )
    parser.add_argument(
        "--bot", required=True, choices=["spark", "flame", "both"],
        help="Which bot to backtest",
    )
    parser.add_argument("--start", default="2008-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2025-11-30", help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--sweep", action="store_true",
        help="Run full PT x SL parameter sweep (9 combos per bot)",
    )
    parser.add_argument("--export", action="store_true", help="Export results to JSON")
    parser.add_argument(
        "--parquet", default="backtest/data/spy_options.parquet",
        help="Path to SPY options parquet file",
    )
    args = parser.parse_args()

    bots = ["spark", "flame"] if args.bot == "both" else [args.bot]

    if args.sweep:
        all_sweep_results = {}
        for bot in bots:
            all_sweep_results[bot] = run_parameter_sweep(
                bot, args.start, args.end, args.export, args.parquet
            )
        if len(bots) == 2:
            print_consolidated_scorecard(
                all_sweep_results["spark"], all_sweep_results["flame"]
            )
    else:
        for bot in bots:
            result = run_backtest(bot, args.start, args.end, parquet_path=args.parquet)
            print_summary(bot, result)
            if args.export:
                save_result(bot, result, args.start, args.end)


if __name__ == "__main__":
    main()
