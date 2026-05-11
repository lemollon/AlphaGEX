"""Pure HELIOS signal generator. No I/O.

Mirrors spec section "Entry signal" exactly. Caller fetches strikes/vix/prophet
from whatever data source (Tradier live, ORAT for backtest), then calls
generate_signal() with primitives.
"""
from __future__ import annotations

from typing import Optional, Sequence

from quant.gex_walls import GammaStrike, WallConfig, find_major_walls
from trading.helios.models import HeliosConfig, HeliosTradeSignal, SkipReason, SpreadType


def generate_signal(
    *,
    strikes: Sequence[GammaStrike],
    spot: float,
    vix: float,
    prophet_advice: Optional[dict],
    trades_today: int,
    has_open_position: bool,
    config: HeliosConfig,
) -> HeliosTradeSignal:
    if has_open_position:
        return HeliosTradeSignal.skip(SkipReason.ALREADY_OPEN, "position already open")
    if trades_today >= config.max_trades_per_day:
        return HeliosTradeSignal.skip(SkipReason.MAX_TRADES_TODAY, f"trades_today={trades_today}")

    if vix < config.min_vix or vix > config.max_vix:
        return HeliosTradeSignal.skip(SkipReason.VIX_OUT_OF_RANGE, f"vix={vix:.2f}")

    walls = find_major_walls(
        strikes=strikes,
        spot=spot,
        config=WallConfig(
            concentration_threshold=config.wall_concentration_threshold,
            top_n=config.wall_top_n,
            local_band_pct=0.05,
        ),
    )
    if walls.call_wall is None and walls.put_support is None:
        return HeliosTradeSignal.skip(SkipReason.NO_MAJOR_WALL, "no qualifying wall on either side")

    near_put = walls.put_support is not None and (
        abs(spot - walls.put_support.strike) / spot * 100.0 <= config.wall_filter_pct
    )
    near_call = walls.call_wall is not None and (
        abs(walls.call_wall.strike - spot) / spot * 100.0 <= config.wall_filter_pct
    )

    if not near_put and not near_call:
        return HeliosTradeSignal.skip(SkipReason.NOT_NEAR_WALL, "spot not within wall_filter_pct")

    if near_put and near_call:
        d_put = abs(spot - walls.put_support.strike)
        d_call = abs(walls.call_wall.strike - spot)
        spread_type = SpreadType.BULL_CALL if d_put <= d_call else SpreadType.BEAR_PUT
    elif near_put:
        spread_type = SpreadType.BULL_CALL
    else:
        spread_type = SpreadType.BEAR_PUT

    if prophet_advice and prophet_advice.get("action") == "SKIP_TODAY" and prophet_advice.get("confidence", 0.0) >= 0.80:
        return HeliosTradeSignal.skip(SkipReason.PROPHET_VETO, f"prophet skip {prophet_advice['confidence']:.2f}")

    long_strike = float(round(spot))
    if spread_type == SpreadType.BULL_CALL:
        short_strike = long_strike + config.spread_width
    else:
        short_strike = long_strike - config.spread_width

    return HeliosTradeSignal.trade(spread_type=spread_type, long_strike=long_strike, short_strike=short_strike)
