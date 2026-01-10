# Stress Test 2.0: Full Indicator Coverage TODO

**Status**: COMPLETE
**Last Updated**: 2026-01-09
**Plan File**: `C:\Users\507pl\.claude\plans\witty-skipping-reddy.md`

---

## Overview

Comprehensive stress test for all **43 indicators** across:
- 22 complexity gates (0% -> 105%)
- Separate LONG-only and SHORT-only plays (no mixed)
- All timeframes (LTF, MTF, HTF)
- Mark price emulator coverage (1m intra-bar resolution)
- **353 stress test plays** + **4 validation plays** (357 total)

---

## Final Results Summary

| Gate | Complexity | Plays | Status |
|------|------------|-------|--------|
| 0 | 0% - Foundation | 18 | PASSED |
| 1 | 5% - MA Baseline | 18 | PASSED |
| 2 | 10% - Crossover | 18 | PASSED |
| 3 | 15% - Multi-Output | 18 | PASSED |
| 4 | 20% - Trend | 16 | PASSED |
| 5 | 25% - Volume | 16 | PASSED |
| 6 | 30% - Two-Indicator | 16 | PASSED |
| 7 | 35% - ALL Operator | 16 | PASSED |
| 8 | 40% - ANY Operator | 16 | PASSED |
| 9 | 45% - holds_for | 16 | PASSED |
| 10 | 50% - occurred_within | 16 | PASSED |
| 11 | 55% - Proximity | 16 | PASSED |
| 12 | 60% - HTF Filter | 16 | PASSED |
| 13 | 65% - MTF Confluence | 12 | PASSED |
| 14 | 70% - Complex Boolean | 12 | PASSED |
| 15 | 75% - Mark Price Basic | 16 | PASSED |
| 16 | 80% - Mark Price Complex | 12 | PASSED |
| 17 | 85% - Squeeze/Volatility | 12 | PASSED |
| 18 | 90% - Regression/Utility | 12 | PASSED |
| 19 | 95% - Edge Cases | 12 | PASSED |
| 20 | 100% - Max Complexity | 12 | PASSED |
| 21 | 105% - 1m Intra-bar | 16 | PASSED |
| **TOTAL** | | **353** | **ALL PASSED** |

---

## Progress Tracker

### Gate 0: Foundation - Single Thresholds (0%) COMPLETE
- [x] Create directory structure (`tests/stress/plays/gate_00_foundation/`)
- [x] S_L_001 - S_L_009 (9 long - RSI, CCI, WillR, MFI, Stoch, StochRSI, CMO, TSI, Fisher)
- [x] S_S_001 - S_S_009 (9 short)
- [x] **CHECKPOINT**: Validate Gate 0 - ALL 18 PASSED

### Gate 1: MA Baseline (5%) COMPLETE
- [x] Create directory (`tests/stress/plays/gate_01_ma_baseline/`)
- [x] S_L_010 - S_L_018 (9 long - all 9 MA types)
- [x] S_S_010 - S_S_018 (9 short - all 9 MA types)
- [x] **CHECKPOINT**: Validate Gate 1 - ALL 18 PASSED

### Gate 2: Crossover Basics (10%) COMPLETE
- [x] Create directory (`tests/stress/plays/gate_02_crossover/`)
- [x] S_L_019 - S_L_027 (9 long - MA crossovers)
- [x] S_S_019 - S_S_027 (9 short - MA crossovers)
- [x] **CHECKPOINT**: Validate Gate 2 - ALL 18 PASSED

### Gate 3: Multi-Output Indicators (15%) COMPLETE
- [x] Create directory (`tests/stress/plays/gate_03_multioutput/`)
- [x] S_L_028 - S_L_036 (9 long - MACD, BBands, Stoch, KC, Donchian, Aroon, ADX)
- [x] S_S_028 - S_S_036 (9 short)
- [x] **CHECKPOINT**: Validate Gate 3 - ALL 18 PASSED

### Gate 4: Trend Indicators (20%) COMPLETE
- [x] Create directory (`tests/stress/plays/gate_04_trend/`)
- [x] S_L_037 - S_L_044 (8 long - SuperTrend, PSAR, Vortex, DM, ADX, Aroon, TRIX)
- [x] S_S_037 - S_S_044 (8 short)
- [x] **CHECKPOINT**: Validate Gate 4 - ALL 16 PASSED

### Gate 5: Volume Indicators (25%) COMPLETE
- [x] S_L_045 - S_L_052 (8 long plays - OBV, CMF, MFI, KVO, VWAP)
- [x] S_S_045 - S_S_052 (8 short plays)
- [x] **CHECKPOINT**: Validate Gate 5 - ALL 16 PASSED

### Gate 6: Two-Indicator Combinations (30%) COMPLETE
- [x] S_L_053 - S_L_060 (8 long plays)
- [x] S_S_053 - S_S_060 (8 short plays)
- [x] **CHECKPOINT**: Validate Gate 6 - ALL 16 PASSED

### Gate 7: ALL Operator (35%) COMPLETE
- [x] S_L_061 - S_L_068 (8 long plays)
- [x] S_S_061 - S_S_068 (8 short plays)
- [x] **CHECKPOINT**: Validate Gate 7 - ALL 16 PASSED

### Gate 8: ANY Operator (40%) COMPLETE
- [x] S_L_069 - S_L_076 (8 long plays)
- [x] S_S_069 - S_S_076 (8 short plays)
- [x] **CHECKPOINT**: Validate Gate 8 - ALL 16 PASSED
- [x] Fixed deprecated `eq` operator -> `==` in S_L_073, S_S_073

### Gate 9: holds_for Operator (45%) COMPLETE
- [x] S_L_077 - S_L_084 (8 long plays)
- [x] S_S_077 - S_S_084 (8 short plays)
- [x] **CHECKPOINT**: Validate Gate 9 - ALL 16 PASSED

### Gate 10: occurred_within Operator (50%) COMPLETE
- [x] S_L_085 - S_L_092 (8 long plays)
- [x] S_S_085 - S_S_092 (8 short plays)
- [x] **CHECKPOINT**: Validate Gate 10 - ALL 16 PASSED

### Gate 11: Proximity Operators (55%) COMPLETE
- [x] S_L_093 - S_L_100 (8 long plays - near_pct, near_abs)
- [x] S_S_093 - S_S_100 (8 short plays)
- [x] **CHECKPOINT**: Validate Gate 11 - ALL 16 PASSED

### Gate 12: HTF Filter (60%) COMPLETE
- [x] S_L_101 - S_L_108 (8 long plays)
- [x] S_S_101 - S_S_108 (8 short plays)
- [x] **CHECKPOINT**: Validate Gate 12 - ALL 16 PASSED

### Gate 13: MTF Confluence (65%) COMPLETE
- [x] S_L_109 - S_L_114 (6 long plays)
- [x] S_S_109 - S_S_114 (6 short plays)
- [x] **CHECKPOINT**: Validate Gate 13 - ALL 12 PASSED

### Gate 14: Complex ALL/ANY (70%) COMPLETE
- [x] S_L_115 - S_L_120 (6 long plays)
- [x] S_S_115 - S_S_120 (6 short plays)
- [x] **CHECKPOINT**: Validate Gate 14 - ALL 12 PASSED

### Gate 15: Mark Price Basics (75%) COMPLETE
- [x] S_L_121 - S_L_128 (8 long plays - last_price comparisons)
- [x] S_S_121 - S_S_128 (8 short plays)
- [x] **CHECKPOINT**: Validate Gate 15 - ALL 16 PASSED

### Gate 16: Mark Price Complex (80%) COMPLETE
- [x] S_L_129 - S_L_134 (6 long plays - last_price + windows)
- [x] S_S_129 - S_S_134 (6 short plays)
- [x] **CHECKPOINT**: Validate Gate 16 - ALL 12 PASSED

### Gate 17: Squeeze & Volatility (85%) COMPLETE
- [x] S_L_135 - S_L_140 (6 long plays - squeeze, BBands width, ATR, NATR)
- [x] S_S_135 - S_S_140 (6 short plays)
- [x] **CHECKPOINT**: Validate Gate 17 - ALL 12 PASSED

### Gate 18: Regression & Utility (90%) COMPLETE
- [x] S_L_141 - S_L_146 (6 long plays - linreg, midprice, ohlc4, mom, roc)
- [x] S_S_141 - S_S_146 (6 short plays)
- [x] **CHECKPOINT**: Validate Gate 18 - ALL 12 PASSED

### Gate 19: Edge Cases (95%) COMPLETE
- [x] S_L_147 - S_L_152 (6 long plays - extreme thresholds, multi-extreme)
- [x] S_S_147 - S_S_152 (6 short plays)
- [x] **CHECKPOINT**: Validate Gate 19 - ALL 12 PASSED

### Gate 20: Maximum Complexity (100%) COMPLETE
- [x] S_L_153 - S_L_158 (6 long plays - all features combined)
- [x] S_S_153 - S_S_158 (6 short plays)
- [x] **CHECKPOINT**: Validate Gate 20 - ALL 12 PASSED

### Gate 21: 1m Intra-bar (105%) COMPLETE
- [x] S_L_159 - S_L_166 (8 long plays - last_price gt/lt/cross, tight TP/SL)
- [x] S_S_159 - S_S_166 (8 short plays)
- [x] **CHECKPOINT**: Validate Gate 21 - ALL 16 PASSED
- [x] Tests 1m resolution within exec TF bars
- [x] Covers comparison operators (gt, lt) with last_price
- [x] Tight TP/SL (1%/2%) for intra-bar trigger validation

### Validation Plays (V_130-V_133) COMPLETE
- [x] V_130_last_price_vs_close.yml - last_price (1m) vs close (exec TF)
- [x] V_131_last_price_htf_cross.yml - last_price crossing HTF indicator
- [x] V_132_forward_fill_behavior.yml - HTF forward-fill validation
- [x] V_133_duration_window_1m.yml - holds_for/occurred_within at 1m granularity
- [x] **CHECKPOINT**: All 4 validation plays pass normalization

---

## Validation Commands

```bash
# Normalize a single play
python trade_cli.py backtest play-normalize --play tests/stress/plays/gate_00_foundation/S_L_001_rsi_threshold.yml

# Normalize all plays in a gate
python trade_cli.py backtest play-normalize-batch --dir tests/stress/plays/gate_00_foundation/

# Run smoke test on a play
python trade_cli.py backtest run --play tests/stress/plays/gate_00_foundation/S_L_001_rsi_threshold.yml --smoke
```

---

## Indicator Coverage Matrix

| Category | Indicators | Primary Gates |
|----------|------------|---------------|
| Momentum | rsi, cci, willr, cmo, mom, roc | 0, 6-8, 18 |
| Stochastic | stoch, stochrsi | 0, 3, 6-8 |
| Trend | supertrend, psar, adx, aroon, dm, vortex | 4, 12-14 |
| MA | ema, sma, wma, dema, tema, trima, zlma, kama, alma | 1, 2, 12-14 |
| Volatility | bbands, kc, atr, natr, squeeze | 3, 11, 17 |
| Volume | mfi, obv, cmf, kvo, vwap | 0, 5, 13 |
| Signal | macd, ppo, trix, tsi, fisher | 0, 3, 14 |
| Utility | linreg, midprice, ohlc4, donchian | 3, 18 |

---

## Directory Structure

```
tests/stress/plays/
├── gate_00_foundation/      (18 plays)
├── gate_01_ma_baseline/     (18 plays)
├── gate_02_crossover/       (18 plays)
├── gate_03_multioutput/     (18 plays)
├── gate_04_trend/           (16 plays)
├── gate_05_volume/          (16 plays)
├── gate_06_two_indicator/   (16 plays)
├── gate_07_all_operator/    (16 plays)
├── gate_08_any_operator/    (16 plays)
├── gate_09_holds_for/       (16 plays)
├── gate_10_occurred_within/ (16 plays)
├── gate_11_proximity/       (16 plays)
├── gate_12_htf_filter/      (16 plays)
├── gate_13_mtf_confluence/  (12 plays)
├── gate_14_complex_boolean/ (12 plays)
├── gate_15_mark_price_basic/(16 plays)
├── gate_16_mark_price_complex/(12 plays)
├── gate_17_squeeze_volatility/(12 plays)
├── gate_18_regression_utility/(12 plays)
├── gate_19_edge_cases/      (12 plays)
├── gate_20_max_complexity/  (12 plays)
└── gate_21_1m_intrabar/     (16 plays)

tests/validation/plays/
├── V_130_last_price_vs_close.yml
├── V_131_last_price_htf_cross.yml
├── V_132_forward_fill_behavior.yml
└── V_133_duration_window_1m.yml
```

---

## Bugs Fixed During Implementation

1. **Gate 8**: Deprecated `eq` operator replaced with `==` (canonical form as of 2026-01-09)
   - Files: S_L_073_supertrend_or_psar_flip.yml, S_S_073_supertrend_or_psar_flip.yml

2. **mark-price-smoke**: Off-by-one error in test indices (hardcoded [0, 100, 250])
   - File: src/cli/smoke_tests/prices.py:113
   - Fixed: Now scales with sample_bars parameter

---

## Completion Notes

- All 353 stress plays + 4 validation plays pass normalization
- Coverage spans all 43 indicators in INDICATOR_REGISTRY
- All 11 DSL operators tested (including window operators)
- Multi-timeframe syntax validated (tf, mtf, htf)
- Mark price emulator (last_price) validated at 1m resolution
- 1m intra-bar TP/SL trigger behavior tested (Gate 21)
- Both long-only and short-only strategies tested separately
- Complexity gradient from 0% (single threshold) to 105% (1m intra-bar)
