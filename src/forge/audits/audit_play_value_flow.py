"""
Audit: Play Value Flow Parity

Validates that Play configuration values flow correctly to engine components.
No silent defaults allowed - all values must be explicitly traceable.

Usage:
    python trade_cli.py backtest audit-value-flow --idea-card <card_id>

Checks:
1. slippage_bps: Play → ExecutionConfig
2. taker_fee_rate: Play → RiskProfileConfig (fees flow to risk profile, not execution)
3. maker_fee_bps: Play → strategy_params (for future limit order support)
4. maintenance_margin_rate: Play → RiskProfileConfig
5. min_trade_notional_usdt: Play → RiskProfileConfig
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.backtest.play import Play
    from src.backtest.engine import BacktestEngine


@dataclass
class ValueFlowCheck:
    """Result of a single value flow check."""
    name: str
    expected: float
    actual: float
    passed: bool
    source: str  # Where the value comes from
    target: str  # Where the value should flow to


@dataclass
class ValueFlowAuditResult:
    """Result of the value flow audit."""
    passed: bool
    checks: list[ValueFlowCheck]
    errors: list[str]

    @property
    def checks_passed(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def checks_total(self) -> int:
        return len(self.checks)

    def summary(self) -> str:
        """Return a summary string."""
        status = "PASSED" if self.passed else "FAILED"
        return f"{status}: {self.checks_passed}/{self.checks_total} value flow checks"


def audit_value_flow(
    play: "Play",
    engine: "BacktestEngine",
) -> ValueFlowAuditResult:
    """
    Audit that Play values flow correctly to engine configuration.

    Args:
        play: Source Play
        engine: Configured BacktestEngine

    Returns:
        ValueFlowAuditResult with check details
    """
    checks: list[ValueFlowCheck] = []
    errors: list[str] = []

    # Check 1: slippage_bps
    expected_slippage = play.account.slippage_bps if play.account.slippage_bps is not None else 5.0
    actual_slippage = engine.execution_config.slippage_bps
    slippage_check = ValueFlowCheck(
        name="slippage_bps",
        expected=expected_slippage,
        actual=actual_slippage,
        passed=abs(expected_slippage - actual_slippage) < 0.001,
        source="Play.account.slippage_bps",
        target="engine.execution_config.slippage_bps",
    )
    checks.append(slippage_check)
    if not slippage_check.passed:
        errors.append(
            f"slippage_bps mismatch: Play={expected_slippage}, Engine={actual_slippage}"
        )

    # Check 2: taker_fee_rate (fees flow to RiskProfileConfig, not ExecutionConfig)
    if play.account.fee_model:
        expected_taker_rate = play.account.fee_model.taker_rate  # decimal
        actual_taker_rate = engine.config.risk_profile.taker_fee_rate  # decimal
        taker_check = ValueFlowCheck(
            name="taker_fee_rate",
            expected=expected_taker_rate,
            actual=actual_taker_rate,
            passed=abs(expected_taker_rate - actual_taker_rate) < 0.000001,
            source="Play.account.fee_model.taker_rate",
            target="engine.config.risk_profile.taker_fee_rate",
        )
        checks.append(taker_check)
        if not taker_check.passed:
            errors.append(
                f"taker_fee_rate mismatch: Play={expected_taker_rate}, Engine={actual_taker_rate}"
            )

    # Check 3: maker_fee_bps (stored in strategy_params, used by some components)
    if play.account.fee_model:
        expected_maker = play.account.fee_model.maker_bps
        # maker_fee_bps is passed through strategy_params
        actual_maker = engine.config.params.get("maker_fee_bps", 0.0)
        maker_check = ValueFlowCheck(
            name="maker_fee_bps",
            expected=expected_maker,
            actual=actual_maker,
            passed=abs(expected_maker - actual_maker) < 0.001,
            source="Play.account.fee_model.maker_bps",
            target="engine.config.params['maker_fee_bps']",
        )
        checks.append(maker_check)
        if not maker_check.passed:
            errors.append(
                f"maker_fee_bps mismatch: Play={expected_maker}, Engine={actual_maker}"
            )

    # Check 4: maintenance_margin_rate
    expected_mmr = play.account.maintenance_margin_rate if play.account.maintenance_margin_rate is not None else 0.005
    actual_mmr = engine.config.risk_profile.maintenance_margin_rate
    mmr_check = ValueFlowCheck(
        name="maintenance_margin_rate",
        expected=expected_mmr,
        actual=actual_mmr,
        passed=abs(expected_mmr - actual_mmr) < 0.0001,
        source="Play.account.maintenance_margin_rate",
        target="engine.config.risk_profile.maintenance_margin_rate",
    )
    checks.append(mmr_check)
    if not mmr_check.passed:
        errors.append(
            f"maintenance_margin_rate mismatch: Play={expected_mmr}, Engine={actual_mmr}"
        )

    # Check 5: min_trade_notional_usdt
    if play.account.min_trade_notional_usdt is not None:
        expected_min_trade = play.account.min_trade_notional_usdt
        actual_min_trade = engine.config.risk_profile.min_trade_usdt
        min_trade_check = ValueFlowCheck(
            name="min_trade_notional_usdt",
            expected=expected_min_trade,
            actual=actual_min_trade,
            passed=abs(expected_min_trade - actual_min_trade) < 0.01,
            source="Play.account.min_trade_notional_usdt",
            target="engine.config.risk_profile.min_trade_usdt",
        )
        checks.append(min_trade_check)
        if not min_trade_check.passed:
            errors.append(
                f"min_trade_notional_usdt mismatch: Play={expected_min_trade}, Engine={actual_min_trade}"
            )

    return ValueFlowAuditResult(
        passed=len(errors) == 0,
        checks=checks,
        errors=errors,
    )


def print_audit_result(result: ValueFlowAuditResult) -> None:
    """Print audit result in a formatted way."""
    print("\n" + "=" * 60)
    print("  VALUE FLOW AUDIT")
    print("=" * 60)

    for check in result.checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"  [{status}] {check.name}")
        print(f"          Source: {check.source}")
        print(f"          Target: {check.target}")
        print(f"          Expected: {check.expected}, Actual: {check.actual}")

    print("-" * 60)
    print(f"  {result.summary()}")
    print("=" * 60 + "\n")

    if result.errors:
        print("Errors:")
        for error in result.errors:
            print(f"  - {error}")
