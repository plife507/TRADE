"""
Tests for 1m action model price features: last_price, mark_price.

These features enable precise 1m-resolution trading logic:
- last_price: 1m ticker close (updates every 1m within exec bar)
- mark_price: Fair price for margin/PnL calculations

Both are built-in (no declaration needed) and have specific offset rules:
- last_price: offset 0 (current) and 1 (previous 1m) supported
- mark_price: offset 0 only

Per TEST COVERAGE RULE: Tests both bullish and bearish scenarios.
"""

import pytest

from tests.synthetic.harness.snapshot import SyntheticSnapshot
from src.backtest.rules.dsl_eval import ExprEvaluator
from src.backtest.rules.dsl_nodes import (
    Cond,
    FeatureRef,
    ScalarValue,
    AllExpr,
    ArithmeticExpr,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def evaluator() -> ExprEvaluator:
    """DSL expression evaluator."""
    return ExprEvaluator(max_window_bars=100)


# =============================================================================
# Last Price Tests
# =============================================================================

class TestLastPriceBasic:
    """Test last_price feature access."""

    def test_last_price_gt_feature(self, evaluator: ExprEvaluator):
        """last_price > another feature."""
        snapshot = SyntheticSnapshot.with_features({
            "last_price": 50100.0,
            "ema_200": 50000.0,
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="last_price"),
            op="gt",
            rhs=FeatureRef(feature_id="ema_200"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_last_price_lt_feature(self, evaluator: ExprEvaluator):
        """last_price < another feature."""
        snapshot = SyntheticSnapshot.with_features({
            "last_price": 49900.0,
            "ema_200": 50000.0,
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="last_price"),
            op="lt",
            rhs=FeatureRef(feature_id="ema_200"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_last_price_vs_scalar(self, evaluator: ExprEvaluator):
        """last_price compared to scalar value."""
        snapshot = SyntheticSnapshot.with_features({"last_price": 50000.0})
        cond = Cond(
            lhs=FeatureRef(feature_id="last_price"),
            op="gt",
            rhs=ScalarValue(49000.0),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_last_price_near_level_pct(self, evaluator: ExprEvaluator):
        """last_price near a level (percentage tolerance)."""
        snapshot = SyntheticSnapshot.with_features({
            "last_price": 50050.0,  # 0.1% above 50000
            "fib.level_0.618": 50000.0,
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="last_price"),
            op="near_pct",
            rhs=FeatureRef(feature_id="fib.level_0.618"),
            tolerance=0.005,  # 0.5% tolerance
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True


class TestLastPriceCrossover:
    """Test last_price crossover operators (1m resolution)."""

    def test_last_price_cross_above_ema(self, evaluator: ExprEvaluator):
        """last_price crosses above EMA (bullish)."""
        snapshot = SyntheticSnapshot.with_history({
            "last_price": [49900.0, 50100.0],  # prev below, curr above 50000
            "ema_200": [50000.0, 50000.0],     # constant
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="last_price"),
            op="cross_above",
            rhs=FeatureRef(feature_id="ema_200"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_last_price_cross_below_ema(self, evaluator: ExprEvaluator):
        """last_price crosses below EMA (bearish)."""
        snapshot = SyntheticSnapshot.with_history({
            "last_price": [50100.0, 49900.0],  # prev above, curr below 50000
            "ema_200": [50000.0, 50000.0],     # constant
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="last_price"),
            op="cross_below",
            rhs=FeatureRef(feature_id="ema_200"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_last_price_touch_and_cross(self, evaluator: ExprEvaluator):
        """last_price exactly touches then crosses (edge case)."""
        snapshot = SyntheticSnapshot.with_history({
            "last_price": [50000.0, 50100.0],  # prev == target, curr above
            "ema_200": [50000.0, 50000.0],
        })
        # cross_above: prev <= target AND curr > target
        cond = Cond(
            lhs=FeatureRef(feature_id="last_price"),
            op="cross_above",
            rhs=FeatureRef(feature_id="ema_200"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_last_price_no_cross_already_above(self, evaluator: ExprEvaluator):
        """No cross if already above."""
        snapshot = SyntheticSnapshot.with_history({
            "last_price": [50100.0, 50200.0],  # both above
            "ema_200": [50000.0, 50000.0],
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="last_price"),
            op="cross_above",
            rhs=FeatureRef(feature_id="ema_200"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is False

    def test_last_price_cross_htf_feature(self, evaluator: ExprEvaluator):
        """last_price (1m) crosses HTF feature (4h EMA)."""
        # This tests the cross-TF comparison scenario
        snapshot = SyntheticSnapshot.with_history({
            "last_price": [49800.0, 50100.0],      # 1m resolution
            "ema_50_4h": [50000.0, 50000.0],       # 4h feature (forward-filled)
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="last_price"),
            op="cross_above",
            rhs=FeatureRef(feature_id="ema_50_4h"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True


# =============================================================================
# Mark Price Tests
# =============================================================================

class TestMarkPriceBasic:
    """Test mark_price feature access."""

    def test_mark_price_gt_close(self, evaluator: ExprEvaluator):
        """mark_price > close."""
        snapshot = SyntheticSnapshot.with_features({
            "mark_price": 50000.0,
            "close": 49950.0,
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="mark_price"),
            op="gt",
            rhs=FeatureRef(feature_id="close"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_mark_price_vs_scalar(self, evaluator: ExprEvaluator):
        """mark_price compared to scalar."""
        snapshot = SyntheticSnapshot.with_features({"mark_price": 50000.0})
        cond = Cond(
            lhs=FeatureRef(feature_id="mark_price"),
            op="gte",
            rhs=ScalarValue(50000.0),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_mark_price_near_level_abs(self, evaluator: ExprEvaluator):
        """mark_price near level (absolute tolerance)."""
        snapshot = SyntheticSnapshot.with_features({
            "mark_price": 50025.0,  # Close to 50000
            "fib.level_0.618": 50000.0,
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="mark_price"),
            op="near_abs",
            rhs=FeatureRef(feature_id="fib.level_0.618"),
            tolerance=50.0,  # Within $50
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True


# =============================================================================
# Last Price vs Close (Different Update Rates)
# =============================================================================

class TestLastPriceVsClose:
    """Test scenarios where last_price and close differ.

    In real backtesting:
    - close: Updates once per exec bar (e.g., every 15m)
    - last_price: Updates every 1m (15x more frequent on 15m exec)

    This allows detecting intra-bar movements.
    """

    def test_last_price_above_close_bullish(self, evaluator: ExprEvaluator):
        """last_price moved above close within exec bar (bullish momentum)."""
        snapshot = SyntheticSnapshot.with_features({
            "last_price": 50200.0,  # Current 1m price
            "close": 50000.0,       # Last exec bar close (still 50000)
        })
        # Price has risen since last bar close
        cond = Cond(
            lhs=FeatureRef(feature_id="last_price"),
            op="gt",
            rhs=FeatureRef(feature_id="close"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_last_price_below_close_bearish(self, evaluator: ExprEvaluator):
        """last_price dropped below close within exec bar (bearish momentum)."""
        snapshot = SyntheticSnapshot.with_features({
            "last_price": 49800.0,  # Current 1m price
            "close": 50000.0,       # Last exec bar close
        })
        # Price has dropped since last bar close
        cond = Cond(
            lhs=FeatureRef(feature_id="last_price"),
            op="lt",
            rhs=FeatureRef(feature_id="close"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_intra_bar_breakout_detection(self, evaluator: ExprEvaluator):
        """Detect breakout within exec bar using last_price."""
        snapshot = SyntheticSnapshot.with_features({
            "last_price": 50200.0,
            "close": 50000.0,
            "swing.high_level": 50100.0,  # Swing high
        })
        # last_price broke above swing high, but close hasn't updated yet
        cond = Cond(
            lhs=FeatureRef(feature_id="last_price"),
            op="gt",
            rhs=FeatureRef(feature_id="swing.high_level"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True


# =============================================================================
# Cross-TF Comparisons (1m vs HTF)
# =============================================================================

class TestCrossTFComparisons:
    """Test 1m price vs higher timeframe features."""

    def test_last_price_above_4h_ema(self, evaluator: ExprEvaluator):
        """last_price compared to 4h EMA (forward-filled)."""
        snapshot = SyntheticSnapshot.with_features({
            "last_price": 50500.0,       # Current 1m price
            "ema_50_4h": 50000.0,         # 4h EMA (constant until 4h bar closes)
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="last_price"),
            op="gt",
            rhs=FeatureRef(feature_id="ema_50_4h"),
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_last_price_near_1h_support(self, evaluator: ExprEvaluator):
        """last_price near 1h support level."""
        snapshot = SyntheticSnapshot.with_features({
            "last_price": 49020.0,        # Near support
            "swing_1h.low_level": 49000.0,  # 1h swing low
        })
        cond = Cond(
            lhs=FeatureRef(feature_id="last_price"),
            op="near_pct",
            rhs=FeatureRef(feature_id="swing_1h.low_level"),
            tolerance=0.001,  # Within 0.1%
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_multi_tf_alignment(self, evaluator: ExprEvaluator):
        """Multiple timeframe conditions aligned."""
        snapshot = SyntheticSnapshot.with_features({
            "last_price": 50500.0,
            "ema_50_4h": 50000.0,       # HTF trend up
            "ema_200_D": 48000.0,       # Daily trend up (D = Bybit format)
            "rsi_14": 45.0,             # Not overbought
        })
        # Entry: last_price > 4h EMA AND last_price > daily EMA AND RSI < 70
        cond = AllExpr(children=(
            Cond(
                lhs=FeatureRef(feature_id="last_price"),
                op="gt",
                rhs=FeatureRef(feature_id="ema_50_4h"),
            ),
            Cond(
                lhs=FeatureRef(feature_id="last_price"),
                op="gt",
                rhs=FeatureRef(feature_id="ema_200_D"),
            ),
            Cond(
                lhs=FeatureRef(feature_id="rsi_14"),
                op="lt",
                rhs=ScalarValue(70),
            ),
        ))
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True


# =============================================================================
# Arithmetic with Price Features
# =============================================================================

class TestPriceArithmetic:
    """Test arithmetic operations with price features."""

    def test_last_price_minus_close_threshold(self, evaluator: ExprEvaluator):
        """(last_price - close) > threshold for momentum."""
        snapshot = SyntheticSnapshot.with_features({
            "last_price": 50200.0,
            "close": 50000.0,
        })
        # Price moved $200 above last close
        cond = Cond(
            lhs=ArithmeticExpr(
                left=FeatureRef(feature_id="last_price"),
                op="-",
                right=FeatureRef(feature_id="close"),
            ),
            op="gt",
            rhs=ScalarValue(100.0),  # $100 threshold
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_last_price_close_ratio(self, evaluator: ExprEvaluator):
        """(last_price / close) > 1.001 for 0.1% move."""
        snapshot = SyntheticSnapshot.with_features({
            "last_price": 50100.0,
            "close": 50000.0,
        })
        # 0.2% up move
        cond = Cond(
            lhs=ArithmeticExpr(
                left=FeatureRef(feature_id="last_price"),
                op="/",
                right=FeatureRef(feature_id="close"),
            ),
            op="gt",
            rhs=ScalarValue(1.001),  # 0.1% threshold
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True

    def test_price_distance_from_level_atr_units(self, evaluator: ExprEvaluator):
        """Distance from price to level in ATR units."""
        snapshot = SyntheticSnapshot.with_features({
            "last_price": 50050.0,
            "swing.high_level": 50000.0,
            "atr_14": 100.0,
        })
        # Price is 0.5 ATR above swing high
        cond = Cond(
            lhs=ArithmeticExpr(
                left=ArithmeticExpr(
                    left=FeatureRef(feature_id="last_price"),
                    op="-",
                    right=FeatureRef(feature_id="swing.high_level"),
                ),
                op="/",
                right=FeatureRef(feature_id="atr_14"),
            ),
            op="lt",
            rhs=ScalarValue(1.0),  # Less than 1 ATR away
        )
        result = evaluator.evaluate(cond, snapshot)
        assert result.ok is True
