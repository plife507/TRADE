"""
Derived State Computer - Computes aggregate values from structure state.

Architecture Principle: Pure Math
- Input: MultiTFIncrementalState, BarData
- Output: dict of derived values
- No side effects, stateless computation
- Engine orchestrates invocation

The DerivedStateComputer computes:
1. confluence_score: How many signals align (0.0-1.0)
2. alignment: high_tf/med_tf/low_tf trend agreement (0.0-1.0)
3. regime: Market regime classification

See: docs/specs/PLAY_VISION.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .types import MarketRegime

if TYPE_CHECKING:
    from src.structures import MultiTFIncrementalState, TFIncrementalState, BarData


# Trend direction values (from trend detector)
TREND_UP = 1
TREND_DOWN = -1
TREND_NEUTRAL = 0


class DerivedStateComputer:
    """
    Computes derived values from current structure state.

    Pure computation class. Stateless - all computation based on inputs.

    Derived Values:
        confluence_score: Proportion of aligned bullish/bearish signals (0.0-1.0)
        alignment: Agreement between high_tf, med_tf, and exec trend directions (0.0-1.0)
        momentum: Aggregate momentum signal (-1.0 to 1.0)
        structure_stability: How recently structures changed (0.0-1.0)

    Example:
        >>> computer = DerivedStateComputer()
        >>> derived = computer.compute(incremental_state, bar)
        >>> print(derived["confluence_score"])
        0.75
    """

    def __init__(self) -> None:
        """Initialize the derived state computer."""
        pass  # Stateless - no initialization needed

    def compute(
        self,
        incremental_state: "MultiTFIncrementalState",
        bar: "BarData",
    ) -> dict[str, Any]:
        """
        Compute all derived values for current state.

        Pure function: (state, bar) -> dict

        Args:
            incremental_state: Current MultiTFIncrementalState
            bar: Current BarData

        Returns:
            Dict of derived values
        """
        # Compute individual derived values
        confluence = self._compute_confluence_score(incremental_state)
        alignment = self._compute_alignment(incremental_state)
        momentum = self._compute_momentum(incremental_state, bar)
        stability = self._compute_structure_stability(incremental_state)

        return {
            "confluence_score": confluence,
            "alignment": alignment,
            "momentum": momentum,
            "structure_stability": stability,
        }

    def classify_regime(
        self,
        incremental_state: "MultiTFIncrementalState",
        bar: "BarData",
    ) -> MarketRegime:
        """
        Classify the current market regime.

        Pure function: (state, bar) -> MarketRegime

        Uses trend direction, strength, and volatility to classify:
        - TRENDING_UP: Strong uptrend detected
        - TRENDING_DOWN: Strong downtrend detected
        - RANGING: Low directional movement, bounded price action
        - VOLATILE: High volatility with no clear trend

        Args:
            incremental_state: Current MultiTFIncrementalState
            bar: Current BarData

        Returns:
            MarketRegime classification
        """
        # Get exec trend if available
        exec_trend = self._get_trend_direction(incremental_state.exec)
        exec_strength = self._get_trend_strength(incremental_state.exec)

        # Get high_tf trend for confirmation
        high_tf_trend = self._get_high_tf_trend_direction(incremental_state)

        # Check volatility (via ATR in bar indicators)
        atr = bar.indicators.get("atr", 0.0)
        close = bar.close
        volatility_pct = (atr / close * 100) if close > 0 else 0.0

        # High volatility threshold (e.g., > 3% ATR)
        is_volatile = volatility_pct > 3.0

        # Strong trend threshold
        is_strong_trend = exec_strength > 0.6

        # Classification logic
        if is_volatile and not is_strong_trend:
            return MarketRegime.VOLATILE

        if exec_trend == TREND_UP and is_strong_trend:
            # Confirm with high_tf if available
            if high_tf_trend == TREND_UP or high_tf_trend is None:
                return MarketRegime.TRENDING_UP

        if exec_trend == TREND_DOWN and is_strong_trend:
            if high_tf_trend == TREND_DOWN or high_tf_trend is None:
                return MarketRegime.TRENDING_DOWN

        if exec_strength < 0.3 and not is_volatile:
            return MarketRegime.RANGING

        return MarketRegime.UNKNOWN

    def _compute_confluence_score(
        self,
        incremental_state: "MultiTFIncrementalState",
    ) -> float:
        """
        Compute confluence score: proportion of aligned signals.

        Checks:
        - Trend directions across timeframes
        - Zone states (bullish/bearish bias)
        - Swing positions relative to price

        Returns:
            Float 0.0-1.0 where 1.0 = all signals aligned
        """
        signals_bullish = 0
        signals_bearish = 0
        total_signals = 0

        # Check exec trend
        exec_trend = self._get_trend_direction(incremental_state.exec)
        if exec_trend is not None:
            total_signals += 1
            if exec_trend == TREND_UP:
                signals_bullish += 1
            elif exec_trend == TREND_DOWN:
                signals_bearish += 1

        # Check high_tf trends
        for tf_name, tf_state in incremental_state.high_tf.items():
            high_tf_trend = self._get_trend_direction(tf_state)
            if high_tf_trend is not None:
                total_signals += 1
                if high_tf_trend == TREND_UP:
                    signals_bullish += 1
                elif high_tf_trend == TREND_DOWN:
                    signals_bearish += 1

        # Check zone states (demand = bullish, supply = bearish)
        zone_bias = self._get_zone_bias(incremental_state.exec)
        if zone_bias is not None:
            total_signals += 1
            if zone_bias > 0:
                signals_bullish += 1
            elif zone_bias < 0:
                signals_bearish += 1

        if total_signals == 0:
            return 0.0

        # Confluence = max alignment proportion
        max_aligned = max(signals_bullish, signals_bearish)
        return max_aligned / total_signals

    def _compute_alignment(
        self,
        incremental_state: "MultiTFIncrementalState",
    ) -> float:
        """
        Compute high_tf/med_tf/exec trend alignment score.

        Returns:
            Float 0.0-1.0 where 1.0 = all timeframes trend same direction
        """
        trends: list[int] = []

        # Get exec trend
        exec_trend = self._get_trend_direction(incremental_state.exec)
        if exec_trend is not None and exec_trend != TREND_NEUTRAL:
            trends.append(exec_trend)

        # Get high_tf trends
        for tf_name, tf_state in incremental_state.high_tf.items():
            high_tf_trend = self._get_trend_direction(tf_state)
            if high_tf_trend is not None and high_tf_trend != TREND_NEUTRAL:
                trends.append(high_tf_trend)

        if len(trends) <= 1:
            return 0.0  # Need at least 2 timeframes to measure alignment

        # Count matching directions
        if all(t == TREND_UP for t in trends):
            return 1.0
        if all(t == TREND_DOWN for t in trends):
            return 1.0

        # Partial alignment
        up_count = sum(1 for t in trends if t == TREND_UP)
        down_count = sum(1 for t in trends if t == TREND_DOWN)
        max_aligned = max(up_count, down_count)

        return max_aligned / len(trends)

    def _compute_momentum(
        self,
        incremental_state: "MultiTFIncrementalState",
        bar: "BarData",
    ) -> float:
        """
        Compute aggregate momentum signal.

        Returns:
            Float -1.0 to 1.0 where positive = bullish, negative = bearish
        """
        momentum = 0.0
        weights = 0.0

        # Use trend direction and strength
        exec_trend = self._get_trend_direction(incremental_state.exec)
        exec_strength = self._get_trend_strength(incremental_state.exec)

        if exec_trend is not None:
            momentum += exec_trend * exec_strength
            weights += 1.0

        # Add high_tf trends with lower weight
        for tf_name, tf_state in incremental_state.high_tf.items():
            high_tf_trend = self._get_trend_direction(tf_state)
            high_tf_strength = self._get_trend_strength(tf_state)

            if high_tf_trend is not None:
                momentum += high_tf_trend * high_tf_strength * 0.5
                weights += 0.5

        if weights == 0:
            return 0.0

        return max(-1.0, min(1.0, momentum / weights))

    def _compute_structure_stability(
        self,
        incremental_state: "MultiTFIncrementalState",
    ) -> float:
        """
        Compute structure stability score.

        Based on how recently structures changed (version updates).
        Higher = more stable (fewer recent changes).

        Returns:
            Float 0.0-1.0 where 1.0 = no recent structure changes
        """
        # Placeholder - would need transition history access
        # For now, return 1.0 (stable)
        return 1.0

    def _get_trend_direction(
        self,
        tf_state: "TFIncrementalState",
    ) -> int | None:
        """Get trend direction from a TF state."""
        try:
            # Look for trend detector
            for detector_key in tf_state.list_structures():
                if "trend" in detector_key.lower():
                    detector = tf_state.structures[detector_key]
                    direction = detector.get_value("direction")
                    if direction is not None:
                        return int(direction)
            return None
        except (KeyError, AttributeError):
            return None

    def _get_trend_strength(
        self,
        tf_state: "TFIncrementalState",
    ) -> float:
        """Get trend strength from a TF state."""
        try:
            for detector_key in tf_state.list_structures():
                if "trend" in detector_key.lower():
                    detector = tf_state.structures[detector_key]
                    strength = detector.get_value("strength")
                    if strength is not None:
                        return float(strength)
            return 0.0
        except (KeyError, AttributeError):
            return 0.0

    def _get_high_tf_trend_direction(
        self,
        incremental_state: "MultiTFIncrementalState",
    ) -> int | None:
        """Get trend direction from highest timeframe available."""
        # Return first high_tf trend found (assumes ordered by TF)
        for tf_name, tf_state in incremental_state.high_tf.items():
            direction = self._get_trend_direction(tf_state)
            if direction is not None:
                return direction
        return None

    def _get_zone_bias(
        self,
        tf_state: "TFIncrementalState",
    ) -> int | None:
        """
        Get zone bias: +1 for demand (bullish), -1 for supply (bearish).

        Checks zone states - active demand zones = bullish, active supply = bearish.
        """
        try:
            demand_active = False
            supply_active = False

            for detector_key in tf_state.list_structures():
                if "zone" in detector_key.lower():
                    detector = tf_state.structures[detector_key]
                    state = detector.get_value("state")

                    if state == "ACTIVE":
                        # Determine zone type from key or params
                        if "demand" in detector_key.lower():
                            demand_active = True
                        elif "supply" in detector_key.lower():
                            supply_active = True

            if demand_active and not supply_active:
                return 1
            if supply_active and not demand_active:
                return -1
            return 0  # Both or neither

        except (KeyError, AttributeError):
            return None
