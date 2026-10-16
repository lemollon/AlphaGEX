"""Archive re-render: derived markdown is regenerated, stored evidence is never touched."""
import copy, hashlib, json
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from backend import full_options_report as report, report_rerender as rr

STALE = "the term structure is inverted — 0DTE is pricing hotter than the back of the curve, classic event/fear pattern"
GOOD_ID = 'a' * 24
BAD_ID = 'b' * 24
OLD_ID = 'c' * 24


def stored_payload(report_id, kind='morning', marker=''):
    return {
        'generated_at': '2026-10-16T12:36:23.061042+00:00', 'kind': kind, 'report_id': report_id,
        'report_completeness': 'INCOMPLETE', 'advisory_only': True,
        'chart_urls': {'surface': 'https://example.invalid/charts/' + 'f' * 32 + '.png'},
        'evidence': {'generated_at': '2026-10-16T12:36:23+00:00', 'note': marker},
        'report_blocks': {
            'risk_on_defensive': {'verdict': {'status': 'historical', 'value': 'Neutral', 'source': 'stored',
                                              'source_timestamp': '2026-10-15T20:00:00+00:00', 'age_seconds': 59000.0,
                                              'confidence': 'LOW'}},
            'surface': {'term_structure': {'status': 'historical', 'value': {'SPY': {'ratio': 1.01}},
                                           'source': 'stored', 'source_timestamp': '2026-10-15T20:00:00+00:00',
                                           'age_seconds': 59000.0, 'confidence': 'LOW'}},
        },
        'report_markdown': '# Old\n\nSPY: ' + STALE + '.\n',
    }


@pytest.fixture
def db(monkeypatch):
    eng = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    monkeypatch.setattr(report, 'engine', eng)
    report.ensure_tables()
    with eng.begin() as c:
        for rid in (GOOD_ID, BAD_ID):
            p = stored_payload(rid, marker='BAD' if rid == BAD_ID else '')
            c.execute(text('INSERT INTO sw_full_reports VALUES (:i,:g,:k,:p)'),
                      dict(i=rid, g='2026-10-16 12:36:23.061042', k='morning', p=rr.encoded(p)))
        # Legacy / unreadable rows the job must skip, not crash on.
        c.execute(text('INSERT INTO sw_full_reports VALUES (:i,:g,:k,:p)'),
                  dict(i=OLD_ID, g='2026-10-01 12:00:00', k='morning', p=json.dumps({'report_markdown': 'legacy'})))
        c.execute(text('INSERT INTO sw_full_reports VALUES (:i,:g,:k,:p)'),
                  dict(i='d' * 24, g='2026-10-02 12:00:00', k='morning', p='not json'))
    return eng


def rows(eng):
    with eng.begin() as c:
        return {r[0]: r[1:] for r in c.execute(text('SELECT report_id,generated_at,payload_json FROM sw_full_reports'))}


def protected(raw):
    p = json.loads(raw)
    return hashlib.sha256(json.dumps({k: p.get(k) for k in rr.PROTECTED_FIELDS}, sort_keys=True).encode()).hexdigest()


def test_apply_rewrites_markdown_and_backs_up_the_original(db):
    before = rows(db)
    summary = rr.run(db, apply=True)
    after = rows(db)
    assert summary['rows_read'] == 4 and summary['rows_rewritten'] == 2 and summary['rows_skipped'] == 2
    new_md = json.loads(after[GOOD_ID][1])['report_markdown']
    assert 'event/fear' not in new_md and 'inverted' not in new_md
    assert new_md != json.loads(before[GOOD_ID][1])['report_markdown']
    with db.begin() as c:
        backup = c.execute(text(f'SELECT {rr.BACKUP_COLUMN} FROM sw_full_reports WHERE report_id=:i'), {'i': GOOD_ID}).scalar_one()
    assert backup == '# Old\n\nSPY: ' + STALE + '.\n'


def test_blocks_clocks_and_every_other_field_are_preserved(db):
    before = rows(db)
    rr.run(db, apply=True)
    after = rows(db)
    for rid in (GOOD_ID, BAD_ID):
        assert after[rid][0] == before[rid][0]
        assert protected(after[rid][1]) == protected(before[rid][1])
        old, new = json.loads(before[rid][1]), json.loads(after[rid][1])
        assert list(new)[:len(old)] == list(old)
        added = {rr.RENDER_POLICY_FIELD}
        assert set(new) - set(old) == added
        assert {k: v for k, v in old.items() if k != 'report_markdown'} == {k: v for k, v in new.items() if k not in ('report_markdown', *added)}
        # The row's own published policy is untouched; the render record is separate and current.
        assert new.get('report_policy') == old.get('report_policy')
        from backend.report_policy import policy_identity
        assert new[rr.RENDER_POLICY_FIELD] == policy_identity()


def test_rerender_makes_no_market_data_call(db, monkeypatch):
    import socket
    def refuse(*a, **k):
        raise AssertionError('network access during re-render')
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    assert rr.run(db, apply=True)['rows_errored'] == 0


def test_idempotent_second_run_changes_nothing(db):
    rr.run(db, apply=True)
    first = rows(db)
    with db.begin() as c:
        stamp = c.execute(text(f'SELECT {rr.STAMP_COLUMN} FROM sw_full_reports WHERE report_id=:i'), {'i': GOOD_ID}).scalar_one()
    second_summary = rr.run(db, apply=True)
    assert rows(db) == first
    assert second_summary['rows_rewritten'] == 0
    assert second_summary['skipped_reasons'].get('already current') == 2
    with db.begin() as c:
        again = c.execute(text(f'SELECT {rr.STAMP_COLUMN},{rr.BACKUP_COLUMN} FROM sw_full_reports WHERE report_id=:i'), {'i': GOOD_ID}).one()
    assert again[0] == stamp and again[1] == '# Old\n\nSPY: ' + STALE + '.\n'


def test_failed_row_is_left_untouched_and_does_not_abort_the_run(db, monkeypatch):
    from backend import report_policy
    real = report_policy.render_markdown
    def flaky(payload):
        if payload['evidence']['note'] == 'BAD':
            raise RuntimeError('renderer blew up')
        return real(payload)
    monkeypatch.setattr(report_policy, 'render_markdown', flaky)
    before = rows(db)
    summary = rr.run(db, apply=True)
    after = rows(db)
    assert after[BAD_ID] == before[BAD_ID]
    assert summary['rows_errored'] == 1 and 'renderer blew up' in summary['errors'][BAD_ID]
    assert summary['rows_rewritten'] == 1
    assert json.loads(after[GOOD_ID][1])['report_markdown'] != json.loads(before[GOOD_ID][1])['report_markdown']
    with db.begin() as c:
        assert c.execute(text(f'SELECT {rr.BACKUP_COLUMN} FROM sw_full_reports WHERE report_id=:i'), {'i': BAD_ID}).scalar_one() is None


def test_unreadable_and_legacy_rows_are_skipped_with_a_reason(db):
    before = rows(db)
    summary = rr.run(db, apply=True)
    after = rows(db)
    assert after[OLD_ID] == before[OLD_ID] and after['d' * 24] == before['d' * 24]
    assert summary['skipped_reasons']['no stored report_blocks to render from'] == 1
    assert any('not valid JSON' in reason for reason in summary['skipped_reasons'])


def test_dry_run_writes_nothing_and_reports_what_would_change(db):
    before = rows(db)
    summary = rr.run(db, apply=False)
    assert rows(db) == before
    assert backup_column_absent(db)
    assert summary['mode'] == 'dry_run' and summary['rows_rewritten'] == 0 and summary['rows_would_rewrite'] == 2
    assert summary['stale_phrase_rows_before']['event/fear'] == 2 and summary['stale_phrase_rows_after']['event/fear'] == 0


def backup_column_absent(eng):
    from sqlalchemy import inspect
    return rr.BACKUP_COLUMN not in {c['name'] for c in inspect(eng).get_columns('sw_full_reports')}


def test_routes_dry_run_is_get_and_apply_is_post(db, monkeypatch):
    primary(monkeypatch)
    json_of = lambda r: json.loads(r.body)
    dry = json_of(report.rerender_archive_dry_run(report_id=None))
    assert dry['mode'] == 'dry_run' and dry['rows_would_rewrite'] == 2
    applied = json_of(report.rerender_archive_apply(report_id=None, x_rerender_token='s3cret'))
    assert applied['mode'] == 'apply' and applied['rows_rewritten'] == 2
    methods = {(r.path, tuple(sorted(r.methods))) for r in report.router.routes if r.path.endswith('/rerender-archive')}
    assert methods == {('/api/spreadworks/reports/rerender-archive', ('GET',)),
                       ('/api/spreadworks/reports/rerender-archive', ('POST',))}


def primary(monkeypatch, token='s3cret'):
    monkeypatch.setenv('REPORT_RERENDER_TOKEN', token)
    monkeypatch.setenv('REPORT_RERENDER_SERVICE_ID', 'srv-primary')
    monkeypatch.setenv('RENDER_SERVICE_ID', 'srv-primary')
    monkeypatch.delenv('IS_PULL_REQUEST', raising=False)


def test_single_report_scope(db):
    summary = rr.run(db, apply=True, report_id=GOOD_ID)
    assert summary['rows_read'] == 1 and summary['rows_rewritten'] == 1
    assert json.loads(rows(db)[BAD_ID][1])['report_markdown'].startswith('# Old')


@pytest.mark.parametrize('env,header', [('s3cret', None), ('s3cret', 'wrong'), ('s3cret', ''), ('', 'anything'), (None, None), (None, 'anything')])
def test_post_without_the_token_is_refused_and_writes_nothing(db, monkeypatch, env, header):
    from fastapi import HTTPException
    primary(monkeypatch)
    if env is None:
        monkeypatch.delenv('REPORT_RERENDER_TOKEN', raising=False)
    else:
        monkeypatch.setenv('REPORT_RERENDER_TOKEN', env)
    before = rows(db)
    with pytest.raises(HTTPException) as err:
        report.rerender_archive_apply(report_id=None, x_rerender_token=header)
    assert err.value.status_code == 403
    assert rows(db) == before
    assert backup_column_absent(db)


def test_get_dry_run_needs_no_token(db, monkeypatch):
    monkeypatch.delenv('REPORT_RERENDER_TOKEN', raising=False)
    assert json.loads(report.rerender_archive_dry_run(report_id=None).body)['mode'] == 'dry_run'


@pytest.mark.parametrize('case,setup,fragment', [
    ('preview with valid token', {'IS_PULL_REQUEST': 'true'}, 'pull-request preview'),
    ('preview flag 1', {'IS_PULL_REQUEST': '1'}, 'pull-request preview'),
    ('service id mismatch', {'RENDER_SERVICE_ID': 'srv-preview-123'}, 'does not match'),
    ('own service id unset', {'RENDER_SERVICE_ID': None}, 'does not match'),
    ('own service id blank', {'RENDER_SERVICE_ID': '  '}, 'does not match'),
    ('expected service id unset', {'REPORT_RERENDER_SERVICE_ID': None}, 'REPORT_RERENDER_SERVICE_ID is not set'),
    ('both unset', {'REPORT_RERENDER_SERVICE_ID': None, 'RENDER_SERVICE_ID': None}, 'REPORT_RERENDER_SERVICE_ID is not set'),
])
def test_post_refused_off_the_primary_service_even_with_a_valid_token(db, monkeypatch, case, setup, fragment):
    from fastapi import HTTPException
    primary(monkeypatch)
    for name, value in setup.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    before = rows(db)
    with pytest.raises(HTTPException) as err:
        report.rerender_archive_apply(report_id=None, x_rerender_token='s3cret')
    assert err.value.status_code == 403 and fragment in err.value.detail
    assert rows(db) == before
    assert backup_column_absent(db)
    from sqlalchemy import inspect
    assert rr.STAMP_COLUMN not in {c['name'] for c in inspect(db).get_columns('sw_full_reports')}


def test_post_accepted_only_when_primary_and_token_both_pass(db, monkeypatch):
    primary(monkeypatch)
    out = json.loads(report.rerender_archive_apply(report_id=None, x_rerender_token='s3cret').body)
    assert out['mode'] == 'apply' and out['rows_rewritten'] == 2
    monkeypatch.setenv('IS_PULL_REQUEST', 'false')  # Render sets false on non-preview; must not block
    assert json.loads(report.rerender_archive_apply(report_id=None, x_rerender_token='s3cret').body)['rows_rewritten'] == 0

