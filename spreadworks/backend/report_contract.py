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
        "theta_provenance",
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
        "image_inspection"
    ]
}
REQUIRED_BLOCKS = tuple(REQUIREMENTS)
CONTRACT_VERSION = "2026-10-02.2"
FLOW_SOURCE = "ThetaData live trades with contemporaneous ThetaData bid/ask"
LIVE_MAX_AGE_SECONDS = 90
CHART_FORMAT = "PNG"
PROHIBITED_VISUALS = ("mermaid", "ascii", "decorative_ai")

def validate_report(blocks):
    """Validate actual structured output, including explicit per-field disclosures.
    
    Each required field is {value: ..., status: live|historical|unavailable,
    reason: ..., source_timestamp: ..., age_seconds: ..., confidence: ...}.
    Historical and unavailable fields never satisfy complete live data.
    """
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
            if status == "unavailable":
                unavailable.append(key)
                if not item.get("reason"):
                    errors.append(key + ": missing reason")
            elif status == "historical":
                unavailable.append(key)
                if not item.get("source_timestamp") or item.get("age_seconds") is None:
                    errors.append(key + ": missing historical age/source")
            elif status == "live":
                age = item.get("age_seconds")
                if item.get("value") is None:
                    errors.append(key + ": missing value")
                if not item.get("source_timestamp") or not isinstance(age, (int, float)) or not 0 <= age <= LIVE_MAX_AGE_SECONDS:
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
