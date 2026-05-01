"""GOLIATH runner -- entry point that cycles through all 5 instances.

Per master spec section 9.2 + kickoff prompt:
    "trading/goliath/main.py -- entry point: run all 5 instances"

Two cycles, both runnable independently or together:
    run_entry_cycle()       -> evaluate_entry on each non-killed instance
    run_management_cycle()  -> manage_open_positions on each open position

Market-data fetching, broker execution, and position persistence are
delegated to injected callables so this module stays unit-testable
without TV API or Tradier credentials. The defaults raise NotImplementedError
-- the live runner (Phase 6 follow-on or Phase 7) will wire them up.

Usage:
    python -m trading.goliath.main --cycle entry
    python -m trading.goliath.main --cycle management
    python -m trading.goliath.main --cycle both
    python -m trading.goliath.main --dry-run   (logs only; no audit / no broker)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from trading.goliath.audit import recorder as audit_recorder  # noqa: E402
from trading.goliath.configs import all_instances  # noqa: E402
from trading.goliath.engine import (  # noqa: E402
    EngineEntryDecision,
    GoliathEngine,
    MarketSnapshot,
    PlatformContext,
)
from trading.goliath.instance import GoliathInstance, build_all_instances  # noqa: E402
from trading.goliath.monitoring import alerts as monitoring_alerts  # noqa: E402
from trading.goliath.monitoring import heartbeat as monitoring_heartbeat  # noqa: E402

logger = logging.getLogger(__name__)


SnapshotFetcher = Callable[[GoliathInstance], MarketSnapshot]
PlatformFetcher = Callable[[dict[str, GoliathInstance]], PlatformContext]
BrokerExecutor = Callable[[GoliathInstance, EngineEntryDecision], Optional[str]]


def _default_snapshot_fetcher(_inst: GoliathInstance) -> MarketSnapshot:
    raise NotImplementedError(
        "Snapshot fetcher not wired -- pass a real fetcher to Runner. "
        "Live wiring lands with the TV-client + Tradier integration."
    )


def _default_platform_fetcher(_instances: dict[str, GoliathInstance]) -> PlatformContext:
    return PlatformContext(open_position_count=0, open_dollars_at_risk=0.0)


def _default_broker_executor(
    _inst: GoliathInstance, _decision: EngineEntryDecision
) -> Optional[str]:
    raise NotImplementedError(
        "Broker executor not wired -- pass a real executor to Runner. "
        "Default refuses to fake fills (paper-only is configured per-instance)."
    )


@dataclass
class CycleResult:
    """Summary of one entry or management cycle across all instances."""

    instances_evaluated: int = 0
    entries_approved: int = 0
    entries_filled: int = 0
    triggers_fired: int = 0
    skips: list[str] = field(default_factory=list)


@dataclass
class Runner:
    """Top-level orchestrator that cycles through every GOLIATH instance."""

    engine: GoliathEngine = field(default_factory=GoliathEngine)
    snapshot_fetcher: SnapshotFetcher = _default_snapshot_fetcher
    platform_fetcher: PlatformFetcher = _default_platform_fetcher
    broker_executor: BrokerExecutor = _default_broker_executor
    instances: dict[str, GoliathInstance] = field(
        default_factory=lambda: build_all_instances(all_instances())
    )
    dry_run: bool = False

    def run_entry_cycle(self, now: Optional[datetime] = None) -> CycleResult:
        """Run evaluate_entry on every non-killed instance."""
        now = now or datetime.now(timezone.utc)
        result = CycleResult()
        platform = self.platform_fetcher(self.instances)

        for name, instance in self.instances.items():
            result.instances_evaluated += 1

            # Heartbeat per-instance per-cycle. Best-effort, never raises.
            if not self.dry_run:
                monitoring_heartbeat.record_heartbeat(
                    bot_name=name,
                    status="KILLED" if instance.is_killed else "OK",
                    details={"cycle": "entry"},
                )

            if instance.is_killed:
                result.skips.append(f"{name}: kill_active")
                logger.info("skip %s -- instance kill active", name)
                continue

            try:
                snapshot = self.snapshot_fetcher(instance)
            except Exception as exc:  # noqa: BLE001
                result.skips.append(f"{name}: snapshot_error={exc!r}")
                logger.warning("skip %s -- snapshot fetch failed: %r", name, exc)
                # Track TV API failures so the rate-limit alert can fire.
                # Generic snapshot errors count toward the same window;
                # caller can refine if/when we split TV vs yfinance signals.
                if not self.dry_run:
                    monitoring_alerts.record_tv_api_failure()
                    if monitoring_alerts.check_tv_api_failure_rate():
                        monitoring_alerts.alert_tv_api_failures()
                continue

            decision = self.engine.evaluate_entry(instance, snapshot, platform, now=now)

            if not self.dry_run:
                _record_entry_eval(instance, decision)

            if not decision.approved:
                continue
            result.entries_approved += 1

            if self.dry_run:
                logger.info("dry-run %s -- approved (%d contracts)",
                            name, decision.contracts_to_trade)
                continue

            try:
                position_id = self.broker_executor(instance, decision)
            except Exception as exc:  # noqa: BLE001
                logger.error("broker submit failed for %s: %r", name, exc)
                continue

            if position_id:
                result.entries_filled += 1
                logger.info("filled %s position=%s contracts=%d",
                            name, position_id, decision.contracts_to_trade)
                # Discord notification on broker fill. Best-effort.
                try:
                    monitoring_alerts.alert_entry_filled(
                        instance=name,
                        structure={
                            "short_put_strike": decision.structure.short_put.strike,
                            "long_put_strike": decision.structure.long_put.strike,
                            "long_call_strike": decision.structure.long_call.strike,
                            "net_cost": decision.structure.net_cost,
                        },
                        contracts=decision.contracts_to_trade,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("alert_entry_filled failed for %s: %r", name, exc)

        return result

    def run_management_cycle(self, now: Optional[datetime] = None) -> CycleResult:
        """Run manage_open_positions on every instance with open positions."""
        now = now or datetime.now(timezone.utc)
        result = CycleResult()

        for name, instance in self.instances.items():
            if instance.open_count == 0:
                continue
            result.instances_evaluated += 1

            # Heartbeat per-instance per-management-cycle. Best-effort.
            if not self.dry_run:
                monitoring_heartbeat.record_heartbeat(
                    bot_name=name,
                    status="KILLED" if instance.is_killed else "OK",
                    details={"cycle": "management", "open_positions": instance.open_count},
                )

            actions = self.engine.manage_open_positions(instance, now=now)
            result.triggers_fired += len(actions)

            if not actions:
                continue
            for position, action in actions:
                logger.info("trigger %s fired on %s/%s: %s",
                            action.trigger_id, name, position.position_id, action.reason)
                if not self.dry_run:
                    audit_recorder.record_management_eval(
                        instance=name,
                        position_id=position.position_id,
                        triggers_evaluated=[action.trigger_id],
                        fired_action={
                            "trigger_id": action.trigger_id,
                            "close_call": action.close_call,
                            "close_put_spread": action.close_put_spread,
                            "reason": action.reason,
                        },
                        position_snapshot={"state": position.state.value},
                    )
        return result


def _record_entry_eval(instance: GoliathInstance, decision: EngineEntryDecision) -> None:
    chain_payload = [
        {"gate": r.gate, "outcome": r.outcome.value,
         "reason": r.reason, "context": r.context}
        for r in decision.gate_chain
    ]
    structure_payload = None
    if decision.structure is not None:
        s = decision.structure
        structure_payload = {
            "short_put_strike": s.short_put.strike,
            "long_put_strike": s.long_put.strike,
            "long_call_strike": s.long_call.strike,
            "net_cost": s.net_cost,
        }
    last = decision.gate_chain[-1] if decision.gate_chain else None
    decision_label = (
        "STRUCTURE_RETURNED" if decision.approved
        else f"FAILED_AT:{last.gate}" if last else "FAILED_BUILD"
    )
    audit_recorder.record_entry_eval(
        instance=instance.name,
        chain=chain_payload,
        structure=structure_payload,
        decision=decision_label,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="trading.goliath.main")
    p.add_argument("--cycle", choices=["entry", "management", "both"], default="both")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    runner = Runner(dry_run=args.dry_run)
    if args.cycle in ("entry", "both"):
        r = runner.run_entry_cycle()
        logger.info("entry-cycle: evaluated=%d approved=%d filled=%d skips=%d",
                    r.instances_evaluated, r.entries_approved, r.entries_filled,
                    len(r.skips))
    if args.cycle in ("management", "both"):
        r = runner.run_management_cycle()
        logger.info("management-cycle: evaluated=%d triggers_fired=%d",
                    r.instances_evaluated, r.triggers_fired)
    return 0


if __name__ == "__main__":
    sys.exit(main())
