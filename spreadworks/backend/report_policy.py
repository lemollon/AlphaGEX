"""Versioned, deterministic report policy. No model or execution calls.

Presentation, planning horizons and source discipline belong in code, not chat
memory. Missing evidence remains an explicit, attributable disclosure.
"""
from __future__ import annotations
import copy
import hashlib
import html
import json
import math
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
CT = ZoneInfo("America/Chicago")
POLICY_VERSION = "2026-10-08.1"
PRESENTATION = ("Today’s mission", "30-second scoreboard", "Today vs forward")
HOLDING_PERIODS = {10: "Approximately two trading weeks", 20: "Approximately one trading month"}
RULES = ("ThetaData Pro trade-time NBBO flow primary; Tradier market data/fallback; reject legacy ThetaData records","fresh BBO <=90s", "retain frozen morning expected move", "no 0DTE forward inference",
         "no model prose in canonical delivery", "no implicit mock data", "no broker orders")

def parse_clock(value):
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp.astimezone(UTC) if stamp.tzinfo else None
    except (ValueError, TypeError):
        return None

def finite_tree(value):
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(finite_tree(v) for v in value.values())
    if isinstance(value, (tuple, list)):
        return all(finite_tree(v) for v in value)
    return True

def missing(reason):
    return {"status": "unavailable", "reason": reason}

def observed(value, source, stamp, now):
    clock = parse_clock(stamp)
    if value is None or clock is None or clock > now or not finite_tree(value):
        return missing("No valid, finite, timestamped observation: " + source)
    age = (now - clock).total_seconds()
    return dict(value=value, source=source, source_timestamp=clock.isoformat(),
                age_seconds=round(age, 1), confidence="MEDIUM",
                status="live" if age <= 90 else "historical")

def normalize_item(item, now):
    if not isinstance(item, dict):
        return missing("Malformed producer observation")
    item = copy.deepcopy(item)
    if not finite_tree(item):
        return missing("Producer supplied a nonfinite numeric value; rejected")
    if re.search(r"\b(mock|fixture|hypothetical|synthetic|invented)\b", str(item.get("source", "")), re.I):
        return missing("Mock/fixture provenance is prohibited in production reports")
    from .report_contract import FLOW_SOURCE
    if "thetadata" in str(item.get("source", "")).lower() and item.get("source") != FLOW_SOURCE:
        return missing("Unverified legacy ThetaData observation rejected; only versioned trade-time NBBO flow is authorized")
    if item.get("status") == "unavailable":
        item["reason"] = item.get("reason") or "Producer supplied no verified observation"
        return item
    clock = parse_clock(item.get("source_timestamp"))
    if item.get("value") is None or not clock or clock > now:
        return missing("Missing value or invalid/future/timezone-less source clock")
    if not str(item.get("source") or "").strip() or item.get("confidence") not in ("HIGH", "MEDIUM"):
        return missing("Missing source identity or unsupported confidence")
    if item.get("status") not in ("live", "historical"):
        return missing("Invalid producer status")
    item["age_seconds"] = round((now-clock).total_seconds(), 1)
    if item["status"] == "live" and item["age_seconds"] > 90:
        item["status"] = "historical"
        item["reason"] = "LAST KNOWN: original source update retained; contextual only, not an executable live quote"
    # Nested observations keep their own clocks (macro/futures, for example).
    def nested(value):
        if isinstance(value, dict):
            if value.get("status") in ("live", "historical", "unavailable") and ("value" in value or "reason" in value):
                return normalize_item(value, now)
            return {k:nested(v) for k,v in value.items()}
        if isinstance(value, list):
            return [nested(v) for v in value]
        return value
    item["value"] = nested(item["value"])
    dependencies=[]
    def collect(value):
        if isinstance(value,dict):
            if value.get('status') in ('live','historical','unavailable') and ('value' in value or 'reason' in value):dependencies.append(value)
            for child in value.values():collect(child)
        elif isinstance(value,list):
            for child in value:collect(child)
    collect(item['value'])
    clocks=[parse_clock(d.get('source_timestamp')) for d in dependencies if parse_clock(d.get('source_timestamp'))]
    if clocks:
        clock=min([clock,*clocks]);item['source_timestamp']=clock.isoformat();item['age_seconds']=round((now-clock).total_seconds(),1)
    if any(d.get('status')=='unavailable' for d in dependencies):
        item['status']='unavailable';item['reason']='Dependent source unavailable; retained observations and reasons are shown explicitly'
    elif any(d.get('status')=='historical' for d in dependencies) or item['age_seconds']>90:
        item['status']='historical'
    return item

def normalize_blocks(blocks, now=None):
    now = now or datetime.now(UTC)
    if not isinstance(blocks, dict):
        return {}
    return {name:{field:normalize_item(item,now) for field,item in block.items()}
            if isinstance(block,dict) else {} for name,block in blocks.items()}

def policy_identity():
    from .report_contract import REQUIREMENTS
    schema = {"requirements":REQUIREMENTS,"presentation":PRESENTATION,"rules":RULES,"version":POLICY_VERSION}
    return {"version":POLICY_VERSION,"sha256":hashlib.sha256(json.dumps(schema,sort_keys=True).encode()).hexdigest()}

def add_integrity(blocks, payload, now=None):
    now = now or datetime.now(UTC)
    source_rows=[];historical=[];unavailable=[]
    for name,fields in blocks.items():
        if name == "data_integrity":continue
        for field,item in fields.items():
            key=name+"."+field
            if item.get("status")=="historical":historical.append(key)
            if item.get("status")=="unavailable":unavailable.append({"field":key,"reason":item.get("reason")})
            if item.get("source_timestamp"):
                source_rows.append({"field":key,**{k:item.get(k) for k in ("source","source_timestamp","age_seconds","confidence","status")}})
    values={"contract":policy_identity(),"source_clocks":source_rows,"coverage":payload.get("collector_coverage") or {},
        "historical_fields":historical,"unavailable_fields":unavailable,
        "producer_failures":payload.get("producer_failures") or {},
        "refresh_attempts":payload.get("refresh_attempts") or [],
        "model_prose_policy":"Canonical report is rendered from validated observations; model prose is diagnostic only.",
        "execution_scope":"Advisory and report paper simulations only; no broker orders. Empty samples have no win rate.",
        "format":{"sections":"Versioned full contract","opening":PRESENTATION,"theme":"dark",
                  "charts":{"required_panels":11,"delivered_panels":len(payload.get('chart_urls') or {}),
                            "inspection":blocks.get('visuals',{}).get('image_inspection')}}}
    blocks["data_integrity"]={k:observed(v,"Report integrity audit",now,now) for k,v in values.items()}

def business_dates(today, count):
    from .economic_events import is_market_holiday
    dates=[];day=today
    while len(dates)<count:
        day+=timedelta(days=1)
        if day.weekday()<5 and not is_market_holiday(day):dates.append(day)
    return dates

def build_strategy_blocks(blocks, core, plan, runtime, paper, morning, prior, now):
    """Forward reads require actual expiry-specific observations, never 0DTE proxies."""
    today=now.astimezone(CT).date();sessions=business_dates(today,5)
    horizons={"day_strategy":(today,today),"near_forward_strategy":(sessions[1],sessions[4]),
              "forward_strategy":(today+timedelta(days=7),today+timedelta(days=28))}
    setup_list=plan.get("setups") or []
    state_rows=[row for rows in (runtime.get("per_symbol_state") or {}).values() for row in rows if isinstance(row,dict)]
    packages=blocks["contract_packages"]["legs"]
    lifecycle=[{"setup_id":r.get("setup_id"),"state":r.get("state")} for r in state_rows]
    source="Deterministic registered strategy rules"
    for name,(lo,hi) in horizons.items():
        forward=name!="day_strategy";points={};prints={};stamps=[]
        for symbol,row in core.get("surface",{}).items():
            eligible=[]
            for point in row.get("surface_points") or []:
                try:expiry=datetime.fromisoformat(str(point.get("expiration"))).date()
                except (TypeError,ValueError):continue
                if lo<=expiry<=hi and finite_tree(point):eligible.append(point)
            if eligible and row.get("confidence") in ("HIGH","MEDIUM") and parse_clock(row.get("source_timestamp")):
                points[symbol]=eligible;stamps.append(parse_clock(row["source_timestamp"]))
        for symbol,row in core.get("flow",{}).items():
            eligible=[]
            for point in (row.get("evidence") or {}).get("concentrations") or []:
                try:expiry=datetime.fromisoformat(str(point.get("expiration"))).date()
                except (TypeError,ValueError):continue
                if lo<=expiry<=hi and finite_tree(point):eligible.append(point)
            if eligible and row.get("confidence") in ("HIGH","MEDIUM") and parse_clock(row.get("source_timestamp")):
                prints[symbol]=eligible;stamps.append(parse_clock(row["source_timestamp"]))
        pressure={}
        for symbol,rows in prints.items():
            up=sum(float(p.get("premium") or 0) for p in rows if p.get("initiation") in ("calls_bought","puts_sold"))
            down=sum(float(p.get("premium") or 0) for p in rows if p.get("initiation") in ("calls_sold","puts_bought"))
            pressure[symbol]={"upside_initiation_premium":up,"downside_initiation_premium":down,
                "read":"upside pressure" if up>down else "downside pressure" if down>up else "balanced or unclassified",
                "scope":"Observed retained strike concentrations only; not full flow totals or opening inventory"}
        evidence={"observed_expiry_points":points,"observed_expiry_prints":prints,"pressure":pressure,
                  "futures_context":blocks["futures_context"],"guardrail":"Futures context and forward options are separate evidence."}
        # Never turn a freshly computed summary into freshly observed market data.
        clock=min(stamps) if stamps else None
        thesis=pressure or (blocks["risk_on_defensive"]["verdict"].get("value") if not forward else None)
        if forward and not pressure and points:
            thesis={'direction':'INCONCLUSIVE: no verified directional trade-time flow',
                'volatility_context':{s:{'median_iv':sorted(float(p['iv']) for p in rows)[len(rows)//2],
                    'expiries':sorted({p['expiration'] for p in rows})} for s,rows in points.items()},
                'meaning':'Observed expiry-specific option pricing supplies forward risk context. It does not prove bullish or defensive positioning.'}
        matched=[]
        if packages.get("status")=="live":
            for package in packages.get("value") or []:
                legs=package.get("value") or []
                expiry=(legs[0].get("expiration") if legs else None)
                try:date=datetime.fromisoformat(str(expiry)).date()
                except (ValueError,TypeError):continue
                if (not forward and date>=today) or (forward and lo<=date<=hi):matched.append(package)
        quotes=observed(matched or None,"Qualified per-leg executable packages",packages.get("source_timestamp"),now)
        confirmed=bool(matched) and any(
            r.get("state")=="ENTRY_READY" and r.get("setup_id")==p.get("setup_id")
            and parse_clock(r.get("source_timestamp"))
            and 0<=(now-parse_clock(r["source_timestamp"])).total_seconds()<=90
            and len(r.get("confirmation_evidence") or [])>=2
            for r in state_rows for p in matched)
        status="OPEN PAPER" if any(t.get("state")=="OPEN" for t in paper.get("trade_details",[])) and not forward else "ENTRY_READY" if confirmed else "WATCH" if thesis else "PENDING EVIDENCE"
        values={"horizon":{"from":lo.isoformat(),"through":hi.isoformat(),"unit":"Trading-session dates" if name=="near_forward_strategy" else "Calendar dates"},
            "conflicts":{"market_conflicts":blocks["risk_on_defensive"].get("conflicts"),"source_limits":"Prior OI, representative flow, partial calendars; fresh quotes do not prove predictive edge."},
            "structure":"Use the matching registered, freshly qualified defined-risk package; no structure invented from directional pressure.",
            "trigger":setup_list or "No registered trigger; wait for a recorded rule and observed confirmation.",
            "invalidation":[{"setup_id":s.get("setup_id"),"invalidation":s.get("invalidation")} for s in setup_list] or "No observed setup; no inferred invalidation level.",
            "status":status,"quote_qualification":"Every selected leg requires source BBO ≤90s and valid executable side; historical chains are watch-only.",
            "risk_exit_rules":paper.get("fill_rules") or "Defined-risk package and observed exit rule required before any simulated entry.",
            "catalysts":blocks["event_calendar"]["catalysts"]}
        target={k:observed(v,source,now,now) for k,v in values.items()}
        target["thesis"]=observed(thesis,"Expiry-specific observed sentiment" if forward else "Current observed day sentiment",clock if forward else blocks["risk_on_defensive"]["verdict"].get("source_timestamp"),now)
        target["evidence"]=observed(evidence if points or prints else None,"Expiry-specific observed surface / flow",clock,now)
        target["contracts"]=quotes
        blocks[name]=target
    comparisons={"morning_baseline":{"report_id":morning.get("report_id"),"timestamp":morning.get("generated_at"),"thesis":morning.get("report_blocks",{}).get("risk_on_defensive")},
        "prior_checkpoint":{"report_id":prior.get("report_id"),"timestamp":prior.get("generated_at")},
        "current":blocks["risk_on_defensive"],"forward_options":{n:blocks[n]["thesis"] for n in ("near_forward_strategy","forward_strategy")},
        "futures_confirmation":blocks["futures_context"],"alignment":"Compare the displayed dated evidence; futures prices alone do not supply directional change or forward option sentiment.",
        "changes":{"morning":core.get("comparison") or {},"prior_hour":core.get("prior_comparison") or {},"rule":"Missing comparable baselines stay explicit; old reports are not today's morning baseline."}}
    blocks["horizon_comparison"]={k:observed(v,"Persisted report and expiry comparison",now,now) for k,v in comparisons.items()}
    for key,baseline in (("morning_baseline",morning),("prior_checkpoint",prior)):
        if not baseline:blocks["horizon_comparison"][key]=missing("No matching same-session scheduled baseline; verification reports are excluded")
    rules={"activate":"Require the registered trigger, completed-bar confirmation, held retest when specified, and fresh per-leg qualification.",
        "cancel":"Apply the recorded invalidation or reject stale/invalid quotes; never fabricate a replacement price or setup.",
        "switch":"Activate an alternative only if it is independently registered and confirmed; disagreement alone is not a reverse-trade signal.",
        "stand_aside":"Missing source/chain/confirmation, unresolved event verification, or incompatible evidence leaves the strategy conditional.",
        "existing_positions":paper.get("trade_details") or [],"reassessment":"Recheck all horizons and recorded baselines every report; maintain frozen morning expected-move bands and explicit current IV separately."}
    blocks["adaptation_rules"]={k:observed(v,source,now,now) for k,v in rules.items()}

def display(item):
    if not isinstance(item,dict):return "Unavailable"
    value=item.get("value")
    if item.get("status")=="unavailable":
        return "UNAVAILABLE — "+str(item.get("reason") or "No verified observation")+("; unverified estimate: "+json.dumps(value,ensure_ascii=False,default=str) if value is not None else "")
    text=json.dumps(value,ensure_ascii=False,default=str) if isinstance(value,(dict,list)) else str(value)
    stamp=parse_clock(item.get('source_timestamp'))
    clock=stamp.astimezone(CT).strftime('%Y-%m-%d %I:%M:%S %p CT') if stamp else str(item.get('source_timestamp'))
    age=float(item.get('age_seconds') or 0)
    age_text=f'{age:.0f}s' if age<120 else f'{age/60:.1f} min' if age<7200 else f'{age/3600:.1f} hours' if age<172800 else f'{age/86400:.1f} days'
    label='LIVE NOW' if item['status']=='live' else 'LAST KNOWN — CONTEXT ONLY ('+('MEDIUM' if age<3600 else 'LOW')+' contextual reliability)'
    return text+' ['+label+'; updated '+clock+'; age '+age_text+']'

def scoreboard(blocks):
    def get(name,field):return display(blocks.get(name,{}).get(field,{}))
    return [("Regime / trend",get("risk_on_defensive","verdict")),("Chop / breakout risk",get("range_stall","breakout_ends_chop")),
        ("Premium / volatility buying",get("premium_selling","suitability")),("Confidence / data quality","See the source clocks and explicit historical/unavailable fields below; no inferred high confidence."),
        ("Flow / gamma",get("flow","classified_coverage")+"; "+get("gamma","net_gex")),("Best underlying / structure",get("day_strategy","contracts"))]

def render_markdown(payload):
    from .report_contract import REQUIREMENTS
    blocks=payload["report_blocks"];clock=parse_clock(payload.get("generated_at"))
    title="☀️ Morning Options Sentiment" if payload.get("kind")=="morning" else "📡 Intraday Options Sentiment"
    lines=["# "+title,(clock.astimezone(CT).isoformat() if clock else "Timestamp unavailable")+" · "+str(payload.get("kind","report"))+" · "+payload["report_completeness"],
        "## 🎯 Today’s mission",display(blocks["risk_on_defensive"]["verdict"]),
        "Day and forward plans are separate. Execute no strategy from historical or unqualified quotes; use the recorded triggers and conflicts below.",
        "## 🚦 30-second scoreboard","| Decision | Current read |","|---|---|"]
    for label,read in scoreboard(blocks):lines.append("| "+label+" | "+read.replace("|","\\|").replace("\n"," ")+" |")
    lines.extend(["## Today vs forward","| Horizon | Thesis | Status |","|---|---|---|"])
    for name in ("day_strategy","near_forward_strategy","forward_strategy"):
        row=blocks[name];lines.append("| "+name.replace("_"," ")+" | "+display(row["thesis"]).replace("|","\\|")+" | "+display(row["status"]).replace("|","\\|")+" |")
    for name,fields in REQUIREMENTS.items():
        lines.append("### "+name.replace("_"," ").title())
        for field in fields:lines.append("- **"+field+"**: "+display(blocks[name][field]))
    for name,url in (payload.get("chart_urls") or {}).items():lines.append("!["+name.replace("_"," ").title()+"]("+url+")")
    lines.extend(['**BOTTOM LINE**',
        'Regime: '+display(blocks['risk_on_defensive']['verdict']),
        'Opportunity / premium: '+display(blocks['premium_selling']['suitability']),
        'Next test: recorded entry confirmation plus fresh per-leg BBO; dated context alone cannot activate a trade.'])
    return "\n\n".join(lines)

def validate_semantics(payload,now):
    errors=[];evidence=payload.get("evidence") or {};paper=evidence.get("paper") or {}
    if payload.get("mock_mode") or payload.get("kind")=="mock":errors.append("Mock reports cannot enter production delivery")
    if paper.get("closed") is not None:
        counts=paper.get("wins_losses") or {}
        flat=sum(t.get("state")=="CLOSED" and t.get("realized_pnl")==0 for t in paper.get("trade_details",[]))
        if counts.get("wins",0)+counts.get("losses",0)+flat!=paper["closed"]:errors.append("Paper wins/losses do not reconcile with closed trades")
        if paper["closed"]==0 and paper.get("win_rate") is not None:errors.append("Zero-sample paper win rate is undefined")
    for symbol,row in evidence.get("flow",{}).items():
        ev=row.get("evidence") or {};buckets=ev.get("buckets") or {}
        if not finite_tree(ev):
            errors.append(symbol+": nonfinite flow evidence")
            continue
        if buckets and ev.get("total_contracts") is not None:
            total=sum(v.get("contracts",0) for b in buckets.values() for v in b.values() if isinstance(v,dict))
            if total!=ev["total_contracts"]:errors.append(symbol+": flow contracts do not reconcile")
            premium=sum(v.get("premium",0) for b in buckets.values() for v in b.values() if isinstance(v,dict))
            if abs(premium-float(ev.get("total_premium") or 0))>.01:errors.append(symbol+": flow premium does not reconcile")
    for name,fields in (payload.get("report_blocks") or {}).items():
        for field,item in fields.items():
            if item.get("status") in ("live","historical"):
                ts=parse_clock(item.get("source_timestamp"));age=item.get("age_seconds")
                if not ts or ts>now or type(age) not in (int,float) or abs((now-ts).total_seconds()-age)>3:
                    errors.append(name+"."+field+": source clock/age mismatch")
    return errors

def render_opening_html(payload):
    blocks=payload.get("report_blocks") or {};escape=html.escape
    rows="".join("<tr><th>"+escape(k)+"</th><td>"+escape(v)+"</td></tr>" for k,v in scoreboard(blocks))
    out="<h2>🎯 Today’s mission</h2><p>"+escape(display(blocks.get("risk_on_defensive",{}).get("verdict",{})))+"</p><h2>🚦 30-second scoreboard</h2><table>"+rows+"</table><h2>Today vs forward</h2><table>"
    for name in ("day_strategy","near_forward_strategy","forward_strategy"):
        row=blocks.get(name) or {};out+="<tr><th>"+escape(name.replace("_"," "))+"</th><td>"+escape(display(row.get("thesis",{})))+"<br>"+escape(display(row.get("status",{})))+"</td></tr>"
    return out+"</table>"
