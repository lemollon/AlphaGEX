"""Historical event attribution. This does NOT simulate an avoided-day strategy."""
import datetime as dt
import html
import json
import re
import sys
from collections import Counter,defaultdict
from pathlib import Path

root=Path(sys.argv[1])
events=defaultdict(list)
types={'Consumer Price Index':'CPI','Employment Situation':'PAYROLLS','Producer Price Index':'PPI','Job Openings and Labor Turnover Survey':'JOLTS'}
clean=lambda s:' '.join(html.unescape(re.sub('<[^>]+>',' ',s)).split())
for year in range(2023,2027):
    source=f'https://www.bls.gov/schedule/{year}/'
    page=(root/'macro-event-study'/f'bls_{year}.html').read_text()
    found=Counter()
    for tr in re.findall(r'<tr\b[^>]*>(.*?)</tr>',page,re.S):
        cells=re.findall(r'<td\b[^>]*>(.*?)</td>',tr,re.S)
        if len(cells)!=3:continue
        date,time,desc=map(clean,cells)
        title=re.search(r'<strong>(.*?)</strong>',cells[2],re.S)
        if not title or clean(title[1]) not in types:continue
        kind=types[clean(title[1])]
        date=dt.datetime.strptime(date,'%A, %B %d, %Y').date().isoformat()
        if not '2023-09-29'<=date<='2026-09-28':continue
        if not re.fullmatch(r'\d\d:\d\d [AP]M',time):raise ValueError('invalid release time')
        events[date].append({'kind':kind,'timeET':time,'source':source,'title':desc,'calendarAvailability':'Historical published calendar; original point-in-time schedule versions not recovered; no surprise values used'})
        found[kind]+=1
    print(year,dict(found))
source=(root/'alphagex-test-run/research/flame_event_risk_sweep_20260930.cjs').read_text()
section=source.split('const FOMC_DECISION_DAYS=new Set(')[-1].split(');',1)[0]
if section==source:raise ValueError('FOMC dates not found')
for day in re.findall(r"'([0-9]{4}-[0-9]{2}-[0-9]{2})'",section):
    events[day].append({'kind':'FOMC','timeET':'02:00 PM','source':'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm','title':'FOMC policy decision','calendarAvailability':'Scheduled meeting; no decision outcome used'})
rows=[json.loads(line) for line in (root/'spark-flame-minute-protection-results/days.jsonl').read_text().splitlines()]
calendar=[r['day'] for r in rows]
assert len(calendar)==751
stats=defaultdict(lambda:{'sessions':0,'tradingDays':0,'lossDays':0,'grossLoss':0,'grossWin':0,'recordedPnl':0})
worst=defaultdict(list)
for r in rows:
    labels=[e['kind'] for e in events.get(r['day'],[])];buckets=['ALL','ANY_EVENT' if labels else 'NO_LISTED_EVENT',*labels]
    for a in r['accounts']:
        if a['scenarioId'] not in ('spark_base','spark_add','flame_base','flame_add'):continue
        key=(a['scenarioId'],a['fillCase'])
        if a['pnl']<0:worst[key].append({'date':r['day'],'pnl':a['pnl'],'events':events.get(r['day'],[]),'before':a['before'],'lossPct':round(-a['pnl']/a['before']*100,2)})
        for bucket in buckets:
            s=stats[key+(bucket,)];s['sessions']+=1;s['tradingDays']+=a['hostN']+a['flintN']>0;s['lossDays']+=a['pnl']<0;s['recordedPnl']+=a['pnl'];s['grossLoss']+=min(0,a['pnl']);s['grossWin']+=max(0,a['pnl'])
output={'scope':'Attribution of already reconciled account ledgers; correlation is not causation; no counterfactual profits or rerun sizing inferred','events':dict(sorted(events.items())),'eventCounts':dict(Counter(e['kind'] for row in events.values() for e in row)),'statistics':[],'worstDays':{f'{sid}:{fill}':sorted(v,key=lambda d:d['pnl'])[:20] for (sid,fill),v in worst.items()}}
for (sid,fill,bucket),s in stats.items():
    for k in ('grossLoss','grossWin','recordedPnl'):s[k]=round(s[k],2)
    s['lossRateOnTradedDaysPct']=round(s['lossDays']/s['tradingDays']*100,2) if s['tradingDays'] else None
    output['statistics'].append({'scenario':sid,'fill':fill,'bucket':bucket,**s})
(root/'macro-event-study/event_loss_attribution.json').write_text(json.dumps(output,indent=2))
(root/'macro-event-study/event_calendar.json').write_text(json.dumps(dict(sorted(events.items())),indent=2))
print('calendar counts',output['eventCounts'])
for row in output['statistics']:
    if row['scenario'] in ('spark_base','flame_base') and row['fill']=='natural' and row['bucket'] in ('FOMC','PAYROLLS','CPI','NO_LISTED_EVENT'):print(row)
