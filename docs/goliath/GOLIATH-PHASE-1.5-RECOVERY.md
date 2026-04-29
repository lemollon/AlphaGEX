# GOLIATH Phase 1.5 — Recovery Doc (v2 — Decomposed)

**Purpose:** Reconstruct Phase 1.5 spec after chat deletion. Recovered from prior conversation snippets (high confidence) plus minimal reconstruction (clearly flagged).

**Status:** Phase 1 complete and merged (per Leron, 2026-04-28). Phase 1.5 is the next gate.

**Why v2:** Two prior Claude Code sessions hit `Stream idle timeout` while attempting to write the original ~400-line single-file calibration script. The script has been decomposed into an orchestrator + 4 metric modules to fit each module within a single API response. This is better engineering anyway (separation of concerns, independently testable metrics) and is documented as a deliberate spec adjustment, not a workaround.

**How to read this doc:**

- Plain text = recovered verbatim from prior chat
- `[RECONSTRUCTED — VERIFY]` blocks = inferred from pattern of item 1; review before approving (Leron has already accepted these)
- `[NEW]` = added during recovery for operational safety, not part of original spec
- `[v2 CHANGE]` = changes from the original recovery doc to support decomposed builds

---

## PHASE 1.5 — Calibration Phase (per Addition 1)

### Goal

Empirically validate the four spec parameters that drive strike mapping:

1. Wall concentration threshold (default `2.0× median`)
2. Tracking error fudge factor (default `0.1`)
3. Volatility drag formula coefficient
4. Realized volatility window (default `30 days`)

Pull 90 days of history from TV `/gex/historical` and yfinance. Produce a calibration report. Adjust spec defaults only if reality diverges materially.

### File Deliverables — `[v2 CHANGE]` Decomposed Structure

| File                                                   | Lines     | Purpose                                                                                                       |
| ------------------------------------------------------ | --------- | ------------------------------------------------------------------------------------------------------------- |
| `scripts/goliath_calibration.py`                       | ~80       | Orchestrator — parses args, fetches data, calls each metric module, assembles report                          |
| `trading/goliath/calibration/__init__.py`              | ~10       | Package init, exports public API                                                                              |
| `trading/goliath/calibration/data_fetch.py`            | ~120      | TV historical + yfinance pulls with parquet caching                                                           |
| `trading/goliath/calibration/wall_concentration.py`    | ~80       | Metric 1                                                                                                      |
| `trading/goliath/calibration/tracking_error.py`        | ~80       | Metric 2                                                                                                      |
| `trading/goliath/calibration/vol_drag.py`              | ~80       | Metric 3                                                                                                      |
| `trading/goliath/calibration/vol_window.py`            | ~80       | Metric 4                                                                                                      |
| `docs/goliath/goliath-calibration-results.md`          | ~300      | Generated calibration report — empirical numbers vs spec defaults, recommended config changes, sign-off block |
| `trading/goliath/models.py` (partial)                  | ~50 added | Add 4 calibration parameters to `GoliathConfig` dataclass with spec defaults                                  |
| `tests/goliath/calibration/test_data_fetch.py`         | ~60       | Tests for fetch + cache behavior (synthetic inputs)                                                           |
| `tests/goliath/calibration/test_wall_concentration.py` | ~50       | Metric 1 math tests                                                                                           |
| `tests/goliath/calibration/test_tracking_error.py`     | ~50       | Metric 2 math tests                                                                                           |
| `tests/goliath/calibration/test_vol_drag.py`           | ~50       | Metric 3 math tests                                                                                           |
| `tests/goliath/calibration/test_vol_window.py`         | ~50       | Metric 4 math tests                                                                                           |

`[v2 CHANGE]` Total: ~1100 lines across 14 files (vs original spec's ~950 across 4 files). Slight increase due to module boilerplate (imports, package init), but each file is small enough to write in a single API response.

### Module Contracts — `[v2 CHANGE]` Required for Decomposition

Each metric module exposes one public function with a stable signature so the orchestrator can call them uniformly. **Updated post-Step-3 [GOLIATH-DELTA] (yellow, accepted by Leron):** all four signatures take a keyword-only `client` arg for dependency injection. Production code passes `client=None` and lets `calibrate()` lazily construct `TradingVolatilityAPI()`. Tests inject a mock. Modules that don't use the TV client (tracking_error, vol_drag, vol_window) accept the kwarg for symmetry and ignore it.

```python
# trading/goliath/calibration/wall_concentration.py
def calibrate(
    gex_history: dict[str, pd.DataFrame],
    config: GoliathConfig,
    *,
    client: "TradingVolatilityAPI | None" = None,
) -> WallConcentrationResult:
    """Returns per-underlying wall concentration sanity check + spec validation.

    NOTE: Originally specified as 90-day distribution. Downgraded to
    current-state cross-section sanity check after [GOLIATH-BLOCKED]
    finding that TV's v2 API does not expose historical strike-level
    data. v0.3 upgrade path tracked in goliath-v0.3-todos.md.
    """

# trading/goliath/calibration/tracking_error.py
def calibrate(
    price_history: dict[str, pd.DataFrame],
    config: GoliathConfig,
    *,
    client: "TradingVolatilityAPI | None" = None,  # unused, accepted for symmetry
) -> TrackingErrorResult:
    """Returns per-pair observed/spec TE ratio + spec validation."""

# trading/goliath/calibration/vol_drag.py
def calibrate(
    price_history: dict[str, pd.DataFrame],
    config: GoliathConfig,
    *,
    client: "TradingVolatilityAPI | None" = None,  # unused, accepted for symmetry
) -> VolDragResult:
    """Returns per-pair observed/theoretical drag ratio + spec validation."""

# trading/goliath/calibration/vol_window.py
def calibrate(
    price_history: dict[str, pd.DataFrame],
    config: GoliathConfig,
    *,
    client: "TradingVolatilityAPI | None" = None,  # unused, accepted for symmetry
) -> VolWindowResult:
    """Returns per-underlying optimal vol window + spec validation."""
```

Result types are dataclasses defined in each module. The orchestrator is dumb — it fetches once, passes data to each metric, and assembles results into the markdown report.

`[v2 CHANGE]` Wall concentration result fields differ from the other three: it emits `CALIB-SANITY-OK` / `CALIB-FINDING` / `CALIB-BLOCK` (no `CALIB-OK` / `CALIB-ADJUST`) and has no percentile fields or `recommended_value`. See module docstring for rationale.

### Calibration Metrics to Compute

For each underlying (MSTR, TSLA, NVDA, COIN, AMD):

**1. Wall concentration distribution.** For each of last 90 days of GEX snapshots, find the largest positive gamma below spot. Compute its ratio vs median gamma of strikes within ±5% of spot. Report distribution (median, P25, P75, P90).

**2. Volatility drag observation.** For each pair (underlying, LETF), compute weekly returns over 90 days. Compare actual `LETF_return / underlying_return` ratio to theoretical `2 - 0.5 × leverage × (leverage-1) × σ² × t`. Report mean/median ratio and standard error.

**3. Tracking error band.** Same weekly pairs — compute residuals between observed LETF return and predicted return (after drag). Report observed standard deviation; compare to spec's `leverage × σ × √t × √(2/3) × 0.1` formula.

**4. Realized volatility window sensitivity.** Compute 20-, 30-, 60-day realized vol on each underlying. Report which window minimizes drag-prediction residuals.

### Acceptance Criteria

The calibration report must include explicit numerical determinations:

**1. Wall threshold** *(recovered verbatim)*
Report `wall_concentration_p25_to_p90`. If spec default `2.0×` falls within `[p25, p90]` of actual data → keep default. If outside → recommend new value at the median.

**2. Tracking error** *(partially recovered + reconstructed tail — accepted by Leron)*
Report `observed_te_stddev / spec_predicted_te`.

> `[RECONSTRUCTED — VERIFY]` Decision rule (inferred from item 1's pattern):
>
> - If ratio is within `[0.75, 1.25]` → keep spec fudge factor `0.1`
> - If ratio < `0.75` → spec is too conservative; recommend reducing fudge factor proportionally (e.g., `0.1 × ratio`)
> - If ratio > `1.25` → spec is too aggressive; recommend increasing fudge factor proportionally
> - Report per-underlying ratios; if any single underlying is > 1.5× the universe median, flag for spec review rather than auto-adjusting universe-wide

**3. Volatility drag coefficient** *(fully reconstructed — accepted by Leron)*

> `[RECONSTRUCTED — VERIFY]` Report `observed_drag_ratio / theoretical_drag_ratio` per underlying-LETF pair.
>
> - Theoretical formula: `2 - 0.5 × leverage × (leverage-1) × σ² × t`
> - Decision rule:
>   - If mean ratio across all pairs is within `[0.90, 1.10]` → keep theoretical formula as-is, no coefficient adjustment
>   - If mean ratio is outside `[0.90, 1.10]` → recommend a calibration multiplier `k` such that `predicted_drag × k ≈ observed_drag` at the median
>   - Per-pair ratios must also be reported; if any single pair diverges by > 25% from the universe mean, flag that pair for review (may indicate the LETF is not behaving as a clean leveraged proxy — common with MSTU due to known structural issues per spec)
> - Standard error on the mean must be reported; if SE is > 0.15 the calibration is too noisy to act on, recommend extending window to 180d

**4. Realized volatility window** *(fully reconstructed — accepted by Leron)*

> `[RECONSTRUCTED — VERIFY]` Report drag-prediction residual standard deviation for each window (20d, 30d, 60d) per underlying.
>
> - Decision rule:
>   - If 30d window produces the lowest residual SD across the majority of underlyings (≥ 3 of 5) → keep spec default of 30d
>   - If a different window wins majority → recommend that window as new default
>   - If results are split (no clear majority) → keep 30d default and note the split in the report; do not change spec on ambiguous evidence
> - Report per-underlying winner alongside universe winner; if any single underlying has a strongly preferred window (residual SD > 30% lower than 30d), flag for possible per-underlying override rather than universe-wide change

### Universe Failure Rule *(recovered verbatim)*

If 1+ underlying fails coverage or calibration produces unusable results, escalate to Leron immediately with the failure data — do not work around it. Universe may need to change.

### Status Report on Completion *(adapted from Phase 1 format — recovered)*

```
[GOLIATH-PHASE-COMPLETE] Phase 1.5
What was built: orchestrator, 4 metric modules, data_fetch module, calibration report, GoliathConfig parameters
Tests added: X across 5 test files
Tests passing: X/X
Acceptance criteria met: yes/no with details per criterion
Per-underlying calibration results:
  MSTR: wall=X.X×, te_ratio=X.XX, drag_ratio=X.XX, best_vol_window=Xd
  TSLA: wall=X.X×, te_ratio=X.XX, drag_ratio=X.XX, best_vol_window=Xd
  NVDA: wall=X.X×, te_ratio=X.XX, drag_ratio=X.XX, best_vol_window=Xd
  COIN: wall=X.X×, te_ratio=X.XX, drag_ratio=X.XX, best_vol_window=Xd
  AMD:  wall=X.X×, te_ratio=X.XX, drag_ratio=X.XX, best_vol_window=Xd
Recommended spec changes: [list, or "none — spec defaults validated"]
Open questions for Leron: any
```

---

## Build Order — `[v2 CHANGE]` Optimized for Single-Response Writes

Each step below is sized to fit in one Claude Code response. Steps commit independently. If a stream times out, only the current step is lost — prior commits are safe and the next session resumes from the next uncommitted step.

**Step 1:** `trading/goliath/models.py` — add 4 calibration params to `GoliathConfig`. Commit: `GOLIATH Phase 1.5 step 1: add calibration params to GoliathConfig`.

**Step 2:** `trading/goliath/calibration/__init__.py` + `trading/goliath/calibration/data_fetch.py` — package init + data fetch module with parquet caching. Commit: `GOLIATH Phase 1.5 step 2: data fetch module with caching`.

**Step 3:** `trading/goliath/calibration/wall_concentration.py` + `tests/goliath/calibration/test_wall_concentration.py`. Commit: `GOLIATH Phase 1.5 step 3: wall concentration metric`.

**Step 4:** `trading/goliath/calibration/tracking_error.py` + `tests/goliath/calibration/test_tracking_error.py`. Commit: `GOLIATH Phase 1.5 step 4: tracking error metric`.

**Step 5:** `trading/goliath/calibration/vol_drag.py` + `tests/goliath/calibration/test_vol_drag.py`. Commit: `GOLIATH Phase 1.5 step 5: vol drag metric`.

**Step 6:** `trading/goliath/calibration/vol_window.py` + `tests/goliath/calibration/test_vol_window.py`. Commit: `GOLIATH Phase 1.5 step 6: vol window metric`.

**Step 7:** `tests/goliath/calibration/test_data_fetch.py` — fetch/cache behavior tests. Commit: `GOLIATH Phase 1.5 step 7: data fetch tests`.

**Step 8:** `scripts/goliath_calibration.py` — orchestrator that calls all 4 modules and writes the markdown report. Commit: `GOLIATH Phase 1.5 step 8: orchestrator script`.

**Step 9:** Run `python scripts/goliath_calibration.py` against real data, generate `docs/goliath/goliath-calibration-results.md`. Commit: `GOLIATH Phase 1.5 step 9: calibration results`.

**Step 10:** Run full test suite, produce final status report, STOP.

---

## Standard summary

**(1) What was done** — Updated recovery doc to v2 reflecting decomposed file structure: 4 metric modules + orchestrator instead of one ~400-line script. Added module contracts and a 10-step build order sized to fit single API responses. All recovered/reconstructed acceptance criteria preserved exactly.

**(2) What it affects** — This file replaces v1 on disk. The kickoff prompt (separate file) references this v2 doc. Claude Code will see one consistent spec.

**(3) What to test** — Per-step. Each commit is independently testable. Tests for each metric live alongside the metric module.

**(4) What's left** — `[v2 CHANGE]` Phase 1.5 work itself, executed in 10 small steps via the v2 resumption prompt.
