# Stress Test 3.0: Market Structure Coverage

**Status**: IN PROGRESS
**Created**: 2026-01-09
**Goal**: 100% coverage of all 6 structure types and their output fields

---

## Overview

A comprehensive stress test focused exclusively on **market structures** (incremental detectors). This follows the same methodology as Stress Test 2.0 (indicator coverage) but targets the structure registry.

### Key Rules

1. **No parallel DB access** - Run backtests sequentially
2. **Use `--fill-gaps` flag** - Let CLI handle data fetching
3. **No 0-trade plays** - Loosen conditions if needed (check plumbing, not find alpha)
4. **Debug actual bugs** - Fix engine issues, not just syntax
5. **Human-in-loop for syntax/cookbook issues** - Don't assume DSL is correct

### Naming Convention

- **Play ID**: `S3_L_{gate}_{id}` (long) or `S3_S_{gate}_{id}` (short)
- **Directory**: `tests/stress/plays/struct_gate_XX_name/`

---

## Structure Registry (6 Types)

| Type | Depends On | Required Params | Key Outputs |
|------|------------|-----------------|-------------|
| `swing` | None | `left`, `right` | high_level, low_level, high_idx, low_idx, version, pair_* |
| `trend` | swing | None | direction, strength, bars_in_trend, version |
| `zone` | swing | `zone_type`, `width_atr` | state, upper, lower, anchor_idx, version |
| `fibonacci` | swing | `levels`, `mode` | level_0.382, level_0.5, anchor_high, anchor_low, range |
| `rolling_window` | None | `size`, `mode`, `source` | value |
| `derived_zone` | swing | `levels`, `mode`, `max_active` | zone{N}_*, active_count, any_*, closest_* |

---

## Gate Plan (17 Gates, ~170 Plays)

### Gate 0: Foundation (1-5%)
**Goal**: Basic structure declaration + simple field access

| ID | Name | Structure | Field | Direction |
|----|------|-----------|-------|-----------|
| 001 | swing_high_exists | swing | high_level > 0 | long |
| 002 | swing_high_exists | swing | high_level > 0 | short |
| 003 | swing_low_exists | swing | low_level > 0 | long |
| 004 | swing_low_exists | swing | low_level > 0 | short |
| 005 | rolling_max | rolling_window | value > 0 | long |
| 006 | rolling_max | rolling_window | value > 0 | short |
| 007 | rolling_min | rolling_window | value > 0 | long |
| 008 | rolling_min | rolling_window | value > 0 | short |

**Symbols**: BTCUSDT, ETHUSDT
**TF**: 15m
**Plays**: 8

---

### Gate 1: Swing Basics (6-10%)
**Goal**: All basic swing output fields

| ID | Name | Field Tested | Notes |
|----|------|--------------|-------|
| 009 | swing_high_level | high_level | Price level of swing high |
| 010 | swing_high_idx | high_idx | Bar index of swing high |
| 011 | swing_low_level | low_level | Price level of swing low |
| 012 | swing_low_idx | low_idx | Bar index of swing low |
| 013 | swing_version | version | Monotonic counter |
| 014 | swing_confirmed_idx | last_confirmed_pivot_idx | Last confirmed pivot bar |
| 015 | swing_confirmed_type | last_confirmed_pivot_type | "high" or "low" enum |

**Symbols**: BTCUSDT, SOLUSDT
**TF**: 15m, 1h
**Plays**: 14 (7 fields x 2 directions)

---

### Gate 2: Swing Pairing (11-15%)
**Goal**: Pair fields (L→H and H→L sequences) - UNTESTED in Stress 2.0!

| ID | Name | Field Tested | Notes |
|----|------|--------------|-------|
| 016 | pair_high_level | pair_high_level | Price of paired swing high |
| 017 | pair_low_level | pair_low_level | Price of paired swing low |
| 018 | pair_direction | pair_direction | 1 (L→H) or -1 (H→L) |
| 019 | pair_version | pair_version | Pair sequence counter |

**Note**: These fields track complete L→H or H→L swing sequences for coherent fibonacci anchoring.

**Symbols**: ETHUSDT, XRPUSDT
**TF**: 15m, 1h
**Plays**: 8 (4 fields x 2 directions)

---

### Gate 3: Trend Structure (16-20%)
**Goal**: All trend output fields

| ID | Name | Field Tested | Notes |
|----|------|--------------|-------|
| 020 | trend_up | direction == 1 | Uptrend detection |
| 021 | trend_down | direction == -1 | Downtrend detection |
| 022 | trend_neutral | direction == 0 | Ranging market |
| 023 | trend_strength | strength > 0 | Trend strength metric |
| 024 | trend_bars | bars_in_trend > 0 | Bars since trend start |
| 025 | trend_version | version > 0 | Direction change counter |

**Symbols**: BTCUSDT, SOLUSDT
**TF**: 15m, 1h
**Plays**: 12 (6 conditions x 2 directions)

---

### Gate 4: Rolling Window Variants (21-25%)
**Goal**: Different modes, sizes, sources

| ID | Name | Mode | Size | Source |
|----|------|------|------|--------|
| 026 | rolling_max_20_high | max | 20 | high |
| 027 | rolling_min_20_low | min | 20 | low |
| 028 | rolling_max_50_close | max | 50 | close |
| 029 | rolling_min_50_close | min | 50 | close |
| 030 | rolling_max_10_high | max | 10 | high |
| 031 | rolling_min_10_low | min | 10 | low |

**Symbols**: BTCUSDT, ETHUSDT
**TF**: 15m
**Plays**: 12 (6 variants x 2 directions)

---

### Gate 5: Zone Structure (26-30%)
**Goal**: Demand/supply zone fields

| ID | Name | Field Tested | Zone Type |
|----|------|--------------|-----------|
| 032 | zone_active_demand | state == "active" | demand |
| 033 | zone_active_supply | state == "active" | supply |
| 034 | zone_broken | state == "broken" | demand/supply |
| 035 | zone_upper | upper > 0 | demand |
| 036 | zone_lower | lower > 0 | supply |
| 037 | zone_anchor | anchor_idx > 0 | demand |
| 038 | zone_version | version > 0 | supply |

**Symbols**: BTCUSDT, LINKUSDT
**TF**: 15m, 1h
**Plays**: 14 (7 conditions x 2 directions)

---

### Gate 6: Fibonacci Retracement (31-40%)
**Goal**: Standard retracement levels and anchors

| ID | Name | Level/Field | Notes |
|----|------|-------------|-------|
| 039 | fib_236 | level_0.236 | 23.6% retracement |
| 040 | fib_382 | level_0.382 | 38.2% (golden ratio) |
| 041 | fib_500 | level_0.5 | 50% midpoint |
| 042 | fib_618 | level_0.618 | 61.8% (golden ratio) |
| 043 | fib_786 | level_0.786 | 78.6% deep retrace |
| 044 | fib_anchor_high | anchor_high | 0% reference |
| 045 | fib_anchor_low | anchor_low | 100% reference |
| 046 | fib_range | range | high - low distance |

**Mode**: retracement
**Symbols**: BTCUSDT, ETHUSDT, SOLUSDT
**TF**: 15m, 1h
**Plays**: 16 (8 fields x 2 directions)

---

### Gate 7: Fibonacci Extension (41-50%)
**Goal**: Extension modes and levels

| ID | Name | Mode | Level |
|----|------|------|-------|
| 047 | ext_100 | extension | level_1.0 |
| 048 | ext_127 | extension | level_1.272 |
| 049 | ext_161 | extension | level_1.618 |
| 050 | ext_200 | extension | level_2.0 |
| 051 | ext_up_127 | extension_up | level_1.272 |
| 052 | ext_up_161 | extension_up | level_1.618 |
| 053 | ext_down_127 | extension_down | level_1.272 |
| 054 | ext_down_161 | extension_down | level_1.618 |

**Symbols**: BTCUSDT, ETHUSDT
**TF**: 15m
**Plays**: 16 (8 variants x 2 directions)

---

### Gate 8: Derived Zone Slots (51-55%)
**Goal**: K slots pattern (zone0, zone1, zone2)

| ID | Name | Slot | Field |
|----|------|------|-------|
| 055 | dz_zone0_lower | zone0 | lower |
| 056 | dz_zone0_upper | zone0 | upper |
| 057 | dz_zone0_state | zone0 | state |
| 058 | dz_zone1_lower | zone1 | lower |
| 059 | dz_zone1_upper | zone1 | upper |
| 060 | dz_zone1_state | zone1 | state |
| 061 | dz_zone2_state | zone2 | state |
| 062 | dz_slot_inside | zone0 | inside |

**max_active**: 3
**Symbols**: BTCUSDT, ETHUSDT
**TF**: 15m
**Plays**: 16 (8 variants x 2 directions)

---

### Gate 9: Derived Zone Aggregates (56-60%)
**Goal**: Aggregate fields across all slots

| ID | Name | Field | Notes |
|----|------|-------|-------|
| 063 | dz_active_count | active_count | Count of active zones |
| 064 | dz_any_active | any_active | Boolean: any zone active |
| 065 | dz_any_touched | any_touched | Boolean: any zone touched |
| 066 | dz_any_inside | any_inside | Boolean: price inside any zone |
| 067 | dz_closest_lower | closest_active_lower | Nearest zone lower bound |
| 068 | dz_closest_upper | closest_active_upper | Nearest zone upper bound |
| 069 | dz_closest_idx | closest_active_idx | Index of closest zone |
| 070 | dz_source_version | source_version | Swing version tracker |

**Symbols**: BTCUSDT, SOLUSDT
**TF**: 15m
**Plays**: 16 (8 fields x 2 directions)

---

### Gate 10: Derived Zone Lifecycle (61-65%)
**Goal**: Zone aging and touch tracking - UNTESTED fields!

| ID | Name | Field | Notes |
|----|------|-------|-------|
| 071 | dz_age_bars | zone0_age_bars | Bars since zone formed |
| 072 | dz_touch_count | zone0_touch_count | Number of touches |
| 073 | dz_last_touch_age | zone0_last_touch_age | Bars since last touch |
| 074 | dz_touched_this_bar | zone0_touched_this_bar | Boolean |
| 075 | dz_newest_idx | newest_active_idx | Most recent zone index |
| 076 | dz_instance_id | zone0_instance_id | Unique zone identifier |

**Symbols**: BTCUSDT, ETHUSDT
**TF**: 15m
**Plays**: 12 (6 fields x 2 directions)

---

### Gate 11: Structure + Indicator (66-70%)
**Goal**: Combine structures with basic indicators

| ID | Name | Structure | Indicator |
|----|------|-----------|-----------|
| 077 | swing_ema | swing.high_level | ema_50 |
| 078 | swing_rsi | swing.low_level | rsi_14 |
| 079 | trend_rsi | trend.direction | rsi_14 |
| 080 | trend_ema | trend.strength | ema_21 |
| 081 | zone_atr | zone.upper/lower | atr_14 |
| 082 | fib_rsi | fib.level_0.618 | rsi_14 |
| 083 | rolling_ema | rolling.value | ema_50 |
| 084 | derived_rsi | derived.any_active | rsi_14 |

**Symbols**: BTCUSDT, ETHUSDT, SOLUSDT
**TF**: 15m
**Plays**: 16 (8 combos x 2 directions)

---

### Gate 12: Multi-Structure (71-75%)
**Goal**: Multiple structures in same Play

| ID | Name | Structures | Logic |
|----|------|------------|-------|
| 085 | swing_trend | swing + trend | Swing high + trend up |
| 086 | swing_fib | swing + fibonacci | Swing + fib level |
| 087 | swing_zone | swing + zone | Swing + zone active |
| 088 | trend_fib | trend + fibonacci | Trend + near fib |
| 089 | rolling_swing | rolling + swing | Breakout + swing |
| 090 | fib_derived | fibonacci + derived_zone | Fib + K slots |

**Symbols**: BTCUSDT, ETHUSDT
**TF**: 15m
**Plays**: 12 (6 combos x 2 directions)

---

### Gate 13: HTF Structures (76-80%)
**Goal**: Structures on higher timeframes (4h, 1h)

| ID | Name | Structure | HTF | Exec TF |
|----|------|-----------|-----|---------|
| 091 | swing_4h | swing | 4h | 15m |
| 092 | trend_1h | trend | 1h | 15m |
| 093 | fib_4h | fibonacci | 4h | 15m |
| 094 | zone_1h | zone | 1h | 15m |
| 095 | rolling_4h | rolling_window | 4h | 15m |
| 096 | derived_1h | derived_zone | 1h | 15m |

**Note**: Tests forward-fill behavior for structures on TF > exec.

**Symbols**: BTCUSDT, ETHUSDT
**TF**: 15m exec, 1h/4h HTF
**Plays**: 12 (6 structures x 2 directions)

---

### Gate 14: Complex Boolean + Structures (81-85%)
**Goal**: ALL/ANY operators with structure conditions

| ID | Name | Boolean | Structures |
|----|------|---------|------------|
| 097 | all_swing_trend | ALL | swing + trend |
| 098 | any_fib_zone | ANY | fib OR zone |
| 099 | nested_all_any | ALL[ANY, cond] | Nested logic |
| 100 | not_broken | NOT | zone.state != broken |
| 101 | all_3_structures | ALL | swing + trend + fib |
| 102 | any_derived_slots | ANY | zone0 OR zone1 active |

**Symbols**: BTCUSDT, SOLUSDT
**TF**: 15m
**Plays**: 12 (6 patterns x 2 directions)

---

### Gate 15: Temporal + Structures (86-90%)
**Goal**: Window operators with structure conditions

| ID | Name | Window Op | Structure |
|----|------|-----------|-----------|
| 103 | holds_trend | holds_for | trend.direction == 1 |
| 104 | occurred_swing | occurred_within | swing.version changed |
| 105 | holds_zone | holds_for | zone.state == active |
| 106 | occurred_touch | occurred_within | derived.any_touched |
| 107 | count_inside | count_true | derived.any_inside |
| 108 | holds_fib_near | holds_for_duration | near fib level |

**Symbols**: BTCUSDT, ETHUSDT
**TF**: 15m
**Plays**: 12 (6 patterns x 2 directions)

---

### Gate 16: Edge Cases (91-95%)
**Goal**: Boundary conditions and empty states

| ID | Name | Edge Case | Notes |
|----|------|-----------|-------|
| 109 | empty_slot | zone1_state == NONE | Empty K slot |
| 110 | no_zones | active_count == 0 | All zones broken |
| 111 | rapid_pivots | left=2, right=2 | Fast swings |
| 112 | large_window | size=100 | Big rolling window |
| 113 | warmup_period | First N bars | During warmup |
| 114 | all_fib_levels | 7 levels | Maximum fib config |

**Symbols**: BTCUSDT, XRPUSDT
**TF**: 15m
**Plays**: 12 (6 cases x 2 directions)

---

### Gate 17: Ultimate Complexity (96-100%)
**Goal**: Everything combined

| ID | Name | Components |
|----|------|------------|
| 115 | ultimate_6_structures | All 6 structure types |
| 116 | ultimate_htf_mtf | HTF + MTF structures |
| 117 | ultimate_boolean | ALL + ANY + NOT with structures |
| 118 | ultimate_temporal | holds_for + occurred_within |
| 119 | ultimate_indicators | 5+ indicators + structures |
| 120 | ultimate_everything | All of the above |

**Symbols**: BTCUSDT
**TF**: 15m exec, 1h MTF, 4h HTF
**Plays**: 12 (6 patterns x 2 directions)

---

## Execution Plan

### Phase 1: Play Generation
- [ ] Create directory structure
- [ ] Generate Gate 0-4 plays (Foundation + Swing + Rolling)
- [ ] Generate Gate 5-7 plays (Zone + Fibonacci)
- [ ] Generate Gate 8-10 plays (Derived Zones)
- [ ] Generate Gate 11-13 plays (Combos + HTF)
- [ ] Generate Gate 14-16 plays (Boolean + Temporal + Edge)
- [ ] Generate Gate 17 plays (Ultimate)
- [ ] Run `play-normalize-batch` on all gates

### Phase 2: Sequential Execution
- [ ] Gate 0: Foundation (8 plays)
- [ ] Gate 1: Swing Basics (14 plays)
- [ ] Gate 2: Swing Pairing (8 plays)
- [ ] Gate 3: Trend (12 plays)
- [ ] Gate 4: Rolling Window (12 plays)
- [ ] Gate 5: Zone (14 plays)
- [ ] Gate 6: Fib Retracement (16 plays)
- [ ] Gate 7: Fib Extension (16 plays)
- [ ] Gate 8: DZ Slots (16 plays)
- [ ] Gate 9: DZ Aggregates (16 plays)
- [ ] Gate 10: DZ Lifecycle (12 plays)
- [ ] Gate 11: Struct + Indicator (16 plays)
- [ ] Gate 12: Multi-Structure (12 plays)
- [ ] Gate 13: HTF Structures (12 plays)
- [ ] Gate 14: Complex Boolean (12 plays)
- [ ] Gate 15: Temporal Ops (12 plays)
- [ ] Gate 16: Edge Cases (12 plays)
- [ ] Gate 17: Ultimate (12 plays)

### Phase 3: Bug Fixes
- [ ] Document all bugs found (BUG-016+)
- [ ] Fix actual engine bugs
- [ ] Confirm syntax/cookbook issues with human
- [ ] Re-run failed plays after fixes

### Phase 4: Documentation
- [ ] Update STRESS_TEST_3_EXECUTION.md with results
- [ ] Update OPEN_BUGS.md with any new bugs
- [ ] Create validation plays (V_120+) for structures
- [ ] Final commit and push

---

## Expected Totals

| Category | Count |
|----------|-------|
| Gates | 18 (0-17) |
| Plays | ~170 |
| Structures Tested | 6/6 |
| Output Fields | ~50 |
| Symbols | 5 (BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, LINKUSDT) |

---

## Commands

```bash
# Normalize a gate
python trade_cli.py backtest play-normalize-batch --dir tests/stress/plays/struct_gate_XX/

# Run single play with fill-gaps
python trade_cli.py backtest run --play <path> --fill-gaps

# Run full validation
python trade_cli.py backtest audit-toolkit
```

---

## Bugs Found

| Bug ID | Description | Status |
|--------|-------------|--------|
| (none yet) | | |

---

## Session Log

### Session 1: 2026-01-09
- Created STRESS_TEST_3_TODO.md
- (execution pending)
