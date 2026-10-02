# Squeeze Premarket Cron (PREREG #3 / V3)

This is **PRE-REGISTRATION #3 (V3)** from
`dev/squeeze/research/PREREG.md` ("PRE-REGISTRATION #3 -- PREMARKET-TURNOVER
VARIANT"), written 2026-10-02. It runs the premarket-turnover squeeze screen
on Render instead of the local workstation, because the workstation's
network path to ThetaData is unreliable, while the existing `thetadata-proxy`
Render private service reaches ThetaData over gRPC directly and does not
depend on the workstation at all.

## What this does — and does NOT do

**Signal-logging + Discord alert only.** This job does not compute a fill,
an entry price, or an exit, and it does not place a trade. The pre-reg's own
fill convention (first NBBO ask timestamped >= 09:30:00 ET, spread-bound
<=2%/side) is explicitly gated on a quote-level (bid/ask) data pull that does
not exist yet — see PREREG.md's "Entry / exit" section before building one.

## Frozen thresholds — do not change without a new pre-registration

| Parameter | Value |
|---|---|
| Premarket turnover floor | `premarket volume / shares_outstanding >= 0.15` |
| Premarket move floor | `last premarket print vs prior-close proxy >= +10%` |
| Dedupe window | 30 calendar days, first qualifying signal per symbol |
| Signal window | 04:00:00–09:29:59 ET |

These numbers are first guesses, not fits (see PREREG.md). Per the pre-reg's
own honesty constraints: if the first read shows the rule needs threshold
changes, that is a NEW pre-registration (V3b), never an edit to this file or
to `main.py`.

## What this consumes, what it owns

- **Reads** `squeeze_premarket_universe` (symbol, shares_outstanding,
  median20_volume, as_of_date). This job does NOT populate that table — a
  separate local sync job does. If the table is empty, this job logs a
  warning and exits cleanly (exit code 0), not an error.
- **Owns** `squeeze_premarket_signals` — every qualifying hit, deduped per
  symbol per 30 calendar days.
- Both tables are `CREATE TABLE IF NOT EXISTS`'d on startup (AlphaGEX's
  standard "auto-create on first use" convention).

## Data source

`thetadata_proxy`'s `/v3/stock/history/ohlc` endpoint
(`spreadworks/thetadata_proxy/app.py`), reached over Render's private
network via the `THETADATA_BASE_URL` env var — the same env var already used
by `data/vix_minute_fetcher.py` and `backend/api/routes/spark_flame_research_routes.py`.
Never hardcode the proxy's hostname; set `THETADATA_BASE_URL` on the Cron Job
resource instead (see the root `render.yaml` / `spreadworks/render.yaml` for
the `fromService` pattern other services already use to resolve it).

**Prior-close approximation**: `squeeze_premarket_universe` has no
`prior_close` column, so this job requests a wider window (00:00:00–09:29:59
ET) in one call per symbol and takes the last bar strictly before 04:00:00 ET
as a stand-in for "prior close." That is NOT the literal 16:00 ET prior
regular-session close the pre-reg describes — it is the simpler of two
options the task spec allowed, accepted only because this is a signal-only
scanner, not a scored/fill-aware ledger. See the `main.py` module docstring
for the full reasoning.

## Discord alerts

Reads `SQUEEZE_DISCORD_WEBHOOK` first, falling back to the platform-shared
`DISCORD_WEBHOOK_URL` already used by every other SpreadWorks bot. If neither
is set, it logs a warning and skips the Discord post (DB writes still
happen).

## Do not touch

- FAMILY #2 (`intraday_velocity_scan.py`, `live_velocity_screen.py`) and its
  tables (`forward_signals_intraday`, `forward_signals`) — out of scope.
- The frozen V3 thresholds/universe definition in `PREREG.md` — read-only
  reference, never edit to make a result look better.
