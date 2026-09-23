"""Cache-only MES paired GEX filter study; never sends orders or downloads data.

Frozen v4 entries/exits are held fixed. Filtered-out trades are NOT replaced.
End-of-day proxies are lagged by one and two observed source sessions. Neither
series is a verified as-published dealer inventory or minute-by-minute GEX tape.
Repeated 2023/24 development only; this module never reads 2025 outcomes.
"""
from __future__ import annotations
from bisect import bisect_left
from collections import Counter
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import gzip
import hashlib
import json
import logging
import math
import os

STUDY = 'valor-mes-gex-overlay-v5-20260923'
BASE_STUDY = 'valor-mes-rebuild-v4-20260923'
BASE_HASH = 'a89b8b6eb6b0cf51896672f9238c09e2e8030bbc72ea0f366bd50d8b2dc7ea3c'
LOCK = 63260923
YEARS = (2023, 2024)
SPECS = ('opening_acceptance_retest', 'prior_extreme_reclaim', 'gap_fill_after_opening_failure')
SERIES = ('SPX_ORATS_7DTE_PROXY', 'SPY_BASELINE_PROXY')
FILTERS = ('all_matched', 'positive_only', 'negative_only')
CHICAGO = ZoneInfo('America/Chicago')


def aware(value):
    t = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise ValueError('Naive trade timestamp is not allowed')
    return t


def clean_source(rows):
    """Validate sorted, unique source dates. No silently dropped invalid data."""
    out = []
    for source_date, net in rows:
        d = source_date if isinstance(source_date, date) else date.fromisoformat(str(source_date))
        v = float(net)
        if not math.isfinite(v):
            raise ValueError('Nonfinite GEX')
        out.append((d, v))
    out.sort()
    if len({d for d, _ in out}) != len(out):
        raise ValueError('Duplicate GEX source dates')
    return out


def attach(trades, source, lag):
    """Use only source dates STRICTLY before decision date; no backfilling."""
    if lag not in (1, 2):
        raise ValueError('Only preregistered lags 1 and 2 are allowed')
    dates = [d for d, _ in source]
    out = []
    for trade in trades:
        t = dict(trade)
        decision = aware(t['signal_time'])
        if aware(t['entry']) < decision:
            raise ValueError('Fill precedes decision')
        day = decision.astimezone(CHICAGO).date()
        if day.year not in YEARS:
            raise ValueError('Research cannot access non-development trade years')
        i = bisect_left(dates, day) - lag
        g = None
        reason = 'no_prior_source_session'
        if i >= 0:
            d, v = source[i]
            age = (day - d).days
            if age <= (4 if lag == 1 else 7):
                g = dict(source_date=d.isoformat(), net_gex=v, age_calendar_days=age,
                         sign=1 if v > 0 else (-1 if v < 0 else 0))
                reason = None
            else:
                reason = 'stale_source_date'
        t['gex'] = g
        t['gex_missing_reason'] = reason
        out.append(t)
    return out


def retained(t, name):
    g = t.get('gex')
    if g is None:
        return False
    if name == 'all_matched':
        return True
    if name == 'positive_only':
        return g['sign'] == 1
    if name == 'negative_only':
        return g['sign'] == -1
    raise ValueError('Unknown frozen filter')


def stats(trades, censored):
    ordered = sorted(trades, key=lambda t: (aware(t['exit']), aware(t['entry'])))
    p = [float(t['net']) for t in ordered]
    if any(not math.isfinite(x) for x in p):
        raise ValueError('Nonfinite trade PnL')
    wins, losses = sum(x for x in p if x > 0), -sum(x for x in p if x < 0)
    eq = peak = dd = 0.
    months = {f'{y}-{m:02d}': 0. for y in YEARS for m in range(1, 13)}
    for t, value in zip(ordered, p):
        eq += value
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
        key = aware(t['exit']).astimezone(CHICAGO).strftime('%Y-%m')
        months[key] = months.get(key, 0.) + value
    trade_years = {aware(t['entry']).astimezone(CHICAGO).year for t in trades + censored}
    months = {k: round(v, 6) for k, v in months.items() if int(k[:4]) in trade_years}
    n = len(p)
    return dict(trades=n, net_dollars=round(sum(p), 6),
        avg_trade=round(sum(p)/n, 6) if n else None,
        win_rate=round(100*sum(x > 0 for x in p)/n, 4) if n else None,
        profit_factor=round(wins/losses, 6) if losses else None,
        gross_wins=round(wins, 6), gross_losses=round(losses, 6),
        closed_trade_max_drawdown=round(dd, 6), censored_positions=len(censored),
        censored_fraction=len(censored)/max(1, n+len(censored)), monthly=months,
        positive_months=sum(x > 0 for x in months.values()),
        negative_months=sum(x < 0 for x in months.values()),
        zero_months=sum(x == 0 for x in months.values()))


def validate_base(rows, year):
    keys = {(r['spec'], r['cost_ticks_each_side']) for r in rows}
    if keys != {(s, t) for s in SPECS for t in (2, 4)} or len(rows) != 6:
        raise ValueError('Unexpected v4 specification set')
    for r in rows:
        if any(aware(t['entry']).astimezone(CHICAGO).year != year for t in r['trade_ledger']):
            raise ValueError('Wrong-year trade')
        if len(r['trade_ledger']) != r['trades']:
            raise ValueError('Base count mismatch')
        if abs(sum(float(t['net']) for t in r['trade_ledger']) - float(r['net_dollars'])) > 1e-5:
            raise ValueError('Base ledger does not reconcile')
        for t in r['trade_ledger']:
            expected = int(t['side'])*(float(t['exit_fill'])-float(t['entry_fill']))*5. - 3.
            if abs(expected-float(t['net'])) > 1e-5:
                raise ValueError('MES accounting does not reconcile')


def evaluate(rows, sources, year):
    validate_base(rows, year)
    output = []
    for r in rows:
        all_stats = stats(r['trade_ledger'], r['censored_ledger'])
        for source_name, source in sources.items():
            for lag in (1, 2):
                tagged = attach(r['trade_ledger'], source, lag)
                unresolved = attach(r['censored_ledger'], source, lag)
                matched = [t for t in tagged if t['gex'] is not None]
                matched_censored = [t for t in unresolved if t['gex'] is not None]
                reference = stats(matched, matched_censored)
                for name in FILTERS:
                    kept = [t for t in tagged if retained(t, name)]
                    kept_censored = [t for t in unresolved if retained(t, name)]
                    rejected = [t for t in matched if not retained(t, name)]
                    s = stats(kept, kept_censored)
                    s.update(year=year, spec=r['spec'], source=source_name, lag_sessions=lag,
                        filter=name, cost_ticks_each_side=r['cost_ticks_each_side'],
                        round_trip_fee_assumed=3., original_trades=all_stats['trades'],
                        original_net=all_stats['net_dollars'], matched_trades=reference['trades'],
                        matched_net=reference['net_dollars'],
                        missing_gex=len(tagged)-len(matched),
                        missing_reasons=dict(Counter(t['gex_missing_reason'] for t in tagged if t['gex'] is None)),
                        blocked_matched_trades=len(rejected), blocked_matched_net=round(sum(t['net'] for t in rejected), 6),
                        delta_net_vs_matched=round(s['net_dollars']-reference['net_dollars'], 6),
                        expectancy_change_vs_matched=round(s['avg_trade']-reference['avg_trade'], 6)
                            if s['avg_trade'] is not None and reference['avg_trade'] is not None else None,
                        ledger=kept, censored_ledger=kept_censored,
                        live_ready=False, gex_resolution='lagged_reconstructed_daily',
                        dataset_vintage_verified=False, mnq_changed=False)
                    if abs(s['net_dollars']+s['blocked_matched_net']-reference['net_dollars']) > 1e-5:
                        raise ValueError('Matched cohort fails paired reconciliation')
                    output.append(s)
    return output


def gates(rows):
    decisions = []
    for source in SERIES:
        for spec in SPECS:
            for name in ('positive_only', 'negative_only'):
                r = [x for x in rows if x['source']==source and x['spec']==spec and
                     x['filter']==name and x['cost_ticks_each_side']==4 and x['year'] in YEARS]
                primary = [x for x in r if x['lag_sessions']==1]
                delayed = [x for x in r if x['lag_sessions']==2]
                passed = len(primary)==2 and {x['year'] for x in primary}==set(YEARS) and all(
                    x['trades']>=100 and x['net_dollars']>0 and x['profit_factor'] is not None and
                    x['profit_factor']>=1.1 and x['censored_fraction']<=.01 for x in primary)
                delay_pass = len(delayed)==2 and {x['year'] for x in delayed}==set(YEARS) and all(x['trades']>0 and x['net_dollars']>0 for x in delayed)
                decisions.append(dict(source=source,spec=spec,filter=name,
                    development_numeric_gate=passed,extra_session_delay_positive_both_years=delay_pass,
                    ready_for_promotion=False,needs_as_published_source_validation=True,
                    reason='exploratory proxy filter; matched-cohort analysis, not full strategy regeneration'))
    return decisions


def run():
    import psycopg2
    from psycopg2.extras import Json
    conn = psycopg2.connect(os.environ['DATABASE_URL'], connect_timeout=15)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute('SELECT pg_try_advisory_lock(%s)', (LOCK,))
    if not cur.fetchone()[0]:
        conn.close()
        return
    code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def state(status, detail):
        cur.execute('''INSERT INTO valor_mes_gex_v5_state(study_id,status,detail)
            VALUES(%s,%s,%s) ON CONFLICT(study_id) DO UPDATE SET
            status=excluded.status,detail=excluded.detail,updated_at=now()''',
            (STUDY,status,Json(dict(detail,source_sha256=code_hash,mnq_changed=False,new_vendor_downloads=0))))
    try:
        cur.execute('''CREATE TABLE IF NOT EXISTS valor_mes_gex_v5_state(
            study_id text PRIMARY KEY,status text NOT NULL,detail jsonb,updated_at timestamptz DEFAULT now());
            CREATE TABLE IF NOT EXISTS valor_mes_gex_v5_results(
            study_id text,year integer,manifest jsonb NOT NULL,summary jsonb NOT NULL,
            evidence_gzip bytea NOT NULL,created_at timestamptz DEFAULT now(),PRIMARY KEY(study_id,year));''')
        cur.execute('SELECT status FROM valor_mes_gex_v5_state WHERE study_id=%s',(STUDY,))
        if cur.fetchone()==('completed',):
            return
        cur.execute("SELECT COUNT(*) FROM valor_mes_gex_v5_results WHERE study_id=%s AND manifest->>'source_sha256' IS DISTINCT FROM %s",(STUDY,code_hash))
        if cur.fetchone()[0]:
            state('blocked_source_version',{})
            return
        state('reading_fixed_input_ledgers',{})
        cur.execute("SELECT study_id,year,manifest,evidence_gzip FROM valor_mes_v4_results WHERE study_id=%s AND year IN (2023,2024) ORDER BY year",(BASE_STUDY,))
        saved=cur.fetchall()
        if len(saved)!=2 or any(r[2].get('source_sha256')!=BASE_HASH for r in saved):
            raise ValueError('v4 baseline version not available')
        cur.execute("SELECT trade_date,net_gamma FROM gex_structure_daily WHERE symbol='SPX' AND trade_date>='2022-01-01' AND trade_date<'2025-01-01' ORDER BY trade_date")
        spx=cur.fetchall()
        cur.execute("SELECT trade_date,net_gex FROM sw_gamma_daily WHERE trade_date>='2022-01-01' AND trade_date<'2025-01-01' ORDER BY trade_date")
        sources=dict(zip(SERIES,[clean_source(spx),clean_source(cur.fetchall())]))
        if any(not source for source in sources.values()):
            raise ValueError('Empty GEX source')
        source_evidence={k:[(d.isoformat(),v) for d,v in s] for k,s in sources.items()}
        source_hash=hashlib.sha256(json.dumps(source_evidence,sort_keys=True,allow_nan=False).encode()).hexdigest()
        all_rows=[]
        for _,year,base_manifest,compressed in saved:
            cur.execute('SELECT manifest,summary FROM valor_mes_gex_v5_results WHERE study_id=%s AND year=%s',(STUDY,year))
            previous=cur.fetchone()
            if previous:
                if previous[0]['gex_snapshot_sha256']!=source_hash:
                    raise ValueError('GEX input source changed across resumptions')
                all_rows.extend(previous[1])
                continue
            state('evaluating_paired_filters',dict(year=year))
            original=json.loads(gzip.decompress(bytes(compressed)))
            results=evaluate(original,sources,year)
            manifest=dict(study_id=STUDY,source_sha256=code_hash,base_study=BASE_STUDY,
                base_source_sha256=BASE_HASH,base_evidence_sha256=hashlib.sha256(bytes(compressed)).hexdigest(),
                gex_snapshot_sha256=source_hash,base_manifest=base_manifest,
                sources={k:dict(rows=len(s),first_date=s[0][0].isoformat(),last_date=s[-1][0].isoformat()) for k,s in sources.items()},
                filters=FILTERS,lags=[1,2],development_years=YEARS,
                no_replacement_entries=True,as_published_vintage_verified=False,
                gex_used=True,gex_resolution='lagged_daily_proxy',new_vendor_downloads=0,
                mnq_changed=False,live_ready=False,phase='paired_development_analysis',
                calendar_age_limits_days={'lag1':4,'lag2':7},
                no_gex_price_mapping=True,no_unseen_holdout_claim=True)
            summary=[{k:v for k,v in r.items() if k not in ('ledger','censored_ledger')} for r in results]
            evidence=gzip.compress(json.dumps(dict(results=results,gex_source_snapshot=source_evidence),allow_nan=False).encode(),mtime=0)
            cur.execute('INSERT INTO valor_mes_gex_v5_results(study_id,year,manifest,summary,evidence_gzip) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                        (STUDY,year,Json(manifest),Json(summary),evidence))
            all_rows.extend(summary)
        state('completed',dict(years=YEARS,summary_rows=len(all_rows),decisions=gates(all_rows),
            numeric_passes=sum(x['development_numeric_gate'] for x in gates(all_rows)),
            live_ready=False,as_published_vintage_verified=False,gex_used=True,
            gex_resolution='lagged_daily_proxy',no_2025_or_2026_outcomes_read=True))
    except Exception as exc:
        try:
            state('failed',dict(error_type=type(exc).__name__))
        except Exception:
            pass
        logging.getLogger(__name__).exception('MES GEX paired research failed')
    finally:
        try:
            cur.execute('SELECT pg_advisory_unlock(%s)',(LOCK,))
        finally:
            conn.close()


def launch_if_enabled():
    flag=os.getenv('VALOR_MES_GEX_V5_AUTORUN',os.getenv('VALOR_MES_V4_AUTORUN',
         os.getenv('VALOR_EXIT_RESEARCH_AUTORUN',os.getenv('VALOR_CONTRACT_RESEARCH_AUTORUN','false'))))
    if flag.lower() not in {'1','true','yes','on'}:
        return False
    import threading
    threading.Thread(target=run,name='valor-mes-gex-v5-cache-only',daemon=True).start()
    return True


if __name__=='__main__':
    run()
