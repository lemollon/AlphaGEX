#!/usr/bin/env python3
"""Offline fixed-design signal diagnostic; no trading, fitting or DB access."""
import argparse
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from replay_valor_execution import CT, UTC, load_inputs, timestamp

HORIZONS = (1, 5, 15, 30)
SPLIT = timestamp('2026-09-21T00:00:00+00:00')
START = timestamp('2026-09-15T00:00:00+00:00')
END = timestamp('2026-09-22T12:42:00+00:00')
SOURCES = ('GEX_MOMENTUM', 'GEX_MEAN_REVERSION')


def session(at):
    return 'overnight' if at.astimezone(CT).hour >= 15 or at.astimezone(CT).hour < 8 else 'rth'


def observations(bars, signals):
    """One global 30-minute exclusion window; identical cohort at all horizons.

    Enter next-minute open, exit horizon-minute open. MFE/MAE use only
    intervening bars, excluding the exit bar's subsequent high and low.
    Require all 31 timestamps so closures cannot masquerade as continuous time.
    """
    rows, counts = [], Counter()
    next_allowed = START
    for entry in sorted(signals):
        for signal in signals[entry]:
            scan = timestamp(signal['scan_time'])
            if entry < next_allowed:
                counts['overlap_excluded'] += 1
                continue
            if signal['signal_source'] not in SOURCES:
                raise ValueError('Unexpected signal source')
            times = [entry + timedelta(minutes=i) for i in range(31)]
            if any(t not in bars for t in times):
                counts['closure_or_end_excluded'] += 1
                continue
            if scan < SPLIT <= times[-1]:
                counts['split_boundary_excluded'] += 1
                continue
            next_allowed = times[-1]
            sign = 1 if signal['signal_direction'] == 'LONG' else -1
            price = bars[entry][0]
            # CME trading date: evening session belongs to the next date.
            local = entry.astimezone(CT)
            day = (local + timedelta(days=1) if local.hour >= 17 else local).date().isoformat()
            for horizon in HORIZONS:
                held = [bars[t] for t in times[:horizon]]
                high, low = max(b[1] for b in held), min(b[2] for b in held)
                forward = sign * (bars[times[horizon]][0] - price)
                rows.append(dict(scan_id=signal['scan_id'], entry_utc=entry.isoformat(),
                                 split='development' if scan < SPLIT else 'validation',
                                 source=signal['signal_source'], session=session(scan), trading_day=day,
                                 direction=signal['signal_direction'], horizon=horizon,
                                 forward_points=forward, gross_dollars=round(forward * 5, 2),
                                 mfe_points=max(0, high-price if sign == 1 else price-low),
                                 mae_points=max(0, price-low if sign == 1 else high-price)))
            counts['nonoverlapping_windows_selected'] += 1
    return rows, dict(counts)


def summarize(rows, fee):
    if not rows:
        return {'n': 0, 'days': 0, 'net_mean_2ticks': None}
    gross = [r['gross_dollars'] for r in rows]
    daily = defaultdict(float)
    for row in rows:
        daily[row['trading_day']] += row['gross_dollars'] - fee - 5
    result = dict(n=len(rows), days=len(daily), gross_mean=round(sum(gross)/len(rows), 2),
                  mfe_mean_points=round(sum(r['mfe_points'] for r in rows)/len(rows), 3),
                  mae_mean_points=round(sum(r['mae_points'] for r in rows)/len(rows), 3),
                  daily_net_2ticks={k: round(v, 2) for k, v in sorted(daily.items())},
                  positive_days=sum(v > 0 for v in daily.values()))
    for ticks in (1, 2, 4):
        cost = fee + ticks * 2 * 1.25
        values = [g-cost for g in gross]
        result[f'net_mean_{ticks}ticks'] = round(sum(values)/len(values), 2)
        result[f'net_total_{ticks}ticks'] = round(sum(values), 2)
        result[f'win_pct_{ticks}ticks'] = round(100*sum(v > 0 for v in values)/len(values), 1)
    return result


def analyze(rows, fee):
    groups = []
    for split in ('development', 'validation'):
        for source in SOURCES:
            for sess in ('rth', 'overnight'):
                for horizon in HORIZONS:
                    group = [r for r in rows if (r['split'], r['source'], r['session'], r['horizon']) == (split, source, sess, horizon)]
                    groups.append(dict(split=split, source=source, session=sess, horizon=horizon, **summarize(group, fee)))
    # Fixed primary horizon and eligibility. Validation never selects a winner.
    eligible = [g for g in groups if g['split'] == 'development' and g['horizon'] == 15
                and g['n'] >= 20 and g['days'] >= 3 and g['net_mean_2ticks'] > 0
                and g['positive_days'] > g['days']/2]
    candidate = max(eligible, key=lambda g: (g['net_mean_2ticks'], g['source'], g['session'])) if eligible else None
    return groups, candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', required=True, type=Path)
    parser.add_argument('--round-trip-fee', type=float, default=3)
    args = parser.parse_args()
    import math
    if not math.isfinite(args.round_trip_fee) or args.round_trip_fee < 0:
        raise ValueError('Invalid fees')
    bars, signals, loaded = load_inputs(args.data_dir, START, END)
    rows, excluded = observations(bars, signals)
    groups, candidate = analyze(rows, args.round_trip_fee)
    report = dict(test='FIXED-DESIGN MES SIGNAL QUALITY', production_ready=False,
                  split_utc=SPLIT.isoformat(), primary_horizon_minutes=15,
                  fee_assumption=args.round_trip_fee, input_counts=loaded, cohort_counts=excluded,
                  groups=groups, development_selected_candidate=candidate,
                  input_sha256={name: hashlib.sha256((args.data_dir/name).read_bytes()).hexdigest()
                                for name in ('MESZ6_1m.csv.gz', 'mes_scan_inputs.jsonl.gz')},
                  limitations=[
                      'Chronological validation is retrospective: aggregate results for this week were already inspected. Not an untouched holdout.',
                      'One week and very few validation sessions cannot establish profitability or statistical significance.',
                      'Nonoverlapping windows reduce duplicate exposure; they are not statistically independent. No IID significance claim.',
                      'Global first-signal sampling can underrepresent another source arriving during the exclusion window.',
                      'Same 30-minute-complete cohort at all horizons; excludes closures, split boundary and final incomplete windows.',
                      'Recorded signals and assumed MESZ6 contract assignment; historical n+1 GEX and feedback not regenerated.',
                      'Constant fees assumed; adverse slippage approximates spread/impact. Fixed-horizon returns are not full Valor execution.',
                      'MFE is an ex-post excursion, not a realizable profit target. Four fixed buckets still entail selection risk.',
                  ])
    out = args.data_dir / ('signal_quality_' + datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    (out/'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    with gzip.open(out/'observations.jsonl.gz', 'wt') as handle:
        for row in rows:
            handle.write(json.dumps(row)+'\n')
    print('NET $/OBSERVATION — ONE MES; 2 TICKS/SIDE + ASSUMED FEES')
    print('period       source              session      n days      1m      5m     15m     30m')
    for split in ('development', 'validation'):
        for source in SOURCES:
            for sess in ('rth', 'overnight'):
                subset = [g for g in groups if (g['split'],g['source'],g['session']) == (split,source,sess)]
                first = subset[0]
                values = ' '.join(f"{g['net_mean_2ticks']:7.2f}" if g['n'] else '    n/a' for g in subset)
                print(f"{split:12} {source:19} {sess:10} {first['n']:3} {first['days']:4} {values}")
    if candidate:
        print('DEVELOPMENT-SELECTED CANDIDATE:', candidate['source'], candidate['session'])
        print('Fixed horizon check ($/observation at 2 ticks/side):')
        for g in groups:
            if (g['source'], g['session']) == (candidate['source'], candidate['session']):
                print(g['split'], f"{g['horizon']}min", 'n=', g['n'], 'net_mean=', g['net_mean_2ticks'])
    else:
        print('NO CANDIDATE met the fixed development criteria. Do not relax criteria to manufacture a winner.')
    print('COHORT:', json.dumps(excluded))
    print('REPORT:', out/'summary.json')
    print('No orders, database access, or trading-setting changes. All 1/5/15/30-minute groups saved in report.')


if __name__ == '__main__':
    main()
