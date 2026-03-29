"""
ShadowEngine — single play running with real SimExchange on live WS data.

Each ShadowEngine is fully isolated:
- Own SimulatedExchange (ledger, order book, position)
- Own PlayEngine (signal state, indicators, structures)
- Own LiveDataProvider (candle buffers, indicator caches)
- Own ShadowJournal (JSONL trade log)

The ShadowOrchestrator manages N of these concurrently, feeding them
candles from a SharedFeedHub (one WS per symbol, fan-out).

Memory budget: ~50 MB per engine (LiveDataProvider dominates at ~30 MB).
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

from ..utils.datetime_utils import utc_now
from ..utils.logger import get_module_logger

from .config import ShadowPlayConfig
from .journal import ShadowJournal
from .types import ShadowEngineState, ShadowEngineStats, ShadowSnapshot, ShadowTrade

if TYPE_CHECKING:
    from ..backtest.play import Play
    from ..backtest.sim.exchange import SimulatedExchange
    from ..backtest.sim.types import Fill, StepResult
    from ..backtest.runtime.types import Bar
    from ..engine.interfaces import Candle
    from ..engine.play_engine import PlayEngine, PlayEngineConfig

logger = get_module_logger(__name__)


class ShadowEngine:
    """Single play running in shadow mode with full SimExchange simulation.

    Lifecycle:
        CREATED -> initialize() -> WARMING_UP -> (enough bars) -> RUNNING -> stop() -> STOPPED

    The orchestrator calls on_candle() for each closed candle from the WS feed.
    The engine processes it through both SimExchange (fills) and PlayEngine (signals).
    """

    __slots__ = (
        "_play",
        "_instance_id",
        "_config",
        "_sim_exchange",
        "_engine",
        "_journal",
        "_state",
        "_stats",
        "_prev_bar",
        "_latest_mark_price",
        "_latest_last_price",
        "_latest_index_price",
        "_latest_funding_rate",
        "_last_snapshot_time",
        "_snapshot_interval",
        "_initial_equity",
        "_trades_buffer",
        "_snapshots_buffer",
    )

    def __init__(
        self,
        play: Play,
        instance_id: str | None = None,
        play_config: ShadowPlayConfig | None = None,
        snapshot_interval_seconds: int = 3600,
    ) -> None:
        self._play = play
        self._instance_id = instance_id or uuid.uuid4().hex[:12]
        self._config = play_config or ShadowPlayConfig()
        self._snapshot_interval = snapshot_interval_seconds

        # Set by initialize()
        self._sim_exchange: SimulatedExchange | None = None
        self._engine: PlayEngine | None = None
        self._journal: ShadowJournal | None = None

        # State
        self._state = ShadowEngineState.CREATED
        self._stats = ShadowEngineStats()
        self._prev_bar: Bar | None = None
        self._initial_equity = self._config.initial_equity_usdt

        # External price overrides (from WS ticker)
        self._latest_mark_price: float | None = None
        self._latest_last_price: float | None = None
        self._latest_index_price: float | None = None
        self._latest_funding_rate: float = 0.0

        # Snapshot timing (monotonic to avoid NTP drift)
        self._last_snapshot_time = 0.0

        # Buffered writes for orchestrator to flush
        self._trades_buffer: list[ShadowTrade] = []
        self._snapshots_buffer: list[ShadowSnapshot] = []

    # ── Properties ──────────────────────────────────────────────

    @property
    def instance_id(self) -> str:
        return self._instance_id

    @property
    def play(self) -> Play:
        return self._play

    @property
    def state(self) -> ShadowEngineState:
        return self._state

    @property
    def stats(self) -> ShadowEngineStats:
        return self._stats

    @property
    def symbol(self) -> str:
        return self._play.symbol_universe[0]

    @property
    def equity(self) -> float:
        if self._sim_exchange is not None:
            return self._sim_exchange.equity_usdt
        return self._initial_equity

    # ── Lifecycle ───────────────────────────────────────────────

    def initialize(self) -> None:
        """Create SimExchange, PlayEngine, and journal.

        Call once before feeding candles. Separated from __init__ so
        the orchestrator can batch-initialize engines.
        """
        if self._state != ShadowEngineState.CREATED:
            raise RuntimeError(f"Cannot initialize engine in state {self._state}")

        from ..backtest.sim.exchange import SimulatedExchange
        from ..engine.factory import PlayEngineFactory

        # Create SimExchange with play's risk config
        self._sim_exchange = self._create_sim_exchange()

        # Create PlayEngine in shadow mode with BacktestExchange wrapping the sim
        self._engine = self._create_play_engine()

        # Initialize LiveDataProvider indicator caches with play's feature specs
        # Without this, on_candle_close() pushes OHLCV but indicators never compute
        self._init_indicator_caches()

        # Pre-fill LiveDataProvider with historical bars from DuckDB/REST
        # so warmup completes immediately instead of waiting N minutes for live candles
        self._warmup_from_history()

        # Journal
        self._journal = ShadowJournal(self._instance_id)

        # Stats
        self._stats.started_at = utc_now()
        self._stats.equity_usdt = self._initial_equity
        self._stats.peak_equity_usdt = self._initial_equity
        self._last_snapshot_time = time.monotonic()

        self._state = ShadowEngineState.WARMING_UP
        logger.info(
            "ShadowEngine initialized: %s %s %s equity=%.0f",
            self._instance_id, self._play.id, self.symbol, self._initial_equity,
        )

    def stop(self) -> ShadowEngineStats:
        """Stop the engine and return final stats."""
        self._state = ShadowEngineState.STOPPED
        self._stats.stopped_at = utc_now()

        # Take final snapshot
        self._take_snapshot(force=True)

        if self._journal:
            self._journal.close()

        logger.info(
            "ShadowEngine stopped: %s trades=%d pnl=%.2f dd=%.1f%%",
            self._instance_id,
            self._stats.trades_closed,
            self._stats.cumulative_pnl_usdt,
            self._stats.max_drawdown_pct,
        )
        return self._stats

    # ── Candle Processing (hot path) ────────────────────────────

    def on_ticker(self, mark_price: float, last_price: float, index_price: float, funding_rate: float) -> None:
        """Update external prices from WS ticker. Called before on_candle.

        No allocations — just float assignments.
        """
        self._latest_mark_price = mark_price
        self._latest_last_price = last_price
        self._latest_index_price = index_price
        self._latest_funding_rate = funding_rate

    def on_candle(self, bar: Bar, timeframe: str) -> None:
        """Process a closed candle through the engine.

        Called by the orchestrator for each closed candle from the WS feed.
        This is the hot path — minimize allocations.

        Args:
            bar: Closed candle (canonical Bar type from runtime.types)
            timeframe: Timeframe string (e.g., "15m", "1h")
        """
        if self._state not in (ShadowEngineState.WARMING_UP, ShadowEngineState.RUNNING):
            return

        if self._engine is None or self._sim_exchange is None:
            return

        assert self._journal is not None

        try:
            self._process_candle(bar, timeframe)
        except Exception as e:
            self._state = ShadowEngineState.ERROR
            self._journal.record_error(str(e), utc_now().isoformat())
            logger.error("ShadowEngine %s error: %s", self._instance_id, e)

    def _process_candle(self, bar: Bar, timeframe: str) -> None:
        """Internal candle processing — extracted for clean error boundary."""
        assert self._engine is not None
        assert self._sim_exchange is not None
        assert self._journal is not None

        # 1. Feed candle to LiveDataProvider (updates indicators, structures)
        #    LiveDataProvider expects Candle (interfaces.py), not Bar (runtime.types)
        from ..engine.interfaces import Candle
        candle = Candle(
            ts_open=bar.ts_open,
            ts_close=bar.ts_close,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )
        data_provider = self._engine._data_provider
        data_provider.on_candle_close(candle, timeframe)  # type: ignore[union-attr]

        # 2. Check if this is the exec timeframe
        exec_tf = self._play.exec_tf
        if timeframe != exec_tf:
            return  # Non-exec TF: indicators updated, no signal eval

        # 3. Check warmup
        if not data_provider.is_ready():
            if self._state != ShadowEngineState.WARMING_UP:
                self._state = ShadowEngineState.WARMING_UP
            self._prev_bar = bar
            return

        if self._state == ShadowEngineState.WARMING_UP:
            self._state = ShadowEngineState.RUNNING
            logger.info("ShadowEngine %s warmup complete, running", self._instance_id)

        # 4. Inject external prices into SimExchange's PriceModel
        if self._latest_mark_price is not None:
            self._sim_exchange._price_model.set_external_prices(
                mark_price=self._latest_mark_price,
                last_price=self._latest_last_price,
                index_price=self._latest_index_price,
            )

        # 5. Set bar timestamp on BacktestExchange (required for order submission)
        exchange_adapter = self._engine.exchange
        set_ts = getattr(exchange_adapter, "set_current_bar_timestamp", None)
        if set_ts is not None:
            set_ts(bar.ts_close)

        # 6. Process bar through SimExchange FIRST (fills pending orders from
        #    previous bar's signal — same fill-on-next-bar pattern as backtest)
        step_result = self._sim_exchange.process_bar(
            bar,
            self._prev_bar,
        )

        # 7. Process bar through PlayEngine (signal generation → may submit new order)
        signal = self._engine.process_bar(-1)

        # 7. Update stats (zero allocations)
        self._stats.bars_processed += 1
        self._stats.last_bar_at = bar.ts_close
        self._stats.last_mark_price = step_result.mark_price or bar.close
        self._stats.last_funding_rate = self._latest_funding_rate
        self._stats.update_equity(self._sim_exchange.equity_usdt)

        # 8. Execute signal (submit order to SimExchange for next bar's fill)
        if signal is not None:
            self._stats.signals_generated += 1
            self._engine.execute_signal(signal)
            self._journal.record_signal(
                direction=signal.direction,
                symbol=signal.symbol,
                price=bar.close,
                timestamp_iso=bar.ts_close.isoformat(),
            )

        # 9. Process fills from step_result
        self._process_fills(step_result)

        # 10. Update cumulative PnL
        self._stats.cumulative_pnl_usdt = self._sim_exchange.equity_usdt - self._initial_equity

        # 11. Check drawdown auto-stop
        if (self._config.auto_stop_on_drawdown
                and self._stats.max_drawdown_pct >= self._config.max_drawdown_pct):
            logger.warning(
                "ShadowEngine %s hit max drawdown %.1f%% >= %.1f%%, stopping",
                self._instance_id, self._stats.max_drawdown_pct, self._config.max_drawdown_pct,
            )
            self.stop()
            return

        # 12. Periodic snapshot
        self._take_snapshot()

        self._prev_bar = bar

    def _process_fills(self, step_result: StepResult) -> None:
        """Process fills from SimExchange step result."""
        assert self._journal is not None

        for fill in step_result.fills:
            if fill.reason.value == "entry":
                self._stats.trades_opened += 1
                logger.info(
                    "FILL entry %s %s @ %.4f size=%.4f",
                    fill.side, self.symbol, fill.price, fill.size,
                )
            else:
                # Exit fill — record as completed trade
                self._stats.trades_closed += 1
                pnl = self._compute_trade_pnl(fill)
                if pnl >= 0:
                    self._stats.winning_trades += 1
                else:
                    self._stats.losing_trades += 1

                trade = self._build_trade_record(fill, pnl)
                self._trades_buffer.append(trade)
                self._journal.record_trade(trade)
                logger.info(
                    "FILL exit %s %s @ %.4f pnl=%.2f equity=%.2f",
                    fill.side, self.symbol, fill.price, pnl,
                    self._sim_exchange.equity_usdt if self._sim_exchange else 0,
                )

    def _compute_trade_pnl(self, exit_fill: Fill) -> float:
        """Compute realized PnL from exit fill. Uses sim ledger."""
        # The sim ledger already computed realized PnL — read from it
        if self._sim_exchange is None:
            return 0.0
        ledger = self._sim_exchange._ledger
        return ledger.state.cash_balance_usdt - self._initial_equity - self._stats.cumulative_pnl_usdt

    def _build_trade_record(self, exit_fill: Fill, pnl: float) -> ShadowTrade:
        """Build a ShadowTrade from an exit fill."""
        # Approximate entry info from fill metadata
        return ShadowTrade(
            trade_id=uuid.uuid4().hex[:12],
            instance_id=self._instance_id,
            play_id=self._play.id,
            symbol=exit_fill.symbol,
            direction=exit_fill.side.value,
            entry_time=exit_fill.timestamp,  # approximate
            exit_time=exit_fill.timestamp,
            entry_price=0.0,  # filled by orchestrator from sim position history
            exit_price=exit_fill.price,
            size_usdt=exit_fill.size_usdt,
            pnl_usdt=pnl,
            fees_usdt=exit_fill.fee,
            exit_reason=exit_fill.reason.value,
            mae_pct=0.0,  # TODO: read from sim position tracking
            mfe_pct=0.0,
            duration_minutes=0.0,
            entry_funding_rate=self._latest_funding_rate,
            entry_atr_pct=0.0,
        )

    # ── Snapshots ──────────────────────────────────────────────

    def _take_snapshot(self, force: bool = False) -> None:
        """Take equity snapshot if interval elapsed (or forced)."""
        now_mono = time.monotonic()
        if not force and (now_mono - self._last_snapshot_time) < self._snapshot_interval:
            return

        self._last_snapshot_time = now_mono

        if self._sim_exchange is None:
            return

        assert self._journal is not None

        snapshot = ShadowSnapshot(
            timestamp=utc_now(),
            instance_id=self._instance_id,
            equity_usdt=self._sim_exchange.equity_usdt,
            cash_balance_usdt=self._sim_exchange._ledger.state.cash_balance_usdt,
            unrealized_pnl_usdt=self._sim_exchange._ledger.state.unrealized_pnl_usdt,
            position_side=self._sim_exchange.position.side.value if self._sim_exchange.position else None,
            position_size_usdt=self._sim_exchange.position.size_usdt if self._sim_exchange.position else 0.0,
            mark_price=self._stats.last_mark_price,
            cumulative_pnl_usdt=self._stats.cumulative_pnl_usdt,
            total_trades=self._stats.trades_closed,
            winning_trades=self._stats.winning_trades,
            max_drawdown_pct=self._stats.max_drawdown_pct,
            funding_rate=self._latest_funding_rate,
            atr_pct=0.0,  # TODO: read from indicator cache
        )

        self._snapshots_buffer.append(snapshot)
        self._journal.record_snapshot(snapshot)

    # ── Buffer Access (for orchestrator DB flush) ───────────────

    def drain_trades(self) -> list[ShadowTrade]:
        """Drain buffered trades for DB write. Returns and clears buffer."""
        trades = self._trades_buffer
        self._trades_buffer = []
        return trades

    def drain_snapshots(self) -> list[ShadowSnapshot]:
        """Drain buffered snapshots for DB write. Returns and clears buffer."""
        snapshots = self._snapshots_buffer
        self._snapshots_buffer = []
        return snapshots

    # ── Staleness Detection ────────────────────────────────────

    def is_stale(self, max_age_seconds: float = 300.0) -> bool:
        """Check if engine hasn't received a candle recently."""
        if self._stats.last_bar_at is None:
            return False  # Never received a bar — still in warmup
        age = (utc_now() - self._stats.last_bar_at).total_seconds()
        return age > max_age_seconds

    # ── Factory Helpers ────────────────────────────────────────

    def _create_sim_exchange(self) -> SimulatedExchange:
        """Create a SimulatedExchange from play config."""
        from ..backtest.sim.exchange import SimulatedExchange
        from ..config.constants import DEFAULTS

        play = self._play
        symbol = play.symbol_universe[0]

        # Extract leverage from play's risk model sizing rule
        leverage = DEFAULTS.risk.max_leverage
        if play.risk_model is not None:
            leverage = play.risk_model.sizing.max_leverage

        sim = SimulatedExchange(
            symbol=symbol,
            initial_capital=self._config.initial_equity_usdt,
            leverage=leverage,
        )

        return sim

    def _create_play_engine(self) -> PlayEngine:
        """Create a PlayEngine in shadow mode with BacktestExchange wrapping the sim."""
        from ..engine.adapters.backtest import BacktestExchange
        from ..engine.adapters.live import LiveDataProvider
        from ..engine.adapters.state import InMemoryStateStore
        from ..engine.play_engine import PlayEngine, PlayEngineConfig

        play = self._play

        # Use "backtest" mode so PlayEngine actually executes signals through
        # the BacktestExchange/SimExchange. "shadow" mode skips execution (no-op).
        config = PlayEngineConfig(
            mode="backtest",
            initial_equity=self._config.initial_equity_usdt,
        )

        # LiveDataProvider for real-time indicators/structures
        # Shadow uses LIVE WS data (real market data, paper-trade execution)
        data_provider = LiveDataProvider(play, demo=False)

        # BacktestExchange wrapping our SimExchange
        exchange = BacktestExchange(play, config)
        exchange.set_simulated_exchange(self._sim_exchange)

        state_store = InMemoryStateStore()

        engine = PlayEngine(
            play=play,
            data_provider=data_provider,
            exchange=exchange,
            state_store=state_store,
            config=config,
        )

        return engine

    def _warmup_from_history(self) -> None:
        """Pre-fill LiveDataProvider buffers with historical bars from DuckDB/REST.

        Reuses LiveDataProvider's existing warmup pipeline (same as LiveRunner):
        1. _sync_warmup_data() — fetch from Bybit REST into DuckDB
        2. _load_initial_bars() — load from DuckDB into buffers, compute indicators

        This means shadow engines start ready immediately instead of waiting
        N minutes for enough live candles to fill the warmup window.
        """
        assert self._engine is not None
        from ..engine.adapters.live import LiveDataProvider
        from ..data.realtime_state import RealtimeState
        import asyncio

        dp = self._engine._data_provider
        if not isinstance(dp, LiveDataProvider):
            logger.warning("DataProvider is not LiveDataProvider, skipping history pre-fill")
            return

        try:
            # _load_initial_bars() early-returns if _realtime_state is None.
            # Set a temporary state so the bar-buffer check proceeds (it will be
            # empty, causing fallback to DuckDB/REST — which is what we want).
            if dp._realtime_state is None:
                dp._realtime_state = RealtimeState()

            # Skip _sync_warmup_data() — it writes to DuckDB, which conflicts
            # when multiple shadow engines warm up in parallel (single-writer lock).
            # _load_initial_bars() reads from DuckDB (safe for concurrent reads)
            # and falls back to REST API if DuckDB has insufficient data.
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(dp._load_initial_bars())
            finally:
                loop.close()

            logger.info(
                "ShadowEngine %s warmup from history complete: ready=%s",
                self._instance_id, dp.is_ready(),
            )
        except Exception as e:
            logger.warning(
                "ShadowEngine %s warmup from history failed (will warm up from live): %s",
                self._instance_id, e,
            )

    def _init_indicator_caches(self) -> None:
        """Initialize LiveDataProvider indicator caches with play's feature specs.

        LiveDataProvider.on_candle_close() pushes OHLCV into buffers but
        indicator computation requires initialize_from_history() to register
        the incremental indicator instances. Normally this happens during
        connect() → _load_initial_bars(). For shadow mode (no WS connect),
        we call it directly with a seed candle so specs are registered.
        """
        assert self._engine is not None
        from ..engine.interfaces import Candle

        dp = self._engine._data_provider
        # Access LiveDataProvider internals (type: ignore for protocol)
        get_specs = getattr(dp, "_get_indicator_specs_for_tf", None)
        if get_specs is None:
            return  # Not a LiveDataProvider

        tf_mapping = getattr(dp, "_tf_mapping", {})

        # Create a seed candle (values don't matter — just triggers spec registration)
        seed = Candle(
            ts_open=self._play.features[0].tf if False else utc_now(),  # type: ignore[arg-type]
            ts_close=utc_now(),
            open=50000.0, high=50001.0, low=49999.0, close=50000.0, volume=1000.0,
        )

        # Initialize each TF's indicator cache with its specs
        for tf_role in ("low_tf", "med_tf", "high_tf"):
            cache = getattr(dp, f"_{tf_role}_indicators", None)
            if cache is None:
                continue
            specs = get_specs(tf_role)
            if specs:
                cache.initialize_from_history([seed], specs)
                logger.info(
                    "Initialized %d indicator specs for %s (%s)",
                    len(specs), tf_role, tf_mapping.get(tf_role, "?"),
                )
