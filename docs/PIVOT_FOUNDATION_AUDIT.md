# Pivot Foundation Audit Report

**Date**: 2026-01-16
**Status**: Complete (Gates 0-7)
**Branch**: feature/unified-engine

---

## Executive Summary

The pivot foundation system provides the base infrastructure for all market structure analysis in TRADE. This audit verified the correctness of three core detectors:

1. **Swing Detector** (`src/structures/detectors/swing.py`) - Pivot point detection
2. **Trend Detector** (`src/structures/detectors/trend.py`) - Wave-based trend classification
3. **Market Structure Detector** (`src/structures/detectors/market_structure.py`) - BOS/CHoCH events

**Bugs Fixed**:
- BUG #1: Trend detector wave comparison was comparing to itself (self-comparison bug)
- BUG #2: Market structure BOS was firing on every consecutive bar above break level
- CLEANUP: Removed unused `field` import from base.py

All components passed validation with 26/26 validation plays and 5/5 stress tests.

---

## Bugs Found and Fixed

### BUG FIX #1: Trend Detector Wave Comparison Bug (FIXED)

**Location**: `src/structures/detectors/trend.py:308-318`

**Issue**: The trend detector was comparing wave START levels against `_prev_same_type`, but `_prev_same_type` held the same swing level (comparing to itself).

**Example**:
```
Sequence: H1=100 -> L1=88 -> H2=105 -> L2=90

Wave 2 (L1->H2) analysis:
- Wave start is L1 = 88
- _prev_low was also 88 (set when L1 was detected)
- is_higher_low = 88 > 88 = False  <-- BUG: comparing to itself
```

**Root Cause**: When a swing low (L1) was detected, `_prev_low` was updated to L1's level. Then when the next wave (L1->H2) was formed, the START of that wave (L1) was compared against `_prev_low`, which was the same value.

**Fix**: Removed the redundant START comparison logic. Only compare wave END to previous same-type level. The wave START was already compared as the END of the previous wave, so comparing it again was both redundant and buggy.

**Code Change** (lines 308-318):
```python
# Before (buggy):
if start_type == "low" and not math.isnan(self._prev_low):
    wave.is_higher_low = start_level > self._prev_low  # Compares to itself!
    wave.is_lower_low = start_level < self._prev_low

# After (fixed):
# Only compare the END of the wave to previous same-type level.
# The START was already compared as the END of the previous wave,
# so comparing it again would be redundant and buggy (compares to itself).
if end_type == "high" and not math.isnan(self._prev_high):
    wave.is_higher_high = end_level > self._prev_high
    wave.is_lower_high = end_level < self._prev_high

if end_type == "low" and not math.isnan(self._prev_low):
    wave.is_lower_low = end_level < self._prev_low
    wave.is_higher_low = end_level > self._prev_low
```

**Verification**:
- Unit test (H1->L1->H2->L2): direction=1 (uptrend), last_hh=True, last_hl=True
- All 26 validation plays pass
- All 5 pivot foundation stress tests pass

---

### BUG FIX #2: Market Structure BOS Repeat Trigger (FIXED)

**Location**: `src/structures/detectors/market_structure.py`

**Issue**: BOS was firing on every bar above the break level (e.g., bars 21, 22, 23, 24 in test) instead of firing once per break.

**Root Cause**: After a BOS fired, the code set `break_level` to `prev_prev_swing` (the previous-previous swing level), but that level was ALSO already broken. This caused BOS to fire repeatedly on consecutive bars while price remained above the broken level.

**Example**:
```
Bar 20: Price breaks above swing high at 105 -> BOS fires
Bar 21: break_level reset to prev_prev_high (100), but price (106) > 100 -> BOS fires again!
Bar 22: Same pattern repeats -> BOS fires again!
```

**Fix**: Changed all three break-checking methods to always set `break_level = NaN` after a BOS fires:
- `_check_bullish_bias_breaks()` - Sets `_break_level_high = NaN` after bullish BOS
- `_check_bearish_bias_breaks()` - Sets `_break_level_low = NaN` after bearish BOS
- `_check_ranging_breaks()` - Sets respective break level to NaN after any BOS

**Behavior Change**: Now requires a NEW swing to form before another BOS can trigger in that direction. This is the correct semantic - BOS means "break of structure", not "price above structure".

**Verification**:
- Market structure BOS fires exactly once per break event
- CHoCH logic unaffected (different mechanism)
- All validation plays pass

---

### CLEANUP: Unused Import (FIXED)

**Location**: `src/structures/base.py:23`

**Issue**: Unused `field` import from dataclasses module.

**Fix**: Removed the unused import.

---

## Verification Tests Passed

The following verification tests were run after all bug fixes:

| Test | Status | Notes |
|------|--------|-------|
| Incremental/live trading state persistence | PASS | All state stored in detector instance attributes |
| Market structure BOS fires once per break | PASS | No repeated triggers on consecutive bars |
| State determinism | PASS | Same bars produce same events |
| Trend detector wave tracking | PASS | HH/HL/LH/LL flags correct |
| No NaN corruption in swing levels | PASS | Levels remain valid after BOS |
| Clean deprecated code scan | PASS | Only 1 trivial unused import found (now removed) |

---

## Components Audited

### 1. Swing Detector (`src/structures/detectors/swing.py`)

The swing detector provides pivot point detection with two modes: fractal (fixed bar count) and ATR zigzag (volatility-adaptive).

| Test Case | Status | Notes |
|-----------|--------|-------|
| Fractal mode basic detection | PASS | V_PF_001-003, left/right window |
| ATR ZigZag mode | PASS | V_PF_030-031, atr_multiplier threshold |
| Strict alternation mode | PASS | V_PF_020-022, H-L-H-L sequence enforced |
| Significance calculation | PASS | V_PF_001, ATR multiple measurement |
| Major/minor classification | PASS | V_PF_002, threshold-based |
| Pairing state machine | PASS | pair_version increments on complete pairs |
| Min ATR move filter | PASS | V_PF_010, filters insignificant pivots |
| Min PCT move filter | PASS | V_PF_012, percentage-based filter |
| Combined filters | PASS | V_PF_013, both must pass |
| First pivot accepted | PASS | V_PF_014, no previous to compare |
| Equal values (ties) | PASS | Strict inequality: pivot_val must be strictly greater/less |

**Key Outputs Verified**:
- `high_level`, `high_idx` - Most recent swing high
- `low_level`, `low_idx` - Most recent swing low
- `high_significance`, `low_significance` - ATR multiples
- `high_is_major`, `low_is_major` - Threshold classification
- `pair_direction` - "bullish" (L->H) or "bearish" (H->L)
- `pair_version` - Increments only on complete pairs
- `version` - Increments on ANY pivot

### 2. Trend Detector (`src/structures/detectors/trend.py`)

The trend detector uses wave-based tracking to classify market trend direction and strength.

| Test Case | Status | Notes |
|-----------|--------|-------|
| Empty state handling | PASS | direction=0, strength=0, wave_count=0 |
| Single swing (no wave) | PASS | Pending state, no classification yet |
| Single wave (bearish/bullish) | PASS | direction from wave type, strength=0 |
| Equal prices (H2 == H1) | PASS | is_higher_high = False (strict comparison) |
| Uptrend sequence (HH + HL) | PASS | V_PF_041, direction=1 |
| Downtrend sequence (LH + LL) | PASS | V_PF_042, direction=-1 |
| Mixed/ranging | PASS | V_PF_043, direction=0 |
| Strength levels | PASS | V_PF_044, 2+ consecutive waves = strong (2) |
| Recovery scenario | PASS | V_PF_045, LL then HH,HH,HH detects recovery |
| Trend reversal detection | PASS | V_PF_046, version increments on direction change |
| Version increment | PASS | Only on direction change |

**Key Outputs Verified**:
- `direction` - 1 (uptrend), -1 (downtrend), 0 (ranging)
- `strength` - 0 (weak), 1 (normal), 2 (strong)
- `bars_in_trend` - Resets on direction change
- `wave_count` - Consecutive waves in same direction
- `last_wave_direction` - "bullish" or "bearish"
- `last_hh`, `last_hl`, `last_lh`, `last_ll` - Individual comparison flags
- `version` - Increments on direction change

### 3. Market Structure Detector (`src/structures/detectors/market_structure.py`)

The market structure detector identifies Break of Structure (BOS) and Change of Character (CHoCH) events.

| Test Case | Status | Notes |
|-----------|--------|-------|
| BOS bullish detection | PASS | V_PF_050, break above swing high in uptrend |
| BOS bearish detection | PASS | V_PF_051, break below swing low in downtrend |
| CHoCH bull-to-bear | PASS | V_PF_052, break below swing low in uptrend |
| CHoCH bear-to-bull | PASS | V_PF_053, break above swing high in downtrend |
| Event flag reset | PASS | V_PF_054, bos_this_bar/choch_this_bar reset each bar |
| Version increment | PASS | V_PF_055, increments on any structure event |
| Initial bias establishment | PASS | V_PF_056, first break establishes bias |
| confirmation_close option | PASS | Uses close vs wick for break detection |

**Key Outputs Verified**:
- `bias` - "bullish", "bearish", "ranging"
- `bos_this_bar` - True if BOS occurred this bar
- `choch_this_bar` - True if CHoCH occurred this bar
- `bos_direction` - "bullish", "bearish", "none"
- `choch_direction` - "bullish", "bearish", "none"
- `last_bos_idx`, `last_bos_level` - Last BOS event details
- `last_choch_idx`, `last_choch_level` - Last CHoCH event details
- `break_level_high`, `break_level_low` - Levels being watched
- `version` - Increments on any structure event

### 4. Incremental/Live Trading Considerations

| Aspect | Status | Notes |
|--------|--------|-------|
| State persistence | PASS | All state stored in detector instance attributes |
| No look-ahead bias | PASS | Pivots confirmed after `right` bars (fractal) or threshold (zigzag) |
| Warmup period | PASS | Registry provides warmup formulas based on params |
| O(1) updates | PASS | All updates are O(window) or better |
| Memory bounded | PASS | Fixed-size ring buffers and deques |

---

## Validation Test Coverage

### Validation Plays (26 total)

| Gate | Plays | Status |
|------|-------|--------|
| Gate 0 (Significance) | V_PF_001-003 | 3/3 PASS |
| Gate 1 (Filtering) | V_PF_010, 012-014 | 4/4 PASS |
| Gate 2 (Alternation) | V_PF_020-022 | 3/3 PASS |
| Gate 3 (ATR ZigZag) | V_PF_030-031 | 2/2 PASS |
| Gate 4 (Trend) | V_PF_040-046 | 7/7 PASS |
| Gate 5 (Market Structure) | V_PF_050-056 | 7/7 PASS |

### Stress Tests (5 total)

| Test | Symbol | Focus | Status |
|------|--------|-------|--------|
| S_PF_001 | BTC | ATR ZigZag long-term | PASS |
| S_PF_002 | ETH | High volatility period | PASS |
| S_PF_003 | SOL | Ranging/consolidation | PASS |
| S_PF_004 | BTC | MTF coordination | PASS |
| S_PF_005 | BTC | Mode comparison (fractal) | PASS |

---

## Performance Benchmarks

All performance targets exceeded:

| Component | Target | Measured | Status |
|-----------|--------|----------|--------|
| Swing update (fractal) | < 1ms/bar | 0.003 ms/bar | PASS |
| Swing update (zigzag) | < 1ms/bar | 0.002 ms/bar | PASS |
| Trend update | < 0.5ms/bar | 0.0002 ms/bar | PASS |
| Market structure update | < 0.5ms/bar | 0.0004 ms/bar | PASS |

---

## Open Issues

None identified. All components functioning correctly after bug fixes (2 bugs fixed + 1 cleanup).

---

## Test Commands

```bash
# Run all validation plays
python -c "
import subprocess
from pathlib import Path
dir_path = Path('tests/validation/plays/pivot_foundation')
for play in sorted(dir_path.glob('V_PF_*.yml')):
    result = subprocess.run(['python', 'trade_cli.py', 'backtest', 'run', '--play', play.stem, '--dir', str(dir_path), '--synthetic', '--no-artifacts'], capture_output=True)
    print(f'{play.stem}: {\"PASS\" if result.returncode == 0 else \"FAIL\"}')"

# Run stress tests
python trade_cli.py backtest run --play S_PF_001_btc_atr_zigzag --dir tests/stress/plays/pivot_foundation --fix-gaps
python trade_cli.py backtest run --play S_PF_002_eth_high_volatility --dir tests/stress/plays/pivot_foundation --fix-gaps
python trade_cli.py backtest run --play S_PF_003_sol_ranging --dir tests/stress/plays/pivot_foundation --fix-gaps
python trade_cli.py backtest run --play S_PF_004_multi_tf_coordination --dir tests/stress/plays/pivot_foundation --fix-gaps
python trade_cli.py backtest run --play S_PF_005_mode_comparison --dir tests/stress/plays/pivot_foundation --fix-gaps

# Run full smoke test
python trade_cli.py --smoke full
```

---

## Architecture Overview

```
src/structures/              # Canonical structure detectors
├── detectors/
│   ├── swing.py             # Pivot detection (Gates 0-3)
│   │   ├── mode: fractal    # Fixed bar-count window
│   │   ├── mode: atr_zigzag # Volatility-adaptive
│   │   ├── min_atr_move     # Significance filtering
│   │   ├── min_pct_move     # Percentage filtering
│   │   └── strict_alternation # H-L-H-L enforcement
│   │
│   ├── trend.py             # Wave-based trend (Gate 4)
│   │   ├── Wave dataclass   # Complete swing wave
│   │   ├── _waves deque     # Last 4 waves
│   │   └── direction/strength classification
│   │
│   └── market_structure.py  # BOS/CHoCH (Gate 5)
│       ├── bias tracking    # bullish/bearish/ranging
│       ├── BOS detection    # Continuation signals
│       └── CHoCH detection  # Reversal signals
│
├── registry.py              # Warmup formulas + output types
└── state.py                 # TFIncrementalState, MultiTFIncrementalState

tests/validation/plays/pivot_foundation/  # 26 validation plays
tests/stress/plays/pivot_foundation/      # 5 stress tests
```

---

## Recommendations

1. **Use ATR ZigZag mode** for high_tf structure analysis - produces cleaner pivots
2. **Use fractal mode with strict_alternation** for exec_tf entry timing
3. **Set appropriate min_atr_move** (1.0-2.0) to filter noise in choppy markets
4. **Monitor pair_version** for Fib anchor stability, not individual pivot version

---

## References

- Gate specification: `docs/todos/PIVOT_FOUNDATION_GATES.md`
- Session context: `docs/SESSION_HANDOFF.md`
- DSL examples: `docs/PLAY_DSL_COOKBOOK.md`
- Validation plays: `tests/validation/plays/pivot_foundation/`
- Stress tests: `tests/stress/plays/pivot_foundation/`
