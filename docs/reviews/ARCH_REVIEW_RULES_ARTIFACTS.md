# Architecture Review: Rules, Artifacts & Gates

**Date**: January 2026
**Reviewer**: Claude Code (Architecture Review)
**Scope**: Rules compilation/evaluation, artifact output format, validation gates design, IdeaCard loading/validation

---

## Executive Summary

This review covers four interconnected subsystems that form the configuration-to-execution pipeline:

1. **Rules Module** (`src/backtest/rules/`): Compiles and evaluates signal conditions
2. **Artifacts Module** (`src/backtest/artifacts/`): Manages run output persistence and determinism verification
3. **Gates Module** (`src/backtest/gates/`): Validates configurations before execution
4. **IdeaCard Module** (`src/backtest/idea_card*.py`): Strategy specification and YAML validation

Overall architecture quality is **good** with clear separation of concerns. Key strengths include fail-fast validation, compile-time optimization, and deterministic hashing. Areas needing attention include import inconsistencies, potential circular dependencies, and some dead code.

---

## 1. Rules Module

### 1.1 compile.py

**Purpose**: Compile-time reference resolver for IdeaCard conditions. Parses and validates paths at normalization time to eliminate string parsing overhead in the hot loop.

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `validate_ref_path()` | Validates dot-separated paths (price.*, indicator.*, structure.*) |
| `compile_ref()` | Creates CompiledRef from path string or literal value |
| `compile_condition()` | Compiles a full condition dict with lhs_ref/rhs_ref |
| `_validate_price_path()` | Validates price.mark.close style paths |
| `_validate_indicator_path()` | Validates indicator.key.tf_role paths |
| `_validate_structure_path()` | Validates structure.block_key.field paths (Stage 5+ zones) |

**Key Types**:
- `RefNamespace` (Enum): PRICE, INDICATOR, STRUCTURE, LITERAL
- `CompiledRef` (dataclass, frozen): Pre-compiled reference for O(1) resolution
- `CompileError` (Exception): Actionable error with allowed values list

**Dependencies**:
- `.types` (RefValue, ReasonCode, ValueType)
- `src.backtest.market_structure.types` (lazy import for SWING/TREND outputs)

**Issues Found**:
1. **Lazy import pattern**: `_get_structure_fields()` uses global mutable state (`STRUCTURE_FIELDS`), which could cause issues if called from multiple threads
2. **Path hardcoding**: PRICE_FIELDS only supports `mark.{close,high,low}`, no `last.*` (commented out)
3. **Zone validation deferred**: Zone key/field validation happens at runtime, not compile time (line 296-298)

**Structural Concerns**:
- Well-designed fail-fast approach
- Clear separation between compile-time validation and runtime resolution
- Good error messages with allowed values suggestions

---

### 1.2 eval.py

**Purpose**: Operator implementations for rule evaluation with strict type contracts.

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `eval_gt/lt/ge/le()` | Numeric comparison operators |
| `eval_eq()` | Equality for bool/int/enum (NOT float) |
| `eval_approx_eq()` | Float comparison with tolerance |
| `evaluate_condition()` | Main entry point for compiled conditions |
| `evaluate_condition_dict()` | Entry point for IdeaCard signal evaluation |
| `_check_numeric()` | Type validation helper |

**Type Contracts**:
- `gt, lt, ge, le`: NUMERIC only (int or float)
- `eq`: BOOL, INT, or ENUM only (NO float - must use approx_eq)
- `approx_eq`: FLOAT only, requires tolerance parameter

**Dependencies**:
- `.types` (EvalResult, ReasonCode, RefValue, ValueType)
- `.compile` (CompiledRef)

**Issues Found**:
1. **Dead code comment**: Line 22-23 states "Operator enum REMOVED (was dead code)" but the `__init__.py` still exports `Operator` - this will cause ImportError
2. **Alias duplication**: `OPERATORS` dict has both "ge"/"gte" and "le"/"lte" pointing to same functions - correct but could use constant
3. **Math import**: `import math` at top level but only used for NaN check in types.py, not here

**Structural Concerns**:
- Clean functional design with pure operator functions
- Every evaluation returns `EvalResult` with `ReasonCode` - good for debugging
- Proper rejection of float equality with actionable error message

---

### 1.3 types.py

**Purpose**: Rule evaluation type definitions - enums and dataclasses for condition evaluation.

**Key Types**:
| Type | Purpose |
|------|---------|
| `ReasonCode` (IntEnum) | Machine-readable outcome codes (R_OK, R_MISSING_LHS, R_TYPE_MISMATCH, etc.) |
| `ValueType` (IntEnum) | Value type classification (NUMERIC, INT, FLOAT, BOOL, ENUM, STRING, MISSING) |
| `RefValue` (dataclass, frozen) | Resolved reference value with type info |
| `EvalResult` (dataclass, frozen) | Condition evaluation result with debug info |

**Key Methods**:
- `ValueType.from_value()`: Classifies Python value to ValueType
- `RefValue.from_resolved()`: Factory for creating RefValue from resolved value
- `EvalResult.success/failure()`: Factory methods for results
- `EvalResult.to_dict()`: Serialization for logging

**Dependencies**:
- None (leaf module)

**Issues Found**:
1. **Math import inside method**: `ValueType.from_value()` imports math inside the method (line 84) - should be at module level
2. **NUMERIC redundant**: ValueType has both NUMERIC and separate INT/FLOAT - overlap is unclear. `is_numeric` property checks all three.

**Structural Concerns**:
- Excellent immutable design with frozen dataclasses
- Clear separation between value types for operator validation
- Good factory methods with meaningful defaults

---

### 1.4 registry.py

**Purpose**: Single source of truth for operator semantics. Defines which operators are supported and their requirements.

**Key Types**:
| Type | Purpose |
|------|---------|
| `OpCategory` (Enum) | Input type categories (NUMERIC, BOOL_INT_ENUM, FLOAT_ONLY) |
| `OperatorSpec` (dataclass, frozen) | Specification for a single operator |

**Registry Contents**:
```python
OPERATOR_REGISTRY = {
    "gt", "lt", "ge", "le", "gte", "lte"  # Supported, NUMERIC
    "eq"                                    # Supported, BOOL_INT_ENUM
    "approx_eq"                             # Supported, FLOAT_ONLY, needs_tolerance
    "cross_above", "cross_below"            # BANNED - Stage 4c
}
```

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `get_operator_spec()` | Get spec from registry (case-insensitive) |
| `is_operator_supported()` | Check if operator is implemented |
| `validate_operator()` | Compile-time validation with error message |
| `get_canonical_operator()` | Resolve aliases (gte->ge, lte->le) |

**Dependencies**:
- None (leaf module)

**Issues Found**:
1. **Cross operators banned**: `cross_above/cross_below` are explicitly banned in Stage 4c with actionable error messages suggesting derived indicators
2. **Unused field**: `needs_prev_value` in OperatorSpec is defined but never checked in validation

**Structural Concerns**:
- Excellent single source of truth design
- Good actionable error messages for unsupported operators
- Proper alias handling

---

### 1.5 `__init__.py` - CRITICAL BUG (VERIFIED)

**Issues Found**:
1. **CRITICAL: Dead import**: Line 28 imports `Operator` from `.eval` but eval.py explicitly removed the Operator enum. The comment on lines 22-23 of eval.py states:

```python
# NOTE: Operator enum REMOVED (was dead code - never referenced).
# All operator handling uses OPERATOR_REGISTRY in registry.py as single source of truth.
```

Yet `__init__.py` still contains:
```python
# __init__.py line 28 - WILL FAIL
from .eval import (
    evaluate_condition,
    Operator,  # <-- DOES NOT EXIST - will raise ImportError
    OPERATORS,
)
```

And also exports it in `__all__`:
```python
__all__ = [
    ...
    "Operator",  # <-- Should not exist
    ...
]
```

**Severity**: This will cause ImportError when any code imports from `src.backtest.rules`.

**Fix Required**: Remove `Operator` from both the import statement and `__all__` list in `__init__.py`.

---

## 2. Artifacts Module

### 2.1 artifact_standards.py

**Purpose**: Defines canonical folder/file naming conventions for backtest artifacts.

**Key Features**:
- Hash-based deterministic folder structure
- Two categories: `_validation` (overwrite OK) and `strategies` (append-only)
- Version-controlled manifest schema (currently 1.0.0)
- Required files validation (result.json, trades.parquet, equity.parquet, pipeline_signature.json)

**Key Types**:
| Type | Purpose |
|------|---------|
| `VersionMismatchError` | Exception for incompatible schema versions |
| `ArtifactPathConfig` | Configuration for building artifact paths |
| `RunManifest` | Mandatory manifest for every backtest run |
| `ManifestVerificationResult` | Result of manifest verification |
| `ArtifactValidationResult` | Result of artifact validation |
| `ResultsSummary` | Summary of backtest results with 50+ metrics |

**Folder Structure**:
```
backtests/
└── {category}/                    # _validation or strategies
    └── {idea_card_id}/
        └── {universe_id}/         # Symbol or uni_<hash>
            └── {8-char-input-hash}/
                ├── run_manifest.json
                ├── result.json
                ├── trades.parquet
                ├── equity.parquet
                └── pipeline_signature.json
```

**Dependencies**:
- `.hashes` (compute_input_hash, compute_universe_id)
- `.pipeline_signature` (PipelineSignature)
- `pandas`, `pyarrow.parquet` (for validation)

**Issues Found**:
1. **Large file**: 1265 lines - could be split into separate files (manifest.py, validation.py, summary.py)
2. **Circular import risk**: `ArtifactPathConfig.__post_init__` imports from `.hashes`
3. **Legacy field rename**: `computed_warmup_by_role` renamed to `computed_lookback_bars_by_role` - breaking change documented in comments

**Structural Concerns**:
- Comprehensive validation of artifact completeness
- Good versioning strategy with major version compatibility check
- Clear category semantics (_validation vs strategies)
- Well-documented hash verification rules

---

### 2.2 equity_writer.py

**Purpose**: Writes equity curve CSV files (convenience export alongside lossless events.jsonl).

**Key Methods**:
| Method | Purpose |
|--------|---------|
| `add_point()` | Add single equity curve point |
| `add_points()` | Add multiple points from list |
| `write()` | Write accumulated data to CSV |

**Dependencies**:
- `csv` (standard library)
- `pathlib` (standard library)

**Issues Found**:
1. **CSV format**: Still writes CSV while artifact_standards expects parquet - potential mismatch
2. **No ts_ms column**: Does not include required `ts_ms` column per REQUIRED_EQUITY_COLUMNS

**Structural Concerns**:
- Simple, focused design
- Properly handles datetime serialization
- Clear separation from lossless events.jsonl

---

### 2.3 parquet_writer.py

**Purpose**: Provides consistent Parquet writing with pyarrow engine.

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `write_parquet()` | Write DataFrame to Parquet with standard settings |
| `read_parquet()` | Read Parquet file to DataFrame |
| `compare_csv_parquet()` | Compare CSV and Parquet for migration parity |

**Design Choices**:
- pyarrow engine for broad compatibility
- snappy compression (fast, reasonable ratio)
- Parquet version 2.6 for compatibility
- No index written (matches CSV behavior)

**Dependencies**:
- `pandas`
- `pyarrow`, `pyarrow.parquet`

**Issues Found**:
- None significant. Clean, focused implementation.

**Structural Concerns**:
- Good abstraction for consistent Parquet handling
- Useful parity comparison function for migration validation

---

### 2.4 hashes.py

**Purpose**: Deterministic hashing utilities for backtest artifacts.

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `compute_trades_hash()` | Hash of trades list (16-char SHA256 prefix) |
| `compute_equity_hash()` | Hash of equity curve (16-char SHA256 prefix) |
| `compute_run_hash()` | Combined hash of trades + equity + idea_card |
| `compute_universe_id()` | Symbol set identifier (single symbol or uni_<hash>) |
| `compute_input_hash()` | Short hash for folder naming (8 or 12 chars) |
| `compute_artifact_file_hash()` | Full SHA256 of file contents |

**Canonicalization Rules** (documented in file):
1. JSON keys: sorted alphabetically
2. Lists: sorted and deduplicated
3. Timestamps: ISO8601 format
4. Symbol casing: UPPERCASE
5. Timeframes: normalized to {value}{unit} format

**Key Types**:
- `InputHashComponents` (dataclass): All factors affecting backtest results

**Dependencies**:
- `hashlib`, `json` (standard library)
- `..types` (Trade, EquityPoint)

**Issues Found**:
1. **_canonicalize_tf fallback**: Returns input as-is for unknown formats (line 209) - should raise ValueError in strict mode
2. **Hash truncation**: 16-char hashes may have collision risk for large archives

**Structural Concerns**:
- Excellent canonicalization documentation
- Clear rules for deterministic hashing
- Good separation between short hash (folder) and full hash (verification)

---

### 2.5 determinism.py

**Purpose**: Determinism verification for backtest runs.

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `compare_runs()` | Compare two existing runs for hash equality |
| `verify_determinism_rerun()` | Re-run and compare outputs |

**Key Types**:
- `HashComparison`: Result of comparing single hash field
- `DeterminismResult`: Full verification result with report

**Dependencies**:
- `.artifact_standards` (STANDARD_FILES, ResultsSummary)
- `src.tools.backtest_cli_wrapper` (lazy import for re-run)

**Issues Found**:
1. **Circular import risk**: Imports from `src.tools` in verify_determinism_rerun (line 232)
2. **File key mismatch**: Uses `STANDARD_FILES["manifest"]` but file is named "run_manifest.json" - will KeyError

**Structural Concerns**:
- Good verification workflow design
- Clear reporting with print_report()
- Proper separation of compare vs re-run modes

---

### 2.6 manifest_writer.py

**Purpose**: Writes run_manifest.json with run metadata (legacy writer).

**Key Methods**:
| Method | Purpose |
|--------|---------|
| `set_run_info()` | Set basic run information |
| `set_data_window()` | Set data window timestamps |
| `set_config()` | Set config and compute hash |
| `set_health_report()` | Set DataHealthCheck summary |
| `write()` | Write manifest to file |

**Dependencies**:
- `subprocess` (for git commit)
- `json`, `hashlib` (standard library)

**Issues Found**:
1. **Duplicate functionality**: This writer vs `RunManifest.write_json()` in artifact_standards.py - redundant
2. **No schema version**: Unlike RunManifest in artifact_standards.py, this doesn't include schema_version

**Structural Concerns**:
- Simpler API than RunManifest dataclass
- Missing version tracking - should be deprecated in favor of RunManifest

---

### 2.7 pipeline_signature.py

**Purpose**: Production verification artifact proving real pipeline execution (not stubs).

**Key Types**:
- `PipelineSignature` (dataclass): Records exact implementations used

**Validation Requirements**:
- config_source must be "IdeaCard"
- uses_system_config_loader must be False
- placeholder_mode must be False
- strict_indicator_access must be True
- feature_keys_match must be True (declared == computed)

**Dependencies**:
- None (leaf module)

**Issues Found**:
- None significant. Clean Gate D.1 implementation.

**Structural Concerns**:
- Excellent provenance tracking
- Clear validation rules for production verification
- Good for detecting stub/placeholder usage

---

### 2.8 eventlog_writer.py

**Purpose**: Append-only JSONL event log during simulation.

**Event Types**:
- `step`: Bar open/close, mark price, OHLCV
- `fill`: Order fills
- `funding`: Funding rate events
- `liquidation`: Liquidation events
- `entries_disabled`: Entry blocked events
- `htf_refresh`/`mtf_refresh`: Cache refresh events
- `snapshot_context`: Per-TF snapshot state (Phase 4)
- `trade_entry`/`trade_exit`: Trade lifecycle (Phase 4)

**Key Features**:
- Context manager support (`with EventLogWriter(...):`)
- Auto-incrementing event_id
- Immediate flush after each event

**Dependencies**:
- `json` (standard library)

**Issues Found**:
- None significant. Clean streaming design.

**Structural Concerns**:
- Good lossless event capture
- Proper resource management with context manager
- Useful for debugging and replay

---

### 2.9 snapshot_artifacts.py

**Purpose**: Emit lossless snapshots of computed indicators for audit.

**Key Types**:
- `SnapshotFrameInfo`: Metadata about a snapshot frame (role-keyed)
- `SnapshotManifest`: Manifest for snapshot artifact set

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `emit_snapshot_artifacts()` | Write snapshot frames and manifest |
| `load_snapshot_artifacts()` | Load snapshots from run directory |

**Dependencies**:
- `pandas`
- `.indicator_registry` (get_registry)
- `.runtime.types` (FeatureSnapshot)

**Issues Found**:
1. **Circular import**: Imports from `.indicator_registry` may cause issues
2. **Missing import**: `FeatureSnapshot` import from `.runtime.types` - verify exists

**Structural Concerns**:
- Good contract tracking (outputs_expected_by_registry vs outputs_written)
- Role-keyed naming (exec/htf/mtf) vs TF-keyed (legacy)
- Useful for pandas_ta parity audits

---

## 3. Gates Module

### 3.1 production_first_import_gate.py

**Purpose**: AST-based scanner enforcing "no business logic in tests" rule (Gate A).

**Violation Types**:
| Type | Description |
|------|-------------|
| FUNC_NAME | Disallowed function names (build_, compute_, refresh_, etc.) |
| DATAFRAME_MATH | DataFrame indicator patterns (.rolling, .ewm, etc.) |
| TEST_IMPORT | Tests importing from other tests |
| ORCHESTRATION | Test-defined pipeline logic |

**Allowlists**:
- `tests/_fixtures/**` - Synthetic data generation
- `tests/helpers/**` - Assert helpers

**Dependencies**:
- `ast` (standard library)

**Issues Found**:
1. **No tests directory**: Project appears to have CLI-only validation (per CLAUDE.md) - this gate may be vestigial

**Structural Concerns**:
- Clean AST visitor pattern
- Good suggested targets for violations
- Proper CLI interface with --fail-on-violations

---

### 3.2 indicator_requirements_gate.py

**Purpose**: Validates required indicator keys are available before signal evaluation.

**Gate Timing**: After FeatureFrameBuilder, before signal_rules evaluation

**Key Types**:
- `IndicatorGateStatus` (Enum): PASSED, FAILED, SKIPPED
- `RoleValidationResult`: Per-TF role validation result
- `IndicatorRequirementsResult`: Overall gate result

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `validate_indicator_requirements()` | Main validation entry point |
| `extract_available_keys_from_dataframe()` | Get indicator columns from DataFrame |
| `extract_available_keys_from_feature_frames()` | Get keys from all frames |

**Dependencies**:
- `..idea_card` (IdeaCard)
- `pandas` (type hint only)

**Issues Found**:
- None significant. Clean gate implementation.

**Structural Concerns**:
- Good fail-loud design with actionable error messages
- Proper separation from feature computation
- Clear per-role validation

---

### 3.3 idea_card_generator.py

**Purpose**: Creates randomized valid IdeaCards for batch verification (Gate D.2).

**Indicator Allowlist**:
- EMA, SMA (length 5-50)
- RSI, ATR (length 7-21)
- MACD, BBands, Stoch, ADX (multi-output)

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `get_available_symbols()` | Query DuckDB for USDT pairs |
| `generate_random_indicator()` | Create random indicator spec |
| `generate_signal_rules()` | Create entry/exit rules |
| `generate_idea_card_yaml()` | Build full YAML with validation |
| `generate_idea_cards()` | Main generation entry point |

**Dependencies**:
- `..indicator_registry` (get_registry)
- `..idea_card_yaml_builder` (normalize_idea_card_yaml)
- `numpy` (random generation)
- `src.data.historical_data_store` (symbol discovery)

**Issues Found**:
1. **Hardcoded known_good symbols**: Falls back to ["BTCUSDT", "SOLUSDT"] if DB unavailable
2. **1h-only execution**: TIMEFRAMES_EXEC only has "1h" for "verified data coverage"

**Structural Concerns**:
- Good deterministic seed support
- Proper normalization validation before writing
- Clean numpy type conversion

---

### 3.4 batch_verification.py

**Purpose**: Runs multiple IdeaCards and produces batch_summary.json (Gate D.2).

**Key Types**:
- `CardRunResult`: Result for single IdeaCard run
- `BatchSummary`: Summary of batch verification

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `run_batch_verification()` | Main batch runner |

**Dependencies**:
- `.idea_card_generator` (generate_idea_cards)
- `..runner` (run_backtest_with_gates)
- `..idea_card` (load_idea_card)
- `...data.historical_data_store` (get_historical_store)

**Issues Found**:
1. **Runner import**: Imports `..runner` which may not exist - need to verify
2. **Hardcoded window**: Uses explicit dates or computed from now()

**Structural Concerns**:
- Good progress reporting during batch
- Proper cleanup support
- Clear success/failure tracking

---

## 4. IdeaCard Module

### 4.1 idea_card.py

**Purpose**: Declarative strategy specification - the complete self-contained config.

**Key Types** (20+ types defined):

| Category | Types |
|----------|-------|
| Fee/Account | `FeeModel`, `AccountConfig` |
| Position | `PositionMode`, `PositionPolicy` |
| Risk | `StopLossType`, `TakeProfitType`, `SizingModel`, `StopLossRule`, `TakeProfitRule`, `SizingRule`, `RiskModel` |
| Signals | `RuleOperator`, `Condition`, `EntryRule`, `ExitRule`, `SignalRules` |
| Structure | `MarketStructureConfig`, `TFConfig` |
| Core | `IdeaCard` |

**BANNED_OPERATORS**: `{"cross_above", "cross_below"}` - fail at parse time

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `load_idea_card()` | Load from YAML file (searches multiple directories) |
| `list_idea_cards()` | List available IdeaCards |

**Dependencies**:
- `.features.feature_spec` (FeatureSpec, FeatureSpecSet)
- `.market_structure.spec` (StructureSpec, TYPE_CHECKING import)
- `yaml`

**Issues Found**:
1. **Large file**: 1165 lines - could split into submodules (position.py, risk.py, signals.py)
2. **Condition refs**: `lhs_ref` and `rhs_ref` typed as `Any` to avoid circular import
3. **Mutable default**: `tf_configs` uses `field(default_factory=dict)` which is correct, but could be frozen Dict

**Structural Concerns**:
- Excellent fail-fast validation in __post_init__
- Comprehensive from_dict/to_dict serialization
- Good separation of concerns within the file
- Clear documentation of constraints (single position, no scale-in)

---

### 4.2 idea_card_yaml_builder.py

**Purpose**: Build-time validation and normalization for IdeaCard YAML files.

**Validation Error Codes**:
| Code | Description |
|------|-------------|
| UNSUPPORTED_INDICATOR | Indicator type not in registry |
| INVALID_PARAM | Invalid parameter for indicator |
| MULTI_OUTPUT_BASE_KEY_REFERENCED | Used base key instead of expanded key |
| UNDECLARED_FEATURE | Referenced feature not declared |
| UNSUPPORTED_STRUCTURE_TYPE | Unknown structure type |
| INVALID_STRUCTURE_PARAM | Missing required param |
| STRUCTURE_EXEC_ONLY | Stage 3 only supports exec TF |
| DUPLICATE_STRUCTURE_KEY | Duplicate block key |
| INVALID_ENUM_TOKEN | Invalid enum value |

**Key Functions**:
| Function | Purpose |
|----------|---------|
| `validate_idea_card_yaml()` | Main validation entry point |
| `normalize_idea_card_yaml()` | Normalize and validate |
| `generate_required_indicators()` | Auto-generate from feature_specs |
| `compile_condition()` | Stage 4c condition compilation |
| `compile_signal_rules()` | Compile all conditions in rules |
| `compile_idea_card()` | Full IdeaCard compilation |

**Dependencies**:
- `.indicator_registry` (get_registry)
- `.rules.compile` (compile_ref)
- `.rules.registry` (validate_operator)
- `src.backtest.market_structure.types` (TrendState, ZoneState)
- `src.backtest.market_structure.detectors` (ZONE_PUBLIC_FIELDS)

**Issues Found**:
1. **Large file**: 1200 lines - Stage 4c compilation added significant complexity
2. **Circular import**: Imports `Condition as ConditionClass` from `.idea_card` at function level (line 1093)
3. **Enum normalization in-place**: Modifies condition dict in-place during validation (line 721)

**Structural Concerns**:
- Excellent multi-stage validation (scopes, refs, structure, risk)
- Good ScopeMappings pattern for tracking declared keys
- Comprehensive enum token normalization
- Clear separation of validation and compilation

---

## 5. Cross-Cutting Issues

### 5.1 Import Inconsistencies

| Location | Issue |
|----------|-------|
| `rules/__init__.py` | Exports `Operator` but it doesn't exist in eval.py |
| `determinism.py` | Uses `STANDARD_FILES["manifest"]` but key is "run_manifest" |
| Multiple files | Lazy imports to avoid circular dependencies |

### 5.2 Potential Circular Dependencies

```
idea_card.py <--> idea_card_yaml_builder.py <--> rules/compile.py
                         |
                         v
              market_structure/types.py
```

### 5.3 Code Duplication

| Area | Files | Issue |
|------|-------|-------|
| Manifest writing | manifest_writer.py, artifact_standards.py | Two different manifest writers |
| Hash computation | hashes.py, manifest_writer.py | compute_config_hash exists in both |

### 5.4 Large Files Needing Split

| File | Lines | Suggested Split |
|------|-------|-----------------|
| artifact_standards.py | 1265 | manifest.py, validation.py, summary.py |
| idea_card.py | 1165 | position.py, risk.py, signals.py, core.py |
| idea_card_yaml_builder.py | 1200 | validation.py, compilation.py |

---

## 6. Recommendations

### 6.1 Critical (Must Fix)

1. **Fix rules/__init__.py**: Remove `Operator` import that references deleted code
2. **Fix determinism.py**: Change `STANDARD_FILES["manifest"]` to `STANDARD_FILES["run_manifest"]`

### 6.2 High Priority

1. **Deprecate manifest_writer.py**: Use RunManifest from artifact_standards.py only
2. **Add schema version to legacy manifest**: For backward compatibility checking
3. **Complete zone validation**: Move zone key/field validation to compile time

### 6.3 Medium Priority

1. **Split large files**: Improve maintainability
2. **Consolidate hash functions**: Single source of truth for hashing
3. **Add type stubs**: Replace `Any` types in Condition with proper forward refs

### 6.4 Low Priority

1. **Thread safety**: Fix `_get_structure_fields()` global mutable state
2. **Strict timeframe parsing**: Raise ValueError for unknown formats
3. **Review Gate A relevance**: Ensure production_first_import_gate is still needed

---

## 7. Summary

### Strengths

1. **Fail-fast design**: Validation at compile/load time catches errors early
2. **Deterministic hashing**: Well-documented canonicalization rules
3. **Rich type system**: Comprehensive dataclasses with validation
4. **Actionable errors**: Error messages include suggestions and allowed values
5. **Clear separation**: Rules compilation vs evaluation, validation vs execution

### Weaknesses

1. **Import inconsistencies**: Dead exports, mismatched keys
2. **Large files**: Several 1000+ line files need splitting
3. **Code duplication**: Multiple manifest writers, hash functions
4. **Deferred validation**: Some structure validation happens at runtime

### Overall Assessment

The architecture is **solid** with good design principles. The main concerns are maintenance issues (dead code, large files) rather than fundamental design flaws. The compile-time optimization approach for rules evaluation is well-executed and the artifact system provides strong determinism guarantees.
