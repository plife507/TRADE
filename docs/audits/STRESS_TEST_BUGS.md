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
| DOC-001 | 2.1 | P3 | OPEN | Cookbook shows wrong BBands output names |
| DOC-002 | 2.1 | P3 | OPEN | Cookbook shows wrong MACD output names |
| DEBT-001 | 2.1 | P2 | OPEN | Symbol-to-word operator conversion is a legacy shim |

---

## Technical Debt

### DEBT-001: Symbol-to-word operator conversion is legacy shim

**Gate**: 2.1 (found during Phase 1 verification)
**Severity**: P2 (architectural inconsistency, violates ALL FORWARD directive)
**Status**: OPEN

**Current State**:
- `play.py` converts symbols (`>`, `<`) to words (`gt`, `lt`) during Play loading
- DSL parser/evaluator only understand words
- Cookbook shows both syntaxes inconsistently
- This is a preprocessing shim that creates two valid syntaxes

**Files Affected**:
- `src/backtest/play/play.py` (lines 141-147) - converter location
- `src/backtest/rules/dsl_nodes/constants.py` - operator definitions
- `src/backtest/rules/evaluation/condition_ops.py` - operator evaluation
- `docs/specs/PLAY_DSL_COOKBOOK.md` - documentation

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
**Status**: OPEN
**File**: `docs/specs/PLAY_DSL_COOKBOOK.md`

**Issue**:
- Cookbook Section 2 shows MACD outputs as: `macd, macd_signal, macd_hist`
- Registry canonical output names are: `macd, signal, histogram`

**Correct Documentation**:
```yaml
# MACD (multi-output)
macd_12_26_9:
  indicator: macd
  params:
    fast: 12
    slow: 26
    signal: 9
  # Outputs: macd, signal, histogram
```

**Resolution**:
- Update cookbook Section 2 to use registry canonical names
- Change `macd_signal` → `signal`, `macd_hist` → `histogram`

---

### DOC-001: Cookbook shows wrong BBands output names

**Gate**: 2.1 (found during Phase 1 verification)
**Severity**: P3 (documentation only, engine works correctly)
**Status**: OPEN
**File**: `docs/specs/PLAY_DSL_COOKBOOK.md`

**Issue**:
- Cookbook Section 2 shows BBands outputs as: `bbl (lower), bbm (middle), bbu (upper), bbb, bbp`
- Registry canonical output names are: `lower, middle, upper, bandwidth, percent_b`
- The parenthetical explanations are correct, but should be the PRIMARY names

**Correct Documentation**:
```yaml
# Bollinger Bands (multi-output)
bbands_20_2:
  indicator: bbands
  params:
    length: 20
    std: 2.0
  # Outputs: lower, middle, upper, bandwidth, percent_b
```

**Resolution**:
- Update cookbook Section 2 to use registry canonical names
- Remove pandas_ta internal column names (`bbl/bbm/bbu/bbb/bbp`)

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

(None currently)

---

## Resolved Bugs

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
| Forward-Fill | 0 | HTF/MTF alignment |
| Cross Detection | 0 | History offset bugs |
| Window State | 0 | Bar counting issues |
| Arithmetic | 0 | Division/overflow |
| Struct Access | 0 | KeyError/field issues |
| Zone State | 0 | Detection/activation |
| Data Sync | 1 | Timezone/datetime issues |
| Config | 1 | Play configuration issues (not engine bugs) |
| Other | 0 | Uncategorized |
