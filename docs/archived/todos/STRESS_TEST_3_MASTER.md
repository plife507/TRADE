# Stress Test 3.0: Master TODO

**Status**: IN PROGRESS (Gate 0 COMPLETE)
**Created**: 2026-01-09
**Goal**: 100% coverage of all 6 structure types
**Progress**: 8/136 plays PASSED

---

## Rules

1. **Sequential execution** - One backtest at a time, no parallel DB access
2. **CLI only** - Use `python trade_cli.py backtest run --play <name> --dir <path> --fix-gaps --emit-snapshots`
3. **No 0 trades** - Loosen conditions if play generates 0 trades
4. **Debug actual bugs** - Use debugger agent for engine issues
5. **Human in loop** - Confirm syntax/cookbook issues before changing
6. **Update after each gate** - Use docs-writer agent to update this file
7. **THOROUGH VALIDATION** - Spot-check minimum 5 trades per play, verify structure math is correct

## Validation Methodology

### Two-Layer Validation

**Layer 1: Tier 2 Math Tests (Pure Algorithms)**
- Location: `tests/validation/tier2_structures/`
- Tests: 25 known-answer tests for all 6 structure types
- Status: **25/25 PASSED** (verified 2026-01-09)

**Layer 2: Stress Test Plays (Engine Integration)**
- Verify engine produces correct structure outputs
- Spot-check 5+ trades per play against OHLCV data
- Cross-reference structure values with expected behavior

**"Generates trades" ≠ "Math is correct"**

For each play:
1. Run with `--emit-snapshots`
2. Inspect trade artifacts
3. Verify 5+ trades have correct structure values
4. Cross-reference structure output with expected behavior
5. Only proceed after validation passes

**What to verify per structure:**
| Structure | Verification |
|-----------|--------------|
| swing | high_level/low_level match actual pivot prices on chart |
| trend | direction matches HH/HL (up) or LH/LL (down) pattern |
| zone | upper/lower bound actual demand/supply zone |
| fibonacci | levels are correct % between anchor_high and anchor_low |
| rolling_window | value is actual min/max over N bars |
| derived_zone | K slots contain valid fib zones from pivots |

---

## Structure Registry (6 Types)

| Type | Status | Plays | Notes |
|------|--------|-------|-------|
| swing | TESTED (4/4) | gate_00_foundation, gate_01_ma_baseline, gate_02_crossover, gate_03_multioutput | Basic pivot detection |
| rolling_window | TESTED (4/4) | gate_04_trend, gate_05_volume, gate_06_two_indicator, gate_07_all_operator | O(1) min/max |
| trend | NOT TESTED | 0/? | Direction classification |
| zone | NOT TESTED | 0/? | Demand/supply zones |
| fibonacci | NOT TESTED | 0/? | Retracement/extension |
| derived_zone | NOT TESTED | 0/? | K slots + aggregates |

---

## Gate Progress

| Gate | Name | Plays | Pass | Fail | Skip | Status |
|------|------|-------|------|------|------|--------|
| 0 | Foundation | 8 | 8 | 0 | 0 | COMPLETE |
| 1 | Swing Basics | 20 | 0 | 0 | 0 | NOT STARTED |
| 3 | Trend | 16 | 0 | 0 | 0 | NOT STARTED |
| 4 | Rolling Window | 16 | 0 | 0 | 0 | NOT STARTED |
| 6 | Fib Retracement | 18 | 0 | 0 | 0 | NOT STARTED |
| 8 | DZ Slots | 16 | 0 | 0 | 0 | NOT STARTED |
| 9 | DZ Aggregates | 24 | 0 | 0 | 0 | NOT STARTED |
| 11 | Struct+Indicator | 8 | 0 | 0 | 0 | NOT STARTED |
| 12 | Multi-Structure | 6 | 0 | 0 | 0 | NOT STARTED |
| 17 | Ultimate | 4 | 0 | 0 | 0 | NOT STARTED |
| **TOTAL** | | **136** | **8** | **0** | **0** | **5.9%** |

---

## Bugs Found

| Bug ID | Gate | Description | Status |
|--------|------|-------------|--------|
| BUG-016 | 0 | rolling_window used `field` param but cookbook said `source` | FIXED |

**BUG-016 Details:**
- **Issue**: rolling_window detector expected `field` parameter but Play DSL Cookbook documented `source`
- **Root Cause**: Inconsistency with feature naming conventions (features use `source`)
- **Fix**: Changed detector to use `source` parameter (better UX consistency)
- **File**: `src/backtest/incremental/detectors/rolling_window.py`
- **Validation**: All 4 rolling_window plays passed after fix

---

## Current Gate

**Gate**: 1 (Swing Basics - Next)
**Play**: gate_01_swing_basics_*.yml
**Status**: Ready to start

---

## Session Log

### Session 1: 2026-01-09

**Tier 2 Math Tests (BASELINE)**:
- [x] Ran tier2_structures tests: 25/25 PASSED
  - swing: 4 tests (T2_001-004)
  - fibonacci: 6 tests (T2_010-015)
  - zone: 4 tests (T2_020-023)
  - trend: 4 tests (T2_030-033)
  - rolling_window: 3 tests (T2_040-042)
  - derived_zone: 4 tests (T2_050-053)
- Pure algorithm validation complete ✓

**Gate 0 Results (COMPLETE)**:
- [x] Created master TODO
- [x] Gate 0: Foundation (8 plays) - ALL PASSED
  - Structures: swing (4 plays), rolling_window (4 plays)
  - Bug found and fixed: BUG-016 (rolling_window param naming)
  - All plays generated valid trades

**Next Gates** (To be executed):
- [ ] Gate 1: Swing Basics (20 plays)
- [ ] Gate 3: Trend (16 plays)
- [ ] Gate 4: Rolling Window (16 plays)
- [ ] Gate 6: Fib Retracement (18 plays)
- [ ] Gate 8: DZ Slots (16 plays)
- [ ] Gate 9: DZ Aggregates (24 plays)
- [ ] Gate 11: Struct+Indicator (8 plays)
- [ ] Gate 12: Multi-Structure (6 plays)
- [ ] Gate 17: Ultimate (4 plays)

---

## CLI Commands

```bash
# Run single play
python trade_cli.py backtest run --play <name> --dir <path> --fix-gaps

# Normalize gate
python trade_cli.py backtest play-normalize-batch --dir <path>
```
