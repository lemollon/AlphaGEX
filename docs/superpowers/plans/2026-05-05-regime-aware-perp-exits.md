# Regime-Aware Perp Exits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all 11 AGAPE perp/futures bots profitable in both chop and trend by selecting an entry-time exit profile (chop or trend) and adding an MFE-giveback exit that runs alongside the existing trail stop. Backtest before flipping each bot live.

**Architecture:** New shared modules at `trading/agape_shared/{exit_profile.py,regime_classifier.py,regime_aware_exits.py}` hold the dataclass + classifier + new exit-management function. Each bot's existing `_manage_no_loss_trailing` is wrapped with a one-line check on `config.use_regime_aware_exits`; when False, the current path runs unchanged. Each bot's positions table grows one nullable `regime_at_entry` column. The existing `backtest/perp_exit_optimizer.py` is extended to look up per-trade regime from `scan_activity` rows and simulate per-regime profiles.

**Tech Stack:** Python 3.11, FastAPI, PostgreSQL (psycopg2 via `database_adapter.get_connection`), dataclasses, pytest. The 11 affected bot directories are `trading/agape_{btc,eth,sol,avax,xrp,doge,shib}_perp/` and `trading/agape_{shib,link,ltc,bch}_futures/`.

**Spec:** [`docs/superpowers/specs/2026-05-05-regime-aware-perp-exits-design.md`](../specs/2026-05-05-regime-aware-perp-exits-design.md)

---

## File Structure

**New files:**
- `trading/agape_shared/__init__.py` — package marker
- `trading/agape_shared/exit_profile.py` — `ExitProfile` dataclass + factory helpers
- `trading/agape_shared/regime_classifier.py` — `classify_regime()` pure function
- `trading/agape_shared/regime_aware_exits.py` — `manage_position_regime_aware()` shared exit function (MFE-giveback math + profile-driven trail/target)
- `tests/trading/agape_shared/__init__.py`
- `tests/trading/agape_shared/test_exit_profile.py`
- `tests/trading/agape_shared/test_regime_classifier.py`
- `tests/trading/agape_shared/test_regime_aware_exits.py`
- `backtest/run_regime_aware_optimizer.py` — convenience runner for the regime-aware grid

**Modified per-bot files (×11 bots):**
- `trading/agape_<bot>/models.py` — add `regime_at_entry: Optional[str] = None` to Position; add `use_regime_aware_exits: bool = False` and `exit_profile_chop: Optional[ExitProfile]`, `exit_profile_trend: Optional[ExitProfile]` to Config; load_from_db handles them
- `trading/agape_<bot>/db.py` — `_ensure_tables` ALTERs in `regime_at_entry`; `save_position` writes it; `get_open_positions` and `get_closed_trades` SELECT it
- `trading/agape_<bot>/trader.py` — call `classify_regime` after signal generation; set `position.regime_at_entry` before `save_position`; in `_manage_no_loss_trailing` branch to `manage_position_regime_aware` when flag is True

**Modified shared files:**
- `backend/api/routes/perp_exit_optimizer_routes.py` — add `exit_profile_chop`, `exit_profile_trend`, `use_regime_aware_exits` to `_ALLOWED_KEYS` so `/apply` can write them per bot
- `backtest/perp_exit_optimizer.py` — extend `simulate()` to accept an `ExitProfile`; add `load_regime_per_entry()`; aggregate per-regime metrics

The 11 bot directories are mechanically identical at the level the patches touch, so each per-bot task lists every file path explicitly.

---

## Task 1: Create `ExitProfile` dataclass with tests

**Files:**
- Create: `trading/agape_shared/__init__.py`
- Create: `trading/agape_shared/exit_profile.py`
- Create: `tests/trading/agape_shared/__init__.py`
- Create: `tests/trading/agape_shared/test_exit_profile.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/trading/agape_shared/test_exit_profile.py
from trading.agape_shared.exit_profile import ExitProfile, default_chop_profile, default_trend_profile


def test_exit_profile_round_trip_dict():
    p = ExitProfile(
        activation_pct=0.3, trail_distance_pct=0.15, profit_target_pct=1.0,
        mfe_giveback_pct=40.0, max_hold_hours=6, max_unrealized_loss_pct=1.5,
        emergency_stop_pct=5.0,
    )
    p2 = ExitProfile.from_dict(p.to_dict())
    assert p2 == p


def test_default_chop_profile_is_tighter_than_trend():
    chop = default_chop_profile()
    trend = default_trend_profile()
    assert chop.activation_pct < trend.activation_pct
    assert chop.trail_distance_pct < trend.trail_distance_pct
    assert chop.max_hold_hours < trend.max_hold_hours
    assert chop.max_unrealized_loss_pct < trend.max_unrealized_loss_pct
    # Chop has a hard target, trend doesn't
    assert chop.profit_target_pct > 0
    assert trend.profit_target_pct == 0
    # Chop closes giveback faster
    assert chop.mfe_giveback_pct < trend.mfe_giveback_pct


def test_from_dict_tolerates_unknown_keys():
    p = ExitProfile.from_dict({
        "activation_pct": 0.5, "trail_distance_pct": 0.3, "profit_target_pct": 0.0,
        "mfe_giveback_pct": 50, "max_hold_hours": 12, "max_unrealized_loss_pct": 2.0,
        "emergency_stop_pct": 5.0, "extra_unknown_key": "ignored",
    })
    assert p.activation_pct == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/trading/agape_shared/test_exit_profile.py -v
```

Expected: `ModuleNotFoundError: No module named 'trading.agape_shared.exit_profile'`

- [ ] **Step 3: Implement `__init__.py` and `exit_profile.py`**

```python
# trading/agape_shared/__init__.py
"""Shared modules for the AGAPE perp/futures bot family."""
```

```python
# trading/agape_shared/exit_profile.py
"""ExitProfile dataclass — the per-regime knobs each AGAPE perp/futures bot
selects between at trade entry. See
docs/superpowers/specs/2026-05-05-regime-aware-perp-exits-design.md.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, fields
from typing import Any, Dict


@dataclass
class ExitProfile:
    activation_pct: float
    trail_distance_pct: float
    profit_target_pct: float        # 0.0 disables the hard target (rides for trend)
    mfe_giveback_pct: float         # 0..100; 0 disables the giveback exit
    max_hold_hours: int
    max_unrealized_loss_pct: float
    emergency_stop_pct: float = 5.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ExitProfile":
        names = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in d.items() if k in names}
        return cls(**kwargs)


def default_chop_profile() -> ExitProfile:
    """Initial chop defaults from the design spec §2 table."""
    return ExitProfile(
        activation_pct=0.3,
        trail_distance_pct=0.15,
        profit_target_pct=1.0,
        mfe_giveback_pct=40.0,
        max_hold_hours=6,
        max_unrealized_loss_pct=1.5,
        emergency_stop_pct=5.0,
    )


def default_trend_profile() -> ExitProfile:
    """Initial trend defaults from the design spec §2 table."""
    return ExitProfile(
        activation_pct=0.7,
        trail_distance_pct=0.5,
        profit_target_pct=0.0,
        mfe_giveback_pct=60.0,
        max_hold_hours=24,
        max_unrealized_loss_pct=2.5,
        emergency_stop_pct=5.0,
    )
```

```python
# tests/trading/agape_shared/__init__.py
```

- [ ] **Step 4: Run test to verify pass**

```bash
pytest tests/trading/agape_shared/test_exit_profile.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add trading/agape_shared/__init__.py trading/agape_shared/exit_profile.py \
        tests/trading/agape_shared/__init__.py tests/trading/agape_shared/test_exit_profile.py
git commit -m "feat(agape-shared): ExitProfile dataclass with chop/trend defaults"
```

---

## Task 2: Implement `classify_regime` with full path coverage

**Files:**
- Create: `trading/agape_shared/regime_classifier.py`
- Create: `tests/trading/agape_shared/test_regime_classifier.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/trading/agape_shared/test_regime_classifier.py
from trading.agape_shared.regime_classifier import classify_regime, Regime


def _snap(combined_signal=None, combined_confidence=None, crypto_gex_regime=None):
    return {
        "combined_signal": combined_signal,
        "combined_confidence": combined_confidence,
        "crypto_gex_regime": crypto_gex_regime,
    }


def test_long_high_confidence_is_trend():
    assert classify_regime(_snap("LONG", "HIGH")) == Regime.TREND


def test_short_medium_confidence_is_trend():
    assert classify_regime(_snap("SHORT", "MEDIUM")) == Regime.TREND


def test_long_low_confidence_is_chop():
    # Low-confidence directional reads behave like chop in practice
    assert classify_regime(_snap("LONG", "LOW")) == Regime.CHOP


def test_range_bound_is_chop():
    assert classify_regime(_snap("RANGE_BOUND", "HIGH")) == Regime.CHOP


def test_missing_signal_uses_gex_tiebreaker():
    assert classify_regime(_snap(None, None, "NEGATIVE")) == Regime.TREND
    assert classify_regime(_snap(None, None, "POSITIVE")) == Regime.CHOP


def test_completely_missing_is_unknown():
    assert classify_regime(_snap()) == Regime.UNKNOWN


def test_wait_signal_is_unknown():
    # WAIT shouldn't open a trade in production but if it ever does, treat as unknown
    assert classify_regime(_snap("WAIT", "HIGH")) == Regime.UNKNOWN


def test_accepts_object_with_attributes():
    class Snap:
        combined_signal = "LONG"
        combined_confidence = "HIGH"
        crypto_gex_regime = "NEUTRAL"
    assert classify_regime(Snap()) == Regime.TREND
```

- [ ] **Step 2: Run to verify fail**

```bash
pytest tests/trading/agape_shared/test_regime_classifier.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement classifier**

```python
# trading/agape_shared/regime_classifier.py
"""Stateless market-regime classifier for AGAPE perp/futures bots.

Returns one of CHOP / TREND / UNKNOWN given a snapshot dict-or-object that
exposes `combined_signal`, `combined_confidence`, and `crypto_gex_regime`.
See docs/superpowers/specs/2026-05-05-regime-aware-perp-exits-design.md §1.
"""
from __future__ import annotations

from enum import Enum
from typing import Any


class Regime(str, Enum):
    CHOP = "chop"
    TREND = "trend"
    UNKNOWN = "unknown"


_TREND_CONFIDENCES = {"MEDIUM", "HIGH"}
_DIRECTIONAL_SIGNALS = {"LONG", "SHORT"}


def _get(snap: Any, key: str):
    if isinstance(snap, dict):
        return snap.get(key)
    return getattr(snap, key, None)


def classify_regime(snap: Any) -> Regime:
    sig = _get(snap, "combined_signal")
    conf = _get(snap, "combined_confidence")
    gex = _get(snap, "crypto_gex_regime")

    if sig in _DIRECTIONAL_SIGNALS and conf in _TREND_CONFIDENCES:
        return Regime.TREND
    if sig == "RANGE_BOUND":
        return Regime.CHOP
    if sig in _DIRECTIONAL_SIGNALS:  # remaining: LOW confidence
        return Regime.CHOP
    if sig is None:
        if gex == "NEGATIVE":
            return Regime.TREND
        if gex == "POSITIVE":
            return Regime.CHOP
    return Regime.UNKNOWN
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/trading/agape_shared/test_regime_classifier.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add trading/agape_shared/regime_classifier.py tests/trading/agape_shared/test_regime_classifier.py
git commit -m "feat(agape-shared): classify_regime helper (chop/trend/unknown)"
```

---

## Task 3: Implement `manage_position_regime_aware` with MFE-giveback

**Files:**
- Create: `trading/agape_shared/regime_aware_exits.py`
- Create: `tests/trading/agape_shared/test_regime_aware_exits.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/trading/agape_shared/test_regime_aware_exits.py
import pytest
from trading.agape_shared.exit_profile import ExitProfile
from trading.agape_shared.regime_aware_exits import (
    evaluate_exit, ExitDecision, ExitAction,
)


PROFILE_CHOP = ExitProfile(
    activation_pct=0.3, trail_distance_pct=0.15, profit_target_pct=1.0,
    mfe_giveback_pct=40.0, max_hold_hours=6, max_unrealized_loss_pct=1.5,
    emergency_stop_pct=5.0,
)


def _state(side="long", entry=100.0, current=100.0, hwm=100.0,
           open_age_hours=0.0, trailing_active=False, current_stop=None):
    return {
        "side": side, "entry_price": entry, "current_price": current,
        "high_water_mark": hwm, "open_age_hours": open_age_hours,
        "trailing_active": trailing_active, "current_stop": current_stop,
    }


def test_max_loss_fires_first():
    s = _state(current=98.0)  # -2% loss
    d = evaluate_exit(s, PROFILE_CHOP)
    assert d.action == ExitAction.CLOSE
    assert d.reason.startswith("MAX_LOSS_")


def test_emergency_stop_fires_above_max_loss():
    # Profile has emergency at 5%, max_loss at 1.5%; -1.5% triggers MAX_LOSS,
    # which is the correct first hit (not emergency).
    s = _state(current=98.5)  # -1.5% loss exactly
    d = evaluate_exit(s, PROFILE_CHOP)
    assert d.reason.startswith("MAX_LOSS_")


def test_profit_target_fires_in_chop():
    s = _state(current=101.0, hwm=101.0)  # +1% profit
    d = evaluate_exit(s, PROFILE_CHOP)
    assert d.action == ExitAction.CLOSE
    assert d.reason.startswith("PROFIT_TARGET_")


def test_trail_stop_hit_fires_before_giveback():
    # Trail already armed at 100.5; current 100.4 → hit
    s = _state(current=100.4, hwm=100.7, trailing_active=True, current_stop=100.5)
    d = evaluate_exit(s, PROFILE_CHOP)
    assert d.action == ExitAction.CLOSE
    assert d.reason.startswith("TRAIL_STOP")
    assert d.close_price == pytest.approx(100.5)


def test_mfe_giveback_fires_when_no_other_trigger():
    # MFE pushed to +0.8% (hwm=100.8), then current pulled back to 100.45
    # giveback_pct = 40% → giveback_floor = 100 + (100.8-100)*(1-0.4) = 100.48
    # current 100.45 < floor 100.48 → close.
    s = _state(current=100.45, hwm=100.8)
    d = evaluate_exit(s, PROFILE_CHOP)
    assert d.action == ExitAction.CLOSE
    assert d.reason.startswith("MFE_GIVEBACK_")


def test_mfe_giveback_skips_below_min_mfe():
    # MFE only +0.4% — below the 0.5% minimum, don't fire giveback even if
    # current <= floor.
    s = _state(current=100.05, hwm=100.4)
    d = evaluate_exit(s, PROFILE_CHOP)
    assert d.action == ExitAction.NONE


def test_arms_trail_when_max_profit_crosses_activation():
    # hwm=100.4 → max_profit_pct = 0.4% < activation 0.3% — already past, should arm.
    # Simpler: hwm=100.5 (+0.5% > 0.3% activation), no trail yet.
    s = _state(current=100.4, hwm=100.5, trailing_active=False)
    d = evaluate_exit(s, PROFILE_CHOP)
    # No close — but the decision should signal arm-trail with stop at hwm - trail_dist
    assert d.action == ExitAction.ARM_TRAIL
    expected_stop = max(100.0, 100.5 - 100.0 * (0.15 / 100))
    assert d.new_stop == pytest.approx(expected_stop)


def test_max_hold_fires_when_no_close_yet():
    s = _state(current=100.2, hwm=100.2, open_age_hours=6.5)  # > 6h limit
    d = evaluate_exit(s, PROFILE_CHOP)
    assert d.action == ExitAction.CLOSE
    assert d.reason == "MAX_HOLD_TIME"


def test_short_side_giveback():
    # Short entry 100, hwm down to 99.2 (MFE +0.8%), current bounced to 99.55
    # giveback_floor = 100 - 0.8 * (1 - 0.4) = 99.52
    # 99.55 > 99.52 → close (price has retraced through floor for a short).
    s = _state(side="short", entry=100.0, current=99.55, hwm=99.2)
    d = evaluate_exit(s, PROFILE_CHOP)
    assert d.action == ExitAction.CLOSE
    assert d.reason.startswith("MFE_GIVEBACK_")
```

- [ ] **Step 2: Run to verify fail**

```bash
pytest tests/trading/agape_shared/test_regime_aware_exits.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# trading/agape_shared/regime_aware_exits.py
"""Pure-function exit decision used by every AGAPE perp/futures bot when
its `use_regime_aware_exits` flag is on.

Mirrors trader._manage_no_loss_trailing's exit-priority order, but driven
by an ExitProfile (one per regime) and adds an MFE-giveback exit between
the existing trail-stop and the funding/time-based exits. State is passed
in as a plain dict so this stays unit-testable without a live DB.

Priority (first-match-wins):
  1. MAX_LOSS / EMERGENCY_STOP      (hard stops)
  2. PROFIT_TARGET                   (chop only — trend disables with 0)
  3. TRAIL_STOP                      (existing armed trail hit)
  4. MFE_GIVEBACK                    (NEW — closes when N% of peak gain bled back)
  5. MAX_HOLD_TIME                   (deadline)
  6. ARM_TRAIL or UPDATE_TRAIL       (if max_profit_pct crossed activation)
  7. NONE                            (no action this tick)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional

from trading.agape_shared.exit_profile import ExitProfile


# Don't fire MFE-giveback on noise — the run-up has to be at least this big.
_MFE_GIVEBACK_MIN_PCT = 0.5


class ExitAction(str, Enum):
    NONE = "none"
    CLOSE = "close"
    ARM_TRAIL = "arm_trail"
    UPDATE_TRAIL = "update_trail"


@dataclass
class ExitDecision:
    action: ExitAction
    reason: str = ""
    close_price: Optional[float] = None     # set for CLOSE
    new_stop: Optional[float] = None        # set for ARM_TRAIL / UPDATE_TRAIL


def _profit_pct(side: str, entry: float, current: float) -> float:
    if entry <= 0:
        return 0.0
    direction = 1.0 if side == "long" else -1.0
    return ((current - entry) / entry) * 100.0 * direction


def _max_profit_pct(side: str, entry: float, hwm: float) -> float:
    """% of peak favorable excursion since open."""
    if entry <= 0:
        return 0.0
    if side == "long":
        return max(0.0, (hwm - entry) / entry * 100.0)
    return max(0.0, (entry - hwm) / entry * 100.0)


def _giveback_floor(side: str, entry: float, hwm: float, giveback_pct: float) -> float:
    """The price level at which `giveback_pct` of the MFE has bled back."""
    if side == "long":
        return entry + (hwm - entry) * (1.0 - giveback_pct / 100.0)
    return entry - (entry - hwm) * (1.0 - giveback_pct / 100.0)


def evaluate_exit(state: Mapping[str, Any], profile: ExitProfile) -> ExitDecision:
    side = state["side"]
    entry = float(state["entry_price"])
    current = float(state["current_price"])
    hwm = float(state.get("high_water_mark") or entry)
    if hwm <= 0:
        hwm = entry
    open_age_hours = float(state.get("open_age_hours") or 0.0)
    trailing_active = bool(state.get("trailing_active") or False)
    current_stop = state.get("current_stop")

    profit_pct = _profit_pct(side, entry, current)
    max_profit_pct = _max_profit_pct(side, entry, hwm)

    # 1. MAX LOSS / EMERGENCY STOP
    if -profit_pct >= profile.max_unrealized_loss_pct:
        return ExitDecision(
            ExitAction.CLOSE,
            reason=f"MAX_LOSS_{profile.max_unrealized_loss_pct}pct",
            close_price=current,
        )
    if -profit_pct >= profile.emergency_stop_pct:
        return ExitDecision(ExitAction.CLOSE, reason="EMERGENCY_STOP", close_price=current)

    # 2. PROFIT TARGET (only when set)
    if profile.profit_target_pct > 0.0 and profit_pct >= profile.profit_target_pct:
        return ExitDecision(
            ExitAction.CLOSE,
            reason=f"PROFIT_TARGET_+{profit_pct:.2f}pct",
            close_price=current,
        )

    # 3. TRAIL STOP HIT
    if trailing_active and current_stop is not None:
        cs = float(current_stop)
        hit = (side == "long" and current <= cs) or (side != "long" and current >= cs)
        if hit:
            return ExitDecision(
                ExitAction.CLOSE,
                reason=f"TRAIL_STOP_+{profit_pct:.2f}pct",
                close_price=cs,
            )

    # 4. MFE GIVEBACK (new). Only if MFE was meaningful and giveback enabled.
    if profile.mfe_giveback_pct > 0.0 and max_profit_pct >= _MFE_GIVEBACK_MIN_PCT:
        floor = _giveback_floor(side, entry, hwm, profile.mfe_giveback_pct)
        below_floor = (side == "long" and current < floor) or (side != "long" and current > floor)
        if below_floor:
            return ExitDecision(
                ExitAction.CLOSE,
                reason=f"MFE_GIVEBACK_{int(profile.mfe_giveback_pct)}pct_of_+{max_profit_pct:.2f}pct",
                close_price=current,
            )

    # 5. MAX HOLD
    if open_age_hours >= profile.max_hold_hours:
        return ExitDecision(ExitAction.CLOSE, reason="MAX_HOLD_TIME", close_price=current)

    # 6a. ARM TRAIL on first cross of activation
    if (not trailing_active) and max_profit_pct >= profile.activation_pct:
        trail_dist = entry * (profile.trail_distance_pct / 100.0)
        if side == "long":
            new_stop = max(entry, hwm - trail_dist)
        else:
            new_stop = min(entry, hwm + trail_dist)
        return ExitDecision(ExitAction.ARM_TRAIL, new_stop=new_stop)

    # 6b. UPDATE TRAIL (move stop closer to hwm if it improved)
    if trailing_active:
        trail_dist = entry * (profile.trail_distance_pct / 100.0)
        if side == "long":
            new_stop = hwm - trail_dist
            if new_stop > (current_stop or 0) and new_stop >= entry:
                return ExitDecision(ExitAction.UPDATE_TRAIL, new_stop=new_stop)
        else:
            new_stop = hwm + trail_dist
            if current_stop is not None and new_stop < current_stop and new_stop <= entry:
                return ExitDecision(ExitAction.UPDATE_TRAIL, new_stop=new_stop)

    return ExitDecision(ExitAction.NONE)
```

- [ ] **Step 4: Run to verify pass**

```bash
pytest tests/trading/agape_shared/test_regime_aware_exits.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add trading/agape_shared/regime_aware_exits.py tests/trading/agape_shared/test_regime_aware_exits.py
git commit -m "feat(agape-shared): regime-aware exit decision with MFE-giveback"
```

---

## Task 4: Schema migration — add `regime_at_entry` to all 11 positions tables

**Files (modify, all 11):**
- `trading/agape_btc_perp/db.py`
- `trading/agape_eth_perp/db.py`
- `trading/agape_sol_perp/db.py`
- `trading/agape_avax_perp/db.py`
- `trading/agape_xrp_perp/db.py`
- `trading/agape_doge_perp/db.py`
- `trading/agape_shib_perp/db.py`
- `trading/agape_shib_futures/db.py`
- `trading/agape_link_futures/db.py`
- `trading/agape_ltc_futures/db.py`
- `trading/agape_bch_futures/db.py`

- [ ] **Step 1: For each db.py, locate the existing `_ensure_tables` ALTER block**

It has the pattern (example from `trading/agape_shib_futures/db.py:157`):

```python
for col_sql in [
    "ALTER TABLE agape_shib_futures_positions ADD COLUMN IF NOT EXISTS trailing_active BOOLEAN DEFAULT FALSE",
    "ALTER TABLE agape_shib_futures_positions ADD COLUMN IF NOT EXISTS current_stop FLOAT",
    ...
]:
    try:
        cursor.execute(col_sql)
    except Exception:
        pass
```

- [ ] **Step 2: Add the regime_at_entry ALTER to each block**

For every bot, append this line inside the existing `for col_sql in [...]` list:

```python
"ALTER TABLE agape_<bot>_positions ADD COLUMN IF NOT EXISTS regime_at_entry VARCHAR(20)",
```

Replace `<bot>` with each bot's table prefix: `btc_perp`, `eth_perp`, `sol_perp`, `avax_perp`, `xrp_perp`, `doge_perp`, `shib_perp`, `shib_futures`, `link_futures`, `ltc_futures`, `bch_futures`.

- [ ] **Step 3: Update each `save_position()` to write `regime_at_entry`**

Each db.py has an INSERT in `save_position`. Add the new column to both the column list and the values placeholders. Example diff for `trading/agape_shib_futures/db.py`:

```python
            cursor.execute("""
                INSERT INTO agape_shib_futures_positions (
                    position_id, side, quantity, entry_price,
                    stop_loss, take_profit, max_risk_usd,
                    underlying_at_entry, funding_rate_at_entry,
                    funding_regime_at_entry, ls_ratio_at_entry,
                    squeeze_risk_at_entry, max_pain_at_entry,
                    crypto_gex_at_entry, crypto_gex_regime_at_entry,
                    oracle_advice, oracle_win_probability, oracle_confidence,
                    oracle_top_factors,
                    signal_action, signal_confidence, signal_reasoning,
                    status, open_time, high_water_mark,
                    regime_at_entry
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s
                )
            """, (
                pos.position_id, pos.side.value, pos.quantity, pos.entry_price,
                pos.stop_loss, pos.take_profit, pos.max_risk_usd,
                pos.underlying_at_entry, pos.funding_rate_at_entry,
                pos.funding_regime_at_entry, pos.ls_ratio_at_entry,
                pos.squeeze_risk_at_entry, pos.max_pain_at_entry,
                pos.crypto_gex_at_entry, pos.crypto_gex_regime_at_entry,
                pos.oracle_advice, pos.oracle_win_probability, pos.oracle_confidence,
                json.dumps(pos.oracle_top_factors),
                pos.signal_action, pos.signal_confidence, pos.signal_reasoning,
                pos.status.value, pos.open_time or _now_ct(),
                pos.entry_price,
                getattr(pos, "regime_at_entry", None),
            ))
```

Apply the same shape to each of the 11 db.py files (column names and `pos.<field>` are the same; only the table prefix differs).

- [ ] **Step 4: Update each `get_open_positions()` and `get_closed_trades()` to SELECT `regime_at_entry`**

Add `regime_at_entry` to the SELECT column list and the dict return mapping. Example for `agape_shib_futures/db.py:get_open_positions`:

```python
            cursor.execute("""
                SELECT position_id, side, quantity, entry_price,
                       stop_loss, take_profit, max_risk_usd,
                       underlying_at_entry, funding_rate_at_entry,
                       funding_regime_at_entry, ls_ratio_at_entry,
                       squeeze_risk_at_entry, max_pain_at_entry,
                       crypto_gex_at_entry, crypto_gex_regime_at_entry,
                       oracle_advice, oracle_win_probability, oracle_confidence,
                       oracle_top_factors,
                       signal_action, signal_confidence, signal_reasoning,
                       status, open_time, high_water_mark,
                       COALESCE(trailing_active, FALSE), current_stop,
                       regime_at_entry
                FROM agape_shib_futures_positions
                WHERE status = 'open'
                ORDER BY open_time DESC
            """)
```

In the row→dict loop, add: `"regime_at_entry": row[27],` (index = previous max + 1).

For `get_closed_trades`, also add `regime_at_entry` to the SELECT and the row dict.

- [ ] **Step 5: Smoke-test syntax**

```bash
python -c "
import ast, pathlib
for f in [
  'trading/agape_btc_perp/db.py','trading/agape_eth_perp/db.py',
  'trading/agape_sol_perp/db.py','trading/agape_avax_perp/db.py',
  'trading/agape_xrp_perp/db.py','trading/agape_doge_perp/db.py',
  'trading/agape_shib_perp/db.py','trading/agape_shib_futures/db.py',
  'trading/agape_link_futures/db.py','trading/agape_ltc_futures/db.py',
  'trading/agape_bch_futures/db.py',
]:
    ast.parse(pathlib.Path(f).read_text(encoding='utf-8'))
    print(f, 'OK')
"
```

Expected: all 11 files print OK.

- [ ] **Step 6: Commit**

```bash
git add trading/agape_*/db.py
git commit -m "feat(agape-perp): add regime_at_entry column to all 11 positions tables"
```

---

## Task 5: Add Position + Config fields, classify regime at entry

**Files (modify, all 11):**
- `trading/agape_<bot>/models.py` — every bot
- `trading/agape_<bot>/trader.py` — every bot

- [ ] **Step 1: Add Position field**

In every `trading/agape_<bot>/models.py`, locate the `AgapeXxx<Bot>Position` dataclass. After the existing optional/defaulted fields (right after `last_update`), add:

```python
    # Regime at entry (chop / trend / unknown). Set by trader.run_cycle
    # when use_regime_aware_exits is enabled; None otherwise (legacy rows).
    regime_at_entry: Optional[str] = None
```

- [ ] **Step 2: Add Config fields**

In the same `models.py` for each bot, locate the `AgapeXxx<Bot>Config` dataclass and add (right after the existing exit-related fields):

```python
    # Regime-aware exits feature flag (default off — current behaviour preserved).
    use_regime_aware_exits: bool = False
    # Optional per-regime profile overrides; None falls back to default_chop_profile()
    # / default_trend_profile() at use-time. Stored as a JSON string in
    # autonomous_config and parsed on load_from_db.
    exit_profile_chop_json: Optional[str] = None
    exit_profile_trend_json: Optional[str] = None
```

`Optional[str]` is the simplest persistence-friendly shape; `load_from_db` already handles `str` → `setattr`. The actual `ExitProfile` is built on demand:

```python
# In the same models.py, after the @dataclass class block:
import json
from trading.agape_shared.exit_profile import (
    ExitProfile, default_chop_profile, default_trend_profile,
)


def _resolve_profile(json_str, default_factory):
    if not json_str:
        return default_factory()
    try:
        return ExitProfile.from_dict(json.loads(json_str))
    except Exception:
        return default_factory()


def get_chop_profile(cfg) -> ExitProfile:
    return _resolve_profile(cfg.exit_profile_chop_json, default_chop_profile)


def get_trend_profile(cfg) -> ExitProfile:
    return _resolve_profile(cfg.exit_profile_trend_json, default_trend_profile)
```

(Define `get_chop_profile` / `get_trend_profile` once per bot at the bottom of its `models.py` — copy-paste, same code.)

- [ ] **Step 3: Stamp regime at entry in trader.run_cycle**

In every `trading/agape_<bot>/trader.py`, locate `run_cycle`'s position-creation block (the section that calls `self.executor.execute_trade(signal)` and then `self.db.save_position(position)`). Insert a regime stamp between those two calls:

```python
            position = self.executor.execute_trade(signal)
            if position:
                # Stamp entry-time regime so the exit path can choose its profile.
                from trading.agape_shared.regime_classifier import classify_regime
                regime = classify_regime(market_data) if market_data else None
                position.regime_at_entry = regime.value if regime else None
                self.db.save_position(position)
```

- [ ] **Step 4: Syntax-check**

```bash
python -c "
import ast, pathlib
for f in [
  'trading/agape_btc_perp/models.py','trading/agape_btc_perp/trader.py',
  'trading/agape_eth_perp/models.py','trading/agape_eth_perp/trader.py',
  'trading/agape_sol_perp/models.py','trading/agape_sol_perp/trader.py',
  'trading/agape_avax_perp/models.py','trading/agape_avax_perp/trader.py',
  'trading/agape_xrp_perp/models.py','trading/agape_xrp_perp/trader.py',
  'trading/agape_doge_perp/models.py','trading/agape_doge_perp/trader.py',
  'trading/agape_shib_perp/models.py','trading/agape_shib_perp/trader.py',
  'trading/agape_shib_futures/models.py','trading/agape_shib_futures/trader.py',
  'trading/agape_link_futures/models.py','trading/agape_link_futures/trader.py',
  'trading/agape_ltc_futures/models.py','trading/agape_ltc_futures/trader.py',
  'trading/agape_bch_futures/models.py','trading/agape_bch_futures/trader.py',
]:
    ast.parse(pathlib.Path(f).read_text(encoding='utf-8'))
    print(f, 'OK')
"
```

Expected: all OK.

- [ ] **Step 5: Commit**

```bash
git add trading/agape_*/models.py trading/agape_*/trader.py
git commit -m "feat(agape-perp): stamp regime_at_entry on every new position"
```

After this commit + auto-deploy, every new position will have `regime_at_entry` populated. Behavior is otherwise unchanged.

---

## Task 6: Wire regime-aware exit path behind feature flag

**Files (modify, all 11):**
- `trading/agape_<bot>/trader.py` — `_manage_no_loss_trailing` method

- [ ] **Step 1: Branch each bot's `_manage_no_loss_trailing`**

For each bot, replace the body of `_manage_no_loss_trailing(self, pos, current_price, now)` to delegate to the shared evaluator when the flag is set. The legacy path stays as the else branch — no behavior change for bots with the flag off.

```python
    def _manage_no_loss_trailing(self, pos, current_price, now):
        if getattr(self.config, "use_regime_aware_exits", False):
            return self._manage_regime_aware(pos, current_price, now)
        # ----- legacy path (unchanged) -----
        entry = pos["entry_price"]
        is_long = pos["side"] == "long"
        # ... [existing body stays here verbatim] ...

    def _manage_regime_aware(self, pos, current_price, now):
        from trading.agape_shared.regime_aware_exits import (
            evaluate_exit, ExitAction,
        )
        from trading.agape_<bot>.models import (
            get_chop_profile, get_trend_profile,
        )
        from trading.agape_shared.regime_classifier import Regime

        regime = (pos.get("regime_at_entry") or "").lower()
        profile = get_trend_profile(self.config) if regime == Regime.TREND.value \
                  else get_chop_profile(self.config)

        open_time_str = pos.get("open_time")
        try:
            ot = datetime.fromisoformat(open_time_str) if isinstance(open_time_str, str) else open_time_str
            if ot and ot.tzinfo is None:
                ot = ot.replace(tzinfo=CENTRAL_TZ)
            open_age_hours = ((now - ot).total_seconds() / 3600.0) if ot else 0.0
        except Exception:
            open_age_hours = 0.0

        state = {
            "side": pos["side"],
            "entry_price": pos["entry_price"],
            "current_price": current_price,
            "high_water_mark": pos.get("high_water_mark") or pos["entry_price"],
            "open_age_hours": open_age_hours,
            "trailing_active": pos.get("trailing_active", False),
            "current_stop": pos.get("current_stop"),
        }
        decision = evaluate_exit(state, profile)
        if decision.action == ExitAction.CLOSE:
            return self._close_position(pos, decision.close_price, decision.reason)
        if decision.action == ExitAction.ARM_TRAIL:
            self.db._execute(
                f"UPDATE agape_<bot>_positions SET trailing_active = TRUE, current_stop = %s "
                f"WHERE position_id = %s AND status = 'open'",
                (round(decision.new_stop, 8), pos["position_id"]),
            )
            return False
        if decision.action == ExitAction.UPDATE_TRAIL:
            self.db._execute(
                f"UPDATE agape_<bot>_positions SET current_stop = %s "
                f"WHERE position_id = %s AND status = 'open'",
                (round(decision.new_stop, 8), pos["position_id"]),
            )
            return False
        return False
```

Replace `agape_<bot>` placeholders with the actual bot's table prefix and module name in each file (e.g. `agape_sol_perp` for `trading/agape_sol_perp/trader.py`).

- [ ] **Step 2: Verify SAR call site is preserved**

The legacy `_manage_no_loss_trailing` calls SAR exit (`_execute_sar`) inline. The regime-aware path intentionally skips SAR for v1 (per spec §"non-goals"). When ops flips a bot's flag on, SAR stops firing for that bot — that's the intended trade. Document this with a one-line comment at the top of `_manage_regime_aware`:

```python
        # NOTE: Regime-aware path does not invoke SAR. Spec §non-goals; revisit if needed.
```

- [ ] **Step 3: Run unit tests for the shared module**

```bash
pytest tests/trading/agape_shared/ -v
```

Expected: still passes (no shared module changes).

- [ ] **Step 4: Syntax check**

```bash
python -c "
import ast, pathlib
for f in pathlib.Path('trading').glob('agape_*/trader.py'):
    ast.parse(f.read_text(encoding='utf-8'))
    print(f, 'OK')
"
```

- [ ] **Step 5: Commit**

```bash
git add trading/agape_*/trader.py
git commit -m "feat(agape-perp): wire regime-aware exits behind use_regime_aware_exits flag"
```

After this commit + auto-deploy, **no behavior change yet** — the flag is False on every bot. Flipping a row in `autonomous_config` later (Task 9) will activate the new path on a per-bot basis.

---

## Task 7: Whitelist new keys in `/api/admin/perp-exit-optimizer/apply`

**File:**
- Modify: `backend/api/routes/perp_exit_optimizer_routes.py:166-177`

- [ ] **Step 1: Add the new keys to `_ALLOWED_KEYS`**

```python
_ALLOWED_KEYS = {
    "no_loss_activation_pct",
    "no_loss_trail_distance_pct",
    "no_loss_profit_target_pct",
    "max_unrealized_loss_pct",
    "no_loss_emergency_stop_pct",
    "max_hold_hours",
    "use_sar",
    "sar_trigger_pct",
    "sar_mfe_threshold_pct",
    "use_no_loss_trailing",
    # NEW — regime-aware exits
    "use_regime_aware_exits",
    "exit_profile_chop_json",
    "exit_profile_trend_json",
}
```

- [ ] **Step 2: Smoke test**

```bash
python -c "from backend.api.routes.perp_exit_optimizer_routes import _ALLOWED_KEYS; \
print('use_regime_aware_exits' in _ALLOWED_KEYS, \
      'exit_profile_chop_json' in _ALLOWED_KEYS, \
      'exit_profile_trend_json' in _ALLOWED_KEYS)"
```

Expected: `True True True`.

- [ ] **Step 3: Commit**

```bash
git add backend/api/routes/perp_exit_optimizer_routes.py
git commit -m "feat(perp-exit-optimizer): allow apply endpoint to write regime-aware keys"
```

---

## Task 8: Extend backtester to load regime per entry and simulate per profile

**Files:**
- Modify: `backtest/perp_exit_optimizer.py`
- Create: `backtest/run_regime_aware_optimizer.py`

- [ ] **Step 1: Add `load_regime_per_entry` to `perp_exit_optimizer.py`**

Append below the existing `load_price_stream` function (around line 191):

```python
def load_regime_per_entry(conn, table: str) -> dict[str, str]:
    """Map position_id -> regime label ('chop'|'trend'|'unknown') by looking
    up the scan_activity row that opened each position and running the
    saved combined_signal/combined_confidence/crypto_gex_regime through
    the same classifier used by live trading.
    """
    from trading.agape_shared.regime_classifier import classify_regime
    sql = f"""
        SELECT position_id, combined_signal, combined_confidence, crypto_gex_regime
        FROM {table}_scan_activity
        WHERE position_id IS NOT NULL
    """
    cur = conn.cursor()
    cur.execute(sql)
    out: dict[str, str] = {}
    for pid, sig, conf, gex in cur.fetchall():
        snap = {
            "combined_signal": sig,
            "combined_confidence": conf,
            "crypto_gex_regime": gex,
        }
        out[pid] = classify_regime(snap).value
    cur.close()
    return out
```

- [ ] **Step 2: Add `simulate_with_profile` parallel to existing `simulate`**

Append below the existing `simulate()` (around line 286):

```python
def simulate_with_profile(entry, ts_arr, px_arr, profile) -> tuple[float, str, float, float, float]:
    """Profile-driven version of simulate(). Mirrors
    trading.agape_shared.regime_aware_exits.evaluate_exit's priority order
    (no SAR, MFE-giveback added). Returns the same tuple shape as simulate()
    so the existing evaluate() aggregator can call either."""
    import bisect
    from trading.agape_shared.regime_aware_exits import (
        evaluate_exit, ExitAction,
    )
    open_ts = entry["open_time"].timestamp()
    entry_price = float(entry["entry_price"])
    is_long = entry["side"] == "long"
    deadline_ts = open_ts + profile.max_hold_hours * 3600.0

    start = bisect.bisect_left(ts_arr, open_ts)
    if start >= len(ts_arr):
        return (entry_price, "NO_FORWARD_DATA", 0.0, 0.0, 0.0)

    hwm = entry_price
    trailing_active = False
    current_stop: float | None = None
    mfe_pct_max = 0.0
    mae_pct_max = 0.0
    last_price = entry_price

    n = len(ts_arr)
    i = start
    while i < n:
        ts = ts_arr[i]
        if ts > deadline_ts:
            return (last_price, "MAX_HOLD_TIME", profile.max_hold_hours, mfe_pct_max, mae_pct_max)
        price = px_arr[i]
        last_price = price
        i += 1

        direction = 1.0 if is_long else -1.0
        profit_pct = ((price - entry_price) / entry_price * 100.0) * direction
        if profit_pct > mfe_pct_max:
            mfe_pct_max = profit_pct
        if profit_pct < mae_pct_max:
            mae_pct_max = profit_pct

        state = {
            "side": entry["side"],
            "entry_price": entry_price,
            "current_price": price,
            "high_water_mark": hwm,
            "open_age_hours": (ts - open_ts) / 3600.0,
            "trailing_active": trailing_active,
            "current_stop": current_stop,
        }
        d = evaluate_exit(state, profile)
        if d.action == ExitAction.CLOSE:
            return (d.close_price, d.reason, (ts - open_ts) / 3600.0, mfe_pct_max, mae_pct_max)
        if d.action == ExitAction.ARM_TRAIL:
            trailing_active = True
            current_stop = d.new_stop
        elif d.action == ExitAction.UPDATE_TRAIL:
            current_stop = d.new_stop

        # Update hwm AFTER exit checks (matches live trader cadence)
        if (is_long and price > hwm) or ((not is_long) and price < hwm):
            hwm = price

    return (last_price, "STREAM_END", (ts_arr[-1] - open_ts) / 3600.0, mfe_pct_max, mae_pct_max)
```

- [ ] **Step 3: Add `evaluate_with_profile` aggregator**

Append below existing `evaluate()`:

```python
def evaluate_with_profile(entries, ts_arr, px_arr, profile) -> dict:
    """Mirror of evaluate() but using simulate_with_profile."""
    total_pnl = 0.0
    sum_win = 0.0
    sum_loss = 0.0
    wins = losses = 0
    reasons: dict[str, int] = {}
    skipped = 0
    hold_hours_sum = 0.0
    counted = 0
    for e in entries:
        cp, reason, hold_h, _, _ = simulate_with_profile(e, ts_arr, px_arr, profile)
        if reason in ("NO_FORWARD_DATA", "STREAM_END"):
            skipped += 1
            continue
        qty = float(e["quantity"])
        d = 1.0 if e["side"] == "long" else -1.0
        pnl = (cp - float(e["entry_price"])) * qty * d
        total_pnl += pnl
        counted += 1
        hold_hours_sum += hold_h
        if pnl > 0:
            wins += 1
            sum_win += pnl
        else:
            losses += 1
            sum_loss += abs(pnl)
        bucket = reason.split("_")[0]
        if reason.startswith("MAX_LOSS"): bucket = "MAX_LOSS"
        elif reason == "MAX_HOLD_TIME": bucket = "MAX_HOLD"
        elif reason.startswith("PROFIT_TARGET"): bucket = "PROFIT_TARGET"
        elif reason.startswith("TRAIL_STOP"): bucket = "TRAIL_STOP"
        elif reason.startswith("MFE_GIVEBACK"): bucket = "MFE_GIVEBACK"
        reasons[bucket] = reasons.get(bucket, 0) + 1
    return {
        "total_pnl": round(total_pnl, 2),
        "trades": counted,
        "wins": wins, "losses": losses,
        "win_rate_pct": round(wins / counted * 100.0, 1) if counted else None,
        "avg_win": round(sum_win / wins, 2) if wins else 0.0,
        "avg_loss": round(sum_loss / losses, 2) if losses else 0.0,
        "avg_hold_hours": round(hold_hours_sum / counted, 2) if counted else 0.0,
        "skipped": skipped,
        "reasons": reasons,
    }
```

- [ ] **Step 4: Smoke test on a single bot's data structure (dry-run, no DB)**

```bash
python -c "
from trading.agape_shared.exit_profile import default_chop_profile
from backtest.perp_exit_optimizer import simulate_with_profile

# Synthetic +1.2% rally then 50% retrace
entries = [{'side':'long','entry_price':100.0,'quantity':1.0,
            'open_time':__import__('datetime').datetime(2026,5,1,10,0,
                tzinfo=__import__('datetime').timezone.utc)}]
import datetime as dt
base = dt.datetime(2026,5,1,10,0,tzinfo=dt.timezone.utc).timestamp()
ts = [base + i*60 for i in range(60)]
px = [100.0 + (0.012*100)*((i)/30) for i in range(30)] + \
     [101.2 - (0.005*100)*((i-30)/30) for i in range(30,60)]
profile = default_chop_profile()
cp, reason, hold, mfe, mae = simulate_with_profile(entries[0], ts, px, profile)
print(f'close={cp:.2f} reason={reason} hold={hold:.2f}h mfe={mfe:.2f}% mae={mae:.2f}%')
"
```

Expected: a sensible exit reason fires (PROFIT_TARGET at +1% on the run-up, or MFE_GIVEBACK during the retrace) — exact value depends on tick spacing but reason should NOT be `STREAM_END` or `NO_FORWARD_DATA`.

- [ ] **Step 5: Create the runner**

```python
# backtest/run_regime_aware_optimizer.py
"""Convenience runner — for ONE bot, evaluates current production config,
default chop+trend profiles, and a small grid around the defaults; reports
per-regime metrics so the operator can pick profile values to /apply.

Usage:
    python -m backtest.run_regime_aware_optimizer --bot SOL --since 2026-04-01
    python -m backtest.run_regime_aware_optimizer --bot SHIB_FUTURES --grid coarse
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import os
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading.agape_shared.exit_profile import (
    ExitProfile, default_chop_profile, default_trend_profile,
)
from backtest.perp_exit_optimizer import (
    BOTS, load_entries, load_price_stream, load_regime_per_entry,
    evaluate_with_profile,
)


def _bot_by_label(label: str) -> dict:
    norm = f"AGAPE_{label.upper()}"
    if not norm.endswith(("_PERP", "_FUTURES")):
        # Caller said e.g. SOL — assume perp
        norm = norm + "_PERP" if norm.split("_")[1] not in ("LINK","LTC","BCH","SHIB_FUTURES") else norm
    for b in BOTS:
        if b["name"].endswith(label.upper()) or b["name"] == norm:
            return b
    raise SystemExit(f"unknown bot {label}")


def _split_entries(entries, regimes):
    chop, trend, unknown = [], [], []
    for e in entries:
        r = regimes.get(e["position_id"], "unknown")
        if r == "trend":
            trend.append(e)
        elif r == "chop":
            chop.append(e)
        else:
            unknown.append(e)
    return chop, trend, unknown


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bot", required=True, help="e.g. SOL, AVAX, SHIB_FUTURES")
    p.add_argument("--since", default=None, help="YYYY-MM-DD entry filter (open_time >=)")
    p.add_argument("--grid", default="coarse", choices=("coarse","fine"))
    args = p.parse_args()

    from database_adapter import get_connection
    conn = get_connection()
    if not conn:
        raise SystemExit("no DB connection")

    bot = _bot_by_label(args.bot)
    print(f"bot={bot['name']}  table={bot['table']}  starting_capital={bot['starting_capital']}")

    entries = load_entries(conn, bot["table"])
    if args.since:
        cutoff = dt.datetime.fromisoformat(args.since).replace(tzinfo=dt.timezone.utc)
        entries = [e for e in entries if e["open_time"] >= cutoff]
    print(f"entries: {len(entries)}")

    ts_arr, px_arr = load_price_stream(conn, bot["table"], bot["price_col"])
    print(f"price-stream points: {len(ts_arr)}")

    regimes = load_regime_per_entry(conn, bot["table"])
    chop_e, trend_e, unk_e = _split_entries(entries, regimes)
    print(f"split: chop={len(chop_e)}  trend={len(trend_e)}  unknown={len(unk_e)}")

    # Baseline: default chop applied to everyone (apples-to-current behaviour)
    bl = evaluate_with_profile(entries, ts_arr, px_arr, default_chop_profile())
    print("\n[baseline: default chop profile, all entries]")
    print(json.dumps(bl, indent=2))

    # Per-regime: chop entries -> chop profile; trend entries -> trend profile
    rc = evaluate_with_profile(chop_e, ts_arr, px_arr, default_chop_profile())
    rt = evaluate_with_profile(trend_e, ts_arr, px_arr, default_trend_profile())
    ru = evaluate_with_profile(unk_e, ts_arr, px_arr, default_chop_profile())
    combined_pnl = rc["total_pnl"] + rt["total_pnl"] + ru["total_pnl"]
    combined_trades = rc["trades"] + rt["trades"] + ru["trades"]
    print("\n[regime-aware: default chop+trend profiles]")
    print(f"  chop:    {json.dumps(rc)}")
    print(f"  trend:   {json.dumps(rt)}")
    print(f"  unknown: {json.dumps(ru)}")
    print(f"  combined total_pnl={combined_pnl:+.2f}  trades={combined_trades}")

    if args.grid == "fine":
        # Tiny per-bot grid around the defaults, only on the chop portion
        # (trend portion has fewer knobs that matter — keep it simple for v1).
        print("\n[chop grid search around defaults]")
        best = None
        for act in [0.2, 0.3, 0.5]:
            for trail in [0.1, 0.15, 0.25]:
                for tgt in [0.6, 1.0, 1.5]:
                    for mfe in [30.0, 40.0, 60.0]:
                        prof = ExitProfile(act, trail, tgt, mfe, 6, 1.5, 5.0)
                        r = evaluate_with_profile(chop_e, ts_arr, px_arr, prof)
                        if best is None or r["total_pnl"] > best[0]["total_pnl"]:
                            best = (r, prof)
        print(f"  best chop config: pnl={best[0]['total_pnl']:+.2f} "
              f"trades={best[0]['trades']} wr={best[0]['win_rate_pct']}%")
        print(f"  profile: {best[1].to_dict()}")

    conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Commit**

```bash
git add backtest/perp_exit_optimizer.py backtest/run_regime_aware_optimizer.py
git commit -m "feat(backtest): regime-aware optimizer (per-trade regime + per-profile sim)"
```

---

## Task 9: Pilot rollout (operator action — backtest then flip flag)

**Files:** none (operator-only).

- [ ] **Step 1: Operator runs backtest for SOL**

```bash
python -m backtest.run_regime_aware_optimizer --bot SOL --since 2026-04-01 --grid fine
```

Paste output back to Claude. Look for:
- `chop` count > 0 (otherwise classifier didn't trigger; investigate)
- combined `total_pnl` should beat the baseline by enough to justify flipping
- `best chop config` profile values

- [ ] **Step 2: Same for AVAX and SHIB_FUTURES**

```bash
python -m backtest.run_regime_aware_optimizer --bot AVAX --since 2026-04-01 --grid fine
python -m backtest.run_regime_aware_optimizer --bot SHIB_FUTURES --since 2026-04-01 --grid fine
```

Note: `SHIB_FUTURES` was wiped on 2026-05-05; only post-2026-05-05 trades exist. Backtest may have very few entries — that's expected. Either lower `--since 2026-04-29` or wait a few days for sample-size to build.

- [ ] **Step 3: Apply chosen profiles via the API**

For each pilot bot, after Claude reviews the backtest output and proposes profile JSON, the operator runs (replace JSON values with what Claude proposes):

```bash
curl -X POST $RENDER_API_BASE/api/admin/perp-exit-optimizer/apply \
  -H 'Content-Type: application/json' \
  -d '{
    "bot": "SOL",
    "config": {
      "use_regime_aware_exits": true,
      "exit_profile_chop_json": "{\"activation_pct\":0.3,\"trail_distance_pct\":0.15,\"profit_target_pct\":1.0,\"mfe_giveback_pct\":40.0,\"max_hold_hours\":6,\"max_unrealized_loss_pct\":1.5,\"emergency_stop_pct\":5.0}",
      "exit_profile_trend_json": "{\"activation_pct\":0.7,\"trail_distance_pct\":0.5,\"profit_target_pct\":0.0,\"mfe_giveback_pct\":60.0,\"max_hold_hours\":24,\"max_unrealized_loss_pct\":2.5,\"emergency_stop_pct\":5.0}"
    },
    "note": "regime-aware pilot — backtest 2026-04-01..2026-05-05"
  }'
```

- [ ] **Step 4: Restart `alphagex-trader` (auto-deploy on the next push handles this)**

If no push pending, manually restart on Render dashboard.

- [ ] **Step 5: Monitor for 48-72h via the audit script**

```bash
python scripts/audit_perp_exits.py --bot SOL
python scripts/audit_perp_exits.py --bot AVAX
python scripts/audit_perp_exits.py --bot SHIB_FUTURES
```

Expected: `MFE_GIVEBACK` shows up in the close-reason histogram. `MAX_LOSS` percentage drops vs pre-flip.

---

## Task 10: Roll out to remaining 8 bots

**Files:** none (operator + Claude action; per-bot apply calls).

After SOL/AVAX/SHIB-FUT have shown >24h of healthy regime-aware behaviour:

- [ ] **Step 1: Backtest each remaining bot**

For each of `BTC, ETH, XRP, DOGE, SHIB, LINK_FUTURES, LTC_FUTURES, BCH_FUTURES`:

```bash
python -m backtest.run_regime_aware_optimizer --bot <BOT> --since 2026-04-01 --grid fine
```

- [ ] **Step 2: Claude reviews each output, proposes profile JSON**

- [ ] **Step 3: Operator applies via the API for each bot**

(Same pattern as Task 9 Step 3.)

- [ ] **Step 4: Monitor each bot via `scripts/audit_perp_exits.py --bot <BOT>` for 24-48h**

- [ ] **Step 5: If any bot regresses, set `use_regime_aware_exits=false` for that bot via /apply, investigate**

---

## Summary

10 tasks. Tasks 1-3 are pure additive shared modules with TDD. Tasks 4-7 modify all 11 bots mechanically; the feature flag stays False so behaviour is identical until Task 9 flips it. Task 8 extends the backtest harness. Tasks 9 and 10 are operational rollouts that depend on backtest evidence.

**Reversion path:** every per-bot risk reduces to `use_regime_aware_exits = false` in `autonomous_config`. Worst case rollback for the whole feature: revert the per-bot trader.py changes from Task 6 (single commit, surgical).
