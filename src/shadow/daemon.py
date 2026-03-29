"""
ShadowDaemon — always-on process for VPS deployment.

Wraps ShadowOrchestrator with:
- Config file loading (config/shadow.yml)
- State persistence (save on shutdown, restore on startup)
- Signal handling (SIGTERM → graceful shutdown, SIGHUP → reload)
- Async event loop management

Usage:
    python trade_cli.py shadow daemon                    # Default config
    python trade_cli.py shadow daemon --config shadow.yml  # Custom config

State files:
    data/shadow/state/orchestrator.state.json  — which plays to restore
"""

from __future__ import annotations

import asyncio
import json
import signal
from pathlib import Path
from typing import Any

import yaml

from ..backtest.play.play import load_play
from ..config.constants import PROJECT_ROOT
from ..utils.datetime_utils import utc_now
from ..utils.logger import get_module_logger

from .config import ShadowConfig, ShadowPlayConfig
from .orchestrator import ShadowOrchestrator

logger = get_module_logger(__name__)

SHADOW_STATE_DIR = PROJECT_ROOT / "data" / "shadow" / "state"
ORCHESTRATOR_STATE_FILE = SHADOW_STATE_DIR / "orchestrator.state.json"
DEFAULT_SHADOW_CONFIG = PROJECT_ROOT / "config" / "shadow.yml"


class ShadowDaemon:
    """Always-on shadow exchange process.

    Manages the ShadowOrchestrator lifecycle with graceful shutdown
    and state persistence for VPS deployment.
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path or DEFAULT_SHADOW_CONFIG
        self._orchestrator: ShadowOrchestrator | None = None
        self._stop_event = asyncio.Event()
        self._config: ShadowConfig | None = None
        self._play_configs: dict[str, dict[str, Any]] = {}  # play_id -> config overrides

    async def run(self) -> None:
        """Main daemon entry point. Blocks until stopped."""
        logger.info("ShadowDaemon starting...")

        # Load config
        self._config, self._play_configs = self._load_config()
        self._orchestrator = ShadowOrchestrator(self._config)

        # Set up signal handlers
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGTERM, self._handle_shutdown)
        loop.add_signal_handler(signal.SIGINT, self._handle_shutdown)
        try:
            loop.add_signal_handler(signal.SIGHUP, self._handle_reload)
        except (ValueError, OSError):
            pass  # SIGHUP not available on Windows

        # Start orchestrator background tasks
        orch = self._orchestrator
        assert orch is not None
        await orch.start()

        # Restore state from previous run (if any)
        restored = self._restore_state()

        # Add plays from config (skip already-restored ones)
        self._add_plays_from_config(skip_ids=restored)

        logger.info(
            "ShadowDaemon running: %d engines on %s",
            orch.engine_count,
            ", ".join(orch.active_symbols) or "(none)",
        )

        # Block until stop signal
        await self._stop_event.wait()

        # Graceful shutdown
        logger.info("ShadowDaemon shutting down...")
        self._save_state()
        assert self._orchestrator is not None
        await self._orchestrator.stop()
        logger.info("ShadowDaemon stopped")

    # ── Signal Handlers ────────────────────────────────────────

    def _handle_shutdown(self) -> None:
        """SIGTERM/SIGINT → graceful shutdown."""
        logger.info("Shutdown signal received")
        self._stop_event.set()

    def _handle_reload(self) -> None:
        """SIGHUP → reload config, add/remove plays."""
        logger.info("Reload signal received")
        asyncio.get_event_loop().create_task(self._reload_config())

    async def _reload_config(self) -> None:
        """Reload config and diff play list."""
        if self._orchestrator is None:
            return

        _new_config, new_play_configs = self._load_config()
        self._play_configs = new_play_configs

        current_plays = {
            e.play.id for e in self._orchestrator._engines.values()
        }
        desired_plays = set(new_play_configs.keys())

        to_add = desired_plays - current_plays
        to_remove = current_plays - desired_plays

        for play_id in to_remove:
            # Find instance ID for this play
            for iid, engine in list(self._orchestrator._engines.items()):
                if engine.play.id == play_id:
                    self._orchestrator.remove_play(iid)
                    logger.info("Reload: removed %s", play_id)
                    break

        for play_id in to_add:
            self._add_play(play_id)

        logger.info(
            "Reload complete: +%d -%d → %d engines",
            len(to_add), len(to_remove), self._orchestrator.engine_count,
        )

    # ── Config Loading ──────────────────────────────────────────

    def _load_config(self) -> tuple[ShadowConfig, dict[str, dict[str, Any]]]:
        """Load shadow config from YAML file.

        Returns:
            (ShadowConfig, {play_id: {equity: float, ...}})
        """
        if not self._config_path.exists():
            logger.warning("Config not found: %s — using defaults", self._config_path)
            return ShadowConfig(), {}

        with open(self._config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        shadow = raw.get("shadow", {})

        config = ShadowConfig(
            max_engines=shadow.get("max_engines", 50),
            max_engines_per_symbol=shadow.get("max_engines_per_symbol", 10),
            snapshot_interval_seconds=shadow.get("snapshot_interval_minutes", 60) * 60,
            health_check_interval_seconds=shadow.get("health_check_interval_seconds", 60),
            stale_threshold_seconds=shadow.get("stale_threshold_seconds", 300),
            auto_restart_on_stale=shadow.get("auto_restart_on_stale", True),
            max_restart_attempts=shadow.get("max_restart_attempts", 3),
            db_flush_interval_seconds=shadow.get("db_flush_interval_seconds", 60),
            default_play_config=ShadowPlayConfig(
                initial_equity_usdt=shadow.get("default_equity_usdt", 10000.0),
                max_drawdown_pct=shadow.get("default_max_drawdown_pct", 25.0),
                auto_stop_on_drawdown=shadow.get("auto_stop_on_drawdown", False),
            ),
        )

        # Parse play list
        plays = raw.get("plays", [])
        play_configs: dict[str, dict[str, Any]] = {}
        for entry in plays:
            if isinstance(entry, str):
                play_configs[entry] = {}
            elif isinstance(entry, dict):
                play_id = entry.get("id") or entry.get("play")
                if play_id:
                    play_configs[play_id] = {
                        k: v for k, v in entry.items() if k not in ("id", "play")
                    }

        return config, play_configs

    # ── Play Management ────────────────────────────────────────

    def _add_plays_from_config(self, skip_ids: set[str] | None = None) -> None:
        """Add all plays from config to the orchestrator."""
        skip = skip_ids or set()

        for play_id, overrides in self._play_configs.items():
            if play_id in skip:
                continue
            self._add_play(play_id, overrides)

    def _add_play(self, play_id: str, overrides: dict[str, Any] | None = None) -> None:
        """Load and add a single play."""
        if self._orchestrator is None:
            return

        overrides = overrides or self._play_configs.get(play_id, {})

        try:
            play = load_play(play_id)
        except Exception as e:
            logger.error("Failed to load play '%s': %s", play_id, e)
            return

        # Build play-specific config from overrides
        default = self._config.default_play_config if self._config else ShadowPlayConfig()
        play_config = ShadowPlayConfig(
            initial_equity_usdt=overrides.get("equity_usdt", default.initial_equity_usdt),
            max_drawdown_pct=overrides.get("max_drawdown_pct", default.max_drawdown_pct),
            auto_stop_on_drawdown=overrides.get("auto_stop_on_drawdown", default.auto_stop_on_drawdown),
        )

        try:
            iid = self._orchestrator.add_play(play, play_config=play_config)
            logger.info("Added play %s as %s", play_id, iid)
        except ValueError as e:
            logger.error("Failed to add play '%s': %s", play_id, e)

    # ── State Persistence ──────────────────────────────────────

    def _save_state(self) -> None:
        """Save orchestrator state for restart resume.

        Saves which plays are running and their instance IDs so the
        daemon can restore them on next startup.
        """
        if self._orchestrator is None:
            return

        SHADOW_STATE_DIR.mkdir(parents=True, exist_ok=True)

        state: dict[str, Any] = {
            "saved_at": utc_now().isoformat(),
            "instances": {},
        }

        for iid, engine in self._orchestrator._engines.items():
            state["instances"][iid] = {
                "play_id": engine.play.id,
                "started_at": engine.stats.started_at.isoformat() if engine.stats.started_at else None,
                "equity_usdt": engine.equity,
                "bars_processed": engine.stats.bars_processed,
                "trades_closed": engine.stats.trades_closed,
            }

        # Atomic write
        tmp_path = ORCHESTRATOR_STATE_FILE.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(state, indent=2), encoding="utf-8", newline="\n")
        tmp_path.replace(ORCHESTRATOR_STATE_FILE)

        logger.info("State saved: %d instances", len(state["instances"]))

    def _restore_state(self) -> set[str]:
        """Restore engines from saved state. Returns set of restored play_ids."""
        if not ORCHESTRATOR_STATE_FILE.exists():
            return set()

        if self._orchestrator is None:
            return set()

        try:
            raw = json.loads(ORCHESTRATOR_STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read state file: %s", e)
            return set()

        restored: set[str] = set()
        instances = raw.get("instances", {})

        for iid, inst_state in instances.items():
            play_id = inst_state.get("play_id")
            if not play_id:
                continue

            overrides = self._play_configs.get(play_id, {})
            try:
                play = load_play(play_id)
            except Exception as e:
                logger.warning("Failed to restore play '%s': %s", play_id, e)
                continue

            default = self._config.default_play_config if self._config else ShadowPlayConfig()
            play_config = ShadowPlayConfig(
                initial_equity_usdt=overrides.get("equity_usdt", default.initial_equity_usdt),
                max_drawdown_pct=overrides.get("max_drawdown_pct", default.max_drawdown_pct),
                auto_stop_on_drawdown=overrides.get("auto_stop_on_drawdown", default.auto_stop_on_drawdown),
            )

            try:
                self._orchestrator.add_play(play, play_config=play_config, instance_id=iid)
                restored.add(play_id)
                logger.info("Restored play %s as %s", play_id, iid)
            except Exception as e:
                logger.warning("Failed to restore play '%s': %s", play_id, e)

        # Clean up state file after restore
        try:
            ORCHESTRATOR_STATE_FILE.unlink()
        except OSError:
            pass

        return restored
