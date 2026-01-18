# Unified Engine Baseline Hashes

This document records the baseline trade hashes for the unified PlayEngine after GATE 6 validation.

**Date:** 2026-01-15  
**Engine Version:** PlayEngine (unified backtest/demo/live)  
**Git Commit:** feature/unified-engine branch  
**Seed:** 42 (for synthetic data)

## Purpose

These hashes serve as determinism checkpoints. If these hashes change unexpectedly:
1. It indicates a behavior change in the engine
2. Investigate whether the change was intentional
3. Update this baseline if the change is correct

## Structure Validation Plays

| Play | Trades | Trade Hash | Notes |
|------|--------|-----------|-------|
| V_STRUCT_001_swing_detection | 7 | `7b82b138d9b7b097` | Swing structure detection |
| V_STRUCT_002_trend_classification | 8 | `d15448581c46e920` | Trend classification |
| V_STRUCT_003_derived_zones | 12 | `3234819ff216242b` | Derived zones from fibonacci |
| V_STRUCT_004_fibonacci_levels | 55 | `676a04b556e0aa9e` | Fibonacci retracement levels |

## Feature Validation Plays

| Play | Trades | Trades Hash | Equity Hash | Run Hash | Notes |
|------|--------|-------------|-------------|----------|-------|
| V_130_last_price_vs_close | 10 | `4b66fa6b6265f9e4` | `8423895a40f0de7c` | `93d40234a4322981` | Last price vs close price |
| V_134_multi_tf_roles | 2176 | `33a1bffafca9f110` | `15189b1016d69176` | `2fab2c557e6a824e` | 3-TF roles: high_tf (4h), med_tf (1h), exec (5m) |

## Stress Test Samples

| Play | Trades | PnL (USDT) | Notes |
|------|--------|------------|-------|
| S41_L_001_ema_baseline | 1 | -3.00 | EMA baseline (edge_gate_00) |
| S41_L_009_sma_cross | 0 | 0.00 | SMA cross (edge_gate_01) |
| S41_L_016_tight_sl | 0 | 0.00 | Tight stop loss (edge_gate_02) |

## Core Audits (All Passed)

- **Toolkit Contract Audit**: 43/43 indicators OK
- **Rollup Parity Audit**: 11/11 intervals, 80 comparisons PASS
- **Structure Smoke Test**: 4/4 plays passed

## Changes from BacktestEngine

The unified engine (PlayEngine) produces different hashes than the legacy BacktestEngine because:

1. **Signal evaluation**: Uses PlaySignalEvaluator instead of direct strategy function
2. **1m sub-loop**: Evaluates signals at 1m granularity within exec_tf bars
3. **Adapter architecture**: Exchange operations go through adapters
4. **Incremental state**: Structure detection uses shared state manager

These are intentional architectural improvements. The new hashes are the NEW baseline.

## How to Verify

Run the structure smoke test:
```bash
python trade_cli.py backtest structure-smoke
```

All trade hashes should match this baseline. The test runs twice (determinism check) and hashes must be identical.

## Next Steps

- ✅ Record baselines for MultiTF plays (V_134_multi_tf_roles added)
- Add more validation plays to expand coverage
- Record baselines for risk-based sizing plays
- Track performance metrics (runtime) as baseline evolves
