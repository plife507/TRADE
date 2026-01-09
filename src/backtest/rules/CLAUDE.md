# Rules Module

DSL compilation and evaluation for Play actions. Extracted 2026-01-08 as part of Cookbook Alignment Refactor.

## Module Structure

```
rules/
├── dsl_nodes/           # DSL node types (extracted from dsl_nodes.py)
│   ├── constants.py     # Operator sets, limits
│   ├── base.py          # FeatureRef, ScalarValue, ArithmeticExpr
│   ├── boolean.py       # AllExpr, AnyExpr, NotExpr, SetupRef
│   ├── condition.py     # Cond class
│   ├── windows.py       # HoldsFor, OccurredWithin, CountTrue
│   ├── types.py         # Expr type alias
│   ├── utils.py         # Utility functions
│   └── __init__.py      # Re-exports all public types
│
├── evaluation/          # Expression evaluator (extracted from dsl_eval.py)
│   ├── core.py          # ExprEvaluator class, state, dispatch
│   ├── boolean_ops.py   # _eval_all, _eval_any, _eval_not
│   ├── condition_ops.py # _eval_cond, _eval_crossover
│   ├── window_ops.py    # holds_for, occurred_within, count_true
│   ├── shift_ops.py     # _shift_expr, _shift_arithmetic
│   ├── resolve.py       # _resolve_ref, _resolve_lhs
│   ├── setups.py        # _eval_setup_ref with caching
│   └── __init__.py      # Re-exports ExprEvaluator
│
├── dsl_parser.py        # Parse YAML → DSL nodes
├── dsl_eval.py          # Re-export shim for backward compatibility
├── dsl_nodes.py         # Re-export shim for backward compatibility
└── compile.py           # Compile DSL into evaluable rules
```

## Import Patterns

All public types are re-exported via `__init__.py` for backward compatibility:

```python
# Both work identically:
from src.backtest.rules.dsl_nodes import FeatureRef, Cond, HoldsFor
from src.backtest.rules.dsl_nodes.base import FeatureRef
from src.backtest.rules.dsl_nodes.condition import Cond
from src.backtest.rules.dsl_nodes.windows import HoldsFor

# Evaluator:
from src.backtest.rules.dsl_eval import ExprEvaluator  # Re-export shim
from src.backtest.rules.evaluation import ExprEvaluator  # Direct import
```

## Key Types

### DSL Nodes

| Type | Module | Purpose |
|------|--------|---------|
| `FeatureRef` | base.py | Reference to indicator/structure field |
| `ScalarValue` | base.py | Literal numeric value |
| `ArithmeticExpr` | base.py | Binary arithmetic expression |
| `Cond` | condition.py | Comparison condition (lhs op rhs) |
| `AllExpr` | boolean.py | Logical AND of expressions |
| `AnyExpr` | boolean.py | Logical OR of expressions |
| `NotExpr` | boolean.py | Logical NOT of expression |
| `SetupRef` | boolean.py | Reference to named setup |
| `HoldsFor` | windows.py | Condition held for N bars |
| `OccurredWithin` | windows.py | Condition occurred in last N bars |
| `CountTrue` | windows.py | Count true evaluations in window |

### Evaluation

| Function | Module | Purpose |
|----------|--------|---------|
| `ExprEvaluator.evaluate()` | core.py | Main entry point for expression evaluation |
| `_eval_cond()` | condition_ops.py | Evaluate single condition |
| `_eval_crossover()` | condition_ops.py | Evaluate cross_above/cross_below |
| `_eval_holds_for()` | window_ops.py | Bar-based window: held for N bars |
| `_eval_occurred_within()` | window_ops.py | Bar-based window: occurred in N bars |
| `_eval_count_true()` | window_ops.py | Count true in window |

## DSL v3.0.0 (FROZEN 2026-01-08)

### Operators

| Operator | Type | Example |
|----------|------|---------|
| `gt`, `lt`, `gte`, `lte` | Numeric comparison | `ema_9 > ema_21` |
| `eq` | Equality (discrete) | `zone.state == "ACTIVE"` |
| `cross_above`, `cross_below` | Crossover | `ema_9 cross_above ema_21` |
| `between` | Range | `rsi_14 between [30, 70]` |
| `near_abs`, `near_pct` | Proximity | `price near_pct ema_50 [2.0]` |
| `in` | Set membership | `zone.state in ["ACTIVE", "BROKEN"]` |

### Window Operators

| Operator | Key | Purpose |
|----------|-----|---------|
| `holds_for` | `bars`, `expr`, `anchor_tf` | Condition held for N bars |
| `occurred_within` | `bars`, `expr`, `anchor_tf` | Condition occurred in last N bars |
| `count_true` | `bars`, `expr`, `min_true`, `anchor_tf` | Count true evaluations |
| `holds_for_duration` | `duration`, `expr` | Duration-based holds |
| `occurred_within_duration` | `duration`, `expr` | Duration-based occurrence |
| `count_true_duration` | `duration`, `expr`, `min_true` | Duration-based count |

**CRITICAL**: Window operators use `expr:` key (not `condition:`). Fixed 2026-01-08.

## Cookbook Alignment

This module aligns with `docs/specs/PLAY_DSL_COOKBOOK.md` (canonical source of truth).

All legacy syntax has been removed:
- `blocks:` → Use `actions:`
- `margin_mode: "isolated"` → Use `isolated_usdt`
- `condition:` in windows → Use `expr:`
