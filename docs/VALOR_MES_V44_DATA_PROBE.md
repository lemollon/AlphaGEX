# VALOR MES v44 data probe

## Recommendation

Use the existing paid-for Tastytrade account's read-only DXLink Candle feed to
measure the exact historical MES coverage before defining v44's trading rule.
Do not tune a strategy on the four days of sampled BBO scans, and do not treat
historical candles as executable fills.

## Frozen probe boundary

- Source: Tastytrade OAuth market-data token and DXLink `Candle` events only.
- Exact contract: `/MESZ3`; exact provider symbol: `/MESZ23:XCME`.
- Requested start: 2023-09-18 00:00 UTC.
- Intervals: one-minute and fifteen-minute, extended-hours included.
- Preserved fields: event time, OHLC, total volume, VWAP, bid volume, ask
  volume, provider count/index/sequence/flags, and exact symbol identity.
- One-minute responses may use DXFeed's documented normalized period token
  `{=m}` even when the request used `{=1m}`; those two exact forms are treated
  as equivalent, while other symbols and periods remain rejected.
- Invalid, nonfinite, off-tick, negative-volume, wrong-symbol, and impossible
  candles are rejected rather than repaired.
- The provider response is classified as complete, partial, or cap-truncated.
  A response near 8,000 rows that does not reach the requested start is not
  mislabeled complete.

## Safety boundary

The probe is opt-in and disabled by default. It imports no account, position,
or order code, submits no orders, changes no trading settings, and writes only
to new `valor_mes_dxlink_*` research tables. VALOR remains forced to paper mode.
Any provider or database failure is isolated from API startup.

## Decision rule after the probe

If fifteen-minute extended-hours data reaches the requested contract start and
contains usable bid/ask volume, preregister one order-flow mechanism before
opening any outcomes. One-minute data may calibrate execution and intrabar
ambiguity only; it may not be used to optimize the entry rule. If the feed is
cap-truncated or missing aggressor-side volume, do not claim that the free data
can support an unbiased historical strategy validation.
