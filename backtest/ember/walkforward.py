# backtest/ember/walkforward.py
from __future__ import annotations

import datetime as dt
from typing import List, Tuple

DEFAULT_TRAIN_END = dt.date(2024, 12, 31)


def split(
    trade_dates: List[dt.date],
    train_end: dt.date = DEFAULT_TRAIN_END,
) -> Tuple[List[dt.date], List[dt.date]]:
    """Partition dates into in-sample (<= train_end) and out-of-sample (> train_end)."""
    train = sorted(d for d in trade_dates if d <= train_end)
    oos = sorted(d for d in trade_dates if d > train_end)
    return train, oos
