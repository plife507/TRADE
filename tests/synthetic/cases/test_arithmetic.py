"""
Arithmetic DSL Tests.

Phase 4 of DSL Foundation Freeze.

Tests arithmetic expressions in DSL conditions:
- Basic operations (+, -, *, /, %)
- Division by zero handling
- Nested arithmetic
- Arithmetic in LHS and RHS of conditions
- Arithmetic with feature offsets
"""

import pytest

from src.backtest.rules.dsl_nodes import (
    ArithmeticExpr,
    Cond,
    FeatureRef,
    ScalarValue,
    ARITHMETIC_OPERATORS,
)
from src.backtest.rules.dsl_parser import (
    is_arithmetic_list,
    parse_arithmetic,
    parse_arithmetic_operand,
    parse_lhs,
    parse_rhs,
    parse_cond,
)
from src.backtest.rules.evaluation import ExprEvaluator
from tests.synthetic.harness.snapshot import SyntheticSnapshot


# =============================================================================
# ArithmeticExpr Node Tests
# =============================================================================

class TestArithmeticExprNode:
    """Test ArithmeticExpr AST node creation and validation."""

    def test_basic_subtraction_node(self):
        """Create basic subtraction node."""
        arith = ArithmeticExpr(
            left=FeatureRef(feature_id="ema_9"),
            op="-",
            right=FeatureRef(feature_id="ema_21"),
        )
        assert arith.left.feature_id == "ema_9"
        assert arith.op == "-"
        assert arith.right.feature_id == "ema_21"

    def test_nested_arithmetic_node(self):
        """Create nested arithmetic node."""
        inner = ArithmeticExpr(
            left=FeatureRef(feature_id="ema_9"),
            op="-",
            right=FeatureRef(feature_id="ema_21"),
        )
        outer = ArithmeticExpr(
            left=inner,
            op="/",
            right=FeatureRef(feature_id="atr_14"),
        )
        assert isinstance(outer.left, ArithmeticExpr)
        assert outer.op == "/"
        assert outer.right.feature_id == "atr_14"

    def test_invalid_operator_rejected(self):
        """Invalid arithmetic operator raises ValueError."""
        with pytest.raises(ValueError, match="unknown operator"):
            ArithmeticExpr(
                left=FeatureRef(feature_id="a"),
                op="invalid",
                right=FeatureRef(feature_id="b"),
            )

    @pytest.mark.parametrize("op", list(ARITHMETIC_OPERATORS))
    def test_all_operators_valid(self, op: str):
        """All arithmetic operators create valid nodes."""
        arith = ArithmeticExpr(
            left=FeatureRef(feature_id="a"),
            op=op,
            right=FeatureRef(feature_id="b"),
        )
        assert arith.op == op


# =============================================================================
# Parser Tests
# =============================================================================

class TestArithmeticParsing:
    """Test arithmetic expression parsing."""

    def test_is_arithmetic_list_basic(self):
        """Detect arithmetic list syntax."""
        assert is_arithmetic_list(["ema_9", "-", "ema_21"]) is True
        assert is_arithmetic_list(["a", "+", "b"]) is True
        assert is_arithmetic_list(["x", "*", 10]) is True
        assert is_arithmetic_list([["a", "+", "b"], "/", "c"]) is True

    def test_is_arithmetic_list_rejects_non_arithmetic(self):
        """Non-arithmetic lists are rejected."""
        assert is_arithmetic_list([1, 2, 3]) is False  # No operator
        assert is_arithmetic_list(["a", ">", "b"]) is False  # Not arith op
        assert is_arithmetic_list(["a", "b"]) is False  # Wrong length
        assert is_arithmetic_list(["a", "-", "b", "c"]) is False  # Too many

    def test_parse_arithmetic_basic(self):
        """Parse basic arithmetic expression."""
        arith = parse_arithmetic(["ema_9", "-", "ema_21"])
        assert isinstance(arith, ArithmeticExpr)
        assert arith.left.feature_id == "ema_9"
        assert arith.op == "-"
        assert arith.right.feature_id == "ema_21"

    def test_parse_arithmetic_with_scalar(self):
        """Parse arithmetic with scalar operand."""
        arith = parse_arithmetic(["close", "-", 100])
        assert isinstance(arith.left, FeatureRef)
        assert isinstance(arith.right, ScalarValue)
        assert arith.right.value == 100

    def test_parse_arithmetic_nested(self):
        """Parse nested arithmetic expression."""
        arith = parse_arithmetic([["ema_9", "-", "ema_21"], "/", "atr_14"])
        assert isinstance(arith.left, ArithmeticExpr)
        assert arith.left.op == "-"
        assert arith.op == "/"
        assert arith.right.feature_id == "atr_14"

    def test_parse_arithmetic_operand_string(self):
        """Parse string operand as FeatureRef."""
        operand = parse_arithmetic_operand("rsi_14")
        assert isinstance(operand, FeatureRef)
        assert operand.feature_id == "rsi_14"

    def test_parse_arithmetic_operand_dict(self):
        """Parse dict operand as FeatureRef with field."""
        operand = parse_arithmetic_operand({
            "feature_id": "swing",
            "field": "high_level",
        })
        assert isinstance(operand, FeatureRef)
        assert operand.feature_id == "swing"
        assert operand.field == "high_level"

    def test_parse_arithmetic_operand_number(self):
        """Parse number operand as ScalarValue."""
        operand = parse_arithmetic_operand(50.0)
        assert isinstance(operand, ScalarValue)
        assert operand.value == 50.0

    def test_parse_lhs_arithmetic(self):
        """Parse arithmetic as LHS."""
        lhs = parse_lhs(["ema_9", "-", "ema_21"])
        assert isinstance(lhs, ArithmeticExpr)

    def test_parse_lhs_feature_ref(self):
        """Parse feature ref as LHS."""
        lhs = parse_lhs("rsi_14")
        assert isinstance(lhs, FeatureRef)

    def test_parse_rhs_arithmetic(self):
        """Parse arithmetic as RHS."""
        rhs = parse_rhs(["ema_9", "-", 100])
        assert isinstance(rhs, ArithmeticExpr)

    def test_parse_cond_with_arithmetic_lhs(self):
        """Parse condition with arithmetic LHS."""
        cond = parse_cond({
            "lhs": ["ema_9", "-", "ema_21"],
            "op": "gt",
            "rhs": 100,
        })
        assert isinstance(cond.lhs, ArithmeticExpr)
        assert cond.op == "gt"
        assert isinstance(cond.rhs, ScalarValue)
        assert cond.rhs.value == 100

    def test_parse_cond_with_arithmetic_rhs(self):
        """Parse condition with arithmetic RHS."""
        cond = parse_cond({
            "lhs": "close",
            "op": "gt",
            "rhs": ["swing_high", "-", 10],
        })
        assert isinstance(cond.lhs, FeatureRef)
        assert isinstance(cond.rhs, ArithmeticExpr)


# =============================================================================
# Evaluation Tests
# =============================================================================

class TestArithmeticEvaluation:
    """Test arithmetic expression evaluation."""

    @pytest.fixture
    def evaluator(self) -> ExprEvaluator:
        """Create expression evaluator."""
        return ExprEvaluator()

    def test_subtract_features(self, evaluator: ExprEvaluator):
        """Evaluate: ema_9 - ema_21."""
        snapshot = SyntheticSnapshot.with_features({
            "ema_9": 52.0,
            "ema_21": 50.0,
        })
        cond = Cond(
            lhs=ArithmeticExpr(
                left=FeatureRef(feature_id="ema_9"),
                op="-",
                right=FeatureRef(feature_id="ema_21"),
            ),
            op="gt",
            rhs=ScalarValue(1.0),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True  # 52 - 50 = 2 > 1

    def test_add_features(self, evaluator: ExprEvaluator):
        """Evaluate: a + b."""
        snapshot = SyntheticSnapshot.with_features({
            "a": 10.0,
            "b": 5.0,
        })
        cond = Cond(
            lhs=ArithmeticExpr(
                left=FeatureRef(feature_id="a"),
                op="+",
                right=FeatureRef(feature_id="b"),
            ),
            op="eq",
            rhs=ScalarValue(15),  # INT eq allowed
        )
        # Use gt instead since eq is for discrete
        cond = Cond(
            lhs=ArithmeticExpr(
                left=FeatureRef(feature_id="a"),
                op="+",
                right=FeatureRef(feature_id="b"),
            ),
            op="gte",
            rhs=ScalarValue(15.0),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True  # 10 + 5 = 15 >= 15

    def test_multiply_features(self, evaluator: ExprEvaluator):
        """Evaluate: a * b."""
        snapshot = SyntheticSnapshot.with_features({
            "a": 3.0,
            "b": 4.0,
        })
        cond = Cond(
            lhs=ArithmeticExpr(
                left=FeatureRef(feature_id="a"),
                op="*",
                right=FeatureRef(feature_id="b"),
            ),
            op="lt",
            rhs=ScalarValue(13.0),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True  # 3 * 4 = 12 < 13

    def test_divide_features(self, evaluator: ExprEvaluator):
        """Evaluate: volume / volume_avg."""
        snapshot = SyntheticSnapshot.with_features({
            "volume": 150.0,
            "volume_avg": 100.0,
        })
        cond = Cond(
            lhs=ArithmeticExpr(
                left=FeatureRef(feature_id="volume"),
                op="/",
                right=FeatureRef(feature_id="volume_avg"),
            ),
            op="gt",
            rhs=ScalarValue(1.4),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True  # 150 / 100 = 1.5 > 1.4

    def test_modulo_features(self, evaluator: ExprEvaluator):
        """Evaluate: a % b."""
        snapshot = SyntheticSnapshot.with_features({
            "a": 17,
            "b": 5,
        })
        cond = Cond(
            lhs=ArithmeticExpr(
                left=FeatureRef(feature_id="a"),
                op="%",
                right=FeatureRef(feature_id="b"),
            ),
            op="gte",
            rhs=ScalarValue(2),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True  # 17 % 5 = 2 >= 2

    def test_division_by_zero(self, evaluator: ExprEvaluator):
        """Division by zero returns missing."""
        snapshot = SyntheticSnapshot.with_features({
            "volume": 150.0,
            "zero": 0.0,
        })
        cond = Cond(
            lhs=ArithmeticExpr(
                left=FeatureRef(feature_id="volume"),
                op="/",
                right=FeatureRef(feature_id="zero"),
            ),
            op="gt",
            rhs=ScalarValue(0.0),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is False
        assert "missing" in result.message.lower() or "arithmetic" in result.lhs_path

    def test_modulo_by_zero(self, evaluator: ExprEvaluator):
        """Modulo by zero returns missing."""
        snapshot = SyntheticSnapshot.with_features({
            "a": 17,
            "zero": 0,
        })
        cond = Cond(
            lhs=ArithmeticExpr(
                left=FeatureRef(feature_id="a"),
                op="%",
                right=FeatureRef(feature_id="zero"),
            ),
            op="gte",
            rhs=ScalarValue(0),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is False

    def test_nested_arithmetic(self, evaluator: ExprEvaluator):
        """Evaluate: (ema_9 - ema_21) / atr_14."""
        snapshot = SyntheticSnapshot.with_features({
            "ema_9": 52.0,
            "ema_21": 50.0,
            "atr_14": 1.0,
        })
        cond = Cond(
            lhs=ArithmeticExpr(
                left=ArithmeticExpr(
                    left=FeatureRef(feature_id="ema_9"),
                    op="-",
                    right=FeatureRef(feature_id="ema_21"),
                ),
                op="/",
                right=FeatureRef(feature_id="atr_14"),
            ),
            op="gt",
            rhs=ScalarValue(1.5),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True  # (52 - 50) / 1 = 2 > 1.5

    def test_arithmetic_with_scalar(self, evaluator: ExprEvaluator):
        """Evaluate: close - 100."""
        snapshot = SyntheticSnapshot.with_features({
            "close": 50100.0,
        })
        cond = Cond(
            lhs=ArithmeticExpr(
                left=FeatureRef(feature_id="close"),
                op="-",
                right=ScalarValue(100.0),
            ),
            op="gt",
            rhs=ScalarValue(50000.0),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is False  # 50100 - 100 = 50000, not > 50000

    def test_arithmetic_in_rhs(self, evaluator: ExprEvaluator):
        """Evaluate: close > swing_high - 10."""
        snapshot = SyntheticSnapshot.with_features({
            "close": 95.0,
            "swing_high": 100.0,
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="close"),
            op="gt",
            rhs=ArithmeticExpr(
                left=FeatureRef(feature_id="swing_high"),
                op="-",
                right=ScalarValue(10.0),
            ),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True  # 95 > (100 - 10) = 95 > 90

    def test_missing_left_operand(self, evaluator: ExprEvaluator):
        """Missing left operand returns failure."""
        snapshot = SyntheticSnapshot.with_features({
            "b": 50.0,
        })
        cond = Cond(
            lhs=ArithmeticExpr(
                left=FeatureRef(feature_id="missing"),
                op="-",
                right=FeatureRef(feature_id="b"),
            ),
            op="gt",
            rhs=ScalarValue(0.0),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is False

    def test_missing_right_operand(self, evaluator: ExprEvaluator):
        """Missing right operand returns failure."""
        snapshot = SyntheticSnapshot.with_features({
            "a": 50.0,
        })
        cond = Cond(
            lhs=ArithmeticExpr(
                left=FeatureRef(feature_id="a"),
                op="-",
                right=FeatureRef(feature_id="missing"),
            ),
            op="gt",
            rhs=ScalarValue(0.0),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is False


# =============================================================================
# Condition Result Tests
# =============================================================================

class TestArithmeticConditions:
    """Test arithmetic expressions produce correct boolean results."""

    @pytest.fixture
    def evaluator(self) -> ExprEvaluator:
        """Create expression evaluator."""
        return ExprEvaluator()

    @pytest.mark.parametrize("ema9,ema21,threshold,expected", [
        (52.0, 50.0, 1.0, True),   # 2 > 1
        (52.0, 50.0, 2.0, False),  # 2 > 2 = False
        (50.0, 50.0, 0.0, False),  # 0 > 0 = False
        (55.0, 50.0, 4.9, True),   # 5 > 4.9
    ])
    def test_ema_difference_threshold(
        self,
        evaluator: ExprEvaluator,
        ema9: float,
        ema21: float,
        threshold: float,
        expected: bool,
    ):
        """EMA difference threshold conditions."""
        snapshot = SyntheticSnapshot.with_features({
            "ema_9": ema9,
            "ema_21": ema21,
        })
        cond = Cond(
            lhs=ArithmeticExpr(
                left=FeatureRef(feature_id="ema_9"),
                op="-",
                right=FeatureRef(feature_id="ema_21"),
            ),
            op="gt",
            rhs=ScalarValue(threshold),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is expected

    @pytest.mark.parametrize("volume,avg,ratio,expected", [
        (200.0, 100.0, 1.5, True),   # 2.0 > 1.5
        (150.0, 100.0, 1.5, False),  # 1.5 > 1.5 = False
        (100.0, 100.0, 0.99, True),  # 1.0 > 0.99
    ])
    def test_volume_ratio(
        self,
        evaluator: ExprEvaluator,
        volume: float,
        avg: float,
        ratio: float,
        expected: bool,
    ):
        """Volume ratio conditions."""
        snapshot = SyntheticSnapshot.with_features({
            "volume": volume,
            "volume_avg": avg,
        })
        cond = Cond(
            lhs=ArithmeticExpr(
                left=FeatureRef(feature_id="volume"),
                op="/",
                right=FeatureRef(feature_id="volume_avg"),
            ),
            op="gt",
            rhs=ScalarValue(ratio),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is expected


# =============================================================================
# Integration with Window Operators
# =============================================================================

class TestArithmeticWithWindows:
    """Test arithmetic in window operator contexts."""

    @pytest.fixture
    def evaluator(self) -> ExprEvaluator:
        """Create expression evaluator."""
        return ExprEvaluator()

    def test_arithmetic_in_holds_for(self, evaluator: ExprEvaluator):
        """Arithmetic condition in holds_for window."""
        # EMA difference > 1 for 3 bars
        snapshot = SyntheticSnapshot.with_history({
            "ema_9": [52.0, 53.0, 54.0],
            "ema_21": [50.0, 50.0, 50.0],
        })

        from src.backtest.rules.dsl_nodes import HoldsFor

        expr = HoldsFor(
            bars=3,
            expr=Cond(
                lhs=ArithmeticExpr(
                    left=FeatureRef(feature_id="ema_9"),
                    op="-",
                    right=FeatureRef(feature_id="ema_21"),
                ),
                op="gt",
                rhs=ScalarValue(1.0),
            ),
        )
        result = evaluator.evaluate(expr, snapshot)
        assert result.ok is True  # All 3 bars: 2, 3, 4 > 1

    def test_arithmetic_in_holds_for_broken(self, evaluator: ExprEvaluator):
        """Arithmetic condition fails in window."""
        # EMA difference dips below threshold
        snapshot = SyntheticSnapshot.with_history({
            "ema_9": [52.0, 50.5, 54.0],  # Middle bar: diff = 0.5
            "ema_21": [50.0, 50.0, 50.0],
        })

        from src.backtest.rules.dsl_nodes import HoldsFor

        expr = HoldsFor(
            bars=3,
            expr=Cond(
                lhs=ArithmeticExpr(
                    left=FeatureRef(feature_id="ema_9"),
                    op="-",
                    right=FeatureRef(feature_id="ema_21"),
                ),
                op="gt",
                rhs=ScalarValue(1.0),
            ),
        )
        result = evaluator.evaluate(expr, snapshot)
        assert result.ok is False  # Bar 1: 0.5 > 1 = False
