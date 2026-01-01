# IdeaCard Normalizer Review

> **Comprehensive review** of how the IdeaCard YAML normalizer works, including indicator validation against the vendor registry and pandas_ta.

---

## Executive Summary

The IdeaCard normalizer provides **build-time validation and normalization** for IdeaCard YAML files:

1. **Indicator Validation** - Checks if indicators exist in registry AND are callable in pandas_ta
2. **Parameter Validation** - Validates all params are accepted by each indicator
3. **Reference Validation** - Ensures signal_rules/risk_model use expanded keys (not base keys)
4. **Auto-Generation** - Auto-generates `required_indicators` from feature_specs

**Key Principle:** Registry is the contract. If an indicator isn't in the registry, it's rejected even if it exists in pandas_ta.

---

## 1. Normalizer Architecture

### 1.1 Components

```
┌─────────────────────────────────────────────────────────────┐
│                    IdeaCard Normalizer                       │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Indicator       │  │ Reference       │  │ Auto-Generation │
│ Validation      │  │ Validation     │  │                 │
│                 │  │                 │  │                 │
│ - Registry      │  │ - Signal rules │  │ - required_     │
│   check         │  │ - Risk model    │  │   indicators    │
│ - pandas_ta     │  │ - Expanded keys │  │                 │
│   callable      │  │ - Base key      │  │                 │
│ - Params        │  │   detection     │  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

### 1.2 Validation Flow

```
IdeaCard YAML (raw dict)
    ↓
build_all_scope_mappings()
    ↓
For each tf_config:
    build_scope_mappings()
        ↓
    For each feature_spec:
        1. Check registry.is_supported() ✅
        2. Check pandas_ta callable ✅
        3. Validate params ✅
        4. Get expanded keys ✅
    ↓
validate_signal_rules() - Check all references
validate_risk_model_refs() - Check atr_key, etc.
    ↓
ValidationResult (is_valid, errors)
    ↓
If valid: normalize (auto-generate required_indicators)
If invalid: return unchanged (caller refuses to write)
```

---

## 2. Indicator Validation Process

### 2.1 Two-Stage Validation

**Stage 1: Registry Check**
- Checks if indicator is in `SUPPORTED_INDICATORS`
- Registry is the **contract** - only registry indicators are allowed
- Prevents agents from using indicators that exist in pandas_ta but aren't wired

**Stage 2: pandas_ta Callable Check**
- Verifies indicator is actually callable in pandas_ta
- Uses `getattr(ta, indicator_type, None)` and `callable(ta_func)`
- Catches registry/vendor mismatches

**Code:**
```python
# Stage 1: Registry check
if not registry.is_supported(indicator_type):
    errors.append(ValidationError(
        code=ValidationErrorCode.UNSUPPORTED_INDICATOR,
        message=f"Indicator type '{indicator_type}' is not supported.",
        location=location,
        suggestions=registry.list_indicators(),  # Show available indicators
    ))
    continue

# Stage 2: pandas_ta callable check
try:
    import pandas_ta as ta
    ta_func = getattr(ta, indicator_type, None)
    if ta_func is None or not callable(ta_func):
        errors.append(ValidationError(
            code=ValidationErrorCode.UNSUPPORTED_INDICATOR,
            message=f"Indicator '{indicator_type}' is supported in registry but not callable in pandas_ta.",
            location=location,
        ))
        continue
except ImportError:
    errors.append(ValidationError(
        code=ValidationErrorCode.UNSUPPORTED_INDICATOR,
        message="pandas_ta not available for validation.",
        location=location,
    ))
```

### 2.2 Why Two Checks?

**Registry Check (Stage 1):**
- **Purpose**: Enforces contract - only registry indicators are supported
- **Why**: Prevents using indicators that exist in pandas_ta but aren't wired in vendor
- **Example**: `"ema"` is in registry ✅, `"unknown_indicator"` is not ❌

**pandas_ta Check (Stage 2):**
- **Purpose**: Validates indicator actually exists and is callable
- **Why**: Catches registry/vendor mismatches (registry says supported, but pandas_ta doesn't have it)
- **Example**: Registry has `"ema"`, but pandas_ta import fails or function missing

### 2.3 Parameter Validation

**After indicator validation passes:**
```python
# Validate params are accepted
try:
    registry.validate_params(indicator_type, params)
except ValueError as e:
    errors.append(ValidationError(
        code=ValidationErrorCode.INVALID_PARAM,
        message=str(e),  # e.g., "Unknown param 'foo' for indicator 'ema'"
        location=location,
    ))
```

**Example:**
```yaml
# ✅ Valid
- indicator_type: ema
  params:
    length: 20

# ❌ Invalid - 'foo' not accepted
- indicator_type: ema
  params:
    length: 20
    foo: 10  # Error: Unknown param 'foo' for indicator 'ema'
```

### 2.4 Multi-Output Expansion

**After validation, get expanded keys:**
```python
# Get expanded keys (handles single and multi-output)
expanded_keys = registry.get_expanded_keys(indicator_type, output_key)

# Add to declared_keys
mappings.declared_keys.update(expanded_keys)

# If multi-output, track base -> expanded mapping
if registry.is_multi_output(indicator_type):
    mappings.base_to_expanded[output_key] = expanded_keys
```

**Example:**
```python
# Single-output: ema
expanded_keys = registry.get_expanded_keys("ema", "ema_fast")
# Returns: ["ema_fast"]

# Multi-output: macd
expanded_keys = registry.get_expanded_keys("macd", "macd")
# Returns: ["macd_macd", "macd_signal", "macd_histogram"]
```

---

## 3. Scope Mappings

### 3.1 Purpose

**Scope mappings** track what indicators are declared in each TF role (exec/htf/mtf):

```python
@dataclass
class ScopeMappings:
    role: str                                    # "exec", "htf", "mtf"
    declared_keys: Set[str]                     # All expanded output keys
    base_to_expanded: Dict[str, List[str]]       # base_key -> [expanded_keys]
```

**Example:**
```python
# For exec TF with:
# - ema (output_key: "ema_fast") -> single-output
# - macd (output_key: "macd") -> multi-output

mappings = ScopeMappings(
    role="exec",
    declared_keys={"ema_fast", "macd_macd", "macd_signal", "macd_histogram"},
    base_to_expanded={
        "macd": ["macd_macd", "macd_signal", "macd_histogram"]
    }
)
```

### 3.2 Building Scope Mappings

**Process:**
1. For each `feature_spec` in `tf_config.feature_specs`:
   - Validate indicator type (registry + pandas_ta)
   - Validate params
   - Get expanded keys
   - Add to `declared_keys`
   - If multi-output, add to `base_to_expanded`

**Code:**
```python
def build_scope_mappings(
    tf_config: Dict[str, Any],
    role: str,
    registry: IndicatorRegistry,
) -> Tuple[ScopeMappings, List[ValidationError]]:
    mappings = ScopeMappings(role=role)
    errors: List[ValidationError] = []
    
    feature_specs = tf_config.get("feature_specs", [])
    
    for i, spec in enumerate(feature_specs):
        indicator_type = spec.get("indicator_type", "")
        output_key = spec.get("output_key", "")
        params = spec.get("params", {})
        
        # Validate indicator (registry + pandas_ta)
        if not registry.is_supported(indicator_type):
            errors.append(...)
            continue
        
        # Validate pandas_ta callable
        ta_func = getattr(ta, indicator_type, None)
        if ta_func is None or not callable(ta_func):
            errors.append(...)
            continue
        
        # Validate params
        try:
            registry.validate_params(indicator_type, params)
        except ValueError as e:
            errors.append(...)
        
        # Get expanded keys
        expanded_keys = registry.get_expanded_keys(indicator_type, output_key)
        mappings.declared_keys.update(expanded_keys)
        
        # Track multi-output base keys
        if registry.is_multi_output(indicator_type):
            mappings.base_to_expanded[output_key] = expanded_keys
    
    return mappings, errors
```

---

## 4. Reference Validation

### 4.1 Feature Reference Validation

**Validates that all references in signal_rules and risk_model use declared keys:**

```python
def validate_feature_reference(
    key: str,
    role: str,
    location: str,
    all_mappings: Dict[str, ScopeMappings],
) -> Optional[ValidationError]:
    # OHLCV columns are always valid
    if key in OHLCV_COLUMNS:
        return None
    
    mappings = all_mappings[role]
    
    # Check if key is in declared_keys (expanded key)
    if key in mappings.declared_keys:
        return None  # ✅ Valid
    
    # Check if key is a base key of multi-output indicator
    if key in mappings.base_to_expanded:
        expanded = mappings.base_to_expanded[key]
        return ValidationError(
            code=ValidationErrorCode.MULTI_OUTPUT_BASE_KEY_REFERENCED,
            message=f"Multi-output indicator '{key}' referenced by base key. Use one of the expanded keys instead.",
            location=location,
            suggestions=expanded,  # Show available expanded keys
        )
    
    # Key is truly undeclared
    return ValidationError(
        code=ValidationErrorCode.UNDECLARED_FEATURE,
        message=f"Feature '{key}' referenced but not declared in {role} TF.",
        location=location,
        suggestions=sorted(mappings.declared_keys)[:10],  # Show available keys
    )
```

### 4.2 Error Types

**1. MULTI_OUTPUT_BASE_KEY_REFERENCED**
- **When**: Reference uses base key instead of expanded key
- **Example**: `indicator_key: "macd"` instead of `indicator_key: "macd_macd"`
- **Suggestion**: Shows available expanded keys

**2. UNDECLARED_FEATURE**
- **When**: Reference to key that doesn't exist
- **Example**: `indicator_key: "unknown_indicator"`
- **Suggestion**: Shows available declared keys

**Example:**
```yaml
# ❌ Error: MULTI_OUTPUT_BASE_KEY_REFERENCED
signal_rules:
  entry_rules:
    - conditions:
        - indicator_key: "macd"  # Base key - should use "macd_macd", "macd_signal", or "macd_histogram"
          operator: "gt"
          value: 0

# ✅ Valid
signal_rules:
  entry_rules:
    - conditions:
        - indicator_key: "macd_macd"  # Expanded key
          operator: "gt"
          value: 0
```

### 4.3 Signal Rules Validation

**Validates all references in entry_rules and exit_rules:**
```python
def validate_signal_rules(
    idea_card_dict: Dict[str, Any],
    all_mappings: Dict[str, ScopeMappings],
) -> List[ValidationError]:
    errors: List[ValidationError] = []
    signal_rules = idea_card_dict.get("signal_rules", {})
    
    # Entry rules
    for i, rule in enumerate(signal_rules.get("entry_rules", [])):
        for j, cond in enumerate(rule.get("conditions", [])):
            role = cond.get("tf", "exec")
            indicator_key = cond.get("indicator_key", "")
            
            # Validate indicator_key
            if indicator_key:
                error = validate_feature_reference(
                    indicator_key, role, f"signal_rules.entry_rules[{i}].conditions[{j}].indicator_key", all_mappings
                )
                if error:
                    errors.append(error)
            
            # Validate value if indicator comparison
            if cond.get("is_indicator_comparison", False):
                value = cond.get("value", "")
                if isinstance(value, str) and value:
                    error = validate_feature_reference(
                        value, role, f"signal_rules.entry_rules[{i}].conditions[{j}].value", all_mappings
                    )
                    if error:
                        errors.append(error)
    
    # Exit rules (same logic)
    ...
    
    return errors
```

### 4.4 Risk Model Validation

**Validates references in risk_model (e.g., `atr_key`):**
```python
def validate_risk_model_refs(
    idea_card_dict: Dict[str, Any],
    all_mappings: Dict[str, ScopeMappings],
) -> List[ValidationError]:
    errors: List[ValidationError] = []
    risk_model = idea_card_dict.get("risk_model", {})
    
    # Check stop_loss.atr_key
    stop_loss = risk_model.get("stop_loss", {})
    atr_key = stop_loss.get("atr_key")
    if atr_key:
        error = validate_feature_reference(
            atr_key, "exec", "risk_model.stop_loss.atr_key", all_mappings
        )
        if error:
            errors.append(error)
    
    # Check take_profit.atr_key (same logic)
    ...
    
    return errors
```

---

## 5. Auto-Generation

### 5.1 Required Indicators Generation

**Auto-generates `required_indicators` from feature_specs:**

```python
def generate_required_indicators(
    idea_card_dict: Dict[str, Any],
) -> Dict[str, List[str]]:
    """
    Generate required_indicators for each TF role.
    
    Auto-generates from declared feature_specs, so users don't need
    to manually maintain this list.
    """
    registry = get_registry()
    result: Dict[str, List[str]] = {}
    
    tf_configs = idea_card_dict.get("tf_configs", {})
    
    for role, tf_config in tf_configs.items():
        keys: List[str] = []
        feature_specs = tf_config.get("feature_specs", [])
        
        for spec in feature_specs:
            indicator_type = spec.get("indicator_type", "")
            output_key = spec.get("output_key", "")
            
            if registry.is_supported(indicator_type):
                expanded = registry.get_expanded_keys(indicator_type, output_key)
                keys.extend(expanded)
        
        if keys:
            result[role] = sorted(set(keys))
    
    return result
```

**Example:**
```yaml
# Before normalization (required_indicators can be omitted)
tf_configs:
  exec:
    feature_specs:
      - indicator_type: ema
        output_key: ema_fast
      - indicator_type: macd
        output_key: macd

# After normalization (auto-generated)
tf_configs:
  exec:
    feature_specs:
      - indicator_type: ema
        output_key: ema_fast
      - indicator_type: macd
        output_key: macd
    required_indicators:
      - ema_fast
      - macd_macd
      - macd_signal
      - macd_histogram
```

---

## 6. Normalization Process

### 6.1 Main Entry Point

```python
def normalize_idea_card_yaml(
    idea_card_dict: Dict[str, Any],
    auto_generate_required: bool = True,
) -> Tuple[Dict[str, Any], ValidationResult]:
    """
    Normalize and validate an IdeaCard YAML dict.
    
    Process:
    1. Validate the YAML (fails loud if invalid)
    2. Optionally auto-generate required_indicators
    3. Return normalized dict
    """
    # Step 1: Validate
    result = validate_idea_card_yaml(idea_card_dict)
    
    if not result.is_valid:
        # Return unchanged - caller should refuse to write
        return idea_card_dict, result
    
    # Step 2: Normalize (make copy)
    normalized = dict(idea_card_dict)
    
    # Step 3: Auto-generate required_indicators
    if auto_generate_required:
        required_by_role = generate_required_indicators(normalized)
        
        tf_configs = normalized.get("tf_configs", {})
        for role, keys in required_by_role.items():
            if role in tf_configs:
                tf_configs[role]["required_indicators"] = keys
    
    return normalized, result
```

### 6.2 Validation Entry Point

```python
def validate_idea_card_yaml(idea_card_dict: Dict[str, Any]) -> ValidationResult:
    """
    Validate an IdeaCard YAML dict at build time.
    
    Steps:
    1. Build scope mappings (validates indicators and params)
    2. Validate signal_rules references
    3. Validate risk_model references
    """
    registry = get_registry()
    all_errors: List[ValidationError] = []
    
    # Step 1: Build scope mappings (validates indicators and params)
    all_mappings, mapping_errors = build_all_scope_mappings(idea_card_dict, registry)
    all_errors.extend(mapping_errors)
    
    # Step 2: Validate signal rules references
    signal_errors = validate_signal_rules(idea_card_dict, all_mappings)
    all_errors.extend(signal_errors)
    
    # Step 3: Validate risk model references
    risk_errors = validate_risk_model_refs(idea_card_dict, all_mappings)
    all_errors.extend(risk_errors)
    
    is_valid = len(all_errors) == 0
    
    return ValidationResult(
        is_valid=is_valid,
        errors=all_errors,
    )
```

---

## 7. Complete Example

### 7.1 Input YAML

```yaml
id: BTCUSDT_15m_test
version: 1.0.0
name: Test Strategy

tf_configs:
  exec:
    tf: 15m
    feature_specs:
      - indicator_type: ema
        output_key: ema_fast
        params:
          length: 9
      - indicator_type: macd
        output_key: macd
        params:
          fast: 12
          slow: 26
          signal: 9

signal_rules:
  entry_rules:
    - conditions:
        - indicator_key: ema_fast
          operator: gt
          value: 0
        - indicator_key: macd  # ❌ Base key - should be expanded
          operator: gt
          value: 0
```

### 7.2 Validation Process

**Step 1: Build Scope Mappings**
```python
# For exec TF:
# 1. Validate "ema" - ✅ in registry, ✅ callable in pandas_ta, ✅ params valid
#    expanded_keys = ["ema_fast"]
# 2. Validate "macd" - ✅ in registry, ✅ callable in pandas_ta, ✅ params valid
#    expanded_keys = ["macd_macd", "macd_signal", "macd_histogram"]

mappings = ScopeMappings(
    role="exec",
    declared_keys={"ema_fast", "macd_macd", "macd_signal", "macd_histogram"},
    base_to_expanded={"macd": ["macd_macd", "macd_signal", "macd_histogram"]}
)
```

**Step 2: Validate Signal Rules**
```python
# Check indicator_key: "ema_fast"
# ✅ Found in declared_keys

# Check indicator_key: "macd"
# ❌ Not in declared_keys
# ✅ Found in base_to_expanded
# → Error: MULTI_OUTPUT_BASE_KEY_REFERENCED
#    Suggestions: ["macd_macd", "macd_signal", "macd_histogram"]
```

**Step 3: Validation Result**
```python
result = ValidationResult(
    is_valid=False,
    errors=[
        ValidationError(
            code=ValidationErrorCode.MULTI_OUTPUT_BASE_KEY_REFERENCED,
            message="Multi-output indicator 'macd' referenced by base key. Use one of the expanded keys instead.",
            location="signal_rules.entry_rules[0].conditions[1].indicator_key",
            suggestions=["macd_macd", "macd_signal", "macd_histogram"]
        )
    ]
)
```

### 7.3 Fixed YAML

```yaml
signal_rules:
  entry_rules:
    - conditions:
        - indicator_key: ema_fast
          operator: gt
          value: 0
        - indicator_key: macd_macd  # ✅ Expanded key
          operator: gt
          value: 0
```

**After Normalization:**
```yaml
tf_configs:
  exec:
    required_indicators:  # ✅ Auto-generated
      - ema_fast
      - macd_macd
      - macd_signal
      - macd_histogram
```

---

## 8. CLI Usage

### 8.1 Normalize Command

```bash
# Validate and normalize IdeaCard
python trade_cli.py backtest idea-card-normalize --idea-card BTCUSDT_15m_test

# Normalize and write back to file
python trade_cli.py backtest idea-card-normalize --idea-card BTCUSDT_15m_test --write
```

### 8.2 Output Examples

**Success:**
```
✅ IdeaCard validation passed
Normalized YAML written to: configs/idea_cards/BTCUSDT_15m_test.yml
```

**Failure:**
```
❌ IdeaCard validation failed

============================================================
IDEACARD YAML VALIDATION FAILED
============================================================

1. [MULTI_OUTPUT_BASE_KEY_REFERENCED]
   Multi-output indicator 'macd' referenced by base key. Use one of the expanded keys instead.
   Location: signal_rules.entry_rules[0].conditions[1].indicator_key
   Suggestions: ['macd_macd', 'macd_signal', 'macd_histogram']

============================================================
FIX: Correct the errors above and re-run normalization.
============================================================
```

---

## 9. Key Design Principles

### 9.1 Registry as Contract

**Principle:** Registry defines what's supported, not pandas_ta.

**Why:**
- Prevents using indicators that exist in pandas_ta but aren't wired
- Single source of truth for supported indicators
- Clear contract for agents/orchestrators

**Example:**
```python
# Even if "unknown_indicator" exists in pandas_ta:
# ❌ Rejected - not in registry
# ✅ Only registry indicators are allowed
```

### 9.2 Fail Loud

**Principle:** Validation errors are explicit and actionable.

**Features:**
- Clear error codes (`UNSUPPORTED_INDICATOR`, `MULTI_OUTPUT_BASE_KEY_REFERENCED`)
- Location information (exact path in YAML)
- Suggestions (available indicators, expanded keys)

### 9.3 Auto-Generation

**Principle:** Reduce manual maintenance.

**Features:**
- `required_indicators` auto-generated from `feature_specs`
- No need to manually maintain indicator lists
- Always in sync with feature_specs

### 9.4 Expanded Keys Only

**Principle:** Signal rules must use expanded keys, not base keys.

**Why:**
- Prevents ambiguity (which output of multi-output indicator?)
- Clear contract (explicit output selection)
- Better error messages (suggests correct keys)

---

## 10. Summary

**IdeaCard Normalizer provides:**

1. **Indicator Validation** - Two-stage check (registry + pandas_ta callable)
2. **Parameter Validation** - Ensures all params are accepted
3. **Reference Validation** - Validates signal_rules/risk_model use expanded keys
4. **Auto-Generation** - Auto-generates `required_indicators` from feature_specs

**Key Features:**

- **Registry as contract** - Only registry indicators are supported
- **Fail loud** - Explicit errors with suggestions
- **Expanded keys only** - Multi-output indicators must use expanded keys
- **Auto-generation** - Reduces manual maintenance

**Validation Flow:**

```
IdeaCard YAML → build_scope_mappings() → validate_signal_rules() → validate_risk_model_refs() → ValidationResult
```

**If Valid:**
- Auto-generate `required_indicators`
- Return normalized dict

**If Invalid:**
- Return unchanged dict
- Caller refuses to write YAML

---

## 11. Backlog: Future Validation Enhancements

### 11.1 Timeframe Compatibility Validation

**Status:** Backlog

**Goal:** Add validation that each feature/indicator/spec is compatible with its declared role and timeframe.

**Validation Checks:**
- **Role Compatibility**: Verify indicator is appropriate for its declared role (`exec`, `htf`, `mtf`)
- **Timeframe Compatibility**: Validate indicator works with declared timeframe (e.g., "1m", "5m", "1h", "4h", "1D")
- **Warmup Feasibility**: Check that required warmup/lookback is feasible for the configured window

**Error Output:**
- Offending spec/output key
- Declared tf/role
- Expected compatible tf set (or rule)
- Suggested fixes (closest valid tf or alternative indicator)

**Example:**
```yaml
# ❌ Error: Indicator 'ema' with length=200 requires 200+ warmup bars
#    but '1m' timeframe in 'exec' role may not have sufficient data
#    Location: tf_configs.exec.feature_specs[0]
#    Suggestion: Use '4h' or '1D' timeframe, or reduce length to <50
tf_configs:
  exec:
    tf: 1m
    feature_specs:
      - indicator_type: ema
        output_key: ema_trend
        params:
          length: 200  # Requires 200 bars warmup
```

### 11.2 Semantic Misuse Linting

**Status:** Backlog

**Goal:** Add a linter pass that flags likely semantic mistakes in IdeaCards.

**Lint Rules:**
- **Oscillator Misuse**: Flag using oscillator outputs (RSI, StochRSI, MACD histogram) as if they were price levels
  - Example: Comparing RSI directly to `close` without normalization
- **Unit Incompatibility**: Detect mixing incompatible units (e.g., comparing ATR to RSI directly)
- **Cross Rule Misuse**: Flag "cross" rules on features that aren't comparable in scale unless explicitly normalized
- **Domain Mismatch**: Detect referencing features in signal rules that don't match their intended domain
  - Price vs momentum vs volatility vs volume indicators

**Lint Behavior:**
- **Default**: Non-fatal warnings (does not block normalization)
- **Strict Mode**: `--strict` flag makes lint failures block normalization
- **Structured Output**: Lint results include:
  - `rule_id`: Unique identifier for the lint rule
  - `message`: Human-readable explanation
  - `affected_keys`: List of indicator keys involved
  - `location`: YAML path if available

**Example:**
```yaml
# ⚠️ Warning: SEMANTIC_MISUSE_OSCILLATOR_AS_PRICE
#    Rule: OSCILLATOR_COMPARED_TO_PRICE
#    Location: signal_rules.entry_rules[0].conditions[0]
#    Affected keys: ['rsi', 'close']
#    Message: RSI (oscillator, 0-100 range) compared directly to close (price).
#             Consider normalizing or using RSI threshold (e.g., rsi > 50).
signal_rules:
  entry_rules:
    - conditions:
        - indicator_key: rsi
          operator: gt
          value: close  # ❌ Comparing oscillator to price
          is_indicator_comparison: true
```

**Lint Rule IDs:**
- `OSCILLATOR_COMPARED_TO_PRICE`: Oscillator compared directly to price
- `INCOMPATIBLE_UNITS`: Mixing incompatible units (ATR vs RSI)
- `CROSS_INCOMPATIBLE_SCALE`: Cross rule on non-comparable features
- `DOMAIN_MISMATCH`: Feature used outside intended domain

---

**Document Version:** 1.0  
**Last Updated:** 2024  
**Status:** Comprehensive Normalizer Review

