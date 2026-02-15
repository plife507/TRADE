"""
Factory functions for PlayEngine creation and execution.

This module provides factory functions for creating and running backtests:
- create_engine_from_play: Create PlayEngine from Play (uses DataBuilder)
- run_engine_with_play: Run engine with Play signal evaluation

DataBuilder handles all data preparation.
PlayEngine is the unified engine for backtest/demo/live modes.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from collections.abc import Callable
from typing import Any, TYPE_CHECKING, cast

if TYPE_CHECKING:
    from .data_builder import DataBuilder
    from .types import BacktestResult
    from .play import Play
    from .feature_registry import FeatureRegistry
    from .runtime.types import RuntimeSnapshot
    from .runtime.snapshot_view import RuntimeSnapshotView
    from ..core.risk_manager import Signal
    from ..forge.validation.synthetic_provider import SyntheticDataProvider
    from ..forge.validation.synthetic_data import PatternType


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
    use_synthetic: bool = True,
):
    """
    Create a PlayEngine from a Play with pre-built backtest components.

    This is the canonical factory for Play-native backtest execution.
    Uses DataBuilder for data loading and preparation,
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
    from .data_builder import DataBuilder
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
            "hlc3": FSInputSource.HLC3,
            "ohlc4": FSInputSource.OHLC4,
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
    # Also set 'exec' role pointing to exec_tf specs
    feature_specs_by_role["exec"] = feature_specs_by_role.get(play.exec_tf, [])

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
        if play.account.slippage_bps < 0:
            raise ValueError(f"slippage_bps must be non-negative, got {play.account.slippage_bps}")
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
        inputs=StrategyInstanceInputs(symbol=symbol, tf=play.exec_tf),
        params=strategy_params,
    )

    # Auto-create synthetic provider from Play's synthetic config
    # Only when use_synthetic=True (explicit opt-in via --synthetic flag)
    if use_synthetic and synthetic_provider is None and play.synthetic is not None:
        from src.forge.validation.synthetic_data import generate_synthetic_candles
        from src.forge.validation.synthetic_provider import SyntheticCandlesProvider

        # Gather all required timeframes from tf_mapping
        tf_mapping_resolved = play.tf_mapping or {
            "low_tf": play.exec_tf,
            "med_tf": play.exec_tf,
            "high_tf": play.exec_tf,
            "exec": "low_tf",
        }
        required_tfs = set()
        for role in ("low_tf", "med_tf", "high_tf"):
            tf = tf_mapping_resolved.get(role)
            if tf:
                required_tfs.add(tf)
        # Always include 1m for intrabar/mark price
        required_tfs.add("1m")

        # Generate synthetic candles using Play's config
        candles = generate_synthetic_candles(
            symbol=symbol,
            timeframes=sorted(required_tfs),
            bars_per_tf=play.synthetic.bars,
            seed=play.synthetic.seed,
            pattern=cast("PatternType", play.synthetic.pattern),
            align_multi_tf=True,
        )
        synthetic_provider = SyntheticCandlesProvider(candles)

    # Handle window defaults for synthetic provider mode
    if synthetic_provider is not None and (window_start is None or window_end is None):
        # Get data range from synthetic provider
        exec_tf = play.exec_tf
        data_start, data_end = synthetic_provider.get_data_range(exec_tf)  # type: ignore[attr-defined]
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

    # Use Play's tf_mapping (new 3-feed + exec role system)
    exec_tf = play.exec_tf
    tf_mapping = play.tf_mapping

    if not tf_mapping:
        # Fallback: build tf_mapping from exec_tf (single-TF mode)
        tf_mapping = {
            "low_tf": exec_tf,
            "med_tf": exec_tf,
            "high_tf": exec_tf,
            "exec": "low_tf",
        }

    # Build warmup_bars_by_role from warmup_by_tf using tf_mapping
    # CRITICAL: Use tf_mapping to get correct TF for each role
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
        tf=play.exec_tf,
        description=play.description or "",
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

    # Build data using DataBuilder
    window = system_config.get_window(window_name)
    builder = DataBuilder(
        config=system_config,
        window=window,
        play=play,
        tf_mapping=tf_mapping,
        synthetic_provider=synthetic_provider,
    )
    build_result = builder.build()

    # Extract components from build result (3-feed + exec role system)
    feed_store = build_result.exec_feed  # Resolved exec feed
    high_tf_feed = build_result.high_tf_feed
    med_tf_feed = build_result.med_tf_feed
    quote_feed = build_result.quote_feed
    sim_exchange = build_result.sim_exchange
    incremental_state = build_result.incremental_state
    multi_tf_mode = build_result.multi_tf_mode

    # Create unified PlayEngine with pre-built components via GATE 4 factory
    from src.engine.factory import create_backtest_engine as create_unified_engine

    engine = create_unified_engine(
        play=play,
        feed_store=feed_store,
        sim_exchange=sim_exchange,
        high_tf_feed=high_tf_feed,
        med_tf_feed=med_tf_feed,
        quote_feed=quote_feed,
        tf_mapping=tf_mapping,
        incremental_state=incremental_state,
        on_snapshot=on_snapshot,
    )

    # Store Play and config references for run_engine_with_play()
    engine._play = play
    engine._prepared_frame = build_result.prepared_frame  # type: ignore[attr-defined]  # For sim_start_idx access
    engine._multi_tf_mode = multi_tf_mode  # type: ignore[attr-defined]

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
