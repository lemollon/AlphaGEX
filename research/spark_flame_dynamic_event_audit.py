#!/usr/bin/env python3
"""Independent, read-only reconciliation for the Spark/Flame minute protection replay."""
import concurrent.futures
import json
import sys
import urllib.request
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT=Path('/workspace/scratch/e7a31f7e798f')
OUT=ROOT/'spark-flame-dynamic-event-results'
REPORT=Path('/tmp/spark-flame-dynamic-event-report.json')
SESSIONS=ROOT/'flame-gate-sweep/results/sessions.json'
URL='https://spark-flame-current-3y-20260928.onrender.com/day?date='

def cents(x):
    return int((Decimal(str(x))*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))

def get_day(day, token):
    req=urllib.request.Request(URL+day,headers={'Authorization':'Bearer '+token})
    with urllib.request.urlopen(req,timeout=60) as r:
        return json.loads(r.read())

def main():
    if len(sys.argv)!=2:
        raise SystemExit('token-file required')
    token=Path(sys.argv[1]).read_text().strip()
    report=json.loads(REPORT.read_text())
    if report.get('engineHash')!='6c7630b84b464c6b181fa563bbe83725b2489fbb190bf9fc2629afe4cd2ebd15':
        raise SystemExit('obsolete numerical engine: results rejected')
    days=json.loads(SESSIONS.read_text())
    event_calendar=json.loads((ROOT/'macro-event-study/event_calendar.json').read_text())
    OUT.mkdir(exist_ok=True)
    errors=[]
    def check(ok,msg):
        if not ok: errors.append(msg)
    status=report['status']; summary=report['summary']
    paths={(x['scenario']['id'],x['fillCase']):x for x in summary}
    check(status['stage']=='completed_with_coverage_limits','run_not_terminal')
    check(status['completed']==status['total']==751,'sessions_not_751')
    check(not status.get('dataErrors'),'data_errors_present')
    check(len(paths)==144==len(summary),'summary_path_count')
    check(paths[('flame_base','natural')]['full']['endingEquity']==8185.2,'flame_baseline_natural_parity')
    check(paths[('flame_base','adverse3c')]['full']['endingEquity']==2116.8,'flame_baseline_adverse_parity')
    check(paths[('spark_base','natural')]['full']['endingEquity']==8842.4,'spark_baseline_natural_parity')
    check(paths[('spark_base','adverse3c')]['full']['endingEquity']==4322.4,'spark_baseline_adverse_parity')
    check(len(days)==751 and len(set(days))==751 and days==sorted(days),'calendar_mismatch')
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        rows=list(pool.map(lambda d:get_day(d,token),days))
    rows_by_day={r['day']:r for r in rows}
    (OUT/'report.json').write_text(json.dumps(report,indent=2))
    with (OUT/'days.jsonl').open('w') as f:
        for row in rows: f.write(json.dumps(row,separators=(',',':'))+'\n')
    chains={p:cents(x['full']['startingEquity']) for p,x in paths.items()}
    pnl=defaultdict(int); tickets=defaultdict(int); host_days=defaultdict(int); flint_days=defaultdict(int)
    ledger=defaultdict(list)
    fomc={'2023-11-01','2023-12-13','2024-01-31','2024-03-20','2024-05-01','2024-06-12','2024-07-31','2024-09-18','2024-11-07','2024-12-18','2025-01-29','2025-03-19','2025-05-07','2025-06-18','2025-07-30','2025-09-17','2025-10-29','2025-12-10','2026-01-28','2026-03-18','2026-04-29','2026-06-17','2026-07-29','2026-09-16'}
    for expected,row in zip(days,rows):
        check(row.get('day')==expected,f'day_mismatch:{expected}')
        accts={(a['scenarioId'],a['fillCase']):a for a in row.get('accounts',[])}
        trs={(a['scenarioId'],a['fillCase']):a['trades'] for a in row.get('trades',[])}
        check(set(accts)==set(paths)==set(trs) and len(row.get('accounts',[]))==len(row.get('trades',[]))==144,f'path_set:{expected}')
        for p,a in accts.items():
            ledger[p].append((expected,a))
            ts=trs[p]
            scenario=paths[p]['scenario'];mode=scenario.get('eventMode','none')
            expected_events=[e['kind'] for e in event_calendar.get(expected,[])]
            check(sorted(row.get('events',[]))==sorted(expected_events),f'event_labels:{expected}')
            blackout=('FOMC' in expected_events if mode=='fed' else any(k in expected_events for k in ['FOMC','CPI','PAYROLLS']) if mode=='major' else False)
            if blackout: check(not ts and a['hostN']==a['flintN']==0,f'event_admission:{p}:{expected}')
            vix_prices=dict(row['minuteInputs']['vix']);spy_closes=dict(row['minuteInputs']['spyClose'])
            for t in ts:
                if t['reason'] not in ('intraday_shock','profit_giveback'):continue
                check(t['exit']>t.get('triggerMinute',t['exit']),f'dynamic_no_delay:{p}:{expected}')
                sig=t['signal'];trigger=t['triggerMinute']
                current=spy_closes.get(trigger);prior=spy_closes.get(trigger-5)
                actual_spy=(current/prior-1)*100 if current and prior else None
                vv=vix_prices.get(trigger);vp=vix_prices.get(trigger-5)
                actual_vix=(vv/vp-1)*100 if vv and vp else None
                for k,value in [('spy5Pct',actual_spy),('vix5Pct',actual_vix)]:
                    check(sig.get(k) is None if value is None else sig.get(k) is not None and abs(sig[k]-value)<1e-8,f'signal_input:{p}:{expected}:{k}')
                expected_pnl=((cents(t['credit'])-cents(t['exitDebit']))*100-140)*t['n']
                check(cents(t['pnl'])==expected_pnl,f'dynamic_quote_pnl:{p}:{expected}')
                if t['reason']=='intraday_shock':
                    check(scenario.get('dynamicShock') and sig['markedDebit']>=t['credit']*1.50,f'shock_arm:{p}:{expected}')
                    right_call=t['leg']=='flint'
                    check(actual_spy is not None and (actual_spy>=.25 if right_call else actual_spy<=-.25 and actual_vix is not None and actual_vix>=3),f'shock_direction:{p}:{expected}')
                else:
                    check(scenario.get('dynamicTrail') and sig['peakProfit']>=t['credit']*.25 and t['credit']-sig['markedDebit']<=sig['peakProfit']*.50,f'trail_trigger:{p}:{expected}')
            check(not a.get('unresolved'),f'unresolved:{p}:{expected}')
            check(cents(a['before'])==chains[p],f'chain_before:{p}:{expected}')
            daypnl=sum(cents(t['pnl']) for t in ts)
            check(daypnl==cents(a['pnl']),f'daily_trade_pnl:{p}:{expected}')
            check(cents(a['after'])==cents(a['before'])+daypnl,f'chain_after:{p}:{expected}')
            check(all(t['day']==expected and t['symbol'] in ('SPY','XSP') and t['n']>0 and t['entry']<=t['exit'] for t in ts),f'trade_shape:{p}:{expected}')
            if 'risk10' in p[0]:
                risk=sum(cents((abs(t['short']-t['long'])-t['credit'])*100*t['n']) for t in ts)
                check(risk<=cents(a['before'])//10,f'risk_cap:{p}:{expected}')
            if '_fed' in p[0] and expected in fomc:
                check(a['hostN']==0 and a['flintN']==0 and not ts,f'fed_blackout:{p}:{expected}')
            pnl[p]+=daypnl; tickets[p]+=len(ts); host_days[p]+=a['hostN']>0; flint_days[p]+=a['flintN']>0; chains[p]=cents(a['after'])
    for p,s in paths.items():
        full=s['full']; tc=s['tradeCounts']
        check(pnl[p]==cents(full['pnl']),f'summary_pnl:{p}')
        check(chains[p]==cents(full['endingEquity']),f'summary_end:{p}')
        check(tickets[p]==tc['total'],f'ticket_count:{p}')
        check(host_days[p]==full['hostTradeDays'],f'host_days:{p}')
        check(flint_days[p]==full['flintTradeDays'],f'flint_days:{p}')
        check(cents(full['netAfterExternalSubscription'])==pnl[p]-180000,f'subscription:{p}')
        check(s['complete'] and not s['unresolved'],f'incomplete:{p}')
        for period,bills in [('full',36),('train',24),('validation',12)]:
            selected=[(d,a) for d,a in ledger[p] if period=='full' or (d<'2025-09-29' if period=='train' else d>='2025-09-29')]
            stats=s[period]
            check(bool(selected),f'period_empty:{p}:{period}')
            start=cents(selected[0][1]['before']);end=cents(selected[-1][1]['after'])
            peak=start;dd=0;ddpct=0;marked_peak=start;marked_dd=0;months=defaultdict(int)
            streak=longest=worst=lossdays=gaps=hosts=flints=added=traded=0
            for d,a in selected:
                after=cents(a['after']);dp=cents(a['pnl']);peak=max(peak,after)
                dd=max(dd,peak-after);ddpct=max(ddpct,(peak-after)*100/peak)
                marked_dd=max(marked_dd,marked_peak-cents(a['markedMin']),cents(a['markedDD']))
                marked_peak=max(marked_peak,cents(a['markedPeak']))
                gaps+=a['markGaps'];hosts+=a['hostN']>0;flints+=a['flintN']>0;traded+=(a['hostN']+a['flintN'])>0
                ratio=rows_by_day[d]['vix']['ratio']
                added+=a['hostN']>0 and ratio>s['scenario']['baseGate']
                lossdays+=dp<0;streak=streak+1 if dp<0 else 0;longest=max(longest,streak);worst=min(worst,dp);months[d[:7]]+=dp
            for key,value in [('startingEquity',start),('endingEquity',end),('pnl',end-start),('maxClosedDrawdown',dd),('maxMarkedDrawdownObserved',marked_dd),('netAfterExternalSubscription',end-start-bills*5000),('subscriptionCharges',bills*5000),('worstDay',worst)]:
                check(cents(stats[key])==value,f'period_{key}:{p}:{period}')
            check(cents(stats['maxClosedDrawdownPct'])==cents(ddpct),f'period_dd_pct:{p}:{period}')
            check(cents(stats['returnPct'])==cents((end-start)*100/start),f'period_return:{p}:{period}')
            for key,value in [('sessions',len(selected)),('hostTradeDays',hosts),('flintTradeDays',flints),('addedHostDays',added),('tradingDays',traded),('lossDays',lossdays),('longestLosingDayStreak',longest),('markGapMinutes',gaps)]:
                check(stats[key]==value,f'period_{key}:{p}:{period}')
            check({m:cents(v) for m,v in stats['monthly'].items()}==dict(months),f'period_months:{p}:{period}')
    result={'passed':not errors,'errors':errors,'checkedSessions':len(rows),'checkedPaths':len(paths),'checkedTrades':sum(tickets.values()),'scope':'Independent replay-ledger reconciliation: session coverage, paths, trade/day/summary P&L, balances, fixed risk cap, FOMC blackout, subscriptions and frozen baseline parity. Historical fills and reconstructed gamma remain modeled assumptions.'}
    (OUT/'validation.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    if errors: raise SystemExit(1)
if __name__=='__main__': main()
