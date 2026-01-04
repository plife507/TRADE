# Architecture Review: Features, Indicators & Market Structure

**Date**: 2026-01-02
**Reviewer**: Senior Developer Analysis
**Scope**: Feature specification, indicator computation, and market structure detection subsystems

---

## Executive Summary

The codebase demonstrates a well-structured approach to indicator computation and market structure detection with clear separation of concerns. The design follows several strong architectural patterns: registry-based validation, immutable specifications, and vectorized computation. However, there are some structural concerns around code duplication, tightly coupled dependencies, and potential maintainability issues that warrant attention.

---

## 1. Features Module (`src/backtest/features/`)

### 1.1 feature_spec.py

**Purpose**: Declarative specification for indicators that strategies require. Defines what to compute, not how.

**Key Classes/Functions**:
- `FeatureSpec` (frozen dataclass): Immutable indicator specification
- `FeatureSpecSet`: Collection of specs with dependency ordering
- `InputSource` (Enum): Data source selector (OHLCV, computed sources, indicator chaining)
- Factory functions: `ema_spec()`, `sma_spec()`, `rsi_spec()`, etc.

**Dependencies**:
- `indicator_registry.get_registry()` (circular import via deferred import)

**Strengths**:
1. Immutable specs (frozen dataclass) prevent accidental mutation
2. Strong validation in `__post_init__` - fails fast on invalid indicator types
3. Multi-output expansion handled cleanly with `output_keys_list` property
4. Dependency validation ensures chained indicators are ordered correctly
5. Clear separation between declaration (FeatureSpec) and computation (FeatureFrameBuilder)

**Issues Found**:
1. **Circular import pattern**: Uses deferred import `from ..indicator_registry import get_registry` inside methods. While necessary, this creates implicit coupling.
2. **Magic strings**: `input_source == InputSource.INDICATOR` checks are scattered; could use a helper method.
3. **Default parameter handling**: `spec.length` property returns 0 if "length" not in params, which could mask missing required params for some indicators.

**Structural Concerns**:
- Factory functions at module level add 150+ lines of boilerplate. Consider moving to a separate `factories.py` file.
- `FeatureSpecSet._validate_dependencies()` iterates all specs for each addition; O(n^2) for large sets (unlikely to be a real issue but worth noting).

---

### 1.2 feature_frame_builder.py

**Purpose**: Vectorized indicator computation. Transforms FeatureSpecSet into numpy arrays with metadata.

**Key Classes/Functions**:
- `FeatureArrays`: Container for computed indicator arrays with metadata
- `FeatureFrameBuilder`: Main computation orchestrator
- `IndicatorRegistry` (in this file): Wrapper for compute dispatch
- `build_features_from_idea_card()`: High-level API for IdeaCard integration
- `IdeaCardFeatures`: Container for multi-TF feature arrays

**Dependencies**:
- `indicator_vendor.compute_indicator()` - actual computation
- `indicator_registry.get_registry()` - validation and metadata
- `runtime.indicator_metadata` - provenance tracking

**Strengths**:
1. Excellent metadata capture at computation time (feature_spec_id, provenance)
2. Clean separation: builder orchestrates, vendor computes, registry validates
3. Memory-efficient: float32 arrays, C-contiguous for cache efficiency
4. Robust error handling with meaningful messages

**Issues Found**:
1. **Duplicate IndicatorRegistry class**: There are TWO `IndicatorRegistry` classes - one in `indicator_registry.py` and one in `feature_frame_builder.py`. The builder's version is a thin wrapper that delegates to the main registry, but this creates confusion about the canonical source.
2. **Duplicate function definition**: `build_features_from_idea_card()` is defined TWICE in the same file (lines 782-831 and 879-951). The second definition shadows the first. This is a BUG - the first version takes `dfs: Dict[str, pd.DataFrame]`, the second takes a `data_loader` callable.
3. **Import-time side effects**: `_default_registry = IndicatorRegistry()` creates a global instance at import time.

**Structural Concerns**:
- The file is 951 lines and handles too many concerns: FeatureArrays, IndicatorRegistry wrapper, FeatureFrameBuilder, IdeaCard integration. Should be split.
- `_compute_single_output()` and `_compute_multi_output()` share nearly identical logic; could be unified.

---

## 2. Indicators Module

### 2.1 indicator_registry.py

**Purpose**: Single source of truth for supported indicators, their params, outputs, and warmup formulas.

**Key Components**:
- `SUPPORTED_INDICATORS`: Dict defining 42 registered indicators
- `IndicatorInfo` (frozen dataclass): Metadata structure
- `IndicatorRegistry`: Singleton registry implementation
- Warmup formula functions: `_warmup_ema()`, `_warmup_macd()`, etc.

**Dependencies**:
- None (leaf module)

**Strengths**:
1. **Single source of truth**: All indicator metadata centralized
2. **Fail-loud design**: `is_supported()` check prevents unsupported indicators from slipping through
3. **Comprehensive warmup formulas**: Each indicator has a proper warmup calculation
4. **Mutually exclusive output groups**: Properly handles SuperTrend/PSAR long/short exclusivity
5. **Explicit params**: Each indicator declares exactly which params it accepts

**Issues Found**:
1. **Singleton via `__new__`**: The singleton pattern using `__new__` with `_initialized` flag is fragile. If `__init__` raises after `__new__`, subsequent calls will return a broken instance.
2. **Missing validation for param values**: Registry validates param names but not values (e.g., length > 0).
3. **`@lru_cache(maxsize=1)` on `get_registry()`**: Caches the singleton but the singleton pattern already ensures single instance - redundant.

**Structural Concerns**:
- 996 lines in a single file. The warmup functions (lines 53-185) could be a separate module.
- `COMMON_PARAMS` adds params to every indicator but some (like `talib`, `mamode`) may not apply to all.

---

### 2.2 indicator_vendor.py

**Purpose**: Abstraction layer for pandas_ta. Only module that imports pandas_ta directly.

**Key Functions**:
- `compute_indicator()`: Dynamic wrapper for all supported indicators
- `canonicalize_indicator_outputs()`: Normalizes pandas_ta column names
- `_normalize_multi_output()`: Converts DataFrame columns to canonical names
- Explicit wrappers: `ema()`, `sma()`, `rsi()`, `atr()`, `macd()`, `bbands()`, etc.

**Dependencies**:
- `pandas_ta` (external)
- `indicator_registry.get_registry()` - for validation and metadata

**Strengths**:
1. **Clean abstraction**: pandas_ta is fully encapsulated
2. **Structured canonicalization**: `CanonicalizeResult` provides full audit trail
3. **Fail-loud on contract violations**: CANONICAL_COLLISION and MISSING_DECLARED_OUTPUTS are hard errors
4. **Comprehensive column mapping**: `_extract_column_key()` handles all pandas_ta naming quirks

**Issues Found**:
1. **Inconsistent input parameter handling**: `compute_indicator()` builds positional args based on registry inputs, but the order assumed (high, low, close, open, volume) may not match all pandas_ta functions.
2. **Dead code comment (line 715-721)**: Comments reference deleted warmup functions but no actual dead code exists.
3. **Column mapping fragility**: `_extract_column_key()` uses hardcoded prefix mappings. If pandas_ta changes column naming, this breaks silently.

**Structural Concerns**:
- Explicit wrapper functions (`ema()`, `sma()`, etc.) are largely redundant with `compute_indicator()`. They add maintenance burden.
- The `column_mappings` dict (lines 331-409) is extensive but not easily testable for drift.

---

### 2.3 indicators.py

**Purpose**: High-level indicator application for backtest DataFrames.

**Key Functions**:
- `apply_feature_spec_indicators()`: Applies FeatureSpecs to DataFrame
- `get_warmup_from_specs()`: Computes max warmup across specs
- `find_first_valid_bar()`: Finds first bar where all indicators valid
- `get_required_indicator_columns_from_specs()`: Extracts column names

**Dependencies**:
- `indicator_vendor` - computation
- `indicator_registry.get_registry()` - metadata

**Strengths**:
1. **Fail-loud on missing input_source**: Explicit validation
2. **Handles mutually exclusive outputs**: Uses registry for group detection
3. **Clear warmup aggregation**: Simple max() across specs

**Issues Found**:
1. **Duplicate computation logic**: `apply_feature_spec_indicators()` duplicates logic from `FeatureFrameBuilder`. There are now TWO paths to compute indicators: through the builder (returns arrays) and through this function (modifies DataFrame in place).
2. **Inconsistent error handling**: Some indicator types have explicit branches, others fall through to generic `compute_indicator()` call with try/except.
3. **DataFrame mutation**: Function returns a copy but also modifies `df` in place before returning (e.g., adding hlc3/ohlc4 columns).

**Structural Concerns**:
- This file seems to be a legacy path that should be deprecated in favor of `FeatureFrameBuilder`.
- The dual computation paths create maintenance burden and potential for drift.

---

## 3. Market Structure Module (`src/backtest/market_structure/`)

### 3.1 builder.py

**Purpose**: Orchestrates market structure computation from specs.

**Key Classes**:
- `StructureBuilder`: Main orchestrator
- `StructureStore`: Container for structure outputs
- `ZoneStore`: Container for zone outputs
- `StructureManifestEntry`: Audit/debug manifest entry
- `Stage2ValidationError`: Custom exception for constraint violations

**Dependencies**:
- `spec.StructureSpec`, `spec.ZoneSpec`
- `types.*` - enums and output schemas
- `registry.get_detector`, `validate_structure_params`
- `zone_interaction.ZoneInteractionComputer`
- `detectors.ZoneDetector`

**Strengths**:
1. **Clear stage constraints**: Stage 2 validation is explicit and documented
2. **Dependency resolution**: SWING before TREND ordering is automatic
3. **Good separation**: Builder orchestrates, detectors compute
4. **Manifest generation**: Full audit trail for debugging
5. **Zone integration**: Clean cascade from SWING -> Zone -> Interaction

**Issues Found**:
1. **Implicit SWING dependency for TREND**: If multiple SWING blocks exist and `depends_on_swing` is not specified, builder uses "first SWING block" with no warning. This could be surprising behavior.
2. **ATR computation bypass**: `_compute_atr_if_needed()` imports pandas_ta directly instead of going through indicator_vendor, breaking the abstraction.
3. **Stage validation is incomplete**: `validate_stage2_constraints()` only checks tf_role and required params, not other constraints mentioned in docs.

**Structural Concerns**:
- Builder file is 614 lines with multiple responsibilities. Zone building logic could be extracted.
- `StructureStore.get_field()` and `ZoneStore.get_field()` have nearly identical implementations.

---

### 3.2 spec.py

**Purpose**: Dataclasses for structure and zone specifications with stable identity hashing.

**Key Classes**:
- `ConfirmationConfig` (frozen): Confirmation semantics
- `ZoneSpec` (frozen): Zone definition
- `StructureSpec` (frozen): Structure block definition

**Key Properties**:
- `spec_id`: Structure math identity (type + params + confirmation)
- `zone_spec_id`: Zone layer identity
- `block_id`: Placement identity (spec_id + key + tf_role)
- `zone_block_id`: Full identity including zones

**Dependencies**:
- `types.StructureType`, `types.ZoneType`
- Standard library only (hashlib, json)

**Strengths**:
1. **Immutable specs**: Frozen dataclasses
2. **Well-designed identity hashing**: Separate hashes for structure vs zones allows independent iteration
3. **Comprehensive validation**: Width model params validated at construction
4. **Hard-fail on legacy keys**: `structure_type` key in YAML raises immediately

**Issues Found**:
1. **Duplicate hash computation**: `compute_spec_id()`, `compute_zone_spec_id()`, etc. at module level duplicate the property logic. Should be consolidated.
2. **Zone ordering in hash**: `compute_zone_spec_id()` sorts zones by key, but `StructureSpec.zone_spec_id` property does not. Potential hash mismatch.
3. **Default confirmation**: `from_dict()` defaults to "immediate" mode, which may hide missing required config.

**Structural Concerns**:
- The identity hash design is elegant but the three levels (spec_id, block_id, zone_block_id) may be overkill for current use cases.

---

### 3.3 types.py

**Purpose**: Core type definitions, enums, and output schemas.

**Key Components**:
- `StructureType` (Enum): SWING, TREND
- `ZoneType` (Enum): DEMAND, SUPPLY
- `ZoneState` (int Enum): NONE=0, ACTIVE=1, BROKEN=2
- `TrendState` (int Enum): UNKNOWN=0, UP=1, DOWN=2
- Output schema tuples and mappings
- `STRUCTURE_SCHEMA_VERSION`: Semantic versioning for contracts

**Dependencies**:
- Standard library only

**Strengths**:
1. **Clear separation**: Internal vs public output schemas
2. **Schema versioning**: Enables contract tracking
3. **Comprehensive output definitions**: All fields documented with types

**Issues Found**:
1. **Schema version management**: Version "1.2.0" but no changelog or migration path documented.
2. **Int Enum values**: Using ints (0, 1, 2) for enums is efficient but loses type safety in numpy arrays (just int8).
3. **Naming inconsistency**: `TrendState.UP/DOWN` vs comments say "HH/HL pattern (structural uptrend)". The terminology could be clearer.

**Structural Concerns**:
- Output schema definitions are split across this file and registry.py. Single source would be better.

---

### 3.4 registry.py

**Purpose**: Structure type registry with detector class registration.

**Key Components**:
- `BaseDetector` (ABC): Abstract base for detectors
- `RegistryEntry`: Structure type metadata
- `STRUCTURE_REGISTRY`: Main registry dict
- `register_detectors()`: Lazy detector class registration
- Validation functions: `validate_structure_type()`, `validate_structure_params()`

**Dependencies**:
- `types.*` - output schemas and enums
- Lazy import of detectors

**Strengths**:
1. **Lazy registration**: Avoids circular imports elegantly
2. **Dependency tracking**: `depends_on` field enables ordering
3. **Validation centralized**: Single place for type/param validation
4. **Deprecated key handling**: Hard-fail on legacy config keys

**Issues Found**:
1. **Mutable global state**: `_detectors_registered` flag and `STRUCTURE_REGISTRY` mutation could cause issues in tests.
2. **Missing detector gracefully handled but shouldn't happen**: `detector_class=None` check exists but registering is called lazily, so this should never trigger in practice.
3. **Duplicate output schema storage**: `RegistryEntry.outputs` duplicates `STRUCTURE_OUTPUT_SCHEMAS` from types.py.

**Structural Concerns**:
- Registry pattern is good but `RegistryEntry` could use a frozen dataclass for immutability.

---

### 3.5 zone_interaction.py

**Purpose**: Computes zone interaction metrics (touched, inside, time_in_zone).

**Key Classes**:
- `ZoneInteractionComputer`: Metrics computation
- `ZONE_INTERACTION_OUTPUTS`: Field names (frozenset)

**Dependencies**:
- `types.ZoneState`
- NumPy only

**Strengths**:
1. **Clear metric definitions**: Formulas documented in docstring
2. **State-aware computation**: Only computes when state==ACTIVE
3. **Break bar override**: Correctly zeroes metrics on BROKEN state
4. **Instance tracking**: Resets time_in_zone on instance_id change

**Issues Found**:
1. **O(n) loop**: `build_batch()` uses a Python for-loop over bars. This is vectorizable for significant performance gains.
2. **Redundant checks**: NaN checks and state checks are repeated in multiple branches.
3. **Magic numbers**: `ZoneState.ACTIVE.value` used instead of direct enum comparison.

**Structural Concerns**:
- At 147 lines, this module is appropriately sized. Good separation of concerns.

---

### 3.6 Detectors

#### swing_detector.py

**Purpose**: Classic left/right pivot detection for swing highs/lows.

**Key Classes**:
- `SwingDetector(BaseDetector)`: Main detector
- `SwingState`: Internal state values
- `detect_swing_pivots()`: Pure function for testing

**Strengths**:
1. **Clear confirmation logic**: Well-documented window approach
2. **Strict inequality**: Equal values produce no pivot (well-defined tie-breaking)
3. **Forward-fill pattern**: Consistent with other components
4. **Pure function variant**: `detect_swing_pivots()` for testing

**Issues Found**:
1. **O(n * window) loop**: Nested Python loops for pivot detection. Highly vectorizable.
2. **Duplicate window iteration**: Both high and low checks iterate the same window separately.
3. **No early termination optimization**: Could break out of inner loop on first violation.

---

#### trend_classifier.py

**Purpose**: Classifies trend based on swing high/low patterns (HH/HL vs LL/LH).

**Key Classes**:
- `TrendClassifier(BaseDetector)`: Main classifier
- `classify_single_swing_update()`: Pure function for testing

**Strengths**:
1. **Clear classification rules**: HH+HL = UP, LH+LL = DOWN
2. **Version tracking**: `parent_version` increments on changes
3. **Minimum data requirement**: Needs 2 highs + 2 lows before classifying

**Issues Found**:
1. **Swing state decoding**: Uses magic numbers `swing_state[j] in (1, 3)` instead of `SwingState` enum.
2. **List-based history**: Using `list.pop(0)` for sliding window is O(n); deque would be O(1).
3. **No handling of equal pivots**: If `curr_high == prev_high`, the pattern is UNKNOWN. This may not be the desired behavior.

---

#### zone_detector.py

**Purpose**: Computes demand/supply zones from swing points.

**Key Classes**:
- `ZoneDetector`: Zone computation
- Helper functions: `compute_zone_spec_id()`, `compute_zone_instance_id()`

**Strengths**:
1. **State machine**: Clear NONE -> ACTIVE -> BROKEN transitions
2. **Multiple width models**: ATR, percent, fixed all supported
3. **Instance identity**: Deterministic hashing for caching
4. **Warmup handling**: Graceful skip during warmup period

**Issues Found**:
1. **Single zone per spec**: Current implementation tracks only ONE zone at a time. If a new swing creates a new zone, the old one is replaced. No multi-zone support.
2. **Width model validation split**: ZoneSpec validates params exist, ZoneDetector validates they can be used. Could be consolidated.
3. **ATR error handling asymmetry**: During warmup returns None; after warmup raises ValueError. Inconsistent.

**Structural Concerns**:
- Zone detection and zone interaction are tightly coupled through the builder. Consider if they should be merged.

---

## 4. Cross-Cutting Concerns

### 4.1 Code Duplication

| Duplicated Logic | Locations | Impact |
|-----------------|-----------|--------|
| Indicator computation | `indicators.py`, `feature_frame_builder.py` | Two paths to compute same indicators |
| Registry class | `indicator_registry.py`, `feature_frame_builder.py` | Confusion about canonical source |
| `build_features_from_idea_card()` | Defined twice in same file | BUG - second shadows first |
| Output schema definitions | `types.py`, `registry.py` | Potential drift |
| Hash computation | `spec.py` properties and module functions | Maintenance burden |

### 4.2 Naming Inconsistencies

| Issue | Example |
|-------|---------|
| UP/DOWN vs BULL/BEAR | `TrendState.UP` but comments reference "bullish" |
| Internal vs Public | "high_level" -> "swing_high_level" mapping adds cognitive load |
| Warmup vs first_valid | Different terms for similar concepts |

### 4.3 Performance Concerns

| Area | Issue | Severity |
|------|-------|----------|
| Swing detection | Nested Python loops | Medium - can be vectorized |
| Zone interaction | Per-bar Python loop | Medium - can be vectorized |
| Trend classification | List.pop(0) for history | Low - small lists |
| Dependency validation | O(n^2) on large spec sets | Low - unlikely in practice |

### 4.4 Testing Concerns

| Module | Test Path |
|--------|-----------|
| All modules | No pytest - CLI-only validation per project rules |
| Pure functions | `detect_swing_pivots()`, `classify_single_swing_update()` exist for validation |
| Metadata | `backtest metadata-smoke` CLI command |

---

## 5. Recommendations Summary

### Critical (Should Fix)

1. **Remove duplicate `build_features_from_idea_card()`** in feature_frame_builder.py
2. **Consolidate IndicatorRegistry** to single canonical source
3. **Fix ATR import in builder.py** - should use indicator_vendor

### High Priority

4. **Deprecate `indicators.py` DataFrame path** in favor of FeatureFrameBuilder
5. **Consolidate spec hash functions** - property methods OR module functions, not both
6. **Add param value validation** to indicator registry (length > 0, etc.)

### Medium Priority

7. **Extract factory functions** from feature_spec.py to separate file
8. **Vectorize swing/zone detection** for performance
9. **Use collections.deque** in trend classifier for O(1) history management
10. **Consolidate output schema definitions** to single location

### Low Priority

11. **Document schema version changelog**
12. **Consider multi-zone support** for zone detector
13. **Unify internal/public naming** or document mapping clearly

---

## 6. Overall Assessment

**Architecture Grade: B+**

The codebase demonstrates solid architectural thinking with clear patterns:
- Registry pattern for validation
- Immutable specifications
- Clean separation between declaration and computation
- Good provenance/metadata tracking

Main weaknesses are code duplication between parallel paths and some inconsistencies that have accumulated over iterative development. The market structure module is particularly well-designed with clear stage gating and extensibility.

The "fail-loud" philosophy is consistently applied, which is excellent for catching configuration errors early.

---

*Review completed 2026-01-02*
