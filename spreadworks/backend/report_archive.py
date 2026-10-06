"""Read-only report catalog. Stored reports/charts remain the durable source."""
from __future__ import annotations
import json
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import text

PUBLISHED_KINDS = ('morning', 'market_open', 'intraday')
BASE = 'https://spreadworks-backend.onrender.com/api/spreadworks/reports'
CT = ZoneInfo('America/Chicago')

def archive_item(report_id, generated_at, kind, raw):
    stamp = generated_at if isinstance(generated_at, datetime) else datetime.fromisoformat(str(generated_at))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    clock = stamp.astimezone(CT)
    item = {'report_id': report_id, 'kind': kind, 'generated_at': stamp.isoformat(),
            'trading_date': clock.date().isoformat(), 'time_ct': clock.strftime('%H:%M'),
            'report_url': f'{BASE}/{report_id}/view', 'data_url': f'{BASE}/{report_id}/data',
            'assets_url': f'{BASE}/{report_id}/assets', 'pdf_url': f'{BASE}/{report_id}/charts.pdf',
            'offline_url': f'{BASE}/{report_id}/portable.zip'}
    try:
        payload = json.loads(raw)
        blocks = payload.get('report_blocks') or {}
        item.update(completeness=payload.get('report_completeness', 'UNKNOWN'),
            policy_version=(payload.get('report_policy') or {}).get('version'),
            thesis=blocks.get('risk_on_defensive', {}).get('verdict', {}),
            setup_status=blocks.get('day_strategy', {}).get('status', {}),
            chart_count=len(payload.get('chart_urls') or {}), readable=True)
    except (TypeError, ValueError, AttributeError):
        item.update(readable=False, completeness='UNKNOWN', reason='Stored payload cannot be decoded')
    return item

def load_archive(engine, limit=24, offset=0, kind=None, trading_date=None):
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise HTTPException(422, 'Invalid archive pagination')
    if kind is not None and kind not in PUBLISHED_KINDS:
        raise HTTPException(422, 'Invalid published report kind')
    filters = ["kind IN ('morning','market_open','intraday')"]
    params = {'limit': limit, 'offset': offset}
    if kind:
        filters.append('kind=:kind'); params['kind'] = kind
    if trading_date:
        try:
            day = datetime.strptime(trading_date, '%Y-%m-%d').date()
        except ValueError:
            raise HTTPException(422, 'Invalid trading date') from None
        start = datetime.combine(day, time(0), CT)
        end = start + timedelta(days=1)
        params.update(start=start.astimezone(timezone.utc).replace(tzinfo=None),
                      end=end.astimezone(timezone.utc).replace(tzinfo=None))
        filters.extend(['generated_at>=:start', 'generated_at<:end'])
    where = ' AND '.join(filters)
    with engine.connect() as conn:
        total = conn.execute(text('SELECT count(*) FROM sw_full_reports WHERE '+where), params).scalar_one()
        rows = conn.execute(text('SELECT report_id,generated_at,kind,payload_json FROM sw_full_reports WHERE '+where+
                                 ' ORDER BY generated_at DESC, report_id DESC LIMIT :limit OFFSET :offset'), params).all()
    return {'reports': [archive_item(*row) for row in rows], 'total': total,
            'limit': limit, 'offset': offset,
            'next_offset': offset+len(rows) if offset+len(rows)<total else None,
            'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'storage': 'Persistent Postgres report snapshots and stored PNG bytes',
            'notice': 'Reading the archive never refreshes original observations or executes a trade.'}
