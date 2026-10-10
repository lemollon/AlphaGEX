# VALOR MES v45 continuous-product coverage probe

## Recommendation

Test the authenticated Tastytrade/DXLink continuous MES product before making
NinjaTrader a hard dependency. This is a coverage probe, not a strategy test:
do not inspect returns, tune thresholds, or promote any trading rule from it.

## Frozen probe boundary

- Source: the existing Tastytrade OAuth market-data token and DXLink `Candle`
  events only.
- Product identity: `/MES` and exact DXLink symbol `/MES:XCME`.
- Requested start: 2023-01-01 00:00 UTC.
- Intervals: one hour and fifteen minutes, extended hours included.
- The provider may normalize one-hour candle symbols from `{=1h}` to `{=h}`;
  those two exact spellings are accepted. Other products, periods, mixed
  continuous/quarterly identities, invalid geometry, off-tick prices, and
  negative volume remain rejected.
- Preserve OHLC, total volume, VWAP, bid volume, ask volume, provider
  count/index/sequence/flags, exact product identity, and event time.
- A response that fails to reach the requested start is partial or
  cap-truncated even when thousands of valid rows arrive.

The one-hour interval is a signal-data coverage test. Previously collected
exact-contract one-minute candles remain execution-calibration evidence only;
hourly candles do not prove executable fills.

## Safety boundary

The probe imports no account, position, or order module, submits no order, and
changes no trading mode, strategy, position, or sizing rule. It writes only to
the existing dedicated MES research tables. VALOR remains paper-only.

## Frozen decision rule

If the one-hour continuous series reaches at least the start of calendar 2025,
contains bid and ask volume on at least 95% of valid rows, and has no unexplained
timestamp, tick-grid, or roll discontinuity, use it only to preregister one
hourly aggressor-imbalance mechanism before reading outcomes. Use the earliest
complete chronology for discovery, the next untouched block for validation,
and keep the newest block plus forward paper trades sealed.

If coverage starts later than 2025, bid/ask volume is materially missing, or
continuous rolls cannot be audited, reject this fallback and continue with the
NinjaTrader replay-data route. No result from this probe may authorize live
trading or increased size.
