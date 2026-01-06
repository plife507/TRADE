"""
Factory functions module for BacktestEngine.

This module provides factory functions for creating and running BacktestEngine:
- run_backtest: Convenience function to run a backtest from system_id
- create_engine_from_play: Create engine from Play
- run_engine_with_play: Run engine with Play signal evaluation
- _get_play_result_class: Get PlayBacktestResult class

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
    from .play import Play
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
# Play-Native Engine Factory (Feature Registry Architecture)
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


def create_engine_from_play(
    play: "Play",
    window_start: datetime,
    window_end: datetime,
    warmup_by_tf: dict[str, int] | None = None,
    run_dir: Path | None = None,
    on_snapshot: Callable[["RuntimeSnapshotView", int, int, int], None] | None = None,
) -> "BacktestEngine":
    """
    Create a BacktestEngine from an Play.

    This is the canonical factory for Play-native backtest execution.
    Uses the FeatureRegistry for unified indicator/structure access on any TF.

    Args:
        play: Source Play with all strategy/feature specs
        window_start: Backtest window start
        window_end: Backtest window end
        warmup_by_tf: Warmup bars per TF (auto-computed from registry if None)
        run_dir: Optional output directory for artifacts
        on_snapshot: Optional snapshot callback for auditing

    Returns:
        BacktestEngine configured from Play

    Raises:
        ValueError: If Play is missing required sections (account)
    """
    from .engine import BacktestEngine
    from .system_config import (
        SystemConfig,
        RiskProfileConfig,
        StrategyInstanceConfig,
        StrategyInstanceInputs,
    )
    from .features.feature_spec import FeatureSpec, InputSource as FSInputSource
    from .feature_registry import FeatureType

    # Validate required sections
    if play.account is None:
        raise ValueError(
            f"Play '{play.id}' is missing account section. "
            "account.starting_equity_usdt and account.max_leverage are required."
        )

    # Get first symbol
    symbol = play.symbol_universe[0] if play.symbol_universe else "BTCUSDT"

    # Get feature registry
    registry = play.feature_registry

    # Build feature_specs_by_role from registry (for backward compat with engine_data_prep)
    def _feature_to_spec(feature) -> FeatureSpec | None:
        """Convert Feature to FeatureSpec (indicators only)."""
        if feature.type != FeatureType.INDICATOR:
            return None  # Structures don't have FeatureSpecs
        # Map InputSource enum
        input_source_map = {
            "close": FSInputSource.CLOSE,
            "open": FSInputSource.OPEN,
            "high": FSInputSource.HIGH,
            "low": FSInputSource.LOW,
            "volume": FSInputSource.VOLUME,
        }
        fs_input = input_source_map.get(feature.input_source.value, FSInputSource.CLOSE)
        return FeatureSpec(
            indicator_type=feature.indicator_type,
            output_key=feature.id,
            params=dict(feature.params),
            input_source=fs_input,
        )

    feature_specs_by_role: dict[str, list[FeatureSpec]] = {}
    for tf in registry.get_all_tfs():
        specs = []
        for feature in registry.get_for_tf(tf):
            spec = _feature_to_spec(feature)
            if spec:
                specs.append(spec)
        feature_specs_by_role[tf] = specs
    # Also set 'exec' role pointing to execution_tf specs
    feature_specs_by_role["exec"] = feature_specs_by_role.get(play.execution_tf, [])

    # Extract capital/account params from Play (REQUIRED - no defaults)
    initial_equity = play.account.starting_equity_usdt
    max_leverage = play.account.max_leverage

    # Extract fee model from Play (REQUIRED - fail loud if missing)
    if play.account.fee_model is None:
        raise ValueError(
            f"Play '{play.id}' is missing account.fee_model. "
            "Fee model is required (taker_bps, maker_bps). No silent defaults allowed. "
            "Add: account.fee_model.taker_bps and account.fee_model.maker_bps"
        )
    taker_fee_rate = play.account.fee_model.taker_rate

    # Extract min trade notional from Play (REQUIRED - fail loud if missing)
    if play.account.min_trade_notional_usdt is None:
        raise ValueError(
            f"Play '{play.id}' is missing account.min_trade_notional_usdt. "
            "Minimum trade notional is required. No silent defaults allowed. "
            "Add: account.min_trade_notional_usdt (e.g., 10.0)"
        )
    min_trade_usdt = play.account.min_trade_notional_usdt

    # Extract slippage from Play if present (flows to ExecutionConfig)
    slippage_bps = 5.0  # Default only if not specified
    if play.account.slippage_bps is not None:
        slippage_bps = play.account.slippage_bps

    # Extract maker fee from Play
    maker_fee_bps = play.account.fee_model.maker_bps

    # Extract risk params from Play risk_model
    risk_per_trade_pct = 1.0
    if play.risk_model:
        if play.risk_model.sizing.model.value == "percent_equity":
            risk_per_trade_pct = play.risk_model.sizing.value
        # Override max_leverage from risk_model.sizing if different
        if play.risk_model.sizing.max_leverage:
            max_leverage = play.risk_model.sizing.max_leverage

    # Extract maintenance margin rate from Play if present
    maintenance_margin_rate = 0.005  # Default: Bybit lowest tier (0.5%)
    if play.account.maintenance_margin_rate is not None:
        maintenance_margin_rate = play.account.maintenance_margin_rate

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
    requires_history = _blocks_require_history(play.actions)

    # Build params with history config if crossovers are used
    strategy_params: dict[str, Any] = {}
    if requires_history:
        # Request 2 bars of history for each TF with features
        history_config: dict[str, int] = {}
        for tf in registry.get_all_tfs():
            history_config[f"features_{tf}_count"] = 2
        strategy_params["history"] = history_config

    # Pass execution params from Play to engine
    strategy_params["slippage_bps"] = slippage_bps
    strategy_params["taker_fee_bps"] = taker_fee_rate * 10000  # Convert rate to bps
    strategy_params["maker_fee_bps"] = maker_fee_bps

    # Create strategy instance
    strategy_instance = StrategyInstanceConfig(
        strategy_instance_id="play_strategy",
        strategy_id=play.id,
        strategy_version=play.version,
        inputs=StrategyInstanceInputs(symbol=symbol, tf=play.execution_tf),
        params=strategy_params,
    )

    # Strip timezone for engine compatibility (DuckDB stores naive UTC)
    window_start_naive = window_start.replace(tzinfo=None) if window_start.tzinfo else window_start
    window_end_naive = window_end.replace(tzinfo=None) if window_end.tzinfo else window_end

    # Build warmup_bars_by_role from warmup_by_tf for backward compatibility
    # Engine data prep still uses role-based warmup
    warmup_bars_by_role = {
        "exec": warmup_by_tf.get(play.execution_tf, 0),
        "ltf": warmup_by_tf.get(play.execution_tf, 0),  # LTF = exec in single-TF
        "mtf": warmup_by_tf.get(play.execution_tf, 0),  # MTF = exec in single-TF
        "htf": warmup_by_tf.get(play.execution_tf, 0),  # HTF = exec in single-TF
    }
    # Override with actual TF values if multi-TF
    for tf, warmup in warmup_by_tf.items():
        warmup_bars_by_role[tf] = warmup

    # Build tf_mapping from feature registry TFs
    # Sort TFs by minutes to determine htf/mtf/ltf roles
    from .runtime.timeframe import tf_minutes
    all_tfs = sorted(registry.get_all_tfs(), key=lambda tf: tf_minutes(tf))
    exec_tf = play.execution_tf

    if len(all_tfs) == 1:
        # Single-TF mode
        tf_mapping = {"htf": exec_tf, "mtf": exec_tf, "ltf": exec_tf}
    else:
        # Multi-TF mode: map TFs to roles
        # ltf = execution_tf, mtf = next higher, htf = highest
        tf_mapping = {"ltf": exec_tf}
        non_exec_tfs = [tf for tf in all_tfs if tf != exec_tf]
        if non_exec_tfs:
            # Sort remaining TFs by minutes (ascending)
            non_exec_sorted = sorted(non_exec_tfs, key=lambda tf: tf_minutes(tf))
            if len(non_exec_sorted) >= 2:
                tf_mapping["mtf"] = non_exec_sorted[0]  # Lowest non-exec
                tf_mapping["htf"] = non_exec_sorted[-1]  # Highest non-exec
            elif len(non_exec_sorted) == 1:
                # Only one other TF - use it as both mtf and htf
                tf_mapping["mtf"] = non_exec_sorted[0]
                tf_mapping["htf"] = non_exec_sorted[0]
        else:
            tf_mapping["mtf"] = exec_tf
            tf_mapping["htf"] = exec_tf

    # Create SystemConfig
    system_config = SystemConfig(
        system_id=play.id,
        symbol=symbol,
        tf=play.execution_tf,
        strategies=[strategy_instance],
        primary_strategy_instance_id="play_strategy",
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
        # Backward compat for engine_data_prep
        warmup_bars_by_role=warmup_bars_by_role,
        feature_specs_by_role=feature_specs_by_role,
    )

    # Create engine
    engine = BacktestEngine(
        config=system_config,
        window_name="run",
        run_dir=run_dir,
        feature_registry=registry,
        on_snapshot=on_snapshot,
        tf_mapping=tf_mapping,
    )

    # Store Play reference for run_with_play()
    engine._play = play

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


def run_engine_with_play(
    engine: "BacktestEngine",
    play: "Play",
) -> "PlayBacktestResult":
    """
    Run a BacktestEngine using Play signal evaluation.

    This consolidates signal evaluation into the engine execution flow.

    Args:
        engine: BacktestEngine (created via create_engine_from_play)
        play: Play with signal rules

    Returns:
        PlayBacktestResult with trades, equity curve, and metrics
    """
    from .execution_validation import (
        PlaySignalEvaluator,
        SignalDecision,
        compute_play_hash,
    )
    from ..core.risk_manager import Signal

    # Import here to avoid circular import
    PlayBacktestResult = _get_play_result_class()

    # Note: Block validation happens at Play construction via _validate_block_types()

    # Create signal evaluator
    evaluator = PlaySignalEvaluator(play)

    def play_strategy(snapshot, params) -> Signal | None:
        """Strategy function that uses Play signal evaluator."""
        # Check if we have a position
        has_position = snapshot.has_position
        position_side = snapshot.position_side

        # Evaluate signal rules
        result = evaluator.evaluate(snapshot, has_position, position_side)

        # Convert to Signal
        if result.decision == SignalDecision.NO_ACTION:
            return None
        elif result.decision == SignalDecision.ENTRY_LONG:
            # Build metadata with SL/TP and any resolved dynamic metadata
            metadata = {
                "stop_loss": result.stop_loss_price,
                "take_profit": result.take_profit_price,
            }
            if result.resolved_metadata:
                metadata.update(result.resolved_metadata)
            return Signal(
                symbol=play.symbol_universe[0],
                direction="LONG",
                size_usdt=0.0,  # Engine computes from risk_profile
                strategy=play.id,
                confidence=1.0,
                metadata=metadata,
            )
        elif result.decision == SignalDecision.ENTRY_SHORT:
            # Build metadata with SL/TP and any resolved dynamic metadata
            metadata = {
                "stop_loss": result.stop_loss_price,
                "take_profit": result.take_profit_price,
            }
            if result.resolved_metadata:
                metadata.update(result.resolved_metadata)
            return Signal(
                symbol=play.symbol_universe[0],
                direction="SHORT",
                size_usdt=0.0,
                strategy=play.id,
                confidence=1.0,
                metadata=metadata,
            )
        elif result.decision == SignalDecision.EXIT:
            # Build metadata with exit_percent and any resolved dynamic metadata
            metadata = {}
            if result.exit_percent != 100.0:
                metadata["exit_percent"] = result.exit_percent
            if result.resolved_metadata:
                metadata.update(result.resolved_metadata)
            return Signal(
                symbol=play.symbol_universe[0],
                direction="FLAT",
                size_usdt=0.0,
                strategy=play.id,
                confidence=1.0,
                metadata=metadata if metadata else None,
            )

        return None

    # Run the engine
    backtest_result = engine.run(play_strategy)

    # Compute Play hash
    play_hash = compute_play_hash(play)

    return PlayBacktestResult(
        trades=backtest_result.trades,
        equity_curve=backtest_result.equity_curve,
        final_equity=backtest_result.metrics.final_equity,
        play_hash=play_hash,
        metrics=backtest_result.metrics,
        # Pass through stop fields
        stop_reason=backtest_result.stop_reason,
        stop_classification=str(backtest_result.stop_classification) if backtest_result.stop_classification else None,
        stop_reason_detail=backtest_result.stop_reason_detail,
        stopped_early=backtest_result.stopped_early,
    )


@dataclass
class PlayBacktestResult:
    """Result from Play-native backtest execution."""
    trades: list[Any]
    equity_curve: list[Any]
    final_equity: float
    play_hash: str
    metrics: Any = None
    # Stop reason fields from BacktestResult
    stop_reason: str | None = None
    stop_classification: str | None = None
    stop_reason_detail: str | None = None
    stopped_early: bool = False


def _get_play_result_class():
    """
    Get PlayBacktestResult class (avoids import at module level).

    This allows runner.py to define the class and engine.py to use it
    without circular imports.
    """
    return PlayBacktestResult
