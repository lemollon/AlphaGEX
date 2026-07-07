"""TSUNAMI per-instance configurations -- 7 LETFs.

[TSUNAMI-DELTA] yellow: Python module instead of instances.yaml; see
configs/global_config.py for rationale.

Master spec section 1.4 + section 5: each entry maps a LETF to its
underlying, allocation cap, and bot_guard tag. All instances are
paper_only=True until V3-5 (live-trading unlock) clears.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstanceConfig:
    letf_ticker: str
    underlying_ticker: str
    allocation_cap: float
    paper_only: bool
    bot_guard_tag: str
    # False for index-tracking LETFs (e.g. SPXL/SPXS on SPY) whose
    # underlying has no earnings calendar -- G04 is skipped for these
    # rather than fail-closed on a permanent None earnings date.
    has_earnings: bool = True

    @property
    def instance_name(self) -> str:
        return self.bot_guard_tag


# Per master spec section 5: $200 for higher-IV LETFs, $150 for
# lower-volume LETFs. paper_only=True per Q3/V3-5 deferral.
TSUNAMI_INSTANCES: dict[str, InstanceConfig] = {
    "TSUNAMI-MSTU": InstanceConfig(
        letf_ticker="MSTU", underlying_ticker="MSTR",
        allocation_cap=200.0, paper_only=True,
        bot_guard_tag="TSUNAMI-MSTU",
    ),
    "TSUNAMI-TSLL": InstanceConfig(
        letf_ticker="TSLL", underlying_ticker="TSLA",
        allocation_cap=200.0, paper_only=True,
        bot_guard_tag="TSUNAMI-TSLL",
    ),
    "TSUNAMI-NVDL": InstanceConfig(
        letf_ticker="NVDL", underlying_ticker="NVDA",
        allocation_cap=200.0, paper_only=True,
        bot_guard_tag="TSUNAMI-NVDL",
    ),
    "TSUNAMI-CONL": InstanceConfig(
        letf_ticker="CONL", underlying_ticker="COIN",
        allocation_cap=150.0, paper_only=True,
        bot_guard_tag="TSUNAMI-CONL",
    ),
    "TSUNAMI-AMDL": InstanceConfig(
        letf_ticker="AMDL", underlying_ticker="AMD",
        allocation_cap=150.0, paper_only=True,
        bot_guard_tag="TSUNAMI-AMDL",
    ),
    "TSUNAMI-SPXL": InstanceConfig(
        letf_ticker="SPXL", underlying_ticker="SPY",
        allocation_cap=200.0, paper_only=True,
        bot_guard_tag="TSUNAMI-SPXL",
        has_earnings=False,
    ),
    "TSUNAMI-SPXS": InstanceConfig(
        letf_ticker="SPXS", underlying_ticker="SPY",
        allocation_cap=200.0, paper_only=True,
        bot_guard_tag="TSUNAMI-SPXS",
        has_earnings=False,
    ),
}


def get(instance_name: str) -> InstanceConfig:
    """Return the InstanceConfig for the given name (KeyError if unknown)."""
    return TSUNAMI_INSTANCES[instance_name.upper()]


def all_instances() -> list[InstanceConfig]:
    return list(TSUNAMI_INSTANCES.values())
