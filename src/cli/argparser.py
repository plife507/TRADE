"""
Argument parser setup for TRADE CLI.

Defines all subcommands and their arguments:
- backtest: Play-based backtesting (run, preflight, indicators, data-fix, list, audits)
- play: Unified Play engine (backtest/demo/live/shadow)
- test: Indicator validation testing agent
"""

import argparse


def setup_argparse() -> argparse.Namespace:
    """
    Parse command-line arguments for trade_cli.

    Supports:
      --smoke data   Run data builder smoke test only
      --smoke full   Run full CLI smoke test (data + trading + diagnostics)

      backtest run   Run Play-based backtest (golden path)
      backtest preflight   Check data/config without running
      backtest data-fix    Fix data gaps/coverage
      backtest list        List available Plays
    """
    parser = argparse.ArgumentParser(
        description="TRADE - Bybit Unified Trading Account CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python trade_cli.py                              # Interactive mode (default)
  python trade_cli.py --smoke data                 # Data builder smoke test
  python trade_cli.py --smoke full                 # Full CLI smoke test

  # Play-based backtest (golden path):
  python trade_cli.py backtest run --play SOLUSDT_15m_ema_crossover
  python trade_cli.py backtest run --play SOLUSDT_15m_ema_crossover --smoke
  python trade_cli.py backtest preflight --play SOLUSDT_15m_ema_crossover
  python trade_cli.py backtest data-fix --play SOLUSDT_15m_ema_crossover
  python trade_cli.py backtest list
        """
    )

    parser.add_argument(
        "--smoke",
        choices=["data", "full", "data_extensive", "orders", "live_check", "backtest", "forge"],
        default=None,
        help="Run non-interactive smoke test. 'data'/'full'/'data_extensive'/'orders'/'backtest'/'forge' use DEMO. 'live_check' tests LIVE connectivity (opt-in, requires LIVE keys)."
    )

    parser.add_argument(
        "--fresh-db",
        action="store_true",
        default=False,
        help="For backtest smoke: wipe database before preparing data"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Enable debug logging with hash tracing (sets TRADE_DEBUG=1)"
    )

    # Add subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    _setup_backtest_subcommands(subparsers)
    _setup_play_subcommands(subparsers)
    _setup_test_subcommands(subparsers)
    _setup_validate_subcommand(subparsers)
    _setup_account_subcommands(subparsers)
    _setup_position_subcommands(subparsers)
    _setup_panic_subcommand(subparsers)

    return parser.parse_args()


def _setup_backtest_subcommands(subparsers) -> None:
    """Set up backtest subcommand and all its sub-subcommands."""
    backtest_parser = subparsers.add_parser("backtest", help="Play-based backtest (golden path)")
    backtest_subparsers = backtest_parser.add_subparsers(dest="backtest_command", help="Backtest commands")

    # backtest run
    run_parser = backtest_subparsers.add_parser("run", help="Run an Play backtest")
    run_parser.add_argument("--play", required=True, help="Play identifier (e.g., SOLUSDT_15m_ema_crossover)")
    run_parser.add_argument("--dir", dest="plays_dir", help="Override Play directory")
    run_parser.add_argument("--data-env", choices=["live", "demo"], default="live", help="Data environment (default: live)")
    run_parser.add_argument("--start", help="Window start (YYYY-MM-DD or YYYY-MM-DD HH:MM)")
    run_parser.add_argument("--end", help="Window end (YYYY-MM-DD or YYYY-MM-DD HH:MM)")
    run_parser.add_argument("--smoke", action="store_true", help="Smoke mode: fast wiring check with small window")
    run_parser.add_argument("--strict", action="store_true", default=True, help="Strict indicator access (default: True)")
    run_parser.add_argument("--no-strict", action="store_false", dest="strict", help="Disable strict indicator checks")
    run_parser.add_argument("--artifacts-dir", help="Override artifacts directory")
    run_parser.add_argument("--no-artifacts", action="store_true", help="Skip writing artifacts")
    run_parser.add_argument("--emit-snapshots", action="store_true", help="Emit snapshot artifacts (OHLCV + computed indicators)")
    run_parser.add_argument("--fix-gaps", action="store_true", default=True, help="Auto-fetch missing data (default: True)")
    run_parser.add_argument("--no-fix-gaps", action="store_false", dest="fix_gaps", help="Disable auto-fetch of missing data")
    run_parser.add_argument("--validate", action="store_true", default=True, help="Validate artifacts after run (default: True)")
    run_parser.add_argument("--no-validate", action="store_false", dest="validate", help="Skip artifact validation (faster, less safe)")
    run_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    # Synthetic data mode (for validation without DB)
    run_parser.add_argument("--synthetic", action="store_true", help="Use synthetic data instead of DB (for validation runs)")
    run_parser.add_argument("--synthetic-bars", type=int, default=1000, help="Number of bars per timeframe for synthetic data (default: 1000)")
    run_parser.add_argument("--synthetic-seed", type=int, default=42, help="Random seed for synthetic data generation (default: 42)")
    # Import available patterns from synthetic data module
    from src.forge.validation import PATTERN_GENERATORS
    run_parser.add_argument("--synthetic-pattern", choices=list(PATTERN_GENERATORS.keys()), default="trending", help="Pattern for synthetic data (default: trending). Use --list-patterns to see all.")

    # backtest preflight
    preflight_parser = backtest_subparsers.add_parser("preflight", help="Run preflight check without executing")
    preflight_parser.add_argument("--play", required=True, help="Play identifier")
    preflight_parser.add_argument("--data-env", choices=["live", "demo"], default="live", help="Data environment")
    preflight_parser.add_argument("--start", help="Window start")
    preflight_parser.add_argument("--end", help="Window end")
    preflight_parser.add_argument("--fix-gaps", action="store_true", help="Auto-fix data gaps using existing tools")
    preflight_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")

    # backtest indicators (indicator key discovery)
    indicators_parser = backtest_subparsers.add_parser("indicators", help="Discover indicator keys for an Play")
    indicators_parser.add_argument("--play", help="Play identifier (required unless --audit-math-from-snapshots)")
    indicators_parser.add_argument("--data-env", choices=["live", "demo"], default="live", help="Data environment")
    indicators_parser.add_argument("--print-keys", action="store_true", default=True, help="Print all indicator keys")
    indicators_parser.add_argument("--compute", action="store_true", help="Actually compute indicators (requires --start/--end)")
    indicators_parser.add_argument("--start", help="Window start (for --compute)")
    indicators_parser.add_argument("--end", help="Window end (for --compute)")
    indicators_parser.add_argument("--audit-math-from-snapshots", action="store_true", help="Audit math parity using snapshot artifacts")
    indicators_parser.add_argument("--run-dir", help="Run directory for --audit-math-from-snapshots")
    indicators_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")

    # Make --play required unless audit mode
    def validate_indicators_args(args):
        if not args.audit_math_from_snapshots and not args.play:
            indicators_parser.error("--play is required unless --audit-math-from-snapshots is used")
        if args.audit_math_from_snapshots and not args.run_dir:
            indicators_parser.error("--run-dir is required when using --audit-math-from-snapshots")

    # Store validator for later use
    indicators_parser._validate = validate_indicators_args

    # backtest data-fix
    datafix_parser = backtest_subparsers.add_parser("data-fix", help="Fix data for an Play")
    datafix_parser.add_argument("--play", required=True, help="Play identifier")
    datafix_parser.add_argument("--data-env", choices=["live", "demo"], default="live", help="Data environment")
    datafix_parser.add_argument("--start", help="Sync from this date")
    datafix_parser.add_argument("--sync-to-now", action="store_true", help="Sync data to current time")
    datafix_parser.add_argument("--fill-gaps", action="store_true", default=True, help="Fill gaps after sync")
    datafix_parser.add_argument("--heal", action="store_true", help="Run full heal after sync")
    datafix_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")

    # backtest list
    list_parser = backtest_subparsers.add_parser("list", help="List available Plays")
    list_parser.add_argument("--dir", dest="plays_dir", help="Override Plays directory")
    list_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")

    # backtest play-normalize (build-time validation)
    normalize_parser = backtest_subparsers.add_parser(
        "play-normalize",
        help="Validate and normalize an Play YAML (build-time)"
    )
    normalize_parser.add_argument("--play", required=True, help="Play identifier")
    normalize_parser.add_argument("--dir", dest="plays_dir", help="Override Plays directory")
    normalize_parser.add_argument("--write", action="store_true", help="Write normalized YAML in-place")
    normalize_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")

    # backtest play-normalize-batch (batch normalization)
    batch_normalize_parser = backtest_subparsers.add_parser(
        "play-normalize-batch",
        help="Batch validate and normalize all Plays in a directory"
    )
    batch_normalize_parser.add_argument("--dir", dest="plays_dir", required=True, help="Directory containing Play YAML files")
    batch_normalize_parser.add_argument("--write", action="store_true", help="Write normalized YAML in-place")
    batch_normalize_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")

    # backtest verify-suite (global verification suite)
    verify_suite_parser = backtest_subparsers.add_parser(
        "verify-suite",
        help="Run global indicator & strategy verification suite or artifact parity check"
    )
    # Standard verification mode (Play directory)
    verify_suite_parser.add_argument("--dir", dest="plays_dir", help="Directory containing verification Play YAML files")
    verify_suite_parser.add_argument("--data-env", choices=["live", "demo"], default="live", help="Data environment")
    verify_suite_parser.add_argument("--start", help="Fixed window start (YYYY-MM-DD)")
    verify_suite_parser.add_argument("--end", help="Fixed window end (YYYY-MM-DD)")
    verify_suite_parser.add_argument("--strict", action="store_true", default=True, help="Strict indicator access")
    verify_suite_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    verify_suite_parser.add_argument("--skip-toolkit-audit", action="store_true", help="Skip Gate 1 toolkit contract audit")
    # Phase 3.1: CSV vs Parquet parity verification mode
    verify_suite_parser.add_argument("--compare-csv-parquet", action="store_true", help="Verify CSV vs Parquet artifact parity")
    verify_suite_parser.add_argument("--play", dest="parity_play", help="Play ID for parity check")
    verify_suite_parser.add_argument("--symbol", dest="parity_symbol", help="Symbol for parity check")
    verify_suite_parser.add_argument("--run", dest="parity_run", help="Run ID (e.g., run-001 or 'latest')")

    # backtest audit-toolkit (indicator registry audit)
    audit_parser = backtest_subparsers.add_parser(
        "audit-toolkit",
        help="Run toolkit contract audit over all registry indicators"
    )
    audit_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    audit_parser.add_argument("--sample-bars", type=int, default=2000, help="Number of synthetic OHLCV bars (default: 2000)")
    audit_parser.add_argument("--seed", type=int, default=1337, help="Random seed for synthetic data (default: 1337)")
    audit_parser.add_argument("--fail-on-extras", action="store_true", help="Treat extras as failures")
    audit_parser.add_argument("--strict", action="store_true", default=True, help="Fail on any contract breach")

    # backtest audit-incremental-parity (G3-1 - incremental vs vectorized parity)
    inc_parity_parser = backtest_subparsers.add_parser(
        "audit-incremental-parity",
        help="Run G3-1 incremental vs vectorized indicator parity audit (11 indicators)"
    )
    inc_parity_parser.add_argument("--bars", type=int, default=1000, help="Number of synthetic bars (default: 1000)")
    inc_parity_parser.add_argument("--tolerance", type=float, default=1e-6, help="Max allowed difference (default: 1e-6)")
    inc_parity_parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)")
    inc_parity_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # backtest audit-structure-parity (Structure detector vectorized parity)
    struct_parity_parser = backtest_subparsers.add_parser(
        "audit-structure-parity",
        help="Run structure detector vectorized vs incremental parity audit (7 detectors)"
    )
    struct_parity_parser.add_argument("--bars", type=int, default=2000, help="Number of synthetic bars (default: 2000)")
    struct_parity_parser.add_argument("--tolerance", type=float, default=1e-10, help="Max allowed difference (default: 1e-10)")
    struct_parity_parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)")
    struct_parity_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # backtest metadata-smoke (Indicator Metadata v1 smoke test)
    metadata_parser = backtest_subparsers.add_parser(
        "metadata-smoke",
        help="Run Indicator Metadata v1 smoke test (validates metadata capture and export)"
    )
    metadata_parser.add_argument("--symbol", default="BTCUSDT", help="Symbol for synthetic data (default: BTCUSDT)")
    metadata_parser.add_argument("--tf", default="15m", help="Timeframe (default: 15m)")
    metadata_parser.add_argument("--sample-bars", type=int, default=2000, help="Number of synthetic bars (default: 2000)")
    metadata_parser.add_argument("--seed", type=int, default=1337, help="Random seed for reproducibility (default: 1337)")
    metadata_parser.add_argument("--export", dest="export_path", default="artifacts/indicator_metadata.jsonl", help="Export path (default: artifacts/indicator_metadata.jsonl)")
    metadata_parser.add_argument("--format", dest="export_format", choices=["jsonl", "json", "csv"], default="jsonl", help="Export format (default: jsonl)")

    # backtest mark-price-smoke (Mark Price Engine smoke test)
    mark_price_parser = backtest_subparsers.add_parser(
        "mark-price-smoke",
        help="Run Mark Price Engine smoke test (validates MarkPriceEngine and snapshot.get())"
    )
    mark_price_parser.add_argument("--sample-bars", type=int, default=500, help="Number of synthetic bars (default: 500)")
    mark_price_parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)")

    # backtest structure-smoke (Structure smoke test via production engine)
    structure_parser = backtest_subparsers.add_parser(
        "structure-smoke",
        help="Run structure smoke test (validates swing, trend, fibonacci, derived_zone via engine)"
    )
    structure_parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)")

    # backtest math-parity (contract audit + in-memory math parity)
    math_parity_parser = backtest_subparsers.add_parser(
        "math-parity",
        help="Validate indicator math parity (contract + in-memory comparison)"
    )
    math_parity_parser.add_argument("--play", required=True, help="Path to Play YAML for parity audit")
    math_parity_parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    math_parity_parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    math_parity_parser.add_argument("--output-dir", help="Output directory for diff reports (optional)")
    math_parity_parser.add_argument("--contract-sample-bars", type=int, default=2000, help="Synthetic bars for contract audit (default: 2000)")
    math_parity_parser.add_argument("--contract-seed", type=int, default=1337, help="Random seed for contract audit (default: 1337)")
    math_parity_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")

    # backtest audit-snapshot-plumbing (Phase 4 snapshot plumbing parity)
    plumbing_parser = backtest_subparsers.add_parser(
        "audit-snapshot-plumbing",
        help="Run Phase 4 snapshot plumbing parity audit"
    )
    plumbing_parser.add_argument("--play", required=True, help="Play identifier or path")
    plumbing_parser.add_argument("--symbol", help="Override symbol (optional, inferred from Play)")
    plumbing_parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    plumbing_parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    plumbing_parser.add_argument("--max-samples", type=int, default=2000, help="Max exec samples (default: 2000)")
    plumbing_parser.add_argument("--tolerance", type=float, default=1e-12, help="Tolerance for float comparison (default: 1e-12)")
    plumbing_parser.add_argument("--strict", action="store_true", default=True, help="Stop at first mismatch (default: True)")
    plumbing_parser.add_argument("--no-strict", action="store_false", dest="strict", help="Continue after mismatches")
    plumbing_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # backtest verify-determinism (Phase 3 - hash-based determinism verification)
    determinism_parser = backtest_subparsers.add_parser(
        "verify-determinism",
        help="Verify backtest determinism by comparing run hashes"
    )
    determinism_parser.add_argument("--run-a", required=False, help="Path to first run's artifact folder")
    determinism_parser.add_argument("--run-b", required=False, help="Path to second run's artifact folder (for compare mode)")
    determinism_parser.add_argument("--re-run", action="store_true", help="Re-run the Play and compare to existing run")
    determinism_parser.add_argument("--fix-gaps", action="store_true", default=False, help="Allow data sync during re-run")
    determinism_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")

    # backtest metrics-audit
    metrics_audit_parser = backtest_subparsers.add_parser(
        "metrics-audit",
        help="Validate financial metrics calculation (drawdown, Calmar, TF handling)"
    )
    metrics_audit_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")

    # backtest audit-rollup (1m rollup parity audit)
    rollup_parser = backtest_subparsers.add_parser(
        "audit-rollup",
        help="Run 1m rollup parity audit (ExecRollupBucket + snapshot accessors)"
    )
    rollup_parser.add_argument("--intervals", type=int, default=10, help="Number of exec intervals to test (default: 10)")
    rollup_parser.add_argument("--quotes", type=int, default=15, help="Quotes per interval (default: 15)")
    rollup_parser.add_argument("--seed", type=int, default=1337, help="Random seed (default: 1337)")
    rollup_parser.add_argument("--tolerance", type=float, default=1e-10, help="Tolerance (default: 1e-10)")
    rollup_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")


def _setup_play_subcommands(subparsers) -> None:
    """Set up play subcommand and all its sub-subcommands."""
    play_parser = subparsers.add_parser("play", help="Unified Play engine (all modes)")
    play_subparsers = play_parser.add_subparsers(dest="play_command", help="Play commands")

    # play run - Run Play in any mode
    play_run_parser = play_subparsers.add_parser("run", help="Run Play in specified mode")
    play_run_parser.add_argument("--play", required=True, help="Play identifier or YAML path")
    play_run_parser.add_argument(
        "--mode",
        choices=["backtest", "demo", "live", "shadow"],
        default="backtest",
        help="Execution mode (default: backtest)"
    )
    play_run_parser.add_argument("--dir", dest="plays_dir", help="Override Plays directory")
    play_run_parser.add_argument("--start", help="Window start (YYYY-MM-DD) for backtest")
    play_run_parser.add_argument("--end", help="Window end (YYYY-MM-DD) for backtest")
    play_run_parser.add_argument("--confirm", action="store_true", help="Confirm live trading (required for --mode live)")
    play_run_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")

    # play status - Check running instances (future)
    play_status_parser = play_subparsers.add_parser("status", help="Check running Play instances")
    play_status_parser.add_argument("--play", help="Filter by Play ID")
    play_status_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # play stop - Stop running instance (future)
    play_stop_parser = play_subparsers.add_parser("stop", help="Stop a running Play instance")
    play_stop_parser.add_argument("--play", help="Play ID to stop")
    play_stop_parser.add_argument("--force", action="store_true", help="Force stop (may leave positions open)")
    play_stop_parser.add_argument("--all", action="store_true", help="Stop all running instances")
    play_stop_parser.add_argument("--close-positions", action="store_true", help="Close all positions before stopping")

    # play watch - Live dashboard
    play_watch_parser = play_subparsers.add_parser("watch", help="Live dashboard for running instances")
    play_watch_parser.add_argument("--play", help="Filter to a specific Play instance")
    play_watch_parser.add_argument("--interval", type=float, default=2.0, help="Refresh interval in seconds (default: 2)")

    # play logs - Stream logs for running instance
    play_logs_parser = play_subparsers.add_parser("logs", help="Stream logs for a running instance")
    play_logs_parser.add_argument("--play", required=True, help="Play ID or instance ID")
    play_logs_parser.add_argument("--follow", "-f", action="store_true", help="Follow log output continuously")
    play_logs_parser.add_argument("--lines", "-n", type=int, default=50, help="Number of lines to show (default: 50)")

    # play pause - Pause a running instance
    play_pause_parser = play_subparsers.add_parser("pause", help="Pause signal evaluation (keeps receiving data)")
    play_pause_parser.add_argument("--play", required=True, help="Play ID or instance ID to pause")

    # play resume - Resume a paused instance
    play_resume_parser = play_subparsers.add_parser("resume", help="Resume a paused instance")
    play_resume_parser.add_argument("--play", required=True, help="Play ID or instance ID to resume")


def _setup_test_subcommands(subparsers) -> None:
    """Set up test subcommand and all its sub-subcommands."""
    test_parser = subparsers.add_parser("test", help="Indicator validation testing agent")
    test_subparsers = test_parser.add_subparsers(dest="test_command", help="Test commands")

    # test indicators - Run indicator test suite
    test_indicators_parser = test_subparsers.add_parser("indicators", help="Run indicator validation suite")
    test_indicators_parser.add_argument("--symbol", default="BTCUSDT", help="Symbol to test (default: BTCUSDT)")
    test_indicators_parser.add_argument("--tier", choices=["tier19", "tier20", "tier21", "tier22", "tier23", "tier24", "tier25"], help="Run specific tier only")
    test_indicators_parser.add_argument("--condition", choices=["bull", "bear", "range", "volatile"], help="Market condition filter")
    test_indicators_parser.add_argument("--fix-gaps", action="store_true", default=True, help="Auto-fetch missing data (default: True)")
    test_indicators_parser.add_argument("--no-fix-gaps", action="store_false", dest="fix_gaps", help="Disable auto-fetch")
    test_indicators_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # test parity - Run incremental vs vectorized parity
    test_parity_parser = test_subparsers.add_parser("parity", help="Incremental vs vectorized parity check")
    test_parity_parser.add_argument("--bars", type=int, default=2000, help="Number of synthetic bars (default: 2000)")
    test_parity_parser.add_argument("--tolerance", type=float, default=1e-6, help="Max allowed difference (default: 1e-6)")
    test_parity_parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    test_parity_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # test live-parity - Live vs backtest comparison
    test_live_parity_parser = test_subparsers.add_parser("live-parity", help="Live vs backtest parity check")
    test_live_parity_parser.add_argument("--tier", choices=["tier19", "tier20", "tier21", "tier22", "tier23", "tier24", "tier25"], default="tier19", help="Tier to test (default: tier19)")
    test_live_parity_parser.add_argument("--fix-gaps", action="store_true", default=True, help="Auto-fetch missing data")
    test_live_parity_parser.add_argument("--no-fix-gaps", action="store_false", dest="fix_gaps", help="Disable auto-fetch")
    test_live_parity_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # test agent - Full testing agent
    test_agent_parser = test_subparsers.add_parser("agent", help="Run full testing agent")
    test_agent_parser.add_argument("--mode", choices=["full", "btc", "l2"], default="full", help="Agent mode (default: full)")
    test_agent_parser.add_argument("--fix-gaps", action="store_true", default=True, help="Auto-fetch missing data")
    test_agent_parser.add_argument("--no-fix-gaps", action="store_false", dest="fix_gaps", help="Disable auto-fetch")
    test_agent_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")


def _setup_validate_subcommand(subparsers) -> None:
    """Set up validate subcommand for unified validation."""
    validate_parser = subparsers.add_parser(
        "validate",
        help="Unified validation suite (quick/standard/full/pre-live)"
    )
    validate_parser.add_argument(
        "tier",
        choices=["quick", "standard", "full", "pre-live"],
        help="Validation tier: quick (~10s), standard (~2min), full (~10min), pre-live (readiness gate)"
    )
    validate_parser.add_argument(
        "--play",
        help="Play identifier (required for pre-live tier)"
    )
    validate_parser.add_argument(
        "--no-fail-fast",
        action="store_true",
        help="Run all gates even if one fails (default: stop on first failure)"
    )
    validate_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON"
    )


def _setup_account_subcommands(subparsers) -> None:
    """Set up account subcommand."""
    account_parser = subparsers.add_parser("account", help="Account information")
    account_subparsers = account_parser.add_subparsers(dest="account_command", help="Account commands")

    # account balance
    balance_parser = account_subparsers.add_parser("balance", help="Show account balance")
    balance_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # account exposure
    exposure_parser = account_subparsers.add_parser("exposure", help="Show total exposure")
    exposure_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")


def _setup_position_subcommands(subparsers) -> None:
    """Set up position subcommand."""
    position_parser = subparsers.add_parser("position", help="Position management")
    position_subparsers = position_parser.add_subparsers(dest="position_command", help="Position commands")

    # position list
    list_parser = position_subparsers.add_parser("list", help="List open positions")
    list_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # position close
    close_parser = position_subparsers.add_parser("close", help="Close a position")
    close_parser.add_argument("symbol", help="Symbol to close (e.g., BTCUSDT)")


def _setup_panic_subcommand(subparsers) -> None:
    """Set up panic subcommand."""
    panic_parser = subparsers.add_parser("panic", help="Emergency: cancel all orders and close all positions")
    panic_parser.add_argument("--confirm", action="store_true", help="Required confirmation flag")
