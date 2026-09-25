"""Fast frozen-entry exit repair for the validated 311-session Research extension.
Uses only the 57 exact Research entries recovered from the completed cleanroom run.
Entry discovery is NOT rerun; date/strike/efficiency are frozen evidence. Only exit
rules are varied against fresh ThetaData post-entry quote paths.
Research only; no live changes.
"""
import os, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import HTTPServer
import flame_research_exit_repair as repair
import flame_two_entry_optimized as base

core=repair.core
core.SPEC.update({
    "id":"flame-research-frozen57-exit-repair-20260925",
    "start":"2025-06-02","end":"2026-08-31",
    "scope":"frozen 57 validated Research entries; fresh post-entry exit replay only",
    "no_saved_price_inputs":True,
    "no_previous_trade_inputs":False,
    "frozen_entry_source":"completed 311-session cleanroom dual_ext_day ledger",
})

TRADES = [
("2025-06-13",6010000,"0.6488713943046927855341656928"),
("2025-06-18",5990000,"0.4817700354532096892386507292"),
("2025-07-23",6320000,"0.5839822024472634520753738793"),
("2025-08-01",6230000,"0.5619834710743801652892561983"),
("2025-08-20",6350000,"0.3450292397660818713450292398"),
("2025-09-02",6350000,"0.9104477611939619068834929879"),
("2025-09-24",6600000,"0.6791443850267465469415768250"),
("2025-10-10",6610000,"0.4198784592585688548183377507"),
("2025-10-14",6620000,"0.3829194708749129728475284289"),
("2025-10-15",6650000,"0.7140186915888117390165079930"),
("2025-10-16",6640000,"0.4355932203389830508474576271"),
("2025-10-30",6830000,"0.3269841269841269841269841270"),
("2025-10-31",6820000,"0.48"),
("2025-11-14",6740000,"0.3556187766714183675327644785"),
("2025-11-18",6600000,"0.5440171881886293521375055090"),
("2025-11-20",6570000,"0.9843260188087774294670846395"),
("2025-11-21",6590000,"0.6563803169307756463719766472"),
("2025-12-10",6830000,"0.4285714285714013605442176888"),
("2026-01-21",6800000,"0.8016384750893395660020648888"),
("2026-01-29",6880000,"0.5052331113225405372618710284"),
("2026-01-30",6900000,"0.3125134704081937793236601494"),
("2026-02-03",6900000,"0.7022077411381777544936317161"),
("2026-02-05",6800000,"0.5206391478029294274300932091"),
("2026-02-06",6870000,"0.4955223880596864335041211847"),
("2026-02-13",6840000,"0.3608207385352276772711090974"),
("2026-02-17",6820000,"0.4700854700854700854700854701"),
("2026-02-25",6920000,"0.4918032786885245901639344262"),
("2026-03-03",6770000,"0.7520215633423416714496407324"),
("2026-03-09",6690000,"0.3297755398744842301882867446"),
("2026-03-11",6730000,"0.4844697159460948850258003106"),
("2026-03-17",6710000,"0.4142739950779327317473338802"),
("2026-03-23",6550000,"0.5813148788927518029397796165"),
("2026-04-02",6530000,"0.3080264149271066802470827065"),
("2026-04-10",6790000,"0.5205479452055079752298742744"),
("2026-04-29",7090000,"0.3354257511140446049821902790"),
("2026-04-30",7140000,"0.3133047210300160253458343334"),
("2026-05-04",7170000,"0.4889837997054560670309148213"),
("2026-05-18",7360000,"0.3040181956027293404094010614"),
("2026-05-22",7470000,"0.3999999999999428571428571510"),
("2026-05-28",7540000,"0.4743290779020967020337458675"),
("2026-06-03",7550000,"0.3660377358490289782840868657"),
("2026-06-05",7460000,"0.6254738438211002833147771456"),
("2026-06-08",7420000,"0.3185714285714194693877551023"),
("2026-06-11",7270000,"0.3511235955056278405504355513"),
("2026-06-12",7370000,"0.3295346628679962013295346629"),
("2026-06-17",7490000,"0.4139687931217557028547756413"),
("2026-06-26",7350000,"0.3414351851851772815929355283"),
("2026-07-02",7440000,"0.3145539906103286384976525822"),
("2026-07-08",7400000,"0.3141525734331640400020943505"),
("2026-07-13",7510000,"0.6749024707412223667100130039"),
("2026-07-24",7430000,"0.3050237729868584450088293053"),
("2026-07-27",7370000,"0.4302718101816620812113407091"),
("2026-07-28",7420000,"0.6577736890524621075874536325"),
("2026-08-04",7680000,"0.5544328721695309195521055374"),
("2026-08-05",7700000,"0.7036114570361145703611457036"),
("2026-08-06",7680000,"0.4673049900330359991497031493"),
("2026-08-28",7710000,"0.7203755486009518342252921242"),
]

def replay_one(item):
    day,k,eff=item
    last=None
    for attempt in range(1,5):
        feed=core.Feed()
        try:
            df=base.DayFeed(feed,day,{})
            variants={name:repair.replay_variant(df,k,2,720,**cfg) for name,cfg in repair.VARIANTS.items()}
            if attempt>1: core.emit("frozen57_recovered",day=day,attempt=attempt)
            return {"day":day,"eff":float(eff),"variants":variants},None
        except Exception as exc:
            last=exc
            if "transport_failed" not in str(exc) or attempt==4: break
            core.emit("frozen57_retry",day=day,attempt=attempt,reason=str(exc)[:240])
            time.sleep(2*attempt)
    return None,{"day":day,"kind":type(last).__name__,"reason":str(last)[:240]}

def execute():
    core.STATE["stage"]="running"
    rows=[];errors=[]
    workers=max(1,min(int(os.getenv("FLAME_FROZEN57_WORKERS","3")),6))
    core.emit("frozen57_spec",entries=len(TRADES),workers=workers,variants=repair.VARIANTS,live_changed=False)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs={ex.submit(replay_one,t):t[0] for t in TRADES}
        done=0
        for fut in as_completed(futs):
            row,err=fut.result();done+=1
            if row: rows.append(row)
            if err:
                errors.append(err);core.emit("frozen57_day_error",**err)
            if done%10==0 or done==len(TRADES):
                core.emit("frozen57_progress",completed=done,total=len(TRADES),errors=len(errors),day=futs[fut])
    rows.sort(key=lambda x:x["day"])
    if errors:
        core.STATE["stage"]="failed"
        core.emit("frozen57_failed",errors=errors,completed=len(rows))
        return
    results={name:repair.summarize(rows,name) for name in repair.VARIANTS}
    for x in results.values(): core.emit("frozen57_result",**x)
    core.STATE["stage"]="complete"
    core.emit("frozen57_complete",entries=len(rows),errors=0,results=results)

if __name__=="__main__":
    if os.getenv("FLAME_FRESH_MODE")=="frozen57-exit-repair":
        threading.Thread(target=execute,daemon=True).start()
    HTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),core.Handler).serve_forever()
