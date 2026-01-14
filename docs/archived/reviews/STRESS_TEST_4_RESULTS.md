# Stress Test 4.0 Results - Order/Risk/Leverage

**Date**: 2026-01-10
**Status**: ✅ ALL TESTS PASS

---

## Overview

Stress Test 4.0 validates order execution, leverage mechanics, risk settings (SL/TP), position sizing, and exit modes.

**Key Fix Validated**: ROI-based SL/TP calculation (2026-01-10)

---

## Test Summary

| Gate | Category | Plays | Passed | Focus |
|------|----------|-------|--------|-------|
| 00 | Baseline | 6 | 6 | BTC/ETH/SOL, long+short |
| 01 | Leverage | 6 | 6 | 1x, 2x, 3x leverage |
| 02 | Risk/SL/TP | 8 | 8 | SL/TP ratios validation |
| 03 | Sizing | 4 | 4 | Position sizing |
| 05 | Exit Modes | 6 | 6 | sl_tp_only, signal, first_hit |

**Total: 30/30 PASS**

---

## ROI-Based SL/TP Validation

### The Fix (2026-01-10)

```python
# OLD (price-based) - INCORRECT
sl_distance = entry_price * (sl_pct / 100.0)

# NEW (ROI-based) - CORRECT
sl_distance = entry_price * (sl_pct / 100.0) / leverage
```

### Why This Matters

With the old price-based approach:
- 2% SL at 10x leverage = 20% loss on margin (account blowup risk)

With the new ROI-based approach:
- 2% SL at 10x leverage = 2% loss on margin (controlled risk)

### Validation Results - Stop Loss

| Leverage | sl_pct | Expected Price Move | Actual Price Move | Expected ROI | Actual ROI | Status |
|----------|--------|---------------------|-------------------|--------------|------------|--------|
| 1x | 2% | -2.00% | -2.04% | -2.00% | -2.04% | ✅ PASS |
| 2x | 2% | -1.00% | -1.04% | -2.00% | -2.08% | ✅ PASS |
| 3x | 2% | -0.67% | -0.71% | -2.00% | -2.12% | ✅ PASS |

**Key Insight**: ROI on margin is consistently ~-2% across all leverage levels when SL is hit.

### Validation Results - Take Profit

| Leverage | tp_pct | Expected Price Move | Actual Price Move | Expected ROI | Actual ROI | Status |
|----------|--------|---------------------|-------------------|--------------|------------|--------|
| 1x | 4% | 4.00% | 3.96% | 4.00% | 3.96% | ✅ PASS |
| 2x | 4% | 2.00% | 1.96% | 4.00% | 3.92% | ✅ PASS |
| 3x | 4% | 1.33% | 1.29% | 4.00% | 3.88% | ✅ PASS |

### Validation Results - Different SL/TP Ratios (Gate 02)

| Config | SL Exits | Avg SL ROI | Expected | TP Exits | Avg TP ROI | Expected | Status |
|--------|----------|------------|----------|----------|------------|----------|--------|
| SL=1%/TP=2% | 38 | -1.04% | -1.0% | 62 | 1.96% | 2.0% | ✅ PASS |
| SL=2%/TP=4% | 8 | -2.04% | -2.0% | 21 | 3.96% | 4.0% | ✅ PASS |
| SL=3%/TP=6% | 2 | -3.04% | -3.0% | 11 | 5.96% | 6.0% | ✅ PASS |
| SL=5%/TP=10% | 0 | N/A | -5.0% | 4 | 9.96% | 10.0% | ✅ PASS |

---

## Formulas Validated

### Stop Loss Price (Long)
```
sl_price = entry_price × (1 - sl_pct / 100 / leverage)
```

### Stop Loss Price (Short)
```
sl_price = entry_price × (1 + sl_pct / 100 / leverage)
```

### Take Profit Price (Long)
```
tp_price = entry_price × (1 + tp_pct / 100 / leverage)
```

### Take Profit Price (Short)
```
tp_price = entry_price × (1 - tp_pct / 100 / leverage)
```

### ROI at Exit
```
ROI% = (exit_price - entry_price) / entry_price × leverage × 100
```

---

## Test Directory Structure

```
tests/stress/plays/
├── order_gate_00_baseline/     (6 plays)
│   ├── S4_L_001_btc_baseline.yml
│   ├── S4_S_002_btc_baseline.yml
│   ├── S4_L_003_eth_baseline.yml
│   ├── S4_S_004_eth_baseline.yml
│   ├── S4_L_005_sol_baseline.yml
│   └── S4_S_006_sol_baseline.yml
├── order_gate_01_leverage/     (6 plays)
│   ├── S4_L_010_lev_1x.yml
│   ├── S4_L_011_lev_2x.yml
│   ├── S4_L_012_lev_3x.yml
│   ├── S4_S_013_lev_1x.yml
│   ├── S4_S_014_lev_2x.yml
│   └── S4_S_015_lev_3x.yml
├── order_gate_02_risk/         (8 plays)
│   ├── S4_L_020_sl1_tp2.yml
│   ├── S4_L_021_sl2_tp4.yml
│   ├── S4_L_022_sl3_tp6.yml
│   ├── S4_L_023_sl5_tp10.yml
│   ├── S4_S_024_sl1_tp2.yml
│   ├── S4_S_025_sl2_tp4.yml
│   ├── S4_S_026_sl3_tp6.yml
│   └── S4_S_027_sl5_tp10.yml
├── order_gate_03_sizing/       (4 plays)
│   ├── S4_L_030_size_5pct.yml
│   ├── S4_L_031_size_10pct.yml
│   ├── S4_L_032_size_20pct.yml
│   └── S4_L_033_size_50pct.yml
└── order_gate_05_exit_modes/   (6 plays)
    ├── S4_L_050_exit_sl_tp_only.yml
    ├── S4_L_051_exit_signal.yml
    ├── S4_L_052_exit_first_hit.yml
    ├── S4_S_053_exit_sl_tp_only.yml
    ├── S4_S_054_exit_signal.yml
    └── S4_S_055_exit_first_hit.yml
```

---

## Key Observations

### Leverage Impact on Trade Frequency

| Leverage | Total Trades | SL Exits | TP Exits | Signal Exits |
|----------|--------------|----------|----------|--------------|
| 1x | 359 | 8 | 21 | 330 |
| 2x | 359 | 38 | 62 | 259 |
| 3x | 359 | 91 | 83 | 185 |

**Insight**: Higher leverage = more SL/TP exits because price moves represent larger ROI changes.

### Tighter Stops = More SL Exits

| SL% | SL Exits | TP Exits | Win Rate |
|-----|----------|----------|----------|
| 1% | 38 | 62 | 24.8% |
| 2% | 8 | 21 | 23.1% |
| 3% | 2 | 11 | 22.8% |
| 5% | 0 | 4 | 22.8% |

---

## Files Changed

| File | Change |
|------|--------|
| `src/backtest/execution_validation.py` | ROI-based SL/TP calculation |
| `docs/specs/PLAY_DSL_COOKBOOK.md` | Updated documentation |
| `tests/stress/plays/order_gate_*/` | 30 new stress test plays |

---

## Conclusion

**Stress Test 4.0: ✅ PASS**

The ROI-based SL/TP fix is working correctly:
- SL triggers at the expected price move (inversely proportional to leverage)
- ROI on margin is consistent across leverage levels
- TP behaves symmetrically
- All 30 plays execute without errors

**Production Ready**: Order execution, leverage, and risk management mechanics are validated.
