#!/usr/bin/env python3
"""GOLIATH Phase 3 -- sample gate-failure rows for Leron review.

Per kickoff prompt (Phase 3 HARD STOP): print 5 sample
goliath_gate_failures rows to stdout so Leron can eyeball
diagnostic richness before Phase 4 begins.

Each printed row mirrors exactly what the orchestrator would persist
to the goliath_gate_failures table (migration 028) -- timestamp,
letf_ticker, underlying_ticker, failed_gate, failure_outcome,
gates_passed_before_failure, attempted_structure, failure_reason,
context.

Run from repo root:
    python scripts/goliath_gate_failure_samples.py
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading.goliath.gates.orchestrator import (  # noqa: E402
    GateInputs,
    orchestrate_entry,
)
from trading.goliath.models import GoliathConfig  # noqa: E402
from trading.goliath.strike_mapping.engine import (  # noqa: E402
    OptionLeg,
    TradeStructure,
)
from trading.goliath.strike_mapping.letf_mapper import LETFTarget  # noqa: E402
from trading.goliath.strike_mapping.wall_finder import (  # noqa: E402
    GammaStrike,
    Wall,
)


_TODAY = date(2026, 5, 4)


def _config(letf: str, underlying: str) -> GoliathConfig:
    return GoliathConfig(
        instance_name=f"GOLIATH-{letf}",
        letf_ticker=letf,
        underlying_ticker=underlying,
    )


def _structure(*, sp_oi=500, lp_oi=500, lc_oi=500,
               sp_bid=0.50, sp_ask=0.52,
               lc_bid=0.28, lc_ask=0.32) -> TradeStructure:
    sp = OptionLeg(9.0, sp_bid, sp_ask, sp_oi, "put")
    lp = OptionLeg(8.5, 0.18, 0.22, lp_oi, "put")
    lc = OptionLeg(12.0, lc_bid, lc_ask, lc_oi, "call")
    sp_mid = (sp_bid + sp_ask) / 2
    lc_mid = (lc_bid + lc_ask) / 2
    return TradeStructure(
        short_put=sp, long_put=lp, long_call=lc,
        put_spread_credit=sp_mid - 0.20,
        long_call_cost=lc_mid,
        net_cost=lc_mid - (sp_mid - 0.20),
        wall=Wall(strike=191.0, gamma=8.0, median_local_gamma=1.0, concentration_ratio=8.0),
        letf_target=LETFTarget(
            target_strike=9.0, band_low=8.5, band_high=9.5,
            predicted_letf_return=-0.10, vol_drag=-0.005, te_band=0.056,
        ),
    )


def _good_inputs(letf: str, underlying: str, **overrides) -> GateInputs:
    base = dict(
        letf_ticker=letf, underlying_ticker=underlying,
        spy_net_gex=2.0e9,
        underlying_net_gex=1.0e8,
        underlying_strikes=[
            GammaStrike(190.0, 1.0), GammaStrike(191.0, 8.0),
            GammaStrike(195.0, 1.0), GammaStrike(200.0, 1.0),
            GammaStrike(205.0, 1.0), GammaStrike(210.0, 1.0),
        ],
        underlying_spot=200.0,
        next_earnings_date=_TODAY + timedelta(days=30),
        iv_rank=75.0,
        underlying_50d_ma=185.0,
        open_position_count=0,
        config=_config(letf, underlying),
        attempted_structure=_structure(),
        today=_TODAY,
    )
    base.update(overrides)
    return GateInputs(**base)


def _structure_json(s):
    if s is None:
        return None
    return {
        "short_put_strike": s.short_put.strike,
        "long_put_strike": s.long_put.strike,
        "long_call_strike": s.long_call.strike,
        "put_spread_credit": round(s.put_spread_credit, 4),
        "long_call_cost": round(s.long_call_cost, 4),
        "net_cost": round(s.net_cost, 4),
    }


def _row(scenario: str, inputs: GateInputs) -> dict:
    decision = orchestrate_entry(inputs)
    failed = decision.first_failure
    passed_before = [r.gate for r in decision.chain if r.passed]
    return {
        "scenario": scenario,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "letf_ticker": inputs.letf_ticker,
        "underlying_ticker": inputs.underlying_ticker,
        "failed_gate": failed.gate if failed else None,
        "failure_outcome": failed.outcome.value if failed else None,
        "gates_passed_before_failure": passed_before,
        "attempted_structure": _structure_json(inputs.attempted_structure),
        "failure_reason": failed.reason if failed else None,
        "context": failed.context if failed else None,
    }


def main() -> int:
    scenarios = [
        ("G01_SPY_EXTREME_NEGATIVE",
            _good_inputs("MSTU", "MSTR", spy_net_gex=-5.0e9)),
        ("G02_TSLA_UNDERLYING_NEGATIVE",
            _good_inputs("TSLL", "TSLA", underlying_net_gex=-1.0e9)),
        ("G04_NVDA_EARNINGS_IN_3_DAYS",
            _good_inputs("NVDL", "NVDA",
                         next_earnings_date=_TODAY + timedelta(days=3))),
        ("G05_COIN_IV_RANK_COLD_START",
            _good_inputs("CONL", "COIN", iv_rank=None)),
        ("G07_AMD_LONG_CALL_WIDE_SPREAD",
            _good_inputs("AMDL", "AMD",
                         attempted_structure=_structure(lc_bid=0.20, lc_ask=0.40))),
    ]

    print("=" * 78)
    print("GOLIATH Phase 3 -- 5 sample goliath_gate_failures rows")
    print("=" * 78)
    print()

    for name, inputs in scenarios:
        row = _row(name, inputs)
        print(f"--- {name} ---")
        print(json.dumps(row, indent=2, default=str))
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
