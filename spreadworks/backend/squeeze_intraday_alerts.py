"""Intraday SPY gamma context and a user-selected -$10.13B crossing alert."""
from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import text

CT = ZoneInfo('America/Chicago')
THRESHOLD_B = -10.13
TABLE = 'sw_squeeze_intraday_alert_state'


def post_reading(engine, now: datetime, net_gex_b, spot, pct, send) -> bool:
    """Serialize replicas; retry failed delivery without marking it delivered.

    `now` is the completed live pull time. Caller must reject incomplete chains.
    A session's first below-threshold reading alerts even without a prior sample.
    """
    now = now.astimezone(CT)
    if now.weekday() >= 5 or not (510 <= now.hour * 60 + now.minute <= 900):
        return False
    if net_gex_b is None or not math.isfinite(float(net_gex_b)):
        return False
    value = float(net_gex_b)
    below = value < THRESHOLD_B
    with engine.begin() as conn:
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS {TABLE} '
                          '(trade_date DATE PRIMARY KEY, below INTEGER NOT NULL, '
                          'last_hour INTEGER, sampled_at TIMESTAMP)'))
        conn.execute(text(f'INSERT INTO {TABLE} (trade_date, below) VALUES (:d, 0) '
                          'ON CONFLICT (trade_date) DO NOTHING'), {'d': now.date()})
        lock = ' FOR UPDATE' if engine.dialect.name == 'postgresql' else ''
        old = conn.execute(text(f'SELECT below, last_hour, sampled_at FROM {TABLE} '
                                'WHERE trade_date=:d' + lock), {'d': now.date()}).first()
        crossing = below and not bool(old[0])
        hourly = old[1] != now.hour
        if crossing or hourly:
            distance = abs(value - THRESHOLD_B)
            title = ('SPY intraday gamma BELOW -$10.13B' if crossing
                     else 'SPY intraday gamma — current reading')
            body = (f'Net gamma: **${value:+.2f}B**\n'
                    f'Threshold: **-${abs(THRESHOLD_B):.2f}B** · '
                    f'**${distance:.2f}B {"below" if below else "above"}**\n'
                    f'Zone: **{"below your squeeze threshold" if below else "above your squeeze threshold"}**\n'
                    f'Observed: **{now:%Y-%m-%d %I:%M:%S %p %Z}**')
            if spot is not None:
                body += f'\nSPY spot: **${float(spot):.2f}**'
            if pct is not None:
                body += f'\nPercentile if this were the close: **{float(pct):.1%}**'
            embed = {'title': title, 'description': body,
                     'color': 0xFBBF24 if below else 0x9CA3AF,
                     'footer': {'text': 'Live Tradier chain · intraday context; daily signal uses 15:05 CT close'}}
            if not send(embed):
                return False
        conn.execute(text(f'UPDATE {TABLE} SET below=:b, last_hour=:h, sampled_at=:t '
                          'WHERE trade_date=:d'),
                     {'b': int(below), 'h': now.hour, 't': now.replace(tzinfo=None), 'd': now.date()})
    return bool(crossing or hourly)
