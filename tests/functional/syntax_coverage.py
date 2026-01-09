"""
DSL Syntax Coverage Matrix.

Tests typical and atypical/edge case syntax patterns to ensure the DSL
parser and evaluator handle all valid syntax variations correctly.

Organized into two categories:
1. TYPICAL: Common, expected syntax patterns
2. EDGE_CASE: Boundary conditions, unusual but valid syntax
"""

from dataclasses import dataclass
from enum import Enum


class SyntaxCategory(Enum):
    """Category of syntax test."""
    TYPICAL = "typical"
    EDGE_CASE = "edge_case"


@dataclass
class SyntaxTest:
    """Definition of a syntax test case."""
    name: str
    category: SyntaxCategory
    description: str
    features: dict[str, dict]  # Feature declarations needed
    condition: str | dict  # The condition to test (string or dict)
    should_pass: bool = True  # Whether this syntax should be accepted
    notes: str = ""


# =============================================================================
# TYPICAL SYNTAX PATTERNS
# =============================================================================

TYPICAL_SYNTAX = {
    # ----- Basic Comparisons -----
    "T_001_simple_gt": SyntaxTest(
        name="T_001_simple_gt",
        category=SyntaxCategory.TYPICAL,
        description="Simple greater-than with literal",
        features={"rsi_14": {"indicator": "rsi", "params": {"length": 14}}},
        condition='["rsi_14", "gt", 50]',
    ),
    "T_002_simple_lt": SyntaxTest(
        name="T_002_simple_lt",
        category=SyntaxCategory.TYPICAL,
        description="Simple less-than with literal",
        features={"rsi_14": {"indicator": "rsi", "params": {"length": 14}}},
        condition='["rsi_14", "lt", 30]',
    ),
    "T_003_feature_vs_feature": SyntaxTest(
        name="T_003_feature_vs_feature",
        category=SyntaxCategory.TYPICAL,
        description="Compare two features",
        features={
            "ema_9": {"indicator": "ema", "params": {"length": 9}},
            "ema_21": {"indicator": "ema", "params": {"length": 21}},
        },
        condition='["ema_9", "gt", "ema_21"]',
    ),

    # ----- Crossover Patterns -----
    "T_010_cross_above_feature": SyntaxTest(
        name="T_010_cross_above_feature",
        category=SyntaxCategory.TYPICAL,
        description="Cross above another feature",
        features={
            "ema_9": {"indicator": "ema", "params": {"length": 9}},
            "ema_21": {"indicator": "ema", "params": {"length": 21}},
        },
        condition='["ema_9", "cross_above", "ema_21"]',
    ),
    "T_011_cross_above_literal": SyntaxTest(
        name="T_011_cross_above_literal",
        category=SyntaxCategory.TYPICAL,
        description="Cross above literal value (zero-line cross)",
        features={"macd_12_26_9": {"indicator": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}}},
        condition='[{"feature_id": "macd_12_26_9", "field": "histogram"}, "cross_above", 0]',
    ),
    "T_012_cross_below_feature": SyntaxTest(
        name="T_012_cross_below_feature",
        category=SyntaxCategory.TYPICAL,
        description="Cross below another feature",
        features={
            "ema_9": {"indicator": "ema", "params": {"length": 9}},
            "ema_21": {"indicator": "ema", "params": {"length": 21}},
        },
        condition='["ema_9", "cross_below", "ema_21"]',
    ),

    # ----- Field Accessor Syntax -----
    "T_020_field_accessor_basic": SyntaxTest(
        name="T_020_field_accessor_basic",
        category=SyntaxCategory.TYPICAL,
        description="Multi-output indicator field accessor",
        features={"macd_12_26_9": {"indicator": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}}},
        condition='[{"feature_id": "macd_12_26_9", "field": "macd"}, "gt", 0]',
    ),
    "T_021_field_accessor_both_sides": SyntaxTest(
        name="T_021_field_accessor_both_sides",
        category=SyntaxCategory.TYPICAL,
        description="Field accessors on both LHS and RHS",
        features={"macd_12_26_9": {"indicator": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}}},
        condition='[{"feature_id": "macd_12_26_9", "field": "macd"}, "cross_above", {"feature_id": "macd_12_26_9", "field": "signal"}]',
    ),

    # ----- Boolean Logic -----
    "T_030_all_two_conditions": SyntaxTest(
        name="T_030_all_two_conditions",
        category=SyntaxCategory.TYPICAL,
        description="all: with two conditions",
        features={
            "rsi_14": {"indicator": "rsi", "params": {"length": 14}},
            "ema_21": {"indicator": "ema", "params": {"length": 21}},
        },
        condition={
            "all": [
                '["rsi_14", "lt", 30]',
                '["close", "gt", "ema_21"]',
            ]
        },
    ),
    "T_031_any_two_conditions": SyntaxTest(
        name="T_031_any_two_conditions",
        category=SyntaxCategory.TYPICAL,
        description="any: with two conditions",
        features={
            "rsi_14": {"indicator": "rsi", "params": {"length": 14}},
        },
        condition={
            "any": [
                '["rsi_14", "lt", 30]',
                '["rsi_14", "gt", 70]',
            ]
        },
    ),
    "T_032_nested_all_any": SyntaxTest(
        name="T_032_nested_all_any",
        category=SyntaxCategory.TYPICAL,
        description="Nested all containing any",
        features={
            "rsi_14": {"indicator": "rsi", "params": {"length": 14}},
            "ema_9": {"indicator": "ema", "params": {"length": 9}},
            "ema_21": {"indicator": "ema", "params": {"length": 21}},
        },
        condition={
            "all": [
                '["ema_9", "gt", "ema_21"]',  # Trend filter
                {
                    "any": [
                        '["rsi_14", "lt", 30]',  # Oversold
                        '["rsi_14", "cross_above", 50]',  # Momentum
                    ]
                },
            ]
        },
    ),

    # ----- Between Operator -----
    "T_040_between_literals": SyntaxTest(
        name="T_040_between_literals",
        category=SyntaxCategory.TYPICAL,
        description="Between with literal bounds",
        features={"rsi_14": {"indicator": "rsi", "params": {"length": 14}}},
        condition='["rsi_14", "between", 40, 60]',
    ),

    # ----- Close/Price References -----
    "T_050_close_vs_feature": SyntaxTest(
        name="T_050_close_vs_feature",
        category=SyntaxCategory.TYPICAL,
        description="close price vs feature",
        features={"ema_21": {"indicator": "ema", "params": {"length": 21}}},
        condition='["close", "gt", "ema_21"]',
    ),
    "T_051_close_crossover": SyntaxTest(
        name="T_051_close_crossover",
        category=SyntaxCategory.TYPICAL,
        description="close cross above feature",
        features={"ema_21": {"indicator": "ema", "params": {"length": 21}}},
        condition='["close", "cross_above", "ema_21"]',
    ),
}


# =============================================================================
# EDGE CASE SYNTAX PATTERNS
# =============================================================================

EDGE_CASE_SYNTAX = {
    # ----- Numeric Edge Cases -----
    "E_001_zero_literal": SyntaxTest(
        name="E_001_zero_literal",
        category=SyntaxCategory.EDGE_CASE,
        description="Comparison with zero",
        features={"macd_12_26_9": {"indicator": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}}},
        condition='[{"feature_id": "macd_12_26_9", "field": "histogram"}, "gt", 0]',
    ),
    "E_002_negative_literal": SyntaxTest(
        name="E_002_negative_literal",
        category=SyntaxCategory.EDGE_CASE,
        description="Comparison with negative number",
        features={"macd_12_26_9": {"indicator": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}}},
        condition='[{"feature_id": "macd_12_26_9", "field": "histogram"}, "lt", -0.001]',
    ),
    "E_003_small_decimal": SyntaxTest(
        name="E_003_small_decimal",
        category=SyntaxCategory.EDGE_CASE,
        description="Small decimal literal",
        features={"atr_14": {"indicator": "atr", "params": {"length": 14}}},
        condition='["atr_14", "gt", 0.0001]',
    ),
    "E_004_large_number": SyntaxTest(
        name="E_004_large_number",
        category=SyntaxCategory.EDGE_CASE,
        description="Large number literal",
        features={"close": {}},  # Built-in
        condition='["close", "gt", 100000]',
        notes="For high-value assets like BTC",
    ),

    # ----- Boolean Logic Edge Cases -----
    "E_010_single_item_all": SyntaxTest(
        name="E_010_single_item_all",
        category=SyntaxCategory.EDGE_CASE,
        description="all: with single condition",
        features={"rsi_14": {"indicator": "rsi", "params": {"length": 14}}},
        condition={
            "all": [
                '["rsi_14", "lt", 30]',
            ]
        },
        notes="Single-item all should be valid but unusual",
    ),
    "E_011_single_item_any": SyntaxTest(
        name="E_011_single_item_any",
        category=SyntaxCategory.EDGE_CASE,
        description="any: with single condition",
        features={"rsi_14": {"indicator": "rsi", "params": {"length": 14}}},
        condition={
            "any": [
                '["rsi_14", "lt", 30]',
            ]
        },
    ),
    "E_012_not_operator": SyntaxTest(
        name="E_012_not_operator",
        category=SyntaxCategory.EDGE_CASE,
        description="not: operator",
        features={"rsi_14": {"indicator": "rsi", "params": {"length": 14}}},
        condition={
            "not": '["rsi_14", "gt", 70]'
        },
        notes="Enter when NOT overbought",
    ),
    "E_013_deeply_nested": SyntaxTest(
        name="E_013_deeply_nested",
        category=SyntaxCategory.EDGE_CASE,
        description="Deep nesting: all -> any -> all",
        features={
            "rsi_14": {"indicator": "rsi", "params": {"length": 14}},
            "ema_9": {"indicator": "ema", "params": {"length": 9}},
            "ema_21": {"indicator": "ema", "params": {"length": 21}},
            "atr_14": {"indicator": "atr", "params": {"length": 14}},
        },
        condition={
            "all": [
                '["ema_9", "gt", "ema_21"]',
                {
                    "any": [
                        {
                            "all": [
                                '["rsi_14", "lt", 30]',
                                '["atr_14", "gt", 100]',
                            ]
                        },
                        '["rsi_14", "cross_above", 50]',
                    ]
                },
            ]
        },
    ),

    # ----- Operator Edge Cases -----
    "E_020_gte_boundary": SyntaxTest(
        name="E_020_gte_boundary",
        category=SyntaxCategory.EDGE_CASE,
        description="Greater than or equal at boundary",
        features={"rsi_14": {"indicator": "rsi", "params": {"length": 14}}},
        condition='["rsi_14", "gte", 30]',
        notes="Boundary condition at oversold threshold",
    ),
    "E_021_lte_boundary": SyntaxTest(
        name="E_021_lte_boundary",
        category=SyntaxCategory.EDGE_CASE,
        description="Less than or equal at boundary",
        features={"rsi_14": {"indicator": "rsi", "params": {"length": 14}}},
        condition='["rsi_14", "lte", 70]',
    ),
    "E_022_eq_integer": SyntaxTest(
        name="E_022_eq_integer",
        category=SyntaxCategory.EDGE_CASE,
        description="eq with INT type field",
        features={"supertrend_10_3": {"indicator": "supertrend", "params": {"length": 10, "multiplier": 3.0}}},
        condition='[{"feature_id": "supertrend_10_3", "field": "direction"}, "eq", 1]',
        notes="direction is INT type, eq should work",
    ),

    # ----- Reference Style Variations -----
    "E_030_explicit_literal": SyntaxTest(
        name="E_030_explicit_literal",
        category=SyntaxCategory.EDGE_CASE,
        description="Explicit literal syntax",
        features={"rsi_14": {"indicator": "rsi", "params": {"length": 14}}},
        condition='["rsi_14", "lt", {"literal": 30}]',
        notes="Using {literal: value} instead of bare value",
    ),
    "E_031_mixed_ref_styles": SyntaxTest(
        name="E_031_mixed_ref_styles",
        category=SyntaxCategory.EDGE_CASE,
        description="Mix of string ref and field accessor",
        features={
            "ema_21": {"indicator": "ema", "params": {"length": 21}},
            "bbands_20_2": {"indicator": "bbands", "params": {"length": 20, "std": 2.0}},
        },
        condition='["ema_21", "gt", {"feature_id": "bbands_20_2", "field": "middle"}]',
    ),

    # ----- Window Operators -----
    "E_040_holds_for": SyntaxTest(
        name="E_040_holds_for",
        category=SyntaxCategory.EDGE_CASE,
        description="holds_for window operator",
        features={
            "ema_9": {"indicator": "ema", "params": {"length": 9}},
            "ema_21": {"indicator": "ema", "params": {"length": 21}},
        },
        condition='[["ema_9", "gt", "ema_21"], "holds_for", 3]',
        notes="Condition must hold for 3 bars",
    ),
    "E_041_occurred_within": SyntaxTest(
        name="E_041_occurred_within",
        category=SyntaxCategory.EDGE_CASE,
        description="occurred_within window operator",
        features={
            "ema_9": {"indicator": "ema", "params": {"length": 9}},
            "ema_21": {"indicator": "ema", "params": {"length": 21}},
        },
        condition='[["ema_9", "cross_above", "ema_21"], "occurred_within", 5]',
        notes="Crossover happened in last 5 bars",
    ),

    # ----- Near Operators -----
    "E_050_near_pct": SyntaxTest(
        name="E_050_near_pct",
        category=SyntaxCategory.EDGE_CASE,
        description="near_pct operator",
        features={
            "ema_21": {"indicator": "ema", "params": {"length": 21}},
        },
        condition='["close", "near_pct", "ema_21", 0.5]',
        notes="Within 0.5% of EMA",
    ),
    "E_051_near_abs": SyntaxTest(
        name="E_051_near_abs",
        category=SyntaxCategory.EDGE_CASE,
        description="near_abs operator",
        features={
            "ema_21": {"indicator": "ema", "params": {"length": 21}},
        },
        condition='["close", "near_abs", "ema_21", 100]',
        notes="Within $100 of EMA",
    ),
}


# =============================================================================
# POSITION MODE TESTS
# =============================================================================
#
# SUPPORTED MODES:
#   - long_only: Entry long when no position (TESTED)
#   - short_only: Entry short when no position (TESTING HERE)
#
# FUTURE ENHANCEMENT (NOT YET IMPLEMENTED):
#   - long_short: Bidirectional trading with position flip
#     Requires: Engine enhancement to close existing position before
#     opening opposite direction. Currently entry_short only fires
#     when has_position=False (execution_validation.py:972)
#
# =============================================================================

POSITION_MODE_TESTS = {
    # ----- Short Only Tests -----
    # Tests short_only mode - entry_short when no position exists

    "P_010_short_rsi_overbought": SyntaxTest(
        name="P_010_short_rsi_overbought",
        category=SyntaxCategory.TYPICAL,
        description="Short entry on RSI overbought (> 70)",
        features={"rsi_14": {"indicator": "rsi", "params": {"length": 14}}},
        condition='["rsi_14", "gt", 70]',
        notes="mode: short_only",
    ),
    "P_011_short_ema_death_cross": SyntaxTest(
        name="P_011_short_ema_death_cross",
        category=SyntaxCategory.TYPICAL,
        description="Short entry on EMA death cross",
        features={
            "ema_9": {"indicator": "ema", "params": {"length": 9}},
            "ema_21": {"indicator": "ema", "params": {"length": 21}},
        },
        condition='["ema_9", "cross_below", "ema_21"]',
        notes="mode: short_only",
    ),
    "P_012_short_below_vwap": SyntaxTest(
        name="P_012_short_below_vwap",
        category=SyntaxCategory.TYPICAL,
        description="Short entry when price crosses below VWAP",
        features={"vwap_D": {"indicator": "vwap", "params": {"anchor": "D"}}},
        condition='["close", "cross_below", "vwap_D"]',
        notes="mode: short_only",
    ),
    "P_013_short_supertrend_down": SyntaxTest(
        name="P_013_short_supertrend_down",
        category=SyntaxCategory.TYPICAL,
        description="Short entry when SuperTrend flips bearish (direction crosses below 0)",
        features={"supertrend_10_3": {"indicator": "supertrend", "params": {"length": 10, "multiplier": 3.0}}},
        # Use cross_below to detect transition from bullish to bearish
        # direction: 1 = bullish, -1 = bearish, crossing below 0 = flip to bearish
        condition='[{"feature_id": "supertrend_10_3", "field": "direction"}, "cross_below", 0]',
        notes="mode: short_only - Tests SOL's Sep-Dec 2025 downtrend",
    ),
    "P_014_short_macd_cross_below": SyntaxTest(
        name="P_014_short_macd_cross_below",
        category=SyntaxCategory.TYPICAL,
        description="Short entry when MACD crosses below signal",
        features={"macd_12_26_9": {"indicator": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}}},
        condition='[{"feature_id": "macd_12_26_9", "field": "macd"}, "cross_below", {"feature_id": "macd_12_26_9", "field": "signal"}]',
        notes="mode: short_only",
    ),
}


# =============================================================================
# COMBINED COVERAGE
# =============================================================================

ALL_SYNTAX_TESTS = {
    **TYPICAL_SYNTAX,
    **EDGE_CASE_SYNTAX,
    **POSITION_MODE_TESTS,
}


def get_tests_by_category(category: SyntaxCategory) -> dict[str, SyntaxTest]:
    """Get all tests of a specific category."""
    return {k: v for k, v in ALL_SYNTAX_TESTS.items() if v.category == category}


def get_position_mode_tests() -> dict[str, SyntaxTest]:
    """Get all position mode tests."""
    return POSITION_MODE_TESTS
