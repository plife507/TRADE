"""
Multi-Instance Engine Manager.

Enables concurrent engine instances for live, demo, and backtest modes.
Enforces instance limits and provides state isolation.

Cross-process safety:
- Advisory file lock (data/runtime/instances/.lock) serializes check+write
- Atomic file writes (tempfile + os.replace) prevent partial JSON reads
- 15s cooldown after stop prevents restart during cleanup

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
import tempfile
import time
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Literal

# Cross-platform file locking
if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

from .play_engine import PlayEngine
from .runners.live_runner import LiveRunner
from ..utils.datetime_utils import utc_now
from ..utils.logger import get_module_logger

if TYPE_CHECKING:
    from ..backtest.play import Play

logger = get_module_logger(__name__)

_INSTANCE_COOLDOWN_SECONDS = 15.0  # Post-stop cooldown before same slot reopens


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

    def __post_init__(self) -> None:
        assert self.started_at.tzinfo is None, f"InstanceInfo.started_at must be UTC-naive, got tzinfo={self.started_at.tzinfo}"
        if self.last_candle_ts is not None:
            assert self.last_candle_ts.tzinfo is None, f"InstanceInfo.last_candle_ts must be UTC-naive, got tzinfo={self.last_candle_ts.tzinfo}"

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
class _DiskInstance:
    """Typed representation of a parsed instance file from disk."""
    instance_id: str
    symbol: str
    mode: str
    pid: int
    status: str  # "running", "cooldown", "starting"
    cooldown_until: datetime | None
    started_at: datetime
    play_id: str
    path: Path

    def __post_init__(self) -> None:
        if self.cooldown_until is not None:
            assert self.cooldown_until.tzinfo is None, f"_DiskInstance.cooldown_until must be UTC-naive, got tzinfo={self.cooldown_until.tzinfo}"
        assert self.started_at.tzinfo is None, f"_DiskInstance.started_at must be UTC-naive, got tzinfo={self.started_at.tzinfo}"


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

    def __post_init__(self) -> None:
        assert self.started_at.tzinfo is None, f"_EngineInstance.started_at must be UTC-naive, got tzinfo={self.started_at.tzinfo}"


class EngineManager:
    """
    Manages multiple concurrent PlayEngine instances.

    Enforces instance limits:
    - Max 1 live instance (safety - prevents multiple real-money bots)
    - Max 1 demo per symbol (prevents duplicate signals)
    - Max 1 backtest at a time (DuckDB sequential access limitation)

    Cross-process safety:
    - Advisory file lock serializes check+write (prevents two processes
      both passing the limit check simultaneously)
    - 15s cooldown after stop (lets old process cancel orders, close WS,
      release DuckDB locks)
    - Atomic file writes (prevents partial JSON from being visible)
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

        # Cross-process instance tracking (project-relative, not user profile)
        from ..config.constants import INSTANCES_DIR
        self._instances_dir = INSTANCES_DIR
        self._instances_dir.mkdir(parents=True, exist_ok=True)
        self._lock_path = self._instances_dir / ".lock"

        # Clean stale files from previous crashes on startup
        self._read_disk_instances(clean_stale=True)

    @classmethod
    def get_instance(cls) -> "EngineManager":
        """Get singleton instance of EngineManager."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Cross-process file lock
    # ------------------------------------------------------------------

    @contextmanager
    def _instance_lock(self) -> Generator[None]:
        """Cross-process advisory file lock on data/runtime/instances/.lock.

        Uses fcntl.flock(LOCK_EX) on Unix, msvcrt.locking(LK_LOCK) on Windows.
        Held only during the critical section (check limits + write reservation
        file). Auto-releases on fd close or process exit.
        """
        fd = os.open(str(self._lock_path), os.O_CREAT | os.O_RDWR)
        try:
            if sys.platform == "win32":
                deadline = time.monotonic() + 30.0
                while True:
                    try:
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # type: ignore[possibly-undefined]
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Failed to acquire instance lock within 30s")
                        time.sleep(0.1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX)  # type: ignore[possibly-undefined]
            yield
        finally:
            if sys.platform == "win32":
                try:
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)  # type: ignore[possibly-undefined]
                except OSError:
                    pass  # Already unlocked or fd closing will release
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)  # type: ignore[possibly-undefined]
            os.close(fd)

    # ------------------------------------------------------------------
    # Disk instance reader
    # ------------------------------------------------------------------

    def _read_disk_instances(self, *, clean_stale: bool = True) -> list[_DiskInstance]:
        """Read all instance files from disk.

        Centralized disk reader — replaces inline glob+read loops.
        Parses *.json files, validates, and optionally cleans stale entries:
        - Dead PIDs not in cooldown → remove
        - Expired cooldown_until timestamps → remove
        - Invalid JSON (partial writes from old code) → remove

        Returns list of _DiskInstance for active constraints (running,
        cooldown, starting).
        """
        result: list[_DiskInstance] = []
        now = utc_now()

        try:
            paths = list(self._instances_dir.glob("*.json"))
        except Exception as e:
            logger.warning("Failed to list instance files: %s", e)
            return result

        for path in paths:
            try:
                raw = path.read_text(encoding="utf-8")
                data = json.loads(raw)
            except (json.JSONDecodeError, OSError) as e:
                # Invalid JSON (from old partial writes) or read error
                if clean_stale:
                    logger.info("Removing invalid instance file %s: %s", path.name, e)
                    path.unlink(missing_ok=True)
                continue

            iid = data.get("instance_id", "")
            pid = data.get("pid", 0)
            status = data.get("status", "running")
            cooldown_until_str = data.get("cooldown_until")
            cooldown_until: datetime | None = None

            if cooldown_until_str:
                try:
                    cooldown_until = datetime.fromisoformat(cooldown_until_str).replace(tzinfo=None)
                except ValueError:
                    cooldown_until = None

            # Check if this entry is still relevant
            if status == "cooldown":
                if cooldown_until and now >= cooldown_until:
                    # Cooldown expired — clean up
                    if clean_stale:
                        path.unlink(missing_ok=True)
                    continue
                # Cooldown still active — counts as a constraint
            else:
                # Running or starting — check if PID is alive
                if not self._is_pid_alive(pid):
                    if clean_stale:
                        path.unlink(missing_ok=True)
                    continue

            try:
                started_at = datetime.fromisoformat(data.get("started_at", now.isoformat())).replace(tzinfo=None)
            except ValueError:
                started_at = now

            result.append(_DiskInstance(
                instance_id=iid,
                symbol=data.get("symbol", "?"),
                mode=data.get("mode", "demo"),
                pid=pid,
                status=status,
                cooldown_until=cooldown_until,
                started_at=started_at,
                play_id=data.get("play_id", "?"),
                path=path,
            ))

        return result

    # ------------------------------------------------------------------
    # Atomic file writes
    # ------------------------------------------------------------------

    def _write_instance_file(
        self,
        instance_id: str,
        instance: _EngineInstance,
        *,
        status: str = "running",
        cooldown_until: datetime | None = None,
    ) -> None:
        """Write instance state to disk atomically.

        Uses tempfile.mkstemp + os.replace for atomic rename.
        The file is either fully written or not visible at all.
        """
        data: dict = {
            "instance_id": instance_id,
            "pid": os.getpid(),
            "play_id": instance.play.name,
            "symbol": instance.play.symbol_universe[0],
            "mode": instance.mode.value,
            "started_at": instance.started_at.isoformat(),
            "status": status,
        }
        if cooldown_until is not None:
            data["cooldown_until"] = cooldown_until.isoformat()

        target = self._instances_dir / f"{instance_id}.json"
        self._atomic_write_json(target, data)

    def _write_reservation_file(
        self,
        instance_id: str,
        play: "Play",
        mode: str,
    ) -> None:
        """Write a reservation file (status=starting) before engine setup.

        Reserves the slot on disk so other processes see it during
        the check+write critical section.
        """
        data: dict = {
            "instance_id": instance_id,
            "pid": os.getpid(),
            "play_id": play.name,
            "symbol": play.symbol_universe[0],
            "mode": mode,
            "started_at": utc_now().isoformat(),
            "status": "starting",
        }
        target = self._instances_dir / f"{instance_id}.json"
        self._atomic_write_json(target, data)

    def _write_cooldown_file(
        self,
        instance_id: str,
        instance: _EngineInstance,
    ) -> None:
        """Write a cooldown file after instance stops.

        Occupies the slot for _INSTANCE_COOLDOWN_SECONDS, preventing
        immediate restart while the old process cleans up (cancel orders,
        close WebSocket, release DuckDB locks).
        """
        cooldown_until = utc_now() + timedelta(seconds=_INSTANCE_COOLDOWN_SECONDS)
        try:
            data: dict = {
                "instance_id": instance_id,
                "pid": os.getpid(),
                "play_id": instance.play.name,
                "symbol": instance.play.symbol_universe[0],
                "mode": instance.mode.value,
                "started_at": instance.started_at.isoformat(),
                "status": "cooldown",
                "cooldown_until": cooldown_until.isoformat(),
            }
            target = self._instances_dir / f"{instance_id}.json"
            self._atomic_write_json(target, data)
        except Exception as e:
            # If we can't write the cooldown file (filesystem full, etc.),
            # fall back to just removing the instance file
            logger.warning("Failed to write cooldown file for %s: %s", instance_id, e)
            self._remove_instance_file(instance_id)

    def _write_cooldown_file_raw(
        self,
        instance_id: str,
        *,
        play_id: str,
        symbol: str,
        mode: str,
        started_at: str,
    ) -> None:
        """Write a cooldown file from raw data (no _EngineInstance needed).

        Used by stop_cross_process where we only have the disk data.
        """
        cooldown_until = utc_now() + timedelta(seconds=_INSTANCE_COOLDOWN_SECONDS)
        try:
            data: dict = {
                "instance_id": instance_id,
                "pid": 0,  # original process is dead
                "play_id": play_id,
                "symbol": symbol,
                "mode": mode,
                "started_at": started_at,
                "status": "cooldown",
                "cooldown_until": cooldown_until.isoformat(),
            }
            target = self._instances_dir / f"{instance_id}.json"
            self._atomic_write_json(target, data)
        except Exception as e:
            logger.warning("Failed to write cooldown file for %s: %s", instance_id, e)
            self._remove_instance_file(instance_id)

    def _atomic_write_json(self, target: Path, data: dict) -> None:
        """Write JSON to target path atomically via tempfile + os.replace."""
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._instances_dir),
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, str(target))
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _remove_instance_file(self, instance_id: str) -> None:
        """Remove instance file on stop."""
        path = self._instances_dir / f"{instance_id}.json"
        try:
            path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning("Failed to remove instance file %s: %s", path.name, e)

    # ------------------------------------------------------------------
    # Limit checking (cross-process aware)
    # ------------------------------------------------------------------

    def _check_limits(self, play: "Play", mode: str | InstanceMode) -> None:
        """Check if starting a new instance would exceed limits.

        Reads disk instances (running + cooldown + starting) for cross-process
        awareness. Excludes instances already tracked in self._instances to
        avoid double-counting.
        """
        mode = InstanceMode(mode)
        symbol = play.symbol_universe[0]

        # Get all disk instances (running, cooldown, starting)
        disk_instances = self._read_disk_instances(clean_stale=True)

        # Exclude instances we already track in-memory (avoid double-count)
        in_memory_ids = set(self._instances.keys())
        cross_process = [d for d in disk_instances if d.instance_id not in in_memory_ids]

        if mode is InstanceMode.LIVE:
            # Count: in-memory + cross-process live instances
            total_live = self._live_count + sum(
                1 for d in cross_process if d.mode == "live"
            )
            if total_live >= self._max_live:
                running = self._find_running_instance(cross_process, "live")
                if running:
                    raise ValueError(
                        f"Live instance already running (PID {running.pid}). "
                        f"Use 'play stop' first."
                    )
                cooldown_info = self._cooldown_info(cross_process, "live")
                raise ValueError(
                    f"Live instance limit reached ({self._max_live}). "
                    f"Stop existing live instance first.{cooldown_info}"
                )

        elif mode is InstanceMode.DEMO:
            # Count: in-memory + cross-process demo for same symbol
            in_memory_demo = self._demo_by_symbol.get(symbol, 0)
            cross_demo = sum(
                1 for d in cross_process
                if d.mode == "demo" and d.symbol == symbol
            )
            total_demo = in_memory_demo + cross_demo
            if total_demo >= self._max_demo_per_symbol:
                running = self._find_running_instance(cross_process, "demo", symbol)
                if running:
                    raise ValueError(
                        f"Instance already running for {symbol} (PID {running.pid}). "
                        f"Use 'play stop' first."
                    )
                cooldown_info = self._cooldown_info(
                    [d for d in cross_process if d.symbol == symbol],
                    "demo",
                )
                raise ValueError(
                    f"Demo instance limit for {symbol} reached ({self._max_demo_per_symbol}). "
                    f"Stop existing demo instance first.{cooldown_info}"
                )

        elif mode is InstanceMode.BACKTEST:
            total_bt = self._backtest_count + sum(
                1 for d in cross_process if d.mode == "backtest"
            )
            if total_bt >= self._max_backtest:
                running = self._find_running_instance(cross_process, "backtest")
                if running:
                    raise ValueError(
                        f"Backtest already running (PID {running.pid}). "
                        f"DuckDB requires sequential access."
                    )
                cooldown_info = self._cooldown_info(cross_process, "backtest")
                raise ValueError(
                    f"Backtest instance limit reached ({self._max_backtest}). "
                    f"DuckDB requires sequential access. Wait for current backtest to complete.{cooldown_info}"
                )

    def _find_running_instance(
        self,
        cross_process: list[_DiskInstance],
        mode: str,
        symbol: str | None = None,
    ) -> _DiskInstance | None:
        """Find first running cross-process instance matching mode and optional symbol."""
        for d in cross_process:
            if d.mode == mode and d.status == "running" and d.pid > 0:
                if symbol is None or d.symbol == symbol:
                    if self._is_pid_alive(d.pid):
                        return d
        return None

    @staticmethod
    def _cooldown_info(disk_instances: list[_DiskInstance], mode: str) -> str:
        """Build informative cooldown suffix for error messages."""
        for d in disk_instances:
            if d.mode == mode and d.status == "cooldown" and d.cooldown_until:
                remaining = (d.cooldown_until - utc_now()).total_seconds()
                if remaining > 0:
                    return f" (cooldown: {remaining:.0f}s remaining)"
        return ""

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

    # ------------------------------------------------------------------
    # Instance lifecycle
    # ------------------------------------------------------------------

    async def start(
        self,
        play: "Play",
        mode: Literal["live", "demo", "shadow", "backtest"],
        on_signal: "Callable | None" = None,
    ) -> str:
        """
        Start a new engine instance.

        Two-phase slot reservation:
        1. Under cross-process file lock: check limits + write reservation
        2. Outside file lock: create engine, upgrade to "running"
        3. On failure: remove reservation file

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
            # Generate instance ID early (needed for reservation file)
            instance_id = f"{play.name}_{mode}_{uuid.uuid4().hex[:8]}"
            symbol = play.symbol_universe[0]

            # Phase 1: Cross-process check + reservation
            with self._instance_lock():
                self._check_limits(play, mode)
                self._write_reservation_file(instance_id, play, mode)
            # File lock released — slot reserved on disk

            # C7: Validate live mode safety before creating engine
            if mode == "live":
                from .factory import PlayEngineFactory
                try:
                    PlayEngineFactory._validate_live_mode(confirm_live=True)
                except Exception:
                    self._remove_instance_file(instance_id)
                    raise

            logger.info("Starting engine instance: %s", instance_id)

            try:
                if mode == "backtest":
                    self._remove_instance_file(instance_id)
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
                    data_provider=data_provider,  # type: ignore[arg-type]  # LiveDataProvider protocol mismatch (pre-existing)
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
                    started_at=utc_now(),
                )

                self._instances[instance_id] = instance
                self._update_counts(mode, symbol, +1)

                # Start runner in background task
                instance.task = asyncio.create_task(
                    self._run_instance(instance),
                    name=f"engine_{instance_id}",
                )

                # Phase 2: Upgrade reservation to "running"
                self._write_instance_file(instance_id, instance, status="running")

                logger.info("Engine instance started: %s", instance_id)
                return instance_id

            except Exception as e:
                # Rollback in-memory tracking if it was registered
                if instance_id in self._instances:
                    del self._instances[instance_id]
                    self._update_counts(mode, symbol, -1)
                # Release reservation on failure
                self._remove_instance_file(instance_id)
                logger.error("Failed to start engine: %s", e)
                raise RuntimeError(f"Failed to start engine: {e}") from e

    async def stop(self, instance_id: str) -> bool:
        """
        Stop a running engine instance.

        Writes a cooldown file instead of deleting the instance file,
        preventing immediate restart during cleanup.

        Args:
            instance_id: Instance ID to stop

        Returns:
            True if stopped successfully, False if not found
        """
        async with self._lock:
            if instance_id not in self._instances:
                logger.warning("Instance not found: %s", instance_id)
                return False

            instance = self._instances[instance_id]
            logger.info("Stopping engine instance: %s", instance_id)

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

                # Write cooldown file instead of removing
                with self._instance_lock():
                    self._write_cooldown_file(instance_id, instance)

                # Remove from tracking
                del self._instances[instance_id]

                logger.info("Engine instance stopped: %s (cooldown %.0fs)", instance_id, _INSTANCE_COOLDOWN_SECONDS)
                return True

            except Exception as e:
                logger.error("Error stopping instance %s: %s", instance_id, e)
                return False

    def list(self) -> list[InstanceInfo]:
        """
        List all running instances (in-process only).

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

    # ------------------------------------------------------------------
    # Background instance runner
    # ------------------------------------------------------------------

    async def _run_instance(self, instance: _EngineInstance) -> None:
        """Run an instance until stopped."""
        try:
            if instance.runner is not None:
                await instance.runner.start()
                await instance.runner.wait_until_stopped()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Instance %s error: %s", instance.instance_id, e)
            # M9: Clean up crashed instance so it doesn't block new starts
            iid = instance.instance_id
            symbol = instance.play.symbol_universe[0]
            mode = instance.mode.value
            if self._instances.pop(iid, None) is not None:
                self._update_counts(mode, symbol, -1)
                # Write cooldown instead of removing — prevents crash-restart loops
                with self._instance_lock():
                    self._write_cooldown_file(iid, instance)
                logger.info("Cleaned up crashed instance: %s (cooldown %.0fs)", iid, _INSTANCE_COOLDOWN_SECONDS)

    # ------------------------------------------------------------------
    # Stop all / cross-process stop
    # ------------------------------------------------------------------

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

    def stop_cross_process(self, instance_id: str) -> bool:
        """Stop a cross-process instance by sending SIGTERM to its PID.

        Used when `play stop` targets an instance running in a different
        process (e.g. a headless background play).

        Writes a cooldown file after the remote process exits, preventing
        immediate restart.

        Returns True if the signal was sent and instance file cleaned up.
        """
        path = self._instances_dir / f"{instance_id}.json"
        if not path.exists():
            return False

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pid = data.get("pid", 0)
            if pid <= 0:
                return False

            # Capture data for cooldown file before we potentially lose it
            play_id = data.get("play_id", "?")
            symbol = data.get("symbol", "?")
            mode = data.get("mode", "demo")
            started_at = data.get("started_at", utc_now().isoformat())

            if not self._is_pid_alive(pid):
                # Already dead — write cooldown instead of just unlinking
                with self._instance_lock():
                    self._write_cooldown_file_raw(
                        instance_id,
                        play_id=play_id,
                        symbol=symbol,
                        mode=mode,
                        started_at=started_at,
                    )
                return True

            # Send SIGTERM (graceful shutdown)
            self._terminate_pid(pid)

            # Wait briefly for process to exit and clean up its own file
            for _ in range(20):  # 5s max
                time.sleep(0.25)
                if not self._is_pid_alive(pid):
                    break

            # SIGKILL fallback if SIGTERM didn't work
            if self._is_pid_alive(pid):
                logger.warning("PID %s didn't exit after SIGTERM, force-killing", pid)
                self._force_kill_pid(pid)
                # Brief wait for OS cleanup
                for _ in range(8):  # 2s max
                    time.sleep(0.25)
                    if not self._is_pid_alive(pid):
                        break

            # Write cooldown file (replaces instance file)
            with self._instance_lock():
                self._write_cooldown_file_raw(
                    instance_id,
                    play_id=play_id,
                    symbol=symbol,
                    mode=mode,
                    started_at=started_at,
                )

            # Also clean up any pause file
            pause_path = self._instances_dir / f"{instance_id}.pause"
            pause_path.unlink(missing_ok=True)

            return True
        except Exception as e:
            logger.warning("Failed to stop cross-process instance %s: %s", instance_id, e)
            return False

    def get_cross_process_pid(self, instance_id: str) -> int:
        """Get the PID of a cross-process instance, or 0 if not found."""
        path = self._instances_dir / f"{instance_id}.json"
        if not path.exists():
            return 0
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("pid", 0)
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Cross-process instance listing
    # ------------------------------------------------------------------

    def list_all(self) -> list[InstanceInfo]:
        """List all instances including cross-process ones from disk."""
        # Start with in-process instances
        result = self.list()
        known_ids = {info.instance_id for info in result}

        # Read disk instances for cross-process visibility
        disk_instances = self._read_disk_instances(clean_stale=True)

        for d in disk_instances:
            if d.instance_id in known_ids:
                continue  # Already in our process

            # Determine display status
            if d.status == "cooldown":
                if d.cooldown_until:
                    remaining = (d.cooldown_until - utc_now()).total_seconds()
                    display_status = f"cooldown ({remaining:.0f}s)" if remaining > 0 else "cooldown"
                else:
                    display_status = "cooldown"
            elif d.status == "starting":
                display_status = "starting"
            else:
                display_status = "running"

            try:
                inst_mode = InstanceMode(d.mode)
            except ValueError:
                continue

            result.append(InstanceInfo(
                instance_id=d.instance_id,
                play_id=d.play_id,
                symbol=d.symbol,
                mode=inst_mode,
                started_at=d.started_at,
                status=display_status,
            ))

        return result

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        """Check if a process with given PID is alive. Cross-platform."""
        if pid <= 0:
            return False
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return exit_code.value == STILL_ACTIVE
                return True
            finally:
                kernel32.CloseHandle(handle)
        else:
            try:
                os.kill(pid, 0)
                return True
            except PermissionError:
                return True
            except OSError:
                return False

    @staticmethod
    def _terminate_pid(pid: int) -> bool:
        """Send SIGTERM (Unix) or TerminateProcess (Windows) to a process.

        Graceful termination — the process can catch this and clean up.
        On Windows, TerminateProcess is unconditional (no graceful equivalent).

        Returns True if signal was sent successfully, False otherwise.
        """
        if pid <= 0:
            return False
        try:
            if sys.platform == "win32":
                import ctypes
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                PROCESS_TERMINATE = 0x0001
                handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
                if handle:
                    result = kernel32.TerminateProcess(handle, 1)
                    kernel32.CloseHandle(handle)
                    return bool(result)
                return False
            else:
                import signal as _signal
                os.kill(pid, _signal.SIGTERM)
                return True
        except ProcessLookupError:
            return False  # Already dead
        except PermissionError:
            logger.warning("Permission denied sending SIGTERM to PID %s", pid)
            return False
        except OSError as e:
            logger.warning("Failed to terminate PID %s: %s", pid, e)
            return False

    @staticmethod
    def _force_kill_pid(pid: int) -> bool:
        """Send SIGKILL (Unix) or TerminateProcess (Windows) to a process.

        Last-resort kill. On Unix, SIGKILL cannot be caught or ignored.
        On Windows, TerminateProcess is already unconditional (same as _terminate_pid).

        Returns True if signal was sent successfully, False otherwise.
        """
        if pid <= 0:
            return False
        try:
            if sys.platform == "win32":
                import ctypes
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                PROCESS_TERMINATE = 0x0001
                handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
                if handle:
                    result = kernel32.TerminateProcess(handle, 1)
                    kernel32.CloseHandle(handle)
                    return bool(result)
                return False
            else:
                import signal as _signal
                os.kill(pid, _signal.SIGKILL)
                return True
        except ProcessLookupError:
            return False  # Already dead
        except PermissionError:
            logger.warning("Permission denied sending SIGKILL to PID %s", pid)
            return False
        except OSError as e:
            logger.warning("Failed to force-kill PID %s: %s", pid, e)
            return False
