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
from .report_contract import LIVE_MAX_AGE_SECONDS

UTC = timezone.utc
CT = ZoneInfo("America/Chicago")
POLICY_VERSION = "2026-10-08.3"
PRESENTATION = ("Today’s mission", "30-second scoreboard", "Today vs forward",
                "Market story", "Edge board", "Biggest traps", "If/then day plan")
HOLDING_PERIODS = {10: "Approximately two trading weeks", 20: "Approximately one trading month"}
RULES = ("ThetaData Pro trade-time NBBO flow primary; Tradier market data/fallback; reject legacy ThetaData records","fresh BBO <=90s", "retain frozen morning expected move", "no 0DTE forward inference",
         "no model prose in canonical delivery", "no implicit mock data", "no broker orders")

def parse_clock(value):
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp.astimezone(UTC) if stamp.tzinfo else None
    except (ValueError, TypeError):
        return None

def ct_str(iso_value):
    """Render a raw ISO timestamp string in Central Time, matching display()'s house
    convention. For the handful of spots (horizon_comparison's cross-report timestamps)
    that embed a raw timestamp as a plain dict value instead of going through observed()/
    display() — those rendered the bare UTC ISO string unconverted, inconsistent with every
    other date on the page and read as a different, unlabeled hour to a Central-Time reader."""
    clock = parse_clock(iso_value)
    return clock.astimezone(CT).strftime("%Y-%m-%d %I:%M:%S %p CT") if clock else str(iso_value or "")

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

def fmt_number(v):
    """Magnitude-tiered decimal precision -- a raw float repr like 0.15139485927028395
    (median_iv) or -0.04018785705263146 (net_gex_b) is noise past a few significant decimals,
    not information. Leron, 2026-10-10: "There is to many decimal places in the number it's
    need to be rounded." Matches full_options_report._fmt_primitive's convention so a number
    reads the same whether it came through the detailed per-field sections or the opening
    summary / markdown path."""
    a = abs(v)
    if a >= 1e6:
        return str(v)
    decimals = 0 if a >= 1000 else 2 if a >= 1 else 4
    return f"{v:,.{decimals}f}"

_SYM_KEY_RE = re.compile(r"^[A-Z]{1,5}$")
# Matches the bucket suffix anywhere a key ENDS in it (search, not match on the whole key) —
# real field names carry a prefix before the bucket ("term_1_5dte", "iv_6_20dte" in Surface),
# not just the bare bucket ("1_5dte" in Gamma/Flow/Control). Re-checked live 2026-10-09: the
# first fix only handled the bare form; every "term "/"iv " prefixed field still read "1 5dte".
_DTE_BUCKET_RE = re.compile(r"(\d+)(?:_(\d+))?dte$", re.IGNORECASE)

def field_label(key):
    """Human label for a field/bucket name. A blind `_` -> ` ` replace turns a DTE bucket
    key like "1_5dte" (or prefixed, "term_1_5dte") into the typo-looking "1 5dte" / "term 1
    5dte" instead of "1-5 DTE" / "term 1-5 DTE" — special-case that shape (shared by kv rows,
    field headers, chart tick labels) before the generic underscore replace."""
    key = str(key)
    m = _DTE_BUCKET_RE.search(key)
    if m and (m.start() == 0 or key[m.start() - 1] == "_"):
        lo, hi = m.groups()
        bucket = f"{lo}-{hi} DTE" if hi else f"{lo} DTE"
        prefix = key[:m.start()].rstrip("_").replace("_", " ")
        return f"{prefix} {bucket}" if prefix else bucket
    return key.replace("_", " ")

def plain_value(v, depth=0):
    """Plain-text (markdown/Discord-safe, no HTML) rendering of a field value for display().

    A raw json.dumps() of a per-symbol dict ({"SPY": "PREMIUM_RICH", "QQQ": ...}) is not
    readable at a glance; render it as "SPY: PREMIUM_RICH; QQQ: ..." instead. Live bug, found
    2026-10-11 in a user-reported screenshot: shapes too irregular for the branches below (a
    dict with >10 keys like breadth's 18 fields, or a long flat list like holdings.symbols'
    503 tickers) used to fall back to raw json.dumps() of the whole tree, which rendered as
    literal braces/quotes bleeding straight into the "Section summary" UI text instead of
    prose. There is no raw-JSON fallback left anywhere below — every branch bottoms out in
    readable "key value" pairs or a short "[N items]"/"[N fields]" placeholder, so this can
    never again dump code onto the page.
    """
    if v is None:
        return "none"
    if isinstance(v, dict):
        if v and all(isinstance(k, str) and _SYM_KEY_RE.match(k) for k in v):
            return "; ".join(f"{k}: {plain_value(sv, depth + 1)}" for k, sv in v.items())
        if not v:
            return "none"
        # Any width still renders every field as a "key value" pair — real recursion, real
        # values, never a raw dump. No depth cutoff here: report data is always a finite,
        # acyclic tree built by producer code, never arbitrary/cyclic input, and a hard depth
        # gate at a low number (found live 2026-10-11) was collapsing small, perfectly normal
        # nested values -- a 3-field payoff dict with a 1-item breakeven list -- into a useless
        # "[1 items]" placeholder several levels in. The real protection against an actually
        # unbounded structure (breadth's 503-symbol holdings list) is the per-list item cap
        # below, not depth.
        return ", ".join(f"{field_label(k)} {plain_value(vv, depth + 1)}" for k, vv in v.items())
    if isinstance(v, list):
        if not v:
            return "none"
        if all(not isinstance(x, (dict, list)) for x in v):
            shown = v[:12]
            text = ", ".join(plain_value(x, depth + 1) for x in shown)
            if len(v) > 12:
                text += f" (+{len(v) - 12} more)"
            return text
        shown = v[:5]
        text = "; ".join(plain_value(x, depth + 1) for x in shown)
        if len(v) > 5:
            text += f" (+{len(v) - 5} more)"
        return text
    if isinstance(v, str):
        # Shape-based, not key-name-based: ct_str() only converts strings that actually parse
        # as a timezone-aware instant (a bare calendar date like an option expiration has no
        # tzinfo and passes through unchanged) — this subsumes the former per-key-name check,
        # which kept missing new field names (heartbeat, alert_time, requested_at, ...).
        return ct_str(v)
    if isinstance(v, float):
        return fmt_number(v)
    return str(v)

def observed(value, source, stamp, now):
    clock = parse_clock(stamp)
    if value is None or clock is None or clock > now or not finite_tree(value):
        return missing("No valid, finite, timestamped observation: " + source)
    age = (now - clock).total_seconds()
    return dict(value=value, source=source, source_timestamp=clock.isoformat(),
                age_seconds=round(age, 1), confidence="MEDIUM",
                status="live" if age <= LIVE_MAX_AGE_SECONDS else "historical")

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
        # futures_context is NOT embedded here (it used to be, verbatim, in all three strategy
        # sections): it has its own dedicated section, so duplicating it tripled page weight for
        # zero new information, and because futures_context.basis is permanently unavailable by
        # design (same-time futures-vs-cash basis cannot be computed), embedding it meant this
        # evidence field could never report live/historical no matter how complete its own real
        # data was — normalize_item() marks a field unavailable if ANY nested dependency is.
        evidence={"observed_expiry_points":points,"observed_expiry_prints":prints,"pressure":pressure,
                  "guardrail":"See the Futures Context section for overnight ES/NQ positioning; forward options evidence here is priced, not futures-derived."}
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
        # Same full catalyst list used to repeat identically across all three horizons (CPI on
        # the 14th shown under "today" when today is the 8th). Narrow to this section's own
        # [lo,hi] window so each horizon only carries the events that actually fall inside it.
        raw_catalysts=blocks["event_calendar"]["catalysts"];cv=raw_catalysts.get("value")
        if isinstance(cv,list):
            def _in_window(c,lo=lo,hi=hi):
                try:d=datetime.fromisoformat(str(c.get("datetime"))).date()
                except (TypeError,ValueError):return False
                return lo<=d<=hi
            catalysts_for_horizon=dict(raw_catalysts,value=[c for c in cv if _in_window(c)])
        else:catalysts_for_horizon=raw_catalysts
        values={"horizon":{"from":lo.isoformat(),"through":hi.isoformat(),"unit":"Trading-session dates" if name=="near_forward_strategy" else "Calendar dates"},
            "conflicts":{"market_conflicts":blocks["risk_on_defensive"].get("conflicts"),"source_limits":"Prior OI, representative flow, partial calendars; fresh quotes do not prove predictive edge."},
            "structure":"Use the matching registered, freshly qualified defined-risk package; no structure invented from directional pressure.",
            "trigger":setup_list or "No registered trigger; wait for a recorded rule and observed confirmation.",
            "invalidation":[{"setup_id":s.get("setup_id"),"invalidation":s.get("invalidation")} for s in setup_list] or "No observed setup; no inferred invalidation level.",
            "status":status,"quote_qualification":"Every selected leg requires source BBO ≤90s and valid executable side; historical chains are watch-only.",
            # Same fixed text regardless of horizon (it's one global fill/target/stop rule, not
            # day/near/forward-specific) — used to repeat the full ~400-char paragraph 3x across
            # these sections plus a 4th time in Position Management, which is its canonical home.
            "risk_exit_rules":("Same fixed rule for every horizon — see Position Management for the full fill/target/stop text."
                               if paper.get("fill_rules") else "Defined-risk package and observed exit rule required before any simulated entry.")}
        target={k:observed(v,source,now,now) for k,v in values.items()}
        target["thesis"]=observed(thesis,"Expiry-specific observed sentiment" if forward else "Current observed day sentiment",clock if forward else blocks["risk_on_defensive"]["verdict"].get("source_timestamp"),now)
        target["evidence"]=observed(evidence if points or prints else None,"Expiry-specific observed surface / flow",clock,now)
        target["contracts"]=quotes
        # catalysts_for_horizon is already a full observed()-style dict (it's a narrowed copy of
        # blocks["event_calendar"]["catalysts"], itself already observed()-wrapped) — assigning it
        # directly here, like thesis/evidence/contracts above, avoids re-wrapping an already-wrapped
        # dict through the generic values-loop (which produced doubled status/source/timestamp
        # metadata nested inside its own "value").
        target["catalysts"]=catalysts_for_horizon
        blocks[name]=target
    comparisons={"morning_baseline":{"report_id":morning.get("report_id"),"timestamp":ct_str(morning.get("generated_at")) if morning.get("generated_at") else None,"thesis":morning.get("report_blocks",{}).get("risk_on_defensive")},
        "prior_checkpoint":{"report_id":prior.get("report_id"),"timestamp":ct_str(prior.get("generated_at")) if prior.get("generated_at") else None},
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

def _value_text(item):
    """Plain-text rendering of an item's value/unavailable-reason only, no status/provenance
    suffix. Shared by display() (which appends the bracketed "[LIVE NOW; updated ...]" suffix
    for Discord/markdown) and market_story_html (which shows the same reliability info as a
    separate pill a few lines above, so repeating the bracket text in the paragraph would
    duplicate it)."""
    if not isinstance(item,dict):return "Unavailable"
    value=item.get("value")
    if item.get("status")=="unavailable":
        return "UNAVAILABLE — "+str(item.get("reason") or "No verified observation")+("; unverified estimate: "+plain_value(value) if value is not None else "")
    # Live bug, found 2026-10-10 in the markdown/Discord delivery path: a scalar string VALUE
    # (prior_hour_timestamp, heartbeat) skipped plain_value()/ct_str() entirely via bare str(),
    # leaking raw UTC "+00:00" even though the SAME line's own provenance suffix below already
    # converts source_timestamp to CT -- the value and its own metadata showed different, both
    # unlabeled, times.
    return plain_value(value) if isinstance(value,(dict,list)) else (ct_str(value) if isinstance(value,str) else fmt_number(value) if isinstance(value,float) else str(value))

def display(item, compact=False):
    """compact=True drops the per-value "[updated ...; age ...]" provenance suffix, keeping
    only a short reliability tag. Full display() repeats that suffix verbatim on every cell
    of a row (edge_board, scoreboard), which is correct for a standalone field but turns a
    "30-second scoreboard" into a wall of identical timestamps when 3 cells share one source.
    The reliability tag itself (LIVE vs LAST KNOWN) is kept even in compact mode — this report
    never hides staleness, it just stops repeating the same clock three times in one row."""
    if not isinstance(item,dict):return "Unavailable"
    if item.get("status")=="unavailable":return _value_text(item)
    text=_value_text(item)
    age=float(item.get('age_seconds') or 0)
    label='LIVE NOW' if item['status']=='live' else 'LAST KNOWN — CONTEXT ONLY ('+('MEDIUM' if age<3600 else 'LOW')+' contextual reliability)'
    if compact:
        return text+' ['+label+']'
    stamp=parse_clock(item.get('source_timestamp'))
    clock=stamp.astimezone(CT).strftime('%Y-%m-%d %I:%M:%S %p CT') if stamp else str(item.get('source_timestamp'))
    age_text=f'{age:.0f}s' if age<120 else f'{age/60:.1f} min' if age<7200 else f'{age/3600:.1f} hours' if age<172800 else f'{age/86400:.1f} days'
    return text+' ['+label+'; updated '+clock+'; age '+age_text+']'

def scoreboard(blocks):
    def get(name,field):return display(blocks.get(name,{}).get(field,{}),compact=True)
    return [("Regime / trend",get("risk_on_defensive","verdict")),("Chop / breakout risk",get("range_stall","breakout_ends_chop")),
        ("Premium / volatility buying",get("premium_selling","suitability")),("Confidence / data quality","See the source clocks and explicit historical/unavailable fields below; no inferred high confidence."),
        ("Flow / gamma",get("flow","classified_coverage")+"; "+get("gamma","net_gex")),("Best underlying / structure",get("day_strategy","contracts"))]

SECTION_SUMMARY_SECTIONS = (
    "risk_on_defensive", "market_control", "gamma", "flow", "premium_selling",
    "day_strategy", "near_forward_strategy", "forward_strategy",
    "expected_move", "smile", "surface", "forward_strikes",
    "range_stall", "breadth", "profile", "sector_credit", "macro", "futures_context", "event_calendar",
    # Leron, 2026-10-10: "make the read detailed and fun to read... each section should flow
    # into each [other]" -- every section on the page gets this treatment now, not just the
    # 19 originally judged "decision-relevant." The ones below are honestly bookkeeping/audit,
    # so their line says that plainly instead of inventing a trading signal that isn't there.
    "contract_packages", "entry_watches", "candidate_analysis", "position_management",
    "trigger_accountability", "paper_scorecard", "scanner", "event_study", "engine_consensus",
    "morning_comparison", "horizon_comparison", "adaptation_rules", "visuals", "data_integrity",
)

def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)

def _narrative_risk_on_defensive(block):
    verdict_item = block.get("verdict") or {}
    verdict = verdict_item.get("value")
    if not isinstance(verdict, str) or verdict_item.get("status") == "unavailable":
        return None
    mood = ("leaning bullish" if "Risk-on" in verdict else "leaning defensive" if "Defensive" in verdict
            else "split, no clean lean")
    sentence = f"Price is {mood}."
    evidence = (block.get("evidence") or {}).get("value") or {}
    returns = evidence.get("returns") if isinstance(evidence.get("returns"), dict) else {}
    ranked = sorted(((s, v) for s, v in returns.items() if _num(v)), key=lambda kv: kv[1], reverse=True)
    if ranked:
        top_sym, top_val = ranked[0]
        bottom_sym, bottom_val = ranked[-1]
        if top_sym != bottom_sym:
            sentence += f" {top_sym} leads at {top_val:+.2f}%, {bottom_sym} trails at {bottom_val:+.2f}%."
        else:
            sentence += f" {top_sym} is {'up' if top_val >= 0 else 'down'} {abs(top_val):.2f}% today."
    breadth = evidence.get("breadth")
    if isinstance(breadth, dict):
        adv, dec = breadth.get("advances"), breadth.get("declines")
        if _num(adv) and _num(dec) and (adv + dec) > 0:
            if adv > dec * 1.3:
                sentence += f" Breadth backs it up — {int(adv)} advancers to {int(dec)} decliners."
            elif dec > adv * 1.3:
                sentence += f" Breadth pushes back — only {int(adv)} advancers against {int(dec)} decliners."
            else:
                sentence += f" Breadth is a near dead heat, {int(adv)} up to {int(dec)} down."
    return sentence

def _narrative_gamma(block):
    net_item = block.get("net_gex") or {}
    net_val = net_item.get("value")
    if not isinstance(net_val, dict) or net_item.get("status") == "unavailable":
        return None
    walls_val = (block.get("walls") or {}).get("value") or {}
    flip_val = (block.get("flip") or {}).get("value") or {}
    bits = []
    for sym in ("SPY", "QQQ"):
        row = net_val.get(sym)
        gex = row.get("net_gex_b") if isinstance(row, dict) else None
        if not _num(gex):
            continue
        regime = ("dealers are long gamma and should dampen swings" if gex > 0
                  else "dealers are short gamma and can accelerate moves" if gex < 0
                  else "gamma is flat — no dealer cushion either way")
        sentence = f"{sym} net GEX sits at {gex:+.2f}B — {regime}."
        wall_row = (walls_val.get(sym) or {}).get("walls") or {}
        top_call = wall_row.get("top_call") or []
        top_put = wall_row.get("top_put") or []
        call_strike = top_call[0].get("strike") if top_call and isinstance(top_call[0], dict) else None
        put_strike = top_put[0].get("strike") if top_put and isinstance(top_put[0], dict) else None
        if _num(call_strike) and _num(put_strike):
            sentence += f" Call sellers are dug in hardest at {call_strike:g}, put sellers at {put_strike:g}."
        flip_row = flip_val.get(sym)
        flip = flip_row.get("gamma_flip") if isinstance(flip_row, dict) else None
        if _num(flip):
            sentence += f" Flip sits at {flip:g}."
        bits.append(sentence)
    return " ".join(bits) if bits else None

def _narrative_market_control(block):
    side_item = block.get("control_side") or {}
    sides = side_item.get("value")
    if not isinstance(sides, dict) or side_item.get("status") == "unavailable":
        return None
    conf_val = (block.get("control_confidence") or {}).get("value") or {}
    outlook_val = (block.get("forward_control_outlook") or {}).get("value") or {}
    label_word = {"call_sellers": "call sellers", "put_sellers": "put sellers",
                  "mixed": "a mixed crowd", "inconclusive": "no clear side"}
    conf_word = {"HIGH": "high-confidence", "MEDIUM": "medium-confidence", "LOW_FORCES_INCONCLUSIVE": "thin"}
    bits = []
    for sym in ("SPY", "QQQ"):
        buckets = sides.get(sym)
        if not isinstance(buckets, dict) or not buckets:
            continue
        lead_side = buckets.get("0dte") or next(iter(buckets.values()), None)
        word = label_word.get(lead_side, str(lead_side).replace("_", " "))
        conf = conf_val.get(sym) if isinstance(conf_val, dict) else None
        conf_bit = conf_word.get((conf or {}).get("label")) if isinstance(conf, dict) else None
        sentence = f"{sym} is being run by {word} today" + (f", a {conf_bit} read" if conf_bit else "") + "."
        out = outlook_val.get(sym) if isinstance(outlook_val, dict) else None
        if isinstance(out, dict):
            if out.get("outlook") == "persists":
                sentence += " Forward flow agrees — this looks like more than a one-day lean."
            elif out.get("outlook") == "flips":
                sentence += " Forward flow disagrees — don't assume this holds past today."
        bits.append(sentence)
    return " ".join(bits) if bits else None

def _narrative_premium_selling(block):
    suit_item = block.get("suitability") or {}
    suit_val = suit_item.get("value")
    if not isinstance(suit_val, dict) or suit_item.get("status") == "unavailable":
        return None
    meaning_val = (block.get("iv_rv_meaning_today") or {}).get("value") or {}
    forward_val = (block.get("forward_implications") or {}).get("value") or {}
    label_word = {"PREMIUM_RICH": "premium is rich — IV is outrunning realized vol, a seller's edge",
                  "PREMIUM_CHEAP": "premium is cheap — IV isn't paying you enough for the risk",
                  "PREMIUM_FAIR": "premium is fairly priced — no edge either way"}
    bits = []
    for sym in ("SPY", "QQQ"):
        suit = suit_val.get(sym)
        if not isinstance(suit, str):
            continue
        sentence = f"{sym}: " + label_word.get(suit, suit.replace("_", " ").lower())
        meaning = meaning_val.get(sym) if isinstance(meaning_val, dict) else None
        ratio = (meaning or {}).get("ratio")
        if _num(ratio):
            sentence += f" (IV/realized ratio {ratio:.2f})"
        sentence += "."
        forward = forward_val.get(sym) if isinstance(forward_val, dict) else None
        if isinstance(forward, str) and forward:
            sentence += " " + forward
        bits.append(sentence)
    return " ".join(bits) if bits else None

def _narrative_flow(block):
    conf_val = (block.get("price_vix_confirmation") or {}).get("value")
    cb = (block.get("calls_bought") or {}).get("value") or {}
    cs = (block.get("calls_sold") or {}).get("value") or {}
    pb = (block.get("puts_bought") or {}).get("value") or {}
    ps = (block.get("puts_sold") or {}).get("value") or {}
    bits = []
    for sym in ("SPY", "QQQ"):
        totals = {}
        for label, src in (("calls bought", cb), ("calls sold", cs), ("puts bought", pb), ("puts sold", ps)):
            row = src.get(sym) if isinstance(src, dict) else None
            if isinstance(row, dict):
                total = sum(v for v in row.values() if _num(v))
                if total:
                    totals[label] = total
        if not totals:
            continue
        leader = max(totals, key=totals.get)
        sentence = f"{sym} flow is dominated by {leader} — ${totals[leader]:,.0f} in premium."
        conf = conf_val.get(sym) if isinstance(conf_val, dict) else None
        if isinstance(conf, dict):
            read = conf.get("read")
            if read == "confirms":
                sentence += " Price is moving the same way the flow is paying for — this one's clean."
            elif read == "conflicts":
                sentence += " Price is fighting the flow right now — a yellow flag, not a trade."
        bits.append(sentence)
    return " ".join(bits) if bits else None

def _narrative_expected_move(block):
    dollars_item = block.get("dollars") or {}
    dollars_val = dollars_item.get("value")
    if not isinstance(dollars_val, dict) or dollars_item.get("status") == "unavailable":
        return None
    pct_val = (block.get("percent") or {}).get("value") or {}
    lower_val = (block.get("lower") or {}).get("value") or {}
    upper_val = (block.get("upper") or {}).get("value") or {}
    budget_val = (block.get("budget_used") or {}).get("value") or {}
    bits = []
    for sym in ("SPY", "QQQ"):
        d = dollars_val.get(sym)
        dollars = d.get("expected_move_dollars_1d") if isinstance(d, dict) else None
        if not _num(dollars):
            continue
        pct = ((pct_val.get(sym) or {}) if isinstance(pct_val, dict) else {}).get("expected_move_pct_1d")
        lo = ((lower_val.get(sym) or {}) if isinstance(lower_val, dict) else {}).get("expected_move_low")
        hi = ((upper_val.get(sym) or {}) if isinstance(upper_val, dict) else {}).get("expected_move_high")
        sentence = f"{sym}'s one-day expected move is ${dollars:.2f}"
        if _num(pct):
            sentence += f" ({pct:.2f}%)"
        if _num(lo) and _num(hi):
            sentence += f", pricing a {lo:.2f}-{hi:.2f} band"
        sentence += "."
        budget = budget_val.get(sym) if isinstance(budget_val, dict) else None
        frac = (budget or {}).get("absolute_move_fraction")
        if _num(frac):
            used_pct = frac * 100
            if used_pct >= 90:
                sentence += f" It's already burned {used_pct:.0f}% of this morning's frozen move — the room left is thin."
            elif used_pct <= 25:
                sentence += f" Only {used_pct:.0f}% of this morning's frozen move is used — plenty of room either way."
            else:
                sentence += f" {used_pct:.0f}% of this morning's frozen move is used so far."
        bits.append(sentence)
    return " ".join(bits) if bits else None

def _narrative_smile(block):
    atm_item = block.get("atm_iv") or {}
    atm_val = atm_item.get("value")
    if not isinstance(atm_val, dict) or atm_item.get("status") == "unavailable":
        return None
    put_val = (block.get("put_25d_iv") or {}).get("value") or {}
    call_val = (block.get("call_25d_iv") or {}).get("value") or {}
    bits = []
    for sym in ("SPY", "QQQ"):
        atm = (atm_val.get(sym) or {}).get("atm_iv") if isinstance(atm_val.get(sym), dict) else None
        if not _num(atm):
            continue
        put_iv = ((put_val.get(sym) or {}) if isinstance(put_val, dict) else {}).get("put_25d_iv")
        call_iv = ((call_val.get(sym) or {}) if isinstance(call_val, dict) else {}).get("call_25d_iv")
        sentence = f"{sym}'s skew is pricing ATM IV at {atm*100:.1f}%"
        if _num(put_iv) and _num(call_iv):
            skew = put_iv - call_iv
            lean = ("puts are bid harder than calls — the market's paying up for downside protection" if skew > 0.01
                    else "calls are bid harder than puts — unusual, the market's paying up for upside" if skew < -0.01
                    else "puts and calls are priced about evenly")
            sentence += f"; {lean} ({put_iv*100:.1f}% put vs {call_iv*100:.1f}% call at 25-delta)"
        sentence += "."
        bits.append(sentence)
    return " ".join(bits) if bits else None

def _narrative_surface(block):
    atm_item = block.get("atm_iv") or {}
    atm_val = atm_item.get("value")
    if not isinstance(atm_val, dict) or atm_item.get("status") == "unavailable":
        return None
    term0 = (block.get("term_0dte") or {}).get("value") or {}
    term_far = (block.get("term_21plus") or {}).get("value") or {}
    ivrv_val = (block.get("iv_vs_realized") or {}).get("value") or {}
    bits = []
    for sym in ("SPY", "QQQ"):
        atm = (atm_val.get(sym) or {}).get("atm_iv") if isinstance(atm_val.get(sym), dict) else None
        if not _num(atm):
            continue
        near = ((term0.get(sym) or {}) if isinstance(term0, dict) else {}).get("iv_0dte")
        far = ((term_far.get(sym) or {}) if isinstance(term_far, dict) else {}).get("iv_21_365dte")
        sentence = f"{sym}'s vol surface: ATM IV {atm*100:.1f}%"
        if _num(near) and _num(far) and far > 0:
            shape = ("inverted — 0DTE is pricing hotter than the back of the curve, classic event/fear pattern" if near > far * 1.15
                     else "upward-sloping — normal contango, no near-term fear priced in" if near < far * 0.9
                     else "flat across expiries")
            sentence += f"; the term structure is {shape}"
        row = ivrv_val.get(sym) if isinstance(ivrv_val, dict) else None
        iv, rv = (row or {}).get("atm_iv"), (row or {}).get("realized_vol_60m")
        if _num(iv) and _num(rv) and rv > 0:
            gap = (iv - rv) * 100
            sentence += f". IV is running {abs(gap):.1f} points {'above' if gap > 0 else 'below'} realized vol"
        sentence += "."
        bits.append(sentence)
    return " ".join(bits) if bits else None

def _narrative_breadth(block):
    ad_item = block.get("advance_decline") or {}
    ad = ad_item.get("value")
    if not isinstance(ad, dict) or ad_item.get("status") == "unavailable":
        return None
    adv, dec = ad.get("advances"), ad.get("declines")
    if not _num(adv) or not _num(dec):
        return None
    total = adv + dec
    pct_up = (adv / total * 100) if total else None
    verdict = ("broad and convincing" if pct_up is not None and pct_up >= 65
               else "thin and unconvincing" if pct_up is not None and pct_up <= 40
               else "roughly balanced")
    sentence = f"{int(adv)} stocks are advancing against {int(dec)} declining — participation is {verdict}."
    uv = (block.get("up_down_volume") or {}).get("value") or {}
    ratio = uv.get("up_down_volume_ratio") if isinstance(uv, dict) else None
    if _num(ratio):
        sentence += f" Up-volume is running {ratio:.2f}x down-volume."
    nh = (block.get("new_highs_lows") or {}).get("value") or {}
    highs, lows = (nh or {}).get("new_52w_highs"), (nh or {}).get("new_52w_lows")
    if _num(highs) and _num(lows):
        if highs > lows * 2 and highs > 5:
            sentence += f" New 52-week highs ({int(highs)}) are swamping new lows ({int(lows)}) — a real bullish tell."
        elif lows > highs * 2 and lows > 5:
            sentence += f" New 52-week lows ({int(lows)}) are swamping new highs ({int(highs)}) — a real bearish tell."
    return sentence

def _narrative_sector_credit(block):
    rel_item = block.get("relative_returns") or {}
    rel = rel_item.get("value")
    if not isinstance(rel, dict) or rel_item.get("status") == "unavailable" or not rel:
        return None
    ranked = sorted(((s, v) for s, v in rel.items() if _num(v)), key=lambda kv: kv[1], reverse=True)
    if not ranked:
        return None
    top, bottom = ranked[:3], ranked[-3:]
    sentence = ("Leading today: " + ", ".join(f"{s} {v:+.2f}%" for s, v in top)
                + ". Lagging: " + ", ".join(f"{s} {v:+.2f}%" for s, v in reversed(bottom)) + ".")
    credit = (block.get("credit_confirmation") or {}).get("value") or {}
    hyg = credit.get("HYG") if isinstance(credit, dict) else None
    if _num(hyg) and abs(hyg) > 0.02:
        market_up = ranked[0][1] > 0
        if (hyg > 0) == market_up:
            sentence += " Credit (HYG) is backing up the move."
        else:
            sentence += " Credit (HYG) isn't confirming — worth a second look before sizing up."
    return sentence

def _narrative_morning_comparison(block):
    regime_item = block.get("regime_shift") or {}
    regime = regime_item.get("value")
    if not isinstance(regime, dict) or regime_item.get("status") == "unavailable" or not regime:
        return None
    bits = []
    for sym in ("SPY", "QQQ"):
        row = regime.get(sym)
        if not isinstance(row, dict):
            continue
        status = row.get("status")
        if status == "FIRST_REPORT":
            bits.append(f"{sym}: first read of the day — nothing to compare against yet.")
        elif status == "HOLDING":
            bits.append(f"{sym} is holding the same read as this morning — no reason to tear up the plan.")
        elif status == "CHANGED":
            changed = row.get("changed") or []
            if changed:
                bits.append(f"{sym} has moved since this morning: {'; '.join(changed)}. "
                             "This is exactly the kind of shift that should make you revisit the plan intraday.")
            else:
                bits.append(f"{sym}'s setup has shifted since this morning.")
    return " ".join(bits) if bits else None

def _narrative_strategy(block):
    status_item = block.get("status") or {}
    status = status_item.get("value")
    if not isinstance(status, str):
        return None
    status_phrase = {"OPEN PAPER": "a paper position is already open on this one",
                      "ENTRY_READY": "the setup just confirmed — every box is checked",
                      "WATCH": "still a watch item, nothing confirmed yet",
                      "PENDING EVIDENCE": "not enough evidence yet to even call this a watch"}.get(status, status)
    sentence = f"Status: {status_phrase}."
    thesis = (block.get("thesis") or {}).get("value")
    if isinstance(thesis, dict):
        if "direction" in thesis:
            direction = thesis.get("direction")
            if isinstance(direction, str):
                sentence += f" Thesis: {direction}."
        else:
            leaning = [(s, r) for s, r in thesis.items()
                       if isinstance(r, dict) and r.get("read") not in (None, "balanced or unclassified")]
            if leaning:
                sentence += " " + "; ".join(f"{s} flow leans {r['read']}" for s, r in leaning) + "."
    elif isinstance(thesis, str):
        mood = ("leaning bullish" if "Risk-on" in thesis else "leaning defensive" if "Defensive" in thesis
                else "mixed, no clean lean")
        sentence += f" Today's price read is {mood}."
    trigger = (block.get("trigger") or {}).get("value")
    if isinstance(trigger, list) and trigger:
        sentence += f" {len(trigger)} registered setup{'s' if len(trigger) != 1 else ''} on watch."
    return sentence

def _narrative_contract_packages(block):
    legs_item = block.get("legs") or {}
    legs_rows = legs_item.get("value")
    if not isinstance(legs_rows, list) or not legs_rows or legs_item.get("status") == "unavailable":
        return None
    risk_rows = {r.get("setup_id"): r.get("value") for r in (block.get("max_risk_reward") or {}).get("value") or []
                 if isinstance(r, dict)}
    debit_rows = {r.get("setup_id"): r.get("value") for r in (block.get("debit_credit") or {}).get("value") or []
                  if isinstance(r, dict)}
    bits = []
    for row in legs_rows[:3]:
        if not isinstance(row, dict):
            continue
        sid, strategy = row.get("setup_id"), row.get("strategy") or "Structure"
        legs = row.get("value") or []
        strikes = sorted({l.get("strike") for l in legs if isinstance(l, dict) and _num(l.get("strike"))})
        sentence = str(strategy).replace("_", " ").title()
        if strikes:
            sentence += " at " + "/".join(f"{k:g}" for k in strikes)
        dc = debit_rows.get(sid) or {}
        credit, debit = dc.get("natural_credit"), dc.get("natural_debit")
        if _num(credit) and credit:
            sentence += f" — collects ${credit:.2f}"
        elif _num(debit) and debit:
            sentence += f" — costs ${debit:.2f}"
        payoff = risk_rows.get(sid) or {}
        max_risk, max_reward = payoff.get("max_risk"), payoff.get("max_reward")
        if _num(max_risk) and max_risk:
            if max_reward == "unlimited":
                sentence += f", risking ${max_risk:.0f} with unlimited upside"
            elif _num(max_reward):
                sentence += f", risking ${max_risk:.0f} to make ${max_reward:.0f}"
        sentence += " — qualified and live right now."
        bits.append(sentence)
    return " ".join(bits) if bits else None

def _narrative_entry_watches(block):
    trigger_item = block.get("trigger") or {}
    rows = trigger_item.get("value")
    if not isinstance(rows, list) or not rows:
        return None
    state_word = {"ENTRY_READY": "just confirmed and ready", "WATCH": "still on watch, not confirmed yet"}
    bits = []
    for row in rows[:3]:
        if not isinstance(row, dict):
            continue
        sym, sid, state = row.get("symbol"), row.get("setup_id"), row.get("state")
        word = state_word.get(state, (str(state).replace("_", " ").lower() if state else "status unclear"))
        bits.append(f"{sym} setup {sid} is {word}.")
    return " ".join(bits) if bits else None

_NARRATIVE_BUILDERS = {
    "risk_on_defensive": _narrative_risk_on_defensive,
    "gamma": _narrative_gamma,
    "market_control": _narrative_market_control,
    "premium_selling": _narrative_premium_selling,
    "flow": _narrative_flow,
    "expected_move": _narrative_expected_move,
    "smile": _narrative_smile,
    "surface": _narrative_surface,
    "breadth": _narrative_breadth,
    "sector_credit": _narrative_sector_credit,
    "morning_comparison": _narrative_morning_comparison,
    "day_strategy": _narrative_strategy,
    "near_forward_strategy": _narrative_strategy,
    "forward_strategy": _narrative_strategy,
    "contract_packages": _narrative_contract_packages,
    "entry_watches": _narrative_entry_watches,
}

def _generic_narrative_summary(block):
    parts = []
    for field, field_item in block.items():
        if len(parts) >= 3:
            break
        if not isinstance(field_item, dict) or field_item.get("status") == "unavailable":
            continue
        value = field_item.get("value")
        # A raw chart URL/data-URI is never a meaningful recap line (it's the same image
        # already embedded on the page) — skip it rather than echo the URL as prose.
        if value is None or (isinstance(value, str) and (value.startswith("http") or value.startswith("data:"))):
            continue
        parts.append(f"{field_label(field)} is {plain_value(value)}")
    if not parts:
        return "No verified observation yet this checkpoint."
    text = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + ", and " + parts[-1]
    return text[0].upper() + text[1:] + "."

def section_summary(name, block):
    """Narrative recap of a section's own real, populated data — deterministic Python templates,
    never a live model call (RULES forbids model prose in canonical delivery), so every word
    traces back to the same values rendered in the section above it. The sections that drive
    today's trade (gamma, flow, market control, premium selling, the strategy horizons, ...) get
    a bespoke, voice-rich builder built from the real field shapes. A section without one — mostly
    bookkeeping (paper scorecard, scanner health, data integrity, ...) — gets a plain but still
    readable sentence, never a raw field:value dump."""
    builder = _NARRATIVE_BUILDERS.get(name)
    if builder:
        text = builder(block)
        if text:
            return text
    return _generic_narrative_summary(block)

def _side_label(verdict_text):
    t = (verdict_text or "").lower()
    if "defensive" in t:
        return "defensive"
    if "risk-on" in t or "bullish" in t or "upside" in t:
        return "risk-on"
    return "neutral"

_STATUS_MEANING = {
    "WATCH": "No confirmed setup yet — this is a watch item, not a trade.",
    "ENTRY_READY": "Setup is confirmed — verify live per-leg BBO before entering.",
    "PENDING EVIDENCE": "Not enough evidence to form a thesis; wait.",
    "OPEN PAPER": "A paper position is already open on this horizon; manage it, don't re-enter.",
}

_SECTION_ROLE = {
    "expected_move": "Defines the day's statistical range; a sizing tool for strikes/width, not a trade signal by itself.",
    "smile": "Shows how the market prices tail risk across strikes; wider downside skew favors put-side structures over call-side.",
    "surface": "Cross-expiry volatility context for choosing which expiration carries the richest or cheapest premium.",
    "forward_strikes": "Raw strike-level flow detail behind the day/forward thesis above; supporting evidence, not a new signal.",
    "range_stall": "Tracks whether the day is building a balance area or breaking out of one; chop risk for any defined-risk structure.",
    "breadth": "Market-wide participation context; confirms or contradicts the SPY/QQQ-only regime read above.",
    "profile": "Shows where volume has actually transacted today; use value area edges as objective support/resistance.",
    "sector_credit": "Cross-asset leadership and credit-market confirmation; a flagged rotation here should agree with the regime call.",
    "macro": "Delayed rates/FX/commodity backdrop; context only, never a same-session trading signal.",
    "futures_context": "Overnight futures positioning on delayed data; use only to frame the open, not to time entries.",
    "event_calendar": "Known catalysts ahead; a confirmed HIGH-impact event inside the holding period should shrink size or widen the structure.",
    "contract_packages": "The qualified option structures behind the day/forward plans above — execution detail, not a new signal.",
    "entry_watches": "Where each registered setup sits in its own trigger lifecycle — confirms whether a plan above is still a watch or already confirmed.",
    "candidate_analysis": "The roster of symbols and surfaces being tracked — shows what's being watched, not a ranked recommendation.",
    "position_management": "Open simulated risk and exit rules for this report's own paper trades — managing an existing paper position, not a new entry signal.",
    "trigger_accountability": "Audit trail of past triggers and their outcomes — a track record for this system, not today's signal.",
    "paper_scorecard": "Performance of this report's own simulated paper trades — bookkeeping on the system itself, not advice on your account.",
    "scanner": "Scanner heartbeat and delivery health — confirms the pipeline is alive, not a market read.",
    "event_study": "Frozen historical holding-period statistics — describes past behavior only; never treat it as today's expected outcome.",
    "engine_consensus": "Cross-check against the squeeze and TradingVolatility engines — agreement adds confidence to the regime call above, disagreement is a reason to slow down.",
    "morning_comparison": "How price, range and setups have drifted since this morning's baseline — the regime's own HOLDING/CHANGED verdict lives in Positioning & Levels above; this is the supporting detail.",
    "horizon_comparison": "Cross-report consistency check between today's read and the morning/prior checkpoint — a sanity check, not a new signal.",
    "adaptation_rules": "The explicit rules for activating, cancelling or switching a plan — same rules as the If/Then Day Plan above, in full.",
    "visuals": "Chart delivery and integrity status — confirms the panels above are genuine renders, not decoration.",
    "data_integrity": "Report pipeline health and source-clock audit — confirms what you're reading is real and current; never itself a market signal.",
}

def _per_symbol_floats(value):
    """Pull the real numeric reading out of a per-symbol field, regardless of whether the
    producer nested it one level deeper (e.g. gamma.net_gex is {"SPY": {"net_gex_b": x}},
    not {"SPY": x}). Tries the symbol value itself first, then its first numeric child.
    """
    out = []
    if not isinstance(value, dict):
        return out
    for sym_value in value.values():
        if isinstance(sym_value, (int, float)):
            out.append(float(sym_value))
        elif isinstance(sym_value, dict):
            for v in sym_value.values():
                if isinstance(v, (int, float)):
                    out.append(float(v))
                    break
    return out

def section_meaning(name, block, mission_side=None):
    """Deterministic "what it means for the day" line — a lookup on the section's own
    already-computed field values, never new analysis or a fabricated number. Strategy-
    neutral: states what the evidence favors (sellers vs buyers, which side), not which
    specific structure (spread/condor/single) to use.

    Leron, 2026-10-10: "each section should flow into each [other]" -- market_control is the
    one section below Today's Mission with its own real bull/bear-leaning read (call sellers
    capping upside vs put sellers supporting downside), so it's the one place a grounded
    agree/conflict callback to the mission verdict belongs; everywhere else that comparison
    would be forcing a direction onto evidence that genuinely has none (vol pricing, pipeline
    health, audit trails), which is exactly the fabrication this file's rules forbid.
    """
    def val(field):
        item = block.get(field) or {}
        return item.get("value") if item.get("status") != "unavailable" else None
    if name == "risk_on_defensive":
        side = _side_label(val("verdict"))
        return {"defensive": "Bias toward protection or put-side exposure; confirm with flow before acting.",
                "risk-on": "Bias toward upside continuation or call-side exposure; confirm with flow before acting.",
                "neutral": "No clear directional bias from price alone; wait for confirmation."}[side]
    if name == "market_control":
        sides = []
        control = val("control_side") or {}
        for sym_row in (control.values() if isinstance(control, dict) else []):
            if isinstance(sym_row, dict):
                sides.extend(str(v).lower() for v in sym_row.values())
        if not sides or all(s == "inconclusive" for s in sides):
            return "Dealer positioning is unclear today; classified flow coverage is too thin to say who's in control."
        if sides.count("call_sellers") > sides.count("put_sellers"):
            # Capped-upside expectation agrees with a defensive mission call, conflicts with risk-on.
            tie_in=({"risk-on":" That tension with the risk-on mission call above is worth a second look before leaning on either one alone.",
                     "defensive":" That lines up with the defensive mission call above — two independent reads agreeing.",
                     "neutral":""}.get(mission_side,"") if mission_side else "")
            return "Call sellers dominate where classified — a sign of capped upside expectations."+tie_in
        if sides.count("put_sellers") > sides.count("call_sellers"):
            # Downside-support-being-sold agrees with a risk-on mission call, conflicts with defensive.
            tie_in=({"defensive":" That tension with the defensive mission call above is worth a second look before leaning on either one alone.",
                     "risk-on":" That lines up with the risk-on mission call above — two independent reads agreeing.",
                     "neutral":""}.get(mission_side,"") if mission_side else "")
            return "Put sellers dominate where classified — a sign of downside support being sold."+tie_in
        return "Call- and put-selling are evenly split where classified; no net control."
    if name == "gamma":
        signs = _per_symbol_floats(val("net_gex"))
        if not signs:
            return "No verified net gamma reading this checkpoint."
        if all(s >= 0 for s in signs):
            return "Positive gamma dampens moves — expect range-bound price action near the flip."
        if all(s <= 0 for s in signs):
            return "Negative gamma amplifies moves — expect larger swings away from the flip."
        return "Gamma sign is mixed across symbols — dampening in one, amplifying in the other."
    if name == "flow":
        covs = _per_symbol_floats(val("classified_coverage"))
        if covs and max(covs) < 0.5:
            return "Classified coverage is below half the tape — too thin to read directional conviction from flow alone."
        return "Classified coverage supports a directional read; compare calls-bought/sold vs puts-bought/sold above."
    if name == "premium_selling":
        suit = val("suitability") or {}
        labels = set(str(v) for v in (suit.values() if isinstance(suit, dict) else []))
        if "PREMIUM_RICH" in labels:
            return "Premium is rich versus realized move: edge favors premium sellers over premium buyers, unless price/flow confirms expansion."
        if "PREMIUM_CHEAP" in labels:
            return "Premium is cheap versus realized move: edge favors premium buyers over premium sellers."
        return "Premium is fairly priced versus realized move; no edge either way from this reading alone."
    if name in ("day_strategy", "near_forward_strategy", "forward_strategy"):
        status = val("status")
        return _STATUS_MEANING.get(status, "Status is " + str(status) + "; apply the adaptation rules before acting.")
    return _SECTION_ROLE.get(name, "Supporting evidence for the sections above; not a standalone signal.")

def decision_brief_lines(blocks):
    """The decision-first synthesis every report should open with, before any supporting
    detail: the regime call, whether each symbol's flow agrees or conflicts with it, the one
    clean edge if any, and whether the plan has changed since this morning. Leron, 2026-10-12:
    "all the decision making information and why should be at the beginning of every report,
    supporting information after" -- this is the exact walk-through he assembled by hand
    reading a report end to end, now automated. Deterministic: every line traces to a real
    field rendered in its own section below; conflict detection only fires when both readings
    are real values, never inferred from a gap."""
    verdict_item = (blocks.get("risk_on_defensive") or {}).get("verdict") or {}
    verdict = verdict_item.get("value")
    if not isinstance(verdict, str) or verdict_item.get("status") == "unavailable":
        return []
    regime_side = _side_label(verdict)
    mood = {"defensive": "leaning defensive", "risk-on": "leaning bullish",
            "neutral": "mixed, no clean lean"}[regime_side]
    lines = [f"Regime: price is {mood}."]

    net_val = ((blocks.get("gamma") or {}).get("net_gex") or {}).get("value") or {}
    suit_val = ((blocks.get("premium_selling") or {}).get("suitability") or {}).get("value") or {}
    day_thesis = ((blocks.get("day_strategy") or {}).get("thesis") or {}).get("value")
    clean_edge, any_conflict = None, False
    for sym in ("SPY", "QQQ"):
        bits = []
        row = net_val.get(sym)
        gex = row.get("net_gex_b") if isinstance(row, dict) else None
        pinning = None
        if _num(gex):
            pinning = gex > 0
            bits.append("gamma is pinning it, a flat-day setup" if pinning
                        else "gamma is amplifying it, a break can run" if gex < 0
                        else "gamma is flat")
        flow_read = None
        sym_thesis = day_thesis.get(sym) if isinstance(day_thesis, dict) else None
        if isinstance(sym_thesis, dict):
            flow_read = sym_thesis.get("read")
        conflict = False
        if flow_read in ("upside pressure", "downside pressure") and regime_side != "neutral":
            flow_side = "risk-on" if flow_read == "upside pressure" else "defensive"
            if flow_side != regime_side:
                conflict, any_conflict = True, True
                bits.append(f"but flow is {flow_read} -- conflicts with the regime call")
            else:
                bits.append(f"flow ({flow_read}) agrees with the regime call")
        suit = suit_val.get(sym)
        if suit == "PREMIUM_RICH" and not conflict and pinning and clean_edge is None:
            clean_edge = sym
        if bits:
            lines.append(f"{sym}: " + "; ".join(bits) + ".")

    if clean_edge:
        lines.append(f"What this means: the one clean edge right now is {clean_edge} "
                      "premium-selling -- gamma is pinning it and nothing is fighting that read.")
    elif any_conflict:
        lines.append("What this means: nothing yet -- price and flow are fighting each other, "
                      "that is the don't-commit signal.")
    else:
        lines.append("What this means: wait for the setups below to confirm -- no clean edge yet.")

    rs = ((blocks.get("morning_comparison") or {}).get("regime_shift") or {}).get("value") or {}
    statuses = [(rs.get(s) or {}).get("status") for s in ("SPY", "QQQ") if isinstance(rs.get(s), dict)]
    if statuses and all(s == "HOLDING" for s in statuses):
        lines.append("Plan status: holding since this morning -- nothing has actually changed.")
    elif any(s == "CHANGED" for s in statuses):
        lines.append("Plan status: changed since this morning -- worth a second look before trusting the old plan.")
    return lines

def market_story(blocks):
    """Three independent fragments (regime verdict, premium suitability, gamma read) joined
    into one paragraph. A blind join produced run-ons like "...UNAVAILABLE — no timestamped
    observation Gamma sign is mixed..." when a fragment is itself an UNAVAILABLE disclosure
    with no trailing punctuation — each fragment now ends with its own sentence stop."""
    parts = [display(blocks["risk_on_defensive"]["verdict"], compact=True),
             display(blocks["premium_selling"]["suitability"], compact=True),
             section_meaning("gamma", blocks["gamma"])]
    return " ".join(p if p.endswith((".", "!", "?")) else p + "." for p in parts if p)

def market_story_html(blocks):
    """Same three fragments as market_story(), without the "[LIVE NOW; updated ...]" bracket
    tag glued onto each sentence — the scoreboard immediately above this paragraph already
    shows that same reliability info as its own pill, so repeating it inline here just adds
    clutter to a paragraph meant to read as plain prose."""
    parts = [_value_text(blocks["risk_on_defensive"]["verdict"]),
             _value_text(blocks["premium_selling"]["suitability"]),
             section_meaning("gamma", blocks["gamma"])]
    return " ".join(p if p.endswith((".", "!", "?")) else p + "." for p in parts if p)

def edge_board(blocks):
    rows = []
    for name in ("day_strategy", "near_forward_strategy", "forward_strategy"):
        row = blocks[name]
        rows.append((name.replace("_", " "), display(row["trigger"], compact=True),
                     display(row["invalidation"], compact=True), display(row["status"], compact=True)))
    return rows

def biggest_traps(blocks):
    """Market-risk events only — a data-completeness count ("N fields unavailable") is a
    different kind of fact than "CPI drops Tuesday" and reads as a trading trap when it is
    really a meta note about this checkpoint's coverage. That count still lives in Data
    Integrity; it does not belong in the list a trader scans for what could move the market."""
    traps = []
    catalysts = (blocks.get("event_calendar") or {}).get("catalysts") or {}
    cv = catalysts.get("value")
    if isinstance(cv, list):
        for c in cv:
            if isinstance(c, dict) and str(c.get("impact")).upper() == "HIGH":
                traps.append(str(c.get("name")) + " on " + str(c.get("datetime")))
    if not traps:
        traps.append("No flagged high-impact catalysts this checkpoint.")
    return traps

def if_then_day_plan(blocks):
    rules = blocks.get("adaptation_rules") or {}
    return [(k.replace("_", " ").title(), display(v)) for k, v in rules.items()]

def render_markdown(payload):
    from .report_contract import REQUIREMENTS
    blocks=payload["report_blocks"]
    title="☀️ Morning Options Sentiment" if payload.get("kind")=="morning" else "📡 Intraday Options Sentiment"
    lines=["# "+title,ct_str(payload.get("generated_at"))+" · "+str(payload.get("kind","report"))+" · "+payload["report_completeness"]]
    brief=decision_brief_lines(blocks)
    if brief:
        lines.extend(["## 🧭 Decision brief"]+brief)
    lines.extend([
        "## 🎯 Today’s mission",display(blocks["risk_on_defensive"]["verdict"]),
        "Day and forward plans are separate. Execute no strategy from historical or unqualified quotes; use the recorded triggers and conflicts below.",
        "## 🚦 30-second scoreboard","| Decision | Current read |","|---|---|"])
    for label,read in scoreboard(blocks):lines.append("| "+label+" | "+read.replace("|","\\|").replace("\n"," ")+" |")
    lines.extend(["## Today vs forward","| Horizon | Thesis | Status |","|---|---|---|"])
    for name in ("day_strategy","near_forward_strategy","forward_strategy"):
        row=blocks[name];lines.append("| "+name.replace("_"," ")+" | "+display(row["thesis"]).replace("|","\\|")+" | "+display(row["status"]).replace("|","\\|")+" |")
    lines.extend(["## 🧭 Market story",market_story(blocks)])
    lines.extend(["## 🧩 Edge board","| Horizon | Trigger | Invalidation | Status |","|---|---|---|---|"])
    for horizon,trigger,invalid,status in edge_board(blocks):
        lines.append("| "+horizon+" | "+trigger.replace("|","\\|")+" | "+invalid.replace("|","\\|")+" | "+status.replace("|","\\|")+" |")
    lines.append("## ⚠️ Biggest traps")
    lines.extend("- "+t for t in biggest_traps(blocks))
    lines.append("## 🧮 If/then day plan")
    lines.extend("- **"+k+"**: "+v for k,v in if_then_day_plan(blocks))
    mission_side=_side_label((blocks["risk_on_defensive"]["verdict"] or {}).get("value"))
    for name,fields in REQUIREMENTS.items():
        lines.append("### "+name.replace("_"," ").title())
        for field in fields:lines.append("- **"+field+"**: "+display(blocks[name][field]))
        if name in SECTION_SUMMARY_SECTIONS:
            lines.append("Section summary: "+section_summary(name,blocks[name]))
            lines.append("What it means for the day: "+section_meaning(name,blocks[name],mission_side))
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

_TIER_STYLE = {"live": ("#34d399", "LIVE"), "historical": ("#fbbf24", "LAST KNOWN"), "unavailable": ("#f87171", "UNAVAILABLE")}

def pill_html(item):
    """Small colored status badge, kept visually SEPARATE from the value text it describes.
    display()'s "[LIVE NOW; updated ...; age ...]" glued a provenance tag onto the end of
    every sentence; dropped unbroken into a report page's <td> (found live 2026-10-09 — Leron's
    screenshot of the opening summary read as one unbroken wall of text), that tag became
    indistinguishable from the real content. Inline styles only (no CSS classes) — this also
    feeds the email body in report_email.py, which strips <style> blocks and classes."""
    if not isinstance(item, dict):
        return ""
    color, label = _TIER_STYLE.get(item.get("status"), ("#8b97a8", str(item.get("status", "")).upper()))
    return (f'<span style="display:inline-block;font-size:10px;font-weight:700;letter-spacing:.03em;'
            f'color:{color};border:1px solid {color};border-radius:999px;padding:1px 7px;margin-left:6px;'
            f'white-space:nowrap;vertical-align:middle">{html.escape(label)}</span>')

def meta_line_html(item):
    """Small muted 'updated ... CT · age ...' line on its own row — the pill already carries
    the LIVE/LAST KNOWN meaning, so this drops the verbose repeated "CONTEXT ONLY (LOW
    contextual reliability)" clause that display() appends inline."""
    if not isinstance(item, dict):
        return ""
    stamp = parse_clock(item.get("source_timestamp"))
    age = item.get("age_seconds")
    bits = []
    if stamp:
        bits.append("updated " + stamp.astimezone(CT).strftime("%Y-%m-%d %I:%M %p CT"))
    if isinstance(age, (int, float)):
        bits.append("age " + (f"{age:.0f}s" if age < 120 else f"{age/60:.0f}m" if age < 7200 else f"{age/3600:.1f}h"))
    if not bits:
        return ""
    return f'<div style="color:#8b97a8;font-size:11px;margin-top:3px">{html.escape(" &middot; ".join(bits))}</div>'

_OCC_RE = re.compile(r"^[A-Z]{1,6}(\d{6})([CP])(\d{8})$")

def _parse_occ_leg(symbol):
    """Best-effort parse of an OCC option symbol (ROOT+YYMMDD+C/P+strike*1000) into an expiry
    date string, 'call'/'put', and strike. Returns (None, None, None) on any non-match --
    cosmetic for a trade-idea sentence, never a data source, so it must never raise."""
    m = _OCC_RE.match(str(symbol or ""))
    if not m:
        return None, None, None
    yy, mm, dd = m.group(1)[:2], m.group(1)[2:4], m.group(1)[4:6]
    return f"20{yy}-{mm}-{dd}", ("call" if m.group(2) == "C" else "put"), int(m.group(3)) / 1000.0

def _looks_like_package(d):
    return (isinstance(d, dict) and isinstance(d.get("legs"), list) and d["legs"]
            and all(isinstance(l, dict) and _num(l.get("strike")) and l.get("action") in ("buy", "sell")
                    for l in d["legs"]))

def narrative_package_html(pkg):
    """One qualified option structure (qualify_package()'s raw shape: legs + natural_credit/
    debit + payoff) as a plain-English trade idea instead of a per-leg field:value dump --
    Leron, 2026-10-11, screenshot of exactly that dump in the Today's Mission panel: "I don't
    know how to read the information in this image." Every number here still traces to the
    same leg/payoff data; this only changes how it reads."""
    legs = pkg.get("legs") or []
    leg_bits, expiry = [], None
    for l in legs:
        action = "Sell" if l.get("action") == "sell" else "Buy"
        strike = l.get("strike")
        right = "call" if l.get("right") in ("C", "call") else "put" if l.get("right") in ("P", "put") else None
        parsed_expiry, parsed_right, _strike = _parse_occ_leg(l.get("symbol"))
        right = right or parsed_right or "option"
        expiry = expiry or parsed_expiry
        leg_bits.append(f"{action} the {strike:g} {right}" if _num(strike) else f"{action} the {right}")
    sentence = ", ".join(leg_bits) if leg_bits else "Structure"
    strategy = pkg.get("strategy")
    if isinstance(strategy, str) and strategy:
        sentence = f"<b>{html.escape(strategy.replace('_', ' ').title())}</b> — " + sentence
    if expiry:
        sentence += f" (expiring {expiry})"
    credit, debit = pkg.get("natural_credit"), pkg.get("natural_debit")
    if _num(credit) and credit:
        sentence += f" — collect ${credit:.2f}"
    elif _num(debit) and debit:
        sentence += f" — pay ${debit:.2f}"
    payoff = pkg.get("payoff") or {}
    max_risk, max_reward = payoff.get("max_risk"), payoff.get("max_reward")
    if _num(max_risk) and max_risk:
        if max_reward == "unlimited":
            sentence += f". Risk ${max_risk:.0f} with unlimited upside"
        elif _num(max_reward):
            sentence += f". Risk ${max_risk:.0f} to make ${max_reward:.0f}"
    breakeven = payoff.get("breakeven")
    be = breakeven[0] if isinstance(breakeven, list) and breakeven else (breakeven if _num(breakeven) else None)
    if _num(be):
        sentence += f", breakeven at ${be:.2f}"
    sentence += ". Qualified on fresh per-leg quotes — ready to trade right now."
    return sentence

def _looks_like_setup(d):
    return (isinstance(d, dict) and isinstance(d.get("setup_id"), str) and isinstance(d.get("symbol"), str)
            and any(k in d for k in ("thesis", "entry", "invalidation")))

def narrative_setup_html(setup):
    """One registered trade setup -- the full internal plan object (thesis/entry/invalidation
    plus ~15 supporting fields: expiration_preference, profit_taking_framework, source_metadata,
    created_at, sessions, ...) -- as a plain-English trigger description instead of a 17-field
    label dump. Same bug class as narrative_package_html, caught in the Edge Board's Trigger
    column: Leron, 2026-10-11, "why do I feel like something is missing" after the contracts
    fix landed but this sibling field didn't."""
    symbol = setup.get("symbol") or ""
    strategy = setup.get("strategy")
    strategy_label = str(strategy).replace("_", " ") if isinstance(strategy, str) and strategy else "setup"
    sentence = f"<b>{html.escape(str(symbol))} {html.escape(strategy_label)}</b>"
    thesis = setup.get("thesis")
    if isinstance(thesis, str) and thesis:
        sentence += f" — {html.escape(thesis)}"
    entry = setup.get("entry")
    if isinstance(entry, str) and entry:
        sentence += f". Enters on: {html.escape(entry)}"
    invalidation = setup.get("invalidation")
    if isinstance(invalidation, str) and invalidation:
        sentence += f". Cancels if: {html.escape(invalidation)}"
    catalyst = setup.get("catalyst")
    if isinstance(catalyst, str) and catalyst and "no specific catalyst" not in catalyst.lower():
        sentence += f". Catalyst: {html.escape(catalyst)}"
    return sentence + "."

def narrative_html(value, depth=0):
    """Readable HTML for a field's value. A dict (e.g. thesis: {direction, volatility_context,
    meaning}) renders as one labeled line per key — plain_value()'s comma-joined run-on reads
    fine as a single Discord embed line, but the exact same string dropped unbroken into a
    report page's <td> was unreadable prose (Leron, 2026-10-10 screenshot). Everything else
    keeps plain_value()'s shape-based formatting (symbol dicts, scalar lists, timestamp
    strings) so numbers/dates still render identically to the rest of the page."""
    if value is None:
        return '<span style="color:#8b97a8">&mdash;</span>'
    if isinstance(value, dict):
        if value and all(isinstance(k, str) and _SYM_KEY_RE.match(k) for k in value):
            return "<br>".join(f"<b>{html.escape(k)}:</b> {narrative_html(v, depth + 1)}" for k, v in value.items())
        if not value or depth >= 2:
            return html.escape(plain_value(value, depth))
        rows = []
        for k, v in value.items():
            raw_label=field_label(k)
            label = html.escape(raw_label[:1].upper()+raw_label[1:] if raw_label else raw_label)
            if isinstance(v, (dict, list)) and v:
                rows.append(f'<div style="margin:4px 0"><span style="color:#8b97a8">{label}</span><br>{narrative_html(v, depth + 1)}</div>')
            else:
                rows.append(f'<div style="margin:4px 0"><span style="color:#8b97a8">{label}:</span> {narrative_html(v, depth + 1)}</div>')
        return "".join(rows)
    if isinstance(value, list):
        if not value:
            return '<span style="color:#8b97a8">none</span>'
        if value and all(_looks_like_package(x) for x in value):
            shown = value[:3]
            out = "<br>".join(f'<div style="margin:6px 0">{narrative_package_html(x)}</div>' for x in shown)
            if len(value) > 3:
                out += f'<div style="color:#8b97a8">&hellip; +{len(value)-3} more</div>'
            return out
        if value and all(_looks_like_setup(x) for x in value):
            shown = value[:3]
            out = "<br>".join(f'<div style="margin:6px 0">{narrative_setup_html(x)}</div>' for x in shown)
            if len(value) > 3:
                out += f'<div style="color:#8b97a8">&hellip; +{len(value)-3} more</div>'
            return out
        if all(not isinstance(x, (dict, list)) for x in value):
            shown = value[:8]
            text = ", ".join(html.escape(plain_value(x, depth + 1)) for x in shown)
            if len(value) > 8:
                text += f' <span style="color:#8b97a8">&hellip; +{len(value)-8} more</span>'
            return text
        shown = value[:5]
        out = "<br>".join(narrative_html(x, depth + 1) for x in shown)
        if len(value) > 5:
            out += f'<div style="color:#8b97a8">&hellip; +{len(value)-5} more items</div>'
        return out
    if isinstance(value, str):
        return html.escape(ct_str(value))
    if isinstance(value, float):
        return html.escape(fmt_number(value))
    return html.escape(str(value))

def item_cell_html(item):
    """One observed()-shaped item as a self-contained fragment: status pill, readable value,
    small muted meta line — the building block for render_opening_html's rows so the opening
    summary a trader reads first matches the same clear value/status/clock separation the
    per-field sections below it already use."""
    if not isinstance(item, dict):
        return '<span style="color:#8b97a8">Unavailable</span>'
    if item.get("status") == "unavailable":
        reason = str(item.get("reason") or "No verified observation")
        out = pill_html(item) + f'<div style="margin-top:4px;color:#f87171">{html.escape(reason)}</div>'
        if item.get("value") is not None:
            out += f'<div style="margin-top:4px">Unverified estimate: {narrative_html(item["value"])}</div>'
        return out
    return pill_html(item) + f'<div style="margin-top:4px">{narrative_html(item.get("value"))}</div>' + meta_line_html(item)

def positioning_panel_html(blocks):
    """Leron, 2026-10-10: "I need to be able to see during the day where the call sellers and
    put sellers are... Should I be playing long or should I be selling premium? And which
    strikes?" -- every input here already exists under gamma.net_gex/walls, market_control.
    control_side, and premium_selling.suitability; this only moves it to the top of the page
    instead of leaving it buried in the Gamma/Market Control sections below.

    Leron, 2026-10-10 (same day): "it needs to be more nimble... the plan for the day but
    nimble to change intraday." The regime read above told him WHAT today looks like, but
    never said whether that read was still the same one this morning gave him. The
    morning_comparison.regime_shift field (added this change) carries the morning's
    net_gex/control_side/suitability snapshot; the Plan status line below compares it to
    the current read and declares HOLDING/CHANGED/first-report, so an intraday regime flip
    is announced instead of silently sitting in two separately-rendered reports."""
    gamma=blocks.get("gamma") or {}
    mc=blocks.get("market_control") or {}
    ps=blocks.get("premium_selling") or {}
    net_gex=(gamma.get("net_gex") or {}).get("value") or {}
    walls=(gamma.get("walls") or {}).get("value") or {}
    suitability_item=ps.get("suitability") or {}
    suitability=suitability_item.get("value") or {}
    control_side=(mc.get("control_side") or {}).get("value") or {}
    regime_shift=((blocks.get("morning_comparison") or {}).get("regime_shift") or {}).get("value") or {}
    symbols=sorted(set(net_gex) | set(walls) | set(suitability) | set(control_side))
    rows=[]
    for sym in symbols:
        bits=[]
        rs=regime_shift.get(sym)
        if isinstance(rs,dict):
            status=rs.get("status")
            if status=="FIRST_REPORT":
                bits.append('<div style="margin:4px 0;color:#8b97a8"><b>Plan status:</b> first read of the day — no earlier baseline yet</div>')
            elif status=="CHANGED":
                bits.append('<div style="margin:4px 0"><b style="color:#e0a339">Plan status: CHANGED since this morning</b> — '
                             +html.escape('; '.join(rs.get("changed") or []))+'</div>')
            elif status=="HOLDING":
                bits.append('<div style="margin:4px 0"><b style="color:#4caf7d">Plan status: HOLDING</b> — still matches this morning\'s read</div>')
        ng_raw=net_gex.get(sym)
        ng=ng_raw.get("net_gex_b") if isinstance(ng_raw,dict) else ng_raw if isinstance(ng_raw,(int,float)) else None
        if isinstance(ng,(int,float)):
            if ng>0:regime="Positive gamma — dealers dampen moves, range-bound, favors selling premium over directional risk."
            elif ng<0:regime="Negative gamma — dealers amplify moves, trend risk, favors long/directional over selling premium."
            else:regime="Gamma flat — no dealer-hedging bias either way."
            bits.append(f'<div style="margin:4px 0">{html.escape(regime)} <span style="color:#8b97a8">(net GEX {fmt_number(ng)}B)</span></div>')
        wall=((walls.get(sym) or {}).get("walls")) if isinstance(walls.get(sym),dict) else None
        if isinstance(wall,dict):
            top_call=next(iter(wall.get("top_call") or []),None)
            top_put=next(iter(wall.get("top_put") or []),None)
            if isinstance(top_call,dict) and top_call.get("strike") is not None:
                bits.append(f'<div style="margin:4px 0"><span style="color:#8b97a8">Resistance (call wall):</span> {fmt_number(top_call["strike"])}</div>')
            if isinstance(top_put,dict) and top_put.get("strike") is not None:
                bits.append(f'<div style="margin:4px 0"><span style="color:#8b97a8">Support (put wall):</span> {fmt_number(top_put["strike"])}</div>')
        suit=suitability.get(sym)
        if suit:
            bits.append(f'<div style="margin:4px 0"><span style="color:#8b97a8">Premium:</span> {html.escape(str(suit).replace("_"," ").title())}</div>')
        elif suitability_item.get("status")=="unavailable":
            bits.append('<div style="margin:4px 0;color:#8b97a8">Premium suitability: unavailable (needs 60 min of realized trading data; populates after the open)</div>')
        side=control_side.get(sym)
        if isinstance(side,dict):
            conclusive={k:v for k,v in side.items() if v and v!="inconclusive"}
            if conclusive:
                bits.append('<div style="margin:4px 0"><span style="color:#8b97a8">Who\'s selling:</span> '
                             +html.escape(", ".join(f"{field_label(k)} {str(v).replace('_',' ')}" for k,v in conclusive.items()))+'</div>')
            else:
                bits.append('<div style="margin:4px 0;color:#8b97a8">Who\'s selling: too thin to call right now</div>')
        if bits:
            rows.append(f'<b>{html.escape(sym)}</b>'+"".join(bits))
    if not rows:
        return ""
    parts=[f'<div{"" if i==0 else " style=\"margin:10px 0;padding-top:10px;border-top:1px solid #2a3341\""}>{content}</div>'
           for i,content in enumerate(rows)]
    return '<h2>📍 Positioning &amp; levels</h2>'+"".join(parts)

def _week_ahead_outlook_html(blocks):
    """Morning-only lead paragraph: last-known volatility, the week-ahead vol/expected-move
    context, upcoming catalysts, and carried-over gamma positioning -- synthesized into one
    forward-looking story instead of a page of pre-market 'LAST KNOWN'/'unavailable' sections
    with nothing fresh to say. Leron, 2026-10-12: "it should do forward looking by last known
    volatility, expected move and more for the upcoming week, news that affect market
    conditions and it should be outlook based." Every number here still traces to the same
    field rendered in its own section below; this never invents a forward price or level.
    Shipped once (PR #3261), reverted same-day as a precaution during an unrelated production
    outage (root cause traced to the ember_tv_book_cycle scheduled job, not this code -- a
    plain redeploy of the SAME commit fixed it before the revert even landed), then never
    re-shipped. Re-added 2026-10-12 after Leron pointed out the content side of his asks had
    stalled while infra fixes kept shipping instead."""
    bits = []

    surface = blocks.get("surface") or {}
    atm_val = (surface.get("atm_iv") or {}).get("value") or {}
    term_far_val = (surface.get("term_21plus") or {}).get("value") or {}
    row = atm_val.get("SPY")
    atm = row.get("atm_iv") if isinstance(row, dict) else None
    if _num(atm):
        far_row = term_far_val.get("SPY")
        far = far_row.get("iv_21_365dte") if isinstance(far_row, dict) else None
        sentence = f"SPY vol is sitting at {atm*100:.1f}% ATM heading into the week"
        if _num(far) and far > 0:
            if atm > far * 1.15:
                sentence += " — elevated relative to the back of the curve, priced for event risk"
            elif atm < far * 0.9:
                sentence += " — calm, no term premium baked in yet"
        bits.append(sentence + ".")

    nf_thesis = ((blocks.get("near_forward_strategy") or {}).get("thesis") or {}).get("value")
    if isinstance(nf_thesis, dict):
        vol_ctx = nf_thesis.get("volatility_context") or {}
        spy_ctx = vol_ctx.get("SPY") if isinstance(vol_ctx, dict) else None
        median_iv = (spy_ctx or {}).get("median_iv")
        expiries = (spy_ctx or {}).get("expiries")
        if _num(median_iv):
            n_exp = len(expiries) if isinstance(expiries, (list, set)) else None
            sentence = f"Options expiring next week price a {median_iv*100:.1f}% median IV in SPY"
            if n_exp:
                sentence += f" across {n_exp} expiry{'ies' if n_exp != 1 else ''}"
            if _num(atm) and atm > 0 and median_iv > atm * 1.3:
                sentence += (f" — a real step up from today's calmer {atm*100:.1f}% ATM read, "
                             "a sign the market is already pricing in next week's catalysts")
            elif _num(atm) and atm > 0 and median_iv < atm * 0.8:
                sentence += f" — lower than today's {atm*100:.1f}% ATM read, no extra premium baked in for next week yet"
            bits.append(sentence + ".")

    events = ((blocks.get("event_calendar") or {}).get("catalysts") or {}).get("value")
    if isinstance(events, list) and events:
        high = [e for e in events if isinstance(e, dict) and str(e.get("impact")).upper() == "HIGH"]
        shown = (high or events)[:3]
        names = "; ".join(f"{e.get('name')} ({str(e.get('datetime') or '')[:10]})"
                           for e in shown if isinstance(e, dict) and e.get("name"))
        if names:
            label = "High-impact catalysts this week" if high else "On the calendar this week"
            bits.append(f"{label}: {names}.")

    gamma = blocks.get("gamma") or {}
    net_row = ((gamma.get("net_gex") or {}).get("value") or {}).get("SPY")
    gex = net_row.get("net_gex_b") if isinstance(net_row, dict) else None
    if _num(gex):
        wall_row = (((gamma.get("walls") or {}).get("value") or {}).get("SPY") or {}).get("walls") or {}
        top_call = (wall_row.get("top_call") or [{}])[0].get("strike") if wall_row.get("top_call") else None
        top_put = (wall_row.get("top_put") or [{}])[0].get("strike") if wall_row.get("top_put") else None
        sentence = f"Dealers are carrying {gex:+.2f}B net gamma in SPY into the week"
        if _num(top_call) and _num(top_put):
            sentence += f", sellers dug in at {top_call:g} on the call side and {top_put:g} on the put side"
        bits.append(sentence + ".")

    if not bits:
        return ""
    return ('<h2>🔭 Week ahead outlook</h2><p>' + " ".join(html.escape(b) for b in bits) + "</p>"
            '<p style="font-size:.8rem;color:#8b97a8">Built from the last verified observation of '
            "each input — nothing here is invented ahead of the open.</p>")

def render_opening_html(payload):
    blocks=payload.get("report_blocks") or {};escape=html.escape
    divider='<div style="margin-top:8px;padding-top:8px;border-top:1px solid #2a3341">'
    def cell(name,field):return item_cell_html((blocks.get(name) or {}).get(field,{}))
    scoreboard_rows=[
        ("Regime / trend",cell("risk_on_defensive","verdict")),
        ("Chop / breakout risk",cell("range_stall","breakout_ends_chop")),
        ("Premium / volatility buying",cell("premium_selling","suitability")),
        ("Confidence / data quality",'<span style="color:#8b97a8">See the source clocks and explicit historical/unavailable fields below; no inferred high confidence.</span>'),
        ("Flow / gamma",cell("flow","classified_coverage")+divider+cell("gamma","net_gex")+'</div>'),
        ("Best underlying / structure",cell("day_strategy","contracts")),
    ]
    rows="".join("<tr><th>"+escape(k)+"</th><td>"+v+"</td></tr>" for k,v in scoreboard_rows)
    brief=decision_brief_lines(blocks)
    out=(('<h2>🧭 Decision brief</h2><p>'+" ".join(escape(l) for l in brief)+'</p>' if brief else "")
         +(_week_ahead_outlook_html(blocks) if payload.get("kind")=="morning" else "")
         +"<h2>🎯 Today’s mission</h2><div>"+item_cell_html(blocks.get("risk_on_defensive",{}).get("verdict",{}))+"</div>"
         "<p>Everything below supports or challenges this call — scoreboard for the quick read, "
         "Today vs Forward for the trade thesis, Edge Board for the exact trigger and invalidation.</p>"
         +positioning_panel_html(blocks)+
         "<h2>🚦 30-second scoreboard</h2><table>"+rows+"</table><h2>Today vs forward</h2><table>")
    for name in ("day_strategy","near_forward_strategy","forward_strategy"):
        row=blocks.get(name) or {}
        cell_html=item_cell_html(row.get("thesis",{}))+divider+item_cell_html(row.get("status",{}))+'</div>'
        out+="<tr><th>"+escape(name.replace("_"," "))+"</th><td>"+cell_html+"</td></tr>"
    out+="</table>"
    out+="<h2>🧭 Market story</h2><p>"+escape(market_story_html(blocks))+"</p>"
    out+='<h2>🧩 Edge board</h2><table class="wide"><tr><th>Horizon</th><th>Trigger</th><th>Invalidation</th><th>Status</th></tr>'
    for name in ("day_strategy","near_forward_strategy","forward_strategy"):
        row=blocks.get(name) or {}
        out+=("<tr><th>"+escape(name.replace("_"," "))+"</th><td>"+item_cell_html(row.get("trigger",{}))+"</td>"
              "<td>"+item_cell_html(row.get("invalidation",{}))+"</td><td>"+item_cell_html(row.get("status",{}))+"</td></tr>")
    out+="</table>"
    out+="<h2>⚠️ Biggest traps</h2><ul>"+"".join("<li>"+escape(t)+"</li>" for t in biggest_traps(blocks))+"</ul>"
    out+="<h2>🧮 If/then day plan</h2><table>"
    for k,item in (blocks.get("adaptation_rules") or {}).items():
        out+="<tr><th>"+escape(field_label(k))+"</th><td>"+item_cell_html(item)+"</td></tr>"
    out+="</table>"
    return out
