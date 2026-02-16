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
from typing import Any

# Re-export canonical Bar from runtime.types
from .runtime.types import Bar


class StopReason(str, Enum):
    """
    Stop reason taxonomy for backtest termination.

    Terminal stops (halt immediately):
    - LIQUIDATED: equity <= maintenance margin (Bybit liquidation)
    - EQUITY_FLOOR_HIT: equity <= stop_equity_usdt threshold
    - MAX_DRAWDOWN_HIT: drawdown from peak exceeds max_drawdown_pct

    Non-terminal stops (continue with restrictions):
    - STRATEGY_STARVED: can't open new trades, but existing position can run
    """
    LIQUIDATED = "liquidated"
    EQUITY_FLOOR_HIT = "equity_floor_hit"
    MAX_DRAWDOWN_HIT = "max_drawdown_hit"
    STRATEGY_STARVED = "strategy_starved"

    def is_terminal(self) -> bool:
        """Return True if this stop reason halts the backtest immediately."""
        return self in (
            StopReason.LIQUIDATED,
            StopReason.EQUITY_FLOOR_HIT,
            StopReason.MAX_DRAWDOWN_HIT,
        )


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
    exit_time: datetime | None = None
    exit_price: float | None = None
    exit_reason: str | None = None  # "tp", "sl", "signal", "end_of_data", "liquidation", "force"
    
    # PnL
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    net_pnl: float = 0.0
    
    # Risk levels
    stop_loss: float | None = None
    take_profit: float | None = None

    # Phase 4: Bar indices for debugging and auditing
    entry_bar_index: int | None = None
    exit_bar_index: int | None = None

    # Phase 4: Exit price source (e.g., "tp_level", "sl_level", "bar_close", "mark_price")
    exit_price_source: str | None = None

    # Phase 4: Snapshot readiness state at entry/exit
    entry_ready: bool = True
    exit_ready: bool | None = None

    # MAE/MFE: Maximum Adverse/Favorable Excursion during trade
    mae_pct: float = 0.0  # Max adverse move as % of entry price
    mfe_pct: float = 0.0  # Max favorable move as % of entry price

    # Phase 12: Funding PnL (cumulative from all settlements during trade)
    funding_pnl: float = 0.0

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
    def duration_bars(self) -> int | None:
        """Calculate duration in bars if both indices are set."""
        if self.entry_bar_index is not None and self.exit_bar_index is not None:
            return self.exit_bar_index - self.entry_bar_index
        return None

    def to_dict(self) -> dict[str, Any]:
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
            # MAE/MFE
            "mae_pct": self.mae_pct,
            "mfe_pct": self.mfe_pct,
            # Phase 12: Funding
            "funding_pnl": self.funding_pnl,
        }


@dataclass
class EquityPoint:
    """
    Single point on the equity curve.

    Attributes:
        timestamp: Bar timestamp (UTC)
        equity: Total equity (balance + unrealized PnL) in USDT
        drawdown: Current drawdown in USDT from peak equity
        drawdown_pct: Current drawdown as percentage (0.0-1.0)
    """
    timestamp: datetime
    equity: float
    drawdown: float = 0.0
    drawdown_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
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

    def to_dict(self) -> dict[str, Any]:
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
    benchmark_return_pct: float = 0.0  # Buy-and-hold return over same period
    alpha_pct: float = 0.0             # Strategy return - benchmark return

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
    avg_winning_trade_duration_bars: float = 0.0  # Duration breakdown: winners
    avg_losing_trade_duration_bars: float = 0.0   # Duration breakdown: losers
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    expectancy_usdt: float = 0.0
    payoff_ratio: float = 0.0
    recovery_factor: float = 0.0
    omega_ratio: float = 0.0  # Probability-weighted gain/loss ratio (threshold=0)
    
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
    
    # Funding metrics (separate from trading fees)
    total_funding_paid_usdt: float = 0.0      # Total funding paid out (longs in positive funding)
    total_funding_received_usdt: float = 0.0  # Total funding received (shorts in positive funding)
    net_funding_usdt: float = 0.0             # received - paid

    # Extended drawdown
    ulcer_index: float = 0.0  # Pain-adjusted drawdown measure

    # Profit factor mode (handles infinity edge cases)
    profit_factor_mode: str = "finite"  # "finite", "infinite", or "undefined"

    # Entry friction (leveraged trading specific)
    entry_attempts: int = 0           # Total entry signal attempts
    entry_rejections: int = 0         # Entries rejected (margin, size, etc.)
    entry_rejection_rate: float = 0.0  # rejections / attempts

    # Margin stress (leveraged trading specific)
    min_margin_ratio: float = 1.0     # Lowest margin ratio during backtest
    margin_calls: int = 0             # Number of margin warning events

    # Liquidation proximity (leveraged trading specific)
    closest_liquidation_pct: float = 100.0  # Closest approach to liquidation (100 = never close)

    # Tail risk metrics (critical for leveraged trading)
    skewness: float = 0.0           # Return distribution asymmetry (negative = blowup risk)
    kurtosis: float = 0.0           # Fat tails measure (>3 = fatter than normal)
    var_95_pct: float = 0.0         # 95% Value at Risk (worst 5% daily loss)
    cvar_95_pct: float = 0.0        # Expected Shortfall (avg loss beyond VaR)

    # Leverage metrics
    avg_leverage_used: float = 0.0  # Average actual leverage during backtest
    max_gross_exposure_pct: float = 0.0  # Peak position_value / equity * 100

    # Trade quality (MAE/MFE - how trades behave before close)
    mae_avg_pct: float = 0.0        # Avg Maximum Adverse Excursion (worst drawdown per trade)
    mfe_avg_pct: float = 0.0        # Avg Maximum Favorable Excursion (best profit per trade)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            # Equity
            "initial_equity": self.initial_equity,
            "final_equity": self.final_equity,
            "net_profit": self.net_profit,
            "net_return_pct": self.net_return_pct,
            "benchmark_return_pct": self.benchmark_return_pct,
            "alpha_pct": self.alpha_pct,
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
            "avg_winning_trade_duration_bars": self.avg_winning_trade_duration_bars,
            "avg_losing_trade_duration_bars": self.avg_losing_trade_duration_bars,
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "expectancy_usdt": self.expectancy_usdt,
            "payoff_ratio": self.payoff_ratio,
            "recovery_factor": self.recovery_factor,
            "omega_ratio": self.omega_ratio,
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
            # Funding metrics
            "total_funding_paid_usdt": self.total_funding_paid_usdt,
            "total_funding_received_usdt": self.total_funding_received_usdt,
            "net_funding_usdt": self.net_funding_usdt,
            # Extended drawdown
            "ulcer_index": self.ulcer_index,
            # Profit factor mode
            "profit_factor_mode": self.profit_factor_mode,
            # Entry friction
            "entry_attempts": self.entry_attempts,
            "entry_rejections": self.entry_rejections,
            "entry_rejection_rate": self.entry_rejection_rate,
            # Margin stress
            "min_margin_ratio": self.min_margin_ratio,
            "margin_calls": self.margin_calls,
            # Liquidation proximity
            "closest_liquidation_pct": self.closest_liquidation_pct,
            # Tail risk
            "skewness": self.skewness,
            "kurtosis": self.kurtosis,
            "var_95_pct": self.var_95_pct,
            "cvar_95_pct": self.cvar_95_pct,
            # Leverage
            "avg_leverage_used": self.avg_leverage_used,
            "max_gross_exposure_pct": self.max_gross_exposure_pct,
            # Trade quality
            "mae_avg_pct": self.mae_avg_pct,
            "mfe_avg_pct": self.mfe_avg_pct,
        }


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

    def to_dict(self) -> dict[str, Any]:
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
    
    # System-level fields
    symbol: str = ""
    tf: str = ""
    window_name: str = ""
    description: str = ""  # Play description for UI display
    
    # Context
    risk_mode: str = "none"
    data_env: str = "backtest"
    
    # Structured metrics
    metrics: BacktestMetrics = field(default_factory=BacktestMetrics)
    
    # Resolved risk profile fields used for this run
    risk_initial_equity_used: float = 0.0
    risk_per_trade_pct_used: float = 0.0
    risk_max_leverage_used: float = 0.0
    
    # Warm-up and window metadata (for debugging and reproducibility)
    warmup_bars: int = 0
    max_indicator_lookback: int = 0
    data_window_requested_start: str = ""  # ISO string from YAML/preset
    data_window_requested_end: str = ""
    data_window_loaded_start: str = ""     # After warm-up & clamping
    data_window_loaded_end: str = ""
    simulation_start_ts: datetime | None = None  # When simulation actually started
    
    # Artifact paths (relative to run directory)
    trades_path: str = "trades.csv"
    equity_path: str = "equity.csv"
    result_path: str = "result.json"
    
    # In-memory data (not serialized to JSON by default)
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[EquityPoint] = field(default_factory=list)

    # Artifact paths
    artifact_dir: str | None = None

    # Account curve (full margin state per bar)
    account_curve: list[AccountCurvePoint] = field(default_factory=list)

    # Run config echo (for reproducibility)
    run_config_echo: BacktestRunConfigEcho | None = None

    # Stop classification (proof-grade)
    stop_classification: StopReason | None = None  # None if ended naturally
    stop_reason_detail: str | None = None  # Human-readable stable text

    # Early-stop fields (terminal states: account_blown, insufficient_free_margin)
    stopped_early: bool = False
    stop_reason: str | None = None  # "account_blown" | "insufficient_free_margin" | "liquidated"
    stop_ts: datetime | None = None
    stop_bar_index: int | None = None
    stop_details: dict[str, Any] | None = None  # Full exchange snapshot at stop

    # Starvation tracking (non-terminal)
    entries_disabled: bool = False
    first_starved_ts: datetime | None = None
    first_starved_bar_index: int | None = None
    entry_attempts_count: int = 0
    entry_rejections_count: int = 0
    
    def to_dict(self) -> dict[str, Any]:
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
            # System-level
            "symbol": self.symbol,
            "tf": self.tf,
            "window_name": self.window_name,
            "description": self.description,
            # Timestamps
            "start_ts": self.start_ts.isoformat(),
            "end_ts": self.end_ts.isoformat(),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            # Context
            "risk_mode": self.risk_mode,
            "data_env": self.data_env,
            # Metrics (consolidated)
            "metrics": self.metrics.to_dict(),
            # Resolved risk
            "risk_initial_equity_used": self.risk_initial_equity_used,
            "risk_per_trade_pct_used": self.risk_per_trade_pct_used,
            "risk_max_leverage_used": self.risk_max_leverage_used,
            # Warm-up and window metadata
            "warmup_bars": self.warmup_bars,
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
            "artifact_dir": self.artifact_dir,
            # Run config echo
            "run_config_echo": self.run_config_echo.to_dict() if self.run_config_echo else None,
            # Stop classification (proof-grade)
            "stop_classification": self.stop_classification.value if self.stop_classification else None,
            "stop_reason_detail": self.stop_reason_detail,
            # Early-stop fields
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


@dataclass
class TimeBasedReturns:
    """
    Time-based return analytics for charting and analysis.

    Phase 4 of Backtest Analytics: Provides daily, weekly, and monthly
    return series for performance visualization and period analysis.

    Return values are percentages (e.g., 5.2 = 5.2% return).
    """
    # Period returns: {period_key: return_pct}
    daily_returns: dict[str, float] = field(default_factory=dict)    # "2025-01-15" -> 1.5
    weekly_returns: dict[str, float] = field(default_factory=dict)   # "2025-W03" -> 3.2
    monthly_returns: dict[str, float] = field(default_factory=dict)  # "2025-01" -> 8.7

    # Best/worst periods: (period_key, return_pct) or None
    best_day: tuple[str, float] | None = None      # ("2025-01-15", 5.2)
    worst_day: tuple[str, float] | None = None     # ("2025-01-20", -3.1)
    best_week: tuple[str, float] | None = None     # ("2025-W03", 8.5)
    worst_week: tuple[str, float] | None = None    # ("2025-W05", -4.2)
    best_month: tuple[str, float] | None = None    # ("2025-01", 12.3)
    worst_month: tuple[str, float] | None = None   # ("2025-02", -6.1)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "daily_returns": self.daily_returns,
            "weekly_returns": self.weekly_returns,
            "monthly_returns": self.monthly_returns,
            "best_day": list(self.best_day) if self.best_day else None,
            "worst_day": list(self.worst_day) if self.worst_day else None,
            "best_week": list(self.best_week) if self.best_week else None,
            "worst_week": list(self.worst_week) if self.worst_week else None,
            "best_month": list(self.best_month) if self.best_month else None,
            "worst_month": list(self.worst_month) if self.worst_month else None,
        }
