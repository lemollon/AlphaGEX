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

def _ct_safe_tree(v):
    """Walk an arbitrary JSON-able structure converting timestamp-shaped strings to Central
    Time before an irregular shape falls back to raw json.dumps. Live bug, found 2026-10-09:
    a dict with >10 keys (breadth, 18 fields including a nested per-symbol vwap.rows with its
    own source_timestamp) skipped every per-field ct_str() call below and dumped the whole
    tree — including its embedded UTC timestamps — as one raw JSON blob. ct_str() still
    no-ops on non-timestamp strings and bare dates, so this is safe to apply unconditionally."""
    if isinstance(v, str):
        return ct_str(v)
    if isinstance(v, dict):
        return {k: _ct_safe_tree(vv) for k, vv in v.items()}
    if isinstance(v, list):
        return [_ct_safe_tree(x) for x in v]
    return v

def plain_value(v, depth=0):
    """Plain-text (markdown/Discord-safe, no HTML) rendering of a field value for display().

    A raw json.dumps() of a per-symbol dict ({"SPY": "PREMIUM_RICH", "QQQ": ...}) is not
    readable at a glance; render it as "SPY: PREMIUM_RICH; QQQ: ..." instead. Only shapes
    too irregular to summarize this way fall back to a compact JSON string.
    """
    if v is None:
        return "none"
    if isinstance(v, dict):
        if v and all(isinstance(k, str) and _SYM_KEY_RE.match(k) for k in v):
            return "; ".join(f"{k}: {plain_value(sv, depth + 1)}" for k, sv in v.items())
        if v and len(v) <= 10 and depth < 4:
            return ", ".join(f"{field_label(k)} {plain_value(vv, depth + 1)}" for k, vv in v.items())
        return json.dumps(_ct_safe_tree(v), ensure_ascii=False, default=str)
    if isinstance(v, list):
        if not v:
            return "none"
        if len(v) <= 12 and all(not isinstance(x, (dict, list)) for x in v):
            return ", ".join(plain_value(x, depth + 1) for x in v)
        if depth < 3 and all(isinstance(x, dict) for x in v):
            shown = v[:5]
            text = "; ".join(plain_value(x, depth + 1) for x in shown)
            if len(v) > 5:
                text += f" (+{len(v) - 5} more)"
            return text
        return json.dumps(_ct_safe_tree(v), ensure_ascii=False, default=str)
    if isinstance(v, str):
        # Shape-based, not key-name-based: ct_str() only converts strings that actually parse
        # as a timezone-aware instant (a bare calendar date like an option expiration has no
        # tzinfo and passes through unchanged) — this subsumes the former per-key-name check,
        # which kept missing new field names (heartbeat, alert_time, requested_at, ...).
        return ct_str(v)
    return str(v)

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

def display(item, compact=False):
    """compact=True drops the per-value "[updated ...; age ...]" provenance suffix, keeping
    only a short reliability tag. Full display() repeats that suffix verbatim on every cell
    of a row (edge_board, scoreboard), which is correct for a standalone field but turns a
    "30-second scoreboard" into a wall of identical timestamps when 3 cells share one source.
    The reliability tag itself (LIVE vs LAST KNOWN) is kept even in compact mode — this report
    never hides staleness, it just stops repeating the same clock three times in one row."""
    if not isinstance(item,dict):return "Unavailable"
    value=item.get("value")
    if item.get("status")=="unavailable":
        return "UNAVAILABLE — "+str(item.get("reason") or "No verified observation")+("; unverified estimate: "+plain_value(value) if value is not None else "")
    text=plain_value(value) if isinstance(value,(dict,list)) else str(value)
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
)

def section_summary(name, block):
    """Mechanical recap of a section's own populated fields — literal field:value pairs,
    never a model-generated sentence. Cites real data so it can't drift from the section above it.
    """
    parts = []
    for field, item in block.items():
        if len(parts) >= 3:
            break
        if not isinstance(item, dict) or item.get("status") == "unavailable":
            continue
        value = item.get("value")
        if value is None:
            continue
        parts.append(field.replace("_", " ") + ": " + plain_value(value))
    if not parts:
        return "No verified observation yet this checkpoint."
    return "; ".join(parts) + "."

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

def section_meaning(name, block):
    """Deterministic "what it means for the day" line — a lookup on the section's own
    already-computed field values, never new analysis or a fabricated number. Strategy-
    neutral: states what the evidence favors (sellers vs buyers, which side), not which
    specific structure (spread/condor/single) to use.
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
            return "Call sellers dominate where classified — a sign of capped upside expectations."
        if sides.count("put_sellers") > sides.count("call_sellers"):
            return "Put sellers dominate where classified — a sign of downside support being sold."
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

def market_story(blocks):
    """Three independent fragments (regime verdict, premium suitability, gamma read) joined
    into one paragraph. A blind join produced run-ons like "...UNAVAILABLE — no timestamped
    observation Gamma sign is mixed..." when a fragment is itself an UNAVAILABLE disclosure
    with no trailing punctuation — each fragment now ends with its own sentence stop."""
    parts = [display(blocks["risk_on_defensive"]["verdict"], compact=True),
             display(blocks["premium_selling"]["suitability"], compact=True),
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
    lines=["# "+title,ct_str(payload.get("generated_at"))+" · "+str(payload.get("kind","report"))+" · "+payload["report_completeness"],
        "## 🎯 Today’s mission",display(blocks["risk_on_defensive"]["verdict"]),
        "Day and forward plans are separate. Execute no strategy from historical or unqualified quotes; use the recorded triggers and conflicts below.",
        "## 🚦 30-second scoreboard","| Decision | Current read |","|---|---|"]
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
    for name,fields in REQUIREMENTS.items():
        lines.append("### "+name.replace("_"," ").title())
        for field in fields:lines.append("- **"+field+"**: "+display(blocks[name][field]))
        if name in SECTION_SUMMARY_SECTIONS:
            lines.append("Section summary: "+section_summary(name,blocks[name]))
            lines.append("What it means for the day: "+section_meaning(name,blocks[name]))
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
    out+="</table>"
    out+="<h2>🧭 Market story</h2><p>"+escape(market_story(blocks))+"</p>"
    out+='<h2>🧩 Edge board</h2><table class="wide"><tr><th>Horizon</th><th>Trigger</th><th>Invalidation</th><th>Status</th></tr>'
    for horizon,trigger,invalid,status in edge_board(blocks):
        out+="<tr><th>"+escape(horizon)+"</th><td>"+escape(trigger)+"</td><td>"+escape(invalid)+"</td><td>"+escape(status)+"</td></tr>"
    out+="</table>"
    out+="<h2>⚠️ Biggest traps</h2><ul>"+"".join("<li>"+escape(t)+"</li>" for t in biggest_traps(blocks))+"</ul>"
    out+="<h2>🧮 If/then day plan</h2><table>"+"".join("<tr><th>"+escape(k)+"</th><td>"+escape(v)+"</td></tr>" for k,v in if_then_day_plan(blocks))+"</table>"
    return out
