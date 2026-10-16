# Surface producer: bad near-dated ATM IV and 25-delta wings reached the published report

**Date:** 2026-10-16
**Status:** guards added in the same PR as the archive re-render (see REPORT_REQUIREMENTS.md, "Surface producer
guards"). This file is the record of why they exist.
**Line numbers** are at `main` @ `0a73ac2ae`, before the guards.

## What went wrong

Four archived reports published an SPY near-dated ATM IV that no market state supports, against a VIX of 15 to 16
and a VIX9D of 11 to 13 in the same payload:

| Report | Time (UTC) | SPY near IV | VIX9D | Ratio |
|---|---|---|---|---|
| e1a60ef7 | 10-07 20:00 | 76.1% | 11.77 | 6.5x |
| e98fdd26 | 10-09 13:30 | 46.1% | 12.21 | 3.8x |
| 05a96eeb | 10-08 18:00 | 42.6% | 12.96 | 3.3x |
| b819d516 | 10-09 20:00 | 34.7% | 11.09 | 3.1x |

The 76.1% reading was 10.3% on the next capture ten minutes later. QQQ showed the same shape: 21.1% at 20:00 and
32.4% at 20:01 on the same expiry (10-07 close, reports 8685d5e3, 441a74c1, eb82b19a).

The damage was not the sentence. `market_structure.py:1201` derives the expected move from this value, and
e1a60ef7 published **+/-4.8%, SPY 739.9 to 814.5 on a 777.22 spot**, a band roughly seven times too wide, as a
live number. The same value feeds IV-versus-realized, premium selling and entry sections.

## Mechanism (confirmed from the persisted `surface_points` of e1a60ef7)

For SPY 1DTE (expiring 10-08) at 16:00 ET on 10-07, spot 777.22, only 66 option rows survived filtering. Rows near
the money did not survive:

- calls that survived: 6, all deep in the money: strikes 650, 640, 635, 630, 625, 600 at IVs of 135.8%, 145.7%,
  143.7%, 158.3%, 160.0%, 168.0%. Nearest is **$127.2 from spot**.
- puts that survived: 28, nearest strike 793 at 16.5%, **$15.8 from spot**; the next at 820 (44.3%).
- `_atm_ivs_by_dte` takes the nearest surviving call and the nearest surviving put and publishes the median of the
  two. The median of two values is their mean: (135.8% + 16.5%) / 2 = 76.1%.

So the "ATM IV" was the average of a deep-in-the-money call and an in-the-money put, a different strike for each,
neither near the money. The deep ITM call IV is meaningless (no time value to solve for).

The other readings are the same failure at smaller scale: 05a96eeb nearest call $49.1 and put $18.9 away; the 10-08
QQQ trio nearest call $17.7 and put $12.3 away (spot 757.7).

## Code path (all under `spreadworks/backend/`)

1. `tradier_report_source.py:49-52` picks one expiry per DTE bucket (the earliest in 1 to 5 days).
2. `tradier_report_source.py:63-67` keeps a BBO row only if bid and ask were each updated within 90 seconds of
   receipt (`:64`), `bid > 0` and `ask >= bid` (`:66`) and spread over mid is at most 30% (`:67`). Rows that fail
   are dropped silently, so near-the-money rows vanish when the book is thin or stale.
3. `tradier_report_source.py:68-69` solves Black-Scholes IV from the bid/ask mid (`implied_vol`, `:28-40`),
   bracketed from 0.1% to 500% (`:34`). Deep ITM mids with no time value still solve to 100%+.
4. `market_structure.py:985-1001` (`_atm_ivs_by_dte`) picks, per DTE, the surviving call nearest spot and the
   surviving put nearest spot independently (`:997`, no distance limit, possibly different strikes) and publishes
   `statistics.median` of the two (`:1000`).
5. `market_structure.py:1163-1165` takes the smallest DTE of at least 1 as the reference and its value as `atm_iv`.
6. `market_structure.py:1201` computes `em_pct = atm_iv * sqrt(1/252) * 100`; `:1202` onward turns it into dollars,
   `expected_move_low` and `expected_move_high`.
7. `market_structure.py:1169-1170` sets `confidence` from quote age (30 s) and row count (100) only, then drops to
   LOW only if `atm_iv` is None. e1a60ef7 therefore published as **MEDIUM**.
8. `full_options_report.py:97-102` (`cached_core`) replaces any capture whose confidence is not HIGH/MEDIUM with the
   last stored HIGH/MEDIUM capture (`market_structure.py:1685-1695`), labelled `historical_fallback` with its own
   clock. That is the designed last-known path; it is dated, not silent.

## Guards in the live path before this change

None. No distance limit on the "nearest" strike, no same-strike requirement, no agreement test between the two legs,
no cross-check against the VIX family, and confidence did not reflect leg quality.

## The 25-delta wings had the same disease

`_surface_smile` (`market_structure.py:1106-1138`) picks the call and put whose locally calculated delta is nearest
+0.25 and -0.25 with no limit on how far that is from 0.25 (`:1126-1127`). 05a96eeb published a "skew" of
24.3% put versus 74.4% call: the wings had |delta| 0.97 and 0.98 (strikes 791 and 715 against spot 772), i.e. deep
in the money, and the report rendered it as "calls are bid harder than puts - the market's paying up for upside".

## What was measured (138 stored payloads, 272 SPY/QQQ readings, before any guard code)

- Nearest surviving call and put within $0.50 of spot: 230 of 259 readings with both sides. The other 29 are a
  continuous tail from $0.6 to $127.2.
- Call/put IV at the same strike (243 readings): max/min 1.0006 to 1.2833, median 1.06 SPY and 1.04 QQQ. The pair
  ratio does not separate good from bad; the missing common strike does.
- Wing |delta| deviation from 0.25 (270 readings): 245 within 0.05; then 0.054, 0.136, 0.162, 0.162, 0.162, 0.195 ...
  maximum 0.74.
- Put/call wing IV ratio is 1.3 to 1.5x in sound readings (median 1.34, p95 1.53), so it cannot be a test.

## Guards (bands pre-registered in REPORT_REQUIREMENTS.md before the code was written)

- ATM IV only from a call and put at the same strike within 0.15% of spot, pair IVs within 1.5x; otherwise
  unavailable with a specific reason; confidence LOW; expected move, IV-versus-realized and the surface read
  become unavailable through their existing None handling.
- 25-delta wings must have |delta| within 0.10 of 0.25; otherwise the smile and skew are unavailable with the reason.

Applied offline to the stored readings the ATM guard rejects all 4 known-bad SPY readings and all 3 QQQ 10-08 readings,
and also 32 sound-looking readings (39 of 272, 14.3%). That availability cost comes from the same-strike rule and was
accepted rather than widening the band.

## Not covered, on purpose

- The renderer-side VIX9D rule (REPORT_REQUIREMENTS.md, "Surface near-leg corroboration") stays as a second layer. Its
  lower bound of 0.5x is untested. Three SPY readings at about 0.53x of VIX9D on 10-09 (f4a02419, d916c592, b4910bdd,
  5.8 to 5.9% against 11.1) were measured and left alone: no boundary is moved to catch something that has not been
  measured.
- `surface` table rows written before the guard keep their stored values (the table has no per-leg data) and can still be
  served as dated last-known readings.
- `smile.atm_iv` / `smile.atm_strike` (`market_structure.py:1161`, the 30DTE reference smile) still use the nearest surviving
  strike with no distance limit. It was not part of the measurement and is unchanged.
- Archived reports hold the bad numbers in their stored blocks; the producer guards cannot change them. The renderer-side VIX9D rule
  is what limits SPY there; QQQ in archived reports stays uncorroborated. The stored `surface_points` could be re-checked at render
  time (they are persisted in each report's evidence) but that is not built.
- The pair-ratio ceiling of 1.5 has not been tested against a genuinely bad pair; none exists in the sample.
- Quote freshness (90 s, `tradier_report_source.py:64`), the 30% spread filter (`:67`) and the 500% IV bracket (`:34`) are
  unchanged. They are plausible contributors to thin books but were not the demonstrated cause here.
