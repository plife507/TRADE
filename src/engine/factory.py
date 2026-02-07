"""
PlayEngine factory for creating engines in different modes.

The factory provides a unified interface for creating PlayEngine instances:
- Backtest: Historical data with simulated execution
- Demo: Real-time data with Bybit demo API (paper trading)
- Live: Real-time data with Bybit live API (real money)
- Shadow: Real-time data with signal logging only

Architecture (3-Database Model):
    Each mode uses a separate DuckDB file to enable concurrent operations:

    | Mode     | Database File              | API Endpoint         | Purpose           |
    |----------|----------------------------|----------------------|-------------------|
    | backtest | market_data_backtest.duckdb| api.bybit.com        | Historical sims   |
    | demo     | market_data_demo.duckdb    | api-demo.bybit.com   | Paper trading     |
    | live     | market_data_live.duckdb    | api.bybit.com        | Live trading      |

    This allows: backtest + demo + live to run in separate processes simultaneously.

Instance Isolation:
    - Each PlayEngine gets a unique engine_id: "{play}_{mode}_{uuid8}"
    - Backtest mode: Fully isolated, can run multiple in parallel (separate processes)
    - Demo/Live mode: Use global singletons for WebSocket (one instance per process)

Usage:
    from src.engine import PlayEngineFactory

    # Create backtest engine (uses market_data_backtest.duckdb)
    engine = PlayEngineFactory.create(play, mode="backtest")

    # Create demo engine (uses market_data_demo.duckdb + api-demo.bybit.com)
    engine = PlayEngineFactory.create(play, mode="demo")

    # Create live engine (uses market_data_live.duckdb + api.bybit.com)
    engine = PlayEngineFactory.create(play, mode="live", confirm_live=True)

    # Parallel backtests (separate processes)
    from src.engine.runners import run_backtests_parallel
    results = run_backtests_parallel(["S_01", "S_02", "S_03"], max_workers=3)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from .interfaces import DataProvider, ExchangeAdapter, StateStore
from .play_engine import PlayEngine, PlayEngineConfig

from ..utils.logger import get_logger

if TYPE_CHECKING:
    from ..backtest.play import Play


logger = get_logger()


class PlayEngineFactory:
    """
    Factory for creating PlayEngine instances.

    The factory handles:
    - Mode validation and safety checks
    - Adapter injection based on mode
    - Configuration merging (Play + mode-specific)

    Example:
        # Load or create a Play
        play = load_play_from_yaml("my_strategy.yml")

        # Create engine for backtest
        engine = PlayEngineFactory.create(play, mode="backtest")

        # Create engine for demo trading
        engine = PlayEngineFactory.create(play, mode="demo")

        # Create engine for live trading
        engine = PlayEngineFactory.create(
            play,
            mode="live",
            confirm_live=True,  # Required safety check
        )
    """

    @staticmethod
    def create(
        play: "Play",
        mode: Literal["backtest", "demo", "live", "shadow"],
        confirm_live: bool = False,
        run_dir: Path | None = None,
        config_override: dict | None = None,
    ) -> PlayEngine:
        """
        Create a PlayEngine for the specified mode.

        Args:
            play: Play instance with strategy definition
            mode: Execution mode
            confirm_live: Required confirmation for live mode
            run_dir: Optional directory for artifacts (backtest only)
            config_override: Optional config overrides

        Returns:
            Configured PlayEngine ready for execution

        Raises:
            ValueError: If mode is invalid or live trading not confirmed
            RuntimeError: If environment not configured for mode
        """
        # Validate mode
        if mode not in ("backtest", "demo", "live", "shadow"):
            raise ValueError(f"Invalid mode: {mode}. Must be backtest/demo/live/shadow")

        # Safety check for live trading
        if mode == "live":
            PlayEngineFactory._validate_live_mode(confirm_live)

        # Create mode-specific components
        if mode == "backtest":
            return PlayEngineFactory._create_backtest(play, run_dir, config_override)
        elif mode in ("demo", "live"):
            return PlayEngineFactory._create_live(play, mode, config_override)
        else:  # shadow
            return PlayEngineFactory._create_shadow(play, config_override)

    @staticmethod
    def _validate_live_mode(confirm_live: bool) -> None:
        """
        Validate that live trading is properly configured.

        Raises:
            ValueError: If confirmation not provided
            RuntimeError: If environment not configured for live
        """
        # Require explicit confirmation
        if not confirm_live:
            raise ValueError(
                "Live trading requires confirm_live=True. "
                "This ensures you understand you're trading with real money."
            )

        # Check environment variables
        use_demo = os.getenv("BYBIT_USE_DEMO", "true").lower()
        trading_mode = os.getenv("TRADING_MODE", "paper").lower()

        if use_demo == "true":
            raise RuntimeError(
                "Cannot use live mode with BYBIT_USE_DEMO=true. "
                "Set BYBIT_USE_DEMO=false for live trading."
            )

        if trading_mode != "live":
            raise RuntimeError(
                f"TRADING_MODE must be 'live' for live trading, got '{trading_mode}'"
            )

        # Check for live API keys
        if not os.getenv("BYBIT_LIVE_API_KEY"):
            raise RuntimeError("BYBIT_LIVE_API_KEY not set for live trading")

        if not os.getenv("BYBIT_LIVE_API_SECRET"):
            raise RuntimeError("BYBIT_LIVE_API_SECRET not set for live trading")

        logger.warning(
            "LIVE TRADING MODE ENABLED - You are trading with real money!"
        )

    @staticmethod
    def _create_backtest(
        play: "Play",
        run_dir: Path | None,
        config_override: dict | None,
    ) -> PlayEngine:
        """Create backtest engine with simulated components."""
        # Import adapters here to avoid circular imports
        from .adapters.backtest import (
            BacktestDataProvider,
            BacktestExchange,
        )
        from .adapters.state import InMemoryStateStore

        # Get account config from Play
        account = play.account

        # Extract sizing from risk_model if present
        risk_per_trade_pct = 1.0
        max_leverage = account.max_leverage
        if play.risk_model and play.risk_model.sizing:
            risk_per_trade_pct = play.risk_model.sizing.value
            if play.risk_model.sizing.max_leverage:
                max_leverage = play.risk_model.sizing.max_leverage

        # Create config - use PlayEngineConfig's actual fields
        config = PlayEngineConfig(
            mode="backtest",
            initial_equity=account.starting_equity_usdt,
            risk_per_trade_pct=risk_per_trade_pct,
            max_leverage=max_leverage,
            min_trade_usdt=account.min_trade_notional_usdt,
            taker_fee_rate=account.fee_model.taker_bps / 10000.0,  # Convert bps to rate
            maker_fee_rate=account.fee_model.maker_bps / 10000.0,  # Convert bps to rate
            slippage_bps=account.slippage_bps or 2.0,
            persist_state=False,  # Backtest doesn't need state persistence
            # SL vs Liquidation safety check (default: reject unsafe entries)
            on_sl_beyond_liq="reject",
            maintenance_margin_rate=0.004,  # Bybit default MMR
            # Max drawdown (0 = disabled, set from Play account if available)
            max_drawdown_pct=getattr(account, 'max_drawdown_pct', 25.0),
        )

        # Apply overrides
        if config_override:
            for key, value in config_override.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        # Create adapters
        data_provider = BacktestDataProvider(play)
        exchange = BacktestExchange(play, config)
        state_store = InMemoryStateStore()

        return PlayEngine(
            play=play,
            data_provider=data_provider,
            exchange=exchange,
            state_store=state_store,
            config=config,
        )

    @staticmethod
    def _create_live(
        play: "Play",
        mode: Literal["demo", "live"],
        config_override: dict | None,
    ) -> PlayEngine:
        """Create live/demo engine with real exchange components."""
        # Import adapters here to avoid circular imports
        from .adapters.live import (
            LiveDataProvider,
            LiveExchange,
        )
        from .adapters.state import FileStateStore

        # Get account config from Play
        account = play.account

        # Extract sizing from risk_model if present
        risk_per_trade_pct = 1.0
        max_leverage = account.max_leverage
        if play.risk_model and play.risk_model.sizing:
            risk_per_trade_pct = play.risk_model.sizing.value
            if play.risk_model.sizing.max_leverage:
                max_leverage = play.risk_model.sizing.max_leverage

        # Create config - use PlayEngineConfig's actual fields
        config = PlayEngineConfig(
            mode=mode,
            initial_equity=account.starting_equity_usdt,
            risk_per_trade_pct=risk_per_trade_pct,
            max_leverage=max_leverage,
            min_trade_usdt=account.min_trade_notional_usdt,
            taker_fee_rate=account.fee_model.taker_bps / 10000.0,  # Convert bps to rate
            maker_fee_rate=account.fee_model.maker_bps / 10000.0,  # Convert bps to rate
            slippage_bps=account.slippage_bps or 2.0,
            persist_state=True,  # Live needs state persistence
            state_save_interval=10,  # Save frequently in live mode
            # SL vs Liquidation safety check (default: reject unsafe entries)
            on_sl_beyond_liq="reject",
            maintenance_margin_rate=0.004,  # Bybit default MMR
            # Max drawdown (0 = disabled, set from Play account if available)
            max_drawdown_pct=getattr(account, 'max_drawdown_pct', 25.0),
        )

        # Apply overrides
        if config_override:
            for key, value in config_override.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        # Determine if demo mode
        is_demo = mode == "demo"

        # Create adapters
        data_provider = LiveDataProvider(play, demo=is_demo)
        exchange = LiveExchange(play, config, demo=is_demo)
        state_store = FileStateStore()

        return PlayEngine(
            play=play,
            data_provider=data_provider,
            exchange=exchange,
            state_store=state_store,
            config=config,
        )

    @staticmethod
    def _create_shadow(
        play: "Play",
        config_override: dict | None,
    ) -> PlayEngine:
        """Create shadow engine (live data, no execution)."""
        # Shadow uses live data provider but doesn't execute
        # The PlayEngine's execute_signal() handles shadow mode

        from .adapters.live import LiveDataProvider
        from .adapters.state import InMemoryStateStore

        # Shadow mode uses a mock exchange that doesn't execute
        from .adapters.backtest import ShadowExchange

        # Get account config from Play
        account = play.account

        # Extract sizing from risk_model if present
        risk_per_trade_pct = 1.0
        max_leverage = account.max_leverage
        if play.risk_model and play.risk_model.sizing:
            risk_per_trade_pct = play.risk_model.sizing.value
            if play.risk_model.sizing.max_leverage:
                max_leverage = play.risk_model.sizing.max_leverage

        # Create config - use PlayEngineConfig's actual fields
        config = PlayEngineConfig(
            mode="shadow",
            initial_equity=account.starting_equity_usdt,
            risk_per_trade_pct=risk_per_trade_pct,
            max_leverage=max_leverage,
            min_trade_usdt=account.min_trade_notional_usdt,
            persist_state=False,  # Shadow doesn't need state persistence
        )

        # Apply overrides
        if config_override:
            for key, value in config_override.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        # Create adapters
        data_provider = LiveDataProvider(play, demo=True)  # Use demo data
        exchange = ShadowExchange(play, config)  # No-op exchange
        state_store = InMemoryStateStore()

        return PlayEngine(
            play=play,
            data_provider=data_provider,
            exchange=exchange,
            state_store=state_store,
            config=config,
        )


# G1.15: create_engine() removed (2026-01-27) - use PlayEngineFactory.create() directly

def create_backtest_engine(
    play: "Play",
    feed_store: "FeedStore | None" = None,
    sim_exchange: "SimulatedExchange | None" = None,
    high_tf_feed: "FeedStore | None" = None,
    med_tf_feed: "FeedStore | None" = None,
    quote_feed: "FeedStore | None" = None,
    tf_mapping: dict[str, str] | None = None,
    incremental_state: "MultiTFIncrementalState | None" = None,
    config_override: dict | None = None,
    on_snapshot: "Callable | None" = None,
) -> PlayEngine:
    """
    Create a PlayEngine configured for backtest mode with pre-built components.

    This is the GATE 4 factory function that creates a unified PlayEngine
    for backtesting. Unlike PlayEngineFactory.create(), this function
    accepts pre-built FeedStore and SimulatedExchange instances.

    This enables the unified engine path where BacktestRunner can drive
    PlayEngine with pre-built data components, ensuring deterministic results.

    Args:
        play: Play instance with strategy definition
        feed_store: Pre-built FeedStore for exec timeframe data
        sim_exchange: Pre-built SimulatedExchange for order execution
        high_tf_feed: Optional pre-built FeedStore for high_tf data
        med_tf_feed: Optional pre-built FeedStore for med_tf data
        quote_feed: Optional pre-built FeedStore for 1m quote data
        tf_mapping: Optional TF mapping (high_tf/med_tf/low_tf -> TF strings + exec -> role)
        incremental_state: Optional pre-built incremental state for structures
        config_override: Optional config overrides
        on_snapshot: Optional callback(snapshot, exec_idx, high_tf_idx, med_tf_idx) for audits

    Returns:
        PlayEngine configured for backtest with injected components

    Example:
        # Build components via DataBuilder
        builder = DataBuilder(config, window, play, tf_mapping)
        result = builder.build()

        # Create unified engine with same components
        unified_engine = create_backtest_engine(
            play=play,
            feed_store=old_engine._exec_feed,
            sim_exchange=old_engine._exchange,
            high_tf_feed=old_engine._high_tf_feed,
            med_tf_feed=old_engine._med_tf_feed,
            quote_feed=old_engine._quote_feed,
            tf_mapping=old_engine._tf_mapping,
            incremental_state=old_engine._incremental_state,
        )

        # Run via BacktestRunner
        runner = BacktestRunner(unified_engine, feed_store, sim_exchange)
        result = runner.run()
    """
    # Import adapters here to avoid circular imports
    from .adapters.backtest import (
        BacktestDataProvider,
        BacktestExchange,
    )
    from .adapters.state import InMemoryStateStore

    # TYPE_CHECKING imports
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from ..backtest.runtime.feed_store import FeedStore
        from ..backtest.sim.exchange import SimulatedExchange
        from src.structures import MultiTFIncrementalState

    # Get account config from Play
    account = play.account

    # Extract sizing from risk_model if present
    risk_per_trade_pct = 1.0  # Default
    if play.risk_model and play.risk_model.sizing:
        risk_per_trade_pct = play.risk_model.sizing.value

    # Extract max_leverage from risk_model if present (match factory path)
    max_leverage = account.max_leverage
    if play.risk_model and play.risk_model.sizing:
        if play.risk_model.sizing.max_leverage:
            max_leverage = play.risk_model.sizing.max_leverage

    # Create config using correct PlayEngineConfig field names
    # Note: PlayEngineConfig uses rate (0.0006) not bps (6), so convert
    config = PlayEngineConfig(
        mode="backtest",
        initial_equity=account.starting_equity_usdt,
        risk_per_trade_pct=risk_per_trade_pct,
        max_leverage=max_leverage,
        min_trade_usdt=account.min_trade_notional_usdt,
        taker_fee_rate=account.fee_model.taker_bps / 10000.0,  # Convert bps to rate
        maker_fee_rate=account.fee_model.maker_bps / 10000.0,  # Convert bps to rate
        slippage_bps=account.slippage_bps or 2.0,
        persist_state=False,  # Backtest doesn't need state persistence
        on_sl_beyond_liq="reject",
        maintenance_margin_rate=0.004,  # Bybit default MMR
        max_drawdown_pct=getattr(account, 'max_drawdown_pct', 25.0),
    )

    # Apply overrides
    if config_override:
        for key, value in config_override.items():
            if hasattr(config, key):
                setattr(config, key, value)

    # Create adapters
    data_provider = BacktestDataProvider(play)
    exchange = BacktestExchange(play, config)
    state_store = InMemoryStateStore()

    # Wire pre-built FeedStore to data provider
    if feed_store is not None:
        data_provider.set_feed_store(feed_store)

    # Wire pre-built SimulatedExchange to exchange adapter
    if sim_exchange is not None:
        exchange.set_simulated_exchange(sim_exchange)

    # Create the engine
    engine = PlayEngine(
        play=play,
        data_provider=data_provider,
        exchange=exchange,
        state_store=state_store,
        config=config,
    )

    # Wire high_tf/med_tf feeds for multi-timeframe support
    if high_tf_feed is not None:
        engine._high_tf_feed = high_tf_feed
    if med_tf_feed is not None:
        engine._med_tf_feed = med_tf_feed
    if quote_feed is not None:
        engine._quote_feed = quote_feed
    if tf_mapping is not None:
        engine._tf_mapping = tf_mapping
    if incremental_state is not None:
        engine._incremental_state = incremental_state

    # Wire snapshot callback for audits
    if on_snapshot is not None:
        engine.set_on_snapshot(on_snapshot)

    return engine


# =============================================================================
# PROFESSIONAL NAMING ALIASES
# See docs/specs/ENGINE_NAMING_CONVENTION.md for full naming standards
# =============================================================================

# CorePlayEngine is the canonical name for the unified mode-agnostic engine
CorePlayEngine = PlayEngine

# Canonical factory function
create_unified_engine = create_backtest_engine
