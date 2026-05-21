import datetime as dt
from backtest.ember.walkforward import split


def test_split_default_2024_train_2025_oos():
    dates = [dt.date(2023, 1, 3), dt.date(2024, 12, 31), dt.date(2025, 1, 2), dt.date(2025, 6, 1)]
    train, oos = split(dates)
    assert train == [dt.date(2023, 1, 3), dt.date(2024, 12, 31)]
    assert oos == [dt.date(2025, 1, 2), dt.date(2025, 6, 1)]


def test_split_custom_boundary():
    dates = [dt.date(2024, 1, 1), dt.date(2024, 7, 1)]
    train, oos = split(dates, train_end=dt.date(2024, 3, 31))
    assert train == [dt.date(2024, 1, 1)]
    assert oos == [dt.date(2024, 7, 1)]
