"""
Factory functions module for BacktestEngine.

This module provides factory functions for creating and running BacktestEngine:
- run_backtest: Convenience function to run a backtest from system_id
- create_engine_from_idea_card: Create engine from IdeaCard
- run_engine_with_idea_card: Run engine with IdeaCard signal evaluation
- _get_idea_card_result_class: Get IdeaCardBacktestResult class

These functions provide the main entry points for backtest execution.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import BacktestEngine
    from .types import BacktestResult
    from .idea_card import IdeaCard
    from .feature_registry import FeatureRegistry
    from .runtime.types import RuntimeSnapshot
    from .runtime.snapshot_view import RuntimeSnapshotView
    from ..core.risk_manager import Signal


def run_backtest(
    system_id: str,
    window_name: str,
    strategy: Callable[["RuntimeSnapshot", dict[str, Any]], "Signal | None"],
    run_dir: Path | None = None,
) -> "BacktestResult":
    """
    Convenience function to run a backtest.

    Args:
        system_id: System configuration ID
        window_name: Window to use ("hygiene" or "test")
        strategy: Strategy function
        run_dir: Optional directory for artifacts

    Returns:
        BacktestResult
    """
    from .engine import BacktestEngine
    from .system_config import load_system_config

    config = load_system_config(system_id, window_name)
    engine = BacktestEngine(config, window_name, run_dir)
    return engine.run(strategy)


# =============================================================================
# IdeaCard-Native Engine Factory (Feature Registry Architecture)
# =============================================================================
# Uses the new FeatureRegistry for unified indicator/structure access on any TF.


def _compute_warmup_by_tf(registry: "FeatureRegistry") -> dict[str, int]:
    """
    Compute warmup bars required for each timeframe.

    Args:
        registry: FeatureRegistry with all features.

    Returns:
        Dict mapping TF string to warmup bars needed.
    """
    warmup_by_tf = {}
    for tf in registry.get_all_tfs():
        warmup_by_tf[tf] = registry.get_warmup_for_tf(tf)
    return warmup_by_tf


def create_engine_from_idea_card(
    idea_card: "IdeaCard",
    window_start: datetime,
    window_end: datetime,
    warmup_by_tf: dict[str, int] | None = None,
    run_dir: Path | None = None,
    on_snapshot: Callable[["RuntimeSnapshotView", int, int, int], None] | None = None,
) -> "BacktestEngine":
    """
    Create a BacktestEngine from an IdeaCard.

    This is the canonical factory for IdeaCard-native backtest execution.
    Uses the FeatureRegistry for unified indicator/structure access on any TF.

    Args:
        idea_card: Source IdeaCard with all strategy/feature specs
        window_start: Backtest window start
        window_end: Backtest window end
        warmup_by_tf: Warmup bars per TF (auto-computed from registry if None)
        run_dir: Optional output directory for artifacts
        on_snapshot: Optional snapshot callback for auditing

    Returns:
        BacktestEngine configured from IdeaCard

    Raises:
        ValueError: If IdeaCard is missing required sections (account)
    """
    from .engine import BacktestEngine
    from .system_config import (
        SystemConfig,
        RiskProfileConfig,
        StrategyInstanceConfig,
        StrategyInstanceInputs,
    )

    # Validate required sections
    if idea_card.account is None:
        raise ValueError(
            f"IdeaCard '{idea_card.id}' is missing account section. "
            "account.starting_equity_usdt and account.max_leverage are required."
        )

    # Get first symbol
    symbol = idea_card.symbol_universe[0] if idea_card.symbol_universe else "BTCUSDT"

    # Get feature registry
    registry = idea_card.feature_registry

    # Extract capital/account params from IdeaCard (REQUIRED - no defaults)
    initial_equity = idea_card.account.starting_equity_usdt
    max_leverage = idea_card.account.max_leverage

    # Extract fee model from IdeaCard (REQUIRED - fail loud if missing)
    if idea_card.account.fee_model is None:
        raise ValueError(
            f"IdeaCard '{idea_card.id}' is missing account.fee_model. "
            "Fee model is required (taker_bps, maker_bps). No silent defaults allowed. "
            "Add: account.fee_model.taker_bps and account.fee_model.maker_bps"
        )
    taker_fee_rate = idea_card.account.fee_model.taker_rate

    # Extract min trade notional from IdeaCard (REQUIRED - fail loud if missing)
    if idea_card.account.min_trade_notional_usdt is None:
        raise ValueError(
            f"IdeaCard '{idea_card.id}' is missing account.min_trade_notional_usdt. "
            "Minimum trade notional is required. No silent defaults allowed. "
            "Add: account.min_trade_notional_usdt (e.g., 10.0)"
        )
    min_trade_usdt = idea_card.account.min_trade_notional_usdt

    # Extract slippage from IdeaCard if present (flows to ExecutionConfig)
    slippage_bps = 5.0  # Default only if not specified
    if idea_card.account.slippage_bps is not None:
        slippage_bps = idea_card.account.slippage_bps

    # Extract maker fee from IdeaCard
    maker_fee_bps = idea_card.account.fee_model.maker_bps

    # Extract risk params from IdeaCard risk_model
    risk_per_trade_pct = 1.0
    if idea_card.risk_model:
        if idea_card.risk_model.sizing.model.value == "percent_equity":
            risk_per_trade_pct = idea_card.risk_model.sizing.value
        # Override max_leverage from risk_model.sizing if different
        if idea_card.risk_model.sizing.max_leverage:
            max_leverage = idea_card.risk_model.sizing.max_leverage

    # Extract maintenance margin rate from IdeaCard if present
    maintenance_margin_rate = 0.005  # Default: Bybit lowest tier (0.5%)
    if idea_card.account.maintenance_margin_rate is not None:
        maintenance_margin_rate = idea_card.account.maintenance_margin_rate

    # Build RiskProfileConfig
    risk_profile = RiskProfileConfig(
        initial_equity=initial_equity,
        max_leverage=max_leverage,
        risk_per_trade_pct=risk_per_trade_pct,
        taker_fee_rate=taker_fee_rate,
        min_trade_usdt=min_trade_usdt,
        maintenance_margin_rate=maintenance_margin_rate,
    )

    # Compute warmup from registry if not provided
    if warmup_by_tf is None:
        warmup_by_tf = _compute_warmup_by_tf(registry)

    # Auto-detect if crossover operators require history
    requires_history = _blocks_require_history(idea_card.blocks)

    # Build params with history config if crossovers are used
    strategy_params: dict[str, Any] = {}
    if requires_history:
        # Request 2 bars of history for each TF with features
        history_config: dict[str, int] = {}
        for tf in registry.get_all_tfs():
            history_config[f"features_{tf}_count"] = 2
        strategy_params["history"] = history_config

    # Pass execution params from IdeaCard to engine
    strategy_params["slippage_bps"] = slippage_bps
    strategy_params["taker_fee_bps"] = taker_fee_rate * 10000  # Convert rate to bps
    strategy_params["maker_fee_bps"] = maker_fee_bps

    # Create strategy instance
    strategy_instance = StrategyInstanceConfig(
        strategy_instance_id="idea_card_strategy",
        strategy_id=idea_card.id,
        strategy_version=idea_card.version,
        inputs=StrategyInstanceInputs(symbol=symbol, tf=idea_card.execution_tf),
        params=strategy_params,
    )

    # Strip timezone for engine compatibility (DuckDB stores naive UTC)
    window_start_naive = window_start.replace(tzinfo=None) if window_start.tzinfo else window_start
    window_end_naive = window_end.replace(tzinfo=None) if window_end.tzinfo else window_end

    # Create SystemConfig
    system_config = SystemConfig(
        system_id=idea_card.id,
        symbol=symbol,
        tf=idea_card.execution_tf,
        strategies=[strategy_instance],
        primary_strategy_instance_id="idea_card_strategy",
        windows={
            "run": {
                "start": window_start_naive.isoformat(),
                "end": window_end_naive.isoformat(),
            }
        },
        risk_profile=risk_profile,
        risk_mode="none",
        # New fields for Feature Registry architecture
        feature_registry=registry,
        warmup_by_tf=warmup_by_tf,
    )

    # Create engine
    engine = BacktestEngine(
        config=system_config,
        window_name="run",
        run_dir=run_dir,
        feature_registry=registry,
        on_snapshot=on_snapshot,
    )

    # Store IdeaCard reference for run_with_idea_card()
    engine._idea_card = idea_card

    return engine


def _blocks_require_history(blocks: list) -> bool:
    """
    Check if any blocks use crossover operators that require history.

    Args:
        blocks: List of Block objects

    Returns:
        True if crossover operators are used
    """
    from .rules.dsl_nodes import (
        Expr, Cond, AllExpr, AnyExpr, NotExpr,
        HoldsFor, OccurredWithin, CountTrue,
    )

    def _check_expr(expr: Expr) -> bool:
        """Recursively check expression for crossover operators."""
        if isinstance(expr, Cond):
            return expr.op in ("cross_above", "cross_below")
        elif isinstance(expr, AllExpr):
            return any(_check_expr(c) for c in expr.children)
        elif isinstance(expr, AnyExpr):
            return any(_check_expr(c) for c in expr.children)
        elif isinstance(expr, NotExpr):
            return _check_expr(expr.child)
        elif isinstance(expr, (HoldsFor, OccurredWithin, CountTrue)):
            return _check_expr(expr.expr)
        return False

    for block in blocks:
        for case in block.cases:
            if _check_expr(case.when):
                return True

    return False


def run_engine_with_idea_card(
    engine: "BacktestEngine",
    idea_card: "IdeaCard",
) -> "IdeaCardBacktestResult":
    """
    Run a BacktestEngine using IdeaCard signal evaluation.

    This consolidates signal evaluation into the engine execution flow.

    Args:
        engine: BacktestEngine (created via create_engine_from_idea_card)
        idea_card: IdeaCard with signal rules

    Returns:
        IdeaCardBacktestResult with trades, equity curve, and metrics
    """
    from .execution_validation import (
        IdeaCardSignalEvaluator,
        SignalDecision,
        compute_idea_card_hash,
    )
    from ..core.risk_manager import Signal

    # Import here to avoid circular import
    IdeaCardBacktestResult = _get_idea_card_result_class()

    # Verify all conditions have valid feature_id refs
    _verify_all_conditions_compiled(idea_card)

    # Create signal evaluator
    evaluator = IdeaCardSignalEvaluator(idea_card)

    def idea_card_strategy(snapshot, params) -> Signal | None:
        """Strategy function that uses IdeaCard signal evaluator."""
        # Check if we have a position
        has_position = snapshot.has_position
        position_side = snapshot.position_side

        # Evaluate signal rules
        result = evaluator.evaluate(snapshot, has_position, position_side)

        # Convert to Signal
        if result.decision == SignalDecision.NO_ACTION:
            return None
        elif result.decision == SignalDecision.ENTRY_LONG:
            return Signal(
                symbol=idea_card.symbol_universe[0],
                direction="LONG",
                size_usdt=0.0,  # Engine computes from risk_profile
                strategy=idea_card.id,
                confidence=1.0,
                metadata={
                    "stop_loss": result.stop_loss_price,
                    "take_profit": result.take_profit_price,
                }
            )
        elif result.decision == SignalDecision.ENTRY_SHORT:
            return Signal(
                symbol=idea_card.symbol_universe[0],
                direction="SHORT",
                size_usdt=0.0,
                strategy=idea_card.id,
                confidence=1.0,
                metadata={
                    "stop_loss": result.stop_loss_price,
                    "take_profit": result.take_profit_price,
                }
            )
        elif result.decision == SignalDecision.EXIT:
            return Signal(
                symbol=idea_card.symbol_universe[0],
                direction="FLAT",
                size_usdt=0.0,
                strategy=idea_card.id,
                confidence=1.0,
            )

        return None

    # Run the engine
    backtest_result = engine.run(idea_card_strategy)

    # Compute IdeaCard hash
    idea_card_hash = compute_idea_card_hash(idea_card)

    return IdeaCardBacktestResult(
        trades=backtest_result.trades,
        equity_curve=backtest_result.equity_curve,
        final_equity=backtest_result.metrics.final_equity,
        idea_card_hash=idea_card_hash,
        metrics=backtest_result.metrics,
    )


@dataclass
class IdeaCardBacktestResult:
    """Result from IdeaCard-native backtest execution."""
    trades: list[Any]
    equity_curve: list[Any]
    final_equity: float
    idea_card_hash: str
    metrics: Any = None


def _get_idea_card_result_class():
    """
    Get IdeaCardBacktestResult class (avoids import at module level).

    This allows runner.py to define the class and engine.py to use it
    without circular imports.
    """
    return IdeaCardBacktestResult
