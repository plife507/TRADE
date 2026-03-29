"""
Argument parser setup for TRADE CLI.

Defines all subcommands and their arguments:
- backtest: Play-based backtesting (run, preflight, indicators, data-fix, list, normalize)
- play: Unified Play engine (backtest/demo/live/shadow)
- validate: Unified validation suite (quick/standard/full/pre-live/exchange)
- debug: Diagnostic tools (math-parity, snapshot-plumbing, determinism, metrics)
"""

import argparse


def setup_argparse() -> argparse.Namespace:
    """
    Parse command-line arguments for trade_cli.

    Supports:
      validate quick       Run quick validation (~10s)
      validate standard    Run standard validation (~2min)
      validate full        Run full validation (~10min)
      validate exchange    Run exchange integration tests (~30s)

      backtest run         Run Play-based backtest (golden path)
      backtest preflight   Check data/config without running
      backtest data-fix    Fix data gaps/coverage
      backtest list        List available Plays

      debug math-parity    Per-play real-data math verification
      debug snapshot-plumbing  Snapshot field correctness
      debug determinism    Compare two specific run hashes
      debug metrics        Standalone metrics audit
    """
    parser = argparse.ArgumentParser(
        description="TRADE - Bybit Unified Trading Account CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python trade_cli.py                              # Interactive mode (default)
  python trade_cli.py validate quick               # Quick validation (~10s)
  python trade_cli.py validate exchange             # Exchange integration tests

  # Play-based backtest (golden path):
  python trade_cli.py backtest run --play SOLUSDT_15m_ema_crossover
  python trade_cli.py backtest preflight --play SOLUSDT_15m_ema_crossover

  # Debug tools:
  python trade_cli.py debug math-parity --play X --start 2025-01-01 --end 2025-06-30
  python trade_cli.py debug determinism --run-a A --run-b B
        """
    )

    # Verbosity: mutually exclusive group (-q / -v / --debug)
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "-q", "--quiet",
        action="store_true",
        default=False,
        help="Quiet mode: WARNING only, minimal output"
    )
    verbosity.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=False,
        help="Verbose mode: INFO + signal evaluation traces"
    )
    verbosity.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Debug mode: full DEBUG + hash tracing (sets TRADE_DEBUG=1)"
    )

    # Add subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    _setup_backtest_subcommands(subparsers)
    _setup_play_subcommands(subparsers)
    _setup_validate_subcommand(subparsers)
    _setup_debug_subcommands(subparsers)
    _setup_account_subcommands(subparsers)
    _setup_position_subcommands(subparsers)
    _setup_panic_subcommand(subparsers)
    _setup_order_subcommands(subparsers)
    _setup_data_subcommands(subparsers)
    _setup_market_subcommands(subparsers)
    _setup_health_subcommands(subparsers)
    _setup_shadow_subcommands(subparsers)

    return parser.parse_args()


def _setup_backtest_subcommands(subparsers) -> None:
    """Set up backtest subcommand and all its sub-subcommands (operational only)."""
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
    run_parser.add_argument("--artifacts-dir", help="Override artifacts directory")
    run_parser.add_argument("--no-artifacts", action="store_true", help="Skip writing artifacts")
    run_parser.add_argument("--emit-snapshots", action="store_true", help="Emit snapshot artifacts (OHLCV + computed indicators)")
    run_parser.add_argument("--sync", action="store_true", default=True, help="Auto-fetch missing data (default: True)")
    run_parser.add_argument("--no-sync", action="store_false", dest="sync", help="Disable auto-fetch of missing data")
    run_parser.add_argument("--validate", action="store_true", default=True, help="Validate artifacts after run (default: True)")
    run_parser.add_argument("--no-validate", action="store_false", dest="validate", help="Skip artifact validation (faster, less safe)")
    run_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")
    run_parser.add_argument("--json-verbose", action="store_true", dest="json_verbose", help="Include full metrics, hashes, and artifact path in JSON output")
    # Synthetic data mode (for validation without DB)
    run_parser.add_argument("--synthetic", action="store_true", help="Use synthetic data from play's synthetic: block (required). Fails if block missing.")
    run_parser.add_argument("--synthetic-bars", type=int, default=None, help="Override bars per TF from play's synthetic.bars")
    run_parser.add_argument("--synthetic-seed", type=int, default=None, help="Override seed from play's synthetic.seed")
    # Import available patterns from synthetic data module
    from src.forge.validation import PATTERN_GENERATORS
    run_parser.add_argument("--synthetic-pattern", choices=list(PATTERN_GENERATORS.keys()), default=None, help="Override pattern from play's synthetic.pattern")
    run_parser.add_argument("--trace", action="store_true", default=False, dest="engine_trace", help="Enable verbose engine tracing (bar OHLCV, signal results, position changes)")

    # backtest preflight
    preflight_parser = backtest_subparsers.add_parser("preflight", help="Run preflight check without executing")
    preflight_parser.add_argument("--play", required=True, help="Play identifier")
    preflight_parser.add_argument("--data-env", choices=["live", "demo"], default="live", help="Data environment")
    preflight_parser.add_argument("--start", help="Window start")
    preflight_parser.add_argument("--end", help="Window end")
    preflight_parser.add_argument("--sync", action="store_true", help="Auto-sync missing data using existing tools")
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

    # Propagate validator to Namespace via set_defaults (not direct attribute)
    indicators_parser.set_defaults(_validate=validate_indicators_args)

    # backtest data-fix
    datafix_parser = backtest_subparsers.add_parser("data-fix", help="Fix data for an Play")
    datafix_parser.add_argument("--play", required=True, help="Play identifier")
    datafix_parser.add_argument("--data-env", choices=["live", "demo"], default="live", help="Data environment")
    datafix_parser.add_argument("--start", help="Sync from this date")
    datafix_parser.add_argument("--sync-to-now", action="store_true", help="Sync data to current time")
    datafix_parser.add_argument("--sync", action="store_true", default=True, help="Sync gaps after range sync")
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
    play_run_parser.add_argument("--headless", action="store_true",
        help="Run without Rich dashboard (for agents/scripts). Outputs instance JSON and blocks until stopped.")
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
    play_watch_parser.add_argument("--json", action="store_true", dest="json_output",
        help="Output single JSON snapshot and exit (no live dashboard)")

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


def _setup_validate_subcommand(subparsers) -> None:
    """Set up validate subcommand for unified validation."""
    from src.cli.validate import MODULE_NAMES

    validate_parser = subparsers.add_parser(
        "validate",
        help="Unified validation suite (quick/standard/full/real/module/pre-live/exchange)"
    )
    validate_parser.add_argument(
        "tier",
        choices=["quick", "standard", "full", "real", "module", "pre-live", "exchange"],
        help="Validation tier: quick (~7s), standard (~20s), full (~50s), real (~2min), module (single module), pre-live, exchange (~30s)"
    )
    validate_parser.add_argument(
        "--play",
        help="Play identifier (required for pre-live tier)"
    )
    validate_parser.add_argument(
        "--module",
        choices=MODULE_NAMES,
        help="Module name (required for module tier)"
    )
    validate_parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Max parallel workers for play suites (default: cpu_count - 1)"
    )
    validate_parser.add_argument(
        "--no-fail-fast",
        action="store_true",
        help="Run all gates even if one fails (default: stop on first failure)"
    )
    validate_parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Per-play timeout in seconds (default: 120). Hung plays fail instead of blocking."
    )
    validate_parser.add_argument(
        "--gate-timeout",
        type=int,
        default=600,
        help="Per-gate timeout in seconds for concurrent stages (default: 600)."
    )
    validate_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON"
    )


def _setup_debug_subcommands(subparsers) -> None:
    """Set up debug subcommand for diagnostic tools."""
    debug_parser = subparsers.add_parser("debug", help="Diagnostic tools (math-parity, snapshot, determinism, metrics)")
    debug_subparsers = debug_parser.add_subparsers(dest="debug_command", help="Debug commands")

    # debug math-parity
    math_parity_parser = debug_subparsers.add_parser(
        "math-parity",
        help="Validate indicator math parity (contract + in-memory comparison)"
    )
    math_parity_parser.add_argument("--play", required=True, help="Play identifier for parity audit")
    math_parity_parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    math_parity_parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    math_parity_parser.add_argument("--output-dir", help="Output directory for diff reports (optional)")
    math_parity_parser.add_argument("--contract-sample-bars", type=int, default=2000, help="Synthetic bars for contract audit (default: 2000)")
    math_parity_parser.add_argument("--contract-seed", type=int, default=1337, help="Random seed for contract audit (default: 1337)")
    math_parity_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")

    # debug snapshot-plumbing
    plumbing_parser = debug_subparsers.add_parser(
        "snapshot-plumbing",
        help="Run snapshot plumbing parity audit"
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

    # debug determinism
    determinism_parser = debug_subparsers.add_parser(
        "determinism",
        help="Verify backtest determinism by comparing run hashes"
    )
    determinism_parser.add_argument("--run-a", required=False, help="Path to first run's artifact folder")
    determinism_parser.add_argument("--run-b", required=False, help="Path to second run's artifact folder (for compare mode)")
    determinism_parser.add_argument("--re-run", action="store_true", help="Re-run the Play and compare to existing run")
    determinism_parser.add_argument("--sync", action="store_true", default=False, help="Allow data sync during re-run")
    determinism_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")

    # debug metrics
    metrics_parser = debug_subparsers.add_parser(
        "metrics",
        help="Validate financial metrics calculation (drawdown, Calmar, TF handling)"
    )
    metrics_parser.add_argument("--json", action="store_true", dest="json_output", help="Output results as JSON")


def _setup_account_subcommands(subparsers) -> None:
    """Set up account subcommand."""
    account_parser = subparsers.add_parser("account", help="Account information and history")
    account_subparsers = account_parser.add_subparsers(dest="account_command", help="Account commands")

    # account balance
    balance_parser = account_subparsers.add_parser("balance", help="Show account balance")
    balance_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # account exposure
    exposure_parser = account_subparsers.add_parser("exposure", help="Show total exposure")
    exposure_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # account info
    info_parser = account_subparsers.add_parser("info", help="Show account config (margin mode, etc.)")
    info_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # account history
    history_parser = account_subparsers.add_parser("history", help="Order history")
    history_parser.add_argument("--days", type=int, help="Number of days to look back (default: 7)")
    history_parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    history_parser.add_argument("--end", help="End date (YYYY-MM-DD)")
    history_parser.add_argument("--symbol", help="Filter by symbol")
    history_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # account pnl
    pnl_parser = account_subparsers.add_parser("pnl", help="Closed P&L history")
    pnl_parser.add_argument("--days", type=int, help="Number of days to look back (default: 7)")
    pnl_parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    pnl_parser.add_argument("--end", help="End date (YYYY-MM-DD)")
    pnl_parser.add_argument("--symbol", help="Filter by symbol")
    pnl_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # account transactions
    tx_parser = account_subparsers.add_parser("transactions", help="Transaction log")
    tx_parser.add_argument("--days", type=int, help="Number of days to look back (default: 7)")
    tx_parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    tx_parser.add_argument("--end", help="End date (YYYY-MM-DD)")
    tx_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # account collateral
    collateral_parser = account_subparsers.add_parser("collateral", help="Collateral information")
    collateral_parser.add_argument("--currency", help="Filter by currency (e.g., USDT)")
    collateral_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")


def _setup_position_subcommands(subparsers) -> None:
    """Set up position subcommand."""
    position_parser = subparsers.add_parser("position", help="Position management and configuration")
    position_subparsers = position_parser.add_subparsers(dest="position_command", help="Position commands")

    # position list
    list_parser = position_subparsers.add_parser("list", help="List open positions")
    list_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # position close
    close_parser = position_subparsers.add_parser("close", help="Close a position")
    close_parser.add_argument("symbol", help="Symbol to close (e.g., BTCUSDT)")

    # position detail
    detail_parser = position_subparsers.add_parser("detail", help="Get detailed position info")
    detail_parser.add_argument("--symbol", required=True, help="Trading symbol")
    detail_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # position set-tp
    tp_parser = position_subparsers.add_parser("set-tp", help="Set take profit on position")
    tp_parser.add_argument("--symbol", required=True, help="Trading symbol")
    tp_parser.add_argument("--price", type=float, required=True, help="Take profit price")
    tp_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # position set-sl
    sl_parser = position_subparsers.add_parser("set-sl", help="Set stop loss on position")
    sl_parser.add_argument("--symbol", required=True, help="Trading symbol")
    sl_parser.add_argument("--price", type=float, required=True, help="Stop loss price")
    sl_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # position set-tpsl
    tpsl_parser = position_subparsers.add_parser("set-tpsl", help="Set both TP and SL on position")
    tpsl_parser.add_argument("--symbol", required=True, help="Trading symbol")
    tpsl_parser.add_argument("--tp", type=float, help="Take profit price")
    tpsl_parser.add_argument("--sl", type=float, help="Stop loss price")
    tpsl_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # position trailing
    trailing_parser = position_subparsers.add_parser("trailing", help="Set trailing stop on position")
    trailing_parser.add_argument("--symbol", required=True, help="Trading symbol")
    trailing_parser.add_argument("--distance", type=float, required=True, help="Trailing distance in price units (0 to remove)")
    trailing_parser.add_argument("--active-price", type=float, help="Price at which trailing activates")
    trailing_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # position partial-close
    partial_parser = position_subparsers.add_parser("partial-close", help="Partially close a position")
    partial_parser.add_argument("--symbol", required=True, help="Trading symbol")
    partial_parser.add_argument("--percent", type=float, required=True, help="Percentage to close (1-100)")
    partial_parser.add_argument("--price", type=float, help="Limit price (omit for market)")
    partial_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # position margin
    margin_parser = position_subparsers.add_parser("margin", help="Switch margin mode for symbol")
    margin_parser.add_argument("--symbol", required=True, help="Trading symbol")
    margin_parser.add_argument("--mode", required=True, choices=["cross", "isolated"], help="Margin mode")
    margin_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # position risk-limit
    rl_parser = position_subparsers.add_parser("risk-limit", help="Set risk limit for symbol")
    rl_parser.add_argument("--symbol", required=True, help="Trading symbol")
    rl_parser.add_argument("--id", type=int, required=True, help="Risk limit ID")
    rl_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")


def _setup_panic_subcommand(subparsers) -> None:
    """Set up panic subcommand."""
    panic_parser = subparsers.add_parser("panic", help="Emergency: cancel all orders and close all positions")
    panic_parser.add_argument("--confirm", action="store_true", help="Required confirmation flag")


def _setup_order_subcommands(subparsers) -> None:
    """Set up order subcommand group for non-interactive order management."""
    order_parser = subparsers.add_parser("order", help="Order management (buy/sell/list/amend/cancel)")
    order_subparsers = order_parser.add_subparsers(dest="order_command", help="Order commands")

    # Shared order flags (used by buy and sell)
    def _add_order_flags(p) -> None:
        p.add_argument("--symbol", required=True, help="Trading symbol (e.g., BTCUSDT)")
        p.add_argument("--amount", type=float, required=True, help="Position size in USD")
        p.add_argument("--type", required=True, choices=["market", "limit", "stop", "stop-limit"], help="Order type")
        p.add_argument("--price", type=float, help="Limit price (required for limit/stop-limit)")
        p.add_argument("--trigger", type=float, help="Trigger price (required for stop/stop-limit)")
        p.add_argument("--tp", type=float, help="Take profit price")
        p.add_argument("--sl", type=float, help="Stop loss price")
        p.add_argument("--tif", default="GTC", choices=["GTC", "IOC", "FOK", "PostOnly"], help="Time in force (default: GTC)")
        p.add_argument("--reduce-only", action="store_true", help="Reduce-only order")
        p.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # order buy
    buy_parser = order_subparsers.add_parser("buy", help="Place a buy order")
    _add_order_flags(buy_parser)

    # order sell
    sell_parser = order_subparsers.add_parser("sell", help="Place a sell order")
    _add_order_flags(sell_parser)

    # order list
    list_parser = order_subparsers.add_parser("list", help="List open orders")
    list_parser.add_argument("--symbol", help="Filter by symbol")
    list_parser.add_argument("--filter", choices=["Order", "StopOrder"], help="Filter by order type")
    list_parser.add_argument("--limit", type=int, default=50, help="Max orders to return (default: 50)")
    list_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # order amend
    amend_parser = order_subparsers.add_parser("amend", help="Amend an existing order")
    amend_parser.add_argument("--symbol", required=True, help="Trading symbol")
    amend_parser.add_argument("--order-id", required=True, help="Order ID to amend")
    amend_parser.add_argument("--qty", type=float, help="New quantity")
    amend_parser.add_argument("--price", type=float, help="New price")
    amend_parser.add_argument("--tp", type=float, help="New take profit")
    amend_parser.add_argument("--sl", type=float, help="New stop loss")
    amend_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # order cancel
    cancel_parser = order_subparsers.add_parser("cancel", help="Cancel a specific order")
    cancel_parser.add_argument("--symbol", required=True, help="Trading symbol")
    cancel_parser.add_argument("--order-id", required=True, help="Order ID to cancel")
    cancel_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # order cancel-all
    cancel_all_parser = order_subparsers.add_parser("cancel-all", help="Cancel all open orders")
    cancel_all_parser.add_argument("--symbol", help="Filter by symbol (omit for all)")
    cancel_all_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # order leverage
    leverage_parser = order_subparsers.add_parser("leverage", help="Set leverage for a symbol")
    leverage_parser.add_argument("--symbol", required=True, help="Trading symbol")
    leverage_parser.add_argument("--leverage", type=int, required=True, help="Leverage value (1-125)")
    leverage_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # order batch
    batch_parser = order_subparsers.add_parser("batch", help="Place batch orders from JSON file")
    batch_parser.add_argument("--file", required=True, help="Path to JSON file with order array")
    batch_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")


def _setup_data_subcommands(subparsers) -> None:
    """Set up data subcommand group for historical data management."""
    data_parser = subparsers.add_parser("data", help="Historical data management (DuckDB)")
    data_subparsers = data_parser.add_subparsers(dest="data_command", help="Data commands")

    # data sync
    sync_parser = data_subparsers.add_parser("sync", help="Sync historical data for symbols")
    sync_parser.add_argument("--symbols", required=True, help="Comma-separated symbols (e.g., BTCUSDT,ETHUSDT)")
    sync_parser.add_argument("--period", default="30d", help="Period to sync (e.g., 7d, 30d, 3M, 1Y). Default: 30d")
    sync_parser.add_argument("--start", help="Start date (YYYY-MM-DD) — overrides --period")
    sync_parser.add_argument("--end", help="End date (YYYY-MM-DD) — overrides --period")
    sync_parser.add_argument("--heal", action="store_true", help="Run heal after sync")
    sync_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # data info
    info_parser = data_subparsers.add_parser("info", help="Show database statistics")
    info_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # data symbols
    symbols_parser = data_subparsers.add_parser("symbols", help="List cached symbols")
    symbols_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # data status
    status_parser = data_subparsers.add_parser("status", help="Show status for a symbol")
    status_parser.add_argument("--symbol", required=True, help="Symbol to check")
    status_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # data summary
    summary_parser = data_subparsers.add_parser("summary", help="Show symbol summary across all cached data")
    summary_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # data query
    query_parser = data_subparsers.add_parser("query", help="Query OHLCV history from DuckDB")
    query_parser.add_argument("--symbol", required=True, help="Symbol to query")
    query_parser.add_argument("--tf", default="1m", help="Timeframe (default: 1m)")
    query_parser.add_argument("--period", help="Relative period (e.g., 7d, 30d)")
    query_parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    query_parser.add_argument("--end", help="End date (YYYY-MM-DD)")
    query_parser.add_argument("--limit", type=int, help="Max rows to return")
    query_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # data heal
    heal_parser = data_subparsers.add_parser("heal", help="Check and repair data integrity")
    heal_parser.add_argument("--symbol", help="Symbol to heal (omit for all)")
    heal_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # data vacuum
    vacuum_parser = data_subparsers.add_parser("vacuum", help="Vacuum the DuckDB database")
    vacuum_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # data delete
    delete_parser = data_subparsers.add_parser("delete", help="Delete all data for a symbol")
    delete_parser.add_argument("--symbol", required=True, help="Symbol to delete")
    delete_parser.add_argument("--confirm", action="store_true", required=True, help="Required confirmation flag")
    delete_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")


def _setup_market_subcommands(subparsers) -> None:
    """Set up market data subcommand group for live market queries."""
    market_parser = subparsers.add_parser("market", help="Live market data (prices, OHLCV, funding, orderbook)")
    market_subparsers = market_parser.add_subparsers(dest="market_command", help="Market data commands")

    # market price
    price_parser = market_subparsers.add_parser("price", help="Get current price")
    price_parser.add_argument("--symbol", required=True, help="Trading symbol")
    price_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # market ohlcv
    ohlcv_parser = market_subparsers.add_parser("ohlcv", help="Get OHLCV candlestick data")
    ohlcv_parser.add_argument("--symbol", required=True, help="Trading symbol")
    ohlcv_parser.add_argument("--tf", default="15", help="Timeframe interval (e.g., 1, 5, 15, 60, 240, D). Default: 15")
    ohlcv_parser.add_argument("--limit", type=int, default=100, help="Number of candles (default: 100)")
    ohlcv_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # market funding
    funding_parser = market_subparsers.add_parser("funding", help="Get funding rate")
    funding_parser.add_argument("--symbol", required=True, help="Trading symbol")
    funding_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # market oi
    oi_parser = market_subparsers.add_parser("oi", help="Get open interest")
    oi_parser.add_argument("--symbol", required=True, help="Trading symbol")
    oi_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # market orderbook
    ob_parser = market_subparsers.add_parser("orderbook", help="Get orderbook depth")
    ob_parser.add_argument("--symbol", required=True, help="Trading symbol")
    ob_parser.add_argument("--depth", type=int, default=25, help="Depth per side (default: 25)")
    ob_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # market instruments
    inst_parser = market_subparsers.add_parser("instruments", help="Get instrument info")
    inst_parser.add_argument("--symbol", help="Specific symbol (omit for all)")
    inst_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")


def _setup_health_subcommands(subparsers) -> None:
    """Set up health & diagnostics subcommand group."""
    health_parser = subparsers.add_parser("health", help="System health & diagnostics")
    health_subparsers = health_parser.add_subparsers(dest="health_command", help="Health commands")

    # health check
    check_parser = health_subparsers.add_parser("check", help="Comprehensive exchange health check")
    check_parser.add_argument("--symbol", default="BTCUSDT", help="Symbol for testing (default: BTCUSDT)")
    check_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # health connection
    conn_parser = health_subparsers.add_parser("connection", help="Test exchange connectivity")
    conn_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # health rate-limit
    rl_parser = health_subparsers.add_parser("rate-limit", help="Check rate limit status")
    rl_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # health ws
    ws_parser = health_subparsers.add_parser("ws", help="WebSocket connection status")
    ws_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    # health environment
    env_parser = health_subparsers.add_parser("environment", help="Show API environment configuration")
    env_parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")


def _setup_shadow_subcommands(subparsers) -> None:
    """Shadow Exchange — multi-play paper trading with SimExchange + real WS data."""
    shadow_parser = subparsers.add_parser("shadow", help="Shadow Exchange (M4) — paper trading")
    shadow_subparsers = shadow_parser.add_subparsers(dest="shadow_command", help="Shadow commands")

    # shadow run --play X  (single play, foreground)
    run_parser = shadow_subparsers.add_parser("run", help="Run a single play in shadow mode")
    run_parser.add_argument("--play", required=True, help="Play name or path")
    run_parser.add_argument("--equity", type=float, default=10000.0, help="Starting equity (USDT)")
    run_parser.add_argument("--plays-dir", help="Directory to search for plays")
    run_parser.add_argument("--json", action="store_true", dest="json_output", help="JSON output")

    # shadow add --play X  (add to orchestrator)
    add_parser = shadow_subparsers.add_parser("add", help="Add a play to the shadow exchange")
    add_parser.add_argument("--play", required=True, help="Play name or path")
    add_parser.add_argument("--equity", type=float, default=10000.0, help="Starting equity (USDT)")
    add_parser.add_argument("--plays-dir", help="Directory to search for plays")

    # shadow remove --instance X
    remove_parser = shadow_subparsers.add_parser("remove", help="Remove a play from shadow exchange")
    remove_parser.add_argument("--instance", required=True, help="Instance ID to remove")

    # shadow list
    list_parser = shadow_subparsers.add_parser("list", help="List all shadow plays")
    list_parser.add_argument("--json", action="store_true", dest="json_output", help="JSON output")

    # shadow stats --instance X | --all
    stats_parser = shadow_subparsers.add_parser("stats", help="Show shadow play stats")
    stats_group = stats_parser.add_mutually_exclusive_group(required=True)
    stats_group.add_argument("--instance", help="Instance ID")
    stats_group.add_argument("--all", action="store_true", help="All plays")
    stats_parser.add_argument("--json", action="store_true", dest="json_output", help="JSON output")

    # shadow daemon  (always-on mode for VPS)
    daemon_parser = shadow_subparsers.add_parser("daemon", help="Run shadow daemon (always-on, VPS)")
    daemon_parser.add_argument("--config", default="config/shadow.yml", help="Config file path")
