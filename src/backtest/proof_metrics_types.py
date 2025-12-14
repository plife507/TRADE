"""
Proof-grade metrics type definitions.

Structured schema for comprehensive backtest metrics that support
reproducibility verification and proof-grade analysis.

Metric tiers:
- Tier 1 (always present): Performance, drawdown, trade quality
- Tier 2 (optional/None if insufficient data): Risk-adjusted ratios
- Tier 3 (isolated-margin realism): Margin stress, entry friction, liquidation proximity

Edge-case policies:
- profit_factor: Uses ProfitFactorResult to avoid JSON inf
- sharpe/sortino: None if <2 returns or zero variance
- drawdown_pct: Safe handling for peak==0
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, Literal


@dataclass
class ProfitFactorResult:
    """
    Profit factor with explicit mode to avoid JSON infinity issues.
    
    Modes:
    - finite: value is a normal finite number
    - infinite: gross_profit > 0 but gross_loss == 0
    - undefined: both gross_profit and gross_loss are 0
    """
    value: Optional[float]
    mode: Literal["finite", "infinite", "undefined"]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "mode": self.mode,
        }
    
    @classmethod
    def compute(cls, gross_profit: float, gross_loss: float) -> "ProfitFactorResult":
        """Compute profit factor from gross profit and loss."""
        if gross_loss > 0:
            return cls(value=gross_profit / gross_loss, mode="finite")
        elif gross_profit > 0:
            return cls(value=None, mode="infinite")
        else:
            return cls(value=None, mode="undefined")


@dataclass
class PerformanceMetrics:
    """
    Tier 1: Core performance metrics (always present).
    """
    final_equity_usdt: float
    total_net_pnl_usdt: float
    return_pct: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_equity_usdt": self.final_equity_usdt,
            "total_net_pnl_usdt": self.total_net_pnl_usdt,
            "return_pct": self.return_pct,
        }


@dataclass
class DrawdownMetrics:
    """
    Tier 1: Drawdown metrics (always present).
    
    Includes ulcer_index for pain-adjusted analysis.
    """
    max_drawdown_usdt: float
    max_drawdown_pct: float
    max_drawdown_duration_bars: int
    ulcer_index: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_drawdown_usdt": self.max_drawdown_usdt,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_drawdown_duration_bars": self.max_drawdown_duration_bars,
            "ulcer_index": self.ulcer_index,
        }


@dataclass
class TradeQualityMetrics:
    """
    Tier 1: Trade quality metrics (always present).
    
    Includes streaks and duration stats.
    """
    total_trades: int
    win_count: int
    loss_count: int
    win_rate: float
    
    avg_win_usdt: float
    avg_loss_usdt: float
    
    profit_factor: ProfitFactorResult
    expectancy_per_trade: float
    
    avg_trade_duration_bars: Optional[float]
    max_winning_streak: int
    max_losing_streak: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_trades": self.total_trades,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "win_rate": self.win_rate,
            "avg_win_usdt": self.avg_win_usdt,
            "avg_loss_usdt": self.avg_loss_usdt,
            "profit_factor": self.profit_factor.to_dict(),
            "expectancy_per_trade": self.expectancy_per_trade,
            "avg_trade_duration_bars": self.avg_trade_duration_bars,
            "max_winning_streak": self.max_winning_streak,
            "max_losing_streak": self.max_losing_streak,
        }


@dataclass
class RiskAdjustedMetrics:
    """
    Tier 2: Risk-adjusted metrics (None if insufficient samples).
    
    Sharpe/Sortino require >= 2 returns with non-zero variance.
    """
    sharpe_ratio: Optional[float]
    sortino_ratio: Optional[float]
    calmar_ratio: Optional[float]  # return / max_drawdown_pct variant
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
        }


@dataclass
class MarginStressMetrics:
    """
    Tier 3: Margin stress metrics (isolated-margin realism).
    """
    max_used_margin_usdt: float
    max_used_margin_pct_of_equity: float
    min_free_margin_usdt: float
    min_available_balance_usdt: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_used_margin_usdt": self.max_used_margin_usdt,
            "max_used_margin_pct_of_equity": self.max_used_margin_pct_of_equity,
            "min_free_margin_usdt": self.min_free_margin_usdt,
            "min_available_balance_usdt": self.min_available_balance_usdt,
        }


@dataclass
class EntryFrictionMetrics:
    """
    Tier 3: Entry friction metrics (isolated-margin realism).
    
    Tracks starvation and entry rejection patterns.
    """
    entry_rejections_count: int
    entry_attempts_count: int
    entry_rejection_rate: float  # rejections / attempts (0 if no attempts)
    first_starved_timestamp: Optional[datetime]
    first_starved_bar_index: Optional[int]
    pct_time_entries_disabled: float  # % of bars with entries_disabled=True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_rejections_count": self.entry_rejections_count,
            "entry_attempts_count": self.entry_attempts_count,
            "entry_rejection_rate": self.entry_rejection_rate,
            "first_starved_timestamp": self.first_starved_timestamp.isoformat() if self.first_starved_timestamp else None,
            "first_starved_bar_index": self.first_starved_bar_index,
            "pct_time_entries_disabled": self.pct_time_entries_disabled,
        }


@dataclass
class LiquidationProximityMetrics:
    """
    Tier 3: Liquidation proximity metrics (isolated-margin realism).
    
    Tracks how close we came to liquidation.
    """
    min_equity_minus_mm_usdt: float  # Closest to liquidation
    bars_within_5pct_of_mm: int
    bars_within_10pct_of_mm: int
    bars_within_20pct_of_mm: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "min_equity_minus_mm_usdt": self.min_equity_minus_mm_usdt,
            "bars_within_5pct_of_mm": self.bars_within_5pct_of_mm,
            "bars_within_10pct_of_mm": self.bars_within_10pct_of_mm,
            "bars_within_20pct_of_mm": self.bars_within_20pct_of_mm,
        }


@dataclass
class ExposureMetrics:
    """
    Tier 3: Exposure metrics (market participation).
    """
    time_in_market_pct: float  # % of bars with has_position=True
    trades_per_day: Optional[float]  # None if insufficient timestamp range
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "time_in_market_pct": self.time_in_market_pct,
            "trades_per_day": self.trades_per_day,
        }


@dataclass
class BacktestMetricsV2:
    """
    Root proof-grade metrics container.
    
    Structured schema with explicit tiers:
    - Tier 1: performance, drawdown, trade_quality
    - Tier 2: risk_adjusted (may have None fields)
    - Tier 3: margin_stress, entry_friction, liquidation_proximity, exposure
    """
    performance: PerformanceMetrics
    drawdown: DrawdownMetrics
    trade_quality: TradeQualityMetrics
    risk_adjusted: RiskAdjustedMetrics
    margin_stress: MarginStressMetrics
    entry_friction: EntryFrictionMetrics
    liquidation_proximity: LiquidationProximityMetrics
    exposure: ExposureMetrics
    
    # Metadata
    computed_at: datetime = field(default_factory=datetime.now)
    metrics_version: str = "2.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "performance": self.performance.to_dict(),
            "drawdown": self.drawdown.to_dict(),
            "trade_quality": self.trade_quality.to_dict(),
            "risk_adjusted": self.risk_adjusted.to_dict(),
            "margin_stress": self.margin_stress.to_dict(),
            "entry_friction": self.entry_friction.to_dict(),
            "liquidation_proximity": self.liquidation_proximity.to_dict(),
            "exposure": self.exposure.to_dict(),
            "computed_at": self.computed_at.isoformat(),
            "metrics_version": self.metrics_version,
        }

