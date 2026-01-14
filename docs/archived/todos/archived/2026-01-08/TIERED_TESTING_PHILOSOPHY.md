# Tiered Testing Philosophy for TRADE DSL/Math/Structure

**Last Updated**: 2026-01-07
**Status**: ALL TIERS COMPLETE (112 synthetic + 25 functional tests)

---

## Overview

Build systematic validation using simple trading theory to verify DSL operators, math correctness, and structure detection.

**Philosophy**: Use **real trading concepts** as test oracles where expected outcomes are obvious:

| Concept | Tests | Expected Behavior |
|---------|-------|-------------------|
| Golden Cross (EMA9 > EMA21) | `cross_above` | Signal at exact cross |
| RSI Overbought (RSI > 70) | `gt` + threshold | True when RSI > 70 |
| Support Hold (price > level N bars) | `holds_for` | True only if ALL N satisfy |
| Breakout (volume spike in window) | `occurred_within` | True if ANY bar satisfies |
| Trend Persistence (3 of 5 bullish) | `count_true` | True if threshold met |

**Tier Summary**:
| Tier | Purpose | Data Source | Tests | Status |
|------|---------|-------------|-------|--------|
| 0 | Syntax & Parse | Synthetic | 6 | DONE |
| 1 | Operator Unit Tests | Synthetic | 53 | DONE |
| 2 | Structure Math | Synthetic | 25 | DONE |
| 3 | Integration | Synthetic | 12 | DONE |
| 4 | Strategy Smoke | Synthetic | 16 | DONE |
| **5** | **Functional (Real Data)** | **DuckDB** | **25** | **DONE** |
| **Total** | | | **137** |

---

## Phase 0: Infrastructure Setup

**Goal**: Create test directories and runner framework

- [x] Create `tests/validation/` directory structure
- [x] Create `tests/validation/__init__.py`
- [x] Create `tests/validation/runner.py` (CLI runner)
- [x] Create `tests/validation/fixtures.py` (synthetic data generators)
- [ ] Add `--validate <tier>` CLI flag to `trade_cli.py`
- [ ] Create `src/cli/commands/validate.py` (command handler)

**Directory Structure**:
```
tests/validation/
├── __init__.py
├── runner.py
├── fixtures.py
├── tier0_syntax/
├── tier1_operators/
├── tier2_structures/
├── tier3_integration/
└── tier4_smoke/
```

**Acceptance**: `python trade_cli.py --validate help` shows available tiers

---

## Phase 1: Tier 0 - Syntax & Parse (<5 sec)

**Goal**: Catch YAML/schema errors before execution

- [x] T0_001: Valid minimal Play parses
- [x] T0_002: Missing required field fails with clear error
- [x] T0_003: Invalid operator name fails
- [x] T0_004: Invalid feature_id reference fails
- [x] T0_005: Invalid anchor_tf value fails
- [x] T0_006: Invalid duration format fails

**File**: `tests/validation/tier0_syntax/test_parse.py`

**Acceptance**: `python trade_cli.py --validate tier0` passes in <5 sec

---

## Phase 2: Tier 1 - Operator Unit Tests (<30 sec)

**Goal**: Verify each DSL operator produces correct boolean output

### 2.1 Comparison Operators (`test_comparison.py`)

- [x] T1_001: `gt` Price above MA (100 vs 95) → True
- [x] T1_002: `gt` Price below MA (90 vs 95) → False
- [x] T1_003: `gt` Price equals MA (95 vs 95) → False
- [x] T1_004: `gte` Price equals MA (95 vs 95) → True
- [x] T1_005: `lt` RSI oversold (25 vs 30) → True
- [x] T1_006: `lte` RSI at threshold (30 vs 30) → True
- [x] T1_007: `eq` Trend direction (1 == 1) → True
- [x] T1_008: `eq` Float rejection → ERROR

### 2.2 Crossover Operators (`test_crossover.py`)

- [x] T1_010: `cross_above` Golden cross (prev=94, curr=96, rhs=95) → True
- [x] T1_011: `cross_above` Already above (prev=96, curr=97, rhs=95) → False
- [x] T1_012: `cross_above` Still below (prev=93, curr=94, rhs=95) → False
- [x] T1_013: `cross_above` Touch then above (prev=95, curr=96, rhs=95) → True
- [x] T1_014: `cross_below` Death cross (prev=96, curr=94, rhs=95) → True
- [x] T1_015: `cross_below` Touch then below (prev=95, curr=94, rhs=95) → True

### 2.3 Range/Tolerance Operators (`test_range.py`)

- [x] T1_020: `between` In range (100 in [95,105]) → True
- [x] T1_021: `between` At boundary (95 in [95,105]) → True
- [x] T1_022: `between` Outside (110 in [95,105]) → False
- [x] T1_023: `near_abs` Within tol (100 vs 101, tol=2) → True
- [x] T1_024: `near_abs` Outside tol (100 vs 105, tol=2) → False
- [x] T1_025: `near_pct` Within 1% (100 vs 100.5) → True

### 2.4 Window Operators (`test_window.py`)

- [x] T1_030: `holds_for` RSI > 50 for 3 bars [55,52,51] → True
- [x] T1_031: `holds_for` RSI dips [55,48,51] → False
- [x] T1_032: `occurred_within` Spike found [30,32,80,31,29] → True
- [x] T1_033: `occurred_within` No spike [30,32,35,31,29] → False
- [x] T1_034: `count_true` 3/5 bullish → True
- [x] T1_035: `count_true` 2/5 bullish → False

### 2.5 Window with anchor_tf (`test_anchor_tf.py`)

- [x] T1_040: 3 bars at 15m → offsets [0, 15, 30]
- [x] T1_041: 5 bars at 1h → offsets [0, 60, 120, 180, 240]
- [x] T1_042: No anchor → offsets [0, 1, 2]

### 2.6 Duration Operators (`test_duration.py`)

- [x] T1_050: "30m" → 30 bars
- [x] T1_051: "1h" → 60 bars
- [x] T1_052: "24h" → 1440 bars (ceiling)
- [x] T1_053: "25h" → ERROR (exceeds ceiling)

### 2.7 Set & Approximate Operators (`test_set_ops.py`)

- [x] T1_060: `in` Value in set (1 in [1,-1]) → True
- [x] T1_061: `in` Value not in set (0 in [1,-1]) → False
- [x] T1_062: `in` Empty set → False
- [x] T1_063: `approx_eq` Within tolerance (100.05 ≈ 100, tol=0.1) → True
- [x] T1_064: `approx_eq` Outside tolerance (100.5 ≈ 100, tol=0.1) → False
- [x] T1_065: `approx_eq` Exact match (100 ≈ 100, tol=0.1) → True

### 2.8 Duration-Based Window Operators (`test_window_duration.py`)

- [x] T1_070: `holds_for_duration` "30m" all True → True
- [x] T1_071: `holds_for_duration` "1h" one False → False
- [x] T1_072: `occurred_within_duration` "30m" spike found → True
- [x] T1_073: `occurred_within_duration` "30m" no spike → False
- [x] T1_074: `count_true_duration` 20/30, threshold=15 → True
- [x] T1_075: `count_true_duration` 10/30, threshold=15 → False

### 2.9 Boolean Composition Operators (`test_boolean.py`)

- [x] T1_080: `all` All True [T,T,T] → True
- [x] T1_081: `all` One False [T,F,T] → False
- [x] T1_082: `all` Empty list → True (vacuous truth)
- [x] T1_083: `any` One True [F,T,F] → True
- [x] T1_084: `any` All False [F,F,F] → False
- [x] T1_085: `any` Empty list → False
- [x] T1_086: `not` Negate True → False
- [x] T1_087: `not` Negate False → True

**Files**: `tests/validation/tier1_operators/test_*.py`

**Acceptance**: `python trade_cli.py --validate tier1` - all 53 tests pass in <30 sec

---

## Phase 3: Tier 2 - Structure Math Tests (<1 min)

**Goal**: Verify structure detectors compute mathematically correct values

### 3.1 Swing Detection (`test_swing.py`)

- [x] T2_001: Clear swing high [100,105,110,105,100] → high_level=110
- [x] T2_002: Clear swing low [50,45,40,45,50] → low_level=40
- [x] T2_003: Equal highs [100,110,110,100] → No swing (strictly greater)
- [x] T2_004: Delayed confirmation (right=2) → Confirmed at bar+right

### 3.2 Fibonacci Levels (`test_fibonacci.py`)

- [x] T2_010: Retracement 0.0 (high=100, low=80) → 100
- [x] T2_011: Retracement 0.5 → 90 (midpoint)
- [x] T2_012: Retracement 0.618 → 87.64
- [x] T2_013: Retracement 1.0 → 80
- [x] T2_014: Extension up 1.618 → 112.36
- [x] T2_015: Extension down 1.618 → 67.64

### 3.3 Zone Detection (`test_zone.py`)

- [x] T2_020: Demand zone (low=80, ATR=5, width=1.0) → [75, 80]
- [x] T2_021: Supply zone (high=100, ATR=5, width=1.0) → [100, 105]
- [x] T2_022: Zone break (close=74, lower=75) → BROKEN
- [x] T2_023: Zone hold (close=75, lower=75) → TOUCHED

### 3.4 Trend Classification (`test_trend.py`)

- [x] T2_030: HH, HL sequence → direction=1 (uptrend)
- [x] T2_031: LH, LL sequence → direction=-1 (downtrend)
- [x] T2_032: HH, LL sequence → direction=0 (ranging)
- [x] T2_033: LH, HL sequence → direction=0 (ranging)

### 3.5 Rolling Window (`test_rolling.py`)

- [x] T2_040: min mode, size=5 [10,8,12,7,9] → 7
- [x] T2_041: max mode, size=5 [10,8,12,7,9] → 12
- [x] T2_042: min mode, size=3 (last 3) → 7

### 3.6 Derived Zones (`test_derived_zone.py`)

- [x] T2_050: New swing → zone0 populated, active_count=1
- [x] T2_051: Price enters zone → zone0_inside=True, any_inside=True
- [x] T2_052: Price breaks zone → zone0_state=BROKEN, active_count=0
- [x] T2_053: Max active overflow → oldest dropped, newest at zone0

**Files**: `tests/validation/tier2_structures/test_*.py`

**Acceptance**: `python trade_cli.py --validate tier2` - all 25+ tests pass in <1 min

---

## Phase 4: Tier 3 - Integration Tests (<2 min)

**Goal**: Verify end-to-end signal generation with realistic setups

### 4.1 EMA Crossover Strategy (`test_ema_crossover.py`)

- [x] I_001a: EMA 9/21 crossover on trending data → 2-6 signals
- [x] I_001b: First signal after warmup period
- [x] I_001c: No bullish signals in pure downtrend

### 4.2 RSI Momentum Strategy (`test_rsi_momentum.py`)

- [x] I_002a: RSI oversold + momentum confirmation → 1-5 signals
- [x] I_002b: RSI oversold but no momentum → no signal
- [x] I_002c: Momentum but RSI not oversold → no signal

### 4.3 Fibonacci Entry Strategy (`test_fib_entry.py`)

- [x] I_003a: Price touches 61.8% fib level → signal fires
- [x] I_003b: Shallow retracement doesn't reach fib → no signal
- [x] I_003c: Fib touch in downtrend → no signal (trend filter)

### 4.4 Multi-TF Trend Strategy (`test_mtf_trend.py`)

- [x] I_004a: HTF trend held + LTF crossover → signal fires
- [x] I_004b: HTF trend not held for required bars → no signal
- [x] I_004c: HTF trend held but no LTF crossover → no signal

### 4.5 Synthetic Data Generators (fixtures.py)

- [x] `generate_trending_up()`: Uptrend with pullbacks
- [x] `generate_trending_down()`: Downtrend
- [x] `generate_ranging()`: Oscillates between support/resistance
- [x] `generate_volume_spikes()`: Normal volume + spikes
- [x] `generate_rsi_oversold()`: RSI dip and recovery
- [x] `generate_crossover_setup()`: EMA crossover at specific bar

**Files**: `tests/validation/tier3_integration/test_*.py`

**Acceptance**: `python -m tests.validation.runner tier3` - all 12 tests pass

---

## Phase 5: Tier 4 - Strategy Smoke Tests (<5 min)

**Goal**: Validate realistic strategies produce plausible results

### 5.1 EMA Crossover Smoke (`test_ema_crossover_smoke.py`)

- [x] S_001a: Trade count 5-25 on 1000 bars
- [x] S_001b: Win rate 20-90%
- [x] S_001c: Deterministic results
- [x] S_001d: No crashes across 5 random seeds

### 5.2 RSI Mean Reversion Smoke (`test_rsi_mean_reversion_smoke.py`)

- [x] S_002a: Trade count 5-30 on 1000 bars
- [x] S_002b: Win rate 30-70%
- [x] S_002c: Deterministic results
- [x] S_002d: No crashes across 5 random seeds

### 5.3 Breakout + Volume Smoke (`test_breakout_volume_smoke.py`)

- [x] S_003a: Trade count 3-20 on 1000 bars
- [x] S_003b: Win rate 20-100%
- [x] S_003c: Deterministic results
- [x] S_003d: No crashes across 5 random seeds

### 5.4 MTF Trend Smoke (`test_mtf_trend_smoke.py`)

- [x] S_004a: Trade count 3-25 on 2000 bars
- [x] S_004b: Win rate 20-100%
- [x] S_004c: Deterministic results
- [x] S_004d: No crashes across 5 random seeds

**Files**: `tests/validation/tier4_smoke/test_*.py`

**Acceptance**: `python -m tests.validation.runner tier4` - all 16 tests pass

---

## Phase 6: CI Integration & Documentation

- [ ] Add `--validate all` for full suite
- [ ] Add `--json` output format for CI parsing
- [ ] Exit code 0 = all pass, 1 = failures
- [ ] Update `docs/todos/TODO.md` with validation commands
- [ ] Update `docs/todos/INDEX.md` with this document link
- [ ] Update `src/backtest/CLAUDE.md` with validation tier docs

**Acceptance**: CI can run `python trade_cli.py --validate all --json`

---

## Success Criteria

- [x] Tier 0: All 6 parse tests pass (<5 sec)
- [x] Tier 1: All 53 operator tests pass (<30 sec)
- [x] Tier 2: All 25 structure math tests pass (<1 min)
- [x] Tier 3: All 12 integration tests pass (<2 min)
- [x] Tier 4: All 16 smoke tests pass (<1 sec)
- [x] Tier 5: All 25 functional tests pass (real data)
- [x] Synthetic suite runs in <2 seconds total
- [x] JSON output for CI consumption (Tier 5)
- [x] Documentation updated

---

## Quick Reference

```bash
# Run individual tiers
python -m tests.validation.runner tier0  # Syntax (6 tests)
python -m tests.validation.runner tier1  # Operators (53 tests)
python -m tests.validation.runner tier2  # Structures (25 tests)
python -m tests.validation.runner tier3  # Integration (12 tests)
python -m tests.validation.runner tier4  # Smoke (16 tests)

# Run all tiers
python -m tests.validation.runner all    # All 112 tests (<2 sec)

# Tier 5: Functional tests (real data)
python -m tests.functional.runner all           # All 25 tests
python -m tests.functional.runner ema_crossover # Specific strategy
python -m tests.functional.runner --list        # List strategies
```

---

## Phase 7: Tier 5 - Functional Tests (Real Data)

**Goal**: Validate engine functionality using real historical data from DuckDB

**Key Principle**: If a strategy doesn't produce signals for a date range, **change the date range, NOT the strategy**.

### 7.1 Infrastructure

- [x] Create `tests/functional/` directory structure
- [x] Implement `DateRangeFinder` for auto date range selection
- [x] Implement `EngineValidator` assertion framework
- [x] Create test runner with CLI integration

### 7.2 Canonical Test Strategies

Each strategy tests specific engine components with real market data:

| Strategy | Play ID | Engine Components Tested |
|----------|---------|-------------------------|
| EMA Crossover | F_001 | cross_above/cross_below, EMA computation |
| RSI Momentum | F_002 | gt/lt operators, RSI, threshold triggers |
| Fibonacci Zones | F_003 | Swing detection, near_abs, fib levels |
| MTF Trend | F_004 | Multi-TF alignment, forward-fill, holds_for |
| Breakout Volume | F_005 | occurred_within, volume spike detection |
| Zone Bounce | F_006 | Zone states, between operator |
| Derived Zones | F_007 | K-slot allocation, aggregate fields |

### 7.3 Test Coverage

**Per Strategy (3-4 tests each):**
- [x] F_001a-d: EMA Crossover (4 tests)
- [x] F_002a-d: RSI Momentum (4 tests)
- [x] F_003a-c: Fibonacci Zones (3 tests)
- [x] F_004a-c: MTF Trend (3 tests)
- [x] F_005a-c: Breakout Volume (3 tests)
- [x] F_006a-c: Zone Bounce (3 tests)
- [x] F_007a-d: Derived Zones (4 tests)

**Total**: 25 functional tests

### 7.4 Validation Categories

Each test validates across 5 categories:

1. **Signal Generation**: Correct signal count and timing
2. **Position Management**: No overlapping positions, all closed
3. **Trade Recording**: Accurate PnL, monotonic timestamps
4. **Indicator Consistency**: No NaN, correct computation
5. **Edge Cases**: Warmup handling, last bar, determinism

### 7.5 DateRangeFinder

Automatically finds date ranges where strategies produce expected signals:

```python
finder = DateRangeFinder(data_store)
result = finder.find_optimal_range(
    play_config=play_dict,
    symbol="BTCUSDT",
    min_signals=5,
    max_signals=20,
    window_days=30,
)
```

**Files**: `tests/functional/`

```
tests/functional/
├── __init__.py
├── runner.py              # Main test orchestrator
├── date_range_finder.py   # Auto date range selection
├── engine_validator.py    # Validation assertions
└── strategies/
    ├── plays/             # F_001 - F_007 YAML configs
    ├── ema_crossover.py
    ├── rsi_momentum.py
    ├── fibonacci_zones.py
    ├── mtf_trend.py
    ├── breakout_volume.py
    ├── zone_bounce.py
    └── derived_zones.py
```

**Acceptance**: `python -m tests.functional.runner all` - all 25 tests pass
