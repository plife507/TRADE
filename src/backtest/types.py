"""
Backtest type definitions.

Provides dataclasses for backtesting:
- Bar: Canonical OHLCV bar with ts_open/ts_close (re-exported from runtime.types)
- Trade: Executed trade record
- EquityPoint: Equity curve point
- AccountCurvePoint: Full margin state per bar
- BacktestResult: Complete backtest output

Stop taxonomy:
- StopReason: Enum for terminal vs non-terminal stop conditions

Currency model (this simulator version):
- All monetary values are in USDT (quote currency)
- All variable names use "_usdt" suffix for USDT denomination
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional

# Re-export canonical Bar from runtime.types
from .runtime.types import Bar


class StopReason(str, Enum):
    """
    Stop reason taxonomy for backtest termination.
    
    Terminal stops (halt immediately):
    - LIQUIDATED: equity <= maintenance margin (Bybit liquidation)
    - EQUITY_FLOOR_HIT: equity <= stop_equity_usdt threshold
    
    Non-terminal stops (continue with restrictions):
    - STRATEGY_STARVED: can't open new trades, but existing position can run
    """
    LIQUIDATED = "liquidated"
    EQUITY_FLOOR_HIT = "equity_floor_hit"
    STRATEGY_STARVED = "strategy_starved"
    
    def is_terminal(self) -> bool:
        """Return True if this stop reason halts the backtest immediately."""
        return self in (StopReason.LIQUIDATED, StopReason.EQUITY_FLOOR_HIT)


@dataclass
class Trade:
    """
    Record of an executed trade.
    
    Includes entry/exit details, PnL, and fees.
    
    Phase 4 additions:
    - entry_bar_index / exit_bar_index: Bar indices for debugging
    - exit_price_source: How exit price was determined (for TP/SL)
    - entry_ready / exit_ready: Snapshot readiness state at entry/exit
    """
    trade_id: str
    symbol: str
    side: str  # "long" or "short"
    
    # Entry details
    entry_time: datetime
    entry_price: float
    entry_size: float  # In base currency units
    entry_size_usdt: float
    
    # Exit details (None if still open)
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # "tp", "sl", "signal", "end_of_data", "liquidation", "force"
    
    # PnL
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    net_pnl: float = 0.0
    
    # Risk levels
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    # Phase 4: Bar indices for debugging and auditing
    entry_bar_index: Optional[int] = None
    exit_bar_index: Optional[int] = None
    
    # Phase 4: Exit price source (e.g., "tp_level", "sl_level", "bar_close", "mark_price")
    exit_price_source: Optional[str] = None
    
    # Phase 4: Snapshot readiness state at entry/exit
    entry_ready: bool = True
    exit_ready: Optional[bool] = None
    
    @property
    def is_closed(self) -> bool:
        return self.exit_time is not None
    
    @property
    def pnl_pct(self) -> float:
        """
        Trade return as percentage of entry notional.
        
        Defined as: net_pnl / abs(entry_size_usdt).
        Returns 0 if entry_size_usdt is 0.
        """
        if self.entry_size_usdt == 0:
            return 0.0
        return (self.net_pnl / abs(self.entry_size_usdt)) * 100.0
    
    @property
    def duration_bars(self) -> Optional[int]:
        """Calculate duration in bars if both indices are set."""
        if self.entry_bar_index is not None and self.exit_bar_index is not None:
            return self.exit_bar_index - self.entry_bar_index
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "entry_time": self.entry_time.isoformat(),
            "entry_price": self.entry_price,
            "entry_size": self.entry_size,
            "entry_size_usdt": self.entry_size_usdt,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "exit_price": self.exit_price,
            "exit_reason": self.exit_reason,
            "realized_pnl": self.realized_pnl,
            "fees_paid": self.fees_paid,
            "net_pnl": self.net_pnl,
            "pnl_pct": self.pnl_pct,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            # Phase 4: Bar indices and debugging fields
            "entry_bar_index": self.entry_bar_index,
            "exit_bar_index": self.exit_bar_index,
            "duration_bars": self.duration_bars,
            "exit_price_source": self.exit_price_source,
            "entry_ready": self.entry_ready,
            "exit_ready": self.exit_ready,
        }


@dataclass
class EquityPoint:
    """Single point on the equity curve."""
    timestamp: datetime
    equity: float
    drawdown: float = 0.0
    drawdown_pct: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "equity": self.equity,
            "drawdown": self.drawdown,
            "drawdown_pct": self.drawdown_pct,
        }


@dataclass
class AccountCurvePoint:
    """
    Full margin state at each bar for proof-grade metrics.
    
    Captures all Bybit-aligned margin values post-process_bar:
    - equity_usdt: cash + unrealized PnL
    - used_margin_usdt: position IM
    - free_margin_usdt: equity - used_margin (can be negative)
    - available_balance_usdt: max(0, free_margin)
    - maintenance_margin_usdt: position value × MMR
    """
    timestamp: datetime
    equity_usdt: float
    used_margin_usdt: float
    free_margin_usdt: float
    available_balance_usdt: float
    maintenance_margin_usdt: float
    has_position: bool = False
    entries_disabled: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "equity_usdt": self.equity_usdt,
            "used_margin_usdt": self.used_margin_usdt,
            "free_margin_usdt": self.free_margin_usdt,
            "available_balance_usdt": self.available_balance_usdt,
            "maintenance_margin_usdt": self.maintenance_margin_usdt,
            "has_position": self.has_position,
            "entries_disabled": self.entries_disabled,
        }


@dataclass
class WindowConfig:
    """Resolved window configuration for a backtest run."""
    window_name: str  # "hygiene" or "test"
    start: datetime
    end: datetime


@dataclass
class BacktestMetrics:
    """
    Structured backtest performance metrics.
    
    All core metrics for evaluating backtest performance.
    Computed by metrics.compute_backtest_metrics().
    """
    # Equity metrics
    initial_equity: float = 0.0
    final_equity: float = 0.0
    net_profit: float = 0.0
    net_return_pct: float = 0.0
    
    # Drawdown metrics
    max_drawdown_abs: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_bars: int = 0
    
    # Trade metrics
    total_trades: int = 0
    win_rate: float = 0.0
    avg_trade_return_pct: float = 0.0
    profit_factor: float = 0.0
    
    # Risk-adjusted metrics
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    
    # Additional trade stats
    win_count: int = 0
    loss_count: int = 0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    total_fees: float = 0.0
    
    # Extended trade analytics
    avg_win_usdt: float = 0.0
    avg_loss_usdt: float = 0.0
    largest_win_usdt: float = 0.0
    largest_loss_usdt: float = 0.0
    avg_trade_duration_bars: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    expectancy_usdt: float = 0.0
    payoff_ratio: float = 0.0
    recovery_factor: float = 0.0
    
    # Long/short breakdown
    long_trades: int = 0
    short_trades: int = 0
    long_win_rate: float = 0.0
    short_win_rate: float = 0.0
    long_pnl: float = 0.0
    short_pnl: float = 0.0
    
    # Time metrics
    total_bars: int = 0
    bars_in_position: int = 0
    time_in_market_pct: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            # Equity
            "initial_equity": self.initial_equity,
            "final_equity": self.final_equity,
            "net_profit": self.net_profit,
            "net_return_pct": self.net_return_pct,
            # Drawdown
            "max_drawdown_abs": self.max_drawdown_abs,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_drawdown_duration_bars": self.max_drawdown_duration_bars,
            # Trade summary
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "avg_trade_return_pct": self.avg_trade_return_pct,
            "profit_factor": self.profit_factor,
            # Risk-adjusted
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "calmar": self.calmar,
            # Trade counts
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "gross_profit": self.gross_profit,
            "gross_loss": self.gross_loss,
            "total_fees": self.total_fees,
            # Extended trade analytics
            "avg_win_usdt": self.avg_win_usdt,
            "avg_loss_usdt": self.avg_loss_usdt,
            "largest_win_usdt": self.largest_win_usdt,
            "largest_loss_usdt": self.largest_loss_usdt,
            "avg_trade_duration_bars": self.avg_trade_duration_bars,
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "expectancy_usdt": self.expectancy_usdt,
            "payoff_ratio": self.payoff_ratio,
            "recovery_factor": self.recovery_factor,
            # Long/short breakdown
            "long_trades": self.long_trades,
            "short_trades": self.short_trades,
            "long_win_rate": self.long_win_rate,
            "short_win_rate": self.short_win_rate,
            "long_pnl": self.long_pnl,
            "short_pnl": self.short_pnl,
            # Time metrics
            "total_bars": self.total_bars,
            "bars_in_position": self.bars_in_position,
            "time_in_market_pct": self.time_in_market_pct,
        }


@dataclass
class StrategyInstanceSummary:
    """Summary of a StrategyInstance for BacktestResult."""
    strategy_instance_id: str
    strategy_id: str
    strategy_version: str
    role: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        result = {
            "strategy_instance_id": self.strategy_instance_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
        }
        if self.role:
            result["role"] = self.role
        return result


@dataclass
class BacktestRunConfigEcho:
    """
    Captured config values used for a specific backtest run.
    
    Provides reproducibility: even if YAML changes later, this snapshot
    records exactly which parameters were used for this run.
    """
    # Margin model
    initial_margin_rate: float
    maintenance_margin_rate: float
    taker_fee_rate: float
    slippage_bps: float
    mark_price_source: str
    
    # Entry gate behavior
    include_est_close_fee_in_entry_gate: bool
    
    # Stop thresholds
    min_trade_usdt: float
    stop_equity_usdt: float
    
    # Leverage (derived)
    max_leverage: float
    
    # Fee mode
    fee_mode: str = "taker_only"
    
    # Optional version tracking
    execution_version: str = "1.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "initial_margin_rate": self.initial_margin_rate,
            "maintenance_margin_rate": self.maintenance_margin_rate,
            "taker_fee_rate": self.taker_fee_rate,
            "slippage_bps": self.slippage_bps,
            "mark_price_source": self.mark_price_source,
            "include_est_close_fee_in_entry_gate": self.include_est_close_fee_in_entry_gate,
            "min_trade_usdt": self.min_trade_usdt,
            "stop_equity_usdt": self.stop_equity_usdt,
            "max_leverage": self.max_leverage,
            "fee_mode": self.fee_mode,
            "execution_version": self.execution_version,
        }


@dataclass
class BacktestResult:
    """
    Complete backtest result with structured contract.
    
    Contains:
    - Run metadata (system, strategies, window, timestamps)
    - Structured metrics (BacktestMetrics)
    - Resolved risk profile fields used for this run
    - Artifact paths (relative to run directory)
    - Trade list and equity curve (in memory; also written to CSV)
    """
    # Run identification
    run_id: str
    system_id: str
    system_uid: str
    
    # Primary strategy info (for quick access)
    primary_strategy_instance_id: str
    strategy_id: str  # Primary strategy's family id
    strategy_version: str  # Primary strategy's version
    
    # Time range (required, no defaults)
    start_ts: datetime
    end_ts: datetime
    started_at: datetime
    finished_at: datetime
    
    # Strategies summary (all instances in the system)
    strategies: List[StrategyInstanceSummary] = field(default_factory=list)
    
    # System-level fields
    symbol: str = ""
    tf: str = ""
    window_name: str = ""
    
    # Context
    risk_mode: str = "none"
    data_env: str = "backtest"
    
    # Structured metrics (legacy + proof-grade)
    metrics: BacktestMetrics = field(default_factory=BacktestMetrics)
    metrics_v2: Optional[Any] = None  # BacktestMetricsV2 (imported at runtime to avoid circular)
    
    # Resolved risk profile fields used for this run
    risk_initial_equity_used: float = 0.0
    risk_per_trade_pct_used: float = 0.0
    risk_max_leverage_used: float = 0.0
    
    # Warm-up and window metadata (for debugging and reproducibility)
    warmup_bars: int = 0
    warmup_multiplier: int = 5
    max_indicator_lookback: int = 0
    data_window_requested_start: str = ""  # ISO string from YAML/preset
    data_window_requested_end: str = ""
    data_window_loaded_start: str = ""     # After warm-up & clamping
    data_window_loaded_end: str = ""
    simulation_start_ts: Optional[datetime] = None  # When simulation actually started
    
    # Artifact paths (relative to run directory)
    trades_path: str = "trades.csv"
    equity_path: str = "equity.csv"
    result_path: str = "result.json"
    
    # In-memory data (not serialized to JSON by default)
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[EquityPoint] = field(default_factory=list)
    
    # Legacy fields for backward compat
    artifact_dir: Optional[str] = None
    
    # Account curve (full margin state per bar)
    account_curve: List[AccountCurvePoint] = field(default_factory=list)
    
    # Run config echo (for reproducibility)
    run_config_echo: Optional[BacktestRunConfigEcho] = None
    
    # Stop classification (proof-grade)
    stop_classification: Optional[StopReason] = None  # None if ended naturally
    stop_reason_detail: Optional[str] = None  # Human-readable stable text
    
    # Early-stop fields (terminal states: account_blown, insufficient_free_margin)
    # Legacy stop_reason kept for backward compat, maps from stop_classification
    stopped_early: bool = False
    stop_reason: Optional[str] = None  # Legacy: "account_blown" | "insufficient_free_margin" | "liquidated"
    stop_ts: Optional[datetime] = None
    stop_bar_index: Optional[int] = None
    stop_details: Optional[Dict[str, Any]] = None  # Full exchange snapshot at stop
    
    # Starvation tracking (non-terminal)
    entries_disabled: bool = False
    first_starved_ts: Optional[datetime] = None
    first_starved_bar_index: Optional[int] = None
    entry_attempts_count: int = 0
    entry_rejections_count: int = 0
    
    # Backward compat property aliases
    @property
    def start_time(self) -> datetime:
        return self.start_ts
    
    @property
    def end_time(self) -> datetime:
        return self.end_ts
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dict for JSON serialization.
        
        Note: trades and equity_curve are NOT included by default
        since they are written to separate CSV files.
        """
        return {
            # Metadata
            "run_id": self.run_id,
            "system_id": self.system_id,
            "system_uid": self.system_uid,
            # Strategy info
            "primary_strategy_instance_id": self.primary_strategy_instance_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "strategies": [s.to_dict() for s in self.strategies],
            # System-level
            "symbol": self.symbol,
            "tf": self.tf,
            "window_name": self.window_name,
            # Timestamps
            "start_ts": self.start_ts.isoformat(),
            "end_ts": self.end_ts.isoformat(),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            # Context
            "risk_mode": self.risk_mode,
            "data_env": self.data_env,
            # Metrics
            "metrics": self.metrics.to_dict(),
            "metrics_v2": self.metrics_v2.to_dict() if self.metrics_v2 else None,
            # Resolved risk
            "risk_initial_equity_used": self.risk_initial_equity_used,
            "risk_per_trade_pct_used": self.risk_per_trade_pct_used,
            "risk_max_leverage_used": self.risk_max_leverage_used,
            # Warm-up and window metadata
            "warmup_bars": self.warmup_bars,
            "warmup_multiplier": self.warmup_multiplier,
            "max_indicator_lookback": self.max_indicator_lookback,
            "data_window_requested_start": self.data_window_requested_start,
            "data_window_requested_end": self.data_window_requested_end,
            "data_window_loaded_start": self.data_window_loaded_start,
            "data_window_loaded_end": self.data_window_loaded_end,
            "simulation_start_ts": self.simulation_start_ts.isoformat() if self.simulation_start_ts else None,
            # Artifact paths
            "trades_path": self.trades_path,
            "equity_path": self.equity_path,
            "result_path": self.result_path,
            # Legacy
            "artifact_dir": self.artifact_dir,
            # Run config echo
            "run_config_echo": self.run_config_echo.to_dict() if self.run_config_echo else None,
            # Stop classification (proof-grade)
            "stop_classification": self.stop_classification.value if self.stop_classification else None,
            "stop_reason_detail": self.stop_reason_detail,
            # Early-stop fields (legacy compat)
            "stopped_early": self.stopped_early,
            "stop_reason": self.stop_reason,
            "stop_ts": self.stop_ts.isoformat() if self.stop_ts else None,
            "stop_bar_index": self.stop_bar_index,
            "stop_details": self.stop_details,
            # Starvation tracking
            "entries_disabled": self.entries_disabled,
            "first_starved_ts": self.first_starved_ts.isoformat() if self.first_starved_ts else None,
            "first_starved_bar_index": self.first_starved_bar_index,
            "entry_attempts_count": self.entry_attempts_count,
            "entry_rejections_count": self.entry_rejections_count,
        }
