# Fresh VALOR paper observation run

Scope: all six VALOR futures ledgers (MES, MNQ, RTY/M2K, CL/MCL, NG/MNG,
MGC). Existing capital is $600,000 combined. Real-money mode must stay disabled.
CL remains quarantined; a reset does not override an instrument's safety gate.

## Implementation

- Reset obtains the lifecycle advisory transaction lock, refuses live mode,
  unresolved intents and open positions without paper order identifiers.
- Previous positions, trades, scans, signals, logs, fills and daily/equity
  statistics are moved into a dedicated archive schema without copying their
  storage. Empty active tables retain constraints and indexes; dependent views
  are rebound to them. Account/config/ML state is archived as JSONB. Batch
  metadata records the archive schema and exact counts. Any failure rolls back
  the transaction. This avoids duplicating millions of rows on a small disk.
  Archive schemas own shared ID sequences and must not be dropped casually.
  Reset routes run in a thread so database work does not block the API event loop.
- Accounts restart at $600,000, zero realized P&L, trades and margin. Other
  processes detect the new account ID and clear transient loss-streak state.
- Exact contract symbols are pinned from signal through execution. Equity
  indices use the repaired roll policy; commodities require an unambiguous
  broker active-month contract that is tradeable and has not stopped trading.
- Paper buys use observed ask plus one adverse tick; sells use bid minus one
  adverse tick. Prices round adversely to the instrument tick. Missing, crossed,
  stale (>10 seconds), closed-market or insufficient displayed-size quotes
  do not fill. Partial fills, queue position and latency are not modeled.
- A provisional $3 per-contract round-trip fee is booked exactly once at close,
  atomically with the ledger. This is an explicit estimate, not verified broker
  pricing. Global config allows changing the assumption. Gross P&L, fees and
  net P&L are retained in the exit fill evidence.
- Bid/ask, size, contract, broker timestamp, observed timestamp and slippage
  settings are recorded with fills. Scans retain quote/GEX context, rule config,
  instrument parameters and deployment commit for later replay. Overnight GEX
  provenance remains explicitly unverified; copied n+1 fields are not certified.
- Non-MES trailing/SAR/max-loss thresholds use that instrument's scale instead
  of MES thresholds. SAR reversals still obey the existing cooldown.

## Required rollout order

1. Run `scripts/preserve_mes_research.py` in the existing Render shell. It stores
   a checksum-verified compressed copy of `/tmp/mes_research_c18cootu` in
   `valor_research_archives`; it does not reset trading or change settings.
2. Verify the backup row and passing PostgreSQL integration CI. Deploy the
   reviewed branch through the normal GitHub/Render pipeline.
3. Check paper mode and fresh broker quotes. Invoke the archived reset endpoint
   with `starting_capital=600000&full_reset=true` once. Never automatically retry
   a reset after a request timeout; inspect the active account/archive first.
4. Verify the new account, archive counts, zero starting ledger, subsequent
   contract-specific fill records, charged fees and account/ledger agreement.

The fresh run does not imply profitability. It is forward observation with
explicit execution assumptions. Do not call its fills identical to a broker.
