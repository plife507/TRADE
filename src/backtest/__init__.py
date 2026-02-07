"""
Backtest engine module.

Provides deterministic backtesting for trading strategies with:
- Play-native engine creation via factory functions
- Pluggable risk policies (none vs rules)
- Simulated exchange with deterministic execution
- Metrics calculation and artifact writing

USAGE (Play-native):
    from src.backtest import load_play, create_engine_from_play, run_engine_with_play

    play = load_play("my_strategy")
    engine = create_engine_from_play(play, window_start, window_end)
    result = run_engine_with_play(engine, play)
"""

from .types import (
    Bar,
    Trade,
    EquityPoint,
    AccountCurvePoint,
    BacktestMetrics,
    BacktestResult,
    BacktestRunConfigEcho,
    WindowConfig,
    StopReason,
)
from .system_config import (
    SystemConfig,
    RiskProfileConfig,
    list_systems,
    resolve_risk_profile,
)
from .window_presets import (
    get_window_preset,
    list_available_presets,
    has_preset,
)
from .data_builder import DataBuilder, DataBuildResult
from .engine_data_prep import PreparedFrame, MultiTFPreparedFrames
from .engine_factory import (
    create_engine_from_play,
    run_engine_with_play,
    # Professional naming aliases
    create_backtest_engine,
    PlayRunResult,
)
from .risk_policy import (
    RiskPolicy,
    NoneRiskPolicy,
    RulesRiskPolicy,
    create_risk_policy,
)
from .simulated_risk_manager import SimulatedRiskManager, SizingResult
from .play import (
    Play,
    PositionPolicy,
    PositionMode,
    RiskModel,
    StopLossRule,
    StopLossType,
    TakeProfitRule,
    TakeProfitType,
    SizingRule,
    SizingModel,
    load_play,
    list_plays,
    # Config models
    ExitMode,
    FeeModel,
    AccountConfig,
    PLAYS_DIR,
)
from .feature_registry import (
    Feature,
    FeatureType,
    FeatureRegistry,
    InputSource,
)
from .execution_validation import (
    # Gate 8.0
    compute_play_hash,
    validate_play_contract,
    PlayValidationResult,
    ValidationIssue,
    ValidationSeverity,
    # Gate 8.1
    extract_rule_feature_refs,
    get_declared_features_by_role,
    validate_play_features,
    FeatureReference,
    # Gate 8.2
    compute_warmup_requirements,
    WarmupRequirements,
    PlaySignalEvaluator,
    SignalDecision,
    EvaluationResult,
    # Gate 8.4
    validate_pre_evaluation,
    PreEvaluationStatus,
    # Combined
    validate_play_full,
)

__all__ = [
    # Types
    "Bar",
    "Trade",
    "EquityPoint",
    "AccountCurvePoint",
    "BacktestMetrics",
    "BacktestResult",
    "BacktestRunConfigEcho",
    "WindowConfig",
    "StopReason",
    # Config
    "SystemConfig",
    "RiskProfileConfig",
    "list_systems",
    "resolve_risk_profile",
    # Window presets
    "get_window_preset",
    "list_available_presets",
    "has_preset",
    # Data preparation
    "DataBuilder",
    "DataBuildResult",
    "PreparedFrame",
    "MultiTFPreparedFrames",
    # Factory functions
    "create_backtest_engine",  # Professional alias
    "PlayRunResult",  # Professional alias
    # Risk policies
    "RiskPolicy",
    "NoneRiskPolicy",
    "RulesRiskPolicy",
    "create_risk_policy",
    # Simulated risk manager
    "SimulatedRiskManager",
    "SizingResult",
    # Play
    "Play",
    "PositionPolicy",
    "PositionMode",
    "RiskModel",
    "StopLossRule",
    "StopLossType",
    "TakeProfitRule",
    "TakeProfitType",
    "SizingRule",
    "SizingModel",
    "load_play",
    "list_plays",
    # Config models
    "ExitMode",
    "FeeModel",
    "AccountConfig",
    "PLAYS_DIR",
    # Feature Registry
    "Feature",
    "FeatureType",
    "FeatureRegistry",
    "InputSource",
    # Execution Validation (Phase 8)
    "compute_play_hash",
    "validate_play_contract",
    "PlayValidationResult",
    "ValidationIssue",
    "ValidationSeverity",
    "extract_rule_feature_refs",
    "get_declared_features_by_role",
    "validate_play_features",
    "FeatureReference",
    "compute_warmup_requirements",
    "WarmupRequirements",
    "PlaySignalEvaluator",
    "SignalDecision",
    "EvaluationResult",
    "validate_pre_evaluation",
    "PreEvaluationStatus",
    "validate_play_full",
    # P1.2 Refactor: New Play-native engine factory
    "create_engine_from_play",
    "run_engine_with_play",
]
