"""
Artifact Naming + Export Standards.

Defines the canonical folder/file naming conventions for backtest artifacts.
All backtest runs MUST produce artifacts in this format.

Folder structure:
    backtests/
    └── {idea_card_id}/
        └── {symbol}/
            └── {tf_exec}/
                └── {window_start}_{window_end}_{run_id}/
                    ├── result.json
                    ├── trades.csv
                    ├── equity.csv
                    ├── events.csv (optional)
                    └── preflight_report.json

File naming is fixed and deterministic.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
import json


def _utcnow() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


# =============================================================================
# Standard File Names
# =============================================================================

STANDARD_FILES = {
    "result": "result.json",
    "trades": "trades.csv",
    "equity": "equity.csv",
    "events": "events.csv",
    "preflight": "preflight_report.json",
    "account_curve": "account_curve.csv",
    "pipeline_signature": "pipeline_signature.json",
}

# Required files that MUST exist after a successful run
REQUIRED_FILES = {
    "result.json", 
    "trades.csv", 
    "equity.csv", 
    "preflight_report.json",
    "pipeline_signature.json",  # Gate D.1 requirement
}

# Optional files
OPTIONAL_FILES = {"events.csv", "account_curve.csv"}


# =============================================================================
# Required Columns in Artifact Files
# =============================================================================

REQUIRED_TRADES_COLUMNS = {
    "entry_time",
    "exit_time",
    "side",
    "entry_price",
    "exit_price",
    "entry_size_usdt",
    "net_pnl",
    "stop_loss",
    "take_profit",
    "exit_reason",
}

REQUIRED_EQUITY_COLUMNS = {
    "timestamp",
    "equity",
}

REQUIRED_RESULT_FIELDS = {
    "idea_card_id",
    "symbol",
    "tf_exec",
    "window_start",
    "window_end",
    "run_id",
    "trades_count",
    "net_pnl_usdt",
}


# =============================================================================
# Artifact Path Builder
# =============================================================================

def _get_next_run_number(base_dir: Path, idea_card_id: str, symbol: str) -> int:
    """
    Get the next sequential run number for an idea_card/symbol.
    
    Scans existing run folders and returns max + 1.
    """
    parent_dir = base_dir / idea_card_id / symbol
    if not parent_dir.exists():
        return 1
    
    max_run = 0
    for folder in parent_dir.iterdir():
        if folder.is_dir():
            # Try to parse run number from folder name (e.g., "run-001")
            name = folder.name
            if name.startswith("run-"):
                try:
                    run_num = int(name[4:])
                    max_run = max(max_run, run_num)
                except ValueError:
                    pass
    
    return max_run + 1


@dataclass
class ArtifactPathConfig:
    """
    Configuration for building artifact paths.
    
    Folder structure: {base_dir}/{idea_card_id}/{symbol}/run-{N}/
    
    Window dates and timeframe are stored in result.json, not folder names.
    """
    base_dir: Path = field(default_factory=lambda: Path("backtests"))
    idea_card_id: str = ""
    symbol: str = ""
    tf_exec: str = ""  # Stored in result.json, not in path
    window_start: Optional[datetime] = None  # Stored in result.json
    window_end: Optional[datetime] = None    # Stored in result.json
    run_id: str = ""
    
    def __post_init__(self):
        """Generate run_id if not provided."""
        if not self.run_id and self.idea_card_id and self.symbol:
            # Sequential run number: run-001, run-002, etc.
            run_num = _get_next_run_number(self.base_dir, self.idea_card_id, self.symbol)
            self.run_id = f"run-{run_num:03d}"
    
    @property
    def window_str(self) -> str:
        """Get window string for metadata (not used in path)."""
        if self.window_start and self.window_end:
            start_str = self.window_start.strftime("%Y-%m-%d")
            end_str = self.window_end.strftime("%Y-%m-%d")
            return f"{start_str} to {end_str}"
        return "unknown"
    
    @property
    def run_folder(self) -> Path:
        """
        Get the full path to the run folder.
        
        Structure: {base_dir}/{idea_card_id}/{symbol}/{run_id}/
        """
        return (
            self.base_dir
            / self.idea_card_id
            / self.symbol
            / self.run_id
        )
    
    def get_file_path(self, file_key: str) -> Path:
        """Get path to a standard file."""
        if file_key not in STANDARD_FILES:
            raise ValueError(f"Unknown file key: {file_key}. Valid keys: {list(STANDARD_FILES.keys())}")
        return self.run_folder / STANDARD_FILES[file_key]
    
    def create_folder(self) -> Path:
        """Create the run folder and return its path."""
        self.run_folder.mkdir(parents=True, exist_ok=True)
        return self.run_folder
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "base_dir": str(self.base_dir),
            "idea_card_id": self.idea_card_id,
            "symbol": self.symbol,
            "tf_exec": self.tf_exec,
            "window_start": self.window_start.isoformat() if self.window_start else None,
            "window_end": self.window_end.isoformat() if self.window_end else None,
            "run_id": self.run_id,
            "run_folder": str(self.run_folder),
        }


# =============================================================================
# Artifact Validation
# =============================================================================

@dataclass
class ArtifactValidationResult:
    """Result of artifact validation."""
    passed: bool
    run_folder: Path
    files_found: Set[str] = field(default_factory=set)
    files_missing: Set[str] = field(default_factory=set)
    column_errors: Dict[str, List[str]] = field(default_factory=dict)
    result_field_errors: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "passed": self.passed,
            "run_folder": str(self.run_folder),
            "files_found": sorted(self.files_found),
            "files_missing": sorted(self.files_missing),
            "column_errors": self.column_errors,
            "result_field_errors": self.result_field_errors,
            "errors": self.errors,
        }
    
    def print_summary(self) -> None:
        """Print validation summary to console."""
        status_icon = "[OK]" if self.passed else "[FAIL]"
        print(f"\n{status_icon} Artifact Export Gate: {'PASSED' if self.passed else 'FAILED'}")
        print(f"   Folder: {self.run_folder}")
        print(f"   Files found: {len(self.files_found)} / {len(REQUIRED_FILES)} required")
        
        if self.files_missing:
            print(f"   [ERR] Missing files: {', '.join(sorted(self.files_missing))}")
        
        if self.column_errors:
            for file, errors in self.column_errors.items():
                for err in errors:
                    print(f"   [ERR] {file}: {err}")
        
        if self.result_field_errors:
            for err in self.result_field_errors:
                print(f"   [ERR] result.json: {err}")
        
        if self.errors:
            for err in self.errors:
                print(f"   [ERR] {err}")
        
        print()


def validate_artifacts(run_folder: Path) -> ArtifactValidationResult:
    """
    Validate that artifacts in a run folder meet standards.
    
    Args:
        run_folder: Path to the run folder
        
    Returns:
        ArtifactValidationResult with validation results
    """
    result = ArtifactValidationResult(
        passed=True,
        run_folder=run_folder,
    )
    
    # Check folder exists
    if not run_folder.exists():
        result.passed = False
        result.errors.append(f"Run folder does not exist: {run_folder}")
        return result
    
    # Check required files exist
    for filename in REQUIRED_FILES:
        file_path = run_folder / filename
        if file_path.exists():
            result.files_found.add(filename)
        else:
            result.files_missing.add(filename)
    
    if result.files_missing:
        result.passed = False
        result.errors.append(f"Missing required files: {', '.join(sorted(result.files_missing))}")
    
    # Validate trades.csv columns
    trades_path = run_folder / "trades.csv"
    if trades_path.exists():
        try:
            import pandas as pd
            df = pd.read_csv(trades_path, nrows=0)  # Just read headers
            actual_cols = set(df.columns)
            missing_cols = REQUIRED_TRADES_COLUMNS - actual_cols
            if missing_cols:
                result.column_errors["trades.csv"] = [
                    f"Missing required columns: {', '.join(sorted(missing_cols))}"
                ]
                result.passed = False
        except Exception as e:
            result.column_errors["trades.csv"] = [f"Failed to read: {str(e)}"]
            result.passed = False
    
    # Validate equity.csv columns
    equity_path = run_folder / "equity.csv"
    if equity_path.exists():
        try:
            import pandas as pd
            df = pd.read_csv(equity_path, nrows=0)
            actual_cols = set(df.columns)
            missing_cols = REQUIRED_EQUITY_COLUMNS - actual_cols
            if missing_cols:
                result.column_errors["equity.csv"] = [
                    f"Missing required columns: {', '.join(sorted(missing_cols))}"
                ]
                result.passed = False
        except Exception as e:
            result.column_errors["equity.csv"] = [f"Failed to read: {str(e)}"]
            result.passed = False
    
    # Validate result.json fields
    result_path = run_folder / "result.json"
    if result_path.exists():
        try:
            with open(result_path, "r", encoding="utf-8") as f:
                result_data = json.load(f)
            
            missing_fields = REQUIRED_RESULT_FIELDS - set(result_data.keys())
            if missing_fields:
                result.result_field_errors.append(
                    f"Missing required fields: {', '.join(sorted(missing_fields))}"
                )
                result.passed = False
        except Exception as e:
            result.result_field_errors.append(f"Failed to read: {str(e)}")
            result.passed = False
    
    return result


def validate_artifact_path_config(config: ArtifactPathConfig) -> List[str]:
    """
    Validate artifact path configuration before run.
    
    Returns:
        List of error messages (empty if valid)
    """
    errors = []
    
    if not config.idea_card_id:
        errors.append("idea_card_id is required")
    if not config.symbol:
        errors.append("symbol is required")
    if not config.tf_exec:
        errors.append("tf_exec is required")
    if not config.window_start:
        errors.append("window_start is required")
    if not config.window_end:
        errors.append("window_end is required")
    
    return errors


# =============================================================================
# Results Summary
# =============================================================================

@dataclass
class ResultsSummary:
    """Summary of backtest results with comprehensive analytics."""
    # Identity
    idea_card_id: str
    symbol: str
    tf_exec: str
    window_start: datetime
    window_end: datetime
    run_id: str
    
    # Core Metrics
    trades_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    net_pnl_usdt: float = 0.0
    net_return_pct: float = 0.0
    gross_profit_usdt: float = 0.0
    gross_loss_usdt: float = 0.0
    max_drawdown_usdt: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_bars: int = 0
    
    # Risk-Adjusted Metrics
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    profit_factor: float = 0.0
    
    # Extended Trade Analytics
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
    total_fees_usdt: float = 0.0
    
    # Long/Short Breakdown
    long_trades: int = 0
    short_trades: int = 0
    long_win_rate: float = 0.0
    short_win_rate: float = 0.0
    long_pnl: float = 0.0
    short_pnl: float = 0.0
    
    # Time Metrics
    total_bars: int = 0
    bars_in_position: int = 0
    time_in_market_pct: float = 0.0
    
    # Metadata
    artifact_path: str = ""
    run_duration_seconds: float = 0.0
    
    # Gate D required fields (for artifact validation)
    idea_hash: str = ""
    pipeline_version: str = ""
    resolved_idea_path: str = ""
    run_hash: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            # Identity
            "idea_card_id": self.idea_card_id,
            "symbol": self.symbol,
            "tf_exec": self.tf_exec,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "run_id": self.run_id,
            # Core Metrics
            "trades_count": self.trades_count,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 4),
            "net_pnl_usdt": round(self.net_pnl_usdt, 2),
            "net_return_pct": round(self.net_return_pct, 2),
            "gross_profit_usdt": round(self.gross_profit_usdt, 2),
            "gross_loss_usdt": round(self.gross_loss_usdt, 2),
            "max_drawdown_usdt": round(self.max_drawdown_usdt, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "max_drawdown_duration_bars": self.max_drawdown_duration_bars,
            # Risk-Adjusted Metrics
            "sharpe": round(self.sharpe, 2),
            "sortino": round(self.sortino, 2),
            "calmar": round(self.calmar, 2),
            "profit_factor": round(self.profit_factor, 2),
            # Extended Trade Analytics
            "avg_win_usdt": round(self.avg_win_usdt, 2),
            "avg_loss_usdt": round(self.avg_loss_usdt, 2),
            "largest_win_usdt": round(self.largest_win_usdt, 2),
            "largest_loss_usdt": round(self.largest_loss_usdt, 2),
            "avg_trade_duration_bars": round(self.avg_trade_duration_bars, 2),
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "expectancy_usdt": round(self.expectancy_usdt, 2),
            "payoff_ratio": round(self.payoff_ratio, 2),
            "recovery_factor": round(self.recovery_factor, 2),
            "total_fees_usdt": round(self.total_fees_usdt, 2),
            # Long/Short Breakdown
            "long_trades": self.long_trades,
            "short_trades": self.short_trades,
            "long_win_rate": round(self.long_win_rate, 2),
            "short_win_rate": round(self.short_win_rate, 2),
            "long_pnl": round(self.long_pnl, 2),
            "short_pnl": round(self.short_pnl, 2),
            # Time Metrics
            "total_bars": self.total_bars,
            "bars_in_position": self.bars_in_position,
            "time_in_market_pct": round(self.time_in_market_pct, 2),
            # Metadata
            "artifact_path": self.artifact_path,
            "run_duration_seconds": round(self.run_duration_seconds, 2),
            # Gate D required fields
            "idea_hash": self.idea_hash,
            "pipeline_version": self.pipeline_version,
            "resolved_idea_path": self.resolved_idea_path,
            "run_hash": self.run_hash,
        }
    
    def write_json(self, path: Path) -> None:
        """Write summary to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
    
    def print_summary(self) -> None:
        """Print comprehensive summary to console."""
        window_days = (self.window_end - self.window_start).days
        pnl_icon = "[+]" if self.net_pnl_usdt >= 0 else "[-]"
        
        print("\n" + "=" * 60)
        print("  BACKTEST RESULTS SUMMARY")
        print("=" * 60)
        print(f"  IdeaCard:    {self.idea_card_id}")
        print(f"  Symbol:      {self.symbol}")
        print(f"  Timeframe:   {self.tf_exec}")
        print(f"  Window:      {self.window_start.date()} -> {self.window_end.date()} ({window_days}d)")
        print("-" * 60)
        
        # Trade Summary
        print(f"  Trades:      {self.trades_count} ({self.winning_trades}W / {self.losing_trades}L)")
        print(f"  Win Rate:    {self.win_rate * 100:.1f}%")
        print(f"  {pnl_icon} Net PnL:    {self.net_pnl_usdt:+.2f} USDT ({self.net_return_pct:+.1f}%)")
        print(f"  Max DD:      {self.max_drawdown_usdt:.2f} USDT ({self.max_drawdown_pct * 100:.1f}%)")
        print("-" * 60)
        
        # Risk-Adjusted Metrics
        print(f"  Sharpe:      {self.sharpe:.2f}")
        print(f"  Sortino:     {self.sortino:.2f}")
        print(f"  Calmar:      {self.calmar:.2f}")
        print(f"  Profit Factor: {self.profit_factor:.2f}")
        print("-" * 60)
        
        # Trade Analytics
        print(f"  Avg Win:     {self.avg_win_usdt:.2f} USDT")
        print(f"  Avg Loss:    {self.avg_loss_usdt:.2f} USDT")
        print(f"  Payoff Ratio: {self.payoff_ratio:.2f}")
        print(f"  Expectancy:  {self.expectancy_usdt:.2f} USDT/trade")
        print(f"  Max Consec:  {self.max_consecutive_wins}W / {self.max_consecutive_losses}L")
        print("-" * 60)
        
        # Long/Short Breakdown
        if self.long_trades > 0 or self.short_trades > 0:
            print(f"  Long:        {self.long_trades} trades, {self.long_win_rate:.1f}% WR, {self.long_pnl:+.2f} USDT")
            print(f"  Short:       {self.short_trades} trades, {self.short_win_rate:.1f}% WR, {self.short_pnl:+.2f} USDT")
            print("-" * 60)
        
        # Time Metrics
        print(f"  Time in Mkt: {self.time_in_market_pct:.1f}% ({self.bars_in_position}/{self.total_bars} bars)")
        print(f"  Fees:        {self.total_fees_usdt:.2f} USDT")
        print("-" * 60)
        print(f"  Artifacts:   {self.artifact_path}")
        print("=" * 60 + "\n")


def compute_results_summary(
    idea_card_id: str,
    symbol: str,
    tf_exec: str,
    window_start: datetime,
    window_end: datetime,
    run_id: str,
    trades: List[Dict[str, Any]],
    equity_curve: List[Dict[str, Any]],
    artifact_path: str = "",
    run_duration_seconds: float = 0.0,
    # Gate D required fields
    idea_hash: str = "",
    pipeline_version: str = "",
    resolved_idea_path: str = "",
    run_hash: str = "",
    # Optional pre-computed metrics from BacktestMetrics
    metrics: Optional[Any] = None,  # BacktestMetrics type hint avoided for circular import
) -> ResultsSummary:
    """
    Compute results summary from trades and equity curve.
    
    Args:
        idea_card_id: IdeaCard identifier
        symbol: Trading symbol
        tf_exec: Execution timeframe
        window_start: Backtest window start
        window_end: Backtest window end
        run_id: Run identifier
        trades: List of trade dicts with pnl_usdt field
        equity_curve: List of equity point dicts with equity field
        artifact_path: Path to artifact folder
        run_duration_seconds: Run duration
        idea_hash: IdeaCard hash for determinism tracking
        pipeline_version: Pipeline version string
        resolved_idea_path: Path where IdeaCard was loaded from
        run_hash: Combined hash of trades + equity for determinism
        metrics: Pre-computed BacktestMetrics object (if provided, uses these values)
        
    Returns:
        ResultsSummary with computed metrics
    """
    summary = ResultsSummary(
        idea_card_id=idea_card_id,
        symbol=symbol,
        tf_exec=tf_exec,
        window_start=window_start,
        window_end=window_end,
        run_id=run_id,
        artifact_path=artifact_path,
        run_duration_seconds=run_duration_seconds,
        idea_hash=idea_hash,
        pipeline_version=pipeline_version,
        resolved_idea_path=resolved_idea_path,
        run_hash=run_hash,
    )
    
    # If pre-computed metrics provided, use them directly
    if metrics is not None:
        summary.trades_count = metrics.total_trades
        summary.winning_trades = metrics.win_count
        summary.losing_trades = metrics.loss_count
        summary.win_rate = metrics.win_rate / 100.0  # Convert from % to decimal
        summary.net_pnl_usdt = metrics.net_profit
        summary.net_return_pct = metrics.net_return_pct
        summary.gross_profit_usdt = metrics.gross_profit
        summary.gross_loss_usdt = -metrics.gross_loss  # Store as negative
        summary.max_drawdown_usdt = metrics.max_drawdown_abs
        summary.max_drawdown_pct = metrics.max_drawdown_pct / 100.0  # Convert from % to decimal
        summary.max_drawdown_duration_bars = metrics.max_drawdown_duration_bars
        # Risk-adjusted
        summary.sharpe = metrics.sharpe
        summary.sortino = metrics.sortino
        summary.calmar = metrics.calmar
        summary.profit_factor = metrics.profit_factor
        # Extended analytics
        summary.avg_win_usdt = metrics.avg_win_usdt
        summary.avg_loss_usdt = metrics.avg_loss_usdt
        summary.largest_win_usdt = metrics.largest_win_usdt
        summary.largest_loss_usdt = metrics.largest_loss_usdt
        summary.avg_trade_duration_bars = metrics.avg_trade_duration_bars
        summary.max_consecutive_wins = metrics.max_consecutive_wins
        summary.max_consecutive_losses = metrics.max_consecutive_losses
        summary.expectancy_usdt = metrics.expectancy_usdt
        summary.payoff_ratio = metrics.payoff_ratio
        summary.recovery_factor = metrics.recovery_factor
        summary.total_fees_usdt = metrics.total_fees
        # Long/short
        summary.long_trades = metrics.long_trades
        summary.short_trades = metrics.short_trades
        summary.long_win_rate = metrics.long_win_rate
        summary.short_win_rate = metrics.short_win_rate
        summary.long_pnl = metrics.long_pnl
        summary.short_pnl = metrics.short_pnl
        # Time metrics
        summary.total_bars = metrics.total_bars
        summary.bars_in_position = metrics.bars_in_position
        summary.time_in_market_pct = metrics.time_in_market_pct
        return summary
    
    # Legacy: compute from trades/equity if no metrics provided
    summary.trades_count = len(trades)
    
    if trades:
        pnls = [t.get("net_pnl", 0.0) for t in trades]
        summary.winning_trades = sum(1 for p in pnls if p > 0)
        summary.losing_trades = sum(1 for p in pnls if p < 0)
        summary.win_rate = summary.winning_trades / summary.trades_count if summary.trades_count > 0 else 0.0
        summary.net_pnl_usdt = sum(pnls)
        summary.gross_profit_usdt = sum(p for p in pnls if p > 0)
        summary.gross_loss_usdt = sum(p for p in pnls if p < 0)
    
    # Drawdown from equity curve
    if equity_curve:
        equities = [e.get("equity", 0.0) for e in equity_curve]
        if equities:
            peak = equities[0]
            max_dd = 0.0
            max_dd_pct = 0.0
            
            for eq in equities:
                if eq > peak:
                    peak = eq
                dd = peak - eq
                dd_pct = dd / peak if peak > 0 else 0.0
                if dd > max_dd:
                    max_dd = dd
                    max_dd_pct = dd_pct
            
            summary.max_drawdown_usdt = max_dd
            summary.max_drawdown_pct = max_dd_pct
    
    return summary
