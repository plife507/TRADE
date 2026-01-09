# Stress Test Bug Tracker

Bugs discovered during progressive complexity testing.

**Testing Started**: 2026-01-08
**Last Updated**: 2026-01-09

---

## Bug Summary

| ID | Gate | Severity | Status | Description |
|----|------|----------|--------|-------------|
| BUG-001 | 1.1 | P0 | RESOLVED | Timezone-naive vs timezone-aware datetime comparison error |
| BUG-002 | 1.1 | P2 | RESOLVED | 100% sizing with 1x leverage rejects all orders (CONFIG) |
| BUG-003 | 1.5 | P0 | RESOLVED | BBands all NaN due to int/float column name mismatch |
| BUG-004 | 2.4 | P1 | RESOLVED | ArithmeticExpr not handled in execution_validation.py |
| BUG-005 | 3.1 | P1 | RESOLVED | Window operators not handled inside all:/any: blocks |
| BUG-006 | 3.3 | P1 | RESOLVED | Duration window operators missing from shorthand converter |
| BUG-007 | 4.1 | P0 | RESOLVED | Structures section not converted to Feature objects |
| BUG-008 | 5.2 | P1 | RESOLVED | Verbose action format doesn't resolve RHS feature references |
| DOC-001 | 2.1 | P3 | RESOLVED | Cookbook shows wrong BBands output names |
| DOC-002 | 2.1 | P3 | RESOLVED | Cookbook shows wrong MACD output names |
| DEBT-001 | 2.1 | P2 | RESOLVED | Symbol operators now canonical - shim removed |

---

## Technical Debt

### DEBT-001: Symbol operators standardization

**Gate**: 2.1 (found during Phase 1 verification)
**Severity**: P2 (architectural inconsistency, violates ALL FORWARD directive)
**Status**: RESOLVED (2026-01-09)

**Resolution**:
- Symbol operators (`>`, `<`, `>=`, `<=`, `==`, `!=`) are now the ONLY valid operators
- Word operators (`gt`, `lt`, `gte`, `lte`, `eq`) removed from engine
- `op_map` conversion shim removed from `play.py`
- Added `!=` operator (previously broken - mapped to non-existent "neq")
- All Play YAML files updated to use symbols
- 45+ files modified (engine code + test Plays + documentation)

**Changes Made**:
- `src/backtest/rules/dsl_nodes/constants.py` - Operators now symbols
- `src/backtest/rules/evaluation/condition_ops.py` - Dispatch uses symbols
- `src/backtest/rules/eval.py` - Added `eval_neq()`, updated OPERATORS dict
- `src/backtest/rules/registry.py` - Registry uses symbols
- `src/backtest/play/play.py` - Removed op_map converter
- `tests/stress/plays/*.yml` - 6 files updated
- `tests/functional/strategies/plays/*.yml` - 39 files updated
- `docs/specs/PLAY_DSL_COOKBOOK.md` - Documentation updated

---

#### Option A: Standardize on WORDS (`gt`, `lt`, `gte`, `lte`, `eq`)

**Changes Required**:
| Component | Change | Effort |
|-----------|--------|--------|
| `play.py` | Remove `op_map` converter (~10 lines) | Low |
| Engine | None - already native | None |
| Stress test Plays | None - already use words | None |
| Cookbook | Update examples to show words | Medium |
| Other Plays | Audit and update any using symbols | Low |

**Pros**:
- Zero engine changes (lowest risk)
- Stress tests already use words
- Matches internal representation
- Consistent with programming conventions (`gt`, `lt` are common in many languages)
- Single source of truth

**Cons**:
- Less intuitive for non-programmers writing YAML
- `["ema_9", "gt", "ema_21"]` slightly less readable than `["ema_9", ">", "ema_21"]`

**Global Impact**: Minimal - mostly documentation updates

---

#### Option B: Standardize on SYMBOLS (`>`, `<`, `>=`, `<=`, `==`)

**Changes Required**:
| Component | Change | Effort |
|-----------|--------|--------|
| `play.py` | Remove converter (shim eliminated) | Low |
| `constants.py` | Add symbols to VALID_OPERATORS | Low |
| `condition_ops.py` | Handle symbols in dispatch | Medium |
| Stress test Plays | Update all to use symbols | Medium |
| Cookbook | Already shows symbols in examples | Low |
| Other Plays | Update any using words | Medium |

**Pros**:
- More human-readable YAML
- Matches mathematical notation (intuitive)
- Better for strategy authors who aren't programmers
- Cookbook examples already lean toward symbols

**Cons**:
- Requires engine changes (parser + evaluator)
- Need to update existing Play files
- Symbols in YAML strings can look odd (though works fine when quoted)
- Higher risk (touching evaluation code)

**Global Impact**: Medium - engine changes + Play file updates

---

#### Option C: Make BOTH Native (No Conversion, Accept Either)

**Changes Required**:
| Component | Change | Effort |
|-----------|--------|--------|
| `play.py` | Remove converter | Low |
| `constants.py` | Add symbols as aliases | Low |
| `condition_ops.py` | Map symbols to words at eval time | Low |
| Plays | No changes needed | None |
| Cookbook | Document both as valid | Low |

**Pros**:
- Backward compatible with all existing Plays
- User choice (symbols for readability, words for explicitness)
- Lowest migration effort

**Cons**:
- Still two ways to do same thing (inconsistency remains)
- Doesn't fully solve the "single canonical form" goal
- Ambiguity in codebase continues

**Global Impact**: Low effort, but doesn't eliminate the core issue

---

#### Recommendation Matrix

| Factor | Words (A) | Symbols (B) | Both (C) |
|--------|-----------|-------------|----------|
| Engine changes | None | Medium | Low |
| Migration effort | Low | Medium | None |
| Risk | Low | Medium | Low |
| Consistency | High | High | Low |
| Readability | Medium | High | N/A |
| ALL FORWARD compliance | Yes | Yes | Partial |

**Decision Needed**: Human to decide preferred direction before implementation.

---

## Documentation Bugs

### DOC-002: Cookbook shows wrong MACD output names

**Gate**: 2.1 (found during Gate 2.2 preparation)
**Severity**: P3 (documentation only, engine works correctly)
**Status**: RESOLVED
**File**: `docs/specs/PLAY_DSL_COOKBOOK.md`

**Issue**:
- Cookbook Section 2 showed MACD outputs as: `macd, macd_signal, macd_hist`
- Registry canonical output names are: `macd, signal, histogram`

**Resolution** (2026-01-09):
- Updated cookbook Section 2 feature example comment
- Updated Multi-Output table
- Changed `macd_signal` → `signal`, `macd_hist` → `histogram`

---

### DOC-001: Cookbook shows wrong BBands output names

**Gate**: 2.1 (found during Phase 1 verification)
**Severity**: P3 (documentation only, engine works correctly)
**Status**: RESOLVED
**File**: `docs/specs/PLAY_DSL_COOKBOOK.md`

**Issue**:
- Cookbook Section 2 showed BBands outputs as: `bbl (lower), bbm (middle), bbu (upper), bbb, bbp`
- Registry canonical output names are: `lower, middle, upper, bandwidth, percent_b`

**Resolution** (2026-01-09):
- Updated cookbook Section 2 feature example comment
- Updated Multi-Output table
- Now uses registry canonical names: `lower, middle, upper, bandwidth, percent_b`

---

## Bug Details

### Template

```markdown
### BUG-XXX: [Title]

**Gate**: X.Y
**Severity**: P0/P1/P2/P3
**Status**: OPEN/INVESTIGATING/FIXING/RESOLVED
**Symbol**: BTCUSDT/ETHUSDT/SOLUSDT/LTCUSDT

**Symptoms**:
- What happened

**Root Cause**:
- TBD / Identified cause

**Reproduction**:
```bash
python trade_cli.py backtest run --play <ID> ...
```

**Resolution**:
- Fix description (once resolved)

**Files Changed**:
- (list of files modified to fix)
```

---

## Open Bugs

(No open bugs)

---

## Resolved Bugs

### BUG-008: Verbose action format doesn't resolve RHS feature references

**Gate**: 5.2
**Severity**: P1 (blocks all verbose format Plays with feature RHS)
**Status**: RESOLVED (2026-01-09)
**Symbol**: Any
**Category**: Parser

**Symptoms**:
- Backtests fail with `TypeError: '<=' not supported between instances of 'float' and 'str'`
- Verbose format conditions with feature references in RHS don't work
- Shorthand format works fine

**Root Cause**:
- `dsl_parser.py` `parse_rhs()` function treated ALL string values as `ScalarValue`
- The shorthand converter in `play.py` correctly handled this by converting strings to `FeatureRef` dicts
- Verbose format bypassed the shorthand converter, so RHS strings were never resolved

**Reproduction**:
```yaml
actions:
  - id: entry
    cases:
      - when:
          all:
            - lhs: "ema_9"
              op: cross_above
              rhs: "ema_21"    # <- Was kept as literal string "ema_21"
        emit:
          - action: entry_long
```

Result: `TypeError` comparing float EMA value against string "ema_21"

**Resolution**:
- Added `_normalize_rhs_for_operator()` function to `parse_cond()` in `dsl_parser.py`
- Operator-aware heuristic determines string RHS interpretation:
  - **Numeric operators** (`>`, `<`, `>=`, `<=`, `cross_above`, `cross_below`, `near_*`, `between`): String RHS is always a FeatureRef
  - **Discrete operators** (`==`, `!=`): ALL_CAPS strings are enum literals (keep as ScalarValue), otherwise FeatureRef
- Added `_string_to_feature_ref_dict()` helper to convert strings like "ema_21" or "swing.low_level" to proper FeatureRef dicts
- Added `_is_enum_literal()` helper to identify ALL_CAPS enum strings

**Files Changed**:
- `src/backtest/rules/dsl_parser.py`
  - Added `_string_to_feature_ref_dict()` helper
  - Added `_is_enum_literal()` helper
  - Added `_normalize_rhs_for_operator()` function
  - Updated `parse_cond()` to normalize RHS before parsing

**Validation**:
- 21/21 stress tests pass normalization
- 110/110 functional tests pass normalization
- Verbose format works correctly with feature RHS
- Enum literals like "ACTIVE", "BROKEN" still work correctly

---

### BUG-001: Timezone-naive vs timezone-aware datetime comparison error

**Gate**: 1.1
**Severity**: P0 (blocks all backtests with historical data sync)
**Status**: RESOLVED
**Symbol**: BTCUSDT

**Symptoms**:
- Data sync fails with "can't compare offset-naive and offset-aware datetimes"
- Cannot run backtest with --fix-gaps for historical date ranges

**Root Cause**:
- Datetime comparison in historical_sync.py between timezone-aware and timezone-naive objects

**Reproduction**:
```bash
python trade_cli.py backtest run --play S_01_btc_single_ema --start 2024-12-15 --end 2025-01-01 --fix-gaps --dir tests/stress/plays
```

**Resolution**:
- Added `_normalize_to_naive_utc()` helper in historical_sync.py to normalize all datetimes to naive UTC before comparison

**Files Changed**:
- `src/data/historical_sync.py`

---

### BUG-002: 100% sizing with 1x leverage rejects all orders

**Gate**: 1.1
**Severity**: P2 (configuration issue, not engine bug)
**Status**: RESOLVED
**Symbol**: BTCUSDT
**Category**: CONFIG (not engine bug)

**Symptoms**:
- 0 trades generated despite correct signal evaluation
- Orders submitted to exchange but removed without fills
- Debug trace shows: `pending=1->0, fills=0`

**Root Cause**:
- Play configuration impossible with 1x leverage:
  - `max_position_pct: 100%` → position size = $10,000 (full equity)
  - `max_leverage: 1.0` → requires 100% margin = $10,000
  - Fee overhead: ~$5.50 (0.055% taker fee)
  - **Required: $10,005.50, Available: $10,000 → REJECTED**
- Engine correctly rejects due to `INSUFFICIENT_ENTRY_GATE`

**Reproduction**:
```bash
python trade_cli.py backtest run --play S_01_btc_single_ema --start 2024-12-15 --end 2025-01-01 --fix-gaps --dir tests/stress/plays
```

**Resolution**:
- Reduced `max_position_pct` from 100% to 95% to leave room for fees
- **Key Insight**: With 1x leverage, you need margin headroom for fees

**Files Changed**:
- `tests/stress/plays/S_01_btc_single_ema.yml`
  - Changed: `max_position_pct: 100.0` → `max_position_pct: 95.0`

**Lesson Learned**:
- At 1x leverage with fee overhead, max_position_pct must be < 100%
- Rule of thumb: `max_position_pct <= 100% - (fee_bps * 2 / 100)` for round-trip fees

---

### BUG-003: BBands all NaN due to int/float column name mismatch

**Gate**: 1.5
**Severity**: P0 (blocks all BBands backtests)
**Status**: RESOLVED
**Symbol**: BTCUSDT
**Category**: Indicator NaN

**Symptoms**:
- BBands indicator returns all NaN values
- Error: "No valid bars found... All indicator columns have NaN values"
- Affects any Play using BBands with integer std parameter

**Root Cause**:
- YAML parses `std: 2` as integer, not float
- vendor.bbands generates column name "BBL_20_2_2"
- pandas_ta always generates "BBL_20_2.0_2.0" (float format)
- Column name mismatch → empty series returned

**Reproduction**:
```yaml
features:
  bbands_20_2:
    indicator: bbands
    params:
      length: 20
      std: 2  # int, causes mismatch
```

**Resolution**:
- Convert std to float before generating column names: `std_str = f"{float(std)}"`
- Ensures consistent column naming regardless of YAML input type

**Files Changed**:
- `src/backtest/indicator_vendor.py` (line 697)

**Lesson Learned**:
- YAML type coercion can cause subtle mismatches
- pandas_ta column names always use float format for numeric params

---

### BUG-004: ArithmeticExpr not handled in execution_validation.py

**Gate**: 2.4
**Severity**: P1 (blocks all arithmetic DSL expressions)
**Status**: RESOLVED
**Symbol**: BTCUSDT
**Category**: Validation

**Symptoms**:
- Backtest fails with "AttributeError: 'ArithmeticExpr' object has no attribute 'feature_id'"
- Plays with arithmetic expressions like `[["ema_9", "-", "ema_21"], ">", 0]` cannot run
- Error in `extract_rule_feature_refs()` during preflight validation

**Root Cause**:
- `execution_validation.py` assumed `expr.lhs` was always a `FeatureRef`
- For arithmetic expressions, `expr.lhs` is an `ArithmeticExpr` which doesn't have `feature_id` attribute
- Feature ref extraction did not handle nested arithmetic structures

**Reproduction**:
```yaml
actions:
  entry_long:
    all:
      - [["ema_9", "-", "ema_21"], ">", 0]
```

**Resolution**:
- Added `_extract_from_arithmetic()` helper function to recursively extract feature refs from `ArithmeticExpr`
- Updated `_extract_from_expr()` to check if LHS is `FeatureRef` vs `ArithmeticExpr`
- Also handles arithmetic expressions in RHS

**Files Changed**:
- `src/backtest/execution_validation.py`
  - Added import for `ArithmeticExpr`
  - Added `_extract_from_arithmetic()` function
  - Updated `_extract_from_expr()` to handle both `FeatureRef` and `ArithmeticExpr` in LHS/RHS

**Lesson Learned**:
- DSL node types must be handled polymorphically throughout the validation chain
- Arithmetic expressions can appear in both LHS and RHS positions

---

### BUG-005: Window operators not handled inside all:/any: blocks

**Gate**: 3.1
**Severity**: P1 (blocks all window operators inside boolean blocks)
**Status**: RESOLVED
**Symbol**: BTCUSDT
**Category**: Parser

**Symptoms**:
- Backtest fails with "Condition must have at least 3 elements" error
- Window operators like `holds_for` inside `all:` blocks fail to parse
- Error in `_convert_shorthand_condition()` which expects a list

**Root Cause**:
- `_convert_shorthand_conditions()` called `_convert_shorthand_condition()` on each item in `all:`/`any:` blocks
- `_convert_shorthand_condition()` expected a list (3-element condition)
- Window operators are dicts, not lists, causing the error

**Reproduction**:
```yaml
actions:
  entry_long:
    all:
      - holds_for:
          bars: 3
          expr:
            all:
              - ["rsi_14", ">", 50]
      - ["close", ">", "ema_20"]
```

**Resolution**:
- Added `_convert_condition_item()` helper function
- Checks if item is list (call `_convert_shorthand_condition`) or dict (call `_convert_shorthand_conditions`)
- Updated `all:`, `any:`, `not:` handling to use the new helper

**Files Changed**:
- `src/backtest/play/play.py`
  - Added `_convert_condition_item()` function
  - Updated `_convert_shorthand_conditions()` to use it

**Lesson Learned**:
- Condition items in boolean blocks can be either conditions (lists) or nested structures (dicts)
- Parser must handle polymorphic condition items

---

### BUG-006: Duration window operators missing from shorthand converter

**Gate**: 3.3
**Severity**: P1 (blocks all duration-based windows)
**Status**: RESOLVED
**Symbol**: BTCUSDT
**Category**: Parser

**Symptoms**:
- Backtest fails with "Expression must be dict or list, got str" error
- Duration-based window operators fail to parse
- Error in DSL parser when encountering unconverted duration window

**Root Cause**:
- Shorthand converter only handled `holds_for`, `occurred_within`, `count_true`
- Missing handlers for `holds_for_duration`, `occurred_within_duration`, `count_true_duration`
- Duration windows passed through unconverted, causing parser errors downstream

**Reproduction**:
```yaml
actions:
  entry_long:
    all:
      - holds_for_duration:
          duration: "30m"
          expr:
            all:
              - ["rsi_14", ">", 50]
```

**Resolution**:
- Added handlers for all 3 duration-based window operators
- Each converts `expr:` recursively via `_convert_shorthand_conditions()`

**Files Changed**:
- `src/backtest/play/play.py`
  - Added `holds_for_duration` handler
  - Added `occurred_within_duration` handler
  - Added `count_true_duration` handler

**Lesson Learned**:
- When adding new DSL constructs, ensure shorthand conversion handles them
- Duration-based and bar-based windows are parallel constructs requiring parallel support

---

### BUG-007: Structures section not converted to Feature objects

**Gate**: 4.1
**Severity**: P0 (blocks all structure-based Plays)
**Status**: RESOLVED
**Symbol**: BTCUSDT
**Category**: Parser

**Symptoms**:
- Backtests with `structures:` section always produce 0 trades
- No structure initialization messages in logs
- `registry.get_structures()` always returns empty list

**Root Cause**:
- `Play.from_dict()` parsed `structures:` section to extract `structure_keys` for validation
- But structures were NOT converted to `Feature` objects with `FeatureType.STRUCTURE`
- `FeatureRegistry.get_structures()` returned empty because no structure Features existed
- `_build_incremental_state()` skipped structure initialization due to empty list

**Reproduction**:
```yaml
structures:
  exec:
    - type: swing
      key: swing
      params:
        left: 5
        right: 5

actions:
  entry_long:
    all:
      - ["close", ">", "swing.low_level"]
```
Result: 0 trades (structure references evaluated as MISSING)

**Resolution**:
- Added code to `Play.from_dict()` to convert structure specs into `Feature` objects
- Created Feature objects with `type=FeatureType.STRUCTURE`, `structure_type`, `params`, `depends_on`
- Appended structure Features to the features tuple
- Now `registry.get_structures()` returns proper list, incremental state initializes

**Files Changed**:
- `src/backtest/play/play.py`
  - Added structure Feature creation in `from_dict()`
  - Handles both exec and htf structure specs
  - Combines indicator and structure Features

**Lesson Learned**:
- YAML sections that define entities must create corresponding internal objects
- Validation-only parsing (extracting keys) is not sufficient for runtime use
- Structure initialization depends on Feature Registry containing structure Features

---

## Play YAML Adjustments (Non-Bug)

During stress testing, some Play files were adjusted for better test coverage:

| Gate | Play File | Change | Reason |
|------|-----------|--------|--------|
| 1.4 | S_04_btc_basic_and.yml | `rsi_14 < 40` → `rsi_14 < 60` | Original condition too restrictive (0 trades), adjusted for better AND logic validation |
| 1.5 | S_05_btc_multi_output.yml | `field: "bbl"` → `field: "lower"` | Used correct BBands field names from registry |

---

## Bug Categories

Track patterns to identify systemic issues:

| Category | Count | Notes |
|----------|-------|-------|
| Indicator NaN | 1 | Warmup/computation issues |
| Structure | 1 | Structure loading/initialization |
| Forward-Fill | 0 | HTF/MTF alignment |
| Cross Detection | 0 | History offset bugs |
| Window State | 0 | Bar counting issues |
| Arithmetic | 0 | Division/overflow |
| Struct Access | 0 | KeyError/field issues |
| Zone State | 0 | Detection/activation |
| Data Sync | 1 | Timezone/datetime issues |
| Config | 1 | Play configuration issues (not engine bugs) |
| Validation | 1 | Preflight/execution validation bugs |
| Parser | 4 | Shorthand condition conversion issues + verbose RHS resolution (all resolved) |
| Other | 0 | Uncategorized |
