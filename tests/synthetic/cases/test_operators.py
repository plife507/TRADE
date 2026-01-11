"""
DSL Operator validation tests.

Validates:
1. Comparison operators (gt, lt, gte, lte, eq)
2. Range operators (between, near_abs, near_pct, in)
3. Crossover operators (cross_above, cross_below)
4. Boolean logic (all, any, not)
5. Window operators (holds_for, occurred_within, count_true)

Per TEST COVERAGE RULE: Tests symmetric behavior for crossover operators.
"""

import pytest

from tests.synthetic.harness.snapshot import SyntheticSnapshot
from src.backtest.rules.evaluation import ExprEvaluator
from src.backtest.rules.dsl_nodes import (
    Cond,
    FeatureRef,
    ScalarValue,
    RangeValue,
    ListValue,
    AllExpr,
    AnyExpr,
    NotExpr,
    HoldsFor,
    OccurredWithin,
    CountTrue,
)
from src.backtest.rules.types import ReasonCode


# ─────────────────────────────────────────────────────────────────────────────
# Test fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def evaluator() -> ExprEvaluator:
    """DSL expression evaluator."""
    return ExprEvaluator(max_window_bars=100)


# ─────────────────────────────────────────────────────────────────────────────
# Comparison Operators (gt, lt, gte, lte, eq)
# ─────────────────────────────────────────────────────────────────────────────

class TestComparisonOperators:
    """Test comparison operators: gt, lt, gte, lte, eq."""

    @pytest.mark.parametrize("lhs_val,op,rhs_val,expected", [
        # gt - greater than
        (51.0, "gt", 50.0, True),
        (50.0, "gt", 50.0, False),   # Equal is NOT greater
        (49.0, "gt", 50.0, False),

        # lt - less than
        (49.0, "lt", 50.0, True),
        (50.0, "lt", 50.0, False),   # Equal is NOT less
        (51.0, "lt", 50.0, False),

        # gte - greater or equal
        (51.0, "gte", 50.0, True),
        (50.0, "gte", 50.0, True),   # Equal counts
        (49.0, "gte", 50.0, False),

        # lte - less or equal
        (49.0, "lte", 50.0, True),
        (50.0, "lte", 50.0, True),   # Equal counts
        (51.0, "lte", 50.0, False),
    ])
    def test_numeric_comparisons(
        self,
        evaluator: ExprEvaluator,
        lhs_val: float,
        op: str,
        rhs_val: float,
        expected: bool,
    ):
        """Test numeric comparison operators."""
        snapshot = SyntheticSnapshot.with_features({"val": lhs_val})
        cond = Cond(
            lhs=FeatureRef(feature_id="val"),
            op=op,
            rhs=ScalarValue(rhs_val),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok == expected

    def test_eq_with_integer(self, evaluator: ExprEvaluator):
        """eq operator works with integers."""
        snapshot = SyntheticSnapshot.with_features({"trend": 1})
        cond = Cond(
            lhs=FeatureRef(feature_id="trend"),
            op="eq",
            rhs=ScalarValue(1),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

        # Not equal
        cond_ne = Cond(
            lhs=FeatureRef(feature_id="trend"),
            op="eq",
            rhs=ScalarValue(2),
        )
        result_ne = evaluator.evaluate(cond_ne, snapshot)
        assert result_ne.ok is False

    def test_eq_with_boolean(self, evaluator: ExprEvaluator):
        """eq operator works with booleans."""
        snapshot = SyntheticSnapshot.with_features({"is_valid": True})
        cond = Cond(
            lhs=FeatureRef(feature_id="is_valid"),
            op="eq",
            rhs=ScalarValue(True),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_eq_with_string_enum(self, evaluator: ExprEvaluator):
        """eq operator works with string enums."""
        snapshot = SyntheticSnapshot.with_features({"state": "active"})
        cond = Cond(
            lhs=FeatureRef(feature_id="state"),
            op="eq",
            rhs=ScalarValue("active"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_eq_rejects_float(self, evaluator: ExprEvaluator):
        """eq operator rejects float values (use near_abs/near_pct instead)."""
        snapshot = SyntheticSnapshot.with_features({"rsi_14": 50.0})
        cond = Cond(
            lhs=FeatureRef(feature_id="rsi_14"),
            op="eq",
            rhs=ScalarValue(50.0),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is False
        assert result.reason == ReasonCode.FLOAT_EQUALITY

    def test_missing_lhs_returns_failure(self, evaluator: ExprEvaluator):
        """Missing LHS value returns failure with proper reason."""
        snapshot = SyntheticSnapshot()
        cond = Cond(
            lhs=FeatureRef(feature_id="nonexistent"),
            op="gt",
            rhs=ScalarValue(50.0),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is False
        assert result.reason == ReasonCode.MISSING_LHS


# ─────────────────────────────────────────────────────────────────────────────
# Range Operators (between, near_abs, near_pct, in)
# ─────────────────────────────────────────────────────────────────────────────

class TestRangeOperators:
    """Test range operators: between, near_abs, near_pct, in."""

    @pytest.mark.parametrize("val,low,high,expected", [
        (50.0, 40.0, 60.0, True),   # Inside
        (40.0, 40.0, 60.0, True),   # On lower bound (inclusive)
        (60.0, 40.0, 60.0, True),   # On upper bound (inclusive)
        (39.9, 40.0, 60.0, False),  # Below
        (60.1, 40.0, 60.0, False),  # Above
    ])
    def test_between(
        self,
        evaluator: ExprEvaluator,
        val: float,
        low: float,
        high: float,
        expected: bool,
    ):
        """Test between operator: low <= val <= high."""
        snapshot = SyntheticSnapshot.with_features({"rsi_14": val})
        cond = Cond(
            lhs=FeatureRef(feature_id="rsi_14"),
            op="between",
            rhs=RangeValue(low=low, high=high),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok == expected

    @pytest.mark.parametrize("val,target,tolerance,expected", [
        (50.5, 50.0, 1.0, True),    # Within 1.0
        (51.0, 50.0, 1.0, True),    # Exactly at tolerance
        (51.1, 50.0, 1.0, False),   # Just outside
        (49.0, 50.0, 1.0, True),    # Below target, within tolerance
        (48.9, 50.0, 1.0, False),   # Below target, outside tolerance
    ])
    def test_near_abs(
        self,
        evaluator: ExprEvaluator,
        val: float,
        target: float,
        tolerance: float,
        expected: bool,
    ):
        """Test near_abs operator: |val - target| <= tolerance."""
        snapshot = SyntheticSnapshot.with_features({"price": val})
        cond = Cond(
            lhs=FeatureRef(feature_id="price"),
            op="near_abs",
            rhs=ScalarValue(target),
            tolerance=tolerance,
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok == expected

    @pytest.mark.parametrize("val,target,pct,expected", [
        (50.5, 50.0, 0.02, True),   # 1% diff, 2% allowed
        (51.0, 50.0, 0.02, True),   # 2% diff, 2% allowed
        (51.5, 50.0, 0.02, False),  # 3% diff, 2% allowed
        (49.0, 50.0, 0.02, True),   # 2% diff, 2% allowed
        (48.5, 50.0, 0.02, False),  # 3% diff, 2% allowed
    ])
    def test_near_pct(
        self,
        evaluator: ExprEvaluator,
        val: float,
        target: float,
        pct: float,
        expected: bool,
    ):
        """Test near_pct operator: |val - target| / |target| <= pct."""
        snapshot = SyntheticSnapshot.with_features({"price": val})
        cond = Cond(
            lhs=FeatureRef(feature_id="price"),
            op="near_pct",
            rhs=ScalarValue(target),
            tolerance=pct,
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok == expected

    def test_in_operator_string(self, evaluator: ExprEvaluator):
        """Test in operator with string values."""
        snapshot = SyntheticSnapshot.with_features({"state": "active"})

        # In list
        cond_in = Cond(
            lhs=FeatureRef(feature_id="state"),
            op="in",
            rhs=ListValue(("active", "pending")),
        )
        result_in = evaluator.evaluate(cond_in, snapshot)
        assert result_in.ok is True

        # Not in list
        cond_not_in = Cond(
            lhs=FeatureRef(feature_id="state"),
            op="in",
            rhs=ListValue(("broken", "expired")),
        )
        result_not_in = evaluator.evaluate(cond_not_in, snapshot)
        assert result_not_in.ok is False

    def test_in_operator_integer(self, evaluator: ExprEvaluator):
        """Test in operator with integer values."""
        snapshot = SyntheticSnapshot.with_features({"trend": 1})
        cond = Cond(
            lhs=FeatureRef(feature_id="trend"),
            op="in",
            rhs=ListValue((1, -1)),  # Valid trend directions
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True


# ─────────────────────────────────────────────────────────────────────────────
# Crossover Operators (cross_above, cross_below)
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossoverOperators:
    """Test crossover operators: cross_above, cross_below."""

    def test_cross_above_basic(self, evaluator: ExprEvaluator):
        """EMA9 crosses above EMA21."""
        snapshot = SyntheticSnapshot.with_history({
            "ema_9":  [49.0, 51.0],   # prev=49, curr=51
            "ema_21": [50.0, 50.0],   # constant at 50
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="ema_9"),
            op="cross_above",
            rhs=FeatureRef(feature_id="ema_21"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_cross_above_exact_touch(self, evaluator: ExprEvaluator):
        """Exact touch on prev bar still counts as cross."""
        snapshot = SyntheticSnapshot.with_history({
            "ema_9":  [50.0, 51.0],   # prev=50 (equal), curr=51
            "ema_21": [50.0, 50.0],
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="ema_9"),
            op="cross_above",
            rhs=FeatureRef(feature_id="ema_21"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True  # prev <= rhs AND curr > rhs

    def test_cross_above_already_above(self, evaluator: ExprEvaluator):
        """Already above = no cross."""
        snapshot = SyntheticSnapshot.with_history({
            "ema_9":  [51.0, 52.0],   # Both bars above
            "ema_21": [50.0, 50.0],
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="ema_9"),
            op="cross_above",
            rhs=FeatureRef(feature_id="ema_21"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is False

    def test_cross_above_still_below(self, evaluator: ExprEvaluator):
        """Moving up but still below = no cross."""
        snapshot = SyntheticSnapshot.with_history({
            "ema_9":  [48.0, 49.0],   # Rising but still < 50
            "ema_21": [50.0, 50.0],
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="ema_9"),
            op="cross_above",
            rhs=FeatureRef(feature_id="ema_21"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is False

    def test_cross_below_basic(self, evaluator: ExprEvaluator):
        """EMA9 crosses below EMA21."""
        snapshot = SyntheticSnapshot.with_history({
            "ema_9":  [51.0, 49.0],   # prev=51, curr=49
            "ema_21": [50.0, 50.0],
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="ema_9"),
            op="cross_below",
            rhs=FeatureRef(feature_id="ema_21"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_cross_below_exact_touch(self, evaluator: ExprEvaluator):
        """Exact touch on prev bar still counts as cross below."""
        snapshot = SyntheticSnapshot.with_history({
            "ema_9":  [50.0, 49.0],   # prev=50 (equal), curr=49
            "ema_21": [50.0, 50.0],
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="ema_9"),
            op="cross_below",
            rhs=FeatureRef(feature_id="ema_21"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True  # prev >= rhs AND curr < rhs

    def test_cross_below_already_below(self, evaluator: ExprEvaluator):
        """Already below = no cross."""
        snapshot = SyntheticSnapshot.with_history({
            "ema_9":  [48.0, 47.0],   # Both bars below
            "ema_21": [50.0, 50.0],
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="ema_9"),
            op="cross_below",
            rhs=FeatureRef(feature_id="ema_21"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is False

    def test_cross_above_scalar_rhs(self, evaluator: ExprEvaluator):
        """Cross above a scalar threshold."""
        snapshot = SyntheticSnapshot.with_history({
            "rsi_14": [68.0, 72.0],   # Crosses above 70
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="rsi_14"),
            op="cross_above",
            rhs=ScalarValue(70.0),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_cross_below_scalar_rhs(self, evaluator: ExprEvaluator):
        """Cross below a scalar threshold."""
        snapshot = SyntheticSnapshot.with_history({
            "rsi_14": [32.0, 28.0],   # Crosses below 30
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="rsi_14"),
            op="cross_below",
            rhs=ScalarValue(30.0),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True


# ─────────────────────────────────────────────────────────────────────────────
# Boolean Logic (all, any, not)
# ─────────────────────────────────────────────────────────────────────────────

class TestBooleanLogic:
    """Test boolean logic: all, any, not."""

    def test_all_both_true(self, evaluator: ExprEvaluator):
        """all: Both conditions true = True."""
        snapshot = SyntheticSnapshot.with_features({
            "rsi_14": 60.0,
            "ema_9": 52.0,
        })
        expr = AllExpr((
            Cond(lhs=FeatureRef(feature_id="rsi_14"), op="gt", rhs=ScalarValue(50.0)),
            Cond(lhs=FeatureRef(feature_id="ema_9"), op="gt", rhs=ScalarValue(50.0)),
        ))
        result = evaluator.evaluate(expr, snapshot)
        assert result.ok is True

    def test_all_short_circuit(self, evaluator: ExprEvaluator):
        """all: Returns False on first False."""
        snapshot = SyntheticSnapshot.with_features({
            "a": 40.0,  # < 50
            "b": 60.0,  # > 50
        })
        expr = AllExpr((
            Cond(lhs=FeatureRef(feature_id="a"), op="gt", rhs=ScalarValue(50.0)),  # False
            Cond(lhs=FeatureRef(feature_id="b"), op="gt", rhs=ScalarValue(50.0)),  # True (not evaluated)
        ))
        result = evaluator.evaluate(expr, snapshot)
        assert result.ok is False

    def test_any_first_true(self, evaluator: ExprEvaluator):
        """any: First true = True (short-circuit)."""
        snapshot = SyntheticSnapshot.with_features({
            "a": 60.0,  # > 50
            "b": 40.0,  # < 50
        })
        expr = AnyExpr((
            Cond(lhs=FeatureRef(feature_id="a"), op="gt", rhs=ScalarValue(50.0)),  # True
            Cond(lhs=FeatureRef(feature_id="b"), op="gt", rhs=ScalarValue(50.0)),  # False (not evaluated)
        ))
        result = evaluator.evaluate(expr, snapshot)
        assert result.ok is True

    def test_any_all_false(self, evaluator: ExprEvaluator):
        """any: All conditions false = False."""
        snapshot = SyntheticSnapshot.with_features({
            "a": 40.0,
            "b": 30.0,
        })
        expr = AnyExpr((
            Cond(lhs=FeatureRef(feature_id="a"), op="gt", rhs=ScalarValue(50.0)),
            Cond(lhs=FeatureRef(feature_id="b"), op="gt", rhs=ScalarValue(50.0)),
        ))
        result = evaluator.evaluate(expr, snapshot)
        assert result.ok is False

    def test_not_inverts_true(self, evaluator: ExprEvaluator):
        """not: Inverts True to False."""
        snapshot = SyntheticSnapshot.with_features({"rsi_14": 60.0})
        expr = NotExpr(
            Cond(lhs=FeatureRef(feature_id="rsi_14"), op="gt", rhs=ScalarValue(50.0))
        )
        result = evaluator.evaluate(expr, snapshot)
        assert result.ok is False

    def test_not_inverts_false(self, evaluator: ExprEvaluator):
        """not: Inverts False to True."""
        snapshot = SyntheticSnapshot.with_features({"rsi_14": 40.0})
        expr = NotExpr(
            Cond(lhs=FeatureRef(feature_id="rsi_14"), op="gt", rhs=ScalarValue(50.0))
        )
        result = evaluator.evaluate(expr, snapshot)
        assert result.ok is True

    def test_nested_boolean(self, evaluator: ExprEvaluator):
        """(A AND B) OR C."""
        snapshot = SyntheticSnapshot.with_features({
            "a": 60.0,  # > 50 (True)
            "b": 40.0,  # > 50 (False)
            "c": 70.0,  # > 50 (True)
        })
        # (a > 50 AND b > 50) OR (c > 50)
        # = (True AND False) OR True
        # = False OR True
        # = True
        expr = AnyExpr((
            AllExpr((
                Cond(lhs=FeatureRef(feature_id="a"), op="gt", rhs=ScalarValue(50.0)),
                Cond(lhs=FeatureRef(feature_id="b"), op="gt", rhs=ScalarValue(50.0)),
            )),
            Cond(lhs=FeatureRef(feature_id="c"), op="gt", rhs=ScalarValue(50.0)),
        ))
        result = evaluator.evaluate(expr, snapshot)
        assert result.ok is True


# ─────────────────────────────────────────────────────────────────────────────
# Window Operators (holds_for, occurred_within, count_true)
# ─────────────────────────────────────────────────────────────────────────────

class TestWindowOperators:
    """Test window operators: holds_for, occurred_within, count_true."""

    def test_holds_for_exact(self, evaluator: ExprEvaluator):
        """Condition true for exactly N bars."""
        snapshot = SyntheticSnapshot.with_history({
            "rsi_14": [51, 52, 53, 54, 55],  # 5 bars all > 50
        })
        expr = HoldsFor(
            bars=5,
            expr=Cond(lhs=FeatureRef(feature_id="rsi_14"), op="gt", rhs=ScalarValue(50.0)),
        )
        result = evaluator.evaluate(expr, snapshot)
        assert result.ok is True

    def test_holds_for_broken(self, evaluator: ExprEvaluator):
        """Condition breaks before N bars."""
        snapshot = SyntheticSnapshot.with_history({
            "rsi_14": [55, 52, 48, 53, 54],  # bar at offset 2 = 48 < 50
        })
        expr = HoldsFor(
            bars=5,
            expr=Cond(lhs=FeatureRef(feature_id="rsi_14"), op="gt", rhs=ScalarValue(50.0)),
        )
        result = evaluator.evaluate(expr, snapshot)
        assert result.ok is False

    def test_holds_for_shorter_than_bars(self, evaluator: ExprEvaluator):
        """Condition true for fewer than N bars."""
        snapshot = SyntheticSnapshot.with_history({
            "rsi_14": [55, 52, 51],  # Only 3 bars available
        })
        expr = HoldsFor(
            bars=5,  # Need 5 bars
            expr=Cond(lhs=FeatureRef(feature_id="rsi_14"), op="gt", rhs=ScalarValue(50.0)),
        )
        result = evaluator.evaluate(expr, snapshot)
        # Should fail because we don't have 5 bars of history
        assert result.ok is False

    def test_occurred_within_success(self, evaluator: ExprEvaluator):
        """Condition was true at least once in window."""
        snapshot = SyntheticSnapshot.with_history({
            "rsi_14": [40, 42, 65, 45, 43],  # bar at offset 2 = 65 > 60
        })
        expr = OccurredWithin(
            bars=5,
            expr=Cond(lhs=FeatureRef(feature_id="rsi_14"), op="gt", rhs=ScalarValue(60.0)),
        )
        result = evaluator.evaluate(expr, snapshot)
        assert result.ok is True

    def test_occurred_within_failure(self, evaluator: ExprEvaluator):
        """Condition never true in window."""
        snapshot = SyntheticSnapshot.with_history({
            "rsi_14": [40, 42, 45, 48, 43],  # All < 60
        })
        expr = OccurredWithin(
            bars=5,
            expr=Cond(lhs=FeatureRef(feature_id="rsi_14"), op="gt", rhs=ScalarValue(60.0)),
        )
        result = evaluator.evaluate(expr, snapshot)
        assert result.ok is False

    def test_count_true_meets_threshold(self, evaluator: ExprEvaluator):
        """Condition true at least N times in window."""
        snapshot = SyntheticSnapshot.with_history({
            "rsi_14": [65, 42, 62, 45, 63],  # 3 bars > 60 at offsets 0, 2, 4
        })
        expr = CountTrue(
            bars=5,
            min_true=3,
            expr=Cond(lhs=FeatureRef(feature_id="rsi_14"), op="gt", rhs=ScalarValue(60.0)),
        )
        result = evaluator.evaluate(expr, snapshot)
        assert result.ok is True

    def test_count_true_below_threshold(self, evaluator: ExprEvaluator):
        """Condition true fewer than N times in window."""
        snapshot = SyntheticSnapshot.with_history({
            "rsi_14": [65, 42, 45, 45, 63],  # Only 2 bars > 60 at offsets 0, 4
        })
        expr = CountTrue(
            bars=5,
            min_true=3,
            expr=Cond(lhs=FeatureRef(feature_id="rsi_14"), op="gt", rhs=ScalarValue(60.0)),
        )
        result = evaluator.evaluate(expr, snapshot)
        assert result.ok is False


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Test edge cases and type safety."""

    def test_feature_with_field(self, evaluator: ExprEvaluator):
        """Access feature with specific field."""
        snapshot = SyntheticSnapshot.with_features({
            "swing.high_level": 100.0,
            "swing.low_level": 80.0,
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="swing", field="high_level"),
            op="gt",
            rhs=ScalarValue(90.0),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_feature_comparison(self, evaluator: ExprEvaluator):
        """Compare two features."""
        snapshot = SyntheticSnapshot.with_features({
            "ema_9": 52.0,
            "ema_21": 50.0,
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="ema_9"),
            op="gt",
            rhs=FeatureRef(feature_id="ema_21"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_zero_tolerance_near_abs(self, evaluator: ExprEvaluator):
        """Zero tolerance is exact equality."""
        snapshot = SyntheticSnapshot.with_features({"price": 50.0})
        cond = Cond(
            lhs=FeatureRef(feature_id="price"),
            op="near_abs",
            rhs=ScalarValue(50.0),
            tolerance=0.0,
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

        cond_ne = Cond(
            lhs=FeatureRef(feature_id="price"),
            op="near_abs",
            rhs=ScalarValue(50.1),
            tolerance=0.0,
        )
        result_ne = evaluator.evaluate(cond_ne, snapshot)
        assert result_ne.ok is False

    def test_crossover_missing_prev(self, evaluator: ExprEvaluator):
        """Crossover with no previous bar fails gracefully."""
        snapshot = SyntheticSnapshot.with_features({
            "ema_9": 52.0,  # No history
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="ema_9"),
            op="cross_above",
            rhs=ScalarValue(50.0),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is False
        assert result.reason == ReasonCode.MISSING_PREV_VALUE

    def test_infinity_lhs_treated_as_missing(self, evaluator: ExprEvaluator):
        """Positive infinity in LHS is treated as missing."""
        snapshot = SyntheticSnapshot.with_features({
            "val": float("inf"),
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="val"),
            op="gt",
            rhs=ScalarValue(50.0),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is False
        assert result.reason == ReasonCode.MISSING_LHS

    def test_negative_infinity_lhs_treated_as_missing(self, evaluator: ExprEvaluator):
        """Negative infinity in LHS is treated as missing."""
        snapshot = SyntheticSnapshot.with_features({
            "val": float("-inf"),
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="val"),
            op="lt",
            rhs=ScalarValue(50.0),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is False
        assert result.reason == ReasonCode.MISSING_LHS

    def test_infinity_rhs_treated_as_missing(self, evaluator: ExprEvaluator):
        """Infinity in RHS is treated as missing."""
        snapshot = SyntheticSnapshot.with_features({
            "lhs_val": 100.0,
            "rhs_val": float("inf"),
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="lhs_val"),
            op="gt",
            rhs=FeatureRef(feature_id="rhs_val"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is False
        assert result.reason == ReasonCode.MISSING_RHS

    def test_nan_lhs_treated_as_missing(self, evaluator: ExprEvaluator):
        """NaN in LHS is treated as missing."""
        snapshot = SyntheticSnapshot.with_features({
            "val": float("nan"),
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="val"),
            op="gt",
            rhs=ScalarValue(50.0),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is False
        assert result.reason == ReasonCode.MISSING_LHS
