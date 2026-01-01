# End-to-End Indicator Consistency: Registry + YAML Builder

> **Goal**: Guarantee IdeaCard→FeatureSpec→indicator_vendor→pandas_ta consistency at YAML-build time.

## Acceptance Criteria

- [x] Builder refuses to write YAML if `indicator_type` not in SUPPORTED_INDICATORS
- [x] Builder refuses to write YAML if any `params` key not accepted by indicator
- [x] Builder raises `MULTI_OUTPUT_BASE_KEY_REFERENCED` with suggestions when base key used
- [x] Builder raises `UNDECLARED_FEATURE` when key truly unknown
- [x] `required_indicators` auto-generated from feature_specs (no manual declaration needed)
- [x] `backtest audit-toolkit` CLI command validates consistency
- [x] Template/docs use canonical multi-output suffixes

---

## Phase 1: IndicatorRegistry ✅

**File**: `src/backtest/indicator_registry.py` (new)

- [x] 1.1 Create `IndicatorRegistry` class with cached indicator metadata
- [x] 1.2 Define SUPPORTED_INDICATORS (not all pandas_ta - only what vendor wires)
- [x] 1.3 Define input series requirements per indicator
- [x] 1.4 Define acceptable kwargs per indicator
- [x] 1.5 Add `get_indicator_info(name)` → `IndicatorInfo` dataclass
- [x] 1.6 Add `validate_params(name, params_dict)` → raises if unknown param
- [x] 1.7 Add `get_expanded_keys(indicator_type, output_key)` - canonical expansion API
- [x] 1.8 Add `get_primary_output(name)` for multi-output base key suggestions

---

## Phase 2: Refactor indicator_vendor to be registry-driven ✅

**File**: `src/backtest/indicator_vendor.py`

- [x] 2.1 Import and use `IndicatorRegistry` for supported indicators
- [x] 2.2 Use registry input_series for HLC/volume requirements
- [x] 2.3 Fallback to legacy heuristic sets for unsupported indicators
- [x] 2.4 Maintain backward compatibility for all existing callers
- [x] 2.5 Test: EMA, MACD, ADX all compute correctly with registry-driven inputs

---

## Phase 3: YAML Builder/Normalizer ✅

**File**: `src/backtest/idea_card_yaml_builder.py` (new)

### 3.1 Core data structures

- [x] 3.1.1 Define mapping shape per tf_config scope:
  ```python
  declared_keys: Set[str]           # all expanded output keys
  base_to_expanded: Dict[str, List[str]]  # base_output_key → [expanded_keys]
  ```

### 3.2 Validation functions

- [x] 3.2.1 `build_scope_mappings(tf_config)` → returns (ScopeMappings, errors)
- [x] 3.2.2 `validate_feature_reference(key, scope_mappings)` → returns ValidationError or None
- [x] 3.2.3 `validate_signal_rules(idea_card_dict, all_scope_mappings)` → checks all refs
- [x] 3.2.4 `validate_risk_model_refs(idea_card_dict, exec_scope_mappings)` → checks atr_key etc

### 3.3 Error types

- [x] 3.3.1 `MULTI_OUTPUT_BASE_KEY_REFERENCED` with suggested expanded keys
- [x] 3.3.2 `UNDECLARED_FEATURE` for truly unknown keys
- [x] 3.3.3 `UNSUPPORTED_INDICATOR` if indicator_type not in registry
- [x] 3.3.4 `INVALID_PARAM` if params key not accepted by indicator

### 3.4 Main entry point

- [x] 3.4.1 `normalize_idea_card_yaml(raw: dict) -> (normalized, ValidationResult)`
  - Validates all indicator_types exist
  - Validates all params are accepted
  - Validates all signal_rules/risk_model references
  - Auto-generates `required_indicators` from expanded keys
  - Returns normalized dict + validation report

---

## Phase 4: Wire builder into YAML writers ✅

**File**: `src/backtest/gates/idea_card_generator.py`

- [x] 4.1 Import `normalize_idea_card_yaml` from builder
- [x] 4.2 Call builder before `yaml.dump()`
- [x] 4.3 Fail generation if builder raises validation error
- [x] 4.4 Use registry to generate correct expanded keys in signal_rules

---

## Phase 5: CLI commands ✅

### 5.1 idea-card-normalize command

**Files**: `src/tools/backtest_cli_wrapper.py`, `trade_cli.py`

- [x] 5.1.1 Add `backtest_idea_card_normalize_tool()` in wrapper
- [x] 5.1.2 Add argparse subcommand `backtest idea-card-normalize`
- [x] 5.1.3 Options: `--idea-card`, `--write` (in-place), `--json`
- [x] 5.1.4 Print report of what was validated/auto-fixed

### 5.2 audit-toolkit command

- [x] 5.2.1 Add `backtest_audit_toolkit_tool()` in wrapper
- [x] 5.2.2 Add argparse subcommand `backtest audit-toolkit`
- [x] 5.2.3 Verify SUPPORTED_INDICATORS exist in pandas_ta
- [x] 5.2.4 Verify MULTI_OUTPUT_KEYS vs SUPPORTED_INDICATORS consistency

---

## Phase 6: Template and docs alignment ✅

**File**: `configs/idea_cards/_TEMPLATE.yml`

- [x] 6.1 Update multi-output suffix examples to match SUPPORTED_INDICATORS:
  - `bbands` → `_lower`, `_mid`, `_upper`, `_bandwidth`, `_percent_b`
  - `macd` → `_macd`, `_signal`, `_histogram`
  - `stoch` → `_k`, `_d`
  - All other multi-output indicators documented
- [x] 6.2 Add note: `required_indicators` is auto-generated, optional in YAML
- [x] 6.3 Update INDICATOR REFERENCE section with canonical naming
- [x] 6.4 Add validation command references

---

## Validation Commands (CLI-only, no pytest)

```bash
# Normalize IdeaCard YAML (dry-run)
python trade_cli.py backtest idea-card-normalize --idea-card BTCUSDT_1h_macd_kama_trend

# Normalize and write in-place
python trade_cli.py backtest idea-card-normalize --idea-card BTCUSDT_1h_macd_kama_trend --write

# Audit toolkit consistency
python trade_cli.py backtest indicators --audit-toolkit

# Existing: show indicator keys for IdeaCard
python trade_cli.py backtest indicators --idea-card BTCUSDT_1h_macd_kama_trend --print-keys
```

---

## Files Changed

| File | Action |
|------|--------|
| `src/backtest/indicator_registry.py` | NEW |
| `src/backtest/indicator_vendor.py` | MODIFY |
| `src/backtest/idea_card_yaml_builder.py` | NEW |
| `src/backtest/gates/idea_card_generator.py` | MODIFY |
| `src/tools/backtest_cli_wrapper.py` | MODIFY |
| `trade_cli.py` | MODIFY |
| `configs/idea_cards/_TEMPLATE.yml` | MODIFY |
| `docs/todos/INDICATOR_REGISTRY_YAML_BUILDER_PHASES.md` | NEW (this file) |

---

## Notes

- **No pytest files** — all validation via CLI commands
- **Fail loud** — builder refuses to write YAML on validation errors
- **Registry-driven** — no hardcoded indicator input requirements
- **Params passed from YAML** — no per-indicator hardcoded param wiring

