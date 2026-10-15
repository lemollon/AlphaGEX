"""Versioned report requirements. Unavailable fields must be disclosed, never omitted."""
REQUIREMENTS = {
    "risk_on_defensive": [
        "verdict",
        "evidence",
        "conflicts",
        "change_vs_baselines",
        "regime_label"
    ],
    "premium_selling": [
        "suitability",
        "iv_rv_meaning_today",
        "forward_implications",
        "credit_structure_fit",
        "avoid"
    ],
    "surface": [
        "atm_iv",
        "skew_25d",
        "term_0dte",
        "term_1_5dte",
        "term_6_20dte",
        "term_21plus",
        "iv_vs_realized",
        "vix_family",
        "interpretation"
    ],
    "smile": [
        "expiry",
        "put_25d_iv",
        "atm_iv",
        "call_25d_iv",
        "strikes",
        "delta_method"
    ],
    "expected_move": [
        "percent",
        "dollars",
        "lower",
        "upper",
        "reference_spot",
        "session",
        "expiry",
        "method",
        "budget_used",
        "price_location"
    ],
    "gamma": [
        "coverage",
        "net_gex",
        "flip",
        "walls",
        "expiry_buckets",
        "scope_comparability"
    ],
    "flow": [
        "provider_provenance",
        "exchange_timestamp",
        "retrieval_timestamp",
        "age",
        "classified_coverage",
        "unclassified_coverage",
        "calls_bought",
        "calls_sold",
        "puts_bought",
        "puts_sold",
        "expiry_buckets",
        "price_vix_confirmation"
    ],
    "forward_strikes": [
        "expiries",
        "strikes",
        "contracts",
        "premium",
        "prints",
        "contemporaneous_bid_ask",
        "initiation_estimate"
    ],
    "market_control": [
        "control_side",
        "control_evidence",
        "control_confidence",
        "forward_control_outlook"
    ],
    "sector_credit": [
        "relative_returns",
        "leadership",
        "credit_confirmation"
    ],
    "breadth": [
        "advance_decline",
        "up_down_volume",
        "percent_above_vwap",
        "new_highs_lows",
        "proxy_labels"
    ],
    "profile": [
        "poc",
        "vah",
        "val",
        "hvn",
        "lvn",
        "method",
        "acceptance_rejection"
    ],
    "macro": [
        "rates",
        "curve",
        "dollar",
        "fx",
        "commodities",
        "move",
        "proxy_labels"
    ],
    "event_calendar": [
        "next_five_trading_days",
        "catalysts",
        "times",
        "sources",
        "risk_classes"
    ],
    "entry_watches": [
        "trigger",
        "confirmation",
        "invalidation",
        "status",
        "two_minute_closes",
        "successful_retest"
    ],
    "contract_packages": [
        "expiry",
        "strikes",
        "legs",
        "bid_ask",
        "greeks",
        "oi",
        "volume",
        "debit_credit",
        "max_risk_reward",
        "breakeven",
        "liquidity"
    ],
    "paper_scorecard": [
        "fill_reconciliation",
        "entry_ready_alerts",
        "fills",
        "closed",
        "wins_losses",
        "realized_pnl",
        "exceptions",
        "cumulative_pnl",
        "win_rate",
        "average_win_loss",
        "drawdown",
        "equity_history",
        "fill_rules",
        "slippage_costs",
        "trade_details"
    ],
    "morning_comparison": [
        "morning_timestamp",
        "prior_hour_timestamp",
        "price_location",
        "move_usage",
        "chop_status",
        "stall_risk",
        "setup_status",
        "regime_shift",
        "regime_label_shift"
    ],
    "range_stall": [
        "chop_low",
        "midpoint",
        "chop_high",
        "room_to_edges",
        "two_fresh_confirmations",
        "actual_rejection",
        "first_touch_watch",
        "breakout_ends_chop"
    ],
    "scanner": [
        "minute_cadence",
        "heartbeat",
        "registered_setups",
        "delivery_status"
    ],
    "event_study": [
        "holding_period_context",
        "frozen_method",
        "sample_size",
        "validated_statistics"
    ],
    "engine_consensus": [
        "squeeze",
        "trading_volatility_status",
        "contradictions"
    ],
    "visuals": [
        "market_map_png",
        "smile_term_png",
        "flow_png",
        "baseline_comparison_png",
        "event_risk_png",
        "paper_equity_drawdown_png",
        "image_inspection",
        "gamma_expiry_png",
        "sector_credit_png",
        "dark_theme"
        ,"surface_png", "term_structure_png", "volume_profile_png", "delivery_manifest"
    ],
    "futures_context": [
        "es_mes", "nq", "overnight_range", "basis", "index_confirmation"
    ],
    "candidate_analysis": [
        "symbols", "surface", "catalysts", "quote_chain_freshness", "liquidity", "conditional_triggers"
    ],
    "position_management": [
        "position_scope", "risk_exposure", "hold_exit_conditions", "chain_qualification"
    ],
    "trigger_accountability": [
        "registered_triggers", "verified_occurrence", "confirmation_sequence", "mfe_mae", "outcome", "loss_clusters"
    ]
}
STRATEGY_FIELDS = ["horizon", "thesis", "evidence", "conflicts", "structure", "trigger",
                   "invalidation", "status", "contracts", "quote_qualification",
                   "risk_exit_rules", "catalysts"]
for _name in ("day_strategy", "near_forward_strategy", "forward_strategy"):
    REQUIREMENTS[_name] = list(STRATEGY_FIELDS)
# Leron, 2026-10-14: SPY/QQQ's registered setup carries a FIXED structure regardless of
# today's condition, while trade_volatility_scan/engine_consensus already reuse TradingVolatility's
# own deterministic per-ticker structure pick -- the "structures" field on whichever of
# trade_volatility_scan's existing top_long_setups/top_short_setups rows matches SPY or QQQ this
# checkpoint (the vendor's /top-setups response is the only one of its endpoints that actually
# returns a structure; /market-structure does not). day_strategy only (today's own session, not
# the 2-5 session or 1-4 week horizons, which the vendor's current-regime pick does not speak to)
# gets this comparison field: it never overwrites the registered setup's own "structure" field
# above, it only states agreement/disagreement between the two, surfaced as a sentence in
# _narrative_strategy.
REQUIREMENTS["day_strategy"].append("tv_structure_check")
REQUIREMENTS["horizon_comparison"] = ["morning_baseline", "prior_checkpoint", "current",
    "forward_options", "futures_confirmation", "alignment", "changes"]
REQUIREMENTS["adaptation_rules"] = ["activate", "cancel", "switch", "stand_aside",
    "existing_positions", "reassessment"]
REQUIREMENTS["data_integrity"] = ["contract", "source_clocks", "coverage", "historical_fields",
    "unavailable_fields", "producer_failures", "model_prose_policy", "execution_scope", "format", "refresh_attempts"]
# Leron, 2026-10-13: "which stock show the best opprotunity to go long in the short term
# bullish or bearish... what are the strikes and expirations", "put call ratio does is
# support the read", "is it widenening or collapsing". TradingVolatility v2's own deterministic
# engine already computes all of this, cross-ticker, versioned; this section surfaces its
# ranked long/short setups, income (CC/CSP) setups and index put/call-ratio + IV-trend reads.
# Every value here is TradingVolatility's own output, clearly sourced -- nothing invented.
REQUIREMENTS["trade_volatility_scan"] = ["top_long_setups", "top_short_setups", "income_setups",
    "put_call_ratio", "expected_move_trend"]
REQUIRED_BLOCKS = tuple(REQUIREMENTS)
CONTRACT_VERSION = "2026-10-14.1"
FLOW_SOURCE = "ThetaData Pro trade-time NBBO flow v1"
# Display/completeness freshness only -- how old a field's own observation may be before it
# stops counting as "live" for the reader and for report_completeness. Leron, 2026-10-12: "i
# dont need them live at the exact instant as long as thier no older than 10 mins" -- raised
# from 90s. This is NOT the options-execution BBO freshness gate (qualify_package() in
# report_ledger.py, the fill-sim check in tradier_report_source.py, and the ENTRY_READY
# confirmation-evidence check in report_policy.py all keep their own independent <=90s
# check -- RULES' "fresh BBO <=90s" still holds for anything that could become a simulated
# fill). Those stay untouched on purpose: a quote being too old to trust for a trade and a
# field being too old to call "live" in the report text are different risks.
LIVE_MAX_AGE_SECONDS = 600
CHART_FORMAT = "PNG"
PROHIBITED_VISUALS = ("mermaid", "ascii", "decorative_ai")

# Fields that are permanently, structurally unavailable regardless of data quality -- kept in
# the contract because the disclosure must stay explicit, but excluded from the completeness
# bar below because no amount of good data can ever make them live. Leron, 2026-10-12: "why
# does it always say incomplete" -- futures_context.basis is unconditionally unavailable()
# every single report (full_options_report.py: "Exact same-time futures vs cash-index basis
# unavailable; SPY is not substituted for SPX"), which alone made complete_live_data
# impossible forever, for every report kind, regardless of how fresh everything else was.
# Leron, 2026-10-15: same question again -- the 2026-10-12 fix only covered that one field.
# full_options_report.py/report_producers.py build macro.* and the rest of futures_context.*
# with observation(..., delayed=True), which report_producers.observation() hardcodes to
# status="historical" no matter how fresh the underlying fetch is (FRED daily Treasury
# yields, Yahoo 5-minute-delayed ES/NQ continuous futures). Those fields can never be "live"
# at any time of day, on any report kind -- same permanent-impossibility class as basis.
DESIGNED_UNAVAILABLE = {
    ("futures_context", "basis"),
    ("futures_context", "es_mes"),
    ("futures_context", "nq"),
    ("futures_context", "overnight_range"),
    ("macro", "rates"),
    ("macro", "curve"),
    ("macro", "dollar"),
    ("macro", "fx"),
    ("macro", "commodities"),
    ("macro", "move"),
    # Same permanent-impossibility class, different mechanism: report_policy.normalize_item()
    # unconditionally relabels any producer value older than 90 seconds as "historical" with
    # this exact reason, regardless of the field's own 600s live window. TradingVolatility's
    # vendor engine is a periodic snapshot, not a sub-90s feed, and fetch+render alone takes
    # longer than that -- these fields are for all practical purposes never "live".
    ("candidate_analysis", "symbols"),
    ("candidate_analysis", "catalysts"),
    ("candidate_analysis", "quote_chain_freshness"),
    ("candidate_analysis", "liquidity"),
    ("candidate_analysis", "conditional_triggers"),
    ("engine_consensus", "squeeze"),
    ("engine_consensus", "trading_volatility_status"),
    ("engine_consensus", "contradictions"),
    ("trade_volatility_scan", "top_long_setups"),
    ("trade_volatility_scan", "top_short_setups"),
    ("trade_volatility_scan", "income_setups"),
    ("trade_volatility_scan", "put_call_ratio"),
    ("trade_volatility_scan", "expected_move_trend"),
    ("day_strategy", "tv_structure_check"),
    ("near_forward_strategy", "tv_structure_check"),
    ("forward_strategy", "tv_structure_check"),
}

# Fields that are unavailable/historical only because this is the day's FIRST checkpoint,
# generated before the market opens (kind="morning", sent 7:35 AM CT, open is 8:30 AM CT).
# Every one of these is produced from live market/options activity (realized vol, chain IV,
# trade-time flow, breadth, value area, gamma, same-day baselines) and genuinely refreshes to
# "live" once trading resumes -- unlike DESIGNED_UNAVAILABLE above, this is NOT a permanent
# exemption: a market_open or intraday report still showing these as historical/unavailable
# is a real problem and must still read INCOMPLETE. Leron, 2026-10-15: "loosen it" -- scoped
# to the morning checkpoint only, so a normal pre-market morning reads COMPLETE.
MORNING_PRE_OPEN_UNAVAILABLE = {
    ("breadth", "advance_decline"), ("breadth", "up_down_volume"),
    ("breadth", "percent_above_vwap"), ("breadth", "new_highs_lows"),
    ("candidate_analysis", "surface"),
    # Options cannot trade before the 8:30 AM open -- "No freshly qualified conditional
    # package; options closed..." is unconditionally true at 7:35 AM, not a "no trigger
    # fired" gap. A market_open/intraday report with these still unavailable is real news.
    ("contract_packages", "expiry"), ("contract_packages", "strikes"), ("contract_packages", "legs"),
    ("contract_packages", "bid_ask"), ("contract_packages", "greeks"), ("contract_packages", "oi"),
    ("contract_packages", "volume"), ("contract_packages", "debit_credit"),
    ("contract_packages", "max_risk_reward"), ("contract_packages", "breakeven"), ("contract_packages", "liquidity"),
    ("day_strategy", "thesis"), ("day_strategy", "evidence"), ("day_strategy", "conflicts"), ("day_strategy", "contracts"),
    ("near_forward_strategy", "thesis"), ("near_forward_strategy", "evidence"),
    ("near_forward_strategy", "conflicts"), ("near_forward_strategy", "contracts"),
    ("forward_strategy", "thesis"), ("forward_strategy", "evidence"),
    ("forward_strategy", "conflicts"), ("forward_strategy", "contracts"),
    ("expected_move", "percent"), ("expected_move", "dollars"), ("expected_move", "lower"),
    ("expected_move", "upper"), ("expected_move", "reference_spot"), ("expected_move", "expiry"),
    ("expected_move", "method"), ("expected_move", "budget_used"), ("expected_move", "price_location"),
    ("flow", "provider_provenance"), ("flow", "exchange_timestamp"), ("flow", "retrieval_timestamp"),
    ("flow", "age"), ("flow", "classified_coverage"), ("flow", "unclassified_coverage"),
    ("flow", "calls_bought"), ("flow", "calls_sold"), ("flow", "puts_bought"), ("flow", "puts_sold"),
    ("flow", "expiry_buckets"), ("flow", "price_vix_confirmation"),
    ("forward_strikes", "expiries"), ("forward_strikes", "strikes"), ("forward_strikes", "contracts"),
    ("forward_strikes", "premium"), ("forward_strikes", "prints"),
    ("forward_strikes", "contemporaneous_bid_ask"), ("forward_strikes", "initiation_estimate"),
    ("futures_context", "index_confirmation"),
    ("gamma", "coverage"), ("gamma", "net_gex"), ("gamma", "flip"), ("gamma", "walls"), ("gamma", "expiry_buckets"),
    ("horizon_comparison", "morning_baseline"), ("horizon_comparison", "current"),
    ("horizon_comparison", "forward_options"), ("horizon_comparison", "futures_confirmation"),
    ("market_control", "control_side"), ("market_control", "control_evidence"),
    ("market_control", "control_confidence"), ("market_control", "forward_control_outlook"),
    ("morning_comparison", "morning_timestamp"), ("morning_comparison", "price_location"),
    ("morning_comparison", "move_usage"), ("morning_comparison", "chop_status"),
    ("morning_comparison", "stall_risk"), ("morning_comparison", "setup_status"),
    ("morning_comparison", "regime_shift"), ("morning_comparison", "regime_label_shift"),
    ("premium_selling", "suitability"), ("premium_selling", "iv_rv_meaning_today"),
    ("premium_selling", "forward_implications"), ("premium_selling", "credit_structure_fit"),
    ("premium_selling", "avoid"),
    ("profile", "poc"), ("profile", "vah"), ("profile", "val"), ("profile", "hvn"),
    ("profile", "lvn"), ("profile", "method"), ("profile", "acceptance_rejection"),
    ("range_stall", "chop_low"), ("range_stall", "midpoint"), ("range_stall", "chop_high"),
    ("range_stall", "room_to_edges"), ("range_stall", "two_fresh_confirmations"),
    ("range_stall", "actual_rejection"), ("range_stall", "first_touch_watch"), ("range_stall", "breakout_ends_chop"),
    ("risk_on_defensive", "verdict"), ("risk_on_defensive", "evidence"), ("risk_on_defensive", "conflicts"),
    ("risk_on_defensive", "change_vs_baselines"), ("risk_on_defensive", "regime_label"),
    ("sector_credit", "relative_returns"), ("sector_credit", "leadership"), ("sector_credit", "credit_confirmation"),
    ("smile", "expiry"), ("smile", "put_25d_iv"), ("smile", "atm_iv"), ("smile", "call_25d_iv"),
    ("smile", "strikes"), ("smile", "delta_method"),
    ("surface", "atm_iv"), ("surface", "skew_25d"), ("surface", "term_0dte"), ("surface", "term_1_5dte"),
    ("surface", "term_6_20dte"), ("surface", "term_21plus"), ("surface", "iv_vs_realized"),
    ("surface", "vix_family"), ("surface", "interpretation"),
    ("visuals", "market_map_png"), ("visuals", "smile_term_png"), ("visuals", "flow_png"),
    ("visuals", "baseline_comparison_png"), ("visuals", "gamma_expiry_png"), ("visuals", "sector_credit_png"),
    ("visuals", "surface_png"), ("visuals", "term_structure_png"), ("visuals", "volume_profile_png"),
}

def validate_report(blocks, kind=None):
    """Validate actual structured output, including explicit per-field disclosures.

    Each required field is {value: ..., status: live|historical|unavailable,
    reason: ..., source_timestamp: ..., age_seconds: ..., confidence: ...}.
    Historical and unavailable fields never satisfy complete live data, except the
    designed-permanent exemptions above, and (for kind="morning" only) fields that are
    structurally pre-open.
    """
    import math
    from .report_policy import finite_tree, parse_clock
    errors, unavailable = [], []
    for name, fields in REQUIREMENTS.items():
        block = blocks.get(name)
        if not isinstance(block, dict):
            errors.append(name + ": omitted")
            continue
        for field in fields:
            key = name + "." + field
            item = block.get(field)
            if not isinstance(item, dict):
                errors.append(key + ": omitted")
                continue
            status = item.get("status")
            if not finite_tree(item):
                errors.append(key + ": nonfinite value")
            if status == "unavailable":
                unavailable.append(key)
                if not item.get("reason"):
                    errors.append(key + ": missing reason")
            elif status == "historical":
                unavailable.append(key)
                age = item.get("age_seconds")
                if (item.get("value") is None or not parse_clock(item.get("source_timestamp"))
                        or type(age) not in (int, float) or not math.isfinite(age) or age < 0):
                    errors.append(key + ": missing historical age/source")
            elif status == "live":
                age = item.get("age_seconds")
                if item.get("value") is None:
                    errors.append(key + ": missing value")
                if not parse_clock(item.get("source_timestamp")) or type(age) not in (int, float) or not math.isfinite(age) or not 0 <= age <= LIVE_MAX_AGE_SECONDS:
                    errors.append(key + ": stale or untimestamped")
                if item.get("confidence") not in ("HIGH", "MEDIUM"):
                    errors.append(key + ": invalid confidence")
            else:
                errors.append(key + ": invalid status")
    exempt = DESIGNED_UNAVAILABLE | (MORNING_PRE_OPEN_UNAVAILABLE if kind == "morning" else set())
    blocking_unavailable = [k for k in unavailable if tuple(k.split(".", 1)) not in exempt]
    return {"contract_version": CONTRACT_VERSION, "publishable": not errors,
            "complete_live_data": not errors and not blocking_unavailable,
            "errors": errors, "unavailable_fields": unavailable}

def completeness(blocks, rendered):
    """Compatibility check for older consumers; not actual renderer validation."""
    omitted = [name for name in REQUIRED_BLOCKS if name not in set(rendered)]
    missing = [name for name in REQUIRED_BLOCKS if not blocks.get(name, {}).get("available")]
    return {"publishable": not omitted, "all_data_live": not missing,
            "omitted_blocks": omitted, "unavailable_blocks": missing}


def prepare_report_delivery(payload):
    """Render the contract fields and disclosures, then gate delivery on them.

    Supplied structured fields are canonical; legacy prose is supplementary.
    Missing fields are disclosed, not promoted to live data or fabricated.
    """
    from .report_policy import normalize_blocks, render_markdown, policy_identity, add_integrity
    blocks = normalize_blocks(payload.get("report_blocks") or {})
    for name, fields in REQUIREMENTS.items():
        blocks.setdefault(name, {})
        for field in fields:
            blocks[name].setdefault(field, {"status": "unavailable", "reason": "Producer supplied no verified observation."})
    for name in ("day_strategy", "near_forward_strategy", "forward_strategy"):
        if blocks[name]["status"].get("value") == "ENTRY_READY" and blocks[name]["contracts"].get("status") != "live":
            blocks[name]["status"]["value"] = "WATCH"
            blocks[name]["status"]["reason"] = "Executable quotes aged or failed qualification before publication"
    add_integrity(blocks, payload)
    for name, fields in REQUIREMENTS.items():
        block = blocks.setdefault(name, {})
        if not isinstance(block, dict):
            block = {}
            blocks[name] = block
        for field in fields:
            if field not in block:
                block[field] = {"status": "unavailable",
                                "reason": "Producer supplied no verified observation."}
    check = validate_report(blocks, kind=payload.get("kind"))
    payload["report_validation"] = check
    payload["report_blocks"] = blocks
    if not check["publishable"]:
        return check
    # Provider observations are canonical. Arbitrary model prose is retained for
    # diagnostics only and cannot introduce unsupported facts into delivery.
    if not payload.get("report_policy"):
        payload.setdefault("report_unverified_prose", payload.get("report_markdown") or "")
    payload["report_policy"] = policy_identity()
    payload["report_completeness"] = "COMPLETE" if check["complete_live_data"] else "INCOMPLETE"
    payload["report_markdown"] = render_markdown(payload)
    payload["report_original_markdown"] = ""  # legacy callers cannot reinsert prose
    final_check = validate_rendered_report(payload)
    payload["report_validation"] = final_check
    return final_check


def validate_rendered_report(payload):
    """Intraday publication gate: validate fields, final prose and PNG references."""
    import re
    from datetime import datetime, timezone
    blocks = payload.get("report_blocks") or {}
    check = validate_report(blocks, kind=payload.get("kind"))
    errors = list(check["errors"])
    markdown = payload.get("report_markdown") or ""
    now = datetime.now(timezone.utc)
    from .report_policy import policy_identity, validate_semantics, SECTION_SUMMARY_SECTIONS
    if payload.get("report_policy"):
        if payload["report_policy"] != policy_identity():
            errors.append("Report policy version/hash mismatch")
        for heading in ("Today’s mission", "30-second scoreboard", "Today vs forward",
                        "Market story", "Edge board", "Biggest traps", "If/then day plan"):
            if heading not in markdown:
                errors.append("Missing presentation section: " + heading)
        errors.extend(validate_semantics(payload, now))
    for name, fields in REQUIREMENTS.items():
        heading = name.replace("_", " ")
        # Canonical headings allow mechanical verification of the final document.
        match = re.search(r"(?im)^#{1,6}\s+" + re.escape(heading) + r"\s*$", markdown)
        if not match:
            errors.append(name + ": missing rendered heading")
            continue
        tail = markdown[match.end():]
        section = re.split(r"(?m)^#{1,6}\s", tail, maxsplit=1)[0]
        for field in fields:
            item = blocks.get(name, {}).get(field, {})
            # A section in SECTION_SUMMARY_SECTIONS renders a narrative summary instead of a
            # per-field bullet, by design (render_markdown / report_view's fields_html branch) --
            # the literal field NAME is no longer expected to appear as text. Only sections that
            # still fall through to the raw-field-bullet branch (none today; a defensive fallback
            # for any future section added to REQUIREMENTS without a matching narrative builder)
            # are held to this literal-presence check.
            if name not in SECTION_SUMMARY_SECTIONS and field not in section:
                errors.append(name + "." + field + ": missing rendered field")
            if item.get("status") == "live":
                try:
                    stamp = datetime.fromisoformat(item["source_timestamp"].replace("Z", "+00:00"))
                    if stamp.tzinfo is None:
                        raise ValueError("timezone required")
                    age = (now - stamp).total_seconds()
                    if not 0 <= age <= LIVE_MAX_AGE_SECONDS:
                        errors.append(name + "." + field + ": stale at publication")
                except (ValueError, TypeError, KeyError):
                    errors.append(name + "." + field + ": invalid exchange timestamp")
            if name == "visuals" and field.endswith("_png") and item.get("status") in ("live", "historical"):
                ref = str(item.get("value") or "")
                embedded = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", markdown)
                if not ref.lower().endswith(".png") or ref not in embedded:
                    errors.append(field + ": PNG not embedded")
    if "```mermaid" in markdown.lower():
        errors.append("Mermaid is prohibited")
    manifest=blocks.get('visuals',{}).get('delivery_manifest',{})
    if manifest.get('status') in ('live','historical'):
        value=manifest.get('value') or {}
        assets=value.get('images') or []
        expected=set((payload.get('chart_urls') or {}).keys())
        if not expected or {a.get('name') for a in assets}!=expected or len(assets)!=len(expected):
            errors.append('visuals.delivery_manifest: missing/duplicate persisted images')
        for asset in assets:
            if (asset.get('validated') is not True or asset.get('content_type')!='image/png'
                    or not re.fullmatch(r'[a-f0-9]{64}',str(asset.get('sha256') or ''))
                    or str(asset.get('sha256',''))[:32]!=asset.get('chart_id')
                    or asset.get('width',0)<1000 or asset.get('height',0)<600
                    or asset.get('size_bytes',0)<=0):
                errors.append('visuals.delivery_manifest: invalid persisted image proof')
    check["errors"] = errors
    check["publishable"] = not errors
    check["complete_live_data"] = check["complete_live_data"] and not errors
    check["required_sections"] = len(REQUIREMENTS)
    check["required_fields"] = sum(len(fields) for fields in REQUIREMENTS.values())
    return check
