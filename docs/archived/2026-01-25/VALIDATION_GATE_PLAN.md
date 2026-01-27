# Validation Gate Plan: Engine Math & Incremental Indicators

**Status**: IN PROGRESS
**Started**: 2026-01-25
**Goal**: 1% → 100% Demo/Live Ready

---

## Gate 0: Clean Slate ✅ COMPLETE
- [x] Delete all existing validation plays
- [x] Create new directory structure

## Gate 1: Structure Math Validation ✅ COMPLETE (12/12)
- [x] V_S_001_swing_basic - Swing detector basic
- [x] V_S_002_swing_edge - Swing detector edge cases
- [x] V_S_003_trend_basic - Trend detector basic
- [x] V_S_004_trend_reversal - Trend reversal detection
- [x] V_S_005_zone_demand - Demand zone behavior
- [x] V_S_006_zone_supply - Supply zone behavior
- [x] V_S_007_fib_retracement - Fibonacci retracement
- [x] V_S_008_fib_extension - Fibonacci extension
- [x] V_S_009_derived_basic - Derived zone basic
- [x] V_S_010_derived_touch - Derived zone interaction
- [x] V_S_011_rolling_max - Rolling window max
- [x] V_S_012_rolling_min - Rolling window min

## Gate 2: Indicator Validation (43 plays)
- [ ] V_I_001_ema through V_I_043_vwap

## Gate 3: Incremental Implementation (32 indicators)

### Tier 1: Trivial
- [ ] ohlc4 - `(O+H+L+C)/4`
- [ ] midprice - `(H+L)/2`
- [ ] roc - Rate of change
- [ ] mom - Momentum
- [ ] obv - On-balance volume
- [ ] natr - Normalized ATR

### Tier 2: EMA-Composable
- [ ] dema - Double EMA
- [ ] tema - Triple EMA
- [ ] ppo - Percentage Price Oscillator
- [ ] trix - Triple EMA ROC
- [ ] tsi - True Strength Index

### Tier 3: SMA/Buffer-Based
- [ ] wma - Weighted MA
- [ ] trima - Triangular MA
- [ ] linreg - Linear Regression
- [ ] cmf - Chaikin Money Flow
- [ ] cmo - Chande Momentum
- [ ] mfi - Money Flow Index

### Tier 4: Lookback-Based
- [ ] aroon - Aroon indicator
- [ ] donchian - Donchian Channel
- [ ] kc - Keltner Channel
- [ ] dm - Directional Movement
- [ ] vortex - Vortex Indicator

### Tier 5: Complex Adaptive
- [ ] kama - Kaufman Adaptive MA
- [ ] alma - Arnaud Legoux MA
- [ ] zlma - Zero-Lag MA
- [ ] stochrsi - Stochastic RSI
- [ ] uo - Ultimate Oscillator

### Tier 6: Stateful Multi-Output
- [ ] psar - Parabolic SAR
- [ ] squeeze - Squeeze Indicator
- [ ] fisher - Fisher Transform

### Tier 7: Volume Complex
- [ ] kvo - Klinger Volume Oscillator
- [ ] vwap - VWAP (session + rolling modes)

## Gate 4: Parity Validation (43 plays)
- [ ] All incremental == vectorized (tolerance per type)

## Gate 5: Stress Testing
- [ ] V_X_001_nan_handling
- [ ] V_X_002_extreme_values
- [ ] V_X_003_zero_volume
- [ ] V_X_004_same_ohlc
- [ ] V_X_005_max_features

## Gate 6: Demo/Live Readiness
- [ ] LiveIndicatorCache works with all 43 indicators
- [ ] WebSocket tick simulation passes

---

## Tolerance Guidelines

| Indicator Type | Tolerance |
|----------------|-----------|
| Single-output (EMA, SMA) | 1e-10 |
| Multi-output (MACD, BBands) | 1e-8 |
| Oscillators (RSI, Stoch) | 1e-6 relative |

---

## Directory Structure

```
tests/validation/plays/
├── tier00_smoke/
├── tier01_price_features/
├── tier02_operators/
├── tier03_boolean/
├── tier04_arithmetic/
├── tier05_windows/
├── tier06_structures/
├── tier07_indicators/
├── tier08_multi_output/
├── tier09_mtf/
├── tier10_risk/
├── tier11_position/
├── tier12_incremental/
└── tier13_stress/
```

---

## CLI Commands

```bash
# Run single play
python trade_cli.py backtest run --play <PLAY_ID> --synthetic --json

# List plays
python trade_cli.py backtest list --dir tests/validation/plays

# Audit indicators
python trade_cli.py backtest audit-toolkit
```
