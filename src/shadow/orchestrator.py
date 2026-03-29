"""
ShadowOrchestrator — manages N concurrent ShadowEngines.

Responsibilities:
- Add/remove/restart engines (play lifecycle)
- SharedFeedHub coordination (one WS per symbol, fan-out)
- Resource limits (max engines, max per symbol)
- Health monitoring (stale engine detection, auto-restart)
- Batch DB writes (accumulate, flush periodically)
- Graceful shutdown (stop all engines, flush, close feeds)

Memory: orchestrator itself is lightweight. The engines and feeds
hold the data. The orchestrator just coordinates.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

from ..utils.datetime_utils import utc_now
from ..utils.logger import get_module_logger

from .config import ShadowConfig, ShadowPlayConfig
from .engine import ShadowEngine
from .feed_hub import SharedFeedHub
from .types import ShadowEngineState, ShadowEngineStats, ShadowInstanceInfo

if TYPE_CHECKING:
    from ..backtest.play import Play

logger = get_module_logger(__name__)


class ShadowOrchestrator:
    """Manages multiple concurrent ShadowEngines.

    Usage:
        orch = ShadowOrchestrator()
        iid = orch.add_play(play)
        orch.list_plays()
        stats = orch.remove_play(iid)
        orch.stop()
    """

    def __init__(self, config: ShadowConfig | None = None) -> None:
        self._config = config or ShadowConfig()
        self._engines: dict[str, ShadowEngine] = {}   # instance_id -> engine
        self._feed_hub = SharedFeedHub()
        self._started_at = utc_now()

        # Background tasks (set by start())
        self._health_task: asyncio.Task[None] | None = None
        self._flush_task: asyncio.Task[None] | None = None
        self._running = False

    # ── Properties ──────────────────────────────────────────────

    @property
    def engine_count(self) -> int:
        return len(self._engines)

    @property
    def active_symbols(self) -> list[str]:
        return self._feed_hub.active_symbols

    # ── Play Lifecycle ──────────────────────────────────────────

    def add_play(
        self,
        play: Play,
        play_config: ShadowPlayConfig | None = None,
        instance_id: str | None = None,
    ) -> str:
        """Add a play to the shadow exchange. Returns instance_id.

        Creates a ShadowEngine, registers it with the SharedFeedHub,
        and starts processing candles.

        Raises:
            ValueError: If engine limits exceeded
        """
        # Check limits
        self._check_limits(play)

        iid = instance_id or uuid.uuid4().hex[:12]
        config = play_config or self._config.default_play_config
        symbol = play.symbol_universe[0]

        # Create and initialize engine
        engine = ShadowEngine(
            play=play,
            instance_id=iid,
            play_config=config,
            snapshot_interval_seconds=self._config.snapshot_interval_seconds,
        )
        engine.initialize()

        # Ensure WS feed exists for this symbol
        self._feed_hub.ensure_feed(symbol)

        # Register engine to receive candles
        self._feed_hub.register_engine(symbol, engine)

        self._engines[iid] = engine

        logger.info(
            "Orchestrator: added play %s (%s) as %s [%d engines total]",
            play.id, symbol, iid, len(self._engines),
        )
        return iid

    def remove_play(self, instance_id: str) -> ShadowEngineStats:
        """Stop and remove a play. Returns final stats.

        Raises:
            KeyError: If instance_id not found
        """
        engine = self._engines.pop(instance_id)
        symbol = engine.symbol

        # Flush buffered data before stopping
        self._flush_engine(engine)

        # Stop engine
        stats = engine.stop()

        # Unregister from feed (may close WS if last listener)
        self._feed_hub.unregister_engine(symbol, engine)

        logger.info(
            "Orchestrator: removed %s (trades=%d pnl=%.2f)",
            instance_id, stats.trades_closed, stats.cumulative_pnl_usdt,
        )
        return stats

    def list_plays(self) -> list[ShadowInstanceInfo]:
        """List all running shadow plays with live stats."""
        result = []
        for iid, engine in self._engines.items():
            result.append(ShadowInstanceInfo(
                instance_id=iid,
                play_id=engine.play.id,
                symbol=engine.symbol,
                exec_tf=engine.play.exec_tf,
                state=engine.state,
                stats=engine.stats,
            ))
        return result

    def get_engine(self, instance_id: str) -> ShadowEngine | None:
        """Get engine by instance ID."""
        return self._engines.get(instance_id)

    def get_stats(self, instance_id: str) -> ShadowEngineStats | None:
        """Get live stats for a specific play."""
        engine = self._engines.get(instance_id)
        return engine.stats if engine else None

    # ── Async Lifecycle ─────────────────────────────────────────

    async def start(self) -> None:
        """Start background tasks (health check, DB flush)."""
        self._running = True
        self._health_task = asyncio.create_task(self._health_loop())
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("Orchestrator: background tasks started")

    async def stop(self) -> None:
        """Graceful shutdown: stop all engines, close all feeds, flush."""
        self._running = False

        # Cancel background tasks
        for task in (self._health_task, self._flush_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Stop all engines
        for iid in list(self._engines):
            try:
                self.remove_play(iid)
            except Exception as e:
                logger.warning("Error stopping engine %s: %s", iid, e)

        # Close all feeds
        self._feed_hub.stop()

        logger.info("Orchestrator: shutdown complete")

    # ── Background Tasks ────────────────────────────────────────

    async def _health_loop(self) -> None:
        """Periodic health check — detect and restart stale engines."""
        interval = self._config.health_check_interval_seconds
        stale_threshold = self._config.stale_threshold_seconds

        while self._running:
            await asyncio.sleep(interval)

            for iid, engine in list(self._engines.items()):
                if engine.state == ShadowEngineState.ERROR:
                    logger.warning("Engine %s in ERROR state", iid)
                    if self._config.auto_restart_on_stale:
                        await self._restart_engine(iid)

                elif engine.is_stale(stale_threshold):
                    logger.warning("Engine %s stale (no candle in %ds)", iid, stale_threshold)
                    if self._config.auto_restart_on_stale:
                        await self._restart_engine(iid)

    async def _flush_loop(self) -> None:
        """Periodic flush of buffered trades/snapshots to DB.

        Engines accumulate trades and snapshots in memory buffers.
        This loop drains them periodically for batch DB writes.
        """
        interval = self._config.db_flush_interval_seconds

        while self._running:
            await asyncio.sleep(interval)
            self._flush_all()

    async def _restart_engine(self, instance_id: str) -> None:
        """Restart a stale/errored engine."""
        engine = self._engines.get(instance_id)
        if engine is None:
            return

        play = engine.play
        config = engine._config
        symbol = engine.symbol

        # Stop old engine
        try:
            self._flush_engine(engine)
            engine.stop()
            self._feed_hub.unregister_engine(symbol, engine)
        except Exception as e:
            logger.warning("Error stopping engine %s for restart: %s", instance_id, e)

        del self._engines[instance_id]

        # Create new engine with same config
        try:
            self.add_play(play, play_config=config, instance_id=instance_id)
            logger.info("Engine %s restarted", instance_id)
        except Exception as e:
            logger.error("Failed to restart engine %s: %s", instance_id, e)

    # ── Flush / DB Integration ──────────────────────────────────

    def _flush_all(self) -> None:
        """Drain all engine buffers. Called by flush loop."""
        total_trades = 0
        total_snapshots = 0

        for engine in self._engines.values():
            trades = engine.drain_trades()
            snapshots = engine.drain_snapshots()
            total_trades += len(trades)
            total_snapshots += len(snapshots)

            # TODO: write to ShadowPerformanceDB when implemented
            # self._perf_db.batch_write_trades(trades)
            # self._perf_db.batch_write_snapshots(snapshots)

        if total_trades > 0 or total_snapshots > 0:
            logger.info(
                "Orchestrator flush: %d trades, %d snapshots",
                total_trades, total_snapshots,
            )

    def _flush_engine(self, engine: ShadowEngine) -> None:
        """Flush a single engine's buffers (called before stop)."""
        trades = engine.drain_trades()
        snapshots = engine.drain_snapshots()
        if trades or snapshots:
            logger.info(
                "Flushed engine %s: %d trades, %d snapshots",
                engine.instance_id, len(trades), len(snapshots),
            )
            # TODO: write to ShadowPerformanceDB

    # ── Limit Checks ────────────────────────────────────────────

    def _check_limits(self, play: Play) -> None:
        """Check engine limits before adding a new play.

        Raises ValueError if limits exceeded.
        """
        # Total engine limit
        if len(self._engines) >= self._config.max_engines:
            raise ValueError(
                f"Max engines ({self._config.max_engines}) reached. "
                f"Remove an engine before adding another."
            )

        # Per-symbol limit
        symbol = play.symbol_universe[0]
        symbol_count = sum(
            1 for e in self._engines.values() if e.symbol == symbol
        )
        if symbol_count >= self._config.max_engines_per_symbol:
            raise ValueError(
                f"Max engines per symbol ({self._config.max_engines_per_symbol}) "
                f"reached for {symbol}."
            )
