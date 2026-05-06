"""Engine tests use synthetic data injected via dependency injection.
No DB hits. Fast, deterministic."""
import datetime as dt
from dataclasses import dataclass

import pandas as pd
import pytest

from backtest.directional_1dte.engine import Trade, BacktestResult, run_with_loaders
from backtest.directional_1dte.config import SOLOMON


@dataclass
class StubLoaders:
    """Inject synthetic data into the engine via this stub."""
    trading_days: list
    chains: dict   # date -> DataFrame indexed (expiration, strike)
    vix: dict      # date -> float | None
    walls: dict    # date -> {call_wall, put_wall, spot} | None

    def load_trading_days(self, start, end, ticker="SPY"):
        return [d for d in self.trading_days if start <= d <= end]

    def load_chain(self, d, ticker="SPY"):
        return self.chains.get(d, pd.DataFrame())

    def load_vix(self, d):
        return self.vix.get(d)

    def load_gex_walls(self, d, ticker="SPY"):
        return self.walls.get(d)


def make_chain(expiration: dt.date, spot: float, strikes_with_prices):
    """strikes_with_prices: list of (strike, call_mid, put_mid). Bid/ask = mid +/- 0.05."""
    rows = []
    for s, c_mid, p_mid in strikes_with_prices:
        rows.append({
            "expiration_date": expiration, "strike": s,
            "call_bid": c_mid - 0.05, "call_ask": c_mid + 0.05, "call_mid": c_mid,
            "put_bid": p_mid - 0.05, "put_ask": p_mid + 0.05, "put_mid": p_mid,
            "underlying_price": spot, "dte": (expiration - dt.date.today()).days,
        })
    return pd.DataFrame(rows).set_index(["expiration_date", "strike"])


class TestSingleTradeDay:
    def test_bullish_signal_produces_trade_and_settles_above_short(self, solomon):
        d0 = dt.date(2024, 3, 11)  # Monday
        d1 = dt.date(2024, 3, 12)
        # Day 0: spot 500, put_wall 499 (within 1%), VIX 18 -> BULLISH bull-call
        # Strikes 500/502, debit 0.80
        loaders = StubLoaders(
            trading_days=[d0, d1],
            chains={
                d0: make_chain(d1, 500.0, [(498, 3.0, 0.5), (500, 1.5, 1.5),
                                            (502, 0.7, 2.7), (504, 0.3, 4.5)]),
                # Day 1 chain only needs underlying_price for settlement
                d1: pd.DataFrame([{"expiration_date": d1, "strike": 500.0,
                                   "call_bid": 0, "call_ask": 0, "call_mid": 0,
                                   "put_bid": 0, "put_ask": 0, "put_mid": 0,
                                   "underlying_price": 503.0, "dte": 0}]
                                 ).set_index(["expiration_date", "strike"]),
            },
            vix={d0: 18.0, d1: 18.5},
            walls={d0: {"call_wall": 540, "put_wall": 499, "spot": 500},
                   d1: {"call_wall": 540, "put_wall": 502, "spot": 503}},
        )
        result = run_with_loaders(solomon, dt.date(2024, 3, 11), dt.date(2024, 3, 12), loaders)
        assert len(result.trades) == 1
        t = result.trades[0]
        assert t.direction == "BULLISH"
        assert t.long_strike == 500.0
        assert t.short_strike == 502.0
        assert t.entry_debit == pytest.approx(0.80)  # 1.5 - 0.7
        # contracts = floor(1000 / 80) = 12
        assert t.contracts == 12
        # spot 503 settled, payoff = min(503, 502) - 500 = 2.0; pnl = (2.0 - 0.80) * 12 * 100 = 1440
        assert t.realized_pnl == pytest.approx(1440.0)


class TestSkipDays:
    def test_skip_recorded_when_vix_out_of_range(self, solomon):
        d0 = dt.date(2024, 3, 11); d1 = dt.date(2024, 3, 12)
        loaders = StubLoaders(
            trading_days=[d0, d1],
            chains={d0: make_chain(d1, 500.0, [(500, 1.5, 1.5)]),
                    d1: make_chain(d1, 500.0, [(500, 1.5, 1.5)])},
            vix={d0: 50.0, d1: 50.0},  # above max
            walls={d0: {"call_wall": 540, "put_wall": 499, "spot": 500}},
        )
        result = run_with_loaders(solomon, d0, d1, loaders)
        assert len(result.trades) == 0
        assert len(result.skips) == 1
        assert result.skips[0].reason == "VIX_OUT_OF_RANGE"

    def test_long_weekend_gap_recorded(self, solomon):
        # 5-day gap between trading days; only expiration in chain is d1 (5 days out)
        d0 = dt.date(2024, 3, 11); d1 = dt.date(2024, 3, 18)
        loaders = StubLoaders(
            trading_days=[d0, d1],
            chains={d0: make_chain(d1, 500.0, [(500, 1.5, 1.5), (502, 0.7, 2.7)])},
            vix={d0: 18.0},
            walls={d0: {"call_wall": 540, "put_wall": 499, "spot": 500}},
        )
        result = run_with_loaders(solomon, d0, d1, loaders)
        assert len(result.trades) == 0
        assert any(s.reason == "NO_NEAR_EXPIRATION" for s in result.skips)


class TestNoSilentDrops:
    def test_every_processed_day_produces_trade_or_skip(self, solomon):
        days = [dt.date(2024, 3, 11), dt.date(2024, 3, 12), dt.date(2024, 3, 13)]
        loaders = StubLoaders(
            trading_days=days,
            chains={d: make_chain(d, 500.0, [(500, 1.5, 1.5)]) for d in days},
            vix={d: 50.0 for d in days},  # all skipped on VIX
            walls={d: {"call_wall": 540, "put_wall": 499, "spot": 500} for d in days},
        )
        result = run_with_loaders(solomon, days[0], days[-1], loaders)
        # Last day has no T+1 so it's not processed; first two should produce skips
        assert len(result.trades) + len(result.skips) == len(days) - 1


class TestEquityCurve:
    def test_equity_starts_at_starting_capital(self, solomon):
        loaders = StubLoaders(trading_days=[], chains={}, vix={}, walls={})
        result = run_with_loaders(solomon, dt.date(2024, 1, 1), dt.date(2024, 1, 1), loaders)
        assert result.starting_capital == solomon.starting_capital
