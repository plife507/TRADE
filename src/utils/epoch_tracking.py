"""
Epoch and Experiment Tracking for Strategy Lifecycle.

Provides tracking for strategy lifecycle epochs and multi-strategy/timeframe experiments,
all focused on a **single symbol** per experiment.

Epochs = Lifecycle stages (IDEA, CREATION, BACKTEST, DEMO, LIVE)
Experiments = Combinations of strategies/timeframes on the SAME symbol

This module:
- Emits structured events via TradingLogger.event()
- Writes run artifacts under backtests/<timestamp>/<run_id>/
- Integrates with log_context for correlation

Usage:
    from src.utils.epoch_tracking import (
        StrategyEpoch,
        ExperimentType,
        StrategyEpochTracker,
        ExperimentTracker,
        make_timeframe_mix_experiment,
        make_multi_strategy_experiment,
        run_epoch,
    )
    
    # Track a single strategy through epochs
    tracker = StrategyEpochTracker("momentum-v1", "Momentum Strategy")
    run_id = tracker.epoch_start(StrategyEpoch.BACKTEST, "BTCUSDT", ["1h"])
    # ... run backtest ...
    tracker.epoch_complete(run_id, StrategyEpoch.BACKTEST, "BTCUSDT", metrics={...})
    
    # Run an experiment with multiple timeframes
    experiment = ExperimentTracker(
        symbol="BTCUSDT",
        experiment_id="momentum-mtf-test",
        experiment_type=ExperimentType.TIMEFRAME_MIX,
        strategies=[{"strategy_id": "momentum-v1", "timeframes": ["1h", "4h"]}],
    )
    exp_run_id = experiment.start()
    # ... run backtest for each timeframe ...
    experiment.complete(results={...}, overall_metrics={...})
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field, asdict

from .logger import get_logger
from .log_context import (
    new_run_context,
    log_context_scope,
    get_log_context,
    get_run_id,
)


# =============================================================================
# Enums
# =============================================================================

class StrategyEpoch(Enum):
    """Lifecycle epochs for a strategy."""
    IDEA = "idea"
    CREATION = "creation"
    BACKTEST = "backtest"
    DEMO = "demo"
    LIVE = "live"
    ARCHIVED = "archived"


class ExperimentType(Enum):
    """Types of experiments (all on same symbol)."""
    SINGLE_STRATEGY = "single_strategy"  # One strategy, one timeframe
    TIMEFRAME_MIX = "timeframe_mix"  # Same strategy, multiple timeframes
    MULTI_STRATEGY = "multi_strategy"  # Multiple strategies, same symbol
    STRATEGY_TIMEFRAME_COMBO = "strategy_timeframe_combo"  # Multiple strategies, multiple timeframes each
    PARAMETER_SWEEP = "parameter_sweep"  # Same strategy, different parameters


# =============================================================================
# Artifact Writer
# =============================================================================

class ArtifactWriter:
    """
    Writes experiment/epoch artifacts to disk.
    
    Directory structure for backtests (system-first layout):
        data/backtests/{system_id}/{symbol}/{tf}/{window_name}/{run_id}/
            result.json      - BacktestResult serialized
            trades.csv       - Trade list
            equity.csv       - Equity curve
    
    Legacy directory structure (for epoch tracking):
        backtests/<YYYYMMDD_HHMMSS>/<run_id>/
            config.json      - Experiment/epoch configuration
            results.json     - Full results
            summary.json     - High-level summary
            trades.jsonl     - (optional) Per-trade log
    """
    
    def __init__(self, base_dir: str = "backtests"):
        self.base_dir = Path(base_dir)
    
    def get_run_dir(self, run_id: str, timestamp: datetime | None = None) -> Path:
        """Get or create the directory for a run (legacy layout)."""
        ts = timestamp or datetime.now()
        ts_str = ts.strftime("%Y%m%d_%H%M%S")
        run_dir = self.base_dir / ts_str / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir
    
    def get_backtest_run_dir(
        self,
        system_id: str,
        symbol: str,
        tf: str,
        window_name: str,
        run_id: str,
    ) -> Path:
        """
        Get or create directory for a backtest run (system-first layout).
        
        Structure: data/backtests/{system_id}/{symbol}/{tf}/{window_name}/{run_id}/
        
        Args:
            system_id: System identifier
            symbol: Trading symbol (e.g., "SOLUSDT")
            tf: Timeframe (e.g., "5m")
            window_name: Window name (e.g., "hygiene", "test")
            run_id: Run identifier
            
        Returns:
            Path to the run directory (created if not exists)
        """
        run_dir = Path("data") / "backtests" / system_id / symbol / tf / window_name / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir
    
    def write_config(self, run_id: str, config: dict[str, Any], timestamp: datetime | None = None) -> Path:
        """Write configuration to config.json."""
        run_dir = self.get_run_dir(run_id, timestamp)
        config_path = run_dir / "config.json"
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, default=str)
        
        return config_path
    
    def write_results(self, run_id: str, results: dict[str, Any], timestamp: datetime | None = None) -> Path:
        """Write full results to results.json."""
        run_dir = self.get_run_dir(run_id, timestamp)
        results_path = run_dir / "results.json"
        
        with open(results_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, default=str)
        
        return results_path
    
    def write_summary(self, run_id: str, summary: dict[str, Any], timestamp: datetime | None = None) -> Path:
        """Write high-level summary to summary.json."""
        run_dir = self.get_run_dir(run_id, timestamp)
        summary_path = run_dir / "summary.json"
        
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, default=str)
        
        return summary_path
    
    def append_trade(self, run_id: str, trade: dict[str, Any], timestamp: datetime | None = None) -> None:
        """Append a trade record to trades.jsonl."""
        run_dir = self.get_run_dir(run_id, timestamp)
        trades_path = run_dir / "trades.jsonl"
        
        with open(trades_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(trade, default=str) + "\n")


# Global artifact writer
_artifact_writer: ArtifactWriter | None = None


def get_artifact_writer() -> ArtifactWriter:
    """Get the global artifact writer."""
    global _artifact_writer
    if _artifact_writer is None:
        _artifact_writer = ArtifactWriter()
    return _artifact_writer


# =============================================================================
# Strategy Epoch Tracker
# =============================================================================

class StrategyEpochTracker:
    """
    Tracks a strategy through lifecycle epochs.
    
    A strategy can have multiple epochs of the same type (e.g., multiple backtests).
    Each epoch is a separate run with its own run_id.
    """
    
    def __init__(self, strategy_id: str, strategy_name: str):
        """
        Initialize epoch tracker for a strategy.
        
        Args:
            strategy_id: Unique identifier (e.g., "momentum-breakout-v1")
            strategy_name: Human-readable name
        """
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name
        self.logger = get_logger()
        self._artifact_writer = get_artifact_writer()
        self._active_epochs: dict[str, dict] = {}  # run_id -> epoch info
    
    def epoch_start(
        self,
        epoch: StrategyEpoch,
        symbol: str,
        tfs: list[str] | None = None,
        timeframes: list[str] | None = None,
        experiment_id: str | None = None,
        metadata: dict | None = None,
        write_artifacts: bool = True,
    ) -> str:
        """
        Start a new epoch for this strategy.
        
        Args:
            epoch: The lifecycle epoch (IDEA, CREATION, BACKTEST, etc.)
            symbol: Symbol this epoch runs on
            tfs: Timeframes being tested
            experiment_id: Optional parent experiment this epoch is part of
            metadata: Epoch-specific metadata
            write_artifacts: Whether to write config artifact
        
        Returns:
            run_id: Run ID for this epoch (use for epoch_complete)
        """
        # Backward/ergonomic alias:
        # - canonical arg name in codebase is `tfs`
        # - many callers intuitively use `timeframes`
        if (tfs is None) and (timeframes is not None):
            tfs = timeframes

        agent_id = f"{epoch.value}-{self.strategy_id}"
        timestamp = datetime.now(timezone.utc)
        
        with new_run_context(agent_id=agent_id) as ctx:
            epoch_info = {
                "epoch": epoch.value,
                "symbol": symbol,
                "tfs": tfs or [],
                "experiment_id": experiment_id,
                "started_at": timestamp.isoformat(),
                "metadata": metadata or {},
            }
            
            # Store active epoch
            self._active_epochs[ctx.run_id] = epoch_info
            
            # Emit event
            self.logger.event(
                "strategy.epoch.start",
                component="epoch_tracker",
                strategy_id=self.strategy_id,
                strategy_name=self.strategy_name,
                epoch=epoch.value,
                symbol=symbol,
                tfs=tfs or [],
                experiment_id=experiment_id,
                metadata=metadata or {},
            )
            
            # Write config artifact
            if write_artifacts:
                config = {
                    "run_id": ctx.run_id,
                    "strategy_id": self.strategy_id,
                    "strategy_name": self.strategy_name,
                    "epoch": epoch.value,
                    "symbol": symbol,
                    "tfs": tfs or [],
                    "experiment_id": experiment_id,
                    "started_at": timestamp.isoformat(),
                    "metadata": metadata or {},
                }
                self._artifact_writer.write_config(ctx.run_id, config, timestamp)
            
            return ctx.run_id
    
    def epoch_complete(
        self,
        run_id: str,
        epoch: StrategyEpoch,
        symbol: str,
        metrics: dict | None = None,
        passed: bool | None = None,
        next_epoch: StrategyEpoch | None = None,
        promotion_reason: str | None = None,
        write_artifacts: bool = True,
    ) -> None:
        """
        Complete an epoch, optionally promoting to next epoch.
        
        Args:
            run_id: Run ID from epoch_start
            epoch: The epoch being completed
            symbol: Symbol the epoch ran on
            metrics: Performance metrics
            passed: Whether epoch passed promotion criteria
            next_epoch: Next epoch if promoted
            promotion_reason: Why it passed/failed
            write_artifacts: Whether to write result artifacts
        """
        timestamp = datetime.now(timezone.utc)
        
        # Get epoch info if available
        epoch_info = self._active_epochs.pop(run_id, {})
        started_at = epoch_info.get("started_at")
        
        with log_context_scope(run_id=run_id):
            self.logger.event(
                "strategy.epoch.complete",
                component="epoch_tracker",
                strategy_id=self.strategy_id,
                epoch=epoch.value,
                symbol=symbol,
                metrics=metrics or {},
                passed=passed,
                promotion_reason=promotion_reason,
            )
            
            if passed and next_epoch:
                self.logger.event(
                    "strategy.epoch.promotion",
                    component="epoch_tracker",
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    from_epoch=epoch.value,
                    to_epoch=next_epoch.value,
                    reason=promotion_reason,
                )
        
        # Write result artifacts
        if write_artifacts:
            # Calculate duration if we have start time
            duration_seconds = None
            if started_at:
                try:
                    start_dt = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                    duration_seconds = (timestamp - start_dt).total_seconds()
                except (ValueError, TypeError):
                    pass
            
            results = {
                "run_id": run_id,
                "strategy_id": self.strategy_id,
                "epoch": epoch.value,
                "symbol": symbol,
                "metrics": metrics or {},
                "passed": passed,
                "next_epoch": next_epoch.value if next_epoch else None,
                "promotion_reason": promotion_reason,
                "completed_at": timestamp.isoformat(),
                "duration_seconds": duration_seconds,
            }
            
            # Parse timestamp from started_at for consistent directory
            start_timestamp = None
            if started_at:
                try:
                    start_timestamp = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    start_timestamp = timestamp
            else:
                start_timestamp = timestamp
            
            self._artifact_writer.write_results(run_id, results, start_timestamp)
            
            # Write summary
            summary = {
                "run_id": run_id,
                "strategy_id": self.strategy_id,
                "strategy_name": self.strategy_name,
                "epoch": epoch.value,
                "symbol": symbol,
                "passed": passed,
                "total_pnl": metrics.get("total_pnl") if metrics else None,
                "win_rate": metrics.get("win_rate") if metrics else None,
                "duration_seconds": duration_seconds,
            }
            self._artifact_writer.write_summary(run_id, summary, start_timestamp)
    
    def log_trade(
        self,
        run_id: str,
        symbol: str,
        side: str,
        size_usdt: float,
        price: float,
        pnl: float | None = None,
        order_id: str | None = None,
        **extra,
    ) -> None:
        """
        Log a trade during an epoch.
        
        Args:
            run_id: Run ID for the epoch
            symbol: Symbol traded
            side: BUY or SELL
            size_usdt: Position size in USDT
            price: Execution price
            pnl: Realized PnL (optional)
            order_id: Order ID (optional)
            **extra: Additional trade fields
        """
        epoch_info = self._active_epochs.get(run_id, {})
        epoch = epoch_info.get("epoch", "unknown")
        
        with log_context_scope(run_id=run_id):
            self.logger.event(
                f"strategy.{epoch}.trade",
                component="epoch_tracker",
                strategy_id=self.strategy_id,
                symbol=symbol,
                side=side,
                size_usdt=size_usdt,
                price=price,
                pnl=pnl,
                order_id=order_id,
                **extra,
            )
        
        # Append to trades.jsonl
        trade = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "strategy_id": self.strategy_id,
            "epoch": epoch,
            "symbol": symbol,
            "side": side,
            "size_usdt": size_usdt,
            "price": price,
            "pnl": pnl,
            "order_id": order_id,
            **extra,
        }
        
        # Find start timestamp for directory
        started_at = epoch_info.get("started_at")
        start_timestamp = None
        if started_at:
            try:
                start_timestamp = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                pass
        
        self._artifact_writer.append_trade(run_id, trade, start_timestamp)


# =============================================================================
# Experiment Tracker
# =============================================================================

@dataclass
class StrategyConfig:
    """Configuration for a strategy within an experiment."""
    strategy_id: str
    timeframes: list[str]
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExperimentTracker:
    """
    Tracks experiments combining strategies/timeframes on the SAME symbol.
    
    An experiment can contain:
    - Same strategy on multiple timeframes
    - Multiple strategies (each with their timeframes)
    - Parameter variations of the same strategy
    """
    
    def __init__(
        self,
        symbol: str,
        experiment_id: str,
        experiment_name: str | None = None,
        experiment_type: ExperimentType = ExperimentType.SINGLE_STRATEGY,
        strategies: list[dict] | None = None,
        metadata: dict | None = None,
    ):
        """
        Initialize experiment tracker.
        
        Args:
            symbol: Symbol for ALL strategies in this experiment
            experiment_id: Unique experiment identifier
            experiment_name: Human-readable name
            experiment_type: Type of experiment
            strategies: List of strategy configs: [{"strategy_id": ..., "timeframes": [...]}]
            metadata: Additional metadata
        """
        self.symbol = symbol
        self.experiment_id = experiment_id
        self.experiment_name = experiment_name or experiment_id
        self.experiment_type = experiment_type
        self.strategies = strategies or []
        self.metadata = metadata or {}
        self.logger = get_logger()
        self._artifact_writer = get_artifact_writer()
        
        # Tracking state
        self._run_id: str | None = None
        self._started_at: datetime | None = None
        self._ctx = None
    
    def start(self) -> str:
        """
        Start the experiment.
        
        Returns:
            run_id: Run ID for this experiment
        """
        self._started_at = datetime.now(timezone.utc)
        
        # Enter run context
        self._ctx = new_run_context(agent_id=f"experiment-{self.experiment_id}")
        ctx = self._ctx.__enter__()
        self._run_id = ctx.run_id
        
        # Emit event
        self.logger.event(
            "experiment.start",
            component="experiment_tracker",
            experiment_id=self.experiment_id,
            experiment_name=self.experiment_name,
            experiment_type=self.experiment_type.value,
            symbol=self.symbol,
            strategies=self.strategies,
            metadata=self.metadata,
        )
        
        # Write config artifact
        config = {
            "run_id": self._run_id,
            "experiment_id": self.experiment_id,
            "experiment_name": self.experiment_name,
            "experiment_type": self.experiment_type.value,
            "symbol": self.symbol,
            "strategies": self.strategies,
            "metadata": self.metadata,
            "started_at": self._started_at.isoformat(),
        }
        self._artifact_writer.write_config(self._run_id, config, self._started_at)
        
        return self._run_id
    
    def complete(
        self,
        results: dict[str, Any],
        overall_metrics: dict[str, Any] | None = None,
    ) -> None:
        """
        Complete the experiment with results.
        
        Args:
            results: Per-strategy/timeframe results
            overall_metrics: Aggregated metrics for the experiment
        """
        if not self._run_id:
            raise RuntimeError("Experiment not started. Call start() first.")
        
        completed_at = datetime.now(timezone.utc)
        duration_seconds = None
        if self._started_at:
            duration_seconds = (completed_at - self._started_at).total_seconds()
        
        # Emit event
        self.logger.event(
            "experiment.complete",
            component="experiment_tracker",
            experiment_id=self.experiment_id,
            experiment_type=self.experiment_type.value,
            symbol=self.symbol,
            results=results,
            overall_metrics=overall_metrics or {},
        )
        
        # Write result artifacts
        full_results = {
            "run_id": self._run_id,
            "experiment_id": self.experiment_id,
            "experiment_type": self.experiment_type.value,
            "symbol": self.symbol,
            "results": results,
            "overall_metrics": overall_metrics or {},
            "completed_at": completed_at.isoformat(),
            "duration_seconds": duration_seconds,
        }
        self._artifact_writer.write_results(self._run_id, full_results, self._started_at)
        
        # Write summary
        summary = {
            "run_id": self._run_id,
            "experiment_id": self.experiment_id,
            "experiment_name": self.experiment_name,
            "experiment_type": self.experiment_type.value,
            "symbol": self.symbol,
            "strategy_count": len(self.strategies),
            "overall_metrics": overall_metrics or {},
            "duration_seconds": duration_seconds,
        }
        self._artifact_writer.write_summary(self._run_id, summary, self._started_at)
        
        # Exit context
        if self._ctx:
            self._ctx.__exit__(None, None, None)
            self._ctx = None
    
    def get_run_id(self) -> str | None:
        """Get the current run ID."""
        return self._run_id
    
    def create_epoch_tracker(self, strategy_id: str, strategy_name: str | None = None) -> StrategyEpochTracker:
        """
        Create an epoch tracker linked to this experiment.
        
        The tracker will use this experiment's run context for correlation.
        """
        return StrategyEpochTracker(
            strategy_id=strategy_id,
            strategy_name=strategy_name or strategy_id,
        )


# =============================================================================
# Same-Symbol Experiment Helpers
# =============================================================================

def make_timeframe_mix_experiment(
    symbol: str,
    strategy_id: str,
    timeframes: list[str],
    experiment_id: str | None = None,
    metadata: dict | None = None,
) -> ExperimentTracker:
    """
    Create an experiment testing one strategy on multiple timeframes.
    
    Args:
        symbol: Symbol to test on (e.g., "BTCUSDT")
        strategy_id: Strategy identifier
        timeframes: List of timeframes to test (e.g., ["1h", "4h", "1d"])
        experiment_id: Optional experiment ID (generated if not provided)
        metadata: Additional metadata
    
    Returns:
        ExperimentTracker configured for timeframe mix
    
    Example:
        experiment = make_timeframe_mix_experiment(
            symbol="BTCUSDT",
            strategy_id="momentum-v1",
            timeframes=["1h", "4h", "1d"],
        )
        exp_run_id = experiment.start()
    """
    exp_id = experiment_id or f"{strategy_id}-mtf-{symbol.lower()}"
    
    strategies = [
        {"strategy_id": strategy_id, "timeframes": [tf]}
        for tf in timeframes
    ]
    
    return ExperimentTracker(
        symbol=symbol,
        experiment_id=exp_id,
        experiment_name=f"{strategy_id} Multi-Timeframe on {symbol}",
        experiment_type=ExperimentType.TIMEFRAME_MIX,
        strategies=strategies,
        metadata=metadata or {"purpose": "Find optimal timeframe"},
    )


def make_multi_strategy_experiment(
    symbol: str,
    strategy_timeframes: list[dict[str, Any]],
    experiment_id: str | None = None,
    metadata: dict | None = None,
) -> ExperimentTracker:
    """
    Create an experiment testing multiple strategies on the same symbol.
    
    Args:
        symbol: Symbol to test on (e.g., "BTCUSDT")
        strategy_timeframes: List of {"strategy_id": ..., "timeframes": [...], "parameters": {...}}
        experiment_id: Optional experiment ID (generated if not provided)
        metadata: Additional metadata
    
    Returns:
        ExperimentTracker configured for multi-strategy
    
    Example:
        experiment = make_multi_strategy_experiment(
            symbol="BTCUSDT",
            strategy_timeframes=[
                {"strategy_id": "momentum-v1", "timeframes": ["1h"]},
                {"strategy_id": "mean-reversion-v1", "timeframes": ["15m"]},
            ],
        )
        exp_run_id = experiment.start()
    """
    strategy_ids = [s["strategy_id"] for s in strategy_timeframes]
    exp_id = experiment_id or f"multi-strategy-{symbol.lower()}"
    
    return ExperimentTracker(
        symbol=symbol,
        experiment_id=exp_id,
        experiment_name=f"Multi-Strategy on {symbol}",
        experiment_type=ExperimentType.MULTI_STRATEGY,
        strategies=strategy_timeframes,
        metadata=metadata or {"purpose": "Test strategy combination", "strategies": strategy_ids},
    )


def make_parameter_sweep_experiment(
    symbol: str,
    strategy_id: str,
    timeframes: list[str],
    parameter_sets: list[dict[str, Any]],
    experiment_id: str | None = None,
    metadata: dict | None = None,
) -> ExperimentTracker:
    """
    Create an experiment sweeping parameters for a strategy.
    
    Args:
        symbol: Symbol to test on (e.g., "BTCUSDT")
        strategy_id: Strategy identifier
        timeframes: Timeframes to use for each parameter set
        parameter_sets: List of parameter dictionaries to test
        experiment_id: Optional experiment ID (generated if not provided)
        metadata: Additional metadata
    
    Returns:
        ExperimentTracker configured for parameter sweep
    
    Example:
        experiment = make_parameter_sweep_experiment(
            symbol="BTCUSDT",
            strategy_id="momentum-v1",
            timeframes=["1h"],
            parameter_sets=[
                {"momentum_period": 10, "volume_threshold": 1.2},
                {"momentum_period": 20, "volume_threshold": 1.5},
                {"momentum_period": 30, "volume_threshold": 2.0},
            ],
        )
    """
    exp_id = experiment_id or f"{strategy_id}-params-{symbol.lower()}"
    
    strategies = [
        {"strategy_id": strategy_id, "timeframes": timeframes, "parameters": params}
        for params in parameter_sets
    ]
    
    return ExperimentTracker(
        symbol=symbol,
        experiment_id=exp_id,
        experiment_name=f"{strategy_id} Parameter Sweep on {symbol}",
        experiment_type=ExperimentType.PARAMETER_SWEEP,
        strategies=strategies,
        metadata=metadata or {"purpose": "Optimize parameters", "param_count": len(parameter_sets)},
    )


# =============================================================================
# Epoch Runner Wrapper
# =============================================================================

def run_epoch(
    epoch: StrategyEpoch,
    symbol: str,
    strategy_id: str,
    runner_fn: Callable[..., dict],
    strategy_name: str | None = None,
    timeframes: list[str] | None = None,
    experiment_id: str | None = None,
    metadata: dict | None = None,
    promotion_criteria: Callable[[dict], bool] | None = None,
    next_epoch: StrategyEpoch | None = None,
    **runner_kwargs,
) -> dict[str, Any]:
    """
    Wrapper to run an epoch with full tracking.
    
    This is the recommended way to run backtest/demo/live epochs.
    It handles:
    - Context setup
    - Event emission
    - Artifact writing
    - Optional promotion to next epoch
    
    Args:
        epoch: The epoch to run (BACKTEST, DEMO, LIVE)
        symbol: Symbol to run on
        strategy_id: Strategy identifier
        runner_fn: Function that runs the epoch, returns metrics dict
        strategy_name: Human-readable strategy name
        timeframes: Timeframes being used
        experiment_id: Optional parent experiment ID
        metadata: Additional metadata
        promotion_criteria: Optional function that takes metrics and returns True if passed
        next_epoch: Epoch to promote to if passed
        **runner_kwargs: Passed to runner_fn
    
    Returns:
        Dict with run_id, metrics, passed, and promotion info
    
    Example:
        def my_backtest(symbol, timeframe):
            # ... run backtest logic ...
            return {"total_pnl": 1000, "win_rate": 0.65}
        
        result = run_epoch(
            epoch=StrategyEpoch.BACKTEST,
            symbol="BTCUSDT",
            strategy_id="momentum-v1",
            runner_fn=my_backtest,
            timeframes=["1h"],
            promotion_criteria=lambda m: m.get("win_rate", 0) > 0.6,
            next_epoch=StrategyEpoch.DEMO,
            timeframe="1h",  # passed to runner_fn
        )
        
        print(f"Run ID: {result['run_id']}")
        print(f"Passed: {result['passed']}")
    """
    tracker = StrategyEpochTracker(strategy_id, strategy_name or strategy_id)
    
    # Start epoch
    run_id = tracker.epoch_start(
        epoch=epoch,
        symbol=symbol,
        tfs=timeframes,
        experiment_id=experiment_id,
        metadata=metadata,
    )
    
    try:
        # Run the epoch
        with log_context_scope(run_id=run_id):
            metrics = runner_fn(symbol=symbol, **runner_kwargs)
        
        # Check promotion criteria
        passed = None
        promotion_reason = None
        
        if promotion_criteria is not None:
            passed = promotion_criteria(metrics)
            promotion_reason = "Passed promotion criteria" if passed else "Failed promotion criteria"
        
        # Complete epoch
        tracker.epoch_complete(
            run_id=run_id,
            epoch=epoch,
            symbol=symbol,
            metrics=metrics,
            passed=passed,
            next_epoch=next_epoch if passed else None,
            promotion_reason=promotion_reason,
        )
        
        return {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "epoch": epoch.value,
            "symbol": symbol,
            "metrics": metrics,
            "passed": passed,
            "promotion_reason": promotion_reason,
            "next_epoch": next_epoch.value if (passed and next_epoch) else None,
        }
        
    except Exception as e:
        # Log error and complete epoch as failed
        logger = get_logger()
        logger.event(
            "strategy.epoch.error",
            level="ERROR",
            component="epoch_tracker",
            strategy_id=strategy_id,
            epoch=epoch.value,
            symbol=symbol,
            error=str(e),
            error_type=type(e).__name__,
        )
        
        tracker.epoch_complete(
            run_id=run_id,
            epoch=epoch,
            symbol=symbol,
            metrics={"error": str(e)},
            passed=False,
            promotion_reason=f"Error: {e}",
        )
        
        raise

