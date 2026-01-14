"""
Engine Validator for Functional Tests.

Validates engine behavior against expected outcomes.

Categories:
A. Signal Generation - signals occur as expected
B. Position Management - positions open/close correctly
C. Trade Recording - trades have valid data
D. Indicator Consistency - no NaN/Inf, correct computation
E. Edge Cases - boundary conditions handled
"""

from dataclasses import dataclass, field
from typing import Any
import math


@dataclass
class ValidationResult:
    """Result from a single validation check."""

    name: str
    passed: bool
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
        }


class EngineValidator:
    """
    Validates engine behavior against expected outcomes.

    Assertion Categories:
    A - Signal Generation
    B - Position Management
    C - Trade Recording
    D - Indicator Consistency
    E - Edge Cases
    """

    def validate_all(
        self,
        backtest_result: Any,
        play: Any,
    ) -> list[ValidationResult]:
        """
        Run all validation checks on a backtest result.

        Args:
            backtest_result: Result from run_backtest_with_gates
            play: Play configuration

        Returns:
            List of ValidationResult
        """
        results: list[ValidationResult] = []

        # Category A: Signal Generation
        results.append(self.assert_signals_exist(backtest_result))

        # Category B: Position Management
        results.append(self.assert_no_phantom_positions(backtest_result))
        results.append(self.assert_positions_closed_properly(backtest_result))

        # Category C: Trade Recording
        results.append(self.assert_trades_have_required_fields(backtest_result))
        results.append(self.assert_trade_pnl_accurate(backtest_result))
        results.append(self.assert_trade_timestamps_monotonic(backtest_result))

        # Category D: Indicator Consistency
        results.append(self.assert_no_nan_in_results(backtest_result))

        # Category E: Edge Cases
        results.append(self.assert_equity_non_negative(backtest_result))

        return results

    # =========================================================================
    # Category A: Signal Generation
    # =========================================================================

    def assert_signals_exist(self, result: Any) -> ValidationResult:
        """Verify at least one signal was generated."""
        try:
            # Check via trade count (each trade requires entry signal)
            trade_count = 0
            if result.summary:
                trade_count = result.summary.trades_count or 0

            if trade_count > 0:
                return ValidationResult(
                    name="A.1 Signals Exist",
                    passed=True,
                    message=f"Generated {trade_count} trades from signals",
                )
            else:
                return ValidationResult(
                    name="A.1 Signals Exist",
                    passed=False,
                    message="No trades generated (no entry signals fired)",
                )

        except Exception as e:
            return ValidationResult(
                name="A.1 Signals Exist",
                passed=False,
                message=f"Validation error: {e}",
            )

    def assert_signal_count_in_range(
        self,
        result: Any,
        min_signals: int,
        max_signals: int,
    ) -> ValidationResult:
        """Verify signal count is within expected range."""
        try:
            trade_count = 0
            if result.summary:
                trade_count = result.summary.trades_count or 0

            in_range = min_signals <= trade_count <= max_signals

            return ValidationResult(
                name="A.2 Signal Count In Range",
                passed=in_range,
                message=f"{trade_count} trades (expected {min_signals}-{max_signals})",
                details={"trade_count": trade_count, "min": min_signals, "max": max_signals},
            )

        except Exception as e:
            return ValidationResult(
                name="A.2 Signal Count In Range",
                passed=False,
                message=f"Validation error: {e}",
            )

    # =========================================================================
    # Category B: Position Management
    # =========================================================================

    def assert_no_phantom_positions(self, result: Any) -> ValidationResult:
        """Every position must have a corresponding entry signal."""
        try:
            # This is inherently enforced by the engine architecture
            # A position can only be opened if a signal was generated
            # We verify by checking that all trades have entry data

            if not result.artifact_path:
                return ValidationResult(
                    name="B.1 No Phantom Positions",
                    passed=True,
                    message="No artifacts to check (skipped)",
                )

            import pandas as pd
            from pathlib import Path

            trades_path = Path(result.artifact_path) / "trades.parquet"
            if not trades_path.exists():
                return ValidationResult(
                    name="B.1 No Phantom Positions",
                    passed=True,
                    message="No trades file (no positions opened)",
                )

            trades_df = pd.read_parquet(trades_path)

            if trades_df.empty:
                return ValidationResult(
                    name="B.1 No Phantom Positions",
                    passed=True,
                    message="No trades (no positions)",
                )

            # Check that all trades have entry_time (indicating a real entry signal)
            missing_entry = trades_df["entry_time"].isna().sum() if "entry_time" in trades_df.columns else 0

            if missing_entry > 0:
                return ValidationResult(
                    name="B.1 No Phantom Positions",
                    passed=False,
                    message=f"{missing_entry} trades missing entry_time",
                )

            return ValidationResult(
                name="B.1 No Phantom Positions",
                passed=True,
                message=f"All {len(trades_df)} trades have entry data",
            )

        except Exception as e:
            return ValidationResult(
                name="B.1 No Phantom Positions",
                passed=False,
                message=f"Validation error: {e}",
            )

    def assert_positions_closed_properly(self, result: Any) -> ValidationResult:
        """All positions must be closed at end of backtest."""
        try:
            if not result.artifact_path:
                return ValidationResult(
                    name="B.2 Positions Closed",
                    passed=True,
                    message="No artifacts to check",
                )

            import pandas as pd
            from pathlib import Path

            trades_path = Path(result.artifact_path) / "trades.parquet"
            if not trades_path.exists():
                return ValidationResult(
                    name="B.2 Positions Closed",
                    passed=True,
                    message="No trades file",
                )

            trades_df = pd.read_parquet(trades_path)

            if trades_df.empty:
                return ValidationResult(
                    name="B.2 Positions Closed",
                    passed=True,
                    message="No trades",
                )

            # Check that all trades have exit_time
            if "exit_time" not in trades_df.columns:
                return ValidationResult(
                    name="B.2 Positions Closed",
                    passed=False,
                    message="Trades missing exit_time column",
                )

            open_positions = trades_df["exit_time"].isna().sum()

            if open_positions > 0:
                return ValidationResult(
                    name="B.2 Positions Closed",
                    passed=False,
                    message=f"{open_positions} positions still open at end",
                )

            return ValidationResult(
                name="B.2 Positions Closed",
                passed=True,
                message=f"All {len(trades_df)} positions closed",
            )

        except Exception as e:
            return ValidationResult(
                name="B.2 Positions Closed",
                passed=False,
                message=f"Validation error: {e}",
            )

    # =========================================================================
    # Category C: Trade Recording
    # =========================================================================

    def assert_trades_have_required_fields(self, result: Any) -> ValidationResult:
        """Trades have all required fields."""
        required_fields = [
            "entry_time",
            "exit_time",
            "side",
            "entry_price",
            "exit_price",
            "net_pnl",
        ]

        try:
            if not result.artifact_path:
                return ValidationResult(
                    name="C.1 Trade Fields",
                    passed=True,
                    message="No artifacts to check",
                )

            import pandas as pd
            from pathlib import Path

            trades_path = Path(result.artifact_path) / "trades.parquet"
            if not trades_path.exists():
                return ValidationResult(
                    name="C.1 Trade Fields",
                    passed=True,
                    message="No trades file",
                )

            trades_df = pd.read_parquet(trades_path)

            if trades_df.empty:
                return ValidationResult(
                    name="C.1 Trade Fields",
                    passed=True,
                    message="No trades",
                )

            missing = [f for f in required_fields if f not in trades_df.columns]

            if missing:
                return ValidationResult(
                    name="C.1 Trade Fields",
                    passed=False,
                    message=f"Missing fields: {missing}",
                )

            return ValidationResult(
                name="C.1 Trade Fields",
                passed=True,
                message="All required fields present",
            )

        except Exception as e:
            return ValidationResult(
                name="C.1 Trade Fields",
                passed=False,
                message=f"Validation error: {e}",
            )

    def assert_trade_pnl_accurate(self, result: Any, tolerance: float = 0.01) -> ValidationResult:
        """Trade PnL matches entry/exit price delta (within tolerance)."""
        try:
            if not result.artifact_path:
                return ValidationResult(
                    name="C.2 PnL Accuracy",
                    passed=True,
                    message="No artifacts to check",
                )

            import pandas as pd
            from pathlib import Path

            trades_path = Path(result.artifact_path) / "trades.parquet"
            if not trades_path.exists():
                return ValidationResult(
                    name="C.2 PnL Accuracy",
                    passed=True,
                    message="No trades file",
                )

            trades_df = pd.read_parquet(trades_path)

            if trades_df.empty:
                return ValidationResult(
                    name="C.2 PnL Accuracy",
                    passed=True,
                    message="No trades",
                )

            # Check required columns
            required = ["entry_price", "exit_price", "net_pnl", "entry_size_usdt", "side"]
            missing = [c for c in required if c not in trades_df.columns]
            if missing:
                return ValidationResult(
                    name="C.2 PnL Accuracy",
                    passed=False,
                    message=f"Missing columns for PnL check: {missing}",
                )

            # Calculate expected PnL for each trade
            # PnL = size * (exit - entry) / entry for longs
            # PnL = size * (entry - exit) / entry for shorts
            errors = []
            for idx, row in trades_df.iterrows():
                entry_p = row["entry_price"]
                exit_p = row["exit_price"]
                size = row["entry_size_usdt"]
                actual_pnl = row["net_pnl"]
                side = str(row["side"]).lower()

                if entry_p <= 0 or size <= 0:
                    continue

                # Gross PnL calculation (before fees)
                if "long" in side or side == "buy":
                    gross_pnl = size * (exit_p - entry_p) / entry_p
                else:
                    gross_pnl = size * (entry_p - exit_p) / entry_p

                # Allow for fees (actual should be less than or equal to gross)
                # Use both absolute and relative tolerance
                # - Fees typically ~0.11% round-trip (0.055% x 2)
                # - For $1000 trade, fees are ~$1.10
                pnl_diff = abs(actual_pnl - gross_pnl)

                # Expected max fee: ~0.12% of position (taker + slippage)
                expected_max_fee = size * 0.0012 * 2  # Entry + exit fees

                # Tolerance: either within expected fee range OR 25% relative
                # (25% handles small PnL trades where fees dominate)
                relative_diff = pnl_diff / max(abs(gross_pnl), abs(actual_pnl), 1.0) if max(abs(gross_pnl), abs(actual_pnl)) > 0 else 0

                # Pass if: difference is within expected fees OR relative diff < 25%
                if pnl_diff > expected_max_fee and relative_diff > 0.25:
                    errors.append(f"Trade {idx}: expected ~{gross_pnl:.2f}, got {actual_pnl:.2f}")

            if errors:
                return ValidationResult(
                    name="C.2 PnL Accuracy",
                    passed=False,
                    message=f"{len(errors)} trades with PnL mismatch",
                    details={"errors": errors[:5]},  # First 5 errors
                )

            return ValidationResult(
                name="C.2 PnL Accuracy",
                passed=True,
                message=f"All {len(trades_df)} trade PnLs accurate",
            )

        except Exception as e:
            return ValidationResult(
                name="C.2 PnL Accuracy",
                passed=False,
                message=f"Validation error: {e}",
            )

    def assert_trade_timestamps_monotonic(self, result: Any) -> ValidationResult:
        """Trade entry/exit timestamps are monotonically increasing."""
        try:
            if not result.artifact_path:
                return ValidationResult(
                    name="C.3 Timestamps Monotonic",
                    passed=True,
                    message="No artifacts to check",
                )

            import pandas as pd
            from pathlib import Path

            trades_path = Path(result.artifact_path) / "trades.parquet"
            if not trades_path.exists():
                return ValidationResult(
                    name="C.3 Timestamps Monotonic",
                    passed=True,
                    message="No trades file",
                )

            trades_df = pd.read_parquet(trades_path)

            if len(trades_df) < 2:
                return ValidationResult(
                    name="C.3 Timestamps Monotonic",
                    passed=True,
                    message=f"Only {len(trades_df)} trades (skipped)",
                )

            # Sort by entry_time and check monotonicity
            if "entry_time" not in trades_df.columns:
                return ValidationResult(
                    name="C.3 Timestamps Monotonic",
                    passed=False,
                    message="Missing entry_time column",
                )

            trades_sorted = trades_df.sort_values("entry_time")
            is_monotonic = trades_sorted["entry_time"].is_monotonic_increasing

            # Also check that exit_time >= entry_time for each trade
            if "exit_time" in trades_df.columns:
                invalid_exits = (trades_df["exit_time"] < trades_df["entry_time"]).sum()
                if invalid_exits > 0:
                    return ValidationResult(
                        name="C.3 Timestamps Monotonic",
                        passed=False,
                        message=f"{invalid_exits} trades with exit before entry",
                    )

            if not is_monotonic:
                return ValidationResult(
                    name="C.3 Timestamps Monotonic",
                    passed=False,
                    message="Trade entry times not monotonically increasing",
                )

            return ValidationResult(
                name="C.3 Timestamps Monotonic",
                passed=True,
                message=f"All {len(trades_df)} trade timestamps valid",
            )

        except Exception as e:
            return ValidationResult(
                name="C.3 Timestamps Monotonic",
                passed=False,
                message=f"Validation error: {e}",
            )

    # =========================================================================
    # Category D: Indicator Consistency
    # =========================================================================

    def assert_no_nan_in_results(self, result: Any) -> ValidationResult:
        """No NaN or Inf in trade results."""
        try:
            if not result.artifact_path:
                return ValidationResult(
                    name="D.1 No NaN/Inf",
                    passed=True,
                    message="No artifacts to check",
                )

            import pandas as pd
            from pathlib import Path

            trades_path = Path(result.artifact_path) / "trades.parquet"
            if not trades_path.exists():
                return ValidationResult(
                    name="D.1 No NaN/Inf",
                    passed=True,
                    message="No trades file",
                )

            trades_df = pd.read_parquet(trades_path)

            if trades_df.empty:
                return ValidationResult(
                    name="D.1 No NaN/Inf",
                    passed=True,
                    message="No trades",
                )

            # Check numeric columns for NaN/Inf
            numeric_cols = trades_df.select_dtypes(include=["number"]).columns
            issues = []

            for col in numeric_cols:
                nan_count = trades_df[col].isna().sum()
                if nan_count > 0:
                    issues.append(f"{col}: {nan_count} NaN")

                inf_count = trades_df[col].apply(lambda x: math.isinf(x) if isinstance(x, float) else False).sum()
                if inf_count > 0:
                    issues.append(f"{col}: {inf_count} Inf")

            if issues:
                return ValidationResult(
                    name="D.1 No NaN/Inf",
                    passed=False,
                    message="; ".join(issues[:5]),
                )

            return ValidationResult(
                name="D.1 No NaN/Inf",
                passed=True,
                message="No NaN/Inf in numeric columns",
            )

        except Exception as e:
            return ValidationResult(
                name="D.1 No NaN/Inf",
                passed=False,
                message=f"Validation error: {e}",
            )

    # =========================================================================
    # Category E: Edge Cases
    # =========================================================================

    def assert_equity_non_negative(self, result: Any) -> ValidationResult:
        """Equity should never go negative."""
        try:
            if not result.artifact_path:
                return ValidationResult(
                    name="E.1 Equity Non-Negative",
                    passed=True,
                    message="No artifacts to check",
                )

            import pandas as pd
            from pathlib import Path

            equity_path = Path(result.artifact_path) / "equity.parquet"
            if not equity_path.exists():
                return ValidationResult(
                    name="E.1 Equity Non-Negative",
                    passed=True,
                    message="No equity file",
                )

            equity_df = pd.read_parquet(equity_path)

            if equity_df.empty:
                return ValidationResult(
                    name="E.1 Equity Non-Negative",
                    passed=True,
                    message="No equity data",
                )

            if "equity" not in equity_df.columns:
                return ValidationResult(
                    name="E.1 Equity Non-Negative",
                    passed=False,
                    message="Missing equity column",
                )

            negative_count = (equity_df["equity"] < 0).sum()

            if negative_count > 0:
                min_equity = equity_df["equity"].min()
                return ValidationResult(
                    name="E.1 Equity Non-Negative",
                    passed=False,
                    message=f"Equity went negative {negative_count} times (min: {min_equity:.2f})",
                )

            return ValidationResult(
                name="E.1 Equity Non-Negative",
                passed=True,
                message=f"Equity always >= 0 across {len(equity_df)} points",
            )

        except Exception as e:
            return ValidationResult(
                name="E.1 Equity Non-Negative",
                passed=False,
                message=f"Validation error: {e}",
            )

    def assert_final_equity_matches_summary(self, result: Any, tolerance: float = 0.01) -> ValidationResult:
        """Final equity in curve matches summary."""
        try:
            if not result.artifact_path or not result.summary:
                return ValidationResult(
                    name="E.2 Equity Consistency",
                    passed=True,
                    message="No artifacts/summary to check",
                )

            import pandas as pd
            from pathlib import Path

            equity_path = Path(result.artifact_path) / "equity.parquet"
            if not equity_path.exists():
                return ValidationResult(
                    name="E.2 Equity Consistency",
                    passed=True,
                    message="No equity file",
                )

            equity_df = pd.read_parquet(equity_path)

            if equity_df.empty:
                return ValidationResult(
                    name="E.2 Equity Consistency",
                    passed=True,
                    message="No equity data",
                )

            final_equity_curve = equity_df["equity"].iloc[-1]
            summary_pnl = result.summary.net_pnl_usdt or 0
            summary_start = result.summary.starting_equity_usdt or 10000

            expected_final = summary_start + summary_pnl
            diff = abs(final_equity_curve - expected_final)

            if diff > tolerance * expected_final:
                return ValidationResult(
                    name="E.2 Equity Consistency",
                    passed=False,
                    message=f"Curve final {final_equity_curve:.2f} != summary {expected_final:.2f}",
                )

            return ValidationResult(
                name="E.2 Equity Consistency",
                passed=True,
                message=f"Final equity {final_equity_curve:.2f} matches summary",
            )

        except Exception as e:
            return ValidationResult(
                name="E.2 Equity Consistency",
                passed=False,
                message=f"Validation error: {e}",
            )
