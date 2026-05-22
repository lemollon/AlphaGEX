import datetime as dt
from backtest.ember.models import Quote, Leg, Position, MinuteChain, DayChain


def test_quote_mid_uses_bid_ask():
    assert Quote(bid=1.0, ask=1.4, close=1.1).mid == 1.2


def test_quote_mid_falls_back_to_close_on_bad_spread():
    # crossed/zero quote -> use close
    assert Quote(bid=0.0, ask=0.0, close=0.9).mid == 0.9
    assert Quote(bid=2.0, ask=1.0, close=1.3).mid == 1.3


def test_position_holds_legs():
    legs = [Leg(95.0, "P", -1), Leg(90.0, "P", 1), Leg(105.0, "C", -1), Leg(110.0, "C", 1)]
    pos = Position(legs=legs, entry_minute=30, entry_credit=1.20)
    assert pos.contracts == 1
    assert len(pos.legs) == 4


def test_daychain_lookup():
    q = Quote(0.5, 0.7, 0.6)
    mc = MinuteChain(minute=0, spot=100.0, quotes={(95.0, "P"): q})
    day = DayChain(trade_date=dt.date(2024, 6, 3), expiration=dt.date(2024, 6, 4), minutes={0: mc})
    assert day.spot(0) == 100.0
    assert day.quote(0, 95.0, "P") is q
    assert day.quote(0, 999.0, "C") is None
    assert day.spot(7) is None
    assert day.sorted_minutes == [0]
