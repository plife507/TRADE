"""
Fill Timing Validator: Proves fills happen at correct prices/times.

Key rules validated:
1. Signal at bar N → Fill at bar N+1 open (no same-bar fills)
2. Fill price = bar N+1 open (+ slippage within configured BPS)
3. No look-ahead in fill execution

Usage:
    from src.testing_agent.fill_validator import validate_fill_timing

    result = validate_fill_timing(trades, signals, candles, slippage_bps=2)
    if result.passed:
        print("All fills correct")
    else:
        for v in result.violations:
            print(f"Violation: {v}")
"""

from dataclasses import dataclass, field
from typing import Any
import pandas as pd

from ..utils.logger import get_logger

logger = get_logger()


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class FillViolation:
    """A single fill timing violation."""
    trade_id: int | str
    violation_type: str  # "same_bar", "wrong_bar", "price_slippage", "wrong_price"
    signal_bar: int
    fill_bar: int
    expected_fill_bar: int
    signal_price: float  # Close at signal bar
    fill_price: float
    expected_fill_price: float  # Open at expected fill bar
    slippage_bps: float = 0.0
    allowed_slippage_bps: float = 0.0
    notes: str = ""


@dataclass
class FillTimingResult:
    """Result from fill timing validation."""
    passed: bool
    trades_checked: int = 0
    violations: list[FillViolation] = field(default_factory=list)
    same_bar_fills: int = 0
    wrong_bar_fills: int = 0
    slippage_violations: int = 0
    price_violations: int = 0
    max_slippage_bps: float = 0.0
    avg_slippage_bps: float = 0.0


# =============================================================================
# Validation Functions
# =============================================================================

def validate_fill_timing(
    trades: list[dict[str, Any]],
    signals: list[dict[str, Any]] | None = None,
    candles: pd.DataFrame | None = None,
    allowed_slippage_bps: float = 10.0,
    require_next_bar_fill: bool = True,
) -> FillTimingResult:
    """
    Validate that all fills occur at correct bar and price.

    Rules:
    1. If signal fires at bar N, fill must occur at bar N+1 (not bar N)
    2. Fill price must equal bar N+1 open (within slippage tolerance)
    3. Slippage must be within allowed_slippage_bps

    Args:
        trades: List of trade dicts with keys:
            - entry_bar: Bar index of entry fill
            - entry_price: Price of entry fill
            - signal_bar (optional): Bar index of entry signal
            - exit_bar: Bar index of exit fill
            - exit_price: Price of exit fill
        signals: Optional list of signal dicts for cross-reference
        candles: OHLCV DataFrame with columns: timestamp, open, high, low, close, volume
                 Index should align with bar indices in trades
        allowed_slippage_bps: Maximum allowed slippage in basis points
        require_next_bar_fill: If True, fills must be at bar N+1 (not N)

    Returns:
        FillTimingResult with pass/fail and violations
    """
    result = FillTimingResult(passed=True, trades_checked=0)

    if not trades:
        logger.info("No trades to validate")
        return result

    slippages = []

    for trade in trades:
        result.trades_checked += 1
        trade_id = trade.get("trade_id", trade.get("id", result.trades_checked))

        # Get entry details
        entry_bar = trade.get("entry_bar", trade.get("entry_bar_idx", -1))
        entry_price = trade.get("entry_price", 0.0)
        signal_bar = trade.get("signal_bar", entry_bar - 1 if require_next_bar_fill else entry_bar)

        # Validate entry fill timing
        if require_next_bar_fill:
            expected_fill_bar = signal_bar + 1

            # Check for same-bar fill (violation)
            if entry_bar == signal_bar:
                result.same_bar_fills += 1
                result.passed = False
                result.violations.append(FillViolation(
                    trade_id=trade_id,
                    violation_type="same_bar",
                    signal_bar=signal_bar,
                    fill_bar=entry_bar,
                    expected_fill_bar=expected_fill_bar,
                    signal_price=trade.get("signal_price", 0.0),
                    fill_price=entry_price,
                    expected_fill_price=0.0,  # Unknown without candles
                    notes="Entry fill on same bar as signal (look-ahead bias)",
                ))
                continue

            # Check for wrong bar fill
            if entry_bar != expected_fill_bar:
                result.wrong_bar_fills += 1
                result.passed = False
                result.violations.append(FillViolation(
                    trade_id=trade_id,
                    violation_type="wrong_bar",
                    signal_bar=signal_bar,
                    fill_bar=entry_bar,
                    expected_fill_bar=expected_fill_bar,
                    signal_price=trade.get("signal_price", 0.0),
                    fill_price=entry_price,
                    expected_fill_price=0.0,
                    notes=f"Entry fill at bar {entry_bar}, expected bar {expected_fill_bar}",
                ))
                continue

        # Validate fill price against candle open (if candles provided)
        if candles is not None and len(candles) > entry_bar:
            expected_price = candles.iloc[entry_bar]["open"]

            # Calculate slippage
            if expected_price > 0:
                slippage_pct = abs(entry_price - expected_price) / expected_price * 100
                slippage_bps = slippage_pct * 100  # Convert to basis points

                slippages.append(slippage_bps)

                if slippage_bps > result.max_slippage_bps:
                    result.max_slippage_bps = slippage_bps

                if slippage_bps > allowed_slippage_bps:
                    result.slippage_violations += 1
                    result.passed = False
                    result.violations.append(FillViolation(
                        trade_id=trade_id,
                        violation_type="price_slippage",
                        signal_bar=signal_bar,
                        fill_bar=entry_bar,
                        expected_fill_bar=entry_bar,
                        signal_price=candles.iloc[signal_bar]["close"] if signal_bar < len(candles) else 0.0,
                        fill_price=entry_price,
                        expected_fill_price=expected_price,
                        slippage_bps=slippage_bps,
                        allowed_slippage_bps=allowed_slippage_bps,
                        notes=f"Slippage {slippage_bps:.1f} BPS exceeds allowed {allowed_slippage_bps} BPS",
                    ))

        # Validate exit fill timing (SL/TP can execute on same bar as trigger)
        exit_bar = trade.get("exit_bar", trade.get("exit_bar_idx", -1))
        exit_price = trade.get("exit_price", 0.0)
        exit_reason = trade.get("exit_reason", "")

        # For signal-based exits, same rule applies
        if exit_reason == "signal" and require_next_bar_fill:
            exit_signal_bar = trade.get("exit_signal_bar", exit_bar - 1)
            if exit_bar == exit_signal_bar:
                result.same_bar_fills += 1
                result.passed = False
                result.violations.append(FillViolation(
                    trade_id=trade_id,
                    violation_type="same_bar",
                    signal_bar=exit_signal_bar,
                    fill_bar=exit_bar,
                    expected_fill_bar=exit_signal_bar + 1,
                    signal_price=0.0,
                    fill_price=exit_price,
                    expected_fill_price=0.0,
                    notes="Exit fill on same bar as exit signal",
                ))

    # Calculate average slippage
    if slippages:
        result.avg_slippage_bps = sum(slippages) / len(slippages)

    return result


def validate_sl_tp_execution(
    trades: list[dict[str, Any]],
    candles: pd.DataFrame,
    sl_tolerance_pct: float = 0.5,
    tp_tolerance_pct: float = 0.5,
) -> FillTimingResult:
    """
    Validate that SL/TP exits occur at the correct bar and price.

    For a long position:
    - SL should trigger when low <= sl_price
    - TP should trigger when high >= tp_price

    For a short position:
    - SL should trigger when high >= sl_price
    - TP should trigger when low <= tp_price

    Args:
        trades: List of trade dicts with sl_price, tp_price, exit_reason
        candles: OHLCV DataFrame
        sl_tolerance_pct: Allowed tolerance for SL price matching
        tp_tolerance_pct: Allowed tolerance for TP price matching

    Returns:
        FillTimingResult with SL/TP validation
    """
    result = FillTimingResult(passed=True, trades_checked=0)

    for trade in trades:
        result.trades_checked += 1
        trade_id = trade.get("trade_id", result.trades_checked)

        exit_reason = trade.get("exit_reason", "").lower()
        if exit_reason not in ("sl", "tp", "stop_loss", "take_profit"):
            continue  # Not an SL/TP exit

        direction = trade.get("direction", "long").lower()
        entry_bar = trade.get("entry_bar", 0)
        exit_bar = trade.get("exit_bar", -1)
        exit_price = trade.get("exit_price", 0.0)
        sl_price = trade.get("sl_price", 0.0)
        tp_price = trade.get("tp_price", 0.0)

        if exit_bar < 0 or exit_bar >= len(candles):
            continue

        bar = candles.iloc[exit_bar]

        # Validate SL execution
        if exit_reason in ("sl", "stop_loss"):
            if direction == "long":
                # SL triggers when low <= sl_price
                trigger_price = bar["low"]
                should_trigger = trigger_price <= sl_price
            else:
                # Short: SL triggers when high >= sl_price
                trigger_price = bar["high"]
                should_trigger = trigger_price >= sl_price

            if not should_trigger:
                # SL executed but shouldn't have
                result.price_violations += 1
                result.passed = False
                result.violations.append(FillViolation(
                    trade_id=trade_id,
                    violation_type="wrong_price",
                    signal_bar=entry_bar,
                    fill_bar=exit_bar,
                    expected_fill_bar=exit_bar,
                    signal_price=sl_price,
                    fill_price=exit_price,
                    expected_fill_price=sl_price,
                    notes=f"SL triggered at bar {exit_bar} but price didn't breach SL level",
                ))

            # Check execution price is near SL price
            price_diff_pct = abs(exit_price - sl_price) / sl_price * 100 if sl_price > 0 else 0
            if price_diff_pct > sl_tolerance_pct:
                result.price_violations += 1
                result.passed = False
                result.violations.append(FillViolation(
                    trade_id=trade_id,
                    violation_type="price_slippage",
                    signal_bar=entry_bar,
                    fill_bar=exit_bar,
                    expected_fill_bar=exit_bar,
                    signal_price=sl_price,
                    fill_price=exit_price,
                    expected_fill_price=sl_price,
                    slippage_bps=price_diff_pct * 100,
                    notes=f"SL fill price differs by {price_diff_pct:.2f}% from SL level",
                ))

        # Validate TP execution
        elif exit_reason in ("tp", "take_profit"):
            if direction == "long":
                # TP triggers when high >= tp_price
                trigger_price = bar["high"]
                should_trigger = trigger_price >= tp_price
            else:
                # Short: TP triggers when low <= tp_price
                trigger_price = bar["low"]
                should_trigger = trigger_price <= tp_price

            if not should_trigger:
                result.price_violations += 1
                result.passed = False
                result.violations.append(FillViolation(
                    trade_id=trade_id,
                    violation_type="wrong_price",
                    signal_bar=entry_bar,
                    fill_bar=exit_bar,
                    expected_fill_bar=exit_bar,
                    signal_price=tp_price,
                    fill_price=exit_price,
                    expected_fill_price=tp_price,
                    notes=f"TP triggered at bar {exit_bar} but price didn't reach TP level",
                ))

            price_diff_pct = abs(exit_price - tp_price) / tp_price * 100 if tp_price > 0 else 0
            if price_diff_pct > tp_tolerance_pct:
                result.price_violations += 1
                result.passed = False
                result.violations.append(FillViolation(
                    trade_id=trade_id,
                    violation_type="price_slippage",
                    signal_bar=entry_bar,
                    fill_bar=exit_bar,
                    expected_fill_bar=exit_bar,
                    signal_price=tp_price,
                    fill_price=exit_price,
                    expected_fill_price=tp_price,
                    slippage_bps=price_diff_pct * 100,
                    notes=f"TP fill price differs by {price_diff_pct:.2f}% from TP level",
                ))

    return result


def find_earliest_sl_tp_bar(
    candles: pd.DataFrame,
    entry_bar: int,
    entry_price: float,
    sl_pct: float,
    tp_pct: float,
    direction: str = "long",
) -> tuple[int, str]:
    """
    Find the earliest bar where SL or TP would be hit.

    Args:
        candles: OHLCV DataFrame
        entry_bar: Bar index of entry
        entry_price: Entry price
        sl_pct: Stop loss percentage
        tp_pct: Take profit percentage
        direction: "long" or "short"

    Returns:
        Tuple of (bar_index, "sl" or "tp")
        Returns (-1, "") if neither hit
    """
    if direction == "long":
        sl_price = entry_price * (1 - sl_pct / 100)
        tp_price = entry_price * (1 + tp_pct / 100)

        for i in range(entry_bar + 1, len(candles)):
            bar = candles.iloc[i]
            # Check SL first (worse outcome)
            if bar["low"] <= sl_price:
                return (i, "sl")
            if bar["high"] >= tp_price:
                return (i, "tp")
    else:
        sl_price = entry_price * (1 + sl_pct / 100)
        tp_price = entry_price * (1 - tp_pct / 100)

        for i in range(entry_bar + 1, len(candles)):
            bar = candles.iloc[i]
            if bar["high"] >= sl_price:
                return (i, "sl")
            if bar["low"] <= tp_price:
                return (i, "tp")

    return (-1, "")


def validate_sl_tp_timing(
    trades: list[dict[str, Any]],
    candles: pd.DataFrame,
) -> FillTimingResult:
    """
    Validate that SL/TP triggers at the earliest possible bar.

    This catches bugs where SL/TP triggers late.

    Args:
        trades: List of trades with sl_pct, tp_pct, entry details
        candles: OHLCV DataFrame

    Returns:
        FillTimingResult with timing validation
    """
    result = FillTimingResult(passed=True, trades_checked=0)

    for trade in trades:
        result.trades_checked += 1
        trade_id = trade.get("trade_id", result.trades_checked)

        exit_reason = trade.get("exit_reason", "").lower()
        if exit_reason not in ("sl", "tp", "stop_loss", "take_profit"):
            continue

        direction = trade.get("direction", "long")
        entry_bar = trade.get("entry_bar", 0)
        entry_price = trade.get("entry_price", 0.0)
        exit_bar = trade.get("exit_bar", -1)
        sl_pct = trade.get("sl_pct", 3.0)
        tp_pct = trade.get("tp_pct", 6.0)

        # Find when SL/TP should have triggered
        earliest_bar, earliest_type = find_earliest_sl_tp_bar(
            candles, entry_bar, entry_price, sl_pct, tp_pct, direction
        )

        if earliest_bar > 0 and exit_bar > earliest_bar:
            # Exit happened later than it should have
            result.wrong_bar_fills += 1
            result.passed = False
            result.violations.append(FillViolation(
                trade_id=trade_id,
                violation_type="wrong_bar",
                signal_bar=entry_bar,
                fill_bar=exit_bar,
                expected_fill_bar=earliest_bar,
                signal_price=entry_price,
                fill_price=trade.get("exit_price", 0.0),
                expected_fill_price=0.0,
                notes=f"{earliest_type.upper()} should have triggered at bar {earliest_bar}, but triggered at {exit_bar}",
            ))

    return result
