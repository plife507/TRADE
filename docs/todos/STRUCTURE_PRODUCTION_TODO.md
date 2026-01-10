# Structure Module Production TODO

> **Status**: ACTIVE
> **Created**: 2026-01-10
> **Target**: Structure module production-ready
> **Review Doc**: `docs/reviews/STRUCTURE_MODULE_PRODUCTION_REVIEW.md`

---

## Current State Assessment

**136 stress test plays exist** across 18 gates:

| Gate | Name | Plays | Status |
|------|------|------:|--------|
| 00 | foundation | 8 | Ready to run |
| 01 | swing_basics | 20 | Ready to run |
| 02 | swing_pairing | 0 | **NEEDS PLAYS** |
| 03 | trend | 16 | Ready to run |
| 04 | rolling_window | 16 | Ready to run |
| 05 | zone | 0 | **NEEDS PLAYS** |
| 06 | fib_retracement | 18 | Ready to run |
| 07 | fib_extension | 0 | **NEEDS PLAYS** |
| 08 | dz_slots | 16 | Ready to run |
| 09 | dz_aggregates | 24 | Ready to run |
| 10 | dz_lifecycle | 0 | **NEEDS PLAYS** |
| 11 | struct_indicator | 8 | Ready to run |
| 12 | multi_struct | 6 | Ready to run |
| 13 | htf_structures | 0 | **NEEDS PLAYS** |
| 14 | complex_boolean | 0 | **NEEDS PLAYS** |
| 15 | temporal_ops | 0 | **NEEDS PLAYS** |
| 16 | edge_cases | 0 | **NEEDS PLAYS** |
| 17 | ultimate | 4 | Ready to run |

**Play naming**: `S3_L_NNN_*.yml` (long) / `S3_S_NNN_*.yml` (short)

**Location**: `tests/stress/plays/struct_gate_*`

---

## Execution Rules

1. **Sequential execution** - Gates must complete in order
2. **No parallel DB access** - DuckDB doesn't support concurrent writes
3. **Human-in-loop** - Major decisions require human approval
4. **Opus for coding** - Use `model="opus"` for all code changes
5. **Orchestrator for bugs** - Use `orchestrator` agent for multi-file fixes
6. **No legacy code** - Delete old code, don't wrap it

---

## Gate 0: Pre-Flight Validation

**Purpose**: Ensure environment is ready for stress testing

### Checklist

- [ ] **0.1** Verify tier-2 tests still pass
  ```bash
  python -m pytest tests/validation/tier2_structures/ -v
  ```
  - Expected: 25/25 PASS
  - If failures: STOP - fix regressions first

- [ ] **0.2** Verify existing stress test plays are valid YAML
  ```bash
  python trade_cli.py backtest normalize-batch tests/stress/plays/struct_gate_00_foundation --dry-run
  python trade_cli.py backtest normalize-batch tests/stress/plays/struct_gate_01_swing_basics --dry-run
  ```
  - Expected: All plays normalize without error
  - If failures: Fix YAML syntax issues

- [ ] **0.3** Verify database has BTCUSDT data
  ```bash
  python trade_cli.py data query-coverage BTCUSDT
  ```
  - Expected: At least 90 days of 1m/15m/1h/4h data
  - If insufficient: Run data sync first

- [ ] **0.4** Verification log ready
  - Location: `docs/reviews/STRUCTURE_VERIFICATION_LOG.md`

### Gate 0 Exit Criteria

- [ ] All pre-flight checks pass
- [ ] Human confirms ready to proceed

---

## Gate 1: Stress Test Execution

**Purpose**: Run existing 136 stress tests against real market data

### Phase 1.1: Foundation Tests (Gate 00)

- [ ] **1.1.1** Run foundation tests (8 plays)
  ```bash
  # Run sequentially - one play at a time
  for play in tests/stress/plays/struct_gate_00_foundation/*.yml; do
    python trade_cli.py backtest run "$play" --emit-snapshots
  done
  ```
  - Expected: 8/8 pass
  - Document results in verification log

### Phase 1.2: Swing Basics Tests (Gate 01)

- [ ] **1.2.1** Run swing basics tests (20 plays)
  ```bash
  for play in tests/stress/plays/struct_gate_01_swing_basics/*.yml; do
    python trade_cli.py backtest run "$play" --emit-snapshots
  done
  ```
  - Expected: 20/20 pass
  - Tests: high_level, low_level, high_idx, low_idx, version

### Phase 1.3: Trend Tests (Gate 03)

- [ ] **1.3.1** Run trend tests (16 plays)
  ```bash
  for play in tests/stress/plays/struct_gate_03_trend/*.yml; do
    python trade_cli.py backtest run "$play" --emit-snapshots
  done
  ```
  - Expected: 16/16 pass
  - Tests: direction_up, direction_down, strength, bars_in_trend

### Phase 1.4: Rolling Window Tests (Gate 04)

- [ ] **1.4.1** Run rolling window tests (16 plays)
  ```bash
  for play in tests/stress/plays/struct_gate_04_rolling_window/*.yml; do
    python trade_cli.py backtest run "$play" --emit-snapshots
  done
  ```
  - Expected: 16/16 pass
  - Tests: max_20_high, min_20_low, max_50_close, min_50_close

### Phase 1.5: Fibonacci Retracement Tests (Gate 06)

- [ ] **1.5.1** Run fibonacci tests (18 plays)
  ```bash
  for play in tests/stress/plays/struct_gate_06_fib_retracement/*.yml; do
    python trade_cli.py backtest run "$play" --emit-snapshots
  done
  ```
  - Expected: 18/18 pass
  - Tests: level_0.382, level_0.5, level_0.618, anchor_high, anchor_low, range

### Phase 1.6: Derived Zone Slots Tests (Gate 08)

- [ ] **1.6.1** Run derived zone slot tests (16 plays)
  ```bash
  for play in tests/stress/plays/struct_gate_08_dz_slots/*.yml; do
    python trade_cli.py backtest run "$play" --emit-snapshots
  done
  ```
  - Expected: 16/16 pass
  - Tests: zone0_lower, zone0_upper, zone0_state, zone1_lower

### Phase 1.7: Derived Zone Aggregates Tests (Gate 09)

- [ ] **1.7.1** Run derived zone aggregate tests (24 plays)
  ```bash
  for play in tests/stress/plays/struct_gate_09_dz_aggregates/*.yml; do
    python trade_cli.py backtest run "$play" --emit-snapshots
  done
  ```
  - Expected: 24/24 pass
  - Tests: active_count, any_active, any_touched, closest_active

### Phase 1.8: Structure + Indicator Tests (Gate 11)

- [ ] **1.8.1** Run combined structure + indicator tests (8 plays)
  ```bash
  for play in tests/stress/plays/struct_gate_11_struct_indicator/*.yml; do
    python trade_cli.py backtest run "$play" --emit-snapshots
  done
  ```
  - Expected: 8/8 pass

### Phase 1.9: Multi-Structure Tests (Gate 12)

- [ ] **1.9.1** Run multi-structure combination tests (6 plays)
  ```bash
  for play in tests/stress/plays/struct_gate_12_multi_struct/*.yml; do
    python trade_cli.py backtest run "$play" --emit-snapshots
  done
  ```
  - Expected: 6/6 pass

### Phase 1.10: Ultimate Tests (Gate 17)

- [ ] **1.10.1** Run ultimate complexity tests (4 plays)
  ```bash
  for play in tests/stress/plays/struct_gate_17_ultimate/*.yml; do
    python trade_cli.py backtest run "$play" --emit-snapshots
  done
  ```
  - Expected: 4/4 pass

### Gate 1 Summary

| Gate | Plays | Pass | Fail |
|------|------:|-----:|-----:|
| 00 foundation | 8 | | |
| 01 swing_basics | 20 | | |
| 03 trend | 16 | | |
| 04 rolling_window | 16 | | |
| 06 fib_retracement | 18 | | |
| 08 dz_slots | 16 | | |
| 09 dz_aggregates | 24 | | |
| 11 struct_indicator | 8 | | |
| 12 multi_struct | 6 | | |
| 17 ultimate | 4 | | |
| **TOTAL** | **136** | | |

### Gate 1 Exit Criteria

- [ ] All 136 stress tests pass (0 failures)
- [ ] All results documented in verification log
- [ ] Human reviews pass/fail summary
- [ ] If any failures: Create bug tickets, proceed to Gate 3

---

## Gate 2: Manual Verification Against Charts

**Purpose**: Visual confirmation that structure outputs match real price action

### Phase 2.1: Swing Pivot Verification

- [ ] **2.1.1** Select 5 trades from swing stress test output
  - Get trade entry timestamps from backtest artifacts
  - Note `swing.high_level` and `swing.low_level` values

- [ ] **2.1.2** Open TradingView at each timestamp (BTCUSDT, 15m)
  - Visually identify swing highs/lows on chart
  - Compare to detector output values

- [ ] **2.1.3** Document findings in verification log
  ```markdown
  ## Swing Verification
  | Trade # | Timestamp | Expected High | Actual High | Match |
  |---------|-----------|---------------|-------------|-------|
  | 1 | ... | ... | ... | ✅/❌ |
  ```

- [ ] **2.1.4** Calculate accuracy: ___/5 matches

### Phase 2.2: Trend Direction Verification

- [ ] **2.2.1** Select 5 trades with trend signals
  - Get timestamps and `trend.direction` values

- [ ] **2.2.2** Verify on chart
  - direction=1: Should see HH + HL pattern
  - direction=-1: Should see LH + LL pattern
  - direction=0: Should see mixed/ranging pattern

- [ ] **2.2.3** Document findings in verification log

- [ ] **2.2.4** Calculate accuracy: ___/5 matches

### Phase 2.3: Fibonacci Level Verification

- [ ] **2.3.1** Select 5 trades using fibonacci levels
  - Get `anchor_high`, `anchor_low`, `level_0.618` values

- [ ] **2.3.2** Verify arithmetic
  ```
  level_0.618 = anchor_high - 0.618 × (anchor_high - anchor_low)
  ```

- [ ] **2.3.3** Verify anchors match chart pivots

- [ ] **2.3.4** Document findings in verification log

- [ ] **2.3.5** Calculate accuracy: ___/5 matches

### Phase 2.4: Derived Zone State Verification

- [ ] **2.4.1** Select 5 bars with `any_active=true`
  - Verify at least one zone slot has state=ACTIVE

- [ ] **2.4.2** Verify `active_count` matches count of ACTIVE slots

- [ ] **2.4.3** Verify `closest_active_*` points to correct zone

- [ ] **2.4.4** Document findings in verification log

- [ ] **2.4.5** Calculate accuracy: ___/5 matches

### Phase 2.5: Rolling Window Verification

- [ ] **2.5.1** Select 5 bars with rolling_window values
  - Get `rolling_max.value` or `rolling_min.value`

- [ ] **2.5.2** Manually count N bars back, verify min/max

- [ ] **2.5.3** Document findings in verification log

- [ ] **2.5.4** Calculate accuracy: ___/5 matches

### Gate 2 Summary

| Structure | Samples | Matches | Accuracy |
|-----------|--------:|--------:|---------:|
| swing | 5 | | |
| trend | 5 | | |
| fibonacci | 5 | | |
| derived_zone | 5 | | |
| rolling_window | 5 | | |
| **TOTAL** | **25** | | |

### Gate 2 Exit Criteria

- [ ] Overall accuracy >= 95% (allow minor float precision differences)
- [ ] All discrepancies documented with root cause
- [ ] Human reviews verification results
- [ ] If accuracy < 95%: Create bug tickets, proceed to Gate 3

---

## Gate 3: Bug Fixes (Conditional)

**Purpose**: Fix any bugs discovered in Gates 1-2

### If Bugs Found

- [ ] **3.1** Create bug entry in `docs/audits/OPEN_BUGS.md`
  - Assign priority (P0/P1/P2)
  - Document reproduction steps
  - Include failing play path

- [ ] **3.2** Use orchestrator agent for multi-file fixes
  ```
  Use Task tool with subagent_type="orchestrator"
  Prompt: "Fix BUG-XXX: [description]. See OPEN_BUGS.md for details."
  Model: opus
  ```

- [ ] **3.3** Add regression test for each fix
  - Add to tier-2 tests if algorithm bug
  - Add new stress test play if integration bug

- [ ] **3.4** Re-run affected stress tests
  ```bash
  python trade_cli.py backtest run [failing_play.yml] --emit-snapshots
  ```
  - Verify fix resolves the issue
  - Verify no new regressions

- [ ] **3.5** Human review of fix
  - Code review required for P0/P1 bugs
  - Approve fix before proceeding

### If No Bugs Found

- [ ] **3.N** Mark Gate 3 as SKIPPED (no bugs found)

### Gate 3 Exit Criteria

- [ ] All P0 bugs fixed and verified
- [ ] All P1 bugs fixed or documented as known issues
- [ ] Regression tests added for each fix
- [ ] Human approves all fixes

---

## Gate 4: Missing Play Generation (Conditional)

**Purpose**: Generate plays for empty gates if needed for production

### Human Decision Required

- [ ] **4.0** Human decision: Generate missing plays?
  - **YES** - Need full coverage for production
  - **NO** - Current 136 plays sufficient
  - **PARTIAL** - Only critical gaps (zone, swing_pairing)

### Phase 4.1: Zone Structure Plays (Gate 05)

If approved:
- [ ] **4.1.1** Generate zone state plays
  ```
  Use Task tool with subagent_type="orchestrator"
  Prompt: "Generate stress test plays for zone structure (gate_05).
           Cover: state=ACTIVE, state=BROKEN, touch detection.
           Follow S3_L_/S3_S_ naming. Use swing as dependency."
  Model: opus
  ```

- [ ] **4.1.2** Validate generated plays
  ```bash
  python trade_cli.py backtest normalize-batch tests/stress/plays/struct_gate_05_zone --dry-run
  ```

- [ ] **4.1.3** Run generated plays
  ```bash
  for play in tests/stress/plays/struct_gate_05_zone/*.yml; do
    python trade_cli.py backtest run "$play" --emit-snapshots
  done
  ```

### Phase 4.2: Swing Pairing Plays (Gate 02)

If approved:
- [ ] **4.2.1** Generate swing pairing plays
  - Test pair_high_level, pair_low_level, pair_direction
  - Test pair_version increments
  - Test pair_anchor_hash stability

- [ ] **4.2.2** Validate and run generated plays

### Phase 4.3: Other Missing Gates

If full coverage approved:
- [ ] **4.3.1** Generate fib_extension plays (Gate 07)
- [ ] **4.3.2** Generate dz_lifecycle plays (Gate 10)
- [ ] **4.3.3** Generate htf_structures plays (Gate 13)
- [ ] **4.3.4** Generate complex_boolean plays (Gate 14)
- [ ] **4.3.5** Generate temporal_ops plays (Gate 15)
- [ ] **4.3.6** Generate edge_cases plays (Gate 16)

### Gate 4 Exit Criteria

- [ ] Human-approved scope completed
- [ ] All generated plays pass validation
- [ ] All generated plays execute successfully

---

## Gate 5: Enhancements (Optional)

**Purpose**: Add quality improvements identified in review

### Phase 5.1: CHoCH Explicit Field

- [ ] **5.1.0** Human decision: Add CHoCH field?
  - Yes: Proceed with implementation
  - No: Skip to Phase 5.2

- [ ] **5.1.1** Design CHoCH detection logic
  ```python
  # CHoCH = direction changed AND opposite structure formed
  # Bullish CHoCH: Was downtrend, broke above LH
  # Bearish CHoCH: Was uptrend, broke below HL
  ```

- [ ] **5.1.2** Implement in trend detector
  ```
  Use Task tool with subagent_type="orchestrator"
  Prompt: "Add choch_detected bool to trend detector.
           Output key: 'choch'. Type: BOOL.
           True when direction changes.
           Update registry with new output type."
  Model: opus
  ```

- [ ] **5.1.3** Add tier-2 test for CHoCH

- [ ] **5.1.4** Add stress test play for CHoCH

### Phase 5.2: Verbose Structures Debug Flag

- [ ] **5.2.0** Human decision: Add debug flag?
  - Yes: Proceed
  - No: Skip

- [ ] **5.2.1** Implement `--verbose-structures` CLI flag
  - Emit structure state at each bar to log
  - Useful for debugging pivot detection

### Gate 5 Exit Criteria

- [ ] All approved enhancements implemented
- [ ] Tests added for new functionality
- [ ] Human reviews changes

---

## Gate 6: Documentation & Sign-Off

**Purpose**: Complete documentation and get production approval

### Phase 6.1: Update Documentation

- [ ] **6.1.1** Complete `STRUCTURE_VERIFICATION_LOG.md`
  - All stress test results documented
  - All manual verification documented
  - All discrepancies explained

- [ ] **6.1.2** Update `OPEN_BUGS.md`
  - Mark fixed bugs as CLOSED
  - Document any known issues

- [ ] **6.1.3** Update `STRUCTURE_MODULE_PRODUCTION_REVIEW.md`
  - Change status to VERIFIED
  - Add verification summary table
  - Add final recommendations

- [ ] **6.1.4** Update `CLAUDE.md` if needed
  - Add any new structure usage patterns
  - Update registry documentation if keys changed

### Phase 6.2: Final Validation

- [ ] **6.2.1** Re-run full tier-2 test suite
  ```bash
  python -m pytest tests/validation/tier2_structures/ -v
  ```
  - Expected: All pass (25+ depending on additions)

- [ ] **6.2.2** Run backtest smoke test
  ```bash
  python trade_cli.py backtest metadata-smoke
  ```
  - Expected: PASS

- [ ] **6.2.3** Verify no regressions in existing plays
  ```bash
  python trade_cli.py backtest normalize-batch configs/plays/ --dry-run
  ```

### Phase 6.3: Human Sign-Off

- [ ] **6.3.1** Present verification summary to human

  **Gate 1 Results:**
  - Total stress tests: 136
  - Passed: ___
  - Failed: ___

  **Gate 2 Results:**
  - Manual verification accuracy: ___/25 (___%)

  **Gate 3 Results:**
  - Bugs found: ___
  - Bugs fixed: ___

  **Gate 4 Results:**
  - New plays generated: ___

  **Gate 5 Results:**
  - Enhancements added: ___

- [ ] **6.3.2** Human decision: Production ready?
  - **APPROVED**: Mark module as production-ready
  - **REJECTED**: Document concerns, return to appropriate gate

- [ ] **6.3.3** Update module status
  ```markdown
  # In STRUCTURE_MODULE_PRODUCTION_REVIEW.md
  > **Status**: PRODUCTION-READY
  > **Approved**: 2026-XX-XX
  > **Approver**: [Human]
  ```

### Gate 6 Exit Criteria

- [ ] All documentation complete
- [ ] All validation tests pass
- [ ] Human approves production status
- [ ] Module marked as PRODUCTION-READY

---

## Summary Checklist

| Gate | Description | Status |
|------|-------------|--------|
| Gate 0 | Pre-Flight Validation | ⬜ |
| Gate 1 | Stress Test Execution (136 plays) | ⬜ |
| Gate 2 | Manual Chart Verification | ⬜ |
| Gate 3 | Bug Fixes (Conditional) | ⬜ |
| Gate 4 | Missing Play Generation (Conditional) | ⬜ |
| Gate 5 | Enhancements (Optional) | ⬜ |
| Gate 6 | Documentation & Sign-Off | ⬜ |

---

## Execution Notes

### Agent Selection Guide

| Task | Agent | Model | Reason |
|------|-------|-------|--------|
| Run stress tests | Bash directly | N/A | Sequential CLI commands |
| Fix single-file bug | code-reviewer | opus | Focused fix |
| Fix multi-file bug | orchestrator | opus | Coordinates across modules |
| Generate plays | orchestrator | opus | May need Play patterns |
| Add new feature | orchestrator | opus | May touch multiple files |
| Write documentation | docs-writer | sonnet | Documentation specialist |
| Validate changes | validate | sonnet | Read-only checks |

### Human-in-Loop Checkpoints

| Checkpoint | Gate | Decision Required |
|------------|------|-------------------|
| Ready to proceed | Gate 0 | Confirm pre-flight passed |
| Review stress results | Gate 1 | Approve test results |
| Review verification | Gate 2 | Accept accuracy % |
| Approve bug fixes | Gate 3 | Code review P0/P1 |
| Missing play scope | Gate 4 | Full/partial/none |
| Enhancement scope | Gate 5 | Decide which to implement |
| Production approval | Gate 6 | Final sign-off |

### Failure Recovery

| Failure | Recovery Action |
|---------|-----------------|
| Pre-flight fails | Fix environment issues, re-run Gate 0 |
| Stress test fails | Create bug ticket, proceed to Gate 3 |
| Manual verification low accuracy | Investigate root cause, may need algorithm fix |
| Bug fix introduces regression | Revert, re-analyze, fix properly |
| Human rejects production | Document concerns, return to appropriate gate |

---

## Appendix: Stress Test Play Reference

### Play Naming Convention

```
S3_L_{NNN}_{structure}_{aspect}.yml  # Long direction
S3_S_{NNN}_{structure}_{aspect}.yml  # Short direction

Examples:
S3_L_001_swing_high_exists.yml
S3_S_002_swing_low_exists.yml
S3_L_020_trend_direction_up.yml
S3_L_052_fib_0382.yml
S3_L_070_dz_zone0_lower.yml
```

### Play Count by Gate

| Gate | Name | Plays |
|------|------|------:|
| 00 | foundation | 8 |
| 01 | swing_basics | 20 |
| 03 | trend | 16 |
| 04 | rolling_window | 16 |
| 06 | fib_retracement | 18 |
| 08 | dz_slots | 16 |
| 09 | dz_aggregates | 24 |
| 11 | struct_indicator | 8 |
| 12 | multi_struct | 6 |
| 17 | ultimate | 4 |
| **TOTAL** | | **136** |

### Empty Gates (Candidates for Generation)

| Gate | Name | Priority | Recommended Plays |
|------|------|----------|-------------------|
| 02 | swing_pairing | P1 | pair_direction, pair_version, pair_hash |
| 05 | zone | P1 | state transitions, touch, broken |
| 07 | fib_extension | P2 | extension_up, extension_down |
| 10 | dz_lifecycle | P2 | TTL, age tracking |
| 13 | htf_structures | P1 | 1h+15m combinations |
| 14 | complex_boolean | P2 | nested ALL/ANY with structures |
| 15 | temporal_ops | P2 | holds_for, occurred_within |
| 16 | edge_cases | P2 | rapid pivots, equal values |
