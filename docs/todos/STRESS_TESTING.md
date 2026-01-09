# Stress Testing Progress Tracker

Progressive complexity testing from 0% to 100%.

**Started**: 2026-01-08
**Status**: IN_PROGRESS
**Current Gate**: Phase 2 (Gates 2.1-2.4)
**Last Updated**: 2026-01-09

---

## Resume Protocol

**To continue stress testing after context compaction:**

1. Read this file (`docs/todos/STRESS_TESTING.md`) to find current gate
2. Read `docs/audits/STRESS_TEST_BUGS.md` for bug tracking context
3. Check existing Play files in `tests/stress/plays/`
4. Resume at next PENDING gate

**Current Next Step**: Gate 2.2 - MACD Signal Cross (30%)

**Open Items Requiring Decision**:
- DEBT-001: Symbol vs Word operators - see `docs/audits/STRESS_TEST_BUGS.md` for options

---

## Workflow

### For Each Gate

1. **Create Play YAML** in `tests/stress/plays/S_{level}_{symbol}_{description}.yml`
2. **Run backtest**: `python trade_cli.py backtest run --play <ID> --start <date> --end <date> --fix-gaps --dir tests/stress/plays`
3. **Review results**:
   - If trades > 0: Gate PASSED, document results
   - If trades = 0: Investigate (could be restrictive conditions OR engine bug)
   - If error: Document as BUG in `docs/audits/STRESS_TEST_BUGS.md`
4. **Bug handling protocol**:
   - Understand root cause
   - Communicate with human to confirm understanding
   - Agree on fix approach
   - Implement fix
   - Re-run test
5. **Update this tracker** with gate status and results

### Bug Documentation Required

All bugs go to `docs/audits/STRESS_TEST_BUGS.md` with:
- Bug ID, Gate, Severity, Status
- Symptoms, Root Cause, Reproduction steps
- Resolution and Files Changed
- Lesson Learned

### Play YAML Adjustments

Non-bug adjustments (config tuning) also documented in bug tracker under "Play YAML Adjustments (Non-Bug)" section.

### Test Windows by Complexity

| Complexity | Window | Rationale |
|------------|--------|-----------|
| 0-20% | 2 weeks | Basic mechanics |
| 20-40% | 1 month | Crossover strategies need trend cycles |
| 40-60% | 1-2 months | Window operators need sustained patterns |
| 60-80% | 2-3 months | Structures need multiple swing cycles |
| 80-100% | 3-6 months | Full complexity needs varied market regimes |

### Backtest Command Template

```bash
# Standard run
python trade_cli.py backtest run --play <PLAY_ID> --start <YYYY-MM-DD> --end <YYYY-MM-DD> --fix-gaps --dir tests/stress/plays

# With snapshots for debugging
python trade_cli.py backtest run --play <PLAY_ID> --start <YYYY-MM-DD> --end <YYYY-MM-DD> --fix-gaps --dir tests/stress/plays --emit-snapshots
```

---

## Phase 0: Setup - COMPLETED

- [x] Create `tests/stress/plays/` directory
- [x] Create `docs/todos/STRESS_TESTING.md` (this file)
- [x] Create `docs/audits/STRESS_TEST_BUGS.md`

### Existing Play Files

| File | Gate | Description |
|------|------|-------------|
| `S_01_btc_single_ema.yml` | 1.1 | Single EMA threshold |
| `S_02_btc_rsi_threshold.yml` | 1.2 | RSI oversold/overbought |
| `S_03_btc_two_indicators.yml` | 1.3 | EMA + RSI independent |
| `S_04_btc_basic_and.yml` | 1.4 | AND condition (EMA + RSI) |
| `S_05_btc_multi_output.yml` | 1.5 | BBands multi-output fields |
| `S_06_btc_ema_crossover.yml` | 2.1 | EMA 9/21 crossover |

---

## Phase 1: Foundation (0-20% Complexity)

### Gate 1.1 - Single EMA (0%) - STATUS: PASSED

**Bugs Found**:
- BUG-001 RESOLVED: Timezone-naive vs timezone-aware datetime comparison error
- BUG-002 RESOLVED: 100% sizing with 1x leverage rejects all orders (CONFIG issue)

#### BTCUSDT
- [x] Create Play YAML
- [x] Run full backtest
- [x] Review metrics
- [x] Document findings

**Backtest Results (2024-12-15 to 2025-01-01)**:
- Trades: 124 (19W / 105L) - **ENGINE FUNCTIONING**
- Win Rate: 15.3%
- Net PnL: -$1,937.75 (-19.4%)
- Time in Market: 50.1%
- Artifacts: `backtests/_validation/S_01_btc_single_ema/BTCUSDT/5d68f06e8158`

**Gate Status**
- **Result**: PASSED
- **Bugs Found**: 2 (both resolved)
- **Notes**: Engine correctly executes basic EMA strategy. Poor performance expected (whipsaw market).

---

### Gate 1.2 - RSI Threshold (5%) - STATUS: PASSED

#### BTCUSDT
- [x] Create Play YAML
- [x] Run full backtest
- [x] Review metrics
- [x] Document findings

**Backtest Results (2024-12-15 to 2025-01-01)**:
- Trades: 11 (2W / 9L) - **ENGINE FUNCTIONING**
- Win Rate: 18.2%
- Net PnL: -$1,276.77 (-12.8%)
- Time in Market: 51.9%

**Bug Targets Validated**:
- RSI oscillator computation: PASS
- Threshold comparison (lt, gt): PASS
- Single-output indicator access: PASS

**Gate Status**
- **Result**: PASSED
- **Bugs Found**: 0
- **Notes**: RSI indicator working correctly, threshold operators validated

---

### Gate 1.3 - Two Indicators (10%) - STATUS: PASSED

#### BTCUSDT
- [x] Create Play YAML
- [x] Run full backtest
- [x] Review metrics

**Backtest Results (2024-12-15 to 2025-01-01)**:
- Trades: 52 (20W / 32L) - **ENGINE FUNCTIONING**
- Win Rate: 38.5%
- Net PnL: -$1,527.05 (-15.3%)

**Bug Targets Validated**:
- Multiple feature declaration: PASS
- Independent signal evaluation: PASS

**Gate Status**
- **Result**: PASSED
- **Bugs Found**: 0

---

### Gate 1.4 - Basic AND (15%) - STATUS: PASSED

#### BTCUSDT
- [x] Create Play YAML
- [x] Run full backtest
- [x] Review metrics

**Backtest Results (2024-12-15 to 2025-01-01)**:
- Trades: 22 (9W / 13L) - **ENGINE FUNCTIONING**
- Win Rate: 40.9%
- Net PnL: -$1,464.91 (-14.7%)

**Bug Targets Validated**:
- `all:` block evaluation: PASS
- Condition short-circuiting: PASS

**Gate Status**
- **Result**: PASSED
- **Bugs Found**: 0

---

### Gate 1.5 - Multi-Output (20%) - STATUS: PASSED

**Bugs Found**:
- BUG-003 RESOLVED: BBands all NaN due to int/float column name mismatch

#### BTCUSDT
- [x] Create Play YAML
- [x] Run full backtest
- [x] Review metrics

**Backtest Results (2024-12-15 to 2025-01-01)**:
- Trades: 34 (20W / 14L) - **ENGINE FUNCTIONING**
- Win Rate: 58.8%
- Net PnL: -$385.03 (-3.9%)

**Bug Targets Validated**:
- Multi-output indicator field access: PASS
- Struct reference syntax: PASS
- BBands computation: PASS (after fix)

**Gate Status**
- **Result**: PASSED
- **Bugs Found**: 1 (BUG-003 - RESOLVED)

---

## Phase 2: Basic Strategy (20-40% Complexity)

**Test Window**: 1 month (need trend cycles for crossovers)
**Suggested Range**: 2024-12-01 to 2025-01-01

### Gate 2.1 - EMA Crossover (25%) - STATUS: PASSED

**Bug Targets**: `cross_above`/`cross_below` operators, history offset access

#### BTCUSDT
- [x] Create Play YAML (`S_06_btc_ema_crossover.yml`)
- [x] Run full backtest (1 month window)
- [x] Review metrics
- [x] Document findings

**Backtest Results (2024-12-01 to 2025-01-01)**:
- Trades: 80 (14W / 66L) - **ENGINE FUNCTIONING**
- Win Rate: 17.5%
- Net PnL: -$2,061.28 (-20.6%)
- Time in Market: 48.6%
- Artifacts: `backtests/_validation/S_06_btc_ema_crossover/BTCUSDT/45e36e252667`

**Bug Targets Validated**:
- `cross_above` operator: PASS
- `cross_below` operator: PASS
- History offset access for crossover: PASS

**Documentation Bug Found**:
- DOC-001: Cookbook shows BBands outputs as `bbl/bbm/bbu` but registry uses `lower/middle/upper`

**Gate Status**
- **Result**: PASSED
- **Bugs Found**: 0 engine bugs (1 cookbook doc bug)

---

### Gate 2.2 - MACD Signal Cross (30%) - STATUS: PENDING

**Bug Targets**: Cross operator with multi-output struct field references

**Play Template** (uses registry field names: `macd`, `signal`, `histogram`):
```yaml
features:
  macd_12_26_9:
    indicator: macd
    params: {fast: 12, slow: 26, signal: 9}
actions:
  entry_long:
    all:
      - [{feature_id: "macd_12_26_9", field: "macd"}, "cross_above",
         {feature_id: "macd_12_26_9", field: "signal"}]
  exit_long:
    all:
      - [{feature_id: "macd_12_26_9", field: "macd"}, "cross_below",
         {feature_id: "macd_12_26_9", field: "signal"}]
```

**Note**: Registry uses `signal` not `macd_signal` (DOC-002 documents cookbook error)

#### BTCUSDT
- [ ] Create Play YAML (`S_07_btc_macd_cross.yml`)
- [ ] Run full backtest
- [ ] Review metrics
- [ ] Document findings

---

### Gate 2.3 - OR Conditions (35%) - STATUS: PENDING

**Bug Targets**: `any:` block evaluation, mixed literal/field comparisons

**Play Template**:
```yaml
features:
  rsi_14:
    indicator: rsi
    params: {length: 14}
  bbands_20_2:
    indicator: bbands
    params: {length: 20, std: 2}
actions:
  entry_long:
    any:
      - ["rsi_14", "lt", 25]
      - ["close", "lt", {feature_id: "bbands_20_2", field: "lower"}]
  exit_long:
    any:
      - ["rsi_14", "gt", 75]
      - ["close", "gt", {feature_id: "bbands_20_2", field: "upper"}]
```

#### BTCUSDT
- [ ] Create Play YAML (`S_08_btc_or_conditions.yml`)
- [ ] Run full backtest
- [ ] Review metrics
- [ ] Document findings

---

### Gate 2.4 - Simple Arithmetic (40%) - STATUS: PENDING

**Bug Targets**: Arithmetic expression evaluation, expanded condition syntax

**Play Template**:
```yaml
features:
  ema_9:
    indicator: ema
    params: {length: 9}
  ema_21:
    indicator: ema
    params: {length: 21}
  rsi_14:
    indicator: rsi
    params: {length: 14}
actions:
  entry_long:
    all:
      - lhs: ["ema_9", "-", "ema_21"]
        op: gt
        rhs: 0
      - ["rsi_14", "lt", 50]
  exit_long:
    all:
      - lhs: ["ema_9", "-", "ema_21"]
        op: lt
        rhs: 0
```

#### BTCUSDT
- [ ] Create Play YAML (`S_09_btc_arithmetic.yml`)
- [ ] Run full backtest
- [ ] Review metrics
- [ ] Document findings

---

## Phase 3: Intermediate (40-60% Complexity)

### Gate 3.1 - holds_for (45%) - STATUS: PENDING
### Gate 3.2 - occurred_within (50%) - STATUS: PENDING
### Gate 3.3 - Duration Window (55%) - STATUS: PENDING
### Gate 3.4 - Multi-TF Features (60%) - STATUS: PENDING

---

## Phase 4: Advanced (60-80% Complexity)

### Gate 4.1 - Swing Structure (65%) - STATUS: PENDING
### Gate 4.2 - Fibonacci Levels (70%) - STATUS: PENDING
### Gate 4.3 - Complex Arithmetic (75%) - STATUS: PENDING
### Gate 4.4 - count_true Window (80%) - STATUS: PENDING

---

## Phase 5: Expert (80-100% Complexity)

### Gate 5.1 - Derived Zones (85%) - STATUS: PENDING
### Gate 5.2 - Case-Based Actions (90%) - STATUS: PENDING
### Gate 5.3 - Multi-TF Structures (95%) - STATUS: PENDING
### Gate 5.4 - Full Complexity (100%) - STATUS: PENDING

---

## Summary

| Phase | Gates | Passed | Blocked | Bugs |
|-------|-------|--------|---------|------|
| 1 - Foundation | 1.1-1.5 | 5 | 0 | 3 (resolved) |
| 2 - Basic | 2.1-2.4 | 1 | 0 | 0 |
| 3 - Intermediate | 3.1-3.4 | 0 | 0 | 0 |
| 4 - Advanced | 4.1-4.4 | 0 | 0 | 0 |
| 5 - Expert | 5.1-5.4 | 0 | 0 | 0 |
| **Total** | **20** | **6** | **0** | **3 (resolved)** |

### Open Items

| ID | Type | Description | Status |
|----|------|-------------|--------|
| DOC-001 | Doc Bug | Cookbook BBands outputs wrong (`bbl` vs `lower`) | OPEN |
| DOC-002 | Doc Bug | Cookbook MACD outputs wrong (`macd_signal` vs `signal`) | OPEN |
| DEBT-001 | Tech Debt | Symbol-to-word operator conversion shim | OPEN - needs decision |

See `docs/audits/STRESS_TEST_BUGS.md` for full details.

---

## Session Handoff Notes (2026-01-09)

**Completed This Session**:
- Gate 2.1 (EMA Crossover) - PASSED with 80 trades
- Verified Phase 1 Plays match registry (not cookbook)
- Identified cookbook documentation bugs (DOC-001, DOC-002)
- Identified technical debt (DEBT-001) - symbol/word operator shim

**Next Session Start Point**:
- Gate 2.2: MACD Signal Cross (30%)
- Use registry field names: `field: "signal"` (not `macd_signal`)
- Template in Gate 2.2 section needs update to match registry
