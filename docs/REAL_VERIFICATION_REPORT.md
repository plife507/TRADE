# Real-Data Verification Report

Generated: 2026-02-09 22:24

## Summary

| Metric | Value |
|--------|-------|
| Total Plays | 15/60 |
| Passed | 15 |
| Failed | 0 |
| Zero-Trade | 0 |

### Accumulation (RV_001-RV_015)

| # | Play | Symbol | Status | Trades | WR | PnL | Math |
|---|------|--------|--------|--------|----|-----|------|
| 1 | RV_001_btc_accum_ema_zone | BTCUSDT | PASS | 6 | 50% | +420.37 | 26/26 |
| 2 | RV_002_eth_accum_bbands_squeeze | ETHUSDT | PASS | 10 | 50% | +788.31 | 23/23 |
| 3 | RV_003_sol_accum_rsi_macd_mfi | SOLUSDT | PASS | 3 | 67% | +477.08 | 26/26 |
| 4 | RV_004_ltc_accum_stoch_cci | LTCUSDT | PASS | 1 | 0% | -3.13 | 25/25 |
| 5 | RV_005_btc_accum_vwap_obv_cmf | BTCUSDT | PASS | 7 | 43% | +165.09 | 26/26 |
| 6 | RV_006_eth_accum_supertrend_adx | ETHUSDT | PASS | 8 | 38% | -6.95 | 23/23 |
| 7 | RV_007_sol_accum_fisher_kvo_tsi | SOLUSDT | PASS | 3 | 67% | +448.88 | 26/26 |
| 8 | RV_008_btc_accum_cases_metadata | BTCUSDT | PASS | 57 | 39% | -180.85 | 25/26 |
| 9 | RV_009_eth_accum_donchian_keltner | ETHUSDT | PASS | 10 | 50% | +748.55 | 23/23 |
| 10 | RV_010_sol_accum_aroon_dm_vortex | SOLUSDT | PASS | 3 | 67% | +327.45 | 26/26 |
| 11 | RV_011_ltc_accum_psar_natr_roc | LTCUSDT | PASS | 9 | 11% | -1525.39 | 26/26 |
| 12 | RV_012_btc_accum_trix_ppo_cmo | BTCUSDT | PASS | 5 | 20% | -488.08 | 26/26 |
| 13 | RV_013_eth_accum_alma_wma_dema_tema | ETHUSDT | PASS | 10 | 50% | +748.55 | 23/23 |
| 14 | RV_014_sol_accum_kama_linreg_trima_zlma | SOLUSDT | PASS | 3 | 67% | +323.53 | 26/26 |
| 15 | RV_015_btc_accum_all_structures | BTCUSDT | PASS | 6 | 50% | +420.37 | 26/26 |

## Coverage Matrix

(to be filled after all plays run)

## Production Readiness Gates

| Gate | Criterion | Status |
|------|-----------|--------|
| G-RD1 | All plays run without errors | 15/15 |
| G-RD2 | All plays produce trades | 15/15 |
| G-RD3 | Math verification passes | 14/15 |
| G-RD4 | All 4 Wyckoff phases covered | 1/4 |
