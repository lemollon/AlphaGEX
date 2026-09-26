# VALOR MES v46 ES lead-market data probe

## Recommendation

Test the authenticated Tastytrade/DXLink continuous ES product as a new,
data-only lead-market input for MES. This is a coverage probe, not a strategy
test: do not inspect returns, choose a direction, tune a threshold, or promote
a trading rule from it.

## Frozen probe boundary

- Source: the existing Tastytrade OAuth market-data token and DXLink `Candle`
  events only.
- Product identity: `/ES` and exact DXLink symbol `/ES:XCME`.
- Requested start: 2020-01-01 00:00 UTC.
- Interval: one hour, extended hours included.
- The provider may normalize one-hour candle symbols from `{=1h}` to `{=h}`;
  those two exact spellings are accepted. Mixed MES/ES identities, ES quarterly
  contracts, other products or periods, invalid geometry, off-tick prices, and
  negative volume are rejected.
- Preserve OHLC, total volume, VWAP, bid volume, ask volume, provider
  count/index/sequence/flags, exact product identity, and event time.
- A provider cap is recorded honestly. A capped response can pass only if its
  retained chronology independently satisfies every coverage rule below.

ES is the deeper price-discovery market for the same S&P 500 futures complex.
It may supply a preregistered signal, but all candidate entries and exits must
be priced on MES with MES tick value, commissions, spread, and slippage.

## Safety boundary

The probe imports no account, position, or order module, submits no order, and
changes no trading mode, strategy, position, or sizing rule. It writes only to
the existing dedicated research tables. VALOR remains paper-only.

## Frozen decision rule

Accept the data only if the one-hour series begins no later than 2024-09-01,
contains at least 8,000 valid rows, contains bid and ask volume on at least 95%
of valid rows, stays on the 0.25-point tick grid, and has no unexplained
timestamp or roll discontinuity. Otherwise reject this fallback and return to
the NinjaTrader route.

If the data passes, preregister exactly one ES aggressor-imbalance mechanism
before reading any forward MES return. Freeze its direction, threshold,
holding rule, session window, MES fill model, fees, and failure criteria. Use
the earliest 50% of chronology for discovery, the next 25% as untouched
validation, and keep the newest 25% plus forward paper trades sealed. No result
from this probe may authorize live trading or increased size.
