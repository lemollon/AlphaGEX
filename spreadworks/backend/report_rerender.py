"""Re-render the stored report archive from each report's own stored evidence.

Stored reports are immutable evidence. A re-render regenerates ONLY the derived
`report_markdown` (what `report.pdf` and `portable.zip` are built from) by running the
current renderer over that report's own stored `report_blocks`. It never calls a market
data source and never touches blocks, chart references, clocks, ids or completeness.

The original markdown is copied to `report_markdown_pre_rerender` (first rewrite only, so
repeated runs never overwrite the true original) before anything is replaced.
"""
from __future__ import annotations
import copy, hashlib, json
from datetime import datetime, timezone
from sqlalchemy import text, inspect

BACKUP_COLUMN = 'report_markdown_pre_rerender'
STAMP_COLUMN = 'report_rerendered_at'
RENDER_POLICY_FIELD = 'report_markdown_rendered_policy'

# Input only: a re-render must leave every one of these byte-identical.
PROTECTED_FIELDS = ('report_blocks', 'chart_urls', 'generated_at', 'report_id', 'kind',
                    'report_completeness', 'evidence')

# Text the 2026-10-16 renderer fixes removed because it read a 0DTE expiry artifact as a market signal.
STALE_PHRASES = ('inverted', 'event/fear', 'fear pattern', 'front-day premium is elevated')


def encoded(value):
    return json.dumps(value, default=lambda x: x.isoformat() if isinstance(x, datetime) else str(x), allow_nan=False)


def protected_hash(payload):
    """Stable digest of the immutable fields of one stored payload."""
    body = {field: payload.get(field) for field in PROTECTED_FIELDS}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def ensure_columns(engine):
    """Migration: add the backup and stamp columns. Safe to run repeatedly."""
    have = {c['name'] for c in inspect(engine).get_columns('sw_full_reports')}
    with engine.begin() as c:
        for column, kind in ((BACKUP_COLUMN, 'TEXT'), (STAMP_COLUMN, 'TIMESTAMP')):
            if column not in have:
                if engine.dialect.name == 'postgresql':
                    c.execute(text(f'ALTER TABLE sw_full_reports ADD COLUMN IF NOT EXISTS {column} {kind}'))
                else:
                    c.execute(text(f'ALTER TABLE sw_full_reports ADD COLUMN {column} {kind}'))


def _stale_hits(markdown):
    low = (markdown or '').lower()
    return [p for p in STALE_PHRASES if p in low]


def rerender_payload(raw):
    """Pure function: stored payload_json text -> (status, detail, new_payload_json_or_None).

    status is 'rewrite', 'skip' or 'error'. Never raises.
    """
    try:
        payload = json.loads(raw)
    except Exception as exc:
        return 'skip', 'payload_json is not valid JSON (' + type(exc).__name__ + ')', None
    if not isinstance(payload, dict):
        return 'skip', 'payload_json is not an object', None
    blocks = payload.get('report_blocks')
    if not isinstance(blocks, dict) or not blocks:
        return 'skip', 'no stored report_blocks to render from', None
    if not payload.get('report_completeness'):
        return 'skip', 'no stored report_completeness', None
    before = protected_hash(payload)
    try:
        from .report_contract import REQUIREMENTS
        from .report_policy import render_markdown
        work = copy.deepcopy(payload)
        # Reports published before a section existed carry no block for it. Show it as unavailable,
        # exactly as publication does (prepare_report_delivery), on this render copy only; the stored
        # blocks are never written back.
        filled = []
        for name, fields in REQUIREMENTS.items():
            block = work['report_blocks'].setdefault(name, {})
            if not isinstance(block, dict):
                block = work['report_blocks'][name] = {}
            for field in fields:
                if field not in block:
                    block[field] = {'status': 'unavailable', 'reason': 'Producer supplied no verified observation.'}
                    if name not in filled:
                        filled.append(name)
        snapshot = protected_hash(work)
        markdown = render_markdown(work)
        if not isinstance(markdown, str) or not markdown.strip():
            raise ValueError('renderer returned empty markdown')
        if protected_hash(work) != snapshot:
            raise ValueError('renderer mutated protected evidence')
    except Exception as exc:
        return 'error', type(exc).__name__ + ': ' + str(exc)[:300], None
    from .report_policy import policy_identity
    identity = policy_identity()
    if markdown == payload.get('report_markdown') and payload.get(RENDER_POLICY_FIELD) == identity:
        return 'skip', 'already current', None
    updated = dict(payload)
    updated['report_markdown'] = markdown
    # The row's own report_policy stays as published; this records which policy produced the markdown now.
    updated[RENDER_POLICY_FIELD] = identity
    if protected_hash(updated) != before:
        return 'error', 'protected fields changed while assembling the payload', None
    return 'rewrite', {'old_markdown': payload.get('report_markdown') or '', 'new_markdown': markdown, 'sections_shown_unavailable': filled}, encoded(updated)


def run(engine, apply=False, report_id=None, published_only=True):
    """Re-render the stored report archive. apply=False is a read-only dry run.

    `published_only` (the default) restricts the run to the kinds the archive actually
    publishes -- the same `kind IN ('morning','market_open','intraday')` filter
    `report_archive.load_archive` uses, so the rows re-rendered are exactly the rows a
    reader can open. The table also holds diagnostic/verification runs, which carry empty
    blocks by design and are never served; re-rendering those changes nothing a reader
    sees while inflating every count in this summary. Naming one `report_id` addresses
    that row whatever its kind.
    """
    if apply:
        ensure_columns(engine)
    have_backup = BACKUP_COLUMN in {c['name'] for c in inspect(engine).get_columns('sw_full_reports')}
    with engine.begin() as c:
        sql = 'SELECT report_id FROM sw_full_reports'
        params = {}
        if report_id:
            sql += ' WHERE report_id=:id';params = {'id': report_id}
        elif published_only:
            from .report_archive import PUBLISHED_KINDS
            sql += ' WHERE kind IN (' + ','.join(':k%d' % i for i in range(len(PUBLISHED_KINDS))) + ')'
            params = {'k%d' % i: k for i, k in enumerate(PUBLISHED_KINDS)}
        ids = [r[0] for r in c.execute(text(sql + ' ORDER BY generated_at'), params).fetchall()]
    summary = {'mode': 'apply' if apply else 'dry_run',
               'scope': 'one report' if report_id else ('published kinds only' if published_only else 'every row including diagnostics'),
               'rows_read': 0, 'rows_would_rewrite': 0, 'rows_rewritten': 0,
               'rows_skipped': 0, 'rows_errored': 0, 'skipped_reasons': {}, 'errors': {},
               'stale_phrase_rows_before': {p: 0 for p in STALE_PHRASES},
               'stale_phrase_rows_after': {p: 0 for p in STALE_PHRASES},
               'rows_with_contract_fields_absent_from_stored_blocks': 0, 'protected_field_hash_mismatches': 0, 'rows': []}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for rid in ids:
        summary['rows_read'] += 1
        try:
            with engine.begin() as c:
                row = c.execute(text('SELECT payload_json FROM sw_full_reports WHERE report_id=:id'), {'id': rid}).fetchone()
            if not row:
                summary['rows_skipped'] += 1
                summary['skipped_reasons']['row disappeared during run'] = summary['skipped_reasons'].get('row disappeared during run', 0) + 1
                continue
            raw = row[0]
            status, detail, new_raw = rerender_payload(raw)
            current_md = ''
            try:
                current_md = json.loads(raw).get('report_markdown') or ''
            except Exception:
                pass
            if status == 'skip':
                summary['rows_skipped'] += 1
                summary['skipped_reasons'][detail] = summary['skipped_reasons'].get(detail, 0) + 1
                for p in _stale_hits(current_md):
                    summary['stale_phrase_rows_before'][p] += 1;summary['stale_phrase_rows_after'][p] += 1
                continue
            if status == 'error':
                summary['rows_errored'] += 1
                summary['errors'][rid] = detail
                for p in _stale_hits(current_md):
                    summary['stale_phrase_rows_before'][p] += 1;summary['stale_phrase_rows_after'][p] += 1
                continue
            entry = {'report_id': rid, 'old_markdown_chars': len(detail['old_markdown']),
                     'new_markdown_chars': len(detail['new_markdown']),
                     'sections_shown_unavailable': detail['sections_shown_unavailable']}
            if apply:
                with engine.begin() as c:
                    # Optimistic guard: only replace the exact payload we rendered from.
                    result = c.execute(text(
                        f'UPDATE sw_full_reports SET payload_json=:new, {BACKUP_COLUMN}=COALESCE({BACKUP_COLUMN},:old), '
                        f'{STAMP_COLUMN}=:now WHERE report_id=:id AND payload_json=:raw'),
                        {'new': new_raw, 'old': detail['old_markdown'], 'now': now, 'id': rid, 'raw': raw})
                    if result.rowcount != 1:
                        raise RuntimeError('row changed during run; left untouched')
                    after = c.execute(text('SELECT payload_json FROM sw_full_reports WHERE report_id=:id'), {'id': rid}).fetchone()[0]
                if protected_hash(json.loads(after)) != protected_hash(json.loads(raw)):
                    summary['protected_field_hash_mismatches'] += 1
                summary['rows_rewritten'] += 1
            summary['rows_would_rewrite'] += 1
            if detail['sections_shown_unavailable']:
                summary['rows_with_contract_fields_absent_from_stored_blocks'] += 1
            for p in _stale_hits(detail['old_markdown']):
                summary['stale_phrase_rows_before'][p] += 1
            for p in _stale_hits(detail['new_markdown']):
                summary['stale_phrase_rows_after'][p] += 1
            summary['rows'].append(entry)
        except Exception as exc:
            summary['rows_errored'] += 1
            summary['errors'][rid] = type(exc).__name__ + ': ' + str(exc)[:300]
    summary['backup_column_present'] = have_backup or apply
    return summary
