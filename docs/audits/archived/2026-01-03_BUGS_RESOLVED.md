# Archived Bugs - Resolved 2026-01-03

**Source**: Audit Swarm (2026-01-01) + Architecture Review (2026-01-02) + Bug Fix Sessions (2026-01-03)
**Status**: ALL RESOLVED - 72 total bugs fixed

---

## Summary

| Priority | Fixed | Description |
|----------|-------|-------------|
| P0 | 7 | Critical blockers - undefined vars, missing imports, non-determinism |
| P1 | 25 | High priority - memory leaks, O(n) performance, missing integrations |
| P2 | 28 | Medium priority - schema drift, fee calculations, validation gaps |
| P3 | 12 | Polish - naming conventions, dead code, documentation |

---

## Key Refactors Completed

### 1. Incremental State Architecture (2026-01-03)
- O(1) hot loop access via MonotonicDeque/RingBuffer
- STRUCTURE_REGISTRY parallel to INDICATOR_REGISTRY
- 5 structure detectors: swing, fibonacci, zone, trend, rolling_window
- Agent-composable IdeaCard blocks

### 2. 1m Evaluation Loop (2026-01-02)
- mark_price resolution in snapshot
- 1m TP/SL checking in hot loop
- 6 validation IdeaCards (V_60-V_65)

### 3. Market Structure Stages 0-7 (2026-01-01)
- SwingDetector, TrendClassifier, ZoneDetector
- Zone Interaction (touched, inside, time_in_zone)
- State Tracking (SignalState, ActionState, GateState, BlockState)

---

## P0 Fixes (7 total)

| ID | Issue | Fix |
|----|-------|-----|
| P0-01 | net_pnl missing entry fee | Added both entry + exit fees |
| P0-02 | Operator import from removed enum | Removed from imports |
| P0-03 | Undefined warmup_multiplier | Changed to warmup_bars |
| P0-04 | Missing math import | Added import math |
| P0-05 | Undefined timeframe variable | Changed to tf |
| P0-06 | Duplicate function definition | Renamed to build_features_from_preloaded_dfs() |
| P0-07 | Non-deterministic UUIDs | Sequential IDs (order_0001, pos_0001) |

---

## P1 Fixes (25 total)

### Architecture Review (2026-01-02)
| ID | Issue | Fix |
|----|-------|-----|
| P1-21 | Missing _idea_card initialization | Added in __init__ |
| P1-22 | Unbounded state history | Added max_history config |
| P1-23 | Pending orders memory leak | Auto-cleanup on fill/cancel |
| P1-24 | O(n) linear search in state tracker | Added _block_index dict |
| P1-25 | Incomplete liquidation integration | Wired into exchange.process_bar() |

### Bug Fix Session (2026-01-03)
| ID | Issue | Fix |
|----|-------|-----|
| BUG-001 | Double quote lookup in 1m rollup | Direct O(1) array access |
| BUG-002 | Exit fee calculation inconsistency | Use position.size_usdt |
| BUG-003 | Position size mismatch | Documented (intentional) |
| BUG-004 | StepResult.fills always empty | All fills now captured |
| P1-004 | RiskPolicy PortfolioSnapshot incomplete | Pass full portfolio state |
| P1-005 | Exit notional documentation | Added inline comment |
| P0-NEW | Liquidation fee method name | Changed to apply_liquidation_fee() |

### Earlier Fixes
| ID | Issue | Status |
|----|-------|--------|
| P1-09 | O(n) in bars_exec_high/low | FIXED by Incremental State |
| P1-12 | TREND assumes single SWING | FIXED - depends_on_swing param |
| P1-13 | Dual close detection | DOCUMENTED - same source data |
| P1-15 | Schema drift detection | DOCUMENTED - already fails loud |

---

## P2 Fixes (28 total)

| ID | Issue | Fix |
|----|-------|-----|
| P2-01 | Rollup open price | Added open_1m to QuoteState |
| P2-02 | Preflight coverage check | Documented correct semantics |
| P2-03 | Timestamp alignment | Added timezone-aware handling |
| P2-04 | Gate semantics | Added clarifying comment |
| P2-05 | Bounds checking | Added HTF path validation |
| P2-06 | Block history pruning | O(excess) instead of O(n) |
| P2-02 | UUID in trade ID | Sequential IDs |
| P2-03 | JSON without sort_keys | Added sort_keys=True |
| P2-04 | Legacy aliases | Removed SWING_OUTPUTS, TREND_OUTPUTS |
| P2-05 | Mixed NaN handling | Fixed in StructureStore.get_field() |
| P2-06 | ATR TODO unresolved | Resolved |
| P2-07 | String split in hot path | Added _PATH_CACHE |
| P2-08 | Duplicate operator aliases | Consolidated to registry.py |
| P2-09 | RULE_EVAL_SCHEMA_VERSION unused | Removed |
| P2-10 | History manager internal access | Fixed _bars_exec |
| P2-12 | StateTracker.reset() not called | Added reset() call |
| P2-13 | Engine hooks missing type hints | Added Callable type |
| P2-14 | PRICE_FIELDS incomplete | Added high/low |
| P2-15 | mark_price_source soft-fail | Fail-loud __post_init__ |
| P2-17 | Legacy CSV aliases | Removed |
| P2-21 | Dead Operator enum | Removed |
| P2-22 | has_path() returns True for NaN | Added NaN check |
| P2-23 | json.dump missing sort_keys | 6 files updated |
| P2-24 | fee_mode/position_mode not validated | Added __post_init__ |
| P2-25 | Funding uses entry price | Now uses mark_price |
| P2-26 | Schema migration bare try/except | Explicit exception handling |
| P2-27 | Instrument cache never expires | Added 1hr TTL |

---

## P3 Fixes (12 total)

| ID | Issue | Fix |
|----|-------|-----|
| P3-01 | Redundant R_ prefix | Removed from ReasonCode |
| P3-02 | Logical operators not implemented | Removed from docstrings |
| P3-03 | Docstring bullish vs UP/DOWN | Updated terminology |
| P3-04 | Missing TYPE_CHECKING guard | Analyzed, already correct |
| P3-05 | Inconsistent smoke test naming | Standardized names |
| P3-06 | Magic numbers in structure smoke | Extracted ~30 constants |
| P3-07 | Inconsistent version formats | Proper semver "0.1.0-dev" |
| P3-08 | Parquet version hardcoded | Added constants |
| P3-09 | Unused signal_id field | Removed from ActionState |
| P3-10 | GATE_CODE_DESCRIPTIONS pattern | Added .description property |
| P3-11 | IndicatorRegistry in two files | Renamed to IndicatorCompute |
| P3-12 | PositionMode in two files | Removed dead enum |

---

## Validation Passed

All fixes validated through:
- `backtest idea-card-normalize-batch` - 30/30 IdeaCards pass
- `backtest audit-toolkit` - 42/42 indicators pass
- `backtest audit-rollup` - 11/11 intervals pass
- `backtest structure-smoke` - All detectors pass
- `--smoke full` - All checks pass

---

## References

| Document | Purpose |
|----------|---------|
| docs/audits/2026-01-01/AUDIT_INDEX.md | Original audit executive summary |
| docs/audits/2026-01-01/FIX_PLAN.md | Remediation plan |
| docs/todos/INCREMENTAL_STATE_IMPLEMENTATION.md | Incremental state spec |
| docs/todos/1M_EVAL_LOOP_REFACTOR.md | 1m eval loop spec |
