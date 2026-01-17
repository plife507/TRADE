"""
RuntimeSnapshot builder.

Constructs RuntimeSnapshot from materialized inputs:
- Bars (exec/med_tf/high_tf)
- Exchange state (from StepResult)
- Feature snapshots (from cache)
- Mark price (from exchange, NOT recomputed here)
- History (bars and features)

CRITICAL: SnapshotBuilder must NOT call PriceModel.
Mark price is computed once by SimulatedExchange and passed in.

Phase 1: Added history support for crossover detection and structure-based SL.
"""

from datetime import datetime

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
        tf_mapping: dict[str, str],
        history_config: HistoryConfig | None = None,
    ):
        """
        Initialize snapshot builder.

        Args:
            symbol: Trading symbol
            tf_mapping: Dict with high_tf, med_tf, low_tf -> tf string + exec -> role
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
        features_high_tf: FeatureSnapshot,
        features_med_tf: FeatureSnapshot,
        features_exec: FeatureSnapshot,
        history_bars_exec: tuple[Bar, ...] = (),
        history_features_exec: tuple[FeatureSnapshot, ...] = (),
        history_features_high_tf: tuple[FeatureSnapshot, ...] = (),
        history_features_med_tf: tuple[FeatureSnapshot, ...] = (),
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
            features_high_tf: high_tf feature snapshot (may be carry-forward)
            features_med_tf: med_tf feature snapshot (may be carry-forward)
            features_exec: Exec-TF feature snapshot (current bar)
            history_bars_exec: Previous exec-TF bars (oldest first)
            history_features_exec: Previous exec-TF features (oldest first)
            history_features_high_tf: Previous *closed* high_tf features (oldest first)
            history_features_med_tf: Previous *closed* med_tf features (oldest first)
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
        if len(history_features_high_tf) > config.features_high_tf_count and config.features_high_tf_count > 0:
            raise ValueError(
                f"history_features_high_tf has {len(history_features_high_tf)} items, "
                f"but config allows max {config.features_high_tf_count}"
            )
        if len(history_features_med_tf) > config.features_med_tf_count and config.features_med_tf_count > 0:
            raise ValueError(
                f"history_features_med_tf has {len(history_features_med_tf)} items, "
                f"but config allows max {config.features_med_tf_count}"
            )

        # Resolve exec_tf: exec role points to low_tf/med_tf/high_tf, then get concrete TF
        exec_role = self.tf_mapping.get("exec", "low_tf")
        exec_tf = self.tf_mapping.get(exec_role, bar_exec.tf)

        return RuntimeSnapshot(
            ts_close=ts_close,
            symbol=self.symbol,
            exec_tf=exec_tf,
            mark_price=mark_price,
            mark_price_source=mark_price_source,
            bar_exec=bar_exec,
            exchange_state=exchange_state,
            features_high_tf=features_high_tf,
            features_med_tf=features_med_tf,
            features_exec=features_exec,
            tf_mapping=dict(self.tf_mapping),
            history_bars_exec=history_bars_exec,
            history_features_exec=history_features_exec,
            history_features_high_tf=history_features_high_tf,
            history_features_med_tf=history_features_med_tf,
            history_config=self.history_config,
            history_ready=history_ready,
        )

    def build_with_defaults(
        self,
        ts_close: datetime,
        bar_exec: Bar,
        mark_price: float,
        mark_price_source: str,
        exchange_state: ExchangeState,
        features_exec: FeatureSnapshot,
        features_high_tf: FeatureSnapshot | None = None,
        features_med_tf: FeatureSnapshot | None = None,
        history_bars_exec: tuple[Bar, ...] = (),
        history_features_exec: tuple[FeatureSnapshot, ...] = (),
        history_features_high_tf: tuple[FeatureSnapshot, ...] = (),
        history_features_med_tf: tuple[FeatureSnapshot, ...] = (),
        history_ready: bool = True,
    ) -> RuntimeSnapshot:
        """
        Build RuntimeSnapshot with not-ready defaults for missing TFs.

        Use when high_tf/med_tf haven't closed yet (warmup period).

        Args:
            ts_close: Engine step time
            bar_exec: Current exec-TF bar
            mark_price: Mark price from exchange
            mark_price_source: Mark price source
            exchange_state: Exchange state
            features_exec: Exec-TF features (required)
            features_high_tf: Optional high_tf features (default: not-ready)
            features_med_tf: Optional med_tf features (default: not-ready)
            history_bars_exec: Previous exec-TF bars
            history_features_exec: Previous exec-TF features
            history_features_high_tf: Previous high_tf features
            history_features_med_tf: Previous med_tf features
            history_ready: Whether required history is filled

        Returns:
            RuntimeSnapshot with placeholders for missing TFs
        """
        # Create not-ready placeholders if needed
        if features_high_tf is None:
            features_high_tf = create_not_ready_feature_snapshot(
                tf=self.tf_mapping.get("high_tf", bar_exec.tf),
                ts_close=ts_close,
                bar=bar_exec,
                reason="high_tf has not closed yet",
            )

        if features_med_tf is None:
            features_med_tf = create_not_ready_feature_snapshot(
                tf=self.tf_mapping.get("med_tf", bar_exec.tf),
                ts_close=ts_close,
                bar=bar_exec,
                reason="med_tf has not closed yet",
            )

        return self.build(
            ts_close=ts_close,
            bar_exec=bar_exec,
            mark_price=mark_price,
            mark_price_source=mark_price_source,
            exchange_state=exchange_state,
            features_high_tf=features_high_tf,
            features_med_tf=features_med_tf,
            features_exec=features_exec,
            history_bars_exec=history_bars_exec,
            history_features_exec=history_features_exec,
            history_features_high_tf=history_features_high_tf,
            history_features_med_tf=history_features_med_tf,
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
