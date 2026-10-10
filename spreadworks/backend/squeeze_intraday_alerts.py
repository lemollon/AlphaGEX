"""Intraday SPY gamma context and two crossing alerts, kept together on
purpose so one never arrives without the other's context.

WARN_THRESHOLD_B (-$10.13B) is Leron's own original pick — an early heads-up
that gamma is drifting toward dangerous territory. VETO_THRESHOLD_B
(-$12.5B) is gamma_regime.py's own live DEEP_SHORT_B, the level the actual
NO_SELL veto fires at (tightened from -$10B 2026-10-04, see that module).
They are DIFFERENT NUMBERS FOR DIFFERENT REASONS — keep that straight rather
than merging them into one "the" threshold. Every alert shows both legs so a
reader never has to remember which number means what.
"""
from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import text

CT = ZoneInfo('America/Chicago')
WARN_THRESHOLD_B = -10.13   # Leron's own early-warning pick, unchanged
VETO_THRESHOLD_B = -12.5    # mirrors gamma_regime.DEEP_SHORT_B — the live NO_SELL trigger
TABLE = 'sw_squeeze_intraday_alert_state'


def _zone_label(below_warn: bool, below_veto: bool) -> str:
    if below_veto:
        return 'VETO ACTIVE — live NO_SELL trigger'
    if below_warn:
        return 'WARNING — approaching the veto zone'
    return 'clear of both thresholds'


def post_reading(engine, now: datetime, net_gex_b, spot, pct, send) -> bool:
    """Serialize replicas; retry failed delivery without marking it delivered.

    `now` is the completed live pull time. Caller must reject incomplete chains.
    A session's first below-threshold reading alerts even without a prior
    sample, for EITHER threshold independently.
    """
    now = now.astimezone(CT)
    if now.weekday() >= 5 or not (510 <= now.hour * 60 + now.minute <= 900):
        return False
    if net_gex_b is None or not math.isfinite(float(net_gex_b)):
        return False
    value = float(net_gex_b)
    below_warn = value < WARN_THRESHOLD_B
    below_veto = value < VETO_THRESHOLD_B
    with engine.begin() as conn:
        conn.execute(text(f'CREATE TABLE IF NOT EXISTS {TABLE} '
                          '(trade_date DATE PRIMARY KEY, below INTEGER NOT NULL, '
                          'below_veto INTEGER NOT NULL DEFAULT 0, '
                          'last_hour INTEGER, sampled_at TIMESTAMP)'))
        if engine.dialect.name != 'sqlite':
            conn.execute(text(
                f'ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS '
                'below_veto INTEGER NOT NULL DEFAULT 0'))
        conn.execute(text(f'INSERT INTO {TABLE} (trade_date, below, below_veto) '
                          'VALUES (:d, 0, 0) ON CONFLICT (trade_date) DO NOTHING'),
                     {'d': now.date()})
        lock = ' FOR UPDATE' if engine.dialect.name == 'postgresql' else ''
        old = conn.execute(text(
            f'SELECT below, below_veto, last_hour, sampled_at FROM {TABLE} '
            'WHERE trade_date=:d' + lock), {'d': now.date()}).first()
        crossing_warn = below_warn and not bool(old[0])
        crossing_veto = below_veto and not bool(old[1])
        hourly = old[2] != now.hour
        if crossing_warn or crossing_veto or hourly:
            dist_warn = abs(value - WARN_THRESHOLD_B)
            dist_veto = abs(value - VETO_THRESHOLD_B)
            if crossing_veto:
                title = 'SPY intraday gamma BELOW VETO −$12.5B — NO_SELL live'
                color = 0xFF5555
            elif crossing_warn:
                title = 'SPY intraday gamma BELOW WARNING −$10.13B'
                color = 0xFBBF24
            else:
                title = 'SPY intraday gamma — current reading'
                color = 0xFF5555 if below_veto else (0xFBBF24 if below_warn else 0x9CA3AF)
            body = (
                f'Net gamma: **${value:+.2f}B**\n'
                f'Warning (−${abs(WARN_THRESHOLD_B):.2f}B, your early-heads-up pick): '
                f'**${dist_warn:.2f}B {"below" if below_warn else "above"}**\n'
                f'Veto (−${abs(VETO_THRESHOLD_B):.2f}B, gamma_regime\'s live NO_SELL trigger): '
                f'**${dist_veto:.2f}B {"below" if below_veto else "above"}**\n'
                f'Zone: **{_zone_label(below_warn, below_veto)}**\n'
                f'Observed: **{now:%Y-%m-%d %I:%M:%S %p %Z}**'
            )
            if spot is not None:
                body += f'\nSPY spot: **${float(spot):.2f}**'
            if pct is not None:
                body += f'\nPercentile if this were the close: **{float(pct):.1%}**'
            embed = {'title': title, 'description': body, 'color': color,
                     'footer': {'text': 'Live Tradier chain · intraday context; daily signal uses 15:05 CT close'}}
            if not send(embed):
                return False
        conn.execute(text(
            f'UPDATE {TABLE} SET below=:b, below_veto=:bv, last_hour=:h, sampled_at=:t '
            'WHERE trade_date=:d'),
            {'b': int(below_warn), 'bv': int(below_veto), 'h': now.hour,
             't': now.replace(tzinfo=None), 'd': now.date()})
    return bool(crossing_warn or crossing_veto or hourly)
