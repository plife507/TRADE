"""
Gate Evaluation (Stage 7).

Evaluates pre-conditions (gates) for trade actions.

Gate Categories:
1. Warmup gates (G_WARMUP_REMAINING, G_HISTORY_NOT_READY)
2. Cache gates (G_CACHE_NOT_READY)
3. Risk gates (G_RISK_BLOCK, G_MAX_DRAWDOWN, G_INSUFFICIENT_MARGIN)
4. Position gates (G_POSITION_LIMIT, G_EXPOSURE_LIMIT)
5. Cooldown gates (G_COOLDOWN_ACTIVE)

RECORD-ONLY MODE:
- Gate evaluation is observational only
- Does not block trades (engine logic unchanged)
- Captures why trades would be blocked for analysis

Gate evaluation order (fail-fast):
1. G_WARMUP_REMAINING - warmup period not complete
2. G_HISTORY_NOT_READY - insufficient bar history
3. G_CACHE_NOT_READY - feature cache not populated
4. G_RISK_BLOCK - risk policy blocks
5. G_MAX_DRAWDOWN - drawdown limit hit
6. G_INSUFFICIENT_MARGIN - margin check fails
7. G_COOLDOWN_ACTIVE - post-trade cooldown
8. G_POSITION_LIMIT - max positions reached
9. G_EXPOSURE_LIMIT - max exposure reached
"""

from dataclasses import dataclass

from src.backtest.runtime.state_types import (
    GateCode,
    GateResult,
)


@dataclass
class GateContext:
    """
    Context for gate evaluation.

    Provides all inputs needed to evaluate gates without
    requiring access to engine internals.

    Attributes:
        bar_idx: Current bar index
        warmup_bars: Required warmup bars
        history_bars: Available history bars
        cache_ready: Whether feature cache is populated
        current_drawdown_pct: Current drawdown percentage
        max_drawdown_limit_pct: Max allowed drawdown
        available_margin: Available margin in USDT
        required_margin: Required margin for action
        position_count: Current open position count
        max_positions: Max allowed positions
        current_exposure_pct: Current exposure percentage
        max_exposure_pct: Max allowed exposure
        cooldown_bars_remaining: Bars remaining in cooldown
        risk_policy_passed: Whether risk policy passed
        risk_policy_reason: Reason if risk policy failed
    """
    bar_idx: int = 0
    warmup_bars: int = 0
    history_bars: int = 0
    cache_ready: bool = True
    current_drawdown_pct: float = 0.0
    max_drawdown_limit_pct: float = 100.0
    available_margin: float = float('inf')
    required_margin: float = 0.0
    position_count: int = 0
    max_positions: int = 100
    current_exposure_pct: float = 0.0
    max_exposure_pct: float = 100.0
    cooldown_bars_remaining: int = 0
    risk_policy_passed: bool = True
    risk_policy_reason: str | None = None


def evaluate_gates(ctx: GateContext) -> GateResult:
    """
    Evaluate all gates and return result.

    Uses fail-fast evaluation: returns on first failure.
    Collects all failures for diagnostic purposes.

    Args:
        ctx: Gate evaluation context

    Returns:
        GateResult with pass/fail status and reason codes
    """
    failed_codes: list[GateCode] = []
    first_failure: GateCode | None = None
    first_reason: str | None = None

    # Gate 1: Warmup remaining
    if ctx.bar_idx < ctx.warmup_bars:
        code = GateCode.G_WARMUP_REMAINING
        failed_codes.append(code)
        if first_failure is None:
            first_failure = code
            first_reason = f"Warmup: bar {ctx.bar_idx} < required {ctx.warmup_bars}"

    # Gate 2: History not ready
    if ctx.history_bars < ctx.warmup_bars:
        code = GateCode.G_HISTORY_NOT_READY
        failed_codes.append(code)
        if first_failure is None:
            first_failure = code
            first_reason = f"History: {ctx.history_bars} bars < required {ctx.warmup_bars}"

    # Gate 3: Cache not ready
    if not ctx.cache_ready:
        code = GateCode.G_CACHE_NOT_READY
        failed_codes.append(code)
        if first_failure is None:
            first_failure = code
            first_reason = "Feature cache not populated"

    # Gate 4: Risk policy block
    if not ctx.risk_policy_passed:
        code = GateCode.G_RISK_BLOCK
        failed_codes.append(code)
        if first_failure is None:
            first_failure = code
            first_reason = ctx.risk_policy_reason or "Risk policy blocked"

    # Gate 5: Max drawdown
    # P2-004: Using >= (greater-than-or-equal) is intentional:
    # - At exactly the limit, the trade is blocked (conservative)
    # - This prevents "boundary trades" that could exceed the limit
    if ctx.current_drawdown_pct >= ctx.max_drawdown_limit_pct:
        code = GateCode.G_MAX_DRAWDOWN
        failed_codes.append(code)
        if first_failure is None:
            first_failure = code
            first_reason = (
                f"Drawdown {ctx.current_drawdown_pct:.1f}% >= "
                f"limit {ctx.max_drawdown_limit_pct:.1f}%"
            )

    # Gate 6: Insufficient margin
    if ctx.available_margin < ctx.required_margin:
        code = GateCode.G_INSUFFICIENT_MARGIN
        failed_codes.append(code)
        if first_failure is None:
            first_failure = code
            first_reason = (
                f"Margin {ctx.available_margin:.2f} USDT < "
                f"required {ctx.required_margin:.2f} USDT"
            )

    # Gate 7: Cooldown active
    if ctx.cooldown_bars_remaining > 0:
        code = GateCode.G_COOLDOWN_ACTIVE
        failed_codes.append(code)
        if first_failure is None:
            first_failure = code
            first_reason = f"Cooldown: {ctx.cooldown_bars_remaining} bars remaining"

    # Gate 8: Position limit
    if ctx.position_count >= ctx.max_positions:
        code = GateCode.G_POSITION_LIMIT
        failed_codes.append(code)
        if first_failure is None:
            first_failure = code
            first_reason = (
                f"Positions {ctx.position_count} >= "
                f"limit {ctx.max_positions}"
            )

    # Gate 9: Exposure limit
    if ctx.current_exposure_pct >= ctx.max_exposure_pct:
        code = GateCode.G_EXPOSURE_LIMIT
        failed_codes.append(code)
        if first_failure is None:
            first_failure = code
            first_reason = (
                f"Exposure {ctx.current_exposure_pct:.1f}% >= "
                f"limit {ctx.max_exposure_pct:.1f}%"
            )

    # Return result
    if not failed_codes:
        return GateResult.pass_()

    assert first_failure is not None
    return GateResult.fail_(
        code=first_failure,
        reason=first_reason,
        additional_codes=tuple(failed_codes[1:]) if len(failed_codes) > 1 else None,
    )


def evaluate_warmup_gate(bar_idx: int, warmup_bars: int) -> GateResult:
    """
    Evaluate warmup gate only.

    Convenience function for quick warmup check.
    """
    if bar_idx < warmup_bars:
        return GateResult.fail_(
            code=GateCode.G_WARMUP_REMAINING,
            reason=f"Warmup: bar {bar_idx} < required {warmup_bars}",
        )
    return GateResult.pass_()


def evaluate_margin_gate(
    available_margin: float,
    required_margin: float,
) -> GateResult:
    """
    Evaluate margin gate only.

    Convenience function for margin check.
    """
    if available_margin < required_margin:
        return GateResult.fail_(
            code=GateCode.G_INSUFFICIENT_MARGIN,
            reason=(
                f"Margin {available_margin:.2f} USDT < "
                f"required {required_margin:.2f} USDT"
            ),
        )
    return GateResult.pass_()
