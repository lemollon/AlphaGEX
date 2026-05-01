# GOLIATH Phase 1.5 calibration results

- Generated: 2026-05-01T05:03:55.140329+00:00
- Lookback: 90 days
- Universe (10): ['AMD', 'AMDL', 'COIN', 'CONL', 'MSTR', 'MSTU', 'NVDA', 'NVDL', 'TSLA', 'TSLL']
- Data availability: 5/5 GEX histories, 10/10 price histories

## Summary

| Metric | Tag | Recommended |
|---|---|---|
| wall_concentration | `CALIB-SANITY-OK` | — |
| tracking_error | `CALIB-OK` | — |
| vol_drag | `CALIB-BLOCK` | — |
| vol_window | `CALIB-ADJUST` | `20` |

## 1. Wall concentration (sanity check)

**Tag:** `CALIB-SANITY-OK` &nbsp; **Spec default:** `2.0x`

- Universe count: 5
- Universe min / median / max: 1.7688594882629256 / 2.144531521713928 / 5.9341270187299155
- Outliers (>3x deviation from median): none
- Per-underlying: {'MSTR': 2.144531521713928, 'TSLA': 2.2571528629335558, 'NVDA': 1.7688594882629256, 'COIN': 1.9856200792795426, 'AMD': 5.9341270187299155}

**Notes:** universe n=5, median 2.14x, range [1.77, 5.93], no outliers >3.0x from median. Spec default 2.00x is consistent with current-state cross-section. True distribution validation deferred to v0.3 (see goliath-v0.3-todos.md V03-WALL-RECAL).

## 2. Tracking error fudge factor

**Tag:** `CALIB-OK` &nbsp; **Spec default:** `0.1` &nbsp; **Recommended:** —

- Universe count: 5
- Universe median ratio: 0.8548917741715901
- Outliers (>1.5x universe median): [('MSTU', 1.5583884461023172)]
- Per-pair: {'MSTU': {'observed_te': 0.023174903993530678, 'predicted_te': 0.01487107020813289, 'ratio': 1.5583884461023172, 'weeks': 17, 'sigma': 0.6566886795230098}, 'TSLL': {'observed_te': 0.004902752427052208, 'predicted_te': 0.010103489998185614, 'ratio': 0.4852533558139459, 'weeks': 17, 'sigma': 0.4461580378965525}, 'NVDL': {'observed_te': 0.0031970730697363212, 'predicted_te': 0.008676095735974412, 'ratio': 0.36849213828750566, 'weeks': 17, 'sigma': 0.3831260139674635}, 'CONL': {'observed_te': 0.016561842452717232, 'predicted_te': 0.015463345666263686, 'ratio': 1.071038752554703, 'weeks': 17, 'sigma': 0.6828428555890397}, 'AMDL': {'observed_te': 0.012271233972851172, 'predicted_te': 0.014354137381591116, 'ratio': 0.8548917741715901, 'weeks': 17, 'sigma': 0.6338615439831504}}

**Notes:** universe median ratio 0.855 in [0.75, 1.25]; spec fudge 0.100 validated against 5 pair(s). Outliers (>1.5x universe median): MSTU=1.558

## 3. Volatility drag coefficient

**Tag:** `CALIB-BLOCK` &nbsp; **Spec default:** `1.0` &nbsp; **Recommended:** —

- Universe count: 5
- Universe mean ratio: 0.7704371012056305
- Universe median ratio: 0.8008422956266141
- Universe SE: 0.4427995145561743
- Outliers (>25% from universe mean): [('MSTU', 1.3497367775516962), ('NVDL', 0.9840368470108655), ('AMDL', 0.13127685786445636)]
- Per-pair: {'MSTU': {'mean_ratio': 1.3497367775516962, 'median_ratio': 1.198796718384581, 'se_mean': 0.6777628608833971, 'theoretical_drag': -0.008293077342570659, 'weeks': 17, 'sigma': 0.6566886795230098}, 'TSLL': {'mean_ratio': 0.8008422956266141, 'median_ratio': 0.8062110071931449, 'se_mean': 0.3106285741513039, 'theoretical_drag': -0.003828019130378877, 'weeks': 17, 'sigma': 0.4461580378965525}, 'NVDL': {'mean_ratio': 0.9840368470108655, 'median_ratio': 0.863489795684887, 'se_mean': 0.274693360701289, 'theoretical_drag': -0.0028227988957422504, 'weeks': 17, 'sigma': 0.3831260139674635}, 'CONL': {'mean_ratio': 0.5862927279745199, 'median_ratio': 0.7814260766717336, 'se_mean': 0.4479669689347458, 'theoretical_drag': -0.008966814719788349, 'weeks': 17, 'sigma': 0.6828428555890397}, 'AMDL': {'mean_ratio': 0.13127685786445636, 'median_ratio': 0.09108011959210953, 'se_mean': 0.3851929336239787, 'theoretical_drag': -0.0077265472488596805, 'weeks': 17, 'sigma': 0.6338615439831504}}

**Notes:** Initial classification "too noisy" was incorrect diagnosis. Per AMDL per-week investigation (PR #2249, 2026-05-01): 3 of 5 pairs deviate >25% from theoretical drag because theoretical formula assumes Brownian motion (zero autocorrelation), but real LETF behavior diverges in trending regimes. AMDL outperformed naive 2x in 8 of 17 weeks during AMD's April rally. Root cause is formula misspecification during trending periods, not LETF-specific malfunction. Universe-default drag_coefficient = 1.0 retained. v0.3 todo V03-DRAG-AUTOCORR captures the estimator replacement. Universe mean ratio 0.770 (median 0.801), n=5.

## 4. Realized volatility window

**Tag:** `CALIB-ADJUST` &nbsp; **Spec default:** `30d` &nbsp; **Recommended:** `20d`

- Universe count: 5
- Pair-level winner counts: {30: 1, 20: 4}
- Universe majority winner: 20
- Per-underlying override candidates: none
- Per-pair: {'MSTU': {'window_stats': [{'window_days': 20, 'sigma': 0.7018703825483276, 'residual_sd': 0.02317490399353067}, {'window_days': 30, 'sigma': 0.6566886795230098, 'residual_sd': 0.023174903993530668}, {'window_days': 60, 'sigma': 0.9170499635072985, 'residual_sd': 0.023174903993530668}], 'winner': 30, 'winner_residual_sd': 0.023174903993530668}, 'TSLL': {'window_stats': [{'window_days': 20, 'sigma': 0.43679233960267905, 'residual_sd': 0.004902752427052205}, {'window_days': 30, 'sigma': 0.4461580378965525, 'residual_sd': 0.004902752427052205}, {'window_days': 60, 'sigma': 0.38363829231428087, 'residual_sd': 0.004902752427052205}], 'winner': 20, 'winner_residual_sd': 0.004902752427052205}, 'NVDL': {'window_stats': [{'window_days': 20, 'sigma': 0.3458904802798084, 'residual_sd': 0.0031970730697363212}, {'window_days': 30, 'sigma': 0.3831260139674635, 'residual_sd': 0.0031970730697363212}, {'window_days': 60, 'sigma': 0.3894546065037067, 'residual_sd': 0.0031970730697363212}], 'winner': 20, 'winner_residual_sd': 0.0031970730697363212}, 'CONL': {'window_stats': [{'window_days': 20, 'sigma': 0.6075190315498752, 'residual_sd': 0.016561842452717235}, {'window_days': 30, 'sigma': 0.6828428555890397, 'residual_sd': 0.01656184245271724}, {'window_days': 60, 'sigma': 0.8769024231695342, 'residual_sd': 0.01656184245271724}], 'winner': 20, 'winner_residual_sd': 0.016561842452717235}, 'AMDL': {'window_stats': [{'window_days': 20, 'sigma': 0.6072640268427391, 'residual_sd': 0.012271233972851172}, {'window_days': 30, 'sigma': 0.6338615439831504, 'residual_sd': 0.012271233972851172}, {'window_days': 60, 'sigma': 0.7252419397075286, 'residual_sd': 0.012271233972851172}], 'winner': 20, 'winner_residual_sd': 0.012271233972851172}}

**Notes:** 20d window wins majority: 4 of 5 pair(s) prefer 20d. Recommend changing spec from 30d to 20d. Per-pair winners: {30: 1, 20: 4}.


## Sign-off

_Awaiting Leron review. Spec defaults remain in effect until any CALIB-ADJUST recommendations above are explicitly approved._
