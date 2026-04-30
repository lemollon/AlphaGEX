"""GoliathEngine -- wires Phase 2 (strike mapping) + Phase 3 (gates) +
Phase 5 (sizing) + Phase 4 (management) into the bot-level service.

Per master spec section 9.2:
    "Stateless service -- all logic, no state."

[GOLIATH-DELTA] yellow -- spec adjustment:
The recovered signature shows ``evaluate_entry(instance) -> TradeStructure``.
For v0.2 testability we surface market data in the call signature
(MarketSnapshot) rather than fetching inside the engine. The runner
(main.py) is responsible for assembling the snapshot from TV/yfinance.
This lets the engine remain stateless and unit-testable with synthetic
inputs. v0.3 may add an internal-fetcher convenience overload.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Sequence

from .configs import InstanceConfig
from .gates.orchestrator import EntryDecision, GateInputs, orchestrate_entry
from .instance import GoliathInstance
from .management.engine import evaluate_all as evaluate_management
from .management.state import ManagementAction, Position
from .models import GoliathConfig
from .sizing import SizingResult, calculate_contracts
from .strike_mapping.engine import (
    OptionLeg,
    TradeStructure,
    build_trade_structure,
)
from .strike_mapping.wall_finder import GammaStrike

# Standard equity-option multiplier (matches instance.py).
_OPTION_MULTIPLIER = 100
_DEFAULT_DTE_YEARS = 7.0 / 365.0


@dataclass
class MarketSnapshot:
    """Inputs the engine needs to evaluate one entry."""

    spy_net_gex: float
    underlying_net_gex: float
    underlying_strikes: Sequence[GammaStrike]
    underlying_spot: float
    letf_spot: float
    letf_chain: dict[tuple[float, str], OptionLeg]
    sigma_annualized: float
    t_years: float = _DEFAULT_DTE_YEARS
    next_earnings_date: Optional[date] = None
    iv_rank: Optional[float] = None
    underlying_50d_ma: Optional[float] = None


@dataclass
class PlatformContext:
    """Platform-wide aggregates needed for G10 and sizing."""

    open_position_count: int
    open_dollars_at_risk: float


@dataclass
class EngineEntryDecision:
    """Output of GoliathEngine.evaluate_entry."""

    structure: Optional[TradeStructure]
    gate_chain: list = field(default_factory=list)
    sizing: Optional[SizingResult] = None
    contracts_to_trade: int = 0

    @property
    def approved(self) -> bool:
        return self.structure is not None and self.contracts_to_trade > 0


def _instance_to_goliath_config(cfg: InstanceConfig) -> GoliathConfig:
    """Build a GoliathConfig (Phase 1.5 calibration dataclass) from an
    InstanceConfig (per-LETF runtime config). Calibration params stay at
    spec defaults until Step 9 results are committed."""
    return GoliathConfig(
        instance_name=cfg.bot_guard_tag,
        letf_ticker=cfg.letf_ticker,
        underlying_ticker=cfg.underlying_ticker,
    )


class GoliathEngine:
    """Stateless service -- entry + management decision logic."""

    def evaluate_entry(
        self,
        instance: GoliathInstance,
        snapshot: MarketSnapshot,
        platform: PlatformContext,
        now: Optional[datetime] = None,
    ) -> EngineEntryDecision:
        """Run gates + structure + sizing. Returns EngineEntryDecision."""
        config = _instance_to_goliath_config(instance.config)

        attempted = build_trade_structure(
            underlying_strikes=snapshot.underlying_strikes,
            underlying_spot=snapshot.underlying_spot,
            letf_spot=snapshot.letf_spot,
            sigma_annualized=snapshot.sigma_annualized,
            t_years=snapshot.t_years,
            letf_chain=snapshot.letf_chain,
            config=config,
        )

        gate_inputs = GateInputs(
            letf_ticker=instance.letf_ticker,
            underlying_ticker=instance.underlying_ticker,
            spy_net_gex=snapshot.spy_net_gex,
            underlying_net_gex=snapshot.underlying_net_gex,
            underlying_strikes=snapshot.underlying_strikes,
            underlying_spot=snapshot.underlying_spot,
            next_earnings_date=snapshot.next_earnings_date,
            iv_rank=snapshot.iv_rank,
            underlying_50d_ma=snapshot.underlying_50d_ma,
            open_position_count=platform.open_position_count,
            config=config,
            attempted_structure=attempted,
            today=now.date() if now else None,
        )
        gate_decision: EntryDecision = orchestrate_entry(gate_inputs)

        if gate_decision.structure is None:
            return EngineEntryDecision(
                structure=None,
                gate_chain=list(gate_decision.chain),
                sizing=None,
                contracts_to_trade=0,
            )

        # Compute defined-max-loss per contract in dollars.
        # spread width = short_put_strike - long_put_strike (raw).
        # defined_max_loss_raw = width - put_spread_credit.
        # Convert to dollars via the option multiplier.
        s = gate_decision.structure
        spread_width = s.short_put.strike - s.long_put.strike
        defined_max_per_contract = (spread_width - s.put_spread_credit) * _OPTION_MULTIPLIER
        if defined_max_per_contract <= 0:
            # Degenerate (credit >= width); refuse and return.
            return EngineEntryDecision(
                structure=None,
                gate_chain=list(gate_decision.chain),
                sizing=None,
                contracts_to_trade=0,
            )

        sizing = calculate_contracts(
            letf_ticker=instance.letf_ticker,
            defined_max_loss_per_contract=defined_max_per_contract,
            instance_open_dollars=instance.open_dollars_at_risk(),
            platform_open_dollars=platform.open_dollars_at_risk,
        )

        approved_structure = s if sizing.contracts > 0 else None
        return EngineEntryDecision(
            structure=approved_structure,
            gate_chain=list(gate_decision.chain),
            sizing=sizing,
            contracts_to_trade=sizing.contracts,
        )

    def manage_open_positions(
        self,
        instance: GoliathInstance,
        now: Optional[datetime] = None,
    ) -> list[tuple[Position, ManagementAction]]:
        """Run the management trigger chain on every open position.

        Returns a list of (position, fired_action) for positions where a
        trigger fired this cycle. Empty list when no triggers fire.
        """
        actions: list[tuple[Position, ManagementAction]] = []
        for pos in list(instance.open_positions):
            action = evaluate_management(pos, now=now)
            if action is not None:
                actions.append((pos, action))
        return actions
