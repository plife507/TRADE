"""
Integration Scenario Tests.

Phase 6 of DSL Foundation Freeze.

Tests combined DSL conditions that use multiple features together:
- Zone + trend filter
- EMA cross + RSI confirmation
- Bar hold exit
"""

import pytest

from tests.synthetic.harness.snapshot import SyntheticSnapshot
from src.backtest.rules.dsl_eval import ExprEvaluator
from src.backtest.rules.dsl_parser import parse_expr


# =============================================================================
# Module-level evaluator
# =============================================================================

_evaluator = ExprEvaluator(max_window_bars=100)


# =============================================================================
# Helper Functions
# =============================================================================

def evaluate(condition: dict | list, snapshot: SyntheticSnapshot) -> bool:
    """Evaluate a DSL condition against a snapshot."""
    expr = parse_expr(condition)
    result = _evaluator.evaluate(expr, snapshot)
    return result.ok


# =============================================================================
# Scenario 1: Zone Entry with Trend Filter
# =============================================================================

class TestZoneTrendFilter:
    """
    Test combined zone + trend filter conditions.

    Entry when: price in demand zone AND trend is bullish
    """

    def test_zone_and_trend_both_true(self):
        """Entry signal when both zone inside and trend bullish."""
        snapshot = SyntheticSnapshot.with_features({
            "dz.any_inside": True,
            "trend.direction": 1,  # Bullish
        })

        condition = {
            "all": [
                {"lhs": {"feature_id": "dz", "field": "any_inside"}, "op": "eq", "rhs": True},
                {"lhs": {"feature_id": "trend", "field": "direction"}, "op": "eq", "rhs": 1},
            ]
        }

        assert evaluate(condition, snapshot) is True

    def test_zone_true_trend_bearish(self):
        """No entry when zone inside but trend bearish."""
        snapshot = SyntheticSnapshot.with_features({
            "dz.any_inside": True,
            "trend.direction": -1,  # Bearish
        })

        condition = {
            "all": [
                {"lhs": {"feature_id": "dz", "field": "any_inside"}, "op": "eq", "rhs": True},
                {"lhs": {"feature_id": "trend", "field": "direction"}, "op": "eq", "rhs": 1},
            ]
        }

        assert evaluate(condition, snapshot) is False

    def test_zone_false_trend_bullish(self):
        """No entry when trend bullish but not in zone."""
        snapshot = SyntheticSnapshot.with_features({
            "dz.any_inside": False,
            "trend.direction": 1,  # Bullish
        })

        condition = {
            "all": [
                {"lhs": {"feature_id": "dz", "field": "any_inside"}, "op": "eq", "rhs": True},
                {"lhs": {"feature_id": "trend", "field": "direction"}, "op": "eq", "rhs": 1},
            ]
        }

        assert evaluate(condition, snapshot) is False

    def test_zone_touched_or_trend_strong(self):
        """Entry when zone touched OR trend very strong."""
        snapshot = SyntheticSnapshot.with_features({
            "dz.any_touched": False,
            "trend.strength": 2.5,  # Very strong (>2)
        })

        condition = {
            "any": [
                {"lhs": {"feature_id": "dz", "field": "any_touched"}, "op": "eq", "rhs": True},
                {"lhs": {"feature_id": "trend", "field": "strength"}, "op": "gt", "rhs": 2.0},
            ]
        }

        assert evaluate(condition, snapshot) is True


# =============================================================================
# Scenario 2: EMA Cross with RSI Confirmation
# =============================================================================

class TestEmaCrossRsiConfirmation:
    """
    Test EMA crossover with RSI confirmation.

    Entry when: EMA cross AND RSI was oversold within recent bars
    """

    def test_ema_cross_with_rsi_oversold(self):
        """Entry on EMA cross up with recent RSI oversold."""
        # EMA 9 crosses above EMA 21, RSI was oversold (bar 0)
        snapshot = SyntheticSnapshot.with_history({
            "ema_9": [49.0, 51.0],   # Cross up
            "ema_21": [50.0, 50.0],
            "rsi_14": [25.0, 35.0, 40.0, 45.0, 50.0],  # Was < 30 at bar 0
        })

        condition = {
            "all": [
                {"lhs": "ema_9", "op": "cross_above", "rhs": {"feature_id": "ema_21"}},
                {
                    "occurred_within": {
                        "bars": 5,
                        "expr": {"lhs": "rsi_14", "op": "lt", "rhs": 30}
                    }
                },
            ]
        }

        assert evaluate(condition, snapshot) is True

    def test_ema_cross_without_rsi_oversold(self):
        """No entry on EMA cross without recent RSI oversold."""
        # EMA 9 crosses above EMA 21, but RSI never oversold
        snapshot = SyntheticSnapshot.with_history({
            "ema_9": [49.0, 51.0],
            "ema_21": [50.0, 50.0],
            "rsi_14": [45.0, 48.0, 50.0, 52.0, 55.0],  # Never < 30
        })

        condition = {
            "all": [
                {"lhs": "ema_9", "op": "cross_above", "rhs": {"feature_id": "ema_21"}},
                {
                    "occurred_within": {
                        "bars": 5,
                        "expr": {"lhs": "rsi_14", "op": "lt", "rhs": 30}
                    }
                },
            ]
        }

        assert evaluate(condition, snapshot) is False

    def test_no_ema_cross_with_rsi_oversold(self):
        """No entry without EMA cross even if RSI oversold."""
        # No cross - EMA 9 stays above EMA 21
        snapshot = SyntheticSnapshot.with_history({
            "ema_9": [51.0, 52.0],   # Both above 50
            "ema_21": [50.0, 50.0],
            "rsi_14": [25.0, 35.0, 40.0, 45.0, 50.0],
        })

        condition = {
            "all": [
                {"lhs": "ema_9", "op": "cross_above", "rhs": {"feature_id": "ema_21"}},
                {
                    "occurred_within": {
                        "bars": 5,
                        "expr": {"lhs": "rsi_14", "op": "lt", "rhs": 30}
                    }
                },
            ]
        }

        assert evaluate(condition, snapshot) is False

    def test_ema_cross_short_with_rsi_overbought(self):
        """Short entry on EMA cross down with recent RSI overbought."""
        snapshot = SyntheticSnapshot.with_history({
            "ema_9": [51.0, 49.0],   # Cross down
            "ema_21": [50.0, 50.0],
            "rsi_14": [75.0, 70.0, 65.0, 60.0, 55.0],  # Was > 70 at bar 0
        })

        condition = {
            "all": [
                {"lhs": "ema_9", "op": "cross_below", "rhs": {"feature_id": "ema_21"}},
                {
                    "occurred_within": {
                        "bars": 5,
                        "expr": {"lhs": "rsi_14", "op": "gt", "rhs": 70}
                    }
                },
            ]
        }

        assert evaluate(condition, snapshot) is True


# =============================================================================
# Scenario 3: Bar Hold Exit
# =============================================================================

class TestBarHoldExit:
    """
    Test bar hold exit conditions.

    Exit when: RSI > 70 for N consecutive bars
    """

    def test_rsi_overbought_hold_3_bars(self):
        """Exit when RSI overbought for 3 consecutive bars."""
        snapshot = SyntheticSnapshot.with_history({
            "rsi_14": [72.0, 74.0, 73.0],  # All > 70 for 3 bars
        })

        condition = {
            "holds_for": {
                "bars": 3,
                "expr": {"lhs": "rsi_14", "op": "gt", "rhs": 70}
            }
        }

        assert evaluate(condition, snapshot) is True

    def test_rsi_overbought_broken_early(self):
        """No exit when RSI breaks below 70 before 3 bars."""
        snapshot = SyntheticSnapshot.with_history({
            "rsi_14": [72.0, 68.0, 73.0],  # Bar 1 breaks below 70
        })

        condition = {
            "holds_for": {
                "bars": 3,
                "expr": {"lhs": "rsi_14", "op": "gt", "rhs": 70}
            }
        }

        assert evaluate(condition, snapshot) is False

    def test_rsi_overbought_exact_threshold(self):
        """RSI at exactly 70 does NOT trigger (needs > 70)."""
        snapshot = SyntheticSnapshot.with_history({
            "rsi_14": [72.0, 70.0, 73.0],  # Bar 1 = 70, not > 70
        })

        condition = {
            "holds_for": {
                "bars": 3,
                "expr": {"lhs": "rsi_14", "op": "gt", "rhs": 70}
            }
        }

        assert evaluate(condition, snapshot) is False

    def test_price_below_ma_hold_5_bars(self):
        """Exit when price below MA for 5 bars (trend reversal)."""
        snapshot = SyntheticSnapshot.with_history({
            "close": [95.0, 94.0, 93.0, 92.0, 91.0],      # Declining
            "ema_21": [100.0, 100.0, 100.0, 100.0, 100.0], # Flat at 100
        })

        condition = {
            "holds_for": {
                "bars": 5,
                "expr": {"lhs": "close", "op": "lt", "rhs": {"feature_id": "ema_21"}}
            }
        }

        assert evaluate(condition, snapshot) is True


# =============================================================================
# Scenario 4: Complex Nested Logic
# =============================================================================

class TestComplexNestedLogic:
    """Test complex nested boolean logic combinations."""

    def test_entry_with_multiple_filters(self):
        """
        Entry when: (zone_inside AND trend_bullish) OR
                   (rsi_oversold AND volume_spike)
        """
        # Zone condition fails, but RSI + volume passes
        snapshot = SyntheticSnapshot.with_features({
            "dz.any_inside": False,
            "trend.direction": 1,
            "rsi_14": 25.0,
            "volume_ratio": 2.5,
        })

        condition = {
            "any": [
                {
                    "all": [
                        {"lhs": {"feature_id": "dz", "field": "any_inside"}, "op": "eq", "rhs": True},
                        {"lhs": {"feature_id": "trend", "field": "direction"}, "op": "eq", "rhs": 1},
                    ]
                },
                {
                    "all": [
                        {"lhs": "rsi_14", "op": "lt", "rhs": 30},
                        {"lhs": "volume_ratio", "op": "gt", "rhs": 2.0},
                    ]
                },
            ]
        }

        assert evaluate(condition, snapshot) is True

    def test_not_overbought_entry(self):
        """Entry when NOT overbought and in uptrend."""
        snapshot = SyntheticSnapshot.with_features({
            "rsi_14": 55.0,
            "trend.direction": 1,
        })

        condition = {
            "all": [
                {"not": {"lhs": "rsi_14", "op": "gt", "rhs": 70}},  # NOT overbought
                {"lhs": {"feature_id": "trend", "field": "direction"}, "op": "eq", "rhs": 1},
            ]
        }

        assert evaluate(condition, snapshot) is True

    def test_not_overbought_blocked(self):
        """No entry when overbought (NOT condition fails)."""
        snapshot = SyntheticSnapshot.with_features({
            "rsi_14": 75.0,  # Overbought
            "trend.direction": 1,
        })

        condition = {
            "all": [
                {"not": {"lhs": "rsi_14", "op": "gt", "rhs": 70}},
                {"lhs": {"feature_id": "trend", "field": "direction"}, "op": "eq", "rhs": 1},
            ]
        }

        assert evaluate(condition, snapshot) is False


# =============================================================================
# Scenario 5: Arithmetic in Conditions
# =============================================================================

class TestArithmeticInConditions:
    """Test arithmetic expressions in integrated conditions."""

    def test_ema_spread_with_volume(self):
        """Entry when EMA spread > threshold AND volume spike."""
        snapshot = SyntheticSnapshot.with_features({
            "ema_9": 105.0,
            "ema_21": 100.0,
            "volume_ratio": 2.5,
        })

        condition = {
            "all": [
                {"lhs": ["ema_9", "-", "ema_21"], "op": "gt", "rhs": 3.0},  # Spread > 3
                {"lhs": "volume_ratio", "op": "gt", "rhs": 2.0},
            ]
        }

        assert evaluate(condition, snapshot) is True

    def test_percent_change_threshold(self):
        """Entry on percent change above threshold."""
        snapshot = SyntheticSnapshot.with_features({
            "close": 105.0,
            "open": 100.0,
        })

        # (close - open) / open > 0.03 (3% gain)
        condition = {
            "lhs": [["close", "-", "open"], "/", "open"],
            "op": "gt",
            "rhs": 0.03
        }

        assert evaluate(condition, snapshot) is True

    def test_normalized_position_in_range(self):
        """Price position in daily range."""
        snapshot = SyntheticSnapshot.with_features({
            "close": 95.0,
            "high": 100.0,
            "low": 80.0,
        })

        # (close - low) / (high - low) > 0.7 (upper 30% of range)
        condition = {
            "lhs": [["close", "-", "low"], "/", ["high", "-", "low"]],
            "op": "gt",
            "rhs": 0.7
        }

        # (95 - 80) / (100 - 80) = 15 / 20 = 0.75 > 0.7
        assert evaluate(condition, snapshot) is True
