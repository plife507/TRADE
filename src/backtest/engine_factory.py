"""
Factory functions module for BacktestEngine.

This module provides factory functions for creating and running BacktestEngine:
- run_backtest: Convenience function to run a backtest from system_id
- create_engine_from_idea_card: Create engine from IdeaCard
- run_engine_with_idea_card: Run engine with IdeaCard signal evaluation
- _get_idea_card_result_class: Get IdeaCardBacktestResult class

These functions provide the main entry points for backtest execution.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import BacktestEngine
    from .types import BacktestResult
    from .idea_card import IdeaCard
    from .runtime.types import RuntimeSnapshot
    from ..core.risk_manager import Signal


def run_backtest(
    system_id: str,
    window_name: str,
    strategy: Callable[["RuntimeSnapshot", Dict[str, Any]], Optional["Signal"]],
    run_dir: Optional[Path] = None,
) -> "BacktestResult":
    """
    Convenience function to run a backtest.

    Args:
        system_id: System configuration ID
        window_name: Window to use ("hygiene" or "test")
        strategy: Strategy function
        run_dir: Optional directory for artifacts

    Returns:
        BacktestResult
    """
    from .engine import BacktestEngine
    from .system_config import load_system_config

    config = load_system_config(system_id, window_name)
    engine = BacktestEngine(config, window_name, run_dir)
    return engine.run(strategy)


# =============================================================================
# IdeaCard-Native Engine Factory (P1.2 Refactor)
# =============================================================================
# Replaces create_default_engine_factory and IdeaCardEngineWrapper in runner.py

def create_engine_from_idea_card(
    idea_card: "IdeaCard",
    window_start: datetime,
    window_end: datetime,
    warmup_by_role: Dict[str, int],
    delay_by_role: Optional[Dict[str, int]] = None,
    run_dir: Optional[Path] = None,
    on_snapshot: Optional[Callable] = None,
) -> "BacktestEngine":
    """
    Create a BacktestEngine from an IdeaCard.

    This is the canonical factory for IdeaCard-native backtest execution.
    Replaces the legacy adapter pattern (IdeaCardEngineWrapper).

    Args:
        idea_card: Source IdeaCard with all strategy/feature specs
        window_start: Backtest window start
        window_end: Backtest window end
        warmup_by_role: Warmup bars per TF role (from Preflight)
        delay_by_role: Delay bars per TF role (from Preflight)
        run_dir: Optional output directory for artifacts
        on_snapshot: Optional snapshot callback for auditing

    Returns:
        BacktestEngine configured from IdeaCard

    Raises:
        ValueError: If IdeaCard is missing required sections (account)
    """
    from .engine import BacktestEngine
    from .system_config import (
        SystemConfig,
        RiskProfileConfig,
        StrategyInstanceConfig,
        StrategyInstanceInputs,
    )

    # Validate required sections
    if idea_card.account is None:
        raise ValueError(
            f"IdeaCard '{idea_card.id}' is missing account section. "
            "account.starting_equity_usdt and account.max_leverage are required."
        )

    # Get first symbol
    symbol = idea_card.symbol_universe[0] if idea_card.symbol_universe else "BTCUSDT"

    # Extract capital/account params from IdeaCard (REQUIRED - no defaults)
    initial_equity = idea_card.account.starting_equity_usdt
    max_leverage = idea_card.account.max_leverage

    # Extract fee model from IdeaCard (REQUIRED - fail loud if missing)
    if idea_card.account.fee_model is None:
        raise ValueError(
            f"IdeaCard '{idea_card.id}' is missing account.fee_model. "
            "Fee model is required (taker_bps, maker_bps). No silent defaults allowed. "
            "Add: account.fee_model.taker_bps and account.fee_model.maker_bps"
        )
    taker_fee_rate = idea_card.account.fee_model.taker_rate

    # Extract min trade notional from IdeaCard (REQUIRED - fail loud if missing)
    if idea_card.account.min_trade_notional_usdt is None:
        raise ValueError(
            f"IdeaCard '{idea_card.id}' is missing account.min_trade_notional_usdt. "
            "Minimum trade notional is required. No silent defaults allowed. "
            "Add: account.min_trade_notional_usdt (e.g., 10.0)"
        )
    min_trade_usdt = idea_card.account.min_trade_notional_usdt

    # Extract slippage from IdeaCard if present (flows to ExecutionConfig)
    slippage_bps = 5.0  # Default only if not specified
    if idea_card.account.slippage_bps is not None:
        slippage_bps = idea_card.account.slippage_bps

    # Extract maker fee from IdeaCard (fee_model guaranteed to exist from validation above)
    maker_fee_bps = idea_card.account.fee_model.maker_bps

    # Extract risk params from IdeaCard risk_model
    risk_per_trade_pct = 1.0
    if idea_card.risk_model:
        if idea_card.risk_model.sizing.model.value == "percent_equity":
            risk_per_trade_pct = idea_card.risk_model.sizing.value
        # Override max_leverage from risk_model.sizing if different
        if idea_card.risk_model.sizing.max_leverage:
            max_leverage = idea_card.risk_model.sizing.max_leverage

    # Extract maintenance margin rate from IdeaCard if present
    maintenance_margin_rate = 0.005  # Default: Bybit lowest tier (0.5%)
    if idea_card.account.maintenance_margin_rate is not None:
        maintenance_margin_rate = idea_card.account.maintenance_margin_rate

    # Build RiskProfileConfig
    risk_profile = RiskProfileConfig(
        initial_equity=initial_equity,
        max_leverage=max_leverage,
        risk_per_trade_pct=risk_per_trade_pct,
        taker_fee_rate=taker_fee_rate,
        min_trade_usdt=min_trade_usdt,
        maintenance_margin_rate=maintenance_margin_rate,
    )

    # Extract feature specs from IdeaCard
    feature_specs_by_role = {}
    for role, tf_config in idea_card.tf_configs.items():
        feature_specs_by_role[role] = list(tf_config.feature_specs)

    # Delay defaults to empty dict (all zeros)
    delay_bars_by_role = delay_by_role if delay_by_role is not None else {}

    # Auto-detect if crossover operators require history
    requires_history = False
    for rule in idea_card.signal_rules.entry_rules:
        for cond in rule.conditions:
            if cond.operator.value in ("cross_above", "cross_below"):
                requires_history = True
                break
    for rule in idea_card.signal_rules.exit_rules:
        for cond in rule.conditions:
            if cond.operator.value in ("cross_above", "cross_below"):
                requires_history = True
                break

    # Build params with history config if crossovers are used
    strategy_params = {}
    if requires_history:
        strategy_params["history"] = {
            "bars_exec_count": 2,
            "features_exec_count": 2,
            "features_htf_count": 2,
            "features_mtf_count": 2,
        }

    # Pass execution params from IdeaCard to engine (fixes value flow bug)
    # These flow to ExecutionConfig in engine.py
    strategy_params["slippage_bps"] = slippage_bps
    strategy_params["taker_fee_bps"] = taker_fee_rate * 10000  # Convert rate to bps
    strategy_params["maker_fee_bps"] = maker_fee_bps

    # Create strategy instance
    strategy_instance = StrategyInstanceConfig(
        strategy_instance_id="idea_card_strategy",
        strategy_id=idea_card.id,
        strategy_version=idea_card.version,
        inputs=StrategyInstanceInputs(symbol=symbol, tf=idea_card.exec_tf),
        params=strategy_params,
    )

    # Strip timezone for engine compatibility (DuckDB stores naive UTC)
    window_start_naive = window_start.replace(tzinfo=None) if window_start.tzinfo else window_start
    window_end_naive = window_end.replace(tzinfo=None) if window_end.tzinfo else window_end

    # Extract required indicators from IdeaCard tf_configs
    required_indicators_by_role: Dict[str, List[str]] = {}
    for role, tf_config in idea_card.tf_configs.items():
        if tf_config.required_indicators:
            required_indicators_by_role[role] = list(tf_config.required_indicators)

    # Create SystemConfig
    system_config = SystemConfig(
        system_id=idea_card.id,
        symbol=symbol,
        tf=idea_card.exec_tf,
        strategies=[strategy_instance],
        primary_strategy_instance_id="idea_card_strategy",
        windows={
            "run": {
                "start": window_start_naive.isoformat(),
                "end": window_end_naive.isoformat(),
            }
        },
        risk_profile=risk_profile,
        risk_mode="none",
        feature_specs_by_role=feature_specs_by_role,
        warmup_bars_by_role=warmup_by_role,
        delay_bars_by_role=delay_bars_by_role,
        required_indicators_by_role=required_indicators_by_role,
    )

    # Build tf_mapping from IdeaCard
    tf_mapping = {
        "ltf": idea_card.exec_tf,
        "mtf": idea_card.mtf or idea_card.exec_tf,
        "htf": idea_card.htf or idea_card.exec_tf,
    }

    # Create engine
    engine = BacktestEngine(
        config=system_config,
        window_name="run",
        run_dir=run_dir,
        tf_mapping=tf_mapping,
        on_snapshot=on_snapshot,
    )

    # Store IdeaCard reference for run_with_idea_card()
    engine._idea_card = idea_card

    return engine


def run_engine_with_idea_card(
    engine: "BacktestEngine",
    idea_card: "IdeaCard",
) -> "IdeaCardBacktestResult":
    """
    Run a BacktestEngine using IdeaCard signal evaluation.

    This replaces IdeaCardEngineWrapper.run() and consolidates signal
    evaluation into the engine execution flow.

    Args:
        engine: BacktestEngine (created via create_engine_from_idea_card)
        idea_card: IdeaCard with signal rules

    Returns:
        IdeaCardBacktestResult with trades, equity curve, and metrics
    """
    from .execution_validation import (
        IdeaCardSignalEvaluator,
        SignalDecision,
        compute_idea_card_hash,
    )
    from .idea_card_yaml_builder import compile_idea_card
    from ..core.risk_manager import Signal

    # Import here to avoid circular import
    IdeaCardBacktestResult = _get_idea_card_result_class()

    # Stage 4b: Compile condition refs for O(1) hot-loop evaluation
    compiled_idea_card = compile_idea_card(idea_card)

    # Create signal evaluator with compiled IdeaCard
    evaluator = IdeaCardSignalEvaluator(compiled_idea_card)

    def idea_card_strategy(snapshot, params) -> Optional[Signal]:
        """Strategy function that uses IdeaCard signal evaluator."""
        # Check if we have a position
        has_position = snapshot.has_position
        position_side = snapshot.position_side

        # Evaluate signal rules
        result = evaluator.evaluate(snapshot, has_position, position_side)

        # Convert to Signal
        if result.decision == SignalDecision.NO_ACTION:
            return None
        elif result.decision == SignalDecision.ENTRY_LONG:
            return Signal(
                symbol=idea_card.symbol_universe[0],
                direction="LONG",
                size_usd=0.0,  # Engine computes from risk_profile
                strategy=idea_card.id,
                confidence=1.0,
                metadata={
                    "stop_loss": result.stop_loss_price,
                    "take_profit": result.take_profit_price,
                }
            )
        elif result.decision == SignalDecision.ENTRY_SHORT:
            return Signal(
                symbol=idea_card.symbol_universe[0],
                direction="SHORT",
                size_usd=0.0,
                strategy=idea_card.id,
                confidence=1.0,
                metadata={
                    "stop_loss": result.stop_loss_price,
                    "take_profit": result.take_profit_price,
                }
            )
        elif result.decision == SignalDecision.EXIT:
            return Signal(
                symbol=idea_card.symbol_universe[0],
                direction="FLAT",
                size_usd=0.0,
                strategy=idea_card.id,
                confidence=1.0,
            )

        return None

    # Run the engine
    backtest_result = engine.run(idea_card_strategy)

    # Compute IdeaCard hash
    idea_card_hash = compute_idea_card_hash(idea_card)

    return IdeaCardBacktestResult(
        trades=backtest_result.trades,
        equity_curve=backtest_result.equity_curve,
        final_equity=backtest_result.metrics.final_equity,
        idea_card_hash=idea_card_hash,
        metrics=backtest_result.metrics,
    )


@dataclass
class IdeaCardBacktestResult:
    """Result from IdeaCard-native backtest execution."""
    trades: List[Any]
    equity_curve: List[Any]
    final_equity: float
    idea_card_hash: str
    metrics: Any = None


def _get_idea_card_result_class():
    """
    Get IdeaCardBacktestResult class (avoids import at module level).

    This allows runner.py to define the class and engine.py to use it
    without circular imports.
    """
    return IdeaCardBacktestResult
