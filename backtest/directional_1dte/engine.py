"""Daily loop driver. Pure orchestration over signals/pricing/payoff/data."""
import datetime as dt
import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from backtest.directional_1dte import data as default_data
from backtest.directional_1dte.config import BotConfig
from backtest.directional_1dte.signals import generate_signal
from backtest.directional_1dte.pricing import select_strikes, lookup_debit
from backtest.directional_1dte.payoff import compute_payoff


logger = logging.getLogger(__name__)


@dataclass
class Trade:
    bot: str
    entry_date: dt.date
    expiration_date: dt.date
    direction: str
    spread_type: str
    spot_at_entry: float
    long_strike: float
    short_strike: float
    entry_debit: float
    contracts: int
    spot_at_expiry: float
    payoff_per_share: float
    realized_pnl: float
    vix_at_entry: float
    call_wall: float
    put_wall: float
    long_bid: Optional[float]
    long_ask: Optional[float]
    short_bid: Optional[float]
    short_ask: Optional[float]
    expiry_not_t_plus_1: bool


@dataclass
class Skip:
    bot: str
    entry_date: dt.date
    reason: str
    detail: str = ""


@dataclass
class EquityPoint:
    date: dt.date
    equity: float


@dataclass
class BacktestResult:
    bot: str
    config: BotConfig
    start: dt.date
    end: dt.date
    starting_capital: float
    trades: list = field(default_factory=list)
    skips: list = field(default_factory=list)
    equity: list = field(default_factory=list)


def _pick_expiration(chain, trade_date: dt.date) -> Optional[dt.date]:
    """Return the soonest expiration > trade_date in the chain, or None.
    Skips if gap > 4 calendar days (handles pre-2022 SPY MWF cycle)."""
    if chain.empty:
        return None
    expirations = sorted({d for d, _ in chain.index if d > trade_date})
    if not expirations:
        return None
    chosen = expirations[0]
    if (chosen - trade_date).days > 4:
        return None
    return chosen


def run_with_loaders(config: BotConfig, start: dt.date, end: dt.date, loaders) -> BacktestResult:
    """Engine with injectable loaders (for testing). Mirrors run() exactly."""
    result = BacktestResult(
        bot=config.name,
        config=config,
        start=start,
        end=end,
        starting_capital=config.starting_capital,
    )
    equity = config.starting_capital
    trading_days = loaders.load_trading_days(start, end, ticker=config.ticker)
    if not trading_days:
        return result

    for i, t_day in enumerate(trading_days[:-1]):
        # Load entry-day data
        chain_t = loaders.load_chain(t_day, ticker=config.ticker)
        vix_t = loaders.load_vix(t_day)
        walls_t = loaders.load_gex_walls(t_day, ticker=config.ticker)
        spot_t = walls_t["spot"] if walls_t else None

        if spot_t is None or chain_t.empty:
            result.skips.append(Skip(config.name, t_day, "NO_DATA",
                                     "missing chain or walls"))
            continue

        # Generate signal
        signal, reason = generate_signal(walls_t, spot_t, vix_t, config)
        if signal is None:
            result.skips.append(Skip(config.name, t_day, reason or "UNKNOWN_SKIP"))
            continue

        # Pick expiration
        expiration = _pick_expiration(chain_t, t_day)
        if expiration is None:
            result.skips.append(Skip(config.name, t_day, "NO_NEAR_EXPIRATION",
                                     f"no expiration within 4 days of {t_day}"))
            continue
        expiry_not_t_plus_1 = (expiration != trading_days[i + 1])

        # Select strikes & look up debit
        long_k, short_k = select_strikes(spot_t, signal.direction, config.spread_width)
        priced = lookup_debit(chain_t, expiration, long_k, short_k, signal.spread_type)
        if priced is None:
            result.skips.append(Skip(config.name, t_day, "STRIKES_MISSING_FROM_CHAIN",
                                     f"{long_k}/{short_k} on {expiration}"))
            continue
        debit = priced["debit"]
        if debit <= 0 or debit >= config.spread_width:
            result.skips.append(Skip(config.name, t_day, "DEBIT_INVALID",
                                     f"debit={debit:.3f} width={config.spread_width}"))
            continue
        contracts = int(math.floor(config.risk_per_trade / (debit * 100)))
        if contracts < 1:
            result.skips.append(Skip(config.name, t_day, "SIZE_BELOW_1_CONTRACT",
                                     f"debit={debit:.3f}"))
            continue

        # Settle on the expiration day's chain
        chain_exp = loaders.load_chain(expiration, ticker=config.ticker)
        if chain_exp.empty:
            result.skips.append(Skip(config.name, t_day, "NO_T+1_DATA",
                                     f"no chain for {expiration}"))
            continue
        underlying_series = chain_exp["underlying_price"].dropna()
        if underlying_series.empty:
            result.skips.append(Skip(config.name, t_day, "NO_T+1_DATA",
                                     "no underlying price on expiry"))
            continue
        spot_expiry = float(underlying_series.median())
        if spot_expiry > 0 and abs(underlying_series.max() - underlying_series.min()) / spot_expiry > 0.005:
            logger.warning("Underlying spread > 0.5%% on %s: min=%.2f max=%.2f",
                           expiration, underlying_series.min(), underlying_series.max())

        payoff = compute_payoff(signal.spread_type, long_k, short_k, spot_expiry)
        pnl = (payoff - debit) * 100 * contracts
        equity += pnl

        result.trades.append(Trade(
            bot=config.name,
            entry_date=t_day,
            expiration_date=expiration,
            direction=signal.direction,
            spread_type=signal.spread_type,
            spot_at_entry=spot_t,
            long_strike=long_k,
            short_strike=short_k,
            entry_debit=debit,
            contracts=contracts,
            spot_at_expiry=spot_expiry,
            payoff_per_share=payoff,
            realized_pnl=pnl,
            vix_at_entry=vix_t,
            call_wall=walls_t["call_wall"],
            put_wall=walls_t["put_wall"],
            long_bid=priced.get("long_bid"),
            long_ask=priced.get("long_ask"),
            short_bid=priced.get("short_bid"),
            short_ask=priced.get("short_ask"),
            expiry_not_t_plus_1=expiry_not_t_plus_1,
        ))
        result.equity.append(EquityPoint(t_day, equity))

    return result


def run(config: BotConfig, start: dt.date, end: dt.date) -> BacktestResult:
    """Production entry: uses default data loaders against ORAT."""
    return run_with_loaders(config, start, end, default_data)
