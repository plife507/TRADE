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
    system_id: str = "",
    window_name: str = "",
    strategy: "Callable | None" = None,
    run_dir: "Path | None" = None,
) -> "BacktestResult":
    """
    DEPRECATED: Use create_engine_from_play() + run_engine_with_play() instead.

    The system_id-based backtest runner has been removed in favor of
    Play-native execution. Use:

        from src.backtest import create_engine_from_play, run_engine_with_play
        from src.backtest.play import load_play

        play = load_play("my_strategy")
        engine = create_engine_from_play(play, window_start, window_end)
        result = run_engine_with_play(engine, play)

    Raises:
        RuntimeError: Always - this function is deprecated.
    """
    raise RuntimeError(
        "run_backtest() is deprecated. Use create_engine_from_play() + run_engine_with_play() "
        "with a Play file instead. See: from src.backtest import create_engine_from_play, run_engine_with_play"
    )


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
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    warmup_by_tf: dict[str, int] | None = None,
    run_dir: Path | None = None,
    on_snapshot: Callable[["RuntimeSnapshotView", int, int, int], None] | None = None,
    synthetic_provider: "SyntheticDataProvider | None" = None,
    window_name: str = "run",
    data_env: str = "backtest",
):
    """
    Create a PlayEngine from a Play with pre-built backtest components.

    This is the canonical factory for Play-native backtest execution.
    Uses BacktestEngine internally for data loading and preparation,
    then returns a unified PlayEngine with all pre-built components.

    The returned engine can be run via run_engine_with_play() or
    via BacktestRunner for the unified execution path.

    Args:
        play: Source Play with all strategy/feature specs
        window_start: Backtest window start (optional if synthetic_provider used)
        window_end: Backtest window end (optional if synthetic_provider used)
        warmup_by_tf: Warmup bars per TF (auto-computed from registry if None)
        run_dir: Optional output directory for artifacts
        on_snapshot: Optional snapshot callback for auditing
        synthetic_provider: Optional SyntheticDataProvider for DB-free validation
        window_name: Window name for engine config (default: "run")
        data_env: Data environment ("backtest", "live", "demo") - determines DuckDB file

    Returns:
        PlayEngine with pre-built FeedStores, SimulatedExchange, and incremental state

    Raises:
        ValueError: If Play is missing required sections (account)
    """
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from src.forge.validation.synthetic_provider import SyntheticDataProvider
    from .engine import BacktestEngine
    from .system_config import (
        SystemConfig,
        RiskProfileConfig,
        StrategyInstanceConfig,
        StrategyInstanceInputs,
        DataBuildConfig,
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

    # Build feature_specs_by_role from registry for engine_data_prep
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

    # Handle window defaults for synthetic provider mode
    if synthetic_provider is not None and (window_start is None or window_end is None):
        # Get data range from synthetic provider
        exec_tf = play.execution_tf
        data_start, data_end = synthetic_provider.get_data_range(exec_tf)
        if window_start is None:
            window_start = data_start
        if window_end is None:
            window_end = data_end

    # Validate we have window bounds
    if window_start is None or window_end is None:
        raise ValueError(
            "window_start and window_end are required unless synthetic_provider is used"
        )

    # Strip timezone for engine compatibility (DuckDB stores naive UTC)
    window_start_naive = window_start.replace(tzinfo=None) if window_start.tzinfo else window_start
    window_end_naive = window_end.replace(tzinfo=None) if window_end.tzinfo else window_end

    # Build tf_mapping from feature registry TFs FIRST (needed for warmup_bars_by_role)
    # Sort TFs by minutes to determine high_tf/med_tf/low_tf roles
    from .runtime.timeframe import tf_minutes
    all_tfs = sorted(registry.get_all_tfs(), key=lambda tf: tf_minutes(tf))
    exec_tf = play.execution_tf

    if len(all_tfs) == 1:
        # Single-TF mode
        tf_mapping = {"high_tf": exec_tf, "med_tf": exec_tf, "low_tf": exec_tf}
    else:
        # Multi-TF mode: map TFs to roles
        # low_tf = execution_tf, med_tf = next higher, high_tf = highest
        tf_mapping = {"low_tf": exec_tf}
        non_exec_tfs = [tf for tf in all_tfs if tf != exec_tf]
        if non_exec_tfs:
            # Sort remaining TFs by minutes (ascending)
            non_exec_sorted = sorted(non_exec_tfs, key=lambda tf: tf_minutes(tf))
            if len(non_exec_sorted) >= 2:
                tf_mapping["med_tf"] = non_exec_sorted[0]  # Lowest non-exec
                tf_mapping["high_tf"] = non_exec_sorted[-1]  # Highest non-exec
            elif len(non_exec_sorted) == 1:
                # Only one other TF - use it as both med_tf and high_tf
                tf_mapping["med_tf"] = non_exec_sorted[0]
                tf_mapping["high_tf"] = non_exec_sorted[0]
        else:
            tf_mapping["med_tf"] = exec_tf
            tf_mapping["high_tf"] = exec_tf

    # Build warmup_bars_by_role from warmup_by_tf using tf_mapping
    # CRITICAL: Use tf_mapping to get correct TF for each role
    # Previously this used exec_tf warmup for ALL roles (bug!)
    warmup_bars_by_role = {
        "exec": warmup_by_tf.get(tf_mapping.get("low_tf", exec_tf), 0),
        "low_tf": warmup_by_tf.get(tf_mapping.get("low_tf", exec_tf), 0),
        "med_tf": warmup_by_tf.get(tf_mapping.get("med_tf", exec_tf), 0),
        "high_tf": warmup_by_tf.get(tf_mapping.get("high_tf", exec_tf), 0),
    }
    # Also include TF-keyed values for flexibility
    for tf, warmup in warmup_by_tf.items():
        warmup_bars_by_role[tf] = warmup

    # Create SystemConfig
    system_config = SystemConfig(
        system_id=play.id,
        symbol=symbol,
        tf=play.execution_tf,
        description=play.description,
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
        # Feature Registry architecture
        feature_registry=registry,
        warmup_by_tf=warmup_by_tf,
        warmup_bars_by_role=warmup_bars_by_role,
        feature_specs_by_role=feature_specs_by_role,
        # Data environment (backtest, live, demo) - determines which DuckDB to use
        data_build=DataBuildConfig(env=data_env),
    )

    # Create BacktestEngine for data preparation
    # Handles data loading, indicator computation, and feed store building
    data_builder = BacktestEngine(
        config=system_config,
        window_name=window_name,
        run_dir=run_dir,
        feature_registry=registry,
        on_snapshot=on_snapshot,
        tf_mapping=tf_mapping,
        synthetic_provider=synthetic_provider,
    )

    # Store Play reference
    data_builder._play = play

    # Prepare data frames (loads data, computes indicators)
    multi_tf_mode = tf_mapping["high_tf"] != tf_mapping["low_tf"] or tf_mapping["med_tf"] != tf_mapping["low_tf"]
    if multi_tf_mode:
        data_builder.prepare_multi_tf_frames()
    else:
        data_builder.prepare_backtest_frame()

    # Build FeedStores for O(1) access
    data_builder._build_feed_stores()

    # Build incremental state for structure detection
    incremental_state = data_builder._build_incremental_state()

    # Extract all pre-built components
    feed_store = data_builder._exec_feed
    htf_feed = data_builder._htf_feed
    mtf_feed = data_builder._mtf_feed
    quote_feed = data_builder._quote_feed
    sim_exchange = data_builder._exchange

    # Create unified PlayEngine with pre-built components via GATE 4 factory
    from src.engine.factory import create_backtest_engine as create_unified_engine

    engine = create_unified_engine(
        play=play,
        feed_store=feed_store,
        sim_exchange=sim_exchange,
        htf_feed=htf_feed,
        mtf_feed=mtf_feed,
        quote_feed=quote_feed,
        tf_mapping=tf_mapping,
        incremental_state=incremental_state,
        on_snapshot=on_snapshot,
    )

    # Store Play and config references for run_engine_with_play()
    engine._play = play
    engine._prepared_frame = data_builder._prepared_frame  # For sim_start_idx access
    engine._multi_tf_mode = multi_tf_mode

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
    engine,
    play: "Play",
) -> "PlayBacktestResult":
    """
    Run a PlayEngine using Play signal evaluation.

    This runs the unified PlayEngine through BacktestRunner, which handles
    the bar-by-bar execution loop using the pre-built FeedStores and
    SimulatedExchange.

    Args:
        engine: PlayEngine (created via create_engine_from_play)
        play: Play with signal rules

    Returns:
        PlayBacktestResult with trades, equity curve, and metrics
    """
    from .execution_validation import compute_play_hash
    from ..engine.runners import BacktestRunner
    from ..engine.adapters.backtest import BacktestDataProvider

    # Import here to avoid circular import
    PlayBacktestResult = _get_play_result_class()

    # Extract pre-built components from engine
    # FeedStore and SimulatedExchange were set up in create_engine_from_play()
    data_provider = engine._data_provider
    feed_store = data_provider._feed_store if isinstance(data_provider, BacktestDataProvider) else None
    sim_exchange = engine._exchange._sim_exchange if hasattr(engine._exchange, '_sim_exchange') else None

    # Get simulation start index from prepared frame
    sim_start_idx = None
    if hasattr(engine, '_prepared_frame') and engine._prepared_frame is not None:
        sim_start_idx = engine._prepared_frame.sim_start_index

    # Create BacktestRunner with pre-built components
    runner = BacktestRunner(
        engine=engine,
        feed_store=feed_store,
        sim_exchange=sim_exchange,
        sim_start_idx=sim_start_idx,
    )

    # Run the backtest via unified runner
    backtest_result = runner.run()

    # Compute Play hash
    play_hash = compute_play_hash(play)

    # Use metrics from BacktestResult (has compatibility mapping via .metrics property)
    metrics = backtest_result.metrics

    # Convert BacktestResult to PlayBacktestResult
    return PlayBacktestResult(
        trades=backtest_result.trades,
        equity_curve=backtest_result.equity_curve,
        final_equity=backtest_result.final_equity,
        play_hash=play_hash,
        metrics=metrics,
        description=f"{play.id} backtest",
        # BacktestRunner result doesn't have stop fields yet
        stop_reason=None,
        stop_classification=None,
        stop_reason_detail=None,
        stopped_early=False,
    )


@dataclass
class PlayBacktestResult:
    """Result from Play-native backtest execution."""
    trades: list[Any]
    equity_curve: list[Any]
    final_equity: float
    play_hash: str
    metrics: Any = None
    description: str = ""
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


# =============================================================================
# PROFESSIONAL NAMING ALIASES
# See docs/specs/ENGINE_NAMING_CONVENTION.md for full naming standards
# =============================================================================

# Canonical factory function names
create_backtest_engine = create_engine_from_play  # Preferred name
PlayRunResult = PlayBacktestResult  # Play-native result wrapper
