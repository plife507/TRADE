# DSL / Play Domain Review

**Reviewer:** dsl-reviewer  
**Date:** 2026-02-18  
**Scope:** src/backtest/rules/, src/backtest/play/, src/backtest/execution_validation.py, src/backtest/play_yaml_builder.py, src/backtest/feature_registry.py

---

## 1. Module Overview

The DSL/play domain is the strategy specification and evaluation layer. It spans:

- **YAML -> AST pipeline** (dsl_parser.py): Parses play YAML into frozen AST nodes.
- **AST node types** (dsl_nodes/): FeatureRef, Cond, AllExpr, AnyExpr, NotExpr, HoldsFor, OccurredWithin, CountTrue and duration variants. All immutable frozen dataclasses.
- **Evaluation engine** (evaluation/): Pure-functional evaluation of AST against RuntimeSnapshotView. ExprEvaluator dispatches to condition_ops, boolean_ops, window_ops, shift_ops, resolve.
- **Strategy blocks** (strategy_blocks.py): Intent, Case, Block, BlockSet. First-match semantics per block.
- **Play config** (play/): Play dataclass, config_models (AccountConfig, FeeModel, ExitMode), risk_model (StopLossRule, TakeProfitRule, SizingRule).
- **Validation** (dsl_validator.py): Compile-time semantic checks -- circular setup detection, SetupRef in windows, field existence.
- **Operator registry** (registry.py): OperatorSpec catalog and OPERATOR_REGISTRY dict.
- **Feature registry** (feature_registry.py): Unified indicator+structure catalog for feature resolution.
- **Execution validation** (execution_validation.py): Play contract checks -- exit mode compatibility, feature ref extraction.
- **YAML builder** (play_yaml_builder.py): Scaffolding for building play YAML programmatically.

---

## 2. File-by-File Findings

### 2.1 src/backtest/rules/dsl_parser.py

**Module role:** Main YAML-to-AST parse pipeline.

**near_pct double-divide: CONFIRMED FIXED**

parse_cond() divides tolerance by 100 for near_pct/near_abs. parse_condition_shorthand() divides by 100. play.py _convert_shorthand_condition() passes tolerance raw (no division). Evaluator receives correct ratio (0.05 for YAML 5). Fix verified.

**BUG-DSL-001 (MED):** Missing-key guard on window expr field. If expr: key absent from window operator YAML, parse_expr({}) receives empty dict causing cryptic KeyError. Should raise DSLParseError explicitly before calling parse_expr.

**BUG-DSL-003 (LOW):** import re inside _normalize_bracket_syntax() function body. Called on every invocation. Move to module level.

---

### 2.2 src/backtest/rules/eval.py

**Module role:** Pure operator implementations.

**Cross-above/cross-below first-bar: CONFIRMED SAFE** -- MISSING_PREV_VALUE returned on first bar. TradingView semantics (prev <= rhs AND curr > rhs) correct.

**eval_near_pct rhs=0: CONFIRMED SAFE** -- ZeroDivisionError explicitly guarded.

**BUG-EVAL-002 (LOW):** ValueType.NUMERIC defined in types.py but never returned by from_value(). Dead enum value. Remove or document as reserved.

---

### 2.3 src/backtest/rules/strategy_blocks.py

**Module role:** Intent/Case/Block/BlockSet data structures and execution logic.

**BUG-SB-001 (HIGH):** BlockSet.execute() at line ~256 returns intents from ALL firing blocks. No conflict resolution when entry_long and exit_long both fire on the same bar from different blocks. Undefined behavior at the DSL layer.

Recommendation: Document engine priority rules explicitly, or add conflict resolution in BlockSet.execute() with clear priority contract.

**BUG-SB-002 (MED):** VALID_ACTIONS frozenset defined but NOT checked in Intent.__post_init__. Typo like action="exit_llong" passes construction and only fails at engine dispatch. Add validation in __post_init__.

---

### 2.4 src/backtest/rules/compile.py

**BUG-COMP-001 (LOW):** compile_condition() uses legacy {indicator_key, tf} dict format. Appears unreachable in current path (all conditions come via parse_expr()). Remove dead code.

**BUG-COMP-003 (MED):** _validate_structure_path() at line ~301 explicitly defers field name validation to runtime. Typos in structure field paths only fail during evaluation.

---

### 2.5 src/backtest/rules/dsl_validator.py

**Circular setup detection: CONFIRMED CORRECT** -- DFS with 0=unvisited, 1=in-progress, 2=done. Standard cycle detection correctly implemented.

**SetupRef-in-window rejection: CONFIRMED CORRECT** -- Correctly rejected at compile time.

**BUG-VAL-001 (LOW):** _validate_single_ref() accesses private registry._features at line ~162. Should use a public accessor method.

---

### 2.6 src/backtest/rules/registry.py

**Module role:** Operator specification catalog.

**BUG-REG-001 (CRITICAL): near_pct, near_abs, between, in missing from OPERATOR_REGISTRY**

OPERATOR_REGISTRY at lines 52-112 contains only: >, <, >=, <=, ==, !=, approx_eq, cross_above, cross_below.

The following four operators are fully implemented in eval.py and parsed in dsl_parser.py but ABSENT from the registry:
- near_pct (tolerance-based proximity, percentage)
- near_abs (tolerance-based proximity, absolute)
- between (range check)
- in (membership check)

Impact:
- validate_operator returns error for all four
- is_operator_supported returns False for all four
- SUPPORTED_OPERATORS frozenset incorrectly excludes them
- Any validation pass using is_operator_supported() rejects valid plays using these operators

Fix: Add OperatorSpec entries for all four. near_pct/near_abs need needs_tolerance=True.

---

### 2.7 src/backtest/rules/types.py

**BUG-TYPES-001 (LOW):** import math inside ValueType.from_value() hot-path function body. Called on every value classification. Move to module level.

INT coercion (float 1.0 treated as INT) is intentional -- pandas returns float64 for int columns. Documented correctly.

---

### 2.8 src/backtest/rules/evaluation/core.py

**Module role:** ExprEvaluator -- central dispatch for AST evaluation.

**BUG-CORE-001 (HIGH): ExprEvaluator NOT thread-safe despite documentation**

Class docstring claims Thread-safe and stateless but has mutable instance attributes:
  _setup_expr_cache: dict[str, Expr] = {}  -- mutable
  _setup_eval_stack: set[str] = set()       -- mutable

Concurrent evaluation by multiple threads would corrupt these structures.

**BUG-CORE-002 (CRITICAL): Setup expression cache is never populated**

_setup_expr_cache is initialized empty in __init__ and there is no public API to populate it. evaluate() dispatches SetupRef to eval_setup() which reads from _setup_expr_cache. Since the cache is always empty, ALL setup: references in plays fail at runtime with UNKNOWN_SETUP_REF.

Fix: Add set_setup_registry(setups: dict[str, Expr]) method. Call during engine initialization after compiling setups from the play.

---

### 2.9 src/backtest/rules/evaluation/condition_ops.py

**Cross-over first-bar: CONFIRMED SAFE** -- Delegates to eval_cross_above/cross_below which return MISSING_PREV_VALUE on first bar.

**BUG-COND-001 (LOW):** Higher-TF RHS shifted by cond.rhs.shifted(1) where offset is in exec-bar units, not higher-TF-bar units. Semantically incorrect for multi-TF RHS comparisons.

---

### 2.10 src/backtest/rules/evaluation/boolean_ops.py

**NotExpr semantics: CONFIRMED CORRECT** -- eval_not() correctly inverts OK/CONDITION_FAILED/WINDOW_CONDITION_FAILED. True errors propagate unchanged. _ERROR_REASONS frozenset pattern is clean.

---

### 2.11 src/backtest/rules/evaluation/resolve.py

**Division-by-zero: CONFIRMED SAFE** -- evaluate_arithmetic() explicitly handles zero-divisor and overflow. Both documented.

---

### 2.12 src/backtest/rules/evaluation/window_ops.py

**BUG-WIN-001 (MED):** offset_scale = anchor_tf_mins // ACTION_TF_MINUTES at line ~44. If anchor_tf < exec_tf, offset_scale=0. All window offsets become 0 -- window looks at bar 0 repeatedly. Silent incorrect behavior. Guard with ValueError.

**BUG-WIN-002 (LOW):** Post-loop count check is dead code. Early-exit return inside the loop handles all termination.

---

### 2.13 src/backtest/rules/evaluation/shift_ops.py

**BUG-SHIFT-001 (MED):** shift_expr() at line ~128 silently returns unshifted SetupRef with comment that compile-time validation handles it. If validation bypassed, SetupRef inside a window evaluates at bar 0 without error. Replace silent return with runtime assertion.

---

### 2.14 src/backtest/rules/dsl_nodes/base.py

**BUG-NODE-001 (LOW):** No offset ceiling validation on FeatureRef. offset=999999 silently returns MISSING. DSL validator should check offset <= WINDOW_BARS_CEILING.

---

### 2.15 src/backtest/rules/dsl_nodes/windows.py

**Validation: CONFIRMED CORRECT** -- bars >= 1, bars <= 500, duration ceiling 24h (1440 min), min_true in [1, bars]. All enforced at construction.

---

### 2.16 src/backtest/play/play.py

**Module role:** Play dataclass -- complete strategy configuration container.

**BUG-PLAY-001 (MED): tf: exec in feature config NOT resolved to concrete TF**

_parse_features() at line ~698 has explicit guard: feature_tf != "exec".

This skips resolution for the exec role. Feature retains literal string "exec" which fails to match any timeframe buffer in the snapshot at runtime.

Fix: Remove the != "exec" guard and add explicit resolution: if feature_tf == "exec": feature_tf = play.exec_tf

**BUG-PLAY-002 (MED):** Unrecognized condition keys only warned in _convert_shorthand_conditions(). Typo like near_pects: 5 silently dropped. Silent tolerance drops are correctness risks. Raise DSLParseError.

**BUG-PLAY-005 (LOW):** peek_play_yaml() direction detection uses string scan of actions dict repr. Fails for list-format actions. Use recursive walk.

---

### 2.17 src/backtest/play/config_models.py

**BUG-CFG-001 (MED): max_drawdown_pct format inconsistency**

AccountConfig.from_dict() auto-converts default 0.20 from defaults.yml to 20.0 (percentage) via < 1.0 threshold. User-supplied max_drawdown_pct: 0.25 is NOT converted -- account halts at 0.25% drawdown instead of 25%.

Fix: Apply same < 1.0 conversion to user values, or enforce percentage-only format (>= 1.0) with explicit error.

---

### 2.18 src/backtest/play/risk_model.py

**BUG-RISK-001 (MED): Legacy atr_key fallback in StopLossRule (ALL FORWARD, NO LEGACY violation)**

StopLossRule.from_dict() at line ~181: atr_feature_id=d.get("atr_feature_id") or d.get("atr_key"). Silent fallback to legacy atr_key masks typos.

**BUG-RISK-002 (MED):** Same legacy atr_key fallback in TakeProfitRule.from_dict() at line ~224.

Fix both: Remove or d.get("atr_key"). Raise ValueError when atr_feature_id absent if required.

---

### 2.19 src/backtest/execution_validation.py

**Module role:** Play contract validation -- exit mode compatibility, feature ref extraction.

**BUG-EXEC-001 (CRITICAL): Wrong attribute name -- exit actions in else blocks never detected**

_play_has_exit_actions() at line ~213 checks action_block.else_clause but Block dataclass uses else_emit. This attribute does not exist on Block.

hasattr(action_block, else_clause) always returns False. Exit actions in the else: branch of any block are NEVER detected.

Impact: A play using ExitMode.SIGNAL or FIRST_HIT with exit actions exclusively in else: branches passes contract validation incorrectly. The exit mode guarantee is silently broken.

Fix: Change else_clause to else_emit at lines ~213 and ~214.

**BUG-EXEC-002 (MED): Duration window nodes not walked in extract_rule_feature_refs()**

isinstance check at line ~492 covers: HoldsFor, OccurredWithin, CountTrue.
Missing: HoldsForDuration, OccurredWithinDuration, CountTrueDuration.

Feature refs inside duration-based windows invisible to warmup calculation. Under-estimates required warmup bars.

---

### 2.20 src/backtest/play_yaml_builder.py

**BUG-YAML-001 (MED):** build_scope_mappings() directly imports and inspects pandas_ta to check indicator existence. Couples builder to specific library. Fails if not installed. Use the project indicator registry instead.

---

### 2.21 src/backtest/feature_registry.py

**BUG-FREG-001 (MED): Silent 50-bar warmup default (ALL FORWARD, NO LEGACY violation)**

get_warmup_for_tf() at line ~502: except Exception: return 50. Silently returns 50 bars when indicator lookup fails. Masks misconfigured features. Should re-raise or raise ValueError.

**BUG-FREG-002 (LOW):** expand_indicator_outputs() at line ~563 catches broad exceptions and keeps original feature silently. Should log at ERROR level.

---

## 3. Cross-Module Dependency Map

Key call flows through the DSL/play domain:

```
play.py (_parse_*)
  -> dsl_parser.py            parse_condition(), parse_condition_shorthand()
  -> dsl_validator.py         validate_play_references()
  -> feature_registry.py      get_warmup_for_tf(), expand_indicator_outputs()
  -> play/config_models.py    AccountConfig.from_dict()
  -> play/risk_model.py       StopLossRule.from_dict(), TakeProfitRule.from_dict()

dsl_parser.py
  -> dsl_nodes/               Cond, AllExpr, AnyExpr, HoldsFor, ...
  -> registry.py              validate_operator(), is_operator_supported()

execution_validation.py
  -> strategy_blocks.py       Block, Case, Intent, BlockSet
  -> dsl_nodes/               SetupRef, FeatureRef, HoldsFor, duration variants
  -> feature_registry.py      feature metadata for warmup calculation

ExprEvaluator (evaluation/core.py)
  -> evaluation/condition_ops.py   eval_cond() per operator
  -> evaluation/boolean_ops.py     AllExpr/AnyExpr/NotExpr
  -> evaluation/window_ops.py      HoldsFor/OccurredWithin/CountTrue
        -> evaluation/shift_ops.py     FeatureRef.shifted(offset) for lookback
  -> evaluation/resolve.py         resolve_ref(), evaluate_arithmetic()
  -> eval.py                       operator implementations
```

Known mismatches (bugs):
- registry.py is stale vs eval.py: 4 operators implemented but not registered (BUG-REG-001)
- evaluation/core.py expects setup cache populated by engine, but no population API exists (BUG-CORE-002)
- execution_validation.py uses wrong attribute name for Block.else_emit (BUG-EXEC-001)

---

## 4. Summary of Findings

### Critical (Must Fix)

| ID | File | Line | Issue |
|----|------|------|-------|
| BUG-REG-001 | registry.py | 52 | near_pct, near_abs, between, in missing from OPERATOR_REGISTRY |
| BUG-CORE-002 | evaluation/core.py | 92 | _setup_expr_cache never populated -- all setup: references fail at runtime |
| BUG-EXEC-001 | execution_validation.py | 213 | else_clause typo (correct: else_emit) -- exit actions in else blocks never detected |

### High (Should Fix)

| ID | File | Line | Issue |
|----|------|------|-------|
| BUG-SB-001 | strategy_blocks.py | 256 | No conflict resolution when entry+exit both fire same bar |
| BUG-CORE-001 | evaluation/core.py | 92 | ExprEvaluator claims thread-safe but has mutable instance state |

### Medium (Fix Before Release)

| ID | File | Line | Issue |
|----|------|------|-------|
| BUG-SB-002 | strategy_blocks.py | 71 | Intent action not validated against VALID_ACTIONS |
| BUG-DSL-001 | dsl_parser.py | ~289 | Missing expr key in window operator gives cryptic error |
| BUG-COMP-003 | compile.py | ~301 | Structure field validation deferred to runtime |
| BUG-WIN-001 | window_ops.py | ~44 | offset_scale can be 0 when anchor_tf < exec_tf |
| BUG-SHIFT-001 | shift_ops.py | ~128 | SetupRef in shift_expr silently returns unshifted |
| BUG-PLAY-001 | play.py | ~698 | tf: exec in feature config not resolved to concrete TF |
| BUG-PLAY-002 | play.py | ~349 | Unrecognized condition keys only warned, not rejected |
| BUG-CFG-001 | config_models.py | ~183 | max_drawdown_pct: 0.25 silently becomes 0.25% not 25% |
| BUG-RISK-001 | risk_model.py | ~181 | Legacy atr_key fallback in StopLossRule violates ALL FORWARD NO LEGACY |
| BUG-RISK-002 | risk_model.py | ~224 | Same legacy atr_key fallback in TakeProfitRule |
| BUG-EXEC-002 | execution_validation.py | ~492 | Duration-based window nodes not walked for feature ref extraction |
| BUG-YAML-001 | play_yaml_builder.py | ~80 | pandas_ta library coupled directly into builder |
| BUG-FREG-001 | feature_registry.py | ~502 | Silent 50-bar warmup default violates ALL FORWARD NO LEGACY |
| BUG-COND-001 | condition_ops.py | ~148 | Higher-TF RHS shift uses exec-bar offset, not higher-TF-bar offset |

### Low (Clean Up)

| ID | File | Issue |
|----|------|-------|
| BUG-DSL-003 | dsl_parser.py | import re inside function body |
| BUG-EVAL-002 | eval.py | ValueType.NUMERIC dead enum value never produced |
| BUG-TYPES-001 | types.py | import math inside hot-path function |
| BUG-VAL-001 | dsl_validator.py | Accesses private registry._features |
| BUG-COMP-001 | compile.py | Dead legacy code using old dict format |
| BUG-WIN-002 | window_ops.py | Post-loop count check is dead code |
| BUG-NODE-001 | dsl_nodes/base.py | No offset ceiling validation on FeatureRef |
| BUG-FREG-002 | feature_registry.py | Silent exception in expand_indicator_outputs |
| BUG-PLAY-005 | play.py | peek_play_yaml direction detection fragile for list-format actions |

## 5. Positive Observations

- **near_pct double-divide is fully fixed.** The fix in MEMORY.md is correctly applied across all parse paths. Evaluator receives proper ratios.
- **Cross-above/cross-below first-bar is safe.** MISSING_PREV_VALUE returned correctly on first bar, preventing false signals.
- **ArithmeticExpr division-by-zero is handled.** Zero-divisor and overflow both guarded in resolve.py.
- **Window bar bounds are validated.** HoldsFor/OccurredWithin/CountTrue all validate bars >= 1 and bars <= 500 at construction.
- **Circular setup detection is correct.** Standard DFS with three-color marking properly implemented.
- **NotExpr semantics are correct.** Error propagation through negation correctly distinguished from condition inversion.
- **Frozen dataclasses everywhere.** AST node layer is immutable, preventing accidental mutation during evaluation.
- **Incremental O(1) evaluation.** The shift_expr mechanism correctly creates offset AST copies without re-parsing.

---

## 6. Validation Recommendation
```bash
# After addressing critical bugs:
python trade_cli.py validate quick

# After BUG-CORE-002 fix (setup cache):
python trade_cli.py validate module --module G4  # core conditions gate

# After BUG-EXEC-001 fix (else_emit):
python trade_cli.py validate module --module G5  # exit mode validation gate

# After BUG-REG-001 fix (operator registry):
python trade_cli.py validate module --module G3  # DSL operator gate

# Full suite after all fixes:
python trade_cli.py validate standard
```
