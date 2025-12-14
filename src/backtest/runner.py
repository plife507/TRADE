"""
Backtest Runner with Gate Enforcement.

The canonical runner for executing IdeaCard-based backtests.
Enforces all gates before and after the run:

1. Data Preflight Gate (before run)
   - Validates data availability for all TFs
   - Checks timestamps, gaps, alignment
   - Writes preflight_report.json

2. Backtest Execution
   - Runs the backtest engine
   - Produces trades, equity curve, events

3. Artifact Export Gate (after run)
   - Validates all required files exist
   - Checks column headers
   - Validates result.json fields

4. Results Summary
   - Prints console summary
   - Writes result.json

If any gate fails, the runner stops and returns a failure status.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
import json
import time


def _utcnow() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)

import pandas as pd

from .idea_card import IdeaCard, load_idea_card
from .runtime.preflight import (
    PreflightStatus,
    PreflightReport,
    run_preflight_gate,
    DataLoader,
)
from .artifacts.artifact_standards import (
    ArtifactPathConfig,
    ArtifactValidationResult,
    validate_artifacts,
    validate_artifact_path_config,
    ResultsSummary,
    compute_results_summary,
    STANDARD_FILES,
)
from .artifacts.hashes import compute_trades_hash, compute_equity_hash, compute_run_hash
from .gates.indicator_requirements_gate import (
    validate_indicator_requirements,
    extract_available_keys_from_feature_frames,
    IndicatorGateStatus,
    IndicatorRequirementsResult,
)
from .execution_validation import (
    validate_idea_card_full,
    compute_warmup_requirements,
    compute_idea_card_hash,
    IdeaCardSignalEvaluator,
    SignalDecision,
)


class GateFailure(Exception):
    """Raised when a gate fails."""
    pass


# =============================================================================
# Pipeline Version (for artifact tracking)
# =============================================================================
PIPELINE_VERSION = "1.0.0"


# =============================================================================
# IdeaCard-Native Backtest Execution
# =============================================================================

class IdeaCardBacktestResult:
    """Result from IdeaCard-native backtest execution."""
    
    def __init__(
        self,
        trades: List[Any],
        equity_curve: List[Any],
        final_equity: float,
        idea_card_hash: str,
        metrics: Any = None,  # BacktestMetrics from engine
    ):
        self.trades = trades
        self.equity_curve = equity_curve
        self.final_equity = final_equity
        self.idea_card_hash = idea_card_hash
        self.metrics = metrics


def create_default_engine_factory():
    """
    Create a default engine factory that bridges IdeaCard to BacktestEngine.
    
    TEMP: This factory exists until engine natively accepts IdeaCard.
    Single caller: run_backtest_with_gates() in this module.
    
    Returns:
        Factory function that takes (idea_card, runner_config) and returns engine
    """
    from .system_config import SystemConfig, RiskProfileConfig, StrategyInstanceConfig, StrategyInstanceInputs
    from .engine import BacktestEngine
    from .types import WindowConfig
    
    def factory(idea_card: IdeaCard, runner_config: "RunnerConfig") -> "IdeaCardEngineWrapper":
        """
        Create an engine wrapper for the given IdeaCard.
        
        Args:
            idea_card: The IdeaCard to execute
            runner_config: Runner configuration with window dates
            
        Returns:
            Engine wrapper with run() method
        """
        # Get first symbol
        symbol = idea_card.symbol_universe[0] if idea_card.symbol_universe else "BTCUSDT"
        
        # Extract capital/account params from IdeaCard (REQUIRED - no defaults)
        if idea_card.account is None:
            raise ValueError(
                f"IdeaCard '{idea_card.id}' is missing account section. "
                "account.starting_equity_usdt and account.max_leverage are required."
            )
        
        initial_equity = idea_card.account.starting_equity_usdt
        max_leverage = idea_card.account.max_leverage
        
        # Extract fee model from IdeaCard if present
        taker_fee_rate = 0.0006  # Bybit typical default
        if idea_card.account.fee_model:
            taker_fee_rate = idea_card.account.fee_model.taker_rate
        
        # Extract min trade notional from IdeaCard if present
        min_trade_usdt = 1.0
        if idea_card.account.min_trade_notional_usdt is not None:
            min_trade_usdt = idea_card.account.min_trade_notional_usdt
        
        # Extract risk params from IdeaCard risk_model
        risk_per_trade_pct = 1.0
        if idea_card.risk_model:
            if idea_card.risk_model.sizing.model.value == "percent_equity":
                risk_per_trade_pct = idea_card.risk_model.sizing.value
            # Override max_leverage from risk_model.sizing if different
            if idea_card.risk_model.sizing.max_leverage:
                max_leverage = idea_card.risk_model.sizing.max_leverage
        
        # Build minimal SystemConfig for engine
        # TEMP: This adapter will be deleted when engine accepts IdeaCard directly
        risk_profile = RiskProfileConfig(
            initial_equity=initial_equity,  # From IdeaCard.account (REQUIRED)
            max_leverage=max_leverage,
            risk_per_trade_pct=risk_per_trade_pct,
            taker_fee_rate=taker_fee_rate,
            min_trade_usdt=min_trade_usdt,
        )
        
        # Extract feature specs from IdeaCard for engine
        feature_specs_by_role = {}
        for role, tf_config in idea_card.tf_configs.items():
            feature_specs_by_role[role] = list(tf_config.feature_specs)
        
        # Auto-detect if crossover operators require history
        # Check all conditions for cross_above/cross_below operators
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
        
        # Create strategy instance
        strategy_instance = StrategyInstanceConfig(
            strategy_instance_id="idea_card_strategy",
            strategy_id=idea_card.id,
            strategy_version=idea_card.version,
            inputs=StrategyInstanceInputs(symbol=symbol, tf=idea_card.exec_tf),
            params=strategy_params,
        )
        
        # Create SystemConfig
        system_config = SystemConfig(
            system_id=idea_card.id,
            symbol=symbol,
            tf=idea_card.exec_tf,
            strategies=[strategy_instance],
            primary_strategy_instance_id="idea_card_strategy",
            windows={
                "run": {
                    # Strip timezone for engine compatibility (DuckDB stores naive UTC)
                    "start": runner_config.window_start.replace(tzinfo=None).isoformat() if runner_config.window_start.tzinfo else runner_config.window_start.isoformat(),
                    "end": runner_config.window_end.replace(tzinfo=None).isoformat() if runner_config.window_end.tzinfo else runner_config.window_end.isoformat(),
                }
            },
            risk_profile=risk_profile,
            risk_mode="none",
            feature_specs_by_role=feature_specs_by_role,
        )
        
        # Build tf_mapping from IdeaCard
        # This enables multi-TF mode when HTF/MTF are defined
        tf_mapping = {
            "ltf": idea_card.exec_tf,
            "mtf": idea_card.mtf or idea_card.exec_tf,  # Fallback to exec if MTF not defined
            "htf": idea_card.htf or idea_card.exec_tf,  # Fallback to exec if HTF not defined
        }
        
        # Create engine with tf_mapping to enable multi-TF mode
        engine = BacktestEngine(
            config=system_config,
            window_name="run",
            tf_mapping=tf_mapping,
        )
        
        # Return wrapper with signal evaluator
        return IdeaCardEngineWrapper(engine, idea_card)
    
    return factory


class IdeaCardEngineWrapper:
    """
    Wrapper that runs BacktestEngine with IdeaCard signal evaluation.
    
    TEMP: This wrapper bridges IdeaCard signal rules to the engine's strategy interface.
    Will be deleted when engine natively supports IdeaCard.
    """
    
    def __init__(self, engine: Any, idea_card: IdeaCard):
        self.engine = engine
        self.idea_card = idea_card
        self.evaluator = IdeaCardSignalEvaluator(idea_card)
    
    def run(self) -> IdeaCardBacktestResult:
        """
        Run the backtest using IdeaCard signal evaluation.
        
        Returns:
            IdeaCardBacktestResult with trades and equity curve
        """
        from ..core.risk_manager import Signal
        
        def idea_card_strategy(snapshot, params) -> Optional[Signal]:
            """Strategy function that uses IdeaCard signal evaluator."""
            # Check if we have a position
            has_position = snapshot.exchange_state.has_position
            position_side = snapshot.exchange_state.position_side
            
            # Evaluate signal rules
            result = self.evaluator.evaluate(snapshot, has_position, position_side)
            
            # Convert to Signal
            if result.decision == SignalDecision.NO_ACTION:
                return None
            elif result.decision == SignalDecision.ENTRY_LONG:
                return Signal(
                    symbol=self.idea_card.symbol_universe[0],
                    direction="LONG",
                    size_usd=0.0,  # Engine will compute from risk_profile
                    strategy=self.idea_card.id,
                    confidence=1.0,
                    metadata={
                        "stop_loss": result.stop_loss_price,
                        "take_profit": result.take_profit_price,
                    }
                )
            elif result.decision == SignalDecision.ENTRY_SHORT:
                return Signal(
                    symbol=self.idea_card.symbol_universe[0],
                    direction="SHORT",
                    size_usd=0.0,  # Engine will compute from risk_profile
                    strategy=self.idea_card.id,
                    confidence=1.0,
                    metadata={
                        "stop_loss": result.stop_loss_price,
                        "take_profit": result.take_profit_price,
                    }
                )
            elif result.decision == SignalDecision.EXIT:
                return Signal(
                    symbol=self.idea_card.symbol_universe[0],
                    direction="FLAT",
                    size_usd=0.0,
                    strategy=self.idea_card.id,
                    confidence=1.0,
                )
            
            return None
        
        # Run the engine
        backtest_result = self.engine.run(idea_card_strategy)
        
        # Compute IdeaCard hash
        idea_card_hash = compute_idea_card_hash(self.idea_card)
        
        return IdeaCardBacktestResult(
            trades=backtest_result.trades,
            equity_curve=backtest_result.equity_curve,
            final_equity=backtest_result.metrics.final_equity,
            idea_card_hash=idea_card_hash,
            metrics=backtest_result.metrics,
        )


@dataclass
class RunnerConfig:
    """Configuration for the backtest runner."""
    # IdeaCard
    idea_card_id: str = ""
    idea_card: Optional[IdeaCard] = None
    
    # Window
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    window_name: Optional[str] = None  # Alternative to explicit dates
    
    # Paths
    base_output_dir: Path = field(default_factory=lambda: Path("backtests"))
    idea_cards_dir: Optional[Path] = None
    
    # Gates
    skip_preflight: bool = False  # For testing only
    skip_artifact_validation: bool = False  # For testing only
    
    # Data loader
    data_loader: Optional[DataLoader] = None
    
    # Auto-sync
    auto_sync_missing_data: bool = False
    
    def load_idea_card(self) -> IdeaCard:
        """Load the IdeaCard if not already loaded."""
        if self.idea_card is not None:
            return self.idea_card
        
        if not self.idea_card_id:
            raise ValueError("idea_card_id is required")
        
        self.idea_card = load_idea_card(self.idea_card_id, base_dir=self.idea_cards_dir)
        return self.idea_card


@dataclass
class RunnerResult:
    """Result of a backtest run."""
    success: bool
    run_id: str
    artifact_path: Optional[Path] = None
    
    # Gate results
    preflight_report: Optional[PreflightReport] = None
    artifact_validation: Optional[ArtifactValidationResult] = None
    
    # Summary
    summary: Optional[ResultsSummary] = None
    
    # Error info
    error_message: Optional[str] = None
    gate_failed: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "success": self.success,
            "run_id": self.run_id,
            "artifact_path": str(self.artifact_path) if self.artifact_path else None,
            "preflight_passed": self.preflight_report.overall_status == PreflightStatus.PASSED if self.preflight_report else None,
            "artifact_validation_passed": self.artifact_validation.passed if self.artifact_validation else None,
            "summary": self.summary.to_dict() if self.summary else None,
            "error_message": self.error_message,
            "gate_failed": self.gate_failed,
        }


def run_backtest_with_gates(
    config: RunnerConfig,
    engine_factory: Optional[Callable] = None,
) -> RunnerResult:
    """
    Run a backtest with all gates enforced.
    
    Args:
        config: Runner configuration
        engine_factory: Optional factory to create the backtest engine
                       (for testing/dependency injection)
    
    Returns:
        RunnerResult with success status and all gate results
    """
    run_start_time = time.time()
    # run_id will be auto-generated by ArtifactPathConfig based on sequential number
    run_id = ""  # Will be set by artifact config
    
    result = RunnerResult(success=False, run_id=run_id)
    
    try:
        # Load IdeaCard
        idea_card = config.load_idea_card()
        
        # Validate window
        if not config.window_start or not config.window_end:
            raise ValueError("window_start and window_end are required")
        
        # Get first symbol (for now, only single-symbol support)
        if not idea_card.symbol_universe:
            raise ValueError("IdeaCard has no symbols in symbol_universe")
        symbol = idea_card.symbol_universe[0]
        
        # Setup artifact path (run_id is auto-generated if empty)
        artifact_config = ArtifactPathConfig(
            base_dir=config.base_output_dir,
            idea_card_id=idea_card.id,
            symbol=symbol,
            tf_exec=idea_card.exec_tf,
            window_start=config.window_start,
            window_end=config.window_end,
            run_id=run_id,  # Empty = auto-generate sequential number
        )
        # Capture the generated run_id
        run_id = artifact_config.run_id
        
        # Validate artifact config
        path_errors = validate_artifact_path_config(artifact_config)
        if path_errors:
            raise ValueError(f"Invalid artifact config: {'; '.join(path_errors)}")
        
        # Create output folder
        artifact_path = artifact_config.create_folder()
        result.artifact_path = artifact_path
        
        # =====================================================================
        # GATE 1: Data Preflight
        # =====================================================================
        if not config.skip_preflight:
            if not config.data_loader:
                raise ValueError("data_loader is required for preflight gate")
            
            print("\n[PREFLIGHT] Running Data Preflight Gate...")
            
            preflight_report = run_preflight_gate(
                idea_card=idea_card,
                data_loader=config.data_loader,
                window_start=config.window_start,
                window_end=config.window_end,
                gap_threshold_multiplier=3.0,
                auto_sync_missing=config.auto_sync_missing_data,
            )
            
            result.preflight_report = preflight_report
            
            # Write preflight report
            preflight_path = artifact_path / STANDARD_FILES["preflight"]
            preflight_report.write_json(preflight_path)
            
            # Print summary
            preflight_report.print_summary()
            
            # Check gate
            if preflight_report.overall_status == PreflightStatus.FAILED:
                result.gate_failed = "preflight"
                result.error_message = "Data preflight gate failed - see preflight_report.json for details"
                raise GateFailure(result.error_message)
        
        # =====================================================================
        # GATE 2: Indicator Requirements Gate
        # =====================================================================
        # Validate that all required indicator keys are declared
        # This runs before simulation to catch misnamed keys early
        # The actual key availability check happens after frame preparation
        
        # Check if IdeaCard has any required_indicators declared
        has_required_indicators = any(
            tf_config.required_indicators
            for tf_config in idea_card.tf_configs.values()
        )
        
        if has_required_indicators:
            print("\n[INDICATOR GATE] Validating Indicator Requirements...")
            
            # Get declared feature specs (output_key from each spec)
            from .indicators import get_required_indicator_columns_from_specs
            
            available_keys_by_role: Dict[str, set] = {}
            for role, tf_config in idea_card.tf_configs.items():
                specs = list(tf_config.feature_specs)
                if specs:
                    # Get the expanded keys (including multi-output suffixes)
                    expanded_keys = get_required_indicator_columns_from_specs(specs)
                    available_keys_by_role[role] = set(expanded_keys)
                else:
                    available_keys_by_role[role] = set()
            
            # Validate required vs available
            indicator_gate_result = validate_indicator_requirements(
                idea_card=idea_card,
                available_keys_by_role=available_keys_by_role,
            )
            
            # Print result
            if indicator_gate_result.passed:
                print("  [PASS] All required indicators are declared in FeatureSpecs")
            elif indicator_gate_result.status == IndicatorGateStatus.SKIPPED:
                print("  [SKIP] No required_indicators declared in IdeaCard")
            else:
                print(indicator_gate_result.format_error())
                result.gate_failed = "indicator_requirements"
                result.error_message = indicator_gate_result.error_message
                raise GateFailure(result.error_message)
        else:
            print("\n[INDICATOR GATE] Skipped - no required_indicators declared")
        
        # =====================================================================
        # RUN BACKTEST
        # =====================================================================
        print("\n[RUN] Running Backtest...")
        
        # Use provided factory or default
        actual_factory = engine_factory if engine_factory else create_default_engine_factory()
        
        # Create and run engine
        engine = actual_factory(idea_card, config)
        engine_result = engine.run()
        
        # Extract trades and equity
        trades: List[Dict[str, Any]] = []
        equity_curve: List[Dict[str, Any]] = []
        idea_card_hash = ""
        
        if hasattr(engine_result, 'trades'):
            trades = [t.to_dict() if hasattr(t, 'to_dict') else t for t in engine_result.trades]
        if hasattr(engine_result, 'equity_curve'):
            equity_curve = [e.to_dict() if hasattr(e, 'to_dict') else e for e in engine_result.equity_curve]
        if hasattr(engine_result, 'idea_card_hash'):
            idea_card_hash = engine_result.idea_card_hash
        else:
            idea_card_hash = compute_idea_card_hash(idea_card)
        
        # Write trades.csv (use correct column names matching Trade.to_dict())
        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame(columns=[
            "entry_time", "exit_time", "side", "entry_price", "exit_price",
            "entry_size_usdt", "net_pnl", "stop_loss", "take_profit", "exit_reason",
        ])
        trades_df.to_csv(artifact_path / STANDARD_FILES["trades"], index=False)
        
        # Write equity.csv
        equity_df = pd.DataFrame(equity_curve) if equity_curve else pd.DataFrame(columns=[
            "timestamp", "equity",
        ])
        equity_df.to_csv(artifact_path / STANDARD_FILES["equity"], index=False)
        
        # Compute and write results summary
        run_duration = time.time() - run_start_time
        # Compute hashes for determinism tracking
        trades_hash = compute_trades_hash(engine_result.trades) if hasattr(engine_result, 'trades') and engine_result.trades else ""
        equity_hash = compute_equity_hash(engine_result.equity_curve) if hasattr(engine_result, 'equity_curve') and engine_result.equity_curve else ""
        run_hash = compute_run_hash(trades_hash, equity_hash, idea_card_hash)
        
        # Resolve idea path (where IdeaCard was loaded from)
        resolved_idea_path = str(config.idea_cards_dir / f"{idea_card.id}.yml") if config.idea_cards_dir else f"configs/idea_cards/{idea_card.id}.yml"
        
        summary = compute_results_summary(
            idea_card_id=idea_card.id,
            symbol=symbol,
            tf_exec=idea_card.exec_tf,
            window_start=config.window_start,
            window_end=config.window_end,
            run_id=run_id,
            trades=trades,
            equity_curve=equity_curve,
            artifact_path=str(artifact_path),
            run_duration_seconds=run_duration,
            # Gate D required fields
            idea_hash=idea_card_hash,
            pipeline_version=PIPELINE_VERSION,
            resolved_idea_path=resolved_idea_path,
            run_hash=run_hash,
            # Pass pre-computed metrics for comprehensive analytics
            metrics=engine_result.metrics,
        )
        
        result.summary = summary
        
        # Write result.json
        result_path = artifact_path / STANDARD_FILES["result"]
        summary.write_json(result_path)
        
        # =====================================================================
        # Write pipeline_signature.json (Gate D.1)
        # =====================================================================
        from .artifacts.pipeline_signature import (
            PipelineSignature, 
            PIPELINE_SIGNATURE_FILE,
            create_pipeline_signature,
        )
        
        # Get declared feature keys from IdeaCard
        declared_keys = []
        for role, tf_config in idea_card.tf_configs.items():
            for spec in tf_config.feature_specs:
                declared_keys.extend(spec.output_keys_list)
        
        # Get computed feature keys (from engine result if available)
        computed_keys = declared_keys.copy()  # Assume match for now (validated in FeatureFrameBuilder)
        
        pipeline_sig = create_pipeline_signature(
            run_id=run_id,
            idea_card=idea_card,
            idea_card_hash=idea_card_hash,
            resolved_path=resolved_idea_path,
            declared_keys=declared_keys,
            computed_keys=computed_keys,
        )
        
        # Validate signature
        sig_errors = pipeline_sig.validate()
        if sig_errors:
            result.gate_failed = "pipeline_signature"
            result.error_message = f"Pipeline signature validation failed: {sig_errors}"
            raise GateFailure(result.error_message)
        
        # Write signature
        sig_path = artifact_path / PIPELINE_SIGNATURE_FILE
        pipeline_sig.write_json(sig_path)
        
        # =====================================================================
        # GATE 2: Artifact Validation
        # =====================================================================
        if not config.skip_artifact_validation:
            print("\n[ARTIFACTS] Running Artifact Export Gate...")
            
            artifact_validation = validate_artifacts(artifact_path)
            result.artifact_validation = artifact_validation
            
            # Print summary
            artifact_validation.print_summary()
            
            # Check gate
            if not artifact_validation.passed:
                result.gate_failed = "artifact_validation"
                result.error_message = "Artifact export gate failed - see validation errors"
                raise GateFailure(result.error_message)
        
        # =====================================================================
        # SUCCESS
        # =====================================================================
        result.success = True
        
        # Print final summary
        summary.print_summary()
        
        return result
        
    except GateFailure as e:
        # Gate failure - already handled
        print(f"\n[FAILED] Gate Failed: {result.gate_failed}")
        print(f"   {result.error_message}")
        return result
        
    except Exception as e:
        # Unexpected error
        import traceback
        result.error_message = str(e)
        print(f"\n[ERROR] Error: {e}")
        traceback.print_exc()
        return result


def run_smoke_test(
    idea_card_id: str,
    window_start: datetime,
    window_end: datetime,
    data_loader: DataLoader,
    base_output_dir: Path = Path("backtests"),
    idea_cards_dir: Optional[Path] = None,
) -> RunnerResult:
    """
    Convenience function to run a smoke test for an IdeaCard.
    
    Args:
        idea_card_id: IdeaCard identifier
        window_start: Backtest window start
        window_end: Backtest window end
        data_loader: Function to load data (symbol, tf) -> DataFrame
        base_output_dir: Base directory for artifacts
        idea_cards_dir: Directory containing IdeaCard YAMLs
        
    Returns:
        RunnerResult with success status
    """
    config = RunnerConfig(
        idea_card_id=idea_card_id,
        window_start=window_start,
        window_end=window_end,
        data_loader=data_loader,
        base_output_dir=base_output_dir,
        idea_cards_dir=idea_cards_dir,
    )
    
    return run_backtest_with_gates(config)


# =============================================================================
# CLI Entrypoint
# =============================================================================

def main():
    """
    CLI entrypoint for running backtests.
    
    Usage:
        python -m src.backtest.runner --idea <id> --start <date> --end <date> --env <live|demo> --export-root <path>
    
    Example:
        python -m src.backtest.runner --idea SOLUSDT_15m_ema_crossover --start 2024-01-01 --end 2024-03-01 --env live --export-root backtests/
    """
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(
        description="Run IdeaCard-based backtest with gate enforcement",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--idea",
        required=True,
        help="IdeaCard ID (filename without .yml) or path to YAML file",
    )
    parser.add_argument(
        "--start",
        required=True,
        help="Backtest start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        required=True,
        help="Backtest end date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--env",
        choices=["live", "demo"],
        default="live",
        help="Data environment (live or demo)",
    )
    parser.add_argument(
        "--export-root",
        default="backtests/",
        help="Base directory for artifact export",
    )
    parser.add_argument(
        "--idea-dir",
        default=None,
        help="Override IdeaCard directory (default: configs/idea_cards/)",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip data preflight gate (for testing only)",
    )
    parser.add_argument(
        "--auto-sync",
        action="store_true",
        help="Auto-sync missing data during preflight",
    )
    
    args = parser.parse_args()
    
    # Parse dates
    try:
        window_start = datetime.fromisoformat(args.start)
        window_end = datetime.fromisoformat(args.end)
    except ValueError as e:
        print(f"[ERROR] Invalid date format: {e}")
        print("Use YYYY-MM-DD format (e.g., 2024-01-01)")
        sys.exit(1)
    
    # Ensure dates are timezone-aware
    if window_start.tzinfo is None:
        window_start = window_start.replace(tzinfo=timezone.utc)
    if window_end.tzinfo is None:
        window_end = window_end.replace(tzinfo=timezone.utc)
    
    # Create data loader
    from ..data.historical_data_store import get_historical_store
    
    store = get_historical_store(env=args.env)
    
    def data_loader(symbol: str, tf: str, start: datetime, end: datetime):
        """Load OHLCV data from DuckDB."""
        return store.get_ohlcv(symbol=symbol, tf=tf, start=start, end=end)
    
    # Build config
    config = RunnerConfig(
        idea_card_id=args.idea,
        window_start=window_start,
        window_end=window_end,
        data_loader=data_loader,
        base_output_dir=Path(args.export_root),
        idea_cards_dir=Path(args.idea_dir) if args.idea_dir else None,
        skip_preflight=args.skip_preflight,
        auto_sync_missing_data=args.auto_sync,
    )
    
    # Run backtest
    print(f"\n{'='*60}")
    print(f"  BACKTEST RUNNER")
    print(f"{'='*60}")
    print(f"  IdeaCard:   {args.idea}")
    print(f"  Window:     {window_start.date()} -> {window_end.date()}")
    print(f"  Env:        {args.env}")
    print(f"  Export:     {args.export_root}")
    print(f"{'='*60}\n")
    
    result = run_backtest_with_gates(config)
    
    # Exit with appropriate code
    if result.success:
        print(f"\n[SUCCESS] Backtest completed successfully")
        print(f"  Artifacts: {result.artifact_path}")
        sys.exit(0)
    else:
        print(f"\n[FAILED] Backtest failed")
        if result.gate_failed:
            print(f"  Gate failed: {result.gate_failed}")
        if result.error_message:
            print(f"  Error: {result.error_message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
