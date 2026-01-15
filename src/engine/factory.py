"""
PlayEngine factory for creating engines in different modes.

The factory provides a unified interface for creating PlayEngine instances:
- Backtest: Historical data with simulated execution
- Demo: Real-time data with Bybit demo API
- Live: Real-time data with Bybit live API
- Shadow: Real-time data with signal logging only

Usage:
    from src.engine import PlayEngineFactory

    # Create backtest engine
    engine = PlayEngineFactory.create(play, mode="backtest")

    # Create demo engine
    engine = PlayEngineFactory.create(play, mode="demo")

    # Create live engine (requires explicit confirmation)
    engine = PlayEngineFactory.create(play, mode="live")
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

        # Extract SL/TP and sizing from risk_model if present
        stop_loss_pct = None
        take_profit_pct = None
        max_position_pct = 95.0  # Default
        if play.risk_model:
            from ..backtest.play.risk_model import StopLossType, TakeProfitType
            if play.risk_model.stop_loss.type == StopLossType.PERCENT:
                stop_loss_pct = play.risk_model.stop_loss.value
            if play.risk_model.take_profit.type == TakeProfitType.PERCENT:
                take_profit_pct = play.risk_model.take_profit.value
            # Get max_position_pct from sizing rule
            if play.risk_model.sizing:
                max_position_pct = play.risk_model.sizing.value

        # Create config
        config = PlayEngineConfig(
            mode="backtest",
            initial_equity=account.starting_equity_usdt,
            max_position_pct=max_position_pct,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            min_trade_usdt=account.min_trade_notional_usdt,
            taker_fee_bps=account.fee_model.taker_bps,
            maker_fee_bps=account.fee_model.maker_bps,
            slippage_bps=account.slippage_bps,
            persist_state=False,  # Backtest doesn't need state persistence
        )

        # Apply overrides
        if config_override:
            for key, value in config_override.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        # Create adapters
        # Note: These will be fully implemented in Phase 2
        # For now, they raise NotImplementedError
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

        # Extract SL/TP and sizing from risk_model if present
        stop_loss_pct = None
        take_profit_pct = None
        max_position_pct = 95.0  # Default
        if play.risk_model:
            from ..backtest.play.risk_model import StopLossType, TakeProfitType
            if play.risk_model.stop_loss.type == StopLossType.PERCENT:
                stop_loss_pct = play.risk_model.stop_loss.value
            if play.risk_model.take_profit.type == TakeProfitType.PERCENT:
                take_profit_pct = play.risk_model.take_profit.value
            # Get max_position_pct from sizing rule
            if play.risk_model.sizing:
                max_position_pct = play.risk_model.sizing.value

        # Create config
        config = PlayEngineConfig(
            mode=mode,
            initial_equity=account.starting_equity_usdt,
            max_position_pct=max_position_pct,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            min_trade_usdt=account.min_trade_notional_usdt,
            taker_fee_bps=account.fee_model.taker_bps,
            maker_fee_bps=account.fee_model.maker_bps,
            slippage_bps=account.slippage_bps,
            persist_state=True,  # Live needs state persistence
            state_save_interval=10,  # Save frequently in live mode
        )

        # Apply overrides
        if config_override:
            for key, value in config_override.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        # Determine if demo mode
        is_demo = mode == "demo"

        # Create adapters
        # Note: These will be fully implemented in Phases 3-4
        # For now, they raise NotImplementedError
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

        # Get max_position_pct from risk_model if present
        max_position_pct = 95.0  # Default
        if play.risk_model and play.risk_model.sizing:
            max_position_pct = play.risk_model.sizing.value

        # Create config (shadow mode doesn't need SL/TP - no execution)
        config = PlayEngineConfig(
            mode="shadow",
            initial_equity=account.starting_equity_usdt,
            max_position_pct=max_position_pct,
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


def create_engine(
    play: "Play",
    mode: Literal["backtest", "demo", "live", "shadow"] = "backtest",
    **kwargs,
) -> PlayEngine:
    """
    Convenience function for creating PlayEngine.

    This is a shortcut for PlayEngineFactory.create().

    Args:
        play: Play instance
        mode: Execution mode
        **kwargs: Additional arguments for factory

    Returns:
        Configured PlayEngine
    """
    return PlayEngineFactory.create(play, mode, **kwargs)
