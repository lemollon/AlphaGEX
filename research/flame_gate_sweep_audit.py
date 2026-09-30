import collections,csv,gzip,hashlib,json,pathlib,zipfile
OUT=pathlib.Path(__file__).resolve().parent/'results'
def rounded(x):return round(x+1e-9,2)
def metrics(rows,period):
 rows=[d for d in rows if period=='full' or (d['day']<'2025-09-29' if period=='train' else d['day']>='2025-09-29')]
 start=rows[0]['before'];peak=marked=start;dd=ddpct=mdd=0;hosts=flints=added=trading=losses=streak=longest=gaps=0;worst=0;months=collections.defaultdict(float)
 for d in rows:
  peak=max(peak,d['after']);dd=max(dd,peak-d['after']);ddpct=max(ddpct,(peak-d['after'])/peak)
  mdd=max(mdd,marked-d['markedMin'],d['markedDD']);marked=max(marked,d['markedPeak']);gaps+=d['markGaps'];hosts+=d['hostN']>0;flints+=d['flintN']>0;added+=d['hostN']>0 and d['ratio']>.8;trading+=d['hostN']+d['flintN']>0;losses+=d['pnl']<0;streak=streak+1 if d['pnl']<0 else 0;longest=max(longest,streak);worst=min(worst,d['pnl']);months[d['day'][:7]]+=d['pnl']
 end=rows[-1]['after'];pnl=rounded(end-start);charges={'full':1800,'train':1200,'validation':600}[period]
 return dict(startingEquity=start,endingEquity=end,pnl=pnl,returnPct=rounded(100*pnl/start),netAfterExternalSubscription=rounded(pnl-charges),subscriptionCharges=charges,maxClosedDrawdown=rounded(dd),maxClosedDrawdownPct=rounded(ddpct*100),maxMarkedDrawdownObserved=rounded(mdd),markGapMinutes=gaps,hostTradeDays=hosts,flintTradeDays=flints,addedHostDays=added,tradingDays=trading,lossDays=losses,longestLosingDayStreak=longest,worstDay=worst,monthly={m:rounded(v) for m,v in months.items()},sessions=len(rows))
def main():
 r=json.loads((OUT/'report.json').read_text());assert r['status']['completed']==751 and r['status']['baselineParity'] and not r['status']['dataErrors']
 summary={(a['scenario']['id'],a['fillCase']):a for a in r['summary']};assert len(summary)==506
 rows=collections.defaultdict(list);counts=collections.defaultdict(collections.Counter);added=collections.defaultdict(lambda:dict(trades=0,pnl=0,losses=0,months={}));dates=[];totaltrades=0
 with gzip.open(OUT/'days.jsonl.gz','rt') as f:
  for line in f:
   d=json.loads(line);day=d['day'];assert not dates or dates[-1]<day;dates.append(day);assert len(d['accounts'])==506 and len(d['trades'])==506
   tradegroups={(a['scenarioId'],a['fillCase']):a['trades'] for a in d['trades']};assert len(tradegroups)==506
   for a in d['accounts']:
    k=(a['scenarioId'],a['fillCase']);assert k in summary and not a['unresolved'];ts=tradegroups[k]
    assert rounded(sum(t['pnl'] for t in ts))==a['pnl'],(day,k,'trade pnl')
    assert rounded(a['after']-a['before'])==a['pnl'];assert a['before']==(rows[k][-1]['after'] if rows[k] else 2000)
    assert all(t['day']==day and t['n']>0 and t['n']==int(t['n']) for t in ts)
    assert sum(t['n'] for t in ts if t['leg'].startswith('host'))==a['hostN'];assert sum(t['n'] for t in ts if t['leg']=='flint')==a['flintN']
    counts[k]['total']+=len(ts);counts[k]['host']+=sum(t['leg'].startswith('host') for t in ts);counts[k]['flint']+=sum(t['leg']=='flint' for t in ts);counts[k]['addedHost']+=a['hostN']>0 and d['vix']['ratio']>.8
    for t in ts:
     totaltrades+=1
     if d['vix']['ratio']>.8 and t['leg'].startswith('host'):
      z=added[k];z['trades']+=1;z['pnl']=rounded(z['pnl']+t['pnl']);z['losses']+=t['pnl']<0;month=day[:7];m=z['months'].setdefault(month,dict(trades=0,pnl=0,losses=0));m['trades']+=1;m['pnl']=rounded(m['pnl']+t['pnl']);m['losses']+=t['pnl']<0
    rows[k].append({**a,'ratio':d['vix']['ratio']})
 assert len(dates)==751 and dates[0]=='2023-09-29' and dates[-1]=='2026-09-28'
 # frozen calendar exported separately by original native runner
 assert dates==json.loads((OUT/'sessions.json').read_text())
 for k,a in summary.items():
  assert a['complete'] and not a['unresolved'];assert dict(counts[k])==a['tradeCounts'],(k,counts[k],a['tradeCounts'])
  for p in ['full','train','validation']:
   calculated=metrics(rows[k],p)
   for field,value in calculated.items():assert value==a[p][field],(k,p,field,value,a[p][field])
 assert summary[('baseline','natural')]['full']['endingEquity']==8185.2
 assert summary[('baseline','adverse3c')]['full']['endingEquity']==2116.8
 base={f:summary['baseline',f] for f in ['natural','adverse3c']}
 def pass_period(sid,p):
  return all(summary[sid,f][p]['hostTradeDays']>base[f][p]['hostTradeDays'] and summary[sid,f][p]['netAfterExternalSubscription']>max(0,base[f][p]['netAfterExternalSubscription']) and summary[sid,f][p]['maxClosedDrawdownPct']<=base[f][p]['maxClosedDrawdownPct'] for f in base)
 # Ranking reads training fields only; validation is inspected afterward.
 ids=[sid for sid,f in summary if f=='natural' and sid!='baseline']
 ranked=sorted(ids,key=lambda sid:(summary[sid,'adverse3c']['train']['netAfterExternalSubscription'],-summary[sid,'adverse3c']['train']['maxClosedDrawdownPct'],summary[sid,'natural']['train']['netAfterExternalSubscription']),reverse=True)
 survivors=[sid for sid in ranked if pass_period(sid,'train')]
 selection={'selectionUses':'training metrics only','trainingSurvivors':survivors,'topTrainingRanked':ranked[:10],'validationPassAmongTrainingSurvivors':[sid for sid in survivors if pass_period(sid,'validation')],'addedHostTrades':{sid+'|'+f:v for (sid,f),v in added.items()}}
 selection['neighborStability']={}
 for sid in ranked[:10]:
  rule=summary[sid,'natural']['scenario'];neighbors=[other for other in ids if all(summary[other,'natural']['scenario'][k]==rule[k] for k in ['risk','credit','regime'])]
  neighbors=sorted(neighbors,key=lambda other:abs(summary[other,'natural']['scenario']['gate']-rule['gate']))[:3]
  selection['neighborStability'][sid]=[{"scenario":other,"gate":summary[other,'natural']['scenario']['gate'],"trainPass":pass_period(other,'train'),"validationPass":pass_period(other,'validation'),"adverseTrainNet":summary[other,'adverse3c']['train']['netAfterExternalSubscription'],"adverseValidationNet":summary[other,'adverse3c']['validation']['netAfterExternalSubscription']} for other in neighbors]
 (OUT/'selection.json').write_text(json.dumps(selection,indent=2))
 validation=dict(passed=True,checkedPaths=506,checkedSessions=751,checkedTrades=totaltrades,baselineParity=True,engineHash=r['engineHash'],errors=[])
 (OUT/'validation.json').write_text(json.dumps(validation,indent=2))
 with (OUT/'scenario_summary.csv').open('w',newline='') as f:
  fields=['scenario','gate','risk','credit','regime','fills','period']+list(next(iter(summary.values()))['full'].keys());fields.remove('monthly');w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for (sid,fill),a in summary.items():
   for p in ['full','train','validation']:w.writerow({'scenario':sid,**{k:a['scenario'][k] for k in ['gate','risk','credit','regime']},'fills':fill,'period':p,**{k:v for k,v in a[p].items() if k!='monthly'}})
 lines=['# Flame gate scenario comparison','',f'Validated: 253 rule sets × 2 fill assumptions, 506 complete paths, 751 sessions, {totaltrades:,} modeled trade records.','',f'Training survivors meeting every predeclared objective: **{len(survivors)}**. Those also passing chronological validation: **{len(selection["validationPassAmongTrainingSurvivors"])}**.','', 'Ranking below uses training adverse profit only, with drawdown and natural profit tie-breakers. It does not imply that these candidates pass the risk/frequency objectives.','', '| Training rank / rule | Full natural net after subscription | Full adverse net after subscription | Host days natural / adverse | Full closed DD% natural / adverse | Validation net natural / adverse | Training objectives pass | Validation objectives pass |','|---|---:|---:|---:|---:|---:|---|---|']
 for sid in ['baseline']+ranked[:10]:
  n=summary[sid,'natural'];a=summary[sid,'adverse3c'];lines.append(f'| {sid} | ${n["full"]["netAfterExternalSubscription"]:,.2f} | ${a["full"]["netAfterExternalSubscription"]:,.2f} | {n["full"]["hostTradeDays"]} / {a["full"]["hostTradeDays"]} | {n["full"]["maxClosedDrawdownPct"]:.2f}% / {a["full"]["maxClosedDrawdownPct"]:.2f}% | ${n["validation"]["netAfterExternalSubscription"]:,.2f} / ${a["validation"]["netAfterExternalSubscription"]:,.2f} | {pass_period(sid,"train")} | {pass_period(sid,"validation")} |')
 lines+=['','Sizing/credit/regime changes apply only to newly admitted ratio>0.80 sessions. FLINT and host risk remain netted; every account compounds independently. Subscription is external $1,800 over three years. Natural and adverse minute execution are models, not verified historical broker fills. Reconstructed gamma and bounded-second guard repairs inherit the validated baseline assumptions. Quote-gap intraday drawdown is an observed bound.','', 'Training ends September 26, 2025; validation starts September 29, 2025. Validation inherits training-ending account equity. The baseline study already covered these dates: this is a chronological scenario holdout, not pristine unseen data. A large grid introduces selection risk. No live strategy was changed.','', 'See scenario_summary.csv for all parameter combinations and train/validation/full metrics, selection.json for added-host trade P&L, and days.jsonl.gz for every trade/day reconciliation.']
 (OUT/'Flame_Gate_Scenario_Study.md').write_text('\n'.join(lines)+'\n')
 archive=OUT/'Flame_Gate_Scenario_Study.zip'
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for name in ['Flame_Gate_Scenario_Study.md','report.json','validation.json','selection.json','scenario_summary.csv','sessions.json','days.jsonl.gz']:z.write(OUT/name,name)
 print(json.dumps({'validation':validation,'archive':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'trainingSurvivors':len(survivors),'validationPass':selection['validationPassAmongTrainingSurvivors']}),flush=True)
if __name__=='__main__':main()
