"""
Testing Agent: CLI-driven testing framework for TRADE backtests.

This module provides comprehensive indicator validation using real data
and market condition coverage across BTC and L2 alts.

Components:
- runner: Test orchestration and execution
- reporting: Output formatting and summary generation
- validation_runner: Rigorous validation framework
- known_answer_tests: Synthetic scenarios with predetermined answers
- fill_validator: Fill timing correctness validation
- lookahead_detector: Future data leakage detection
- determinism_checker: Reproducibility validation

Usage:
    from src.testing_agent import run_indicator_suite, run_agent

    # Run full indicator validation
    result = run_indicator_suite(fix_gaps=True)

    # Run testing agent in different modes
    result = run_agent(mode="full", fix_gaps=True)  # BTC + L2 alts
    result = run_agent(mode="btc", fix_gaps=True)   # BTC only
    result = run_agent(mode="l2", fix_gaps=True)    # L2 alts only

    # Run rigorous validation
    from src.testing_agent import run_validation, ValidationLevel
    result = run_validation(level=ValidationLevel.ALL)
"""

from .runner import (
    run_indicator_suite,
    run_tier_tests,
    run_symbol_tests,
    run_parity_check,
    run_live_parity,
    run_agent,
    PlayResult,
    TierResult,
    TestResult,
    ParityResult,
    AgentResult,
)

from .reporting import (
    print_suite_report,
    print_tier_report,
    print_symbol_report,
    print_parity_report,
    print_live_parity_report,
    print_agent_report,
    print_play_detail,
    print_tier_summary_stats,
)

from .validation_runner import (
    run_validation,
    ValidationLevel,
    ValidationResult,
    LevelResult,
    print_validation_report,
)

from .known_answer_tests import (
    KnownAnswerScenario,
    KnownAnswerResult,
    ExpectedSignal,
    ExpectedTrade,
    create_ema_cross_scenario,
    create_rsi_threshold_scenario,
    create_sl_tp_scenario,
    get_all_known_answer_scenarios,
    get_scenario_by_name,
    run_known_answer_test,
)

from .fill_validator import (
    FillTimingResult,
    FillViolation,
    validate_fill_timing,
    validate_sl_tp_execution,
    validate_sl_tp_timing,
)

from .lookahead_detector import (
    LookaheadResult,
    LookaheadViolation,
    detect_lookahead_bias,
    detect_indicator_lookahead,
    detect_ema_lookahead,
)

from .determinism_checker import (
    DeterminismResult,
    DeterminismViolation,
    RunHash,
    run_determinism_check,
    compute_trades_hash,
    compute_equity_hash,
    compute_signals_hash,
    format_determinism_report,
)

__all__ = [
    # Runner
    "run_indicator_suite",
    "run_tier_tests",
    "run_symbol_tests",
    "run_parity_check",
    "run_live_parity",
    "run_agent",
    "PlayResult",
    "TierResult",
    "TestResult",
    "ParityResult",
    "AgentResult",
    # Reporting
    "print_suite_report",
    "print_tier_report",
    "print_symbol_report",
    "print_parity_report",
    "print_live_parity_report",
    "print_agent_report",
    "print_play_detail",
    "print_tier_summary_stats",
    # Validation Runner
    "run_validation",
    "ValidationLevel",
    "ValidationResult",
    "LevelResult",
    "print_validation_report",
    # Known-Answer Tests
    "KnownAnswerScenario",
    "KnownAnswerResult",
    "ExpectedSignal",
    "ExpectedTrade",
    "create_ema_cross_scenario",
    "create_rsi_threshold_scenario",
    "create_sl_tp_scenario",
    "get_all_known_answer_scenarios",
    "get_scenario_by_name",
    "run_known_answer_test",
    # Fill Validator
    "FillTimingResult",
    "FillViolation",
    "validate_fill_timing",
    "validate_sl_tp_execution",
    "validate_sl_tp_timing",
    # Look-Ahead Detector
    "LookaheadResult",
    "LookaheadViolation",
    "detect_lookahead_bias",
    "detect_indicator_lookahead",
    "detect_ema_lookahead",
    # Determinism Checker
    "DeterminismResult",
    "DeterminismViolation",
    "RunHash",
    "run_determinism_check",
    "compute_trades_hash",
    "compute_equity_hash",
    "compute_signals_hash",
    "format_determinism_report",
]
