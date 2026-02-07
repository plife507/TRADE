"""
Structure Validation: Proves market structure detection is correct.

Tests the structure detectors with synthetic data where correct answers are known:
1. Swing Detection - pivots at expected bars
2. Trend Detection - HH/HL/LH/LL classification
3. Zone Detection - supply/demand zone bounds
4. Fibonacci - level calculations
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import numpy as np

from ..utils.logger import get_logger

logger = get_logger()


@dataclass
class StructureTestResult:
    """Result of a structure validation test."""
    name: str
    passed: bool
    expected: str
    actual: str
    error_msg: str = ""


# =============================================================================
# Synthetic Data Generators
# =============================================================================

def generate_ohlcv_bar(
    timestamp: datetime,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    volume: float = 1000.0,
) -> dict:
    """Generate a single OHLCV bar."""
    return {
        "timestamp": timestamp,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "volume": volume,
    }


def generate_swing_high_data(
    swing_bar: int = 50,
    base_price: float = 100.0,
    swing_amplitude: float = 10.0,
    num_bars: int = 100,
) -> list[dict]:
    """
    Generate data with a clear swing high at specified bar.

    Pattern: price rises to peak at swing_bar, then falls.
    Left bars have ascending highs, right bars have descending highs.
    """
    bars = []
    start_time = datetime(2025, 1, 1)

    for i in range(num_bars):
        ts = start_time + timedelta(minutes=i)

        # Distance from swing bar
        dist = abs(i - swing_bar)

        if i < swing_bar:
            # Rising to the peak
            progress = i / swing_bar
            high = base_price + (swing_amplitude * progress)
        elif i == swing_bar:
            # Peak
            high = base_price + swing_amplitude
        else:
            # Falling from peak
            progress = (i - swing_bar) / (num_bars - swing_bar)
            high = base_price + swing_amplitude * (1 - progress)

        # Create bar with high at target level
        open_price = high - 0.5
        close_price = high - 0.3
        low_price = high - 1.0

        bars.append(generate_ohlcv_bar(ts, open_price, high, low_price, close_price))

    return bars


def generate_swing_low_data(
    swing_bar: int = 50,
    base_price: float = 100.0,
    swing_amplitude: float = 10.0,
    num_bars: int = 100,
) -> list[dict]:
    """
    Generate data with a clear swing low at specified bar.

    Pattern: price falls to trough at swing_bar, then rises.
    """
    bars = []
    start_time = datetime(2025, 1, 1)

    for i in range(num_bars):
        ts = start_time + timedelta(minutes=i)

        if i < swing_bar:
            # Falling to the trough
            progress = i / swing_bar
            low = base_price - (swing_amplitude * progress)
        elif i == swing_bar:
            # Trough
            low = base_price - swing_amplitude
        else:
            # Rising from trough
            progress = (i - swing_bar) / (num_bars - swing_bar)
            low = base_price - swing_amplitude * (1 - progress)

        # Create bar with low at target level
        open_price = low + 0.3
        close_price = low + 0.5
        high_price = low + 1.0

        bars.append(generate_ohlcv_bar(ts, open_price, high_price, low, close_price))

    return bars


def generate_uptrend_data(
    num_bars: int = 200,
    base_price: float = 100.0,
    trend_strength: float = 0.5,
) -> list[dict]:
    """
    Generate data with clear higher highs and higher lows (uptrend).

    Creates swing pattern: L1 -> H1 -> L2 (higher than L1) -> H2 (higher than H1) -> L3 -> H3
    Uses larger swings and ensures swing points have extreme values.
    """
    bars = []
    start_time = datetime(2025, 1, 1)

    # Create 6 swing points: L1, H1, L2, H2, L3, H3 (for more waves)
    swing_bars = [30, 60, 90, 120, 150, 180]
    swing_levels = [
        base_price - 10,   # L1 (swing low)
        base_price + 20,   # H1 (swing high)
        base_price,        # L2 (higher low - HL)
        base_price + 30,   # H2 (higher high - HH)
        base_price + 10,   # L3 (higher low - HL)
        base_price + 40,   # H3 (higher high - HH)
    ]
    swing_types = ["low", "high", "low", "high", "low", "high"]

    for i in range(num_bars):
        ts = start_time + timedelta(minutes=i)

        # Find which segment we're in
        level = base_price
        for j in range(len(swing_bars)):
            if i <= swing_bars[j]:
                if j == 0:
                    progress = i / swing_bars[j]
                    level = base_price + (swing_levels[j] - base_price) * progress
                else:
                    progress = (i - swing_bars[j-1]) / (swing_bars[j] - swing_bars[j-1])
                    level = swing_levels[j-1] + (swing_levels[j] - swing_levels[j-1]) * progress
                break
        else:
            level = swing_levels[-1]

        # Check if we're at a swing bar - make it a clear pivot
        is_swing_high = i in [60, 120, 180]  # H1, H2, H3
        is_swing_low = i in [30, 90, 150]    # L1, L2, L3

        if is_swing_high:
            # Make this bar have the highest high in the window
            open_price = level - 1
            close_price = level
            high_price = level + 5  # Extra high to ensure it's a swing high
            low_price = level - 2
        elif is_swing_low:
            # Make this bar have the lowest low in the window
            open_price = level + 1
            close_price = level
            high_price = level + 2
            low_price = level - 5  # Extra low to ensure it's a swing low
        else:
            # Normal bar with small range
            open_price = level
            close_price = level + 0.1
            high_price = level + 1
            low_price = level - 1

        bars.append(generate_ohlcv_bar(ts, open_price, high_price, low_price, close_price))

    return bars


def generate_downtrend_data(
    num_bars: int = 200,
    base_price: float = 100.0,
) -> list[dict]:
    """
    Generate data with clear lower highs and lower lows (downtrend).

    Creates swing pattern: H1 -> L1 -> H2 (lower than H1) -> L2 (lower than L1) -> H3 -> L3
    Uses larger swings and ensures swing points have extreme values.
    """
    bars = []
    start_time = datetime(2025, 1, 1)

    # Create 6 swing points: H1, L1, H2, L2, H3, L3 (for more waves)
    swing_bars = [30, 60, 90, 120, 150, 180]
    swing_levels = [
        base_price + 20,   # H1 (swing high)
        base_price,        # L1 (swing low)
        base_price + 10,   # H2 (lower high - LH)
        base_price - 10,   # L2 (lower low - LL)
        base_price,        # H3 (lower high - LH)
        base_price - 20,   # L3 (lower low - LL)
    ]

    swing_types = ["high", "low", "high", "low", "high", "low"]

    for i in range(num_bars):
        ts = start_time + timedelta(minutes=i)

        # Find which segment we're in
        level = base_price
        for j in range(len(swing_bars)):
            if i <= swing_bars[j]:
                if j == 0:
                    progress = i / swing_bars[j]
                    level = base_price + (swing_levels[j] - base_price) * progress
                else:
                    progress = (i - swing_bars[j-1]) / (swing_bars[j] - swing_bars[j-1])
                    level = swing_levels[j-1] + (swing_levels[j] - swing_levels[j-1]) * progress
                break
        else:
            level = swing_levels[-1]

        # Check if we're at a swing bar - make it a clear pivot
        is_swing_high = i in [30, 90, 150]   # H1, H2, H3
        is_swing_low = i in [60, 120, 180]   # L1, L2, L3

        if is_swing_high:
            # Make this bar have the highest high in the window
            open_price = level - 1
            close_price = level
            high_price = level + 5  # Extra high to ensure it's a swing high
            low_price = level - 2
        elif is_swing_low:
            # Make this bar have the lowest low in the window
            open_price = level + 1
            close_price = level
            high_price = level + 2
            low_price = level - 5  # Extra low to ensure it's a swing low
        else:
            # Normal bar with small range
            open_price = level
            close_price = level - 0.1
            high_price = level + 1
            low_price = level - 1

        bars.append(generate_ohlcv_bar(ts, open_price, high_price, low_price, close_price))

    return bars


# =============================================================================
# Swing Detection Tests
# =============================================================================

def test_swing_high_detection() -> StructureTestResult:
    """
    Test: Swing detector finds swing high at correct bar.

    Setup: Clear peak at bar 50 (price rises then falls).
    Expected: Swing high detected within tolerance of bar 50.
    """
    from ..structures.detectors.swing import IncrementalSwing
    from ..structures.base import BarData

    bars = generate_swing_high_data(swing_bar=50, base_price=100.0, swing_amplitude=10.0)

    # Configure detector with moderate lookback
    detector = IncrementalSwing(
        params={
            "left": 5,
            "right": 5,
            "mode": "fractal",
        },
        deps={},
    )

    # Process all bars - convert dict to BarData
    last_high_idx = None
    for i, bar_dict in enumerate(bars):
        bar = BarData(
            idx=i,
            open=bar_dict["open"],
            high=bar_dict["high"],
            low=bar_dict["low"],
            close=bar_dict["close"],
            volume=bar_dict["volume"],
            indicators={},
        )
        detector.update(i, bar)
        high_idx = detector.get_value("high_idx")
        if high_idx is not None and high_idx > 0:
            last_high_idx = high_idx

    # Check if swing high was found near expected bar
    expected_bar = 50
    tolerance = 10  # Allow +/- 10 bars for detection delay

    if last_high_idx is None:
        return StructureTestResult(
            name="swing_high_detection",
            passed=False,
            expected=f"Swing high near bar {expected_bar}",
            actual="No swing high detected",
        )

    diff = abs(last_high_idx - expected_bar)
    passed = diff <= tolerance

    return StructureTestResult(
        name="swing_high_detection",
        passed=passed,
        expected=f"Swing high within {tolerance} bars of {expected_bar}",
        actual=f"Swing high at bar {last_high_idx} (diff={diff})",
    )


def test_swing_low_detection() -> StructureTestResult:
    """
    Test: Swing detector finds swing low at correct bar.

    Setup: Clear trough at bar 50 (price falls then rises).
    Expected: Swing low detected within tolerance of bar 50.
    """
    from ..structures.detectors.swing import IncrementalSwing
    from ..structures.base import BarData

    bars = generate_swing_low_data(swing_bar=50, base_price=100.0, swing_amplitude=10.0)

    detector = IncrementalSwing(
        params={
            "left": 5,
            "right": 5,
            "mode": "fractal",
        },
        deps={},
    )

    last_low_idx = None
    for i, bar_dict in enumerate(bars):
        bar = BarData(
            idx=i,
            open=bar_dict["open"],
            high=bar_dict["high"],
            low=bar_dict["low"],
            close=bar_dict["close"],
            volume=bar_dict["volume"],
            indicators={},
        )
        detector.update(i, bar)
        low_idx = detector.get_value("low_idx")
        if low_idx is not None and low_idx > 0:
            last_low_idx = low_idx

    expected_bar = 50
    tolerance = 10

    if last_low_idx is None:
        return StructureTestResult(
            name="swing_low_detection",
            passed=False,
            expected=f"Swing low near bar {expected_bar}",
            actual="No swing low detected",
        )

    diff = abs(last_low_idx - expected_bar)
    passed = diff <= tolerance

    return StructureTestResult(
        name="swing_low_detection",
        passed=passed,
        expected=f"Swing low within {tolerance} bars of {expected_bar}",
        actual=f"Swing low at bar {last_low_idx} (diff={diff})",
    )


def test_swing_alternation() -> StructureTestResult:
    """
    Test: Swing detector enforces strict H-L-H-L alternation.

    Setup: Data with multiple peaks and troughs.
    Expected: Swings alternate (no consecutive highs or lows).
    """
    from ..structures.detectors.swing import IncrementalSwing

    # Generate data with clear alternating swings
    bars = []
    start_time = datetime(2025, 1, 1)
    base = 100.0

    # Create alternating pattern: up-down-up-down
    for i in range(100):
        ts = start_time + timedelta(minutes=i)
        # Sine wave pattern
        phase = (i / 25) * np.pi  # Period of ~50 bars
        level = base + 10 * np.sin(phase)

        open_price = level
        close_price = level + 0.1
        high_price = level + 0.5
        low_price = level - 0.5

        bars.append(generate_ohlcv_bar(ts, open_price, high_price, low_price, close_price))

    detector = IncrementalSwing(
        params={
            "left": 5,
            "right": 5,
            "mode": "fractal",
            "strict_alternation": True,
        },
        deps={},
    )

    # Track sequence of swings
    swing_sequence = []  # List of "H" or "L"
    last_high_idx = -999
    last_low_idx = -999

    from ..structures.base import BarData
    for i, bar_dict in enumerate(bars):
        bar = BarData(
            idx=i,
            open=bar_dict["open"],
            high=bar_dict["high"],
            low=bar_dict["low"],
            close=bar_dict["close"],
            volume=bar_dict["volume"],
            indicators={},
        )
        detector.update(i, bar)

        high_idx = detector.get_value("high_idx")
        low_idx = detector.get_value("low_idx")

        if high_idx is not None and high_idx > last_high_idx:
            swing_sequence.append(("H", high_idx))
            last_high_idx = high_idx

        if low_idx is not None and low_idx > last_low_idx:
            swing_sequence.append(("L", low_idx))
            last_low_idx = low_idx

    # Sort by bar index
    swing_sequence.sort(key=lambda x: x[1])

    # Check alternation
    violations = 0
    for i in range(1, len(swing_sequence)):
        if swing_sequence[i][0] == swing_sequence[i-1][0]:
            violations += 1

    passed = violations == 0

    return StructureTestResult(
        name="swing_alternation",
        passed=passed,
        expected="0 alternation violations",
        actual=f"{violations} violations in {len(swing_sequence)} swings",
    )


# =============================================================================
# Fibonacci Tests
# =============================================================================

def test_fib_retracement_levels() -> StructureTestResult:
    """
    Test: Fibonacci retracement levels are calculated correctly.

    Formula: level = high - (ratio * range)

    Hand calculation:
        high = 100, low = 50, range = 50
        38.2%: 100 - (0.382 * 50) = 80.9
        50.0%: 100 - (0.500 * 50) = 75.0
        61.8%: 100 - (0.618 * 50) = 69.1
    """
    from ..structures.detectors.fibonacci import IncrementalFibonacci

    high = 100.0
    low = 50.0
    range_val = high - low  # 50

    # Expected levels
    expected = {
        0.382: 100 - (0.382 * 50),  # 80.9
        0.500: 100 - (0.500 * 50),  # 75.0
        0.618: 100 - (0.618 * 50),  # 69.1
    }

    # Create mock swing dependency that provides fixed anchors
    class MockSwing:
        def get_value(self, key):
            values = {
                "high_level": high,
                "low_level": low,
                "high_idx": 50,
                "low_idx": 30,
                "pair_high_level": high,
                "pair_low_level": low,
                "pair_anchor_hash": "test_hash",
                "version": 1,
            }
            return values.get(key)

    detector = IncrementalFibonacci(
        params={
            "levels": [0.382, 0.5, 0.618],
            "mode": "retracement",
            "use_paired_anchor": False,
        },
        deps={"swing": MockSwing()},
    )

    # Update detector
    bar = {"open": 75, "high": 76, "low": 74, "close": 75, "timestamp": datetime.now()}
    detector.update(0, bar)

    # Check levels
    errors = []
    for ratio, expected_level in expected.items():
        key = f"level_{ratio}"
        actual_level = detector.get_value(key)

        if actual_level is None:
            errors.append(f"{key}: None (expected {expected_level:.1f})")
        elif abs(actual_level - expected_level) > 0.1:
            errors.append(f"{key}: {actual_level:.1f} (expected {expected_level:.1f})")

    passed = len(errors) == 0

    return StructureTestResult(
        name="fib_retracement_levels",
        passed=passed,
        expected="All levels within 0.1 of hand-calculated values",
        actual="; ".join(errors) if errors else "All levels correct",
    )


def test_fib_extension_levels() -> StructureTestResult:
    """
    Test: Fibonacci extension levels are calculated correctly.

    For bullish swing (extension mode with "bullish" direction), targets above high.
    Formula: level = high + (ratio * range)

    Hand calculation (bullish, high=100, low=50, range=50):
        0.272: 100 + (0.272 * 50) = 113.6
        0.618: 100 + (0.618 * 50) = 130.9
        1.000: 100 + (1.000 * 50) = 150.0
    """
    from ..structures.detectors.fibonacci import IncrementalFibonacci
    from ..structures.base import BarData

    high = 100.0
    low = 50.0

    # Expected extension levels (above high for bullish)
    # Using positive ratios for extension mode
    expected = {
        0.272: 100 + (0.272 * 50),  # 113.6
        0.618: 100 + (0.618 * 50),  # 130.9
        1.0: 100 + (1.0 * 50),      # 150.0
    }

    class MockSwing:
        def get_value(self, key):
            values = {
                "high_level": high,
                "low_level": low,
                "high_idx": 50,
                "low_idx": 30,
                "pair_high_level": high,
                "pair_low_level": low,
                "pair_direction": "bullish",  # String, not int
                "pair_anchor_hash": "test_hash",
                "pair_version": 1,
                "version": 1,
            }
            return values.get(key)

    detector = IncrementalFibonacci(
        params={
            "levels": [0.272, 0.618, 1.0],  # Positive ratios for extension mode
            "mode": "extension",
            "use_paired_anchor": True,
        },
        deps={"swing": MockSwing()},
    )

    bar = BarData(idx=0, open=75, high=76, low=74, close=75, volume=1000, indicators={})
    detector.update(0, bar)

    errors = []
    for ratio, expected_level in expected.items():
        # Format key same way as detector (removes trailing .0)
        key = f"level_{ratio:g}"
        actual_level = detector.get_value(key)

        if actual_level is None:
            errors.append(f"{key}: None (expected {expected_level:.1f})")
        elif abs(actual_level - expected_level) > 0.1:
            errors.append(f"{key}: {actual_level:.1f} (expected {expected_level:.1f})")

    passed = len(errors) == 0

    return StructureTestResult(
        name="fib_extension_levels",
        passed=passed,
        expected="All extension levels within 0.1 of hand-calculated values",
        actual="; ".join(errors) if errors else "All levels correct",
    )


def test_fib_ote_zone() -> StructureTestResult:
    """
    Test: OTE (Optimal Trade Entry) zone is the 62-79% retracement area.

    Hand calculation (high=100, low=50, range=50):
        62% retracement: 100 - (0.62 * 50) = 69.0
        79% retracement: 100 - (0.79 * 50) = 60.5

    OTE zone for long entry: 60.5 to 69.0
    """
    from ..structures.detectors.fibonacci import IncrementalFibonacci

    high = 100.0
    low = 50.0

    # OTE is typically 0.618 to 0.786 retracement
    ote_upper = 100 - (0.618 * 50)  # 69.1
    ote_lower = 100 - (0.786 * 50)  # 60.7

    class MockSwing:
        def get_value(self, key):
            values = {
                "high_level": high,
                "low_level": low,
                "high_idx": 50,
                "low_idx": 30,
                "pair_high_level": high,
                "pair_low_level": low,
                "pair_anchor_hash": "test_hash",
                "version": 1,
            }
            return values.get(key)

    detector = IncrementalFibonacci(
        params={
            "levels": [0.618, 0.786],
            "mode": "retracement",
            "use_paired_anchor": False,
        },
        deps={"swing": MockSwing()},
    )

    bar = {"open": 65, "high": 66, "low": 64, "close": 65, "timestamp": datetime.now()}
    detector.update(0, bar)

    level_618 = detector.get_value("level_0.618")
    level_786 = detector.get_value("level_0.786")

    errors = []
    if level_618 is None or abs(level_618 - ote_upper) > 0.1:
        errors.append(f"OTE upper: {level_618} (expected {ote_upper:.1f})")
    if level_786 is None or abs(level_786 - ote_lower) > 0.1:
        errors.append(f"OTE lower: {level_786} (expected {ote_lower:.1f})")

    passed = len(errors) == 0

    return StructureTestResult(
        name="fib_ote_zone",
        passed=passed,
        expected=f"OTE zone: {ote_lower:.1f} to {ote_upper:.1f}",
        actual="; ".join(errors) if errors else f"OTE zone: {level_786:.1f} to {level_618:.1f}",
    )


# =============================================================================
# Zone Detection Tests
# =============================================================================

def test_demand_zone_bounds() -> StructureTestResult:
    """
    Test: Demand zone is calculated correctly from swing low.

    Formula:
        lower = swing_low - (ATR * width_atr)
        upper = swing_low

    Hand calculation (swing_low=95, ATR=2.0, width_atr=1.5):
        lower = 95 - (2.0 * 1.5) = 92.0
        upper = 95.0
    """
    from ..structures.detectors.zone import IncrementalZone
    from ..structures.base import BarData

    swing_low = 95.0
    atr = 2.0
    width_atr = 1.5

    expected_lower = swing_low - (atr * width_atr)  # 92.0
    expected_upper = swing_low  # 95.0

    class MockSwing:
        def get_value(self, key):
            values = {
                "low_level": swing_low,
                "low_idx": 30,  # Initial swing
            }
            return values.get(key)

    detector = IncrementalZone(
        params={
            "zone_type": "demand",
            "width_atr": width_atr,
            "atr_key": "atr",
        },
        deps={"swing": MockSwing()},
    )

    # Update with bar inside zone - include ATR in indicators
    bar = BarData(
        idx=31,
        open=94.0,
        high=95.0,
        low=93.0,
        close=94.0,
        volume=1000.0,
        indicators={"atr": atr},
    )
    detector.update(31, bar)

    actual_lower = detector.get_value("lower")
    actual_upper = detector.get_value("upper")

    errors = []
    if actual_lower is None or abs(actual_lower - expected_lower) > 0.1:
        errors.append(f"lower: {actual_lower} (expected {expected_lower})")
    if actual_upper is None or abs(actual_upper - expected_upper) > 0.1:
        errors.append(f"upper: {actual_upper} (expected {expected_upper})")

    passed = len(errors) == 0

    return StructureTestResult(
        name="demand_zone_bounds",
        passed=passed,
        expected=f"Demand zone: {expected_lower} to {expected_upper}",
        actual="; ".join(errors) if errors else f"Zone: {actual_lower} to {actual_upper}",
    )


def test_supply_zone_bounds() -> StructureTestResult:
    """
    Test: Supply zone is calculated correctly from swing high.

    Formula:
        lower = swing_high
        upper = swing_high + (ATR * width_atr)

    Hand calculation (swing_high=105, ATR=2.0, width_atr=1.5):
        lower = 105.0
        upper = 105 + (2.0 * 1.5) = 108.0
    """
    from ..structures.detectors.zone import IncrementalZone
    from ..structures.base import BarData

    swing_high = 105.0
    atr = 2.0
    width_atr = 1.5

    expected_lower = swing_high  # 105.0
    expected_upper = swing_high + (atr * width_atr)  # 108.0

    class MockSwing:
        def get_value(self, key):
            values = {
                "high_level": swing_high,
                "high_idx": 30,
            }
            return values.get(key)

    detector = IncrementalZone(
        params={
            "zone_type": "supply",
            "width_atr": width_atr,
            "atr_key": "atr",
        },
        deps={"swing": MockSwing()},
    )

    bar = BarData(
        idx=31,
        open=106.0,
        high=107.0,
        low=105.0,
        close=106.0,
        volume=1000.0,
        indicators={"atr": atr},
    )
    detector.update(31, bar)

    actual_lower = detector.get_value("lower")
    actual_upper = detector.get_value("upper")

    errors = []
    if actual_lower is None or abs(actual_lower - expected_lower) > 0.1:
        errors.append(f"lower: {actual_lower} (expected {expected_lower})")
    if actual_upper is None or abs(actual_upper - expected_upper) > 0.1:
        errors.append(f"upper: {actual_upper} (expected {expected_upper})")

    passed = len(errors) == 0

    return StructureTestResult(
        name="supply_zone_bounds",
        passed=passed,
        expected=f"Supply zone: {expected_lower} to {expected_upper}",
        actual="; ".join(errors) if errors else f"Zone: {actual_lower} to {actual_upper}",
    )


# =============================================================================
# Trend Detection Tests
# =============================================================================

def test_trend_uptrend_detection() -> StructureTestResult:
    """
    Test: Trend detector identifies uptrend from HH/HL pattern.

    Setup: Engineered data with higher highs and higher lows.
    Expected: direction = 1 (bullish)
    """
    from ..structures.detectors.trend import IncrementalTrend
    from ..structures.detectors.swing import IncrementalSwing

    np.random.seed(42)  # For reproducibility
    bars = generate_uptrend_data(num_bars=100)

    # Create swing detector first (trend depends on it)
    swing_detector = IncrementalSwing(
        params={
            "left": 5,
            "right": 5,
            "mode": "fractal",
        },
        deps={},
    )

    trend_detector = IncrementalTrend(
        params={
            "min_waves": 2,
        },
        deps={"swing": swing_detector},
    )

    # Process all bars - convert dict to BarData
    from ..structures.base import BarData
    for i, bar_dict in enumerate(bars):
        bar = BarData(
            idx=i,
            open=bar_dict["open"],
            high=bar_dict["high"],
            low=bar_dict["low"],
            close=bar_dict["close"],
            volume=bar_dict["volume"],
            indicators={},
        )
        swing_detector.update(i, bar)
        trend_detector.update(i, bar)

    direction = trend_detector.get_value("direction")

    # Direction should be 1 (bullish) for uptrend
    passed = direction == 1

    return StructureTestResult(
        name="trend_uptrend_detection",
        passed=passed,
        expected="direction = 1 (bullish)",
        actual=f"direction = {direction}",
    )


def test_trend_downtrend_detection() -> StructureTestResult:
    """
    Test: Trend detector identifies downtrend from LH/LL pattern.

    Setup: Engineered data with lower highs and lower lows.
    Expected: direction = -1 (bearish)
    """
    from ..structures.detectors.trend import IncrementalTrend
    from ..structures.detectors.swing import IncrementalSwing

    np.random.seed(42)
    bars = generate_downtrend_data(num_bars=100)

    swing_detector = IncrementalSwing(
        params={
            "left": 5,
            "right": 5,
            "mode": "fractal",
        },
        deps={},
    )

    trend_detector = IncrementalTrend(
        params={
            "min_waves": 2,
        },
        deps={"swing": swing_detector},
    )

    # Process all bars - convert dict to BarData
    from ..structures.base import BarData
    for i, bar_dict in enumerate(bars):
        bar = BarData(
            idx=i,
            open=bar_dict["open"],
            high=bar_dict["high"],
            low=bar_dict["low"],
            close=bar_dict["close"],
            volume=bar_dict["volume"],
            indicators={},
        )
        swing_detector.update(i, bar)
        trend_detector.update(i, bar)

    direction = trend_detector.get_value("direction")

    passed = direction == -1

    return StructureTestResult(
        name="trend_downtrend_detection",
        passed=passed,
        expected="direction = -1 (bearish)",
        actual=f"direction = {direction}",
    )


# =============================================================================
# Run All Tests
# =============================================================================

def run_all_structure_tests() -> list[StructureTestResult]:
    """Run all structure validation tests."""
    tests = [
        # Swing tests
        test_swing_high_detection,
        test_swing_low_detection,
        test_swing_alternation,
        # Fibonacci tests
        test_fib_retracement_levels,
        test_fib_extension_levels,
        test_fib_ote_zone,
        # Zone tests
        test_demand_zone_bounds,
        test_supply_zone_bounds,
        # Trend tests
        test_trend_uptrend_detection,
        test_trend_downtrend_detection,
    ]

    results = []
    for test_fn in tests:
        try:
            result = test_fn()
            results.append(result)
        except Exception as e:
            results.append(StructureTestResult(
                name=test_fn.__name__,
                passed=False,
                expected="Test to run",
                actual="",
                error_msg=str(e),
            ))

    return results


def format_structure_test_report(results: list[StructureTestResult]) -> str:
    """Format structure test results as report."""
    lines = []
    lines.append("=" * 60)
    lines.append("MARKET STRUCTURE VALIDATION")
    lines.append("=" * 60)

    passed = sum(1 for r in results if r.passed)
    total = len(results)

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        lines.append(f"{status}: {r.name}")
        if not r.passed:
            lines.append(f"       Expected: {r.expected}")
            lines.append(f"       Actual:   {r.actual}")
            if r.error_msg:
                lines.append(f"       Error:    {r.error_msg}")

    lines.append("-" * 60)
    lines.append(f"TOTAL: {passed}/{total} passed")

    if passed == total:
        lines.append("All structure detection is CORRECT")
    else:
        lines.append("STRUCTURE ERRORS DETECTED")

    lines.append("=" * 60)

    return "\n".join(lines)
