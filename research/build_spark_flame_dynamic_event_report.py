"""Build decision tables only from independently reconciled terminal exports."""
import csv
import calendar
import datetime as dt
import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

ENGINE='6c7630b84b464c6b181fa563bbe83725b2489fbb190bf9fc2629afe4cd2ebd15'

def meets(candidate,baseline,period):
    c,b=candidate[period],baseline[period]
    return (c['hostTradeDays']>b['hostTradeDays'] and
            c['netAfterExternalSubscription']>b['netAfterExternalSubscription'] and
            c['maxClosedDrawdownPct']<=b['maxClosedDrawdownPct'])

def protective_meets(candidate,baseline,period):
    # User priority fixed before viewing this replay's candidate performance:
    # fewer trades/lower profit than baseline are acceptable, but losses after
    # subscriptions are not a profitable protective solution.
    c,b=candidate[period],baseline[period]
    return (c['netAfterExternalSubscription']>0 and
            c['maxClosedDrawdownPct']<b['maxClosedDrawdownPct'])

def build(out):
    validation=json.loads((out/'validation.json').read_text())
    report=json.loads((out/'report.json').read_text())
    if not validation.get('passed') or validation.get('checkedPaths')!=144 or validation.get('checkedSessions')!=751 or report['engineHash']!=ENGINE:
        raise ValueError('Complete independent audit PASS for this numerical engine is required')
    paths={(s['scenario']['id'],s['fillCase']):s for s in report['summary']}
    rows=[json.loads(line) for line in (out/'days.jsonl').read_text().splitlines()]
    if len(rows)!=751: raise ValueError('751 detailed days required')
    selection={}
    for bot in ('spark','flame'):
        ids=sorted({sid for sid,fill in paths if paths[sid,fill]['scenario']['bot']==bot and sid!=bot+'_base'})
        eligible=[sid for sid in ids if all(meets(paths[sid,f],paths[bot+'_base',f],'train') for f in ('natural','adverse3c'))]
        # Rank with training data only. Do not replace this choice after seeing validation.
        eligible.sort(key=lambda sid:min(paths[sid,f]['train']['netAfterExternalSubscription'] for f in ('natural','adverse3c')),reverse=True)
        chosen=eligible[0] if eligible else None
        protective=[sid for sid in ids if all(protective_meets(paths[sid,f],paths[bot+'_base',f],'train') for f in ('natural','adverse3c'))]
        protective.sort(key=lambda sid:min(paths[bot+'_base',f]['train']['maxClosedDrawdownPct']-paths[sid,f]['train']['maxClosedDrawdownPct'] for f in ('natural','adverse3c')),reverse=True)
        risk_choice=protective[0] if protective else None
        selection[bot]={'trainingQualified':eligible,'trainingSelected':chosen,'validationPass':bool(chosen and all(meets(paths[chosen,f],paths[bot+'_base',f],'validation') for f in ('natural','adverse3c'))),'fullPeriodPass':bool(chosen and all(meets(paths[chosen,f],paths[bot+'_base',f],'full') for f in ('natural','adverse3c')))}
        selection[bot].update({'protectiveObjective':'Positive profit after subscriptions and strictly smaller closed drawdown under both fills; frequency and profit versus baseline may fall. Rank by training worst-fill drawdown reduction only.','protectiveTrainingQualified':protective,'protectiveTrainingSelected':risk_choice,'protectiveValidationPass':bool(risk_choice and all(protective_meets(paths[risk_choice,f],paths[bot+'_base',f],'validation') for f in ('natural','adverse3c'))),'protectiveFullPeriodPass':bool(risk_choice and all(protective_meets(paths[risk_choice,f],paths[bot+'_base',f],'full') for f in ('natural','adverse3c')))})
    (out/'selection.json').write_text(json.dumps(selection,indent=2))
    fields=['scenario','bot','fill','period','gate','credit','regime','risk','minute','eventGuard','eventMode','dynamicShock','dynamicTrail','takePct','stopPct','maxRiskPct','startingEquity','endingEquity','pnl','returnPct','netAfterExternalSubscription','maxClosedDrawdownPct','hostTradeDays','flintTradeDays','addedHostDays','sessions']
    with (out/'scenario_summary.csv').open('w',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=fields);writer.writeheader()
        for (sid,fill),s in paths.items():
            for period in ('train','validation','full'):
                writer.writerow({'scenario':sid,'fill':fill,'period':period,**{k:s['scenario'].get(k) for k in fields if k in s['scenario']},**{k:v for k,v in s[period].items() if k in fields}})
    billing=[]
    for n in range(36):
        year=2023+(8+n)//12;month=(8+n)%12+1
        billing.append(dt.date(year,month,min(29,calendar.monthrange(year,month)[1])))
    aggregates={};clusters=defaultdict(lambda:{'addedDays':0,'lossDays':0,'pnl':0.0})
    for row in rows:
        date=dt.date.fromisoformat(row['day'])
        trade_map={(t['scenarioId'],t['fillCase']):t['trades'] for t in row['trades']}
        for a in row['accounts']:
            sid,fill=a['scenarioId'],a['fillCase'];ts=trade_map[sid,fill]
            for grain,label in [('week',f'{date.isocalendar().year}-W{date.isocalendar().week:02d}'),('month',date.strftime('%Y-%m')),('year',date.strftime('%Y'))]:
                key=(sid,fill,grain,label)
                g=aggregates.setdefault(key,{'startingEquity':a['before'],'endingEquity':a['after'],'pnl':0,'hostDays':0,'flintDays':0,'hostTickets':0,'flintTickets':0,'sessions':0})
                g['endingEquity']=a['after'];g['pnl']+=a['pnl'];g['hostDays']+=a['hostN']>0;g['flintDays']+=a['flintN']>0;g['sessions']+=1
                g['hostTickets']+=sum(t['leg'].startswith('host') for t in ts);g['flintTickets']+=sum(t['leg']=='flint' for t in ts)
            if row['vix']['ratio']>paths[sid,fill]['scenario']['baseGate'] and a['hostN']>0:
                c=clusters[sid,fill,date.strftime('%Y-%m')];c['addedDays']+=1;c['lossDays']+=a['pnl']<0;c['pnl']+=a['pnl']
    with (out/'weekly_monthly_yearly.csv').open('w',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=['scenario','fill','frequency','period','startingEquity','endingEquity','pnl','returnPct','subscriptionCharges','netAfterSubscriptions','hostDays','flintDays','hostTickets','flintTickets','sessions']);writer.writeheader()
        for (sid,fill,grain,label),g in sorted(aggregates.items()):
            def bill_label(d):
                return f'{d.isocalendar().year}-W{d.isocalendar().week:02d}' if grain=='week' else d.strftime('%Y-%m' if grain=='month' else '%Y')
            charge=50*sum(bill_label(d)==label for d in billing)
            writer.writerow({'scenario':sid,'fill':fill,'frequency':grain,'period':label,**g,'pnl':round(g['pnl'],2),'returnPct':round(g['pnl']/g['startingEquity']*100,2),'subscriptionCharges':charge,'netAfterSubscriptions':round(g['pnl']-charge,2)})
    (out/'added_day_month_clusters.json').write_text(json.dumps([{'scenario':sid,'fill':fill,'month':month,**v,'pnl':round(v['pnl'],2)} for (sid,fill,month),v in clusters.items()],indent=2))
    text=['# Spark and Flame minute-data protection replay','', '2023-09-29–2026-09-28; 751 sessions; 72 rules × two fill assumptions = 144 independently compounded paths. Flame starts $2,000; Spark $5,000. All paths passed ledger reconciliation.','', 'Selection uses training through 2025-09-26. Final-year validation starts 2025-09-29 and inherits training-end equity. These historical dates have been examined before; this is chronological retrospective validation, not an untouched prospective test.','']
    for bot in ('spark','flame'):
        decision=selection[bot];chosen=decision['trainingSelected'];robust=decision['validationPass'] and decision['fullPeriodPass']
        text+=['## '+bot.title(),'',f'Training-selected candidate: **{chosen or "none"}**. '+('It meets the more entries, more net profit, no worse closed drawdown conditions under both fills in training, validation and the full period.' if robust else '**No robust winner under the stated requirements.**'),'', '| Rule / fill | End balance | Trading P&L | Net after $1,800 | Closed drawdown | Main days / FLINT days | Final-year trading P&L |','|---|---:|---:|---:|---:|---:|---:|']
        risk_choice=decision['protectiveTrainingSelected']
        text+=['',f'Risk-focused training choice (positive profit after subscriptions and reduced drawdown under both fills; fewer entries and less profit than baseline allowed): {risk_choice or "none"}. Final-year protective criteria pass: {decision["protectiveValidationPass"]}. Full-period protective criteria pass: {decision["protectiveFullPeriodPass"]}.','']
        show=[bot+'_base']+([chosen] if chosen else [])+([risk_choice] if risk_choice and risk_choice!=chosen else [])
        for sid in show:
            for fill in ('natural','adverse3c'):
                s=paths[sid,fill];f=s['full']
                text.append(f"| {sid} / {fill} | ${f['endingEquity']:,.2f} | ${f['pnl']:,.2f} | ${f['netAfterExternalSubscription']:,.2f} | {f['maxClosedDrawdownPct']:.2f}% | {f['hostTradeDays']} / {f['flintTradeDays']} | ${s['validation']['pnl']:,.2f} |")
        for sid in show:
            text+=['','Exact parameters for '+sid+': '+json.dumps(paths[sid,'natural']['scenario'],sort_keys=True)+'.','']
        text+=['','Shock controller: after marked closing debit reaches 1.5 times entry credit, puts require a completed five-minute SPY decline of at least 0.25% and VIX increase of at least 3%; FLINT calls require a SPY rise of at least 0.25%. Trail controller: arm after gross spread profit reaches 25% of entry credit, exit after half of peak gross profit is given back. Execute at the next or later valid quote. Event blackouts apply to both host and FLINT new entries.','']
    text+=['## Execution and protection limits','', 'Natural fills use recorded minute bid/ask snapshots; adverse fills add three cents of adverse execution per spread side. Gamma is reconstructed. Invalid guard snapshots use the first valid synchronized second inside the same guard minute. These are modeled fills, not verified Tradier or broker execution.','', 'New shock/giveback exits apply to SPY host/FLINT and XSP host. Signals use completed minute observations and execute at the next or later executable quote. Unfilled triggered exits block completion. A stop is not a guaranteed maximum loss. Historical calendar dates are retrospective and original schedule versions are not recovered; unscheduled headlines are attribution only, never a hindsight exclusion rule.','', 'The study tests 72 specific rules. It does not exhaust wider entry times, hedge structures, sizing, or all VIX thresholds. No live changes are made by this replay.','', 'Detailed weekly, calendar-month and calendar-year dollars, returns on each period’s starting account equity, main/FLINT frequency and allocated external subscriptions are in weekly_monthly_yearly.csv. Subscription charges are external and do not alter sizing. Weekly or monthly buckets can be partial at study boundaries.','']
    (out/'Spark_Flame_Dynamic_Event_Study.md').write_text('\n'.join(text))
    archive=out/'Spark_Flame_Dynamic_Event_Study.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for f in out.iterdir():
            if f.is_file() and f.suffix in ('.json','.jsonl','.csv','.md'):z.write(f,f.name)
    print(json.dumps({'built':str(archive),'selection':selection}))

if __name__=='__main__': build(Path(sys.argv[1]))
