"""
Exchange-side metrics collection.

Tracks execution quality and costs:
- Slippage costs (total and per-trade)
- Fee costs
- Funding costs
- Liquidation events
- Fill rejection counts

These are exchange/execution metrics only.
Strategy-level metrics are computed separately in engine.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional

from ..types import StepResult, Fill, FillReason


@dataclass
class ExchangeMetricsSnapshot:
    """
    Snapshot of exchange metrics at a point in time.
    
    All monetary values in USDTT (quote currency).
    All monetary values are in USDT (quote currency).
    but all values are in USDTT for this simulator version.
    """
    # Slippage metrics
    total_slippage_usdt: float = 0.0
    avg_slippage_bps: float = 0.0
    max_slippage_bps: float = 0.0
    
    # Fee metrics
    total_fees_usdt: float = 0.0
    entry_fees_usdt: float = 0.0
    exit_fees_usdt: float = 0.0
    
    # Funding metrics
    total_funding_pnl_usdt: float = 0.0
    funding_events_count: int = 0
    
    # Liquidation metrics
    liquidation_count: int = 0
    liquidation_fees_usdt: float = 0.0
    
    # Fill metrics
    total_fills: int = 0
    entry_fills: int = 0
    exit_fills: int = 0
    
    # Rejection metrics
    total_rejections: int = 0
    margin_rejections: int = 0
    
    # Volume metrics
    total_volume_usdt: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_slippage_usdt": self.total_slippage_usdt,
            "avg_slippage_bps": self.avg_slippage_bps,
            "max_slippage_bps": self.max_slippage_bps,
            "total_fees_usdt": self.total_fees_usdt,
            "entry_fees_usdt": self.entry_fees_usdt,
            "exit_fees_usdt": self.exit_fees_usdt,
            "total_funding_pnl_usdt": self.total_funding_pnl_usdt,
            "funding_events_count": self.funding_events_count,
            "liquidation_count": self.liquidation_count,
            "liquidation_fees_usdt": self.liquidation_fees_usdt,
            "total_fills": self.total_fills,
            "entry_fills": self.entry_fills,
            "exit_fills": self.exit_fills,
            "total_rejections": self.total_rejections,
            "margin_rejections": self.margin_rejections,
            "total_volume_usdt": self.total_volume_usdt,
        }


class ExchangeMetrics:
    """
    Collects and aggregates exchange-side metrics.
    
    Updated on each bar via record_step().
    """
    
    def __init__(self):
        """Initialize metrics collector."""
        self._reset()
    
    def _reset(self) -> None:
        """Reset all metrics to zero."""
        # Slippage tracking
        self._slippage_amounts: List[float] = []  # USD amounts
        self._slippage_bps_list: List[float] = []
        
        # Fee tracking
        self._entry_fees = 0.0
        self._exit_fees = 0.0
        
        # Funding tracking
        self._funding_pnl = 0.0
        self._funding_count = 0
        
        # Liquidation tracking
        self._liquidation_count = 0
        self._liquidation_fees = 0.0
        
        # Fill tracking
        self._entry_fills = 0
        self._exit_fills = 0
        
        # Rejection tracking
        self._total_rejections = 0
        self._margin_rejections = 0
        
        # Volume tracking
        self._total_volume = 0.0
    
    def record_step(self, step_result: StepResult) -> None:
        """
        Record metrics from a step result.
        
        Args:
            step_result: Result of processing a bar
        """
        # Record fills
        for fill in step_result.fills:
            self._record_fill(fill)
        
        # Record rejections
        for rejection in step_result.rejections:
            self._total_rejections += 1
            if "margin" in rejection.code.lower() or "insufficient" in rejection.code.lower():
                self._margin_rejections += 1
        
        # Record funding
        if step_result.funding_result:
            self._funding_pnl += step_result.funding_result.funding_pnl
            self._funding_count += len(step_result.funding_result.events_applied)
        
        # Record liquidation
        if step_result.liquidation_result and step_result.liquidation_result.liquidated:
            self._liquidation_count += 1
            if step_result.liquidation_result.event:
                self._liquidation_fees += step_result.liquidation_result.event.liquidation_fee
    
    def _record_fill(self, fill: Fill) -> None:
        """
        Record metrics from a fill.
        
        Args:
            fill: Fill to record
        """
        # Volume
        self._total_volume += fill.size_usdt
        
        # Slippage
        if fill.slippage > 0 and fill.price > 0:
            self._slippage_amounts.append(fill.slippage * fill.size)
            slippage_bps = (fill.slippage / fill.price) * 10000
            self._slippage_bps_list.append(slippage_bps)
        
        # Fees by type
        if fill.reason == FillReason.ENTRY:
            self._entry_fills += 1
            self._entry_fees += fill.fee
        else:
            self._exit_fills += 1
            self._exit_fees += fill.fee
    
    def get_metrics(self) -> ExchangeMetricsSnapshot:
        """
        Get current metrics snapshot.
        
        Returns:
            ExchangeMetricsSnapshot with aggregated metrics
        """
        # Calculate slippage stats
        total_slippage = sum(self._slippage_amounts)
        avg_slippage_bps = 0.0
        max_slippage_bps = 0.0
        
        if self._slippage_bps_list:
            avg_slippage_bps = sum(self._slippage_bps_list) / len(self._slippage_bps_list)
            max_slippage_bps = max(self._slippage_bps_list)
        
        return ExchangeMetricsSnapshot(
            # Slippage
            total_slippage_usdt=total_slippage,
            avg_slippage_bps=avg_slippage_bps,
            max_slippage_bps=max_slippage_bps,
            # Fees
            total_fees_usdt=self._entry_fees + self._exit_fees,
            entry_fees_usdt=self._entry_fees,
            exit_fees_usdt=self._exit_fees,
            # Funding
            total_funding_pnl_usdt=self._funding_pnl,
            funding_events_count=self._funding_count,
            # Liquidation
            liquidation_count=self._liquidation_count,
            liquidation_fees_usdt=self._liquidation_fees,
            # Fills
            total_fills=self._entry_fills + self._exit_fills,
            entry_fills=self._entry_fills,
            exit_fills=self._exit_fills,
            # Rejections
            total_rejections=self._total_rejections,
            margin_rejections=self._margin_rejections,
            # Volume
            total_volume_usdt=self._total_volume,
        )
    
    def reset(self) -> None:
        """Reset all metrics."""
        self._reset()

