"""Signal decision: BULL / BEAR / NONE with composite z-score."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backtest.skew_signal.features import MinuteFeatures


Action = Literal["BULL", "BEAR", "NONE"]


@dataclass(frozen=True)
class SignalResult:
    action: Action
    composite_z: float
    skew_z: float
    charm_z: float
    magnet_z: float


def decide_signal(
    f: MinuteFeatures,
    theta_skew: float = 0.005,
    theta_charm: float = 50.0,
    magnet_threshold: float = 1.3,
) -> SignalResult:
    skew_z = -f.delta_skew_15m / theta_skew if theta_skew > 0 else 0.0
    charm_z_call = f.charm_call_total / theta_charm if theta_charm > 0 else 0.0
    charm_z_put = f.charm_put_total / theta_charm if theta_charm > 0 else 0.0
    magnet_z = f.magnet_imbalance / magnet_threshold

    bull = (
        f.delta_skew_15m < -theta_skew
        and f.charm_call_total > theta_charm
        and f.magnet_imbalance >= magnet_threshold
    )
    bear = (
        f.delta_skew_15m > theta_skew
        and f.charm_put_total > theta_charm
        and f.magnet_imbalance <= 1.0 / magnet_threshold
    )

    if bull:
        comp = abs(skew_z) * abs(charm_z_call) * abs(magnet_z)
        return SignalResult(
            action="BULL", composite_z=comp,
            skew_z=skew_z, charm_z=charm_z_call, magnet_z=magnet_z,
        )
    if bear:
        comp = -(abs(skew_z) * abs(charm_z_put) * abs(1.0 / magnet_z if magnet_z > 0 else 1.0))
        return SignalResult(
            action="BEAR", composite_z=comp,
            skew_z=skew_z, charm_z=charm_z_put, magnet_z=magnet_z,
        )
    return SignalResult(
        action="NONE", composite_z=0.0,
        skew_z=skew_z, charm_z=max(charm_z_call, charm_z_put), magnet_z=magnet_z,
    )
