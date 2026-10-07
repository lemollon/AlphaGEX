"""Versioned report requirements. Unavailable fields must be disclosed, never omitted."""
REQUIREMENTS = {
    "risk_on_defensive": [
        "verdict",
        "evidence",
        "conflicts",
        "change_vs_baselines"
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
        "setup_status"
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
        "risk",
        "session",
        "squeeze",
        "hunt",
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
REQUIREMENTS["horizon_comparison"] = ["morning_baseline", "prior_checkpoint", "current",
    "forward_options", "futures_confirmation", "alignment", "changes"]
REQUIREMENTS["adaptation_rules"] = ["activate", "cancel", "switch", "stand_aside",
    "existing_positions", "reassessment"]
REQUIREMENTS["data_integrity"] = ["contract", "source_clocks", "coverage", "historical_fields",
    "unavailable_fields", "producer_failures", "model_prose_policy", "execution_scope", "format", "refresh_attempts"]
REQUIRED_BLOCKS = tuple(REQUIREMENTS)
CONTRACT_VERSION = "2026-10-07.1"
FLOW_SOURCE = "ThetaData Pro trade-time NBBO flow v1"
LIVE_MAX_AGE_SECONDS = 90
CHART_FORMAT = "PNG"
PROHIBITED_VISUALS = ("mermaid", "ascii", "decorative_ai")

def validate_report(blocks):
    """Validate actual structured output, including explicit per-field disclosures.
    
    Each required field is {value: ..., status: live|historical|unavailable,
    reason: ..., source_timestamp: ..., age_seconds: ..., confidence: ...}.
    Historical and unavailable fields never satisfy complete live data.
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
    return {"contract_version": CONTRACT_VERSION, "publishable": not errors,
            "complete_live_data": not errors and not unavailable,
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
    check = validate_report(blocks)
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
    check = validate_report(blocks)
    errors = list(check["errors"])
    markdown = payload.get("report_markdown") or ""
    now = datetime.now(timezone.utc)
    from .report_policy import policy_identity, validate_semantics
    if payload.get("report_policy"):
        if payload["report_policy"] != policy_identity():
            errors.append("Report policy version/hash mismatch")
        for heading in ("Today’s mission", "30-second scoreboard", "Today vs forward"):
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
            if field not in section:
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
