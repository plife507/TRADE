"""
Backtest runner for PlayEngine.

Drives the PlayEngine through historical bar data:
1. Loads historical data into FeedStore
2. Initializes SimulatedExchange via adapter
3. Loops through bars, calling engine.process_bar()
4. Collects results and metrics

Usage:
    from src.engine import PlayEngineFactory
    from src.engine.runners import BacktestRunner

    engine = PlayEngineFactory.create(play, mode="backtest")
    runner = BacktestRunner(engine)
    result = runner.run()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..adapters.backtest import BacktestDataProvider, BacktestExchange
from ..play_engine import PlayEngine

if TYPE_CHECKING:
    from ...backtest.play import Play
    from ...backtest.runtime.feed_store import FeedStore
    from ...backtest.sim.exchange import SimulatedExchange
    from ...backtest.types import Trade, EquityPoint


@dataclass
class BacktestResult:
    """
    Result from a backtest run.

    Contains all trading metrics, trades, and equity curve.
    """

    # Identification
    play_id: str
    symbol: str
    timeframe: str

    # Timing
    start_ts: datetime
    end_ts: datetime
    started_at: datetime
    finished_at: datetime

    # Core metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0

    # PnL
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    total_fees: float = 0.0

    # Risk metrics
    max_drawdown_pct: float = 0.0
    max_drawdown_usdt: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0

    # Equity
    initial_equity: float = 0.0
    final_equity: float = 0.0

    # Trade list and equity curve
    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)

    # Execution details
    bars_processed: int = 0
    warmup_bars: int = 0

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)


class BacktestRunner:
    """
    Runner that executes PlayEngine through historical data.

    Responsibilities:
    - Load historical data and build FeedStore
    - Initialize SimulatedExchange
    - Wire adapters to engine
    - Execute bar-by-bar loop
    - Collect and compute results

    The runner handles all backtest-specific concerns while
    PlayEngine handles signal generation.
    """

    def __init__(
        self,
        engine: PlayEngine,
        feed_store: "FeedStore | None" = None,
        sim_exchange: "SimulatedExchange | None" = None,
    ):
        """
        Initialize backtest runner.

        Args:
            engine: PlayEngine instance (must be in backtest mode)
            feed_store: Optional pre-built FeedStore (for testing)
            sim_exchange: Optional pre-built SimulatedExchange (for testing)
        """
        self._engine = engine
        self._pre_built_feed_store = feed_store
        self._pre_built_sim_exchange = sim_exchange

        # Validate adapters are backtest type
        if not isinstance(engine._data_provider, BacktestDataProvider):
            raise TypeError(
                f"BacktestRunner requires BacktestDataProvider, "
                f"got {type(engine._data_provider).__name__}"
            )
        if not isinstance(engine._exchange, BacktestExchange):
            raise TypeError(
                f"BacktestRunner requires BacktestExchange, "
                f"got {type(engine._exchange).__name__}"
            )

        self._data_provider: BacktestDataProvider = engine._data_provider
        self._exchange_adapter: BacktestExchange = engine._exchange

    def run(
        self,
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
    ) -> BacktestResult:
        """
        Run the backtest.

        Args:
            start_ts: Optional override for simulation start
            end_ts: Optional override for simulation end

        Returns:
            BacktestResult with metrics and trades
        """
        started_at = datetime.now()

        # Initialize data and exchange
        self._setup()

        # Get data bounds
        num_bars = self._data_provider.num_bars
        warmup_bars = self._data_provider.warmup_bars
        start_idx = warmup_bars
        end_idx = num_bars

        # Get timing from data
        first_candle = self._data_provider.get_candle(start_idx)
        last_candle = self._data_provider.get_candle(end_idx - 1)
        actual_start_ts = start_ts or first_candle.ts_open
        actual_end_ts = end_ts or last_candle.ts_close

        # Track equity curve
        equity_curve = []
        initial_equity = self._exchange_adapter.get_equity()

        # Main bar loop
        for bar_idx in range(start_idx, end_idx):
            # Update current bar index in data provider
            self._data_provider.current_bar_index = bar_idx

            # Get candle for this bar
            candle = self._data_provider.get_candle(bar_idx)

            # Process bar through engine (signal generation)
            signal = self._engine.process_bar(bar_idx)

            # Execute signal if any
            if signal is not None:
                self._engine.execute_signal(signal)

            # Step exchange (process fills, TP/SL)
            self._step_exchange(bar_idx)

            # Record equity
            equity = self._exchange_adapter.get_equity()
            equity_curve.append({
                "bar_idx": bar_idx,
                "ts": candle.ts_close,
                "equity": equity,
            })

        # Close any remaining position
        self._close_remaining_position(end_idx - 1)

        # Build result
        finished_at = datetime.now()
        final_equity = self._exchange_adapter.get_equity()
        trades = self._exchange_adapter.trades

        return self._build_result(
            play_id=self._engine._play.play_id,
            symbol=self._data_provider.symbol,
            timeframe=self._data_provider.timeframe,
            start_ts=actual_start_ts,
            end_ts=actual_end_ts,
            started_at=started_at,
            finished_at=finished_at,
            initial_equity=initial_equity,
            final_equity=final_equity,
            trades=trades,
            equity_curve=equity_curve,
            bars_processed=end_idx - start_idx,
            warmup_bars=warmup_bars,
        )

    def _setup(self) -> None:
        """
        Set up data provider and exchange for the run.

        Either uses pre-built components or creates new ones.
        """
        # Set up FeedStore
        if self._pre_built_feed_store is not None:
            self._data_provider.set_feed_store(self._pre_built_feed_store)
        else:
            # Build FeedStore from Play (requires data loading)
            self._build_feed_store()

        # Set up SimulatedExchange
        if self._pre_built_sim_exchange is not None:
            self._exchange_adapter.set_simulated_exchange(self._pre_built_sim_exchange)
        else:
            # Build SimulatedExchange from config
            self._build_sim_exchange()

    def _build_feed_store(self) -> None:
        """
        Build FeedStore from Play configuration.

        Loads historical data, computes indicators, and creates
        the FeedStore for O(1) access in the hot loop.
        """
        # Import here to avoid circular imports
        from ...backtest.engine_data_prep import prepare_backtest_frame_impl
        from ...backtest.engine_feed_builder import build_feed_stores_impl
        from ...backtest.runtime.feed_store import FeedStore

        play = self._engine._play
        config = self._engine._config

        # For now, raise NotImplementedError - full implementation
        # requires integrating with BacktestEngine data loading
        raise NotImplementedError(
            "Full FeedStore building requires BacktestEngine integration. "
            "Use pre-built FeedStore for now."
        )

    def _build_sim_exchange(self) -> None:
        """
        Build SimulatedExchange from config.

        Creates and configures the SimulatedExchange for order
        execution during the backtest.
        """
        from ...backtest.sim.exchange import SimulatedExchange
        from ...backtest.sim.types import ExecutionConfig

        play = self._engine._play
        config = self._engine._config

        # Create exchange with config
        sim_exchange = SimulatedExchange(
            symbol=play.symbol,
            initial_capital=config.initial_equity,
            execution_config=ExecutionConfig(
                slippage_bps=config.slippage_bps,
            ),
        )

        self._exchange_adapter.set_simulated_exchange(sim_exchange)

    def _step_exchange(self, bar_idx: int) -> None:
        """
        Step the exchange for a bar.

        Processes order fills, TP/SL checks, etc.

        Args:
            bar_idx: Current bar index
        """
        sim_exchange = self._exchange_adapter._sim_exchange
        if sim_exchange is None:
            return

        # Build Bar for SimulatedExchange
        from ...backtest.sim.types import Bar

        candle = self._data_provider.get_candle(bar_idx)
        bar = Bar(
            symbol=self._data_provider.symbol,
            tf=self._data_provider.timeframe,
            ts_open=candle.ts_open,
            ts_close=candle.ts_close,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
        )

        # Get previous bar if available
        prev_bar = None
        if bar_idx > 0:
            prev_candle = self._data_provider.get_candle(bar_idx - 1)
            prev_bar = Bar(
                symbol=self._data_provider.symbol,
                tf=self._data_provider.timeframe,
                ts_open=prev_candle.ts_open,
                ts_close=prev_candle.ts_close,
                open=prev_candle.open,
                high=prev_candle.high,
                low=prev_candle.low,
                close=prev_candle.close,
                volume=prev_candle.volume,
            )

        # Process bar
        sim_exchange.set_bar_context(bar_idx)
        sim_exchange.process_bar(bar, prev_bar)

    def _close_remaining_position(self, last_bar_idx: int) -> None:
        """
        Close any remaining position at end of backtest.

        Args:
            last_bar_idx: Index of last bar
        """
        sim_exchange = self._exchange_adapter._sim_exchange
        if sim_exchange is None or sim_exchange.position is None:
            return

        candle = self._data_provider.get_candle(last_bar_idx)
        sim_exchange.force_close_position(
            price=candle.close,
            timestamp=candle.ts_close,
            reason="end_of_data",
        )

    def _build_result(
        self,
        play_id: str,
        symbol: str,
        timeframe: str,
        start_ts: datetime,
        end_ts: datetime,
        started_at: datetime,
        finished_at: datetime,
        initial_equity: float,
        final_equity: float,
        trades: list,
        equity_curve: list,
        bars_processed: int,
        warmup_bars: int,
    ) -> BacktestResult:
        """
        Build BacktestResult from run data.

        Computes metrics from trades and equity curve.
        """
        # Compute basic metrics
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.net_pnl > 0)
        losing_trades = sum(1 for t in trades if t.net_pnl <= 0)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        # Compute PnL
        gross_profit = sum(t.net_pnl for t in trades if t.net_pnl > 0)
        gross_loss = abs(sum(t.net_pnl for t in trades if t.net_pnl < 0))
        net_profit = final_equity - initial_equity
        total_fees = sum(t.fees_paid for t in trades)

        # Compute profit factor
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

        # Compute max drawdown
        max_equity = initial_equity
        max_drawdown_usdt = 0.0
        for point in equity_curve:
            equity = point["equity"]
            if equity > max_equity:
                max_equity = equity
            drawdown = max_equity - equity
            if drawdown > max_drawdown_usdt:
                max_drawdown_usdt = drawdown

        max_drawdown_pct = (max_drawdown_usdt / initial_equity * 100) if initial_equity > 0 else 0.0

        return BacktestResult(
            play_id=play_id,
            symbol=symbol,
            timeframe=timeframe,
            start_ts=start_ts,
            end_ts=end_ts,
            started_at=started_at,
            finished_at=finished_at,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            net_profit=net_profit,
            total_fees=total_fees,
            max_drawdown_pct=max_drawdown_pct,
            max_drawdown_usdt=max_drawdown_usdt,
            profit_factor=profit_factor,
            initial_equity=initial_equity,
            final_equity=final_equity,
            trades=trades,
            equity_curve=equity_curve,
            bars_processed=bars_processed,
            warmup_bars=warmup_bars,
        )
