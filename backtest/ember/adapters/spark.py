from __future__ import annotations

from typing import Optional

from backtest.ember.adapters.base import AdapterConfig
from backtest.ember.data import delta_at
from backtest.ember.fills import FILL_ASK_CROSS, signed_cashflow
from backtest.ember.models import DayChain, Leg, Position


class SparkRepresentativeIC:
    """Builds one representative 1DTE SPY iron condor per day.

    Short strikes are chosen at the target |delta|; wings sit `wing_width`
    dollars further OTM. Entry credit is priced conservatively (ask-cross)."""

    def eligible(self, day: DayChain, cfg: AdapterConfig) -> bool:
        mc = day.minutes.get(cfg.entry_minute)
        if not mc:
            return False
        # need at least a few strikes each side and a spot
        return mc.spot is not None and len(mc.quotes) >= 8

    def _pick_short(self, day: DayChain, cfg: AdapterConfig, right: str) -> Optional[float]:
        mc = day.minutes[cfg.entry_minute]
        spot = mc.spot
        best_strike = None
        best_err = float("inf")
        for (strike, r) in mc.quotes:
            if r != right:
                continue
            # restrict to OTM side
            if right == "P" and strike >= spot:
                continue
            if right == "C" and strike <= spot:
                continue
            # wing strike must also be quoted
            long_strike = strike - cfg.wing_width if right == "P" else strike + cfg.wing_width
            if (long_strike, right) not in mc.quotes:
                continue
            d = delta_at(day, cfg.entry_minute, strike, right)
            if d is None:
                continue
            err = abs(abs(d) - cfg.short_delta)
            if err < best_err:
                best_err, best_strike = err, strike
        return best_strike

    def build_entry(self, day: DayChain, cfg: AdapterConfig) -> Optional[Position]:
        if not self.eligible(day, cfg):
            return None
        mc = day.minutes[cfg.entry_minute]
        short_put = self._pick_short(day, cfg, "P")
        short_call = self._pick_short(day, cfg, "C")
        if short_put is None or short_call is None:
            return None
        long_put = short_put - cfg.wing_width
        long_call = short_call + cfg.wing_width

        legs = [
            Leg(short_put, "P", -1),
            Leg(long_put, "P", 1),
            Leg(short_call, "C", -1),
            Leg(long_call, "C", 1),
        ]
        # all four legs must quote at entry
        for leg in legs:
            if (leg.strike, leg.right) not in mc.quotes:
                return None
        credit = signed_cashflow(legs, mc.quotes, action="open", fill=FILL_ASK_CROSS)
        if credit <= 0:
            return None
        return Position(legs=legs, entry_minute=cfg.entry_minute, entry_credit=credit)
