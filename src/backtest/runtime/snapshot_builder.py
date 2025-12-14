"""
RuntimeSnapshot builder.

Constructs RuntimeSnapshot from materialized inputs:
- Bars (exec/MTF/HTF)
- Exchange state (from StepResult)
- Feature snapshots (from cache)
- Mark price (from exchange, NOT recomputed here)
- History (bars and features)

CRITICAL: SnapshotBuilder must NOT call PriceModel.
Mark price is computed once by SimulatedExchange and passed in.

Phase 1: Added history support for crossover detection and structure-based SL.
"""

from datetime import datetime
from typing import Dict, Optional, Tuple

from .types import (
    Bar,
    FeatureSnapshot,
    ExchangeState,
    RuntimeSnapshot,
    HistoryConfig,
    DEFAULT_HISTORY_CONFIG,
    create_not_ready_feature_snapshot,
)


class SnapshotBuilder:
    """
    Builds RuntimeSnapshot from fully materialized inputs.
    
    This builder consumes pre-computed values. It does NOT:
    - Call PriceModel to compute mark price
    - Compute indicators
    - Access the database
    
    All inputs must be provided by the engine/caller.
    
    Phase 1: Supports history for crossover detection and structure-based SL.
    """
    
    def __init__(
        self,
        symbol: str,
        tf_mapping: Dict[str, str],
        history_config: Optional[HistoryConfig] = None,
    ):
        """
        Initialize snapshot builder.
        
        Args:
            symbol: Trading symbol
            tf_mapping: Dict with htf, mtf, ltf/exec -> tf string
            history_config: Optional history configuration (default: no history)
        """
        self.symbol = symbol
        self.tf_mapping = tf_mapping
        self.history_config = history_config or DEFAULT_HISTORY_CONFIG
    
    def build(
        self,
        ts_close: datetime,
        bar_exec: Bar,
        mark_price: float,
        mark_price_source: str,
        exchange_state: ExchangeState,
        features_htf: FeatureSnapshot,
        features_mtf: FeatureSnapshot,
        features_exec: FeatureSnapshot,
        history_bars_exec: Tuple[Bar, ...] = (),
        history_features_exec: Tuple[FeatureSnapshot, ...] = (),
        history_features_htf: Tuple[FeatureSnapshot, ...] = (),
        history_features_mtf: Tuple[FeatureSnapshot, ...] = (),
        history_ready: bool = True,
    ) -> RuntimeSnapshot:
        """
        Build a RuntimeSnapshot from materialized inputs.
        
        Args:
            ts_close: Engine step time (exec candle close)
            bar_exec: Current exec-TF bar
            mark_price: Mark price from exchange StepResult
            mark_price_source: How mark was computed (close|hlc3|ohlc4)
            exchange_state: Immutable exchange state snapshot
            features_htf: HTF feature snapshot (may be carry-forward)
            features_mtf: MTF feature snapshot (may be carry-forward)
            features_exec: Exec-TF feature snapshot (current bar)
            history_bars_exec: Previous exec-TF bars (oldest first)
            history_features_exec: Previous exec-TF features (oldest first)
            history_features_htf: Previous *closed* HTF features (oldest first)
            history_features_mtf: Previous *closed* MTF features (oldest first)
            history_ready: Whether required history windows are filled
            
        Returns:
            RuntimeSnapshot ready for strategy consumption
        """
        # Validate history lengths don't exceed config
        config = self.history_config
        if len(history_bars_exec) > config.bars_exec_count and config.bars_exec_count > 0:
            raise ValueError(
                f"history_bars_exec has {len(history_bars_exec)} items, "
                f"but config allows max {config.bars_exec_count}"
            )
        if len(history_features_exec) > config.features_exec_count and config.features_exec_count > 0:
            raise ValueError(
                f"history_features_exec has {len(history_features_exec)} items, "
                f"but config allows max {config.features_exec_count}"
            )
        if len(history_features_htf) > config.features_htf_count and config.features_htf_count > 0:
            raise ValueError(
                f"history_features_htf has {len(history_features_htf)} items, "
                f"but config allows max {config.features_htf_count}"
            )
        if len(history_features_mtf) > config.features_mtf_count and config.features_mtf_count > 0:
            raise ValueError(
                f"history_features_mtf has {len(history_features_mtf)} items, "
                f"but config allows max {config.features_mtf_count}"
            )
        
        return RuntimeSnapshot(
            ts_close=ts_close,
            symbol=self.symbol,
            exec_tf=self.tf_mapping.get("ltf", bar_exec.tf),
            mark_price=mark_price,
            mark_price_source=mark_price_source,
            bar_exec=bar_exec,
            exchange_state=exchange_state,
            features_htf=features_htf,
            features_mtf=features_mtf,
            features_exec=features_exec,
            tf_mapping=dict(self.tf_mapping),
            history_bars_exec=history_bars_exec,
            history_features_exec=history_features_exec,
            history_features_htf=history_features_htf,
            history_features_mtf=history_features_mtf,
            history_config=self.history_config,
            history_ready=history_ready,
        )
    
    def build_with_defaults(
        self,
        ts_close: datetime,
        bar_ltf: Bar,
        mark_price: float,
        mark_price_source: str,
        exchange_state: ExchangeState,
        features_ltf: FeatureSnapshot,
        features_htf: Optional[FeatureSnapshot] = None,
        features_mtf: Optional[FeatureSnapshot] = None,
        history_bars_exec: Tuple[Bar, ...] = (),
        history_features_exec: Tuple[FeatureSnapshot, ...] = (),
        history_features_htf: Tuple[FeatureSnapshot, ...] = (),
        history_features_mtf: Tuple[FeatureSnapshot, ...] = (),
        history_ready: bool = True,
    ) -> RuntimeSnapshot:
        """
        Build RuntimeSnapshot with not-ready defaults for missing TFs.
        
        Use when HTF/MTF haven't closed yet (warmup period).
        
        Args:
            ts_close: Engine step time
            bar_ltf: Current exec-TF bar (named ltf for backward compat)
            mark_price: Mark price from exchange
            mark_price_source: Mark price source
            exchange_state: Exchange state
            features_ltf: Exec-TF features (required, named ltf for backward compat)
            features_htf: Optional HTF features (default: not-ready)
            features_mtf: Optional MTF features (default: not-ready)
            history_bars_exec: Previous exec-TF bars
            history_features_exec: Previous exec-TF features
            history_features_htf: Previous HTF features
            history_features_mtf: Previous MTF features
            history_ready: Whether required history is filled
            
        Returns:
            RuntimeSnapshot with placeholders for missing TFs
        """
        # Create not-ready placeholders if needed
        if features_htf is None:
            features_htf = create_not_ready_feature_snapshot(
                tf=self.tf_mapping.get("htf", bar_ltf.tf),
                ts_close=ts_close,
                bar=bar_ltf,
                reason="HTF has not closed yet",
            )
        
        if features_mtf is None:
            features_mtf = create_not_ready_feature_snapshot(
                tf=self.tf_mapping.get("mtf", bar_ltf.tf),
                ts_close=ts_close,
                bar=bar_ltf,
                reason="MTF has not closed yet",
            )
        
        return self.build(
            ts_close=ts_close,
            bar_exec=bar_ltf,
            mark_price=mark_price,
            mark_price_source=mark_price_source,
            exchange_state=exchange_state,
            features_htf=features_htf,
            features_mtf=features_mtf,
            features_exec=features_ltf,
            history_bars_exec=history_bars_exec,
            history_features_exec=history_features_exec,
            history_features_htf=history_features_htf,
            history_features_mtf=history_features_mtf,
            history_ready=history_ready,
        )


def build_exchange_state_from_exchange(exchange) -> ExchangeState:
    """
    Build ExchangeState directly from a SimulatedExchange instance.
    
    This is more efficient than going through get_state() dict.
    
    Args:
        exchange: SimulatedExchange instance
        
    Returns:
        ExchangeState instance
    """
    position = exchange.position
    has_position = position is not None
    
    position_side = None
    position_size_usdt = 0.0
    position_qty = 0.0
    position_entry_price = 0.0
    unrealized_pnl = 0.0
    
    if position is not None:
        position_side = position.side
        position_size_usdt = position.size_usdt
        position_qty = position.size
        position_entry_price = position.entry_price
        unrealized_pnl = exchange.unrealized_pnl_usdt
    
    return ExchangeState(
        equity_usdt=exchange.equity_usdt,
        cash_usdt=exchange.cash_balance_usdt,
        used_margin_usdt=exchange.used_margin_usdt,
        free_margin_usdt=exchange.free_margin_usdt,
        available_balance_usdt=exchange.available_balance_usdt,
        maintenance_margin_usdt=exchange.maintenance_margin,
        has_position=has_position,
        position_side=position_side,
        position_size_usdt=position_size_usdt,
        position_qty=position_qty,
        position_entry_price=position_entry_price,
        unrealized_pnl_usdt=unrealized_pnl,
        entries_disabled=exchange.entries_disabled,
        entries_disabled_reason=exchange.entries_disabled_reason,
    )
