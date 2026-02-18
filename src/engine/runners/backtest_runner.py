"""
Backtest runner for PlayEngine.

Drives the PlayEngine through historical bar data:
1. Loads historical data into FeedStore
2. Initializes SimulatedExchange via adapter
3. Loops through bars, calling engine.process_bar()
4. Collects results and metrics

FILL MECHANICS (CRITICAL FOR LIVE PARITY):
==========================================
Signal-to-fill timeline for 5m exec timeframe:

    5m Bar N:     12:00 - 12:05  <- Signal generated at 12:05 close
    5m Bar N+1:   12:05 - 12:10  <- Fill executed here

    1m bars within Bar N+1:
      12:05 - 12:06  <- Fill at THIS bar's OPEN (12:05:00)
      12:06 - 12:07
      ...

Fill price = first 1m bar's OPEN within next exec bar + slippage

This ensures:
- No look-ahead bias (can't fill at signal bar's close price)
- 1m granularity for accurate entry timing
- Realistic for market orders (fill in milliseconds, not minutes)

LIVE INTEGRATION CHECK:
- Live should fill at current market price (equivalent to "next tick")
- Backtest 1m open approximates this without look-ahead
- Verify live fill prices align with backtest assumptions

Usage:
    from src.engine import PlayEngineFactory
    from src.engine.runners import BacktestRunner

    engine = PlayEngineFactory.create(play, mode="backtest")
    runner = BacktestRunner(engine)
    result = runner.run()
"""

from types import SimpleNamespace

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..adapters.backtest import BacktestDataProvider, BacktestExchange
from ..play_engine import PlayEngine

# Import metrics calculation for proper Sharpe/Sortino/etc computation
from ...backtest.metrics import compute_backtest_metrics
from ...backtest.runtime.timeframe import tf_minutes
from ...backtest.types import EquityPoint, StopReason

if TYPE_CHECKING:
    from ...backtest.play import Play
    from ...backtest.runtime.feed_store import FeedStore
    from ...backtest.sim.exchange import SimulatedExchange


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


    @property
    def metrics(self):
        """
        Compatibility property for legacy metrics access.

        Returns a SimpleNamespace with field names matching the old BacktestResult.metrics format.
        Uses computed_metrics from metadata when available (properly computed Sharpe/Sortino/etc).
        """
        # Get computed metrics from metadata if available
        computed = self.metadata.get("computed_metrics")

        if computed is not None:
            # Use fully computed metrics
            return SimpleNamespace(
                # Core trade metrics
                total_trades=computed.total_trades,
                win_count=computed.win_count,
                loss_count=computed.loss_count,
                win_rate=computed.win_rate,

                # PnL metrics
                net_profit=computed.net_profit,
                gross_profit=computed.gross_profit,
                gross_loss=computed.gross_loss,
                net_return_pct=computed.net_return_pct,

                # Drawdown
                max_drawdown_abs=computed.max_drawdown_abs,
                max_drawdown_pct=computed.max_drawdown_pct,
                max_drawdown_duration_bars=computed.max_drawdown_duration_bars,

                # Risk-adjusted returns (NOW PROPERLY COMPUTED)
                sharpe=computed.sharpe,
                sortino=computed.sortino,
                calmar=computed.calmar,
                profit_factor=computed.profit_factor,

                # Trade analytics (NOW PROPERLY COMPUTED)
                avg_win_usdt=computed.avg_win_usdt,
                avg_loss_usdt=computed.avg_loss_usdt,
                largest_win_usdt=computed.largest_win_usdt,
                largest_loss_usdt=computed.largest_loss_usdt,
                avg_trade_duration_bars=computed.avg_trade_duration_bars,
                max_consecutive_wins=computed.max_consecutive_wins,
                max_consecutive_losses=computed.max_consecutive_losses,
                expectancy_usdt=computed.expectancy_usdt,
                payoff_ratio=computed.payoff_ratio,
                recovery_factor=computed.recovery_factor,
                total_fees=computed.total_fees,

                # Long/short breakdown
                long_trades=computed.long_trades,
                short_trades=computed.short_trades,
                long_win_rate=computed.long_win_rate,
                short_win_rate=computed.short_win_rate,
                long_pnl=computed.long_pnl,
                short_pnl=computed.short_pnl,

                # Time metrics
                total_bars=computed.total_bars,
                bars_in_position=computed.bars_in_position,
                time_in_market_pct=computed.time_in_market_pct,

                # Timing (for eval_start_ts_ms extraction)
                simulation_start=self.start_ts,
            )

        # Fallback to basic metrics if computed_metrics not available
        return SimpleNamespace(
            total_trades=self.total_trades,
            win_count=self.winning_trades,
            loss_count=self.losing_trades,
            win_rate=self.win_rate,
            net_profit=self.net_profit,
            gross_profit=self.gross_profit,
            gross_loss=abs(self.gross_loss),
            net_return_pct=((self.final_equity - self.initial_equity) / self.initial_equity * 100.0) if self.initial_equity > 0 else 0.0,
            max_drawdown_abs=self.max_drawdown_usdt,
            max_drawdown_pct=self.max_drawdown_pct,
            max_drawdown_duration_bars=0,
            sharpe=self.sharpe_ratio,
            sortino=0.0,
            calmar=0.0,
            profit_factor=self.profit_factor,
            avg_win_usdt=0.0,
            avg_loss_usdt=0.0,
            largest_win_usdt=0.0,
            largest_loss_usdt=0.0,
            avg_trade_duration_bars=0,
            max_consecutive_wins=0,
            max_consecutive_losses=0,
            expectancy_usdt=0.0,
            payoff_ratio=0.0,
            recovery_factor=0.0,
            total_fees=self.total_fees,
            long_trades=0,
            short_trades=0,
            long_win_rate=0.0,
            short_win_rate=0.0,
            long_pnl=0.0,
            short_pnl=0.0,
            total_bars=self.bars_processed,
            bars_in_position=0,
            time_in_market_pct=0.0,
            simulation_start=self.start_ts,
        )

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
        sim_start_idx: int | None = None,
    ):
        """
        Initialize backtest runner.

        Args:
            engine: PlayEngine instance (must be in backtest mode)
            feed_store: Optional pre-built FeedStore (for testing)
            sim_exchange: Optional pre-built SimulatedExchange (for testing)
            sim_start_idx: Optional simulation start index (skips warmup period)
        """
        self._engine = engine
        self._pre_built_feed_store = feed_store
        self._pre_built_sim_exchange = sim_exchange
        self._sim_start_idx_override = sim_start_idx

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
        # Use override if provided, otherwise fall back to data provider's warmup_bars
        if self._sim_start_idx_override is not None:
            start_idx = self._sim_start_idx_override
        else:
            start_idx = self._data_provider.warmup_bars
        end_idx = num_bars
        warmup_bars = start_idx  # For result metadata

        # Get timing from data
        first_candle = self._data_provider.get_candle(start_idx)
        last_candle = self._data_provider.get_candle(end_idx - 1)
        actual_start_ts = start_ts or first_candle.ts_open
        actual_end_ts = end_ts or last_candle.ts_close

        # Track equity curve
        equity_curve = []
        initial_equity = self._exchange_adapter.get_equity()

        # Track time in market
        bars_in_position = 0

        # Track peak equity for max drawdown check
        peak_equity = initial_equity
        max_drawdown_pct = self._engine._config.max_drawdown_pct if hasattr(self._engine._config, 'max_drawdown_pct') else 0.0

        # Stop tracking
        stopped_early = False
        stop_reason = None
        stop_classification = None
        stop_reason_detail = None

        # Extract trailing/BE config from Play's risk model
        trailing_config = None
        break_even_config = None
        atr_feature_id = None
        prev_atr_value = None

        play = self._engine._play
        if play.risk_model is not None:
            if play.risk_model.trailing_config is not None:
                tc = play.risk_model.trailing_config
                trailing_config = {
                    "atr_multiplier": tc.atr_multiplier,
                    "trail_pct": tc.trail_pct,
                    "activation_pct": tc.activation_pct,
                }
                atr_feature_id = tc.atr_feature_id

            if play.risk_model.break_even_config is not None:
                bc = play.risk_model.break_even_config
                break_even_config = {
                    "activation_pct": bc.activation_pct,
                    "offset_pct": bc.offset_pct,
                }

        # Main bar loop
        # Execution model:
        # 1. Orders submitted at bar N-1 close fill at bar N open
        # 2. Strategy evaluates at bar N close -> generates signal
        # 3. Signal submits order (to fill at bar N+1 open)
        bar_idx = start_idx
        for bar_idx in range(start_idx, end_idx):
            # Update current bar index in data provider
            self._data_provider.current_bar_index = bar_idx

            # Get candle for this bar
            candle = self._data_provider.get_candle(bar_idx)

            # Set bar context on exchange BEFORE processing
            self._set_bar_context(bar_idx)

            # 1. Process fills from previous bar's orders (fill at THIS bar's open)
            # Also updates trailing/BE stops using previous bar's ATR
            _liquidated = self._process_bar_fills(
                bar_idx,
                trailing_config=trailing_config,
                break_even_config=break_even_config,
                atr_value=prev_atr_value,
            )

            if _liquidated:
                stopped_early = True
                stop_reason = "liquidated"
                stop_classification = StopReason.LIQUIDATED.value
                stop_reason_detail = (
                    f"Liquidation at bar {bar_idx} ({candle.ts_close}): "
                    f"equity fell to or below maintenance margin"
                )
                self._engine.logger.warning(stop_reason_detail)
                break

            # 2. Process bar through engine (signal generation at bar close)
            signal = self._engine.process_bar(bar_idx)

            # 2b. Extract ATR value for next iteration (if trailing is configured)
            if atr_feature_id and self._engine._snapshot_view is not None:
                try:
                    prev_atr_value = self._engine._snapshot_view.get_feature_value(atr_feature_id)
                except (KeyError, AttributeError):
                    prev_atr_value = None

            # 3. Execute signal if any (submits order for NEXT bar's fill)
            if signal is not None:
                self._engine.execute_signal(signal)

            # Track time in market (check position after fills and signals)
            if self._exchange_adapter.has_position:
                bars_in_position += 1

            # Record equity
            equity = self._exchange_adapter.get_equity()
            equity_curve.append({
                "bar_idx": bar_idx,
                "timestamp": candle.ts_close,
                "equity": equity,
            })

            # Update peak equity and check max drawdown
            peak_equity = max(peak_equity, equity)
            if max_drawdown_pct > 0 and peak_equity > 0:
                current_dd_pct = (peak_equity - equity) / peak_equity * 100
                if current_dd_pct >= max_drawdown_pct:
                    # Max drawdown hit - stop backtest
                    stopped_early = True
                    stop_reason = "max_drawdown"
                    stop_classification = StopReason.MAX_DRAWDOWN_HIT.value
                    stop_reason_detail = (
                        f"Max drawdown hit: {current_dd_pct:.2f}% >= {max_drawdown_pct:.2f}% "
                        f"(equity ${equity:.2f}, peak ${peak_equity:.2f})"
                    )
                    self._engine.logger.warning(stop_reason_detail)
                    break

        # Close any remaining position (at last processed bar or stop bar)
        last_bar_idx = bar_idx if stopped_early else end_idx - 1
        close_reason = stop_reason if stopped_early else None
        self._close_remaining_position(last_bar_idx, close_reason)

        # Update equity curve after force close so equity_curve[-1] includes
        # exit fees and slippage from the end-of-data close.  Without this,
        # equity_curve[-1] reflects unrealized PnL at mark price (bar close)
        # but NOT the exit fee/slippage, causing sum(trades.net_pnl) to
        # diverge from (final_equity - initial_equity) by ~$7 per run.
        post_close_equity = self._exchange_adapter.get_equity()
        last_candle = self._data_provider.get_candle(last_bar_idx)
        equity_curve.append({
            "bar_idx": last_bar_idx,
            "timestamp": last_candle.ts_close,
            "equity": post_close_equity,
        })

        # Build result
        finished_at = datetime.now()
        final_equity = post_close_equity
        trades = self._exchange_adapter.trades
        actual_bars_processed = last_bar_idx - start_idx + 1

        return self._build_result(
            play_id=self._engine._play.name or "unknown",
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
            bars_processed=actual_bars_processed,
            warmup_bars=warmup_bars,
            bars_in_position=bars_in_position,
            stopped_early=stopped_early,
            stop_reason=stop_reason,
            stop_classification=stop_classification,
            stop_reason_detail=stop_reason_detail,
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

        NOTE: This method is deprecated. Use DataBuilder via create_engine_from_play()
        to get pre-built FeedStore, then pass to BacktestRunner constructor.
        """
        raise RuntimeError(
            "BacktestRunner requires pre-built FeedStore. "
            "Use create_engine_from_play() which returns a PlayEngine with pre-built data."
        )

    def _build_sim_exchange(self) -> None:
        """
        Build SimulatedExchange from config.

        Creates and configures the SimulatedExchange for order
        execution during the backtest.
        """
        from ...backtest.sim.exchange import SimulatedExchange
        from ...backtest.sim.types import ExecutionConfig
        from ...backtest.system_config import RiskProfileConfig

        play = self._engine._play
        config = self._engine._config

        # Build RiskProfileConfig from Play/config for proper margin calculation
        # This ensures the SimulatedExchange uses the correct leverage/IMR
        risk_profile = RiskProfileConfig(
            initial_equity=config.initial_equity,
            max_leverage=config.max_leverage,
            risk_per_trade_pct=config.risk_per_trade_pct,
            taker_fee_rate=config.taker_fee_rate,
            min_trade_usdt=config.min_trade_usdt,
        )

        # Create exchange with config
        sim_exchange = SimulatedExchange(
            symbol=play.symbol_universe[0],
            initial_capital=config.initial_equity,
            execution_config=ExecutionConfig(
                slippage_bps=config.slippage_bps or 2.0,
            ),
            risk_profile=risk_profile,
        )

        self._exchange_adapter.set_simulated_exchange(sim_exchange)

    def _set_bar_context(self, bar_idx: int) -> None:
        """
        Set the bar context on the exchange before signal processing.

        This allows orders to be submitted with proper price context
        and ensures deterministic timestamps.

        Args:
            bar_idx: Current bar index
        """
        sim_exchange = self._exchange_adapter._sim_exchange
        if sim_exchange is None:
            return

        sim_exchange.set_bar_context(bar_idx)

        # Set deterministic timestamp on exchange adapter
        candle = self._data_provider.get_candle(bar_idx)
        self._exchange_adapter.set_current_bar_timestamp(candle.ts_close)

    def _process_bar_fills(
        self,
        bar_idx: int,
        trailing_config: dict | None = None,
        break_even_config: dict | None = None,
        atr_value: float | None = None,
    ) -> bool:
        """
        Process order fills and TP/SL for a bar.

        Called after signal execution to process any new orders
        and check existing positions for TP/SL.

        Uses 1m granularity for entry fills when quote_feed is available.
        Also updates trailing/BE stops if configured.

        Args:
            bar_idx: Current bar index
            trailing_config: Optional trailing stop config
            break_even_config: Optional break-even config
            atr_value: ATR value from previous bar (for ATR-based trailing)
        """
        sim_exchange = self._exchange_adapter._sim_exchange
        if sim_exchange is None:
            return False

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

        # Get 1m quote feed from engine for granular entry fills
        quote_feed = self._engine._quote_feed
        exec_1m_range = None
        if quote_feed is not None and quote_feed.length > 0:
            exec_tf_minutes = tf_minutes(self._data_provider.timeframe)
            if exec_tf_minutes > 1:
                try:
                    exec_1m_range = quote_feed.get_1m_indices_for_exec(
                        bar_idx, exec_tf_minutes,
                        exec_ts_open=candle.ts_open,
                        exec_ts_close=candle.ts_close,
                    )
                except (ValueError, IndexError):
                    # Fall back to exec-bar granularity if 1m mapping fails
                    exec_1m_range = None

        # Process bar for fills (with 1m granularity when available)
        # Fill price uses first 1m bar's OPEN within this exec bar (see module docstring)
        # Also updates trailing/BE stops if configured
        step_result = sim_exchange.process_bar(
            bar,
            prev_bar,
            quote_feed=quote_feed,
            exec_1m_range=exec_1m_range,
            trailing_config=trailing_config,
            break_even_config=break_even_config,
            atr_value=atr_value,
        )

        # Log fills with actual 1m-based prices
        # NOTE: Logging happens HERE (not in PlayEngine.execute_signal) because:
        # - Order submission returns before fill (async in backtest flow)
        # - Actual fill price only known after process_bar completes
        # - Live mode logs from PlayEngine since exchange returns fill immediately
        from ...utils.debug import is_debug_enabled, debug_trade
        for fill in step_result.fills:
            if fill.reason.value == "entry":
                self._engine.logger.info(
                    f"Order filled: {fill.side.name} {fill.symbol} "
                    f"price={fill.price:.2f} size={fill.size_usdt:.2f} USDT"
                )
            else:
                reason_label = fill.reason.value.upper().replace("_", " ")
                self._engine.logger.info(
                    f"Exit filled: {reason_label} {fill.symbol} "
                    f"price={fill.price:.2f} size={fill.size_usdt:.2f} USDT"
                )

                # 7.3: Log SL/TP/exit fills via debug_trade
                if is_debug_enabled():
                    debug_trade(
                        self._engine._play_hash, bar_idx,
                        event=fill.reason.value,
                        trade_num=self._engine._total_trades,
                        exit=fill.price,
                        pnl=fill.pnl if hasattr(fill, "pnl") else None,
                    )

        return step_result.liquidation_result.liquidated

    def _close_remaining_position(
        self,
        last_bar_idx: int,
        reason: str | None = None,
    ) -> None:
        """
        Close any remaining position at end of backtest.

        Args:
            last_bar_idx: Index of last bar
            reason: Optional close reason (e.g., "max_drawdown", defaults to "end_of_data")
        """
        sim_exchange = self._exchange_adapter._sim_exchange
        if sim_exchange is None or sim_exchange.position is None:
            return

        candle = self._data_provider.get_candle(last_bar_idx)
        sim_exchange.force_close_position(
            price=candle.close,
            timestamp=candle.ts_close,
            reason=reason or "end_of_data",
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
        bars_in_position: int = 0,
        stopped_early: bool = False,
        stop_reason: str | None = None,
        stop_classification: str | None = None,
        stop_reason_detail: str | None = None,
    ) -> BacktestResult:
        """
        Build BacktestResult from run data.

        Uses compute_backtest_metrics() for proper Sharpe/Sortino/Calmar calculation.
        """
        # Convert equity_curve dicts to EquityPoint objects for metrics calculation
        equity_points = [
            EquityPoint(
                timestamp=point["timestamp"],
                equity=point["equity"],
            )
            for point in equity_curve
        ]

        # Use the full metrics calculation from src/backtest/metrics.py
        # This properly computes Sharpe, Sortino, Calmar, avg win/loss, etc.
        metrics = compute_backtest_metrics(
            equity_curve=equity_points,
            trades=trades,
            tf=timeframe,
            initial_equity=initial_equity,
            bars_in_position=bars_in_position,
            strict_tf=False,  # Don't raise on unknown TF, use default
        )

        return BacktestResult(
            play_id=play_id,
            symbol=symbol,
            timeframe=timeframe,
            start_ts=start_ts,
            end_ts=end_ts,
            started_at=started_at,
            finished_at=finished_at,
            # Core trade metrics from computed metrics
            total_trades=metrics.total_trades,
            winning_trades=metrics.win_count,
            losing_trades=metrics.loss_count,
            win_rate=metrics.win_rate,
            # PnL metrics
            gross_profit=metrics.gross_profit,
            gross_loss=metrics.gross_loss,
            net_profit=metrics.net_profit,
            total_fees=metrics.total_fees,
            # Drawdown
            max_drawdown_pct=metrics.max_drawdown_pct,
            max_drawdown_usdt=metrics.max_drawdown_abs,
            # Risk-adjusted (NOW PROPERLY COMPUTED)
            sharpe_ratio=metrics.sharpe,
            profit_factor=metrics.profit_factor,
            # Equity
            initial_equity=initial_equity,
            final_equity=metrics.final_equity,
            # Raw data
            trades=trades,
            equity_curve=equity_curve,
            bars_processed=bars_processed,
            warmup_bars=warmup_bars,
            # Store full metrics and stop info in metadata
            metadata={
                "computed_metrics": metrics,
                "stopped_early": stopped_early,
                "stop_reason": stop_reason,
                "stop_classification": stop_classification,
                "stop_reason_detail": stop_reason_detail,
            },
        )
