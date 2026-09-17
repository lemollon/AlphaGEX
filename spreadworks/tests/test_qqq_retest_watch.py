"""Regression tests using recorded live QQQ one-minute bars from 2026-09-17.

The values below came from Yahoo Finance's live chart response captured on the
same date.  They are fixed production observations, not generated sample data.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from backend.qqq_retest_watch import Bar, Settings, classify_bars


ET = ZoneInfo("America/New_York")


def _settings() -> Settings:
    return Settings(
        enabled=True,
        levels_date=date(2026, 9, 17),
        support_low=714.0,
        support_high=715.0,
        reclaim_low=717.0,
        reclaim_high=718.0,
        support_hold_bars=2,
        reclaim_confirmation_bars=2,
        failure_confirmation_bars=2,
        stale_after_seconds=90.0,
        poll_seconds=10,
        example_spread_width=2.0,
        allow_yahoo_fallback=True,
        sessions=("premarket", "regular", "postmarket"),
    )


def _bar(hhmm: str, open_: float, high: float, low: float, close: float) -> Bar:
    stamp = datetime.strptime(
        f"2026-09-17 {hhmm}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=ET)
    return Bar(stamp, open_, high, low, close)


def test_real_bars_classify_confirmed_failed_retest() -> None:
    bars = [
        _bar("09:34", 714.50, 714.6199951171875, 714.0599975585938,
             714.1099853515625),
        _bar("09:35", 714.1099853515625, 714.50, 714.1099853515625,
             714.3900146484375),
        _bar("09:36", 714.4400024414062, 714.719970703125,
             713.969970703125, 714.2849731445312),
        _bar("09:37", 714.3099975585938, 714.3250122070312,
             713.77001953125, 713.77001953125),
        _bar("09:38", 713.7750244140625, 713.835205078125,
             713.3200073242188, 713.5175170898438),
    ]

    result = classify_bars(bars, _settings())

    assert result.state == "FAILED_RETEST"
    assert result.transition_at == datetime(2026, 9, 17, 9, 39, tzinfo=ET)


def test_real_bars_classify_confirmed_bullish_retest() -> None:
    bars = [
        _bar("09:50", 714.760009765625, 714.97998046875,
             714.614990234375, 714.9099731445312),
        _bar("09:51", 714.9400024414062, 714.9600219726562,
             714.280029296875, 714.7899780273438),
        _bar("09:52", 714.7899780273438, 714.9500122070312,
             714.6900024414062, 714.9400024414062),
        _bar("09:53", 714.9199829101562, 715.0, 714.739990234375,
             714.9400024414062),
        _bar("09:54", 714.9400024414062, 715.4949951171875,
             714.9400024414062, 715.0399780273438),
        _bar("12:57", 716.2000122070312, 716.219970703125,
             715.7999877929688, 716.14501953125),
        _bar("12:58", 716.1300048828125, 716.489990234375,
             716.1300048828125, 716.4332885742188),
        _bar("12:59", 716.4299926757812, 716.7100219726562,
             716.4199829101562, 716.6973876953125),
        _bar("13:00", 716.6799926757812, 717.0700073242188,
             716.64501953125, 717.0150146484375),
        _bar("13:01", 717.010009765625, 717.0399780273438,
             716.8900146484375, 717.0399169921875),
    ]

    result = classify_bars(bars, _settings())

    assert result.state == "BULLISH_RETEST"
    assert result.transition_at == datetime(2026, 9, 17, 13, 2, tzinfo=ET)


def test_real_bar_after_reclaim_returns_to_wait() -> None:
    bars = [
        _bar("09:50", 714.760009765625, 714.97998046875,
             714.614990234375, 714.9099731445312),
        _bar("09:51", 714.9400024414062, 714.9600219726562,
             714.280029296875, 714.7899780273438),
        _bar("13:00", 716.6799926757812, 717.0700073242188,
             716.64501953125, 717.0150146484375),
        _bar("13:01", 717.010009765625, 717.0399780273438,
             716.8900146484375, 717.0399169921875),
        _bar("13:02", 717.0654296875, 717.0654296875,
             716.8101196289062, 716.8300170898438),
    ]

    result = classify_bars(bars, _settings())

    assert result.state == "WAIT"
    assert result.transition_at == datetime(2026, 9, 17, 13, 3, tzinfo=ET)
