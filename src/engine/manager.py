"""
Multi-Instance Engine Manager.

Enables concurrent engine instances for live, demo, and backtest modes.
Enforces instance limits and provides state isolation.


Instance Limits:
- Max 1 live instance (safety)
- Max 1 demo per symbol
- Max 1 backtest at a time (DuckDB limitation)

Usage:
    from src.engine import EngineManager

    manager = EngineManager.get_instance()

    # Start demo trading
    instance_id = await manager.start(play, mode="demo")

    # List running instances
    instances = manager.list()

    # Stop instance
    await manager.stop(instance_id)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from .play_engine import PlayEngine
from .runners.live_runner import LiveRunner
from ..utils.logger import get_logger

if TYPE_CHECKING:
    from ..backtest.play import Play

logger = get_logger()


class InstanceMode(str, Enum):
    """Engine instance mode."""
    LIVE = "live"
    DEMO = "demo"
    BACKTEST = "backtest"
    SHADOW = "shadow"


@dataclass
class InstanceInfo:
    """Information about a running engine instance."""
    instance_id: str
    play_id: str
    symbol: str
    mode: InstanceMode
    started_at: datetime
    status: str
    bars_processed: int = 0
    signals_generated: int = 0
    last_candle_ts: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "play_id": self.play_id,
            "symbol": self.symbol,
            "mode": self.mode.value,
            "started_at": self.started_at.isoformat(),
            "status": self.status,
            "bars_processed": self.bars_processed,
            "signals_generated": self.signals_generated,
            "last_candle_ts": self.last_candle_ts.isoformat() if self.last_candle_ts else None,
        }


@dataclass
class _EngineInstance:
    """Internal tracking of an engine instance."""
    instance_id: str
    play: "Play"
    engine: PlayEngine
    runner: LiveRunner | None  # None for backtest (uses BacktestRunner)
    mode: InstanceMode
    started_at: datetime
    task: asyncio.Task | None = None


class EngineManager:
    """
    Manages multiple concurrent PlayEngine instances.

    Enforces instance limits:
    - Max 1 live instance (safety - prevents multiple real-money bots)
    - Max 1 demo per symbol (prevents duplicate signals)
    - Max 1 backtest at a time (DuckDB sequential access limitation)

    Provides:
    - Instance lifecycle management (start/stop)
    - State isolation between instances
    - Status monitoring
    """

    _instance: "EngineManager | None" = None

    def __init__(self):
        """Initialize manager. Use get_instance() for singleton access."""
        self._instances: dict[str, _EngineInstance] = {}
        self._lock = asyncio.Lock()

        # Instance limits
        self._max_live = 1
        self._max_demo_per_symbol = 1
        self._max_backtest = 1

        # Track counts for fast limit checking
        self._live_count = 0
        self._backtest_count = 0
        self._demo_by_symbol: dict[str, int] = {}

        # G16.4: Cross-process instance tracking
        self._instances_dir = Path(os.path.expanduser("~/.trade/instances"))
        self._instances_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_instance(cls) -> "EngineManager":
        """Get singleton instance of EngineManager."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def start(
        self,
        play: "Play",
        mode: Literal["live", "demo", "shadow", "backtest"],
        on_signal: "Callable | None" = None,
    ) -> str:
        """
        Start a new engine instance.

        Args:
            play: Play configuration
            mode: Execution mode
            on_signal: Optional callback for signal events

        Returns:
            Instance ID for tracking

        Raises:
            ValueError: If instance limits would be exceeded
            RuntimeError: If engine fails to start
        """
        async with self._lock:
            # Check instance limits
            self._check_limits(play, mode)

            # C7: Validate live mode safety before creating engine
            if mode == "live":
                from .factory import PlayEngineFactory
                PlayEngineFactory._validate_live_mode(confirm_live=True)

            # Generate instance ID
            instance_id = f"{play.name}_{mode}_{uuid.uuid4().hex[:8]}"
            symbol = play.symbol_universe[0]

            logger.info(f"Starting engine instance: {instance_id}")

            try:
                if mode == "backtest":
                    # Backtest uses different runner (BacktestRunner)
                    # For now, just track that a backtest is running
                    # Actual backtest is run via CLI tools
                    raise ValueError(
                        "Use CLI 'backtest run' command for backtests. "
                        "EngineManager tracks concurrent instances."
                    )

                # Delegate config construction to shared factory builder
                from .factory import _build_config_from_play
                config = _build_config_from_play(
                    play, mode,
                    persist_state=(mode in ("live", "demo")),
                    state_save_interval=10,
                )

                # Create adapters
                from .adapters.live import LiveDataProvider, LiveExchange
                from .adapters.state import FileStateStore

                demo = (mode == "demo")
                data_provider = LiveDataProvider(play, demo=demo)
                exchange = LiveExchange(play, config, demo=demo)
                state_store = FileStateStore()

                # Create engine
                engine = PlayEngine(
                    play=play,
                    data_provider=data_provider,
                    exchange=exchange,
                    state_store=state_store,
                    config=config,
                )

                # Create runner
                runner = LiveRunner(
                    engine=engine,
                    on_signal=on_signal,
                )

                # G17.3: Set instance_id for pause file-based IPC
                runner._instance_id = instance_id

                # Track instance
                instance = _EngineInstance(
                    instance_id=instance_id,
                    play=play,
                    engine=engine,
                    runner=runner,
                    mode=InstanceMode(mode),
                    started_at=datetime.now(),
                )

                # Start runner in background task
                instance.task = asyncio.create_task(
                    self._run_instance(instance),
                    name=f"engine_{instance_id}",
                )

                self._instances[instance_id] = instance
                self._update_counts(mode, symbol, +1)

                # G16.4: Write cross-process instance file
                self._write_instance_file(instance_id, instance)

                logger.info(f"Engine instance started: {instance_id}")
                return instance_id

            except Exception as e:
                logger.error(f"Failed to start engine: {e}")
                raise RuntimeError(f"Failed to start engine: {e}") from e

    async def stop(self, instance_id: str) -> bool:
        """
        Stop a running engine instance.

        Args:
            instance_id: Instance ID to stop

        Returns:
            True if stopped successfully, False if not found
        """
        async with self._lock:
            if instance_id not in self._instances:
                logger.warning(f"Instance not found: {instance_id}")
                return False

            instance = self._instances[instance_id]
            logger.info(f"Stopping engine instance: {instance_id}")

            try:
                # Stop runner
                if instance.runner is not None:
                    await instance.runner.stop()

                # Cancel task
                if instance.task is not None:
                    instance.task.cancel()
                    try:
                        await instance.task
                    except asyncio.CancelledError:
                        pass

                # Update counts
                symbol = instance.play.symbol_universe[0]
                self._update_counts(instance.mode.value, symbol, -1)

                # G16.4: Remove cross-process instance file
                self._remove_instance_file(instance_id)

                # Remove from tracking
                del self._instances[instance_id]

                logger.info(f"Engine instance stopped: {instance_id}")
                return True

            except Exception as e:
                logger.error(f"Error stopping instance {instance_id}: {e}")
                return False

    def list(self) -> list[InstanceInfo]:
        """
        List all running instances.

        Returns:
            List of InstanceInfo for each running instance
        """
        result = []
        for instance in self._instances.values():
            stats = instance.runner.stats if instance.runner else None
            result.append(InstanceInfo(
                instance_id=instance.instance_id,
                play_id=instance.play.name or "unknown",
                symbol=instance.play.symbol_universe[0],
                mode=instance.mode,
                started_at=instance.started_at,
                status=instance.runner.state.value if instance.runner else "unknown",
                bars_processed=stats.bars_processed if stats else 0,
                signals_generated=stats.signals_generated if stats else 0,
                last_candle_ts=stats.last_candle_ts if stats else None,
            ))
        return result

    def get_runner_stats(self, instance_id: str) -> dict | None:
        """Get detailed runner stats for an instance."""
        instance = self._instances.get(instance_id)
        if instance and instance.runner:
            return instance.runner.stats.to_dict()
        return None

    def get(self, instance_id: str) -> InstanceInfo | None:
        """Get info for a specific instance."""
        if instance_id not in self._instances:
            return None

        instance = self._instances[instance_id]
        stats = instance.runner.stats if instance.runner else None

        return InstanceInfo(
            instance_id=instance.instance_id,
            play_id=instance.play.name or "unknown",
            symbol=instance.play.symbol_universe[0],
            mode=instance.mode,
            started_at=instance.started_at,
            status=instance.runner.state.value if instance.runner else "unknown",
            bars_processed=stats.bars_processed if stats else 0,
            signals_generated=stats.signals_generated if stats else 0,
            last_candle_ts=stats.last_candle_ts if stats else None,
        )

    @property
    def instance_count(self) -> int:
        """Number of running instances."""
        return len(self._instances)

    def _check_limits(self, play: "Play", mode: str | InstanceMode) -> None:
        """Check if starting a new instance would exceed limits."""
        mode = InstanceMode(mode)
        symbol = play.symbol_universe[0]

        if mode is InstanceMode.LIVE:
            if self._live_count >= self._max_live:
                raise ValueError(
                    f"Live instance limit reached ({self._max_live}). "
                    "Stop existing live instance first."
                )

        elif mode is InstanceMode.DEMO:
            current = self._demo_by_symbol.get(symbol, 0)
            if current >= self._max_demo_per_symbol:
                raise ValueError(
                    f"Demo instance limit for {symbol} reached ({self._max_demo_per_symbol}). "
                    "Stop existing demo instance first."
                )

        elif mode is InstanceMode.BACKTEST:
            if self._backtest_count >= self._max_backtest:
                raise ValueError(
                    f"Backtest instance limit reached ({self._max_backtest}). "
                    "DuckDB requires sequential access. Wait for current backtest to complete."
                )

    def _update_counts(self, mode: str | InstanceMode, symbol: str, delta: int) -> None:
        """Update instance counts."""
        mode = InstanceMode(mode)
        if mode is InstanceMode.LIVE:
            self._live_count += delta
        elif mode is InstanceMode.DEMO:
            self._demo_by_symbol[symbol] = self._demo_by_symbol.get(symbol, 0) + delta
            if self._demo_by_symbol[symbol] <= 0:
                del self._demo_by_symbol[symbol]
        elif mode is InstanceMode.BACKTEST:
            self._backtest_count += delta

    async def _run_instance(self, instance: _EngineInstance) -> None:
        """Run an instance until stopped."""
        try:
            if instance.runner is not None:
                await instance.runner.start()
                await instance.runner.wait_until_stopped()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Instance {instance.instance_id} error: {e}")
            # M9: Clean up crashed instance so it doesn't block new starts
            iid = instance.instance_id
            symbol = instance.play.symbol_universe[0]
            mode = instance.mode.value
            if iid in self._instances:
                del self._instances[iid]
                self._update_counts(mode, symbol, -1)
                self._remove_instance_file(iid)
                logger.info(f"Cleaned up crashed instance: {iid}")

    async def stop_all(self) -> int:
        """
        Stop all running instances.

        Returns:
            Number of instances stopped
        """
        stopped = 0
        for instance_id in list(self._instances.keys()):
            if await self.stop(instance_id):
                stopped += 1
        return stopped

    def register_backtest_start(self) -> bool:
        """
        Register that a backtest is starting (called by CLI tools).

        Returns:
            True if backtest can start, False if limit reached
        """
        if self._backtest_count >= self._max_backtest:
            return False
        self._backtest_count += 1
        return True

    def register_backtest_end(self) -> None:
        """Register that a backtest has ended (called by CLI tools)."""
        self._backtest_count = max(0, self._backtest_count - 1)

    # ------------------------------------------------------------------
    # G16.4: Cross-process instance tracking via PID files
    # ------------------------------------------------------------------

    def _write_instance_file(self, instance_id: str, instance: _EngineInstance) -> None:
        """Write instance state to disk for cross-process visibility."""
        data = {
            "instance_id": instance_id,
            "pid": os.getpid(),
            "play_id": instance.play.name,
            "symbol": instance.play.symbol_universe[0],
            "mode": instance.mode.value,
            "started_at": instance.started_at.isoformat(),
        }
        path = self._instances_dir / f"{instance_id}.json"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")

    def _update_instance_file(self, instance_id: str) -> None:
        """Update instance stats in the JSON file."""
        instance = self._instances.get(instance_id)
        if not instance:
            return
        path = self._instances_dir / f"{instance_id}.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            stats = instance.runner.stats if instance.runner else None
            if stats:
                data["stats"] = stats.to_dict()
            data["status"] = instance.runner.state.value if instance.runner else "unknown"
            path.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")
        except Exception as e:
            logger.warning(f"Failed to update instance file {path.name}: {e}")

    def _remove_instance_file(self, instance_id: str) -> None:
        """Remove instance file on stop."""
        path = self._instances_dir / f"{instance_id}.json"
        try:
            path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Failed to remove instance file {path.name}: {e}")

    def list_all(self) -> list[InstanceInfo]:
        """List all instances including cross-process ones from disk."""
        # Start with in-process instances
        result = self.list()
        known_ids = {info.instance_id for info in result}

        # Read disk instances for cross-process visibility
        try:
            for path in self._instances_dir.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    iid = data.get("instance_id", "")
                    if iid in known_ids:
                        continue  # Already in our process

                    # Check if PID is still alive
                    pid = data.get("pid", 0)
                    if not self._is_pid_alive(pid):
                        # Stale file, clean up
                        path.unlink(missing_ok=True)
                        continue

                    result.append(InstanceInfo(
                        instance_id=iid,
                        play_id=data.get("play_id", "?"),
                        symbol=data.get("symbol", "?"),
                        mode=InstanceMode(data.get("mode", "demo")),
                        started_at=datetime.fromisoformat(data["started_at"]),
                        status=data.get("status", "unknown"),
                        bars_processed=data.get("stats", {}).get("bars_processed", 0) if "stats" in data else 0,
                        signals_generated=data.get("stats", {}).get("signals_generated", 0) if "stats" in data else 0,
                    ))
                except Exception as e:
                    logger.warning(f"Failed to read instance file {path.name}: {e}")
                    continue
        except Exception as e:
            logger.warning(f"Failed to list instance files: {e}")

        return result

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        """Check if a process with given PID is alive. Cross-platform."""
        if pid <= 0:
            return False
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        else:
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False
