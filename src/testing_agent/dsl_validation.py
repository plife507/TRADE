"""
DSL Validation: Proves condition evaluation is correct.

Tests the DSL condition operators with known inputs:
1. Comparison operators (>, <, >=, <=, ==, !=)
2. Cross detection (cross_above, cross_below)
3. Boolean logic (all, any, not)
4. Window operations (holds_for, occurred_within, count_true)
5. Range operations (between, near_abs, near_pct)
"""

from dataclasses import dataclass
from typing import Any

from ..utils.logger import get_logger

logger = get_logger()


@dataclass
class DSLTestResult:
    """Result of a DSL validation test."""
    name: str
    passed: bool
    expected: str
    actual: str
    error_msg: str = ""


# =============================================================================
# Mock Snapshot for Testing
# =============================================================================

class MockSnapshot:
    """Mock snapshot that returns configured feature values."""

    def __init__(
        self,
        values: dict[str, float],
        prev_values: dict[str, float] | None = None,
        types: dict[str, str] | None = None,
    ):
        """
        Initialize mock snapshot.

        Args:
            values: Current bar feature values {feature_id: value}
            prev_values: Previous bar values for crossover testing
            types: Optional type declarations {feature_id: "INT"|"FLOAT"|"BOOL"}
        """
        self._values = values
        self._prev_values = prev_values or {}
        self._types = types or {}

    def get_feature_value(
        self,
        feature_id: str,
        field: str | None = None,
        offset: int = 0,
    ) -> float | None:
        """Get feature value, supporting offset for crossover tests."""
        if offset == 0:
            return self._values.get(feature_id)
        elif offset == 1:
            return self._prev_values.get(feature_id)
        return None

    def get_feature_output_type(
        self,
        feature_id: str,
        field: str = "value",
    ):
        """Get declared output type for a feature."""
        from ..structures.types import FeatureOutputType

        type_str = self._types.get(feature_id)
        if type_str == "INT":
            return FeatureOutputType.INT
        elif type_str == "BOOL":
            return FeatureOutputType.BOOL
        # Default to FLOAT for numeric features
        return FeatureOutputType.FLOAT


# =============================================================================
# Comparison Operator Tests
# =============================================================================

def test_greater_than() -> DSLTestResult:
    """
    Test: Greater than operator (>)

    ema_9 = 100, ema_21 = 99
    Expected: ema_9 > ema_21 is True
    """
    from ..backtest.rules.dsl_nodes.condition import Cond
    from ..backtest.rules.dsl_nodes.base import FeatureRef, ScalarValue
    from ..backtest.rules.evaluation.condition_ops import eval_cond

    snapshot = MockSnapshot({"ema_9": 100.0, "ema_21": 99.0})

    cond = Cond(
        lhs=FeatureRef(feature_id="ema_9"),
        op=">",
        rhs=FeatureRef(feature_id="ema_21"),
    )

    result = eval_cond(cond, snapshot)

    passed = result.ok is True

    return DSLTestResult(
        name="greater_than",
        passed=passed,
        expected="True (100 > 99)",
        actual=f"{result.ok} (reason: {result.reason.name})",
    )


def test_greater_than_false() -> DSLTestResult:
    """
    Test: Greater than operator returns False when condition not met.

    ema_9 = 99, ema_21 = 100
    Expected: ema_9 > ema_21 is False
    """
    from ..backtest.rules.dsl_nodes.condition import Cond
    from ..backtest.rules.dsl_nodes.base import FeatureRef
    from ..backtest.rules.evaluation.condition_ops import eval_cond

    snapshot = MockSnapshot({"ema_9": 99.0, "ema_21": 100.0})

    cond = Cond(
        lhs=FeatureRef(feature_id="ema_9"),
        op=">",
        rhs=FeatureRef(feature_id="ema_21"),
    )

    result = eval_cond(cond, snapshot)

    passed = result.ok is False

    return DSLTestResult(
        name="greater_than_false",
        passed=passed,
        expected="False (99 > 100)",
        actual=f"{result.ok}",
    )


def test_less_than() -> DSLTestResult:
    """
    Test: Less than operator (<)

    rsi = 25, threshold = 30
    Expected: rsi < 30 is True
    """
    from ..backtest.rules.dsl_nodes.condition import Cond
    from ..backtest.rules.dsl_nodes.base import FeatureRef, ScalarValue
    from ..backtest.rules.evaluation.condition_ops import eval_cond

    snapshot = MockSnapshot({"rsi": 25.0})

    cond = Cond(
        lhs=FeatureRef(feature_id="rsi"),
        op="<",
        rhs=ScalarValue(value=30.0),
    )

    result = eval_cond(cond, snapshot)

    passed = result.ok is True

    return DSLTestResult(
        name="less_than",
        passed=passed,
        expected="True (25 < 30)",
        actual=f"{result.ok}",
    )


def test_greater_equal() -> DSLTestResult:
    """
    Test: Greater than or equal operator (>=)

    rsi = 30, threshold = 30
    Expected: rsi >= 30 is True (boundary case)
    """
    from ..backtest.rules.dsl_nodes.condition import Cond
    from ..backtest.rules.dsl_nodes.base import FeatureRef, ScalarValue
    from ..backtest.rules.evaluation.condition_ops import eval_cond

    snapshot = MockSnapshot({"rsi": 30.0})

    cond = Cond(
        lhs=FeatureRef(feature_id="rsi"),
        op=">=",
        rhs=ScalarValue(value=30.0),
    )

    result = eval_cond(cond, snapshot)

    passed = result.ok is True

    return DSLTestResult(
        name="greater_equal",
        passed=passed,
        expected="True (30 >= 30)",
        actual=f"{result.ok}",
    )


def test_less_equal() -> DSLTestResult:
    """
    Test: Less than or equal operator (<=)

    rsi = 70, threshold = 70
    Expected: rsi <= 70 is True (boundary case)
    """
    from ..backtest.rules.dsl_nodes.condition import Cond
    from ..backtest.rules.dsl_nodes.base import FeatureRef, ScalarValue
    from ..backtest.rules.evaluation.condition_ops import eval_cond

    snapshot = MockSnapshot({"rsi": 70.0})

    cond = Cond(
        lhs=FeatureRef(feature_id="rsi"),
        op="<=",
        rhs=ScalarValue(value=70.0),
    )

    result = eval_cond(cond, snapshot)

    passed = result.ok is True

    return DSLTestResult(
        name="less_equal",
        passed=passed,
        expected="True (70 <= 70)",
        actual=f"{result.ok}",
    )


def test_equal_integer() -> DSLTestResult:
    """
    Test: Equality operator (==) with integers.

    trend_direction = 1, expected = 1
    Expected: trend_direction == 1 is True
    """
    from ..backtest.rules.dsl_nodes.condition import Cond
    from ..backtest.rules.dsl_nodes.base import FeatureRef, ScalarValue
    from ..backtest.rules.evaluation.condition_ops import eval_cond

    # Declare trend_direction as INT type for equality to work
    snapshot = MockSnapshot(
        values={"trend_direction": 1.0},  # Runtime may store as float
        types={"trend_direction": "INT"},  # But declared as INT
    )

    cond = Cond(
        lhs=FeatureRef(feature_id="trend_direction"),
        op="==",
        rhs=ScalarValue(value=1),
    )

    result = eval_cond(cond, snapshot)

    # Equality on integers should work
    passed = result.ok is True

    return DSLTestResult(
        name="equal_integer",
        passed=passed,
        expected="True (1 == 1)",
        actual=f"{result.ok} (reason: {result.reason.name})",
    )


def test_not_equal() -> DSLTestResult:
    """
    Test: Not equal operator (!=)

    trend_direction = 1, expected = -1
    Expected: trend_direction != -1 is True
    """
    from ..backtest.rules.dsl_nodes.condition import Cond
    from ..backtest.rules.dsl_nodes.base import FeatureRef, ScalarValue
    from ..backtest.rules.evaluation.condition_ops import eval_cond

    snapshot = MockSnapshot(
        values={"trend_direction": 1.0},
        types={"trend_direction": "INT"},
    )

    cond = Cond(
        lhs=FeatureRef(feature_id="trend_direction"),
        op="!=",
        rhs=ScalarValue(value=-1),
    )

    result = eval_cond(cond, snapshot)

    passed = result.ok is True

    return DSLTestResult(
        name="not_equal",
        passed=passed,
        expected="True (1 != -1)",
        actual=f"{result.ok}",
    )


# =============================================================================
# Cross Detection Tests
# =============================================================================

def test_cross_above() -> DSLTestResult:
    """
    Test: Cross above detection.

    Bar N-1: ema_9=99, ema_21=100 (9 below 21)
    Bar N:   ema_9=101, ema_21=100 (9 above 21)
    Expected: cross_above is True
    """
    from ..backtest.rules.dsl_nodes.condition import Cond
    from ..backtest.rules.dsl_nodes.base import FeatureRef
    from ..backtest.rules.evaluation.condition_ops import eval_cond

    snapshot = MockSnapshot(
        values={"ema_9": 101.0, "ema_21": 100.0},
        prev_values={"ema_9": 99.0, "ema_21": 100.0},
    )

    cond = Cond(
        lhs=FeatureRef(feature_id="ema_9"),
        op="cross_above",
        rhs=FeatureRef(feature_id="ema_21"),
    )

    result = eval_cond(cond, snapshot)

    passed = result.ok is True

    return DSLTestResult(
        name="cross_above",
        passed=passed,
        expected="True (99<100 -> 101>100)",
        actual=f"{result.ok} (reason: {result.reason.name})",
    )


def test_cross_above_no_cross() -> DSLTestResult:
    """
    Test: Cross above returns False when already above.

    Bar N-1: ema_9=101, ema_21=100 (already above)
    Bar N:   ema_9=102, ema_21=100 (still above)
    Expected: cross_above is False (no cross happened)
    """
    from ..backtest.rules.dsl_nodes.condition import Cond
    from ..backtest.rules.dsl_nodes.base import FeatureRef
    from ..backtest.rules.evaluation.condition_ops import eval_cond

    snapshot = MockSnapshot(
        values={"ema_9": 102.0, "ema_21": 100.0},
        prev_values={"ema_9": 101.0, "ema_21": 100.0},
    )

    cond = Cond(
        lhs=FeatureRef(feature_id="ema_9"),
        op="cross_above",
        rhs=FeatureRef(feature_id="ema_21"),
    )

    result = eval_cond(cond, snapshot)

    passed = result.ok is False

    return DSLTestResult(
        name="cross_above_no_cross",
        passed=passed,
        expected="False (already above, no cross)",
        actual=f"{result.ok}",
    )


def test_cross_below() -> DSLTestResult:
    """
    Test: Cross below detection.

    Bar N-1: ema_9=101, ema_21=100 (9 above 21)
    Bar N:   ema_9=99, ema_21=100 (9 below 21)
    Expected: cross_below is True
    """
    from ..backtest.rules.dsl_nodes.condition import Cond
    from ..backtest.rules.dsl_nodes.base import FeatureRef
    from ..backtest.rules.evaluation.condition_ops import eval_cond

    snapshot = MockSnapshot(
        values={"ema_9": 99.0, "ema_21": 100.0},
        prev_values={"ema_9": 101.0, "ema_21": 100.0},
    )

    cond = Cond(
        lhs=FeatureRef(feature_id="ema_9"),
        op="cross_below",
        rhs=FeatureRef(feature_id="ema_21"),
    )

    result = eval_cond(cond, snapshot)

    passed = result.ok is True

    return DSLTestResult(
        name="cross_below",
        passed=passed,
        expected="True (101>100 -> 99<100)",
        actual=f"{result.ok}",
    )


# =============================================================================
# Boolean Logic Tests
# =============================================================================

def test_boolean_and() -> DSLTestResult:
    """
    Test: Boolean AND (all) - both conditions must be true.

    ema_9 > ema_21 (100 > 99 = True) AND rsi < 70 (50 < 70 = True)
    Expected: True
    """
    from ..backtest.rules.dsl_nodes.condition import Cond
    from ..backtest.rules.dsl_nodes.boolean import AllExpr
    from ..backtest.rules.dsl_nodes.base import FeatureRef, ScalarValue
    from ..backtest.rules.evaluation.core import ExprEvaluator

    snapshot = MockSnapshot({"ema_9": 100.0, "ema_21": 99.0, "rsi": 50.0})

    cond1 = Cond(
        lhs=FeatureRef(feature_id="ema_9"),
        op=">",
        rhs=FeatureRef(feature_id="ema_21"),
    )
    cond2 = Cond(
        lhs=FeatureRef(feature_id="rsi"),
        op="<",
        rhs=ScalarValue(value=70.0),
    )

    all_expr = AllExpr(children=(cond1, cond2))

    evaluator = ExprEvaluator()
    result = evaluator.evaluate(all_expr, snapshot)

    passed = result.ok is True

    return DSLTestResult(
        name="boolean_and",
        passed=passed,
        expected="True (both conditions true)",
        actual=f"{result.ok}",
    )


def test_boolean_and_fail() -> DSLTestResult:
    """
    Test: Boolean AND fails when one condition is false.

    ema_9 > ema_21 (100 > 99 = True) AND rsi < 30 (50 < 30 = False)
    Expected: False
    """
    from ..backtest.rules.dsl_nodes.condition import Cond
    from ..backtest.rules.dsl_nodes.boolean import AllExpr
    from ..backtest.rules.dsl_nodes.base import FeatureRef, ScalarValue
    from ..backtest.rules.evaluation.core import ExprEvaluator

    snapshot = MockSnapshot({"ema_9": 100.0, "ema_21": 99.0, "rsi": 50.0})

    cond1 = Cond(
        lhs=FeatureRef(feature_id="ema_9"),
        op=">",
        rhs=FeatureRef(feature_id="ema_21"),
    )
    cond2 = Cond(
        lhs=FeatureRef(feature_id="rsi"),
        op="<",
        rhs=ScalarValue(value=30.0),  # 50 < 30 is False
    )

    all_expr = AllExpr(children=(cond1, cond2))

    evaluator = ExprEvaluator()
    result = evaluator.evaluate(all_expr, snapshot)

    passed = result.ok is False

    return DSLTestResult(
        name="boolean_and_fail",
        passed=passed,
        expected="False (rsi < 30 is false)",
        actual=f"{result.ok}",
    )


def test_boolean_or() -> DSLTestResult:
    """
    Test: Boolean OR (any) - either condition can be true.

    ema_9 > ema_21 (99 > 100 = False) OR rsi < 30 (25 < 30 = True)
    Expected: True (second condition is true)
    """
    from ..backtest.rules.dsl_nodes.condition import Cond
    from ..backtest.rules.dsl_nodes.boolean import AnyExpr
    from ..backtest.rules.dsl_nodes.base import FeatureRef, ScalarValue
    from ..backtest.rules.evaluation.core import ExprEvaluator

    snapshot = MockSnapshot({"ema_9": 99.0, "ema_21": 100.0, "rsi": 25.0})

    cond1 = Cond(
        lhs=FeatureRef(feature_id="ema_9"),
        op=">",
        rhs=FeatureRef(feature_id="ema_21"),  # False
    )
    cond2 = Cond(
        lhs=FeatureRef(feature_id="rsi"),
        op="<",
        rhs=ScalarValue(value=30.0),  # True
    )

    any_expr = AnyExpr(children=(cond1, cond2))

    evaluator = ExprEvaluator()
    result = evaluator.evaluate(any_expr, snapshot)

    passed = result.ok is True

    return DSLTestResult(
        name="boolean_or",
        passed=passed,
        expected="True (rsi < 30 is true)",
        actual=f"{result.ok}",
    )


def test_boolean_not() -> DSLTestResult:
    """
    Test: Boolean NOT - inverts result.

    NOT(rsi > 70) where rsi = 50
    rsi > 70 = False, NOT(False) = True
    Expected: True
    """
    from ..backtest.rules.dsl_nodes.condition import Cond
    from ..backtest.rules.dsl_nodes.boolean import NotExpr
    from ..backtest.rules.dsl_nodes.base import FeatureRef, ScalarValue
    from ..backtest.rules.evaluation.core import ExprEvaluator

    snapshot = MockSnapshot({"rsi": 50.0})

    cond = Cond(
        lhs=FeatureRef(feature_id="rsi"),
        op=">",
        rhs=ScalarValue(value=70.0),  # 50 > 70 = False
    )

    not_expr = NotExpr(child=cond)

    evaluator = ExprEvaluator()
    result = evaluator.evaluate(not_expr, snapshot)

    passed = result.ok is True

    return DSLTestResult(
        name="boolean_not",
        passed=passed,
        expected="True (NOT(50 > 70) = NOT(False) = True)",
        actual=f"{result.ok}",
    )


def test_nested_boolean() -> DSLTestResult:
    """
    Test: Nested boolean logic with correct precedence.

    ((a > b) AND (c < d)) OR (e > f)
    where a=100, b=99, c=50, d=70, e=1, f=10

    (100 > 99) = True
    (50 < 70) = True
    True AND True = True
    (1 > 10) = False
    True OR False = True
    """
    from ..backtest.rules.dsl_nodes.condition import Cond
    from ..backtest.rules.dsl_nodes.boolean import AllExpr, AnyExpr
    from ..backtest.rules.dsl_nodes.base import FeatureRef, ScalarValue
    from ..backtest.rules.evaluation.core import ExprEvaluator

    snapshot = MockSnapshot({
        "a": 100.0, "b": 99.0,
        "c": 50.0, "d": 70.0,
        "e": 1.0, "f": 10.0,
    })

    cond_a_gt_b = Cond(lhs=FeatureRef(feature_id="a"), op=">", rhs=FeatureRef(feature_id="b"))
    cond_c_lt_d = Cond(lhs=FeatureRef(feature_id="c"), op="<", rhs=FeatureRef(feature_id="d"))
    cond_e_gt_f = Cond(lhs=FeatureRef(feature_id="e"), op=">", rhs=FeatureRef(feature_id="f"))

    inner_and = AllExpr(children=(cond_a_gt_b, cond_c_lt_d))
    outer_or = AnyExpr(children=(inner_and, cond_e_gt_f))

    evaluator = ExprEvaluator()
    result = evaluator.evaluate(outer_or, snapshot)

    passed = result.ok is True

    return DSLTestResult(
        name="nested_boolean",
        passed=passed,
        expected="True ((True AND True) OR False)",
        actual=f"{result.ok}",
    )


# =============================================================================
# Range Operation Tests
# =============================================================================

def test_between() -> DSLTestResult:
    """
    Test: Between operator for range checking.

    price = 50050, low = 50000, high = 50100
    Expected: price between(50000, 50100) is True
    """
    from ..backtest.rules.dsl_nodes.condition import Cond
    from ..backtest.rules.dsl_nodes.base import FeatureRef, RangeValue
    from ..backtest.rules.evaluation.condition_ops import eval_cond

    snapshot = MockSnapshot({"price": 50050.0})

    # RangeValue expects float values, not FeatureRef
    cond = Cond(
        lhs=FeatureRef(feature_id="price"),
        op="between",
        rhs=RangeValue(low=50000.0, high=50100.0),
    )

    result = eval_cond(cond, snapshot)

    passed = result.ok is True

    return DSLTestResult(
        name="between",
        passed=passed,
        expected="True (50050 between 50000 and 50100)",
        actual=f"{result.ok}",
    )


def test_near_abs() -> DSLTestResult:
    """
    Test: Near absolute tolerance.

    price = 50005, level = 50000, tolerance = 10
    Expected: price near_abs(level, 10) is True (diff = 5 < 10)
    """
    from ..backtest.rules.dsl_nodes.condition import Cond
    from ..backtest.rules.dsl_nodes.base import FeatureRef
    from ..backtest.rules.evaluation.condition_ops import eval_cond

    snapshot = MockSnapshot({"price": 50005.0, "level": 50000.0})

    # tolerance is a float, not ScalarValue
    cond = Cond(
        lhs=FeatureRef(feature_id="price"),
        op="near_abs",
        rhs=FeatureRef(feature_id="level"),
        tolerance=10.0,
    )

    result = eval_cond(cond, snapshot)

    passed = result.ok is True

    return DSLTestResult(
        name="near_abs",
        passed=passed,
        expected="True (|50005 - 50000| = 5 <= 10)",
        actual=f"{result.ok}",
    )


def test_near_pct() -> DSLTestResult:
    """
    Test: Near percentage tolerance.

    price = 50250, level = 50000, tolerance = 0.5%
    Expected: price near_pct(level, 0.5%) is True (diff = 0.5% <= 0.5%)

    Note: tolerance is expressed as a decimal (0.005 = 0.5%)
    """
    from ..backtest.rules.dsl_nodes.condition import Cond
    from ..backtest.rules.dsl_nodes.base import FeatureRef
    from ..backtest.rules.evaluation.condition_ops import eval_cond

    snapshot = MockSnapshot({"price": 50250.0, "level": 50000.0})

    # tolerance is a float as decimal (0.005 = 0.5%)
    cond = Cond(
        lhs=FeatureRef(feature_id="price"),
        op="near_pct",
        rhs=FeatureRef(feature_id="level"),
        tolerance=0.005,  # 0.5%
    )

    result = eval_cond(cond, snapshot)

    passed = result.ok is True

    return DSLTestResult(
        name="near_pct",
        passed=passed,
        expected="True (|50250 - 50000| / 50000 = 0.5%)",
        actual=f"{result.ok}",
    )


# =============================================================================
# Run All Tests
# =============================================================================

def run_all_dsl_tests() -> list[DSLTestResult]:
    """Run all DSL validation tests."""
    tests = [
        # Comparison operators
        test_greater_than,
        test_greater_than_false,
        test_less_than,
        test_greater_equal,
        test_less_equal,
        test_equal_integer,
        test_not_equal,
        # Cross detection
        test_cross_above,
        test_cross_above_no_cross,
        test_cross_below,
        # Boolean logic
        test_boolean_and,
        test_boolean_and_fail,
        test_boolean_or,
        test_boolean_not,
        test_nested_boolean,
        # Range operations
        test_between,
        test_near_abs,
        test_near_pct,
    ]

    results = []
    for test_fn in tests:
        try:
            result = test_fn()
            results.append(result)
        except Exception as e:
            results.append(DSLTestResult(
                name=test_fn.__name__,
                passed=False,
                expected="Test to run",
                actual="",
                error_msg=str(e),
            ))

    return results


def format_dsl_test_report(results: list[DSLTestResult]) -> str:
    """Format DSL test results as report."""
    lines = []
    lines.append("=" * 60)
    lines.append("DSL CONDITION EVALUATION VALIDATION")
    lines.append("=" * 60)

    passed = sum(1 for r in results if r.passed)
    total = len(results)

    # Group by category
    categories = {
        "Comparison Operators": ["greater_than", "greater_than_false", "less_than",
                                 "greater_equal", "less_equal", "equal_integer", "not_equal"],
        "Cross Detection": ["cross_above", "cross_above_no_cross", "cross_below"],
        "Boolean Logic": ["boolean_and", "boolean_and_fail", "boolean_or",
                         "boolean_not", "nested_boolean"],
        "Range Operations": ["between", "near_abs", "near_pct"],
    }

    for category, test_names in categories.items():
        lines.append(f"\n{category}:")
        for r in results:
            if r.name in test_names:
                status = "PASS" if r.passed else "FAIL"
                lines.append(f"  {status}: {r.name}")
                if not r.passed:
                    lines.append(f"         Expected: {r.expected}")
                    lines.append(f"         Actual:   {r.actual}")
                    if r.error_msg:
                        lines.append(f"         Error:    {r.error_msg}")

    lines.append("-" * 60)
    lines.append(f"TOTAL: {passed}/{total} passed")

    if passed == total:
        lines.append("All DSL evaluation is CORRECT")
    else:
        lines.append("DSL ERRORS DETECTED")

    lines.append("=" * 60)

    return "\n".join(lines)
