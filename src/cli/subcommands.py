"""
Subcommand handlers for TRADE CLI.

All handle_* functions are module-level and accept an `args` namespace.
They are dispatched from main() in trade_cli.py.

Sections:
- Backtest handlers (handle_backtest_*)
- Viz handlers (handle_viz_*)
- Play handlers (handle_play_*)
- QA handlers (handle_qa_*)
- Test handlers (handle_test_*)
"""

from rich.panel import Panel
from rich.table import Table

from src.cli.utils import console, BACK


# =============================================================================
# SHARED HELPERS
# =============================================================================

def _parse_datetime(dt_str: str) -> "datetime":
    """Parse datetime string from CLI."""
    from datetime import datetime

    for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"]:
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue

    raise ValueError(f"Cannot parse datetime: '{dt_str}'. Use YYYY-MM-DD or YYYY-MM-DD HH:MM")


def _print_preflight_diagnostics(diag: dict):
    """Print preflight diagnostics in a formatted way.

    Reads from PreflightReport.to_dict() structure:
    - play_id, window, overall_status, tf_results, coverage, etc.
    """
    table = Table(title="Preflight Diagnostics", show_header=False, box=None)
    table.add_column("Key", style="dim", width=25)
    table.add_column("Value", style="bold")

    play_id = diag.get("play_id", "N/A")
    overall_status = diag.get("overall_status", "N/A")

    tf_results = diag.get("tf_results", {})
    first_tf_result = next(iter(tf_results.values()), {}) if tf_results else {}
    symbol = first_tf_result.get("symbol", "N/A")
    exec_tf = first_tf_result.get("tf", "N/A")

    table.add_row("Play", play_id)
    table.add_row("Symbol", symbol)
    table.add_row("Exec TF", exec_tf)
    table.add_row("Status", overall_status)

    console.print(table)

    # Window info
    console.print("\n[bold]Window:[/]")
    window = diag.get("window", {})
    if window.get("start"):
        console.print(f"  Requested: {window['start']} -> {window.get('end', 'now')}")

    warmup_req = diag.get("computed_warmup_requirements", {})
    warmup_bars = warmup_req.get("warmup_bars_exec", 0) if warmup_req else 0
    if not warmup_bars and first_tf_result:
        req_range = first_tf_result.get("required_range", {})
        warmup_bars = req_range.get("warmup_bars", 0)
    console.print(f"  Warmup: {warmup_bars} bars")

    # Coverage from first TF result
    console.print("\n[bold]DB Coverage:[/]")
    coverage = first_tf_result.get("coverage", {})
    min_ts = coverage.get("min_ts")
    max_ts = coverage.get("max_ts")
    bar_count = coverage.get("bar_count", 0)

    if min_ts and max_ts:
        console.print(f"  Range: {min_ts} -> {max_ts}")
        console.print(f"  Bars: {bar_count:,}")
    else:
        console.print("  [yellow]No data found[/]")

    coverage_ok = coverage.get("ok", False)
    coverage_style = "green" if coverage_ok else "red"
    console.print(f"  Sufficient: [{coverage_style}]{'Yes' if coverage_ok else 'No'}[/]")

    if diag.get("error_code"):
        console.print(f"  [yellow]Error: {diag['error_code']}[/]")

    errors = first_tf_result.get("errors", [])
    if errors:
        console.print("\n[bold red]Validation Errors:[/]")
        for err in errors:
            console.print(f"  [red]- {err}[/]")

    warnings = first_tf_result.get("warnings", [])
    if warnings:
        console.print("\n[bold yellow]Warnings:[/]")
        for warn in warnings:
            console.print(f"  [yellow]- {warn}[/]")


# =============================================================================
# BACKTEST SUBCOMMAND HANDLERS
# =============================================================================

def _handle_synthetic_backtest_run(args) -> int:
    """Handle synthetic backtest run (no DB access)."""
    import json
    import yaml
    from pathlib import Path
    from src.backtest.play import load_play, Play
    from src.backtest.runner import run_backtest_with_gates, RunnerConfig
    from src.forge.validation import generate_synthetic_candles
    from src.forge.validation.synthetic_provider import SyntheticCandlesProvider

    plays_dir = Path(args.plays_dir) if getattr(args, "plays_dir", None) else None
    synthetic_bars = getattr(args, "synthetic_bars", 1000)
    synthetic_seed = getattr(args, "synthetic_seed", 42)
    synthetic_pattern = getattr(args, "synthetic_pattern", "trending")

    # Load Play - check if it's a file path first
    play_path = Path(args.play)
    if play_path.exists() and play_path.is_file():
        with open(play_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        play = Play.from_dict(raw)
    else:
        play = load_play(args.play, base_dir=plays_dir)
    exec_tf = play.execution_tf
    required_tfs = {exec_tf, "1m"}  # Always need 1m for intrabar

    # Add Play's declared timeframes (low_tf, med_tf, high_tf)
    if play.low_tf:
        required_tfs.add(play.low_tf)
    if play.med_tf:
        required_tfs.add(play.med_tf)
    if play.high_tf:
        required_tfs.add(play.high_tf)

    # Collect TFs from features
    for f in play.features or []:
        if hasattr(f, "tf") and f.tf:
            required_tfs.add(f.tf)

    if not getattr(args, "json_output", False):
        console.print(Panel(
            f"[bold cyan]BACKTEST RUN (SYNTHETIC)[/]\n"
            f"Play: {args.play}\n"
            f"Bars: {synthetic_bars} | Seed: {synthetic_seed} | Pattern: {synthetic_pattern}\n"
            f"TFs: {sorted(required_tfs)}",
            border_style="cyan"
        ))

    # Generate synthetic candles
    candles = generate_synthetic_candles(
        symbol=play.symbol_universe[0] if play.symbol_universe else "BTCUSDT",
        timeframes=list(required_tfs),
        bars_per_tf=synthetic_bars,
        seed=synthetic_seed,
        pattern=synthetic_pattern,
    )

    provider = SyntheticCandlesProvider(candles)
    data_start, data_end = provider.get_data_range(exec_tf)

    config = RunnerConfig(
        play_id=args.play,
        play=play,
        window_start=data_start,
        window_end=data_end,
        data_loader=None,
        base_output_dir=Path("backtests"),
        plays_dir=plays_dir,
        skip_preflight=True,
        auto_sync_missing_data=False,
    )

    result = run_backtest_with_gates(config, synthetic_provider=provider)

    if getattr(args, "json_output", False):
        output = {
            "status": "pass" if result.success else "fail",
            "error": result.error_message,
            "mode": "synthetic",
            "bars": synthetic_bars,
            "seed": synthetic_seed,
        }
        if result.summary:
            output["metrics"] = {
                "trades_count": result.summary.trades_count,
                "win_rate": result.summary.win_rate,
                "net_pnl_usdt": result.summary.net_pnl_usdt,
            }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1

    if result.success:
        console.print(f"\n[bold green]OK Synthetic backtest complete[/]")
        if result.summary:
            console.print(f"[dim]Trades: {result.summary.trades_count} | PnL: {result.summary.net_pnl_usdt:.2f} USDT[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error_message}[/]")
        return 1


def handle_backtest_run(args) -> int:
    """Handle `backtest run` subcommand."""
    import json
    from pathlib import Path
    from src.tools.backtest_play_tools import backtest_run_play_tool
    from src.tools.shared import ToolResult

    start = _parse_datetime(args.start) if args.start else None
    end = _parse_datetime(args.end) if args.end else None
    artifacts_dir = Path(args.artifacts_dir) if args.artifacts_dir else None
    plays_dir = Path(args.plays_dir) if args.plays_dir else None

    # Handle synthetic mode
    if getattr(args, "synthetic", False):
        return _handle_synthetic_backtest_run(args)

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]BACKTEST RUN[/]\n"
            f"Play: {args.play}\n"
            f"DataEnv: {args.data_env} | Smoke: {args.smoke} | Strict: {args.strict}",
            border_style="cyan"
        ))

    result = backtest_run_play_tool(
        play_id=args.play,
        env=args.data_env,
        start=start,
        end=end,
        smoke=args.smoke,
        strict=args.strict,
        write_artifacts=not args.no_artifacts,
        artifacts_dir=artifacts_dir,
        plays_dir=plays_dir,
        emit_snapshots=args.emit_snapshots,
        fix_gaps=args.fix_gaps,
        validate_artifacts_after=args.validate,
    )

    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1

    if result.data and "preflight" in result.data:
        preflight = result.data["preflight"]
        _print_preflight_diagnostics(preflight)

    if result.success:
        console.print(f"\n[bold green]OK {result.message}[/]")
        if result.data and "artifact_dir" in result.data:
            console.print(f"[dim]Artifacts: {result.data['artifact_dir']}[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        return 1


def handle_backtest_preflight(args) -> int:
    """Handle `backtest preflight` subcommand."""
    import json
    from src.tools.backtest_play_tools import backtest_preflight_play_tool, backtest_data_fix_tool

    start = _parse_datetime(args.start) if args.start else None
    end = _parse_datetime(args.end) if args.end else None

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]BACKTEST PREFLIGHT[/]\n"
            f"Play: {args.play} | DataEnv: {args.data_env}",
            border_style="cyan"
        ))

    if args.fix_gaps and not args.json_output:
        console.print("[dim]Auto-sync enabled: will fetch missing data if needed[/]")

    result = backtest_preflight_play_tool(
        play_id=args.play,
        env=args.data_env,
        start=start,
        end=end,
        fix_gaps=args.fix_gaps,
    )

    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "checks": {
                "play_valid": result.data.get("play_valid") if result.data else None,
                "has_sufficient_coverage": result.data.get("has_sufficient_coverage") if result.data else None,
            },
            "data": result.data,
            "recommended_fix": result.data.get("coverage_issue") if result.data and not result.success else None,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1

    if result.data:
        _print_preflight_diagnostics(result.data)

    if result.success:
        console.print(f"\n[bold green]OK {result.message}[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        return 1


def handle_backtest_indicators(args) -> int:
    """Handle `backtest indicators` subcommand."""
    import json
    from pathlib import Path

    # Validate arguments
    if hasattr(args, '_validate'):
        args._validate(args)

    # Handle audit mode
    if args.audit_math_from_snapshots:
        from src.tools.backtest_audit_tools import backtest_audit_math_from_snapshots_tool

        if not args.run_dir:
            console.print("[red]Error: --run-dir is required for --audit-math-from-snapshots[/]")
            return 1

        run_dir = Path(args.run_dir)

        if not args.json_output:
            console.print(Panel(
                f"[bold cyan]INDICATOR MATH AUDIT[/]\n"
                f"Run Dir: {args.run_dir}",
                border_style="cyan"
            ))

        result = backtest_audit_math_from_snapshots_tool(run_dir=run_dir)

        if args.json_output:
            output = {
                "status": "pass" if result.success else "fail",
                "message": result.message if result.success else result.error,
                "data": result.data,
            }
            print(json.dumps(output, indent=2, default=str))
            return 0 if result.success else 1

        if result.success:
            console.print(f"\n[bold green]OK {result.message}[/]")
            if result.data:
                summary = result.data.get("summary", {})
                console.print(f"\n[dim]Overall: {summary.get('passed_columns', 0)}/{summary.get('total_columns', 0)} columns passed[/]")
                console.print(f"[dim]Max diff: {summary.get('max_abs_diff', 0):.2e}[/]")
                console.print(f"[dim]Mean diff: {summary.get('mean_abs_diff', 0):.2e}[/]")

                if result.data.get("column_results"):
                    console.print(f"\n[bold]Column Results:[/]")
                    for col_result in result.data["column_results"]:
                        status = "[green]PASS[/]" if col_result["passed"] else "[red]FAIL[/]"
                        console.print(f"  {col_result['column']}: {status} "
                                    f"(max_diff={col_result['max_abs_diff']:.2e}, "
                                    f"mean_diff={col_result['mean_abs_diff']:.2e})")
        else:
            console.print(f"\n[bold red]FAIL {result.error}[/]")
            if result.data and result.data.get("error_details"):
                console.print(result.data["error_details"])
        return 0 if result.success else 1

    # Original indicator discovery mode
    from src.tools.backtest_play_tools import backtest_indicators_tool

    start = _parse_datetime(args.start) if args.start else None
    end = _parse_datetime(args.end) if args.end else None

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]BACKTEST INDICATORS[/]\n"
            f"Play: {args.play} | DataEnv: {args.data_env}",
            border_style="cyan"
        ))

    result = backtest_indicators_tool(
        play_id=args.play,
        data_env=args.data_env,
        start=start,
        end=end,
        compute_values=args.compute,
    )

    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1

    if result.success and result.data:
        data = result.data
        console.print(f"\n[bold]Indicator Key Discovery[/]")
        console.print(f"Play: {data.get('play_id')}")
        console.print(f"Symbol: {data.get('symbol')}")
        console.print(f"Execution timeframe: {data.get('exec_tf')}")
        if data.get('high_tf'):
            console.print(f"Higher timeframe: {data.get('high_tf')}")
        if data.get('med_tf'):
            console.print(f"Medium timeframe: {data.get('med_tf')}")

        console.print(f"\n[bold]Declared Keys (from FeatureSpec output_key):[/]")
        for role, keys in data.get("declared_keys_by_role", {}).items():
            console.print(f"  {role}: {keys}")

        console.print(f"\n[bold]Expanded Keys (actual column names, including multi-output):[/]")
        for role, keys in data.get("expanded_keys_by_role", {}).items():
            console.print(f"  {role}: {keys}")

        if data.get("computed_info"):
            console.print(f"\n[bold]Computed Info:[/]")
            for role, info in data["computed_info"].items():
                if "error" in info:
                    console.print(f"  {role}: [red]{info['error']}[/]")
                else:
                    console.print(f"  {role} ({info.get('tf')}):")
                    console.print(f"    Data rows: {info.get('data_rows')}")
                    console.print(f"    First valid bar: {info.get('first_valid_bar')}")
                    console.print(f"    Computed columns: {info.get('computed_columns')}")

        console.print(f"\n[bold green]OK {result.message}[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        return 1


def handle_backtest_data_fix(args) -> int:
    """Handle `backtest data-fix` subcommand."""
    import json
    from src.tools.backtest_play_tools import backtest_data_fix_tool

    start = _parse_datetime(args.start) if args.start else None

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]BACKTEST DATA FIX[/]\n"
            f"Play: {args.play} | DataEnv: {args.data_env}\n"
            f"Sync to now: {args.sync_to_now} | Fill gaps: {args.fill_gaps} | Heal: {args.heal}",
            border_style="cyan"
        ))

    result = backtest_data_fix_tool(
        play_id=args.play,
        env=args.data_env,
        start=start,
        sync_to_now=args.sync_to_now,
        fill_gaps=args.fill_gaps,
        heal=args.heal,
    )

    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1

    if result.success:
        console.print(f"\n[bold green]OK {result.message}[/]")
        if result.data and "operations" in result.data:
            for op in result.data["operations"]:
                status = "OK" if op["success"] else "FAIL"
                console.print(f"  {status} {op['name']}: {op['message']}")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        return 1


def handle_backtest_list(args) -> int:
    """Handle `backtest list` subcommand."""
    import json
    from pathlib import Path
    from src.tools.backtest_play_tools import backtest_list_plays_tool

    plays_dir = Path(args.plays_dir) if args.plays_dir else None

    result = backtest_list_plays_tool(plays_dir=plays_dir)

    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1

    if result.success:
        console.print(f"\n[bold cyan]Available Plays:[/]")
        console.print(f"[dim]Directory: {result.data['directory']}[/]\n")

        for card_id in result.data["plays"]:
            console.print(f"  - {card_id}")

        console.print(f"\n[dim]Total: {len(result.data['plays'])} Plays[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        return 1


def handle_backtest_normalize(args) -> int:
    """Handle `backtest play-normalize` subcommand."""
    import json
    from pathlib import Path
    from src.tools.backtest_play_tools import backtest_play_normalize_tool

    plays_dir = Path(args.plays_dir) if args.plays_dir else None

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]PLAY NORMALIZE[/]\n"
            f"Play: {args.play} | Write: {args.write}",
            border_style="cyan"
        ))

    result = backtest_play_normalize_tool(
        play_id=args.play,
        plays_dir=plays_dir,
        write_in_place=args.write,
    )

    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1

    if result.success:
        console.print(f"\n[bold green]OK {result.message}[/]")
        if result.data:
            if result.data.get("written"):
                console.print(f"[dim]Written to: {result.data.get('yaml_path')}[/]")
            if result.data.get("warnings"):
                for w in result.data["warnings"]:
                    console.print(f"[yellow]Warning: {w}[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        if result.data and result.data.get("error_details"):
            console.print(result.data["error_details"])
        return 1


def _handle_parity_verification(args, verify_artifact_parity_tool) -> int:
    """Handle CSV vs Parquet artifact parity verification (Phase 3.1)."""
    import json

    if not getattr(args, 'parity_play', None):
        console.print("[red]Error: --play is required for parity verification[/]")
        return 1
    if not getattr(args, 'parity_symbol', None):
        console.print("[red]Error: --symbol is required for parity verification[/]")
        return 1

    play_id = args.parity_play
    symbol = args.parity_symbol.upper()
    run_id = getattr(args, 'parity_run', None)
    if run_id and run_id.lower() == 'latest':
        run_id = None

    if not getattr(args, 'json_output', False):
        console.print(Panel(
            f"[bold cyan]CSV vs PARQUET PARITY VERIFICATION[/]\n"
            f"Play: {play_id}\n"
            f"Symbol: {symbol}\n"
            f"Run: {run_id or 'latest'}",
            border_style="cyan"
        ))

    result = verify_artifact_parity_tool(
        play_id=play_id,
        symbol=symbol,
        run_id=run_id,
    )

    if getattr(args, 'json_output', False):
        output = {
            "command": "verify-suite",
            "mode": "compare-csv-parquet",
            "success": result.success,
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        print(json.dumps(output, indent=2))
        return 0 if result.success else 1

    if result.success:
        console.print(f"\n[bold green]PARITY PASSED[/] {result.message}")
        if result.data:
            for ar in result.data.get("artifact_results", []):
                icon = "PASS" if ar.get("passed") else "FAIL"
                console.print(f"  {icon} {ar.get('artifact_name')}")
        return 0
    else:
        console.print(f"\n[bold red]PARITY FAILED[/] {result.error}")
        if result.data:
            for ar in result.data.get("artifact_results", []):
                status = "PASS" if ar.get("passed") else "FAIL"
                console.print(f"  {status} {ar.get('artifact_name')}")
                for err in ar.get("errors", []):
                    console.print(f"      - {err}")
        return 1


def handle_backtest_verify_suite(args) -> int:
    """Handle `backtest verify-suite` subcommand - global verification suite or parity check."""
    import json
    from pathlib import Path
    from src.tools.backtest_play_tools import (
        backtest_play_normalize_batch_tool,
        backtest_run_play_tool,
    )
    from src.tools.backtest_audit_tools import (
        backtest_audit_math_from_snapshots_tool,
        backtest_audit_toolkit_tool,
        verify_artifact_parity_tool,
    )

    # Phase 3.1: CSV vs Parquet Parity Verification Mode
    if getattr(args, 'compare_csv_parquet', False):
        return _handle_parity_verification(args, verify_artifact_parity_tool)

    # Standard Verification Suite Mode
    if not args.plays_dir:
        console.print("[red]Error: --dir is required for verification suite mode[/]")
        console.print("[dim]Use --compare-csv-parquet for artifact parity mode[/]")
        return 1

    if not args.start or not args.end:
        console.print("[red]Error: --start and --end are required for verification suite mode[/]")
        return 1

    plays_dir = Path(args.plays_dir)
    start = _parse_datetime(args.start)
    end = _parse_datetime(args.end)
    skip_toolkit_audit = getattr(args, 'skip_toolkit_audit', False)

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]GLOBAL VERIFICATION SUITE[/]\n"
            f"Directory: {args.plays_dir}\n"
            f"Window: {args.start} -> {args.end}\n"
            f"DataEnv: {args.data_env} | Strict: {args.strict}\n"
            f"Toolkit Audit: {'SKIPPED' if skip_toolkit_audit else 'ENABLED (Gate 1)'}",
            border_style="cyan"
        ))

    suite_results = {
        "suite_config": {
            "plays_dir": str(plays_dir),
            "data_env": args.data_env,
            "window_start": args.start,
            "window_end": args.end,
            "strict": args.strict,
            "skip_toolkit_audit": skip_toolkit_audit,
        },
        "phases": {},
        "summary": {},
    }

    # PHASE 0 (Gate 1): Toolkit Contract Audit (unless skipped)
    if not skip_toolkit_audit:
        console.print("\n[bold]Phase 0 (Gate 1): Toolkit Contract Audit[/]")

        toolkit_result = backtest_audit_toolkit_tool(
            sample_bars=2000,
            seed=1337,
            fail_on_extras=False,
            strict=True,
        )

        suite_results["phases"]["toolkit_audit"] = {
            "success": toolkit_result.success,
            "message": toolkit_result.message if toolkit_result.success else toolkit_result.error,
            "data": toolkit_result.data,
        }

        if not toolkit_result.success:
            console.print(f"[red]FAIL Toolkit audit failed: {toolkit_result.error}[/]")
            if args.json_output:
                suite_results["summary"] = {"overall_success": False, "failure_phase": "toolkit_audit"}
                print(json.dumps(suite_results, indent=2, default=str))
            return 1

        console.print(f"[green]PASS Toolkit audit: {toolkit_result.message}[/]")
    else:
        console.print("\n[dim]Phase 0 (Gate 1): Toolkit Contract Audit - SKIPPED[/]")
        suite_results["phases"]["toolkit_audit"] = {"skipped": True}

    # PHASE 1: Batch normalize all cards
    console.print("\n[bold]Phase 1: Batch Normalization[/]")

    normalize_result = backtest_play_normalize_batch_tool(
        plays_dir=plays_dir,
        write_in_place=True,
    )

    suite_results["phases"]["normalization"] = {
        "success": normalize_result.success,
        "message": normalize_result.message if normalize_result.success else normalize_result.error,
        "data": normalize_result.data,
    }

    if not normalize_result.success:
        console.print(f"[red]FAIL Normalization failed: {normalize_result.error}[/]")
        if args.json_output:
            suite_results["summary"] = {"overall_success": False, "failure_phase": "normalization"}
            print(json.dumps(suite_results, indent=2, default=str))
        return 1

    console.print(f"[green]PASS Normalization successful: {normalize_result.data['summary']['passed']}/{normalize_result.data['summary']['total_cards']} cards[/]")

    # PHASE 2: Run backtests with snapshot emission
    console.print("\n[bold]Phase 2: Backtest Runs with Snapshots[/]")

    backtest_results = []
    failed_backtests = []

    play_ids = normalize_result.data["results"]
    for card_result in play_ids:
        if not card_result["success"]:
            continue

        play_id = card_result["play_id"]
        console.print(f"  Running {play_id}...")

        run_result = backtest_run_play_tool(
            play_id=play_id,
            env=args.data_env,
            start=start,
            end=end,
            smoke=False,
            strict=args.strict,
            write_artifacts=False,
            plays_dir=plays_dir,
            emit_snapshots=True,
        )

        backtest_result = {
            "play_id": play_id,
            "success": run_result.success,
            "message": run_result.message if run_result.success else run_result.error,
            "run_dir": run_result.data.get("artifact_dir") if run_result.data else None,
        }

        if run_result.success:
            console.print(f"    [green]PASS {play_id}: {run_result.message}[/]")
        else:
            console.print(f"    [red]FAIL {play_id}: {run_result.error}[/]")
            failed_backtests.append(play_id)

        backtest_results.append(backtest_result)

    suite_results["phases"]["backtests"] = {
        "results": backtest_results,
        "total_cards": len(backtest_results),
        "successful_runs": len(backtest_results) - len(failed_backtests),
        "failed_runs": len(failed_backtests),
    }

    if failed_backtests:
        console.print(f"[red]FAIL Backtests failed: {len(failed_backtests)}/{len(backtest_results)} cards[/]")
        if args.json_output:
            suite_results["summary"] = {"overall_success": False, "failure_phase": "backtests"}
            print(json.dumps(suite_results, indent=2, default=str))
        return 1

        console.print(f"[green]PASS Backtests successful: {len(backtest_results)}/{len(backtest_results)} cards[/]")

    # PHASE 3: Math parity audits
    console.print("\n[bold]Phase 3: Math Parity Audits[/]")

    audit_results = []
    failed_audits = []

    for backtest_result in backtest_results:
        play_id = backtest_result["play_id"]
        run_dir = backtest_result["run_dir"]

        if not run_dir:
            console.print(f"  [red]FAIL {play_id}: No run directory[/]")
            failed_audits.append(play_id)
            continue

        console.print(f"  Auditing {play_id}...")

        audit_result = backtest_audit_math_from_snapshots_tool(run_dir=Path(run_dir))

        audit_summary = {
            "play_id": play_id,
            "success": audit_result.success,
            "message": audit_result.message if audit_result.success else audit_result.error,
            "run_dir": run_dir,
        }

        if audit_result.success and audit_result.data:
            summary = audit_result.data.get("summary", {})
            audit_summary.update({
                "total_columns": summary.get("total_columns", 0),
                "passed_columns": summary.get("passed_columns", 0),
                "failed_columns": summary.get("failed_columns", 0),
                "max_abs_diff": summary.get("max_abs_diff", 0),
                "mean_abs_diff": summary.get("mean_abs_diff", 0),
            })

            if audit_result.success:
                console.print(f"    [green]PASS {play_id}: {summary.get('passed_columns', 0)}/{summary.get('total_columns', 0)} columns passed[/]")
            else:
                console.print(f"    [red]FAIL {play_id}: {summary.get('failed_columns', 0)}/{summary.get('total_columns', 0)} columns failed[/]")
                failed_audits.append(play_id)
        else:
            console.print(f"    [red]FAIL {play_id}: {audit_result.error}[/]")
            failed_audits.append(play_id)

        audit_results.append(audit_summary)

    suite_results["phases"]["audits"] = {
        "results": audit_results,
        "total_cards": len(audit_results),
        "successful_audits": len(audit_results) - len(failed_audits),
        "failed_audits": len(failed_audits),
    }

    # FINAL SUMMARY
    overall_success = len(failed_audits) == 0

    suite_results["summary"] = {
        "overall_success": overall_success,
        "total_cards": len(backtest_results),
        "normalization_passed": suite_results["phases"]["normalization"]["success"],
        "backtests_passed": len(failed_backtests) == 0,
        "audits_passed": len(failed_audits) == 0,
        "failed_cards": failed_audits,
    }

    if not args.json_output:
        console.print(f"\n[bold]Suite Summary:[/]")
        console.print(f"  Total cards: {len(backtest_results)}")
        console.print(f"  Normalization: {'PASS' if suite_results['summary']['normalization_passed'] else 'FAIL'}")
        console.print(f"  Backtests: {'PASS' if suite_results['summary']['backtests_passed'] else 'FAIL'} ({len(backtest_results) - len(failed_backtests)}/{len(backtest_results)})")
        console.print(f"  Audits: {'PASS' if suite_results['summary']['audits_passed'] else 'FAIL'} ({len(audit_results) - len(failed_audits)}/{len(audit_results)})")

        if overall_success:
            console.print(f"\n[bold green]GLOBAL VERIFICATION SUITE PASSED![/]")
            console.print("All indicators compute correctly and match pandas_ta exactly.")
        else:
            console.print(f"\n[bold red]GLOBAL VERIFICATION SUITE FAILED[/]")
            if failed_audits:
                console.print(f"Failed cards: {', '.join(failed_audits)}")
    else:
        print(json.dumps(suite_results, indent=2, default=str))

    return 0 if overall_success else 1


def handle_backtest_normalize_batch(args) -> int:
    """Handle `backtest play-normalize-batch` subcommand."""
    import json
    from pathlib import Path
    from src.tools.backtest_play_tools import backtest_play_normalize_batch_tool

    plays_dir = Path(args.plays_dir)

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]PLAY NORMALIZE BATCH[/]\n"
            f"Directory: {args.plays_dir} | Write: {args.write}",
            border_style="cyan"
        ))

    result = backtest_play_normalize_batch_tool(
        plays_dir=plays_dir,
        write_in_place=args.write,
    )

    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1

    if result.success:
        console.print(f"\n[bold green]OK {result.message}[/]")
        if result.data:
            summary = result.data.get("summary", {})
            console.print(f"\n[dim]Processed: {summary.get('total_cards', 0)} cards[/]")
            console.print(f"[dim]Passed: {summary.get('passed', 0)}[/]")
            console.print(f"[dim]Failed: {summary.get('failed', 0)}[/]")
            if summary.get("failed", 0) > 0:
                console.print(f"\n[yellow]Failed cards:[/]")
                for card_result in result.data.get("results", []):
                    if not card_result.get("success"):
                        console.print(f"  [red]- {card_result.get('play_id')}: {card_result.get('error', 'Unknown error')}[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        if result.data and result.data.get("error_details"):
            console.print(result.data["error_details"])
        return 1


def handle_backtest_audit_toolkit(args) -> int:
    """Handle `backtest audit-toolkit` subcommand - Gate 1 toolkit contract audit."""
    import json
    from src.tools.backtest_audit_tools import backtest_audit_toolkit_tool

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]TOOLKIT CONTRACT AUDIT (Gate 1)[/]\n"
            f"Sample: {args.sample_bars} bars | Seed: {args.seed}\n"
            f"Strict: {args.strict} | Fail on extras: {args.fail_on_extras}",
            border_style="cyan"
        ))

    result = backtest_audit_toolkit_tool(
        sample_bars=args.sample_bars,
        seed=args.seed,
        fail_on_extras=args.fail_on_extras,
        strict=args.strict,
    )

    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1

    if result.success:
        console.print(f"\n[bold green]PASS {result.message}[/]")
        if result.data:
            console.print(f"[dim]Total indicators: {result.data.get('total_indicators', 0)}[/]")
            console.print(f"[dim]Passed: {result.data.get('passed_indicators', 0)}[/]")
            console.print(f"[dim]With extras dropped: {result.data.get('indicators_with_extras', 0)}[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        if result.data and result.data.get("indicator_results"):
            console.print("\n[bold]Failed Indicators:[/]")
            for r in result.data["indicator_results"]:
                if not r["passed"]:
                    console.print(f"  [red]- {r['indicator_type']}: missing={r['missing_outputs']}, collisions={r['collisions']}, error={r['error_message']}[/]")
        return 1


def handle_backtest_audit_incremental_parity(args) -> int:
    """Handle `backtest audit-incremental-parity` subcommand - G3-1 incremental vs vectorized parity."""
    import json
    from src.forge.audits import run_incremental_parity_audit

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]INCREMENTAL vs VECTORIZED PARITY AUDIT (G3-1)[/]\n"
            f"Bars: {args.bars} | Tolerance: {args.tolerance} | Seed: {args.seed}\n"
            f"Tests 11 O(1) incremental indicators against pandas_ta",
            border_style="cyan"
        ))

    result = run_incremental_parity_audit(
        bars=args.bars,
        tolerance=args.tolerance,
        seed=args.seed,
    )

    if args.json_output:
        print(json.dumps(result.to_dict(), indent=2, default=str))
        return 0 if result.success else 1

    result.print_summary()
    return 0 if result.success else 1


def handle_backtest_audit_structure_parity(args) -> int:
    """Handle `backtest audit-structure-parity` subcommand - structure detector parity."""
    import json
    from src.forge.audits.audit_structure_parity import run_structure_parity_audit

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]STRUCTURE DETECTOR PARITY AUDIT[/]\n"
            f"Bars: {args.bars} | Tolerance: {args.tolerance} | Seed: {args.seed}\n"
            f"Tests 7 structure detectors against vectorized references",
            border_style="cyan"
        ))

    result = run_structure_parity_audit(
        bars=args.bars,
        tolerance=args.tolerance,
        seed=args.seed,
    )

    if args.json_output:
        print(json.dumps(result.to_dict(), indent=2, default=str))
        return 0 if result.success else 1

    result.print_summary()
    return 0 if result.success else 1


def handle_backtest_math_parity(args) -> int:
    """Handle `backtest math-parity` subcommand - indicator math parity audit."""
    import json
    from src.tools.backtest_audit_tools import backtest_math_parity_tool

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]MATH PARITY AUDIT[/]\n"
            f"Play: {args.play}\n"
            f"Window: {args.start} -> {args.end}\n"
            f"Contract audit: {args.contract_sample_bars} bars, seed={args.contract_seed}",
            border_style="cyan"
        ))

    result = backtest_math_parity_tool(
        play=args.play,
        start_date=args.start,
        end_date=args.end,
        output_dir=args.output_dir,
        contract_sample_bars=args.contract_sample_bars,
        contract_seed=args.contract_seed,
    )

    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1

    if result.success:
        console.print(f"\n[bold green]PASS {result.message}[/]")
        if result.data:
            contract_data = result.data.get("contract_audit", {})
            parity_data = result.data.get("parity_audit", {})
            console.print(f"[dim]Contract: {contract_data.get('passed', 0)}/{contract_data.get('total', 0)} indicators[/]")
            if parity_data and parity_data.get("summary"):
                summary = parity_data["summary"]
                console.print(f"[dim]Parity: {summary.get('passed_columns', 0)}/{summary.get('total_columns', 0)} columns[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        if result.data:
            contract_data = result.data.get("contract_audit", {})
            parity_data = result.data.get("parity_audit", {})
            if contract_data:
                console.print(f"[dim]Contract: {contract_data.get('passed', 0)}/{contract_data.get('total', 0)}[/]")
            if parity_data and parity_data.get("summary"):
                summary = parity_data["summary"]
                console.print(f"[dim]Parity: {summary.get('passed_columns', 0)}/{summary.get('total_columns', 0)}, max_diff={summary.get('max_abs_diff', 0):.2e}[/]")
        return 1


def handle_backtest_metadata_smoke(args) -> int:
    """Handle `backtest metadata-smoke` subcommand - Indicator Metadata v1 smoke test."""
    from src.cli.smoke_tests import run_metadata_smoke

    return run_metadata_smoke(
        symbol=args.symbol,
        tf=args.tf,
        sample_bars=args.sample_bars,
        seed=args.seed,
        export_path=args.export_path,
        export_format=args.export_format,
    )


def handle_backtest_mark_price_smoke(args) -> int:
    """Handle `backtest mark-price-smoke` subcommand - Mark Price Engine smoke test."""
    from src.cli.smoke_tests import run_mark_price_smoke

    return run_mark_price_smoke(
        sample_bars=args.sample_bars,
        seed=args.seed,
    )


def handle_backtest_structure_smoke(args) -> int:
    """Handle `backtest structure-smoke` subcommand - Structure smoke test."""
    from src.cli.smoke_tests import run_structure_smoke
    return run_structure_smoke(seed=args.seed)


def handle_backtest_audit_snapshot_plumbing(args) -> int:
    """Handle `backtest audit-snapshot-plumbing` subcommand - Phase 4 plumbing parity."""
    import json
    from src.tools.backtest_audit_tools import backtest_audit_snapshot_plumbing_tool

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]PHASE 4: SNAPSHOT PLUMBING PARITY AUDIT[/]\n"
            f"Play: {args.play}\n"
            f"Window: {args.start} -> {args.end}\n"
            f"Max samples: {args.max_samples} | Tolerance: {args.tolerance:.0e} | Strict: {args.strict}",
            border_style="cyan"
        ))

    result = backtest_audit_snapshot_plumbing_tool(
        play_id=args.play,
        start_date=args.start,
        end_date=args.end,
        max_samples=args.max_samples,
        tolerance=args.tolerance,
        strict=args.strict,
    )

    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1

    if result.success:
        console.print(f"\n[bold green]PASS[/] {result.message}")
        if result.data:
            console.print(f"[dim]  Samples: {result.data.get('total_samples', 0)}[/]")
            console.print(f"[dim]  Comparisons: {result.data.get('total_comparisons', 0)}[/]")
            console.print(f"[dim]  Max samples reached: {result.data.get('max_samples_reached', False)}[/]")
            console.print(f"[dim]  Runtime: {result.data.get('runtime_seconds', 0):.1f}s[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL[/] {result.error}")
        if result.data and result.data.get("first_mismatch"):
            mismatch = result.data["first_mismatch"]
            console.print(f"\n[bold]First mismatch:[/]")
            console.print(f"  ts_close: {mismatch.get('ts_close')}")
            console.print(f"  tf_role: {mismatch.get('tf_role')}")
            console.print(f"  key: {mismatch.get('key')}")
            console.print(f"  offset: {mismatch.get('offset')}")
            console.print(f"  observed: {mismatch.get('observed')}")
            console.print(f"  expected: {mismatch.get('expected')}")
            console.print(f"  abs_diff: {mismatch.get('abs_diff')}")
            console.print(f"  tolerance: {mismatch.get('tolerance')}")
            console.print(f"  exec_idx: {mismatch.get('exec_idx')}")
            console.print(f"  htf_idx: {mismatch.get('htf_idx')}")
            console.print(f"  target_idx: {mismatch.get('target_idx')}")
        return 1


def handle_backtest_audit_rollup(args) -> int:
    """Handle `backtest audit-rollup` subcommand - 1m rollup parity audit."""
    import json
    from src.tools.backtest_audit_tools import backtest_audit_rollup_parity_tool

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]ROLLUP PARITY AUDIT (1m Price Feed)[/]\n"
            f"Intervals: {args.intervals} | Quotes/interval: {args.quotes}\n"
            f"Seed: {args.seed} | Tolerance: {args.tolerance:.0e}",
            border_style="cyan"
        ))

    result = backtest_audit_rollup_parity_tool(
        n_intervals=args.intervals,
        quotes_per_interval=args.quotes,
        seed=args.seed,
        tolerance=args.tolerance,
    )

    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1

    if result.success:
        console.print(f"\nPASS {result.message}")
        if result.data:
            console.print(f"  Total intervals: {result.data.get('total_intervals', 0)}")
            console.print(f"  Total comparisons: {result.data.get('total_comparisons', 0)}")
            console.print(f"  Bucket tests: {'PASS' if result.data.get('bucket_tests_passed') else 'FAIL'}")
            console.print(f"  Accessor tests: {'PASS' if result.data.get('accessor_tests_passed') else 'FAIL'}")
        return 0
    else:
        console.print(f"\nFAIL {result.error}")
        if result.data:
            console.print(f"  Failed intervals: {result.data.get('failed_intervals', 0)}")
            console.print(f"  Failed comparisons: {result.data.get('failed_comparisons', 0)}")
        return 1


def handle_backtest_verify_determinism(args) -> int:
    """Handle `backtest verify-determinism` subcommand - Phase 3 hash-based verification."""
    import json
    from pathlib import Path
    from src.backtest.artifacts.determinism import compare_runs, verify_determinism_rerun

    if not args.json_output:
        console.print(Panel(
            "[bold cyan]DETERMINISM VERIFICATION[/]\n"
            "Compares backtest run hashes to verify determinism.",
            title="Backtest Audit",
            border_style="cyan"
        ))

    if args.re_run:
        if not args.run_a:
            console.print("[red]Error: --re-run requires --run-a (path to existing run)[/]")
            return 1

        run_path = Path(args.run_a)
        if not run_path.exists():
            console.print(f"[red]Error: Run path does not exist: {run_path}[/]")
            return 1

        if not args.json_output:
            console.print(f"[cyan]Re-running Play from: {run_path}[/]")

        result = verify_determinism_rerun(
            run_path=run_path,
            fix_gaps=args.fix_gaps,
        )
    else:
        if not args.run_a or not args.run_b:
            console.print("[red]Error: Compare mode requires both --run-a and --run-b[/]")
            return 1

        run_a = Path(args.run_a)
        run_b = Path(args.run_b)

        if not run_a.exists():
            console.print(f"[red]Error: Run A path does not exist: {run_a}[/]")
            return 1
        if not run_b.exists():
            console.print(f"[red]Error: Run B path does not exist: {run_b}[/]")
            return 1

        if not args.json_output:
            console.print(f"[cyan]Comparing runs:[/]")
            console.print(f"  A: {run_a}")
            console.print(f"  B: {run_b}")

        result = compare_runs(run_a, run_b)

    if args.json_output:
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.passed else 1

    result.print_report()
    return 0 if result.passed else 1


def handle_backtest_metrics_audit(args) -> int:
    """
    Handle `backtest metrics-audit` subcommand.

    Runs embedded test scenarios to validate financial metrics calculations:
    - Drawdown: max_dd_abs and max_dd_pct tracked independently
    - Calmar: uses CAGR, not arithmetic return
    - TF: unknown timeframes raise errors in strict mode
    - Edge cases: proper handling of zero/inf scenarios

    This is CLI validation - no pytest files per project rules.
    """
    import json
    from src.backtest.metrics import (
        _compute_drawdown_metrics,
        _compute_cagr,
        _compute_calmar,
        get_bars_per_year,
        normalize_tf_string,
    )
    from src.backtest.types import EquityPoint
    from datetime import datetime

    results = []
    all_passed = True

    if not args.json_output:
        console.print(Panel(
            "[bold cyan]METRICS AUDIT[/]\n"
            "Validating financial metrics calculations",
            title="Backtest Metrics",
            border_style="cyan"
        ))

    # TEST 1: Drawdown Independent Maxima
    test_name = "Drawdown Independent Maxima"
    try:
        equity_curve = [
            EquityPoint(timestamp=datetime(2024, 1, 1, 0, 0), equity=10.0),
            EquityPoint(timestamp=datetime(2024, 1, 1, 1, 0), equity=1.0),
            EquityPoint(timestamp=datetime(2024, 1, 1, 2, 0), equity=1000.0),
            EquityPoint(timestamp=datetime(2024, 1, 1, 3, 0), equity=900.0),
        ]

        max_dd_abs, max_dd_pct, _ = _compute_drawdown_metrics(equity_curve)

        abs_correct = abs(max_dd_abs - 100.0) < 0.01
        pct_correct = abs(max_dd_pct - 0.90) < 0.01

        passed = abs_correct and pct_correct
        detail = f"max_dd_abs={max_dd_abs:.2f} (expected 100), max_dd_pct={max_dd_pct:.4f} (expected 0.90)"

        results.append({"test": test_name, "passed": passed, "detail": detail})
        if not passed:
            all_passed = False

        if not args.json_output:
            status = "[green]PASS[/]" if passed else "[red]FAIL[/]"
            console.print(f"  {status} {test_name}")
            console.print(f"       {detail}")

    except Exception as e:
        results.append({"test": test_name, "passed": False, "detail": str(e)})
        all_passed = False
        if not args.json_output:
            console.print(f"  [red]FAIL[/] {test_name}: {e}")

    # TEST 2: CAGR Calculation
    test_name = "CAGR Geometric Formula"
    try:
        cagr = _compute_cagr(
            initial_equity=10000.0,
            final_equity=12100.0,
            total_bars=365,
            bars_per_year=365,
        )

        expected_cagr = 0.21
        passed = abs(cagr - expected_cagr) < 0.01
        detail = f"CAGR={cagr:.4f} (expected {expected_cagr})"

        results.append({"test": test_name, "passed": passed, "detail": detail})
        if not passed:
            all_passed = False

        if not args.json_output:
            status = "[green]PASS[/]" if passed else "[red]FAIL[/]"
            console.print(f"  {status} {test_name}")
            console.print(f"       {detail}")

    except Exception as e:
        results.append({"test": test_name, "passed": False, "detail": str(e)})
        all_passed = False
        if not args.json_output:
            console.print(f"  [red]FAIL[/] {test_name}: {e}")

    # TEST 3: Calmar Uses CAGR
    test_name = "Calmar Uses CAGR"
    try:
        calmar = _compute_calmar(
            initial_equity=10000.0,
            final_equity=12100.0,
            max_dd_pct_decimal=0.10,
            total_bars=365,
            tf="D",
            strict_tf=True,
        )

        expected_calmar = 2.1
        passed = abs(calmar - expected_calmar) < 0.1
        detail = f"Calmar={calmar:.2f} (expected ~{expected_calmar})"

        results.append({"test": test_name, "passed": passed, "detail": detail})
        if not passed:
            all_passed = False

        if not args.json_output:
            status = "[green]PASS[/]" if passed else "[red]FAIL[/]"
            console.print(f"  {status} {test_name}")
            console.print(f"       {detail}")

    except Exception as e:
        results.append({"test": test_name, "passed": False, "detail": str(e)})
        all_passed = False
        if not args.json_output:
            console.print(f"  [red]FAIL[/] {test_name}: {e}")

    # TEST 4: TF Strict Mode
    test_name = "TF Strict Mode (Unknown TF Raises)"
    try:
        try:
            _ = get_bars_per_year("unknown_tf", strict=True)
            passed = False
            detail = "Expected ValueError for unknown TF, but none raised"
        except ValueError as e:
            passed = True
            detail = f"Correctly raised ValueError: {str(e)[:60]}..."

        results.append({"test": test_name, "passed": passed, "detail": detail})
        if not passed:
            all_passed = False

        if not args.json_output:
            status = "[green]PASS[/]" if passed else "[red]FAIL[/]"
            console.print(f"  {status} {test_name}")
            console.print(f"       {detail}")

    except Exception as e:
        results.append({"test": test_name, "passed": False, "detail": str(e)})
        all_passed = False
        if not args.json_output:
            console.print(f"  [red]FAIL[/] {test_name}: {e}")

    # TEST 5: TF Normalization
    test_name = "TF Normalization (Bybit formats)"
    try:
        test_cases = [
            ("60", "1h"),
            ("240", "4h"),
            ("D", "D"),
            ("1h", "1h"),
        ]

        all_correct = True
        details = []
        for input_tf, expected in test_cases:
            normalized = normalize_tf_string(input_tf)
            if normalized != expected:
                all_correct = False
                details.append(f"{input_tf}->{normalized} (expected {expected})")
            else:
                details.append(f"{input_tf}->{normalized} OK")

        try:
            normalize_tf_string("1d")
            all_correct = False
            details.append("1d should raise ValueError")
        except ValueError:
            details.append("1d rejected OK")

        passed = all_correct
        detail = ", ".join(details)

        results.append({"test": test_name, "passed": passed, "detail": detail})
        if not passed:
            all_passed = False

        if not args.json_output:
            status = "[green]PASS[/]" if passed else "[red]FAIL[/]"
            console.print(f"  {status} {test_name}")
            console.print(f"       {detail}")

    except Exception as e:
        results.append({"test": test_name, "passed": False, "detail": str(e)})
        all_passed = False
        if not args.json_output:
            console.print(f"  [red]FAIL[/] {test_name}: {e}")

    # TEST 6: Edge Case - Zero Max DD (Calmar capped)
    test_name = "Edge Case: Zero Max DD (Calmar capped)"
    try:
        calmar = _compute_calmar(
            initial_equity=10000.0,
            final_equity=12100.0,
            max_dd_pct_decimal=0.0,
            total_bars=365,
            tf="D",
            strict_tf=True,
        )

        passed = calmar == 100.0
        detail = f"Calmar={calmar} (expected 100.0 when no DD)"

        results.append({"test": test_name, "passed": passed, "detail": detail})
        if not passed:
            all_passed = False

        if not args.json_output:
            status = "[green]PASS[/]" if passed else "[red]FAIL[/]"
            console.print(f"  {status} {test_name}")
            console.print(f"       {detail}")

    except Exception as e:
        results.append({"test": test_name, "passed": False, "detail": str(e)})
        all_passed = False
        if not args.json_output:
            console.print(f"  [red]FAIL[/] {test_name}: {e}")

    # SUMMARY
    passed_count = sum(1 for r in results if r["passed"])
    total_count = len(results)

    if args.json_output:
        output = {
            "passed": all_passed,
            "summary": f"{passed_count}/{total_count} tests passed",
            "tests": results,
        }
        print(json.dumps(output, indent=2))
    else:
        console.print(f"\n[bold]Summary: {passed_count}/{total_count} tests passed[/]")
        if all_passed:
            console.print("[bold green]OK All metrics audit tests PASSED[/]")
        else:
            console.print("[bold red]FAIL Some metrics audit tests FAILED[/]")

    return 0 if all_passed else 1


# =============================================================================
# VIZ SUBCOMMAND HANDLERS
# =============================================================================

def handle_viz_serve(args) -> int:
    """Handle `viz serve` subcommand - start visualization server."""
    try:
        from src.viz.server import run_server

        console.print(Panel(
            f"[bold cyan]BACKTEST VISUALIZATION SERVER[/]\n"
            f"Host: {args.host}:{args.port}\n"
            f"Auto-reload: {args.reload}",
            border_style="cyan"
        ))

        run_server(
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
            reload=args.reload,
        )
        return 0
    except ImportError as e:
        console.print(f"[red]Error: Missing dependencies for visualization server[/]")
        console.print(f"[dim]Run: pip install fastapi uvicorn[/]")
        console.print(f"[dim]Details: {e}[/]")
        return 1
    except Exception as e:
        console.print(f"[red]Error starting server: {e}[/]")
        return 1


def handle_viz_open(args) -> int:
    """Handle `viz open` subcommand - open browser to running server."""
    import webbrowser

    url = f"http://127.0.0.1:{args.port}"
    console.print(f"Opening browser to: {url}")
    webbrowser.open(url)
    return 0


# =============================================================================
# PLAY SUBCOMMAND HANDLERS (Unified Engine)
# =============================================================================

def handle_play_run(args) -> int:
    """
    Handle `play run` subcommand - run Play in specified mode.

    Modes:
        backtest: Historical data simulation
        demo: Real-time data with Bybit demo API (fake money)
        live: Real-time data with Bybit live API (real money)
        shadow: Real-time data with signal logging only (no execution)
    """
    import json
    import yaml
    from pathlib import Path
    from datetime import datetime, timedelta

    mode = args.mode

    # Safety check for live mode
    if mode == "live" and not args.confirm:
        console.print(Panel(
            "[bold red]LIVE TRADING REQUIRES CONFIRMATION[/]\n"
            "[red]You are about to trade with REAL MONEY.[/]\n"
            "[dim]Add --confirm to proceed.[/]",
            border_style="red"
        ))
        return 1

    from src.backtest.play import Play, load_play

    plays_dir = Path(args.plays_dir) if getattr(args, "plays_dir", None) else None
    play_path = Path(args.play)

    try:
        if play_path.exists() and play_path.is_file():
            with open(play_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            play = Play.from_dict(raw)
        else:
            play = load_play(args.play, base_dir=plays_dir)
    except Exception as e:
        console.print(f"[red]Failed to load Play: {e}[/]")
        return 1

    symbols = play.symbol_universe if play.symbol_universe else ["N/A"]
    symbol_str = symbols[0] if len(symbols) == 1 else f"{symbols[0]} (+{len(symbols)-1} more)"

    console.print(Panel(
        f"[bold cyan]Play: {play.name}[/]\n"
        f"[dim]Mode: {mode.upper()}[/]\n"
        f"[dim]Symbol: {symbol_str} | Exec TF: {play.execution_tf}[/]",
        border_style="cyan"
    ))

    from src.engine import PlayEngineFactory, EngineManager

    try:
        # B2: Forward confirm_live to factory
        engine = PlayEngineFactory.create(
            play, mode=mode, confirm_live=getattr(args, "confirm", False),
        )
    except Exception as e:
        console.print(f"[red]Failed to create engine: {e}[/]")
        return 1

    if mode == "backtest":
        return _run_play_backtest(engine, play, args)
    elif mode == "shadow":
        return _run_play_shadow(engine, play, args)
    elif mode in ("demo", "live"):
        # B7: Route through EngineManager for instance limits
        return _run_play_live(play, args, manager=EngineManager.get_instance())

    return 0


def _run_play_backtest(engine, play, args) -> int:
    """Run Play in backtest mode."""
    from datetime import datetime, timedelta

    if args.start:
        start_ts = _parse_datetime(args.start)
    else:
        start_ts = datetime.now() - timedelta(days=30)

    if args.end:
        end_ts = _parse_datetime(args.end)
    else:
        end_ts = datetime.now()

    console.print(f"[dim]Window: {start_ts.date()} to {end_ts.date()}[/]")
    console.print("[yellow]Note: Backtest mode requires full data loading integration.[/]")
    console.print("[yellow]Use 'backtest run' for full backtest functionality for now.[/]")

    return 0


def _run_play_shadow(engine, play, args) -> int:
    """Run Play in shadow mode (signals only, no execution)."""
    import asyncio
    from src.engine.runners import ShadowRunner

    runner = ShadowRunner(engine)

    console.print("[cyan]Starting shadow mode...[/]")
    console.print("[dim]Press Ctrl+C to stop[/]")

    try:
        stats = asyncio.run(runner.run_replay(start_idx=0, end_idx=None))
        console.print(f"\n[green]Shadow run complete:[/]")
        console.print(f"  Bars: {stats.bars_processed}")
        console.print(f"  Signals: {stats.signals_generated}")
        console.print(f"  Long: {stats.long_signals} | Short: {stats.short_signals}")
    except KeyboardInterrupt:
        console.print("\n[yellow]Shadow mode stopped by user[/]")
    except Exception as e:
        console.print(f"\n[red]Shadow mode error: {e}[/]")
        return 1

    return 0


def _run_play_live(play, args, manager=None) -> int:
    """Run Play in live or demo mode via EngineManager."""
    import asyncio
    import signal
    from src.engine import EngineManager

    mode = args.mode
    if manager is None:
        manager = EngineManager.get_instance()

    console.print(f"[cyan]Starting {mode.upper()} mode...[/]")
    console.print("[dim]Press Ctrl+C to stop[/]")

    if mode == "live":
        console.print("[bold red]LIVE TRADING ACTIVE - REAL MONEY[/]")

    instance_id: str | None = None

    async def _run_live():
        nonlocal instance_id
        instance_id = await manager.start(play, mode=mode)
        console.print(f"[dim]Instance: {instance_id}[/]")

        # Wait for the instance to complete
        instance = manager._instances.get(instance_id)
        if instance and instance.task:
            await instance.task

    # B1: Single event loop for start + wait
    # B6: Register signal handlers for graceful shutdown
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # B6: Wire SIGINT/SIGTERM for graceful stop
        def _signal_handler():
            console.print(f"\n[yellow]{mode.upper()} mode: shutdown signal received[/]")
            if instance_id:
                loop.create_task(manager.stop(instance_id))

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _signal_handler)
            except NotImplementedError:
                # Windows does not support add_signal_handler for all signals
                pass

        loop.run_until_complete(_run_live())

    except KeyboardInterrupt:
        console.print(f"\n[yellow]{mode.upper()} mode stopped by user[/]")
        if instance_id:
            loop.run_until_complete(manager.stop(instance_id))
    except Exception as e:
        console.print(f"\n[red]{mode.upper()} mode error: {e}[/]")
        if instance_id:
            try:
                loop.run_until_complete(manager.stop(instance_id))
            except Exception:
                pass
        return 1
    finally:
        loop.close()

    # Print stats from the instance if available
    info = manager.get(instance_id) if instance_id else None
    if info:
        console.print(f"\n[green]{mode.upper()} run complete:[/]")
        console.print(f"  Bars: {info.bars_processed}")
        console.print(f"  Signals: {info.signals_generated}")
    else:
        console.print(f"\n[green]{mode.upper()} run complete.[/]")

    return 0


def handle_play_status(args) -> int:
    """Handle `play status` subcommand - show running instances."""
    from src.engine import EngineManager

    manager = EngineManager.get_instance()
    instances = manager.list()

    if not instances:
        console.print("[dim]No running Play instances.[/]")
        return 0

    table = Table(title="Running Play Instances")
    table.add_column("Instance ID", style="cyan")
    table.add_column("Play", style="white")
    table.add_column("Symbol", style="yellow")
    table.add_column("Mode", style="green")
    table.add_column("Status", style="white")
    table.add_column("Bars", justify="right")
    table.add_column("Signals", justify="right")
    table.add_column("Started", style="dim")

    for info in instances:
        table.add_row(
            info.instance_id,
            info.play_id,
            info.symbol,
            info.mode.value.upper(),
            info.status,
            str(info.bars_processed),
            str(info.signals_generated),
            info.started_at.strftime("%H:%M:%S"),
        )

    console.print(table)
    return 0


def handle_play_stop(args) -> int:
    """Handle `play stop` subcommand - stop a running instance."""
    import asyncio
    from src.engine import EngineManager

    manager = EngineManager.get_instance()
    target = args.play  # instance ID or play name

    # If --all flag, stop everything
    if getattr(args, "all", False):
        count = asyncio.run(manager.stop_all())
        console.print(f"[green]Stopped {count} instance(s).[/]")
        return 0

    # Try to find the instance by ID or play name
    instances = manager.list()
    match = None
    for info in instances:
        if info.instance_id == target or info.play_id == target:
            match = info
            break

    if match is None:
        console.print(f"[red]No running instance found matching '{target}'.[/]")
        console.print("[dim]Use 'play status' to see running instances.[/]")
        return 1

    stopped = asyncio.run(manager.stop(match.instance_id))
    if stopped:
        console.print(f"[green]Stopped instance: {match.instance_id}[/]")
        return 0
    else:
        console.print(f"[red]Failed to stop instance: {match.instance_id}[/]")
        return 1


# =============================================================================
# QA SUBCOMMAND HANDLERS
# =============================================================================

def handle_qa_audit(args) -> int:
    """Handle `qa audit` subcommand - run QA audit agent swarm."""
    from src.qa_swarm import (
        run_qa_audit_sync,
        QAAuditConfig,
        Severity,
        FindingCategory,
        format_report_rich,
        format_report_json,
        format_report_markdown,
        save_report,
    )

    categories = None
    if getattr(args, "categories", None):
        categories = [FindingCategory(c) for c in args.categories]

    config = QAAuditConfig(
        paths=args.paths,
        min_severity=Severity(args.severity),
        categories=categories,
        parallel=not getattr(args, "no_parallel", False),
        timeout_seconds=args.timeout,
        max_findings_per_agent=args.max_findings,
        include_snippets=getattr(args, "verbose", False),
    )

    output_format = getattr(args, "format", "rich")

    if output_format == "rich":
        console.print(Panel(
            f"[bold cyan]QA AUDIT[/]\n"
            f"Paths: {', '.join(config.paths)}\n"
            f"Min Severity: {config.min_severity.value}\n"
            f"Parallel: {config.parallel}",
            border_style="cyan"
        ))

    try:
        report = run_qa_audit_sync(config)
    except Exception as e:
        console.print(f"[bold red]Audit failed: {e}[/]")
        return 1

    output_path = getattr(args, "output", None)

    if output_format == "json":
        json_output = format_report_json(report)
        if output_path:
            save_report(report, output_path, "json")
            console.print(f"[green]Report saved to {output_path}[/]")
        else:
            print(json_output)
    elif output_format == "markdown":
        md_output = format_report_markdown(report)
        if output_path:
            save_report(report, output_path, "markdown")
            console.print(f"[green]Report saved to {output_path}[/]")
        else:
            print(md_output)
    else:
        format_report_rich(report, console, verbose=getattr(args, "verbose", False))

    return 0 if report.pass_status else 1


# =============================================================================
# TEST SUBCOMMAND HANDLERS
# =============================================================================

def handle_test_indicators(args) -> int:
    """Handle `test indicators` subcommand - run indicator validation suite."""
    import json

    tier = getattr(args, "tier", None)
    symbol = getattr(args, "symbol", "BTCUSDT")
    condition = getattr(args, "condition", None)
    fix_gaps = getattr(args, "fix_gaps", True)

    if not args.json_output:
        title = f"INDICATOR TEST SUITE"
        if tier:
            title += f" ({tier})"
        console.print(Panel(
            f"[bold cyan]{title}[/]\n"
            f"Symbol: {symbol} | Fix gaps: {fix_gaps}\n"
            f"Condition: {condition or 'all'}",
            border_style="cyan"
        ))

    from src.testing_agent.runner import run_indicator_suite, run_tier_tests
    from src.testing_agent.reporting import print_suite_report, print_tier_report

    if tier:
        result = run_tier_tests(tier=tier, fix_gaps=fix_gaps, symbol=symbol, condition=condition)
        if args.json_output:
            output = {
                "status": "pass" if result.success else "fail",
                "tier": tier,
                "plays_passed": result.plays_passed,
                "plays_failed": result.plays_failed,
                "indicators": result.indicators_tested,
            }
            print(json.dumps(output, indent=2))
        else:
            print_tier_report(result, tier)
    else:
        result = run_indicator_suite(fix_gaps=fix_gaps, symbol=symbol)
        if args.json_output:
            output = {
                "status": "pass" if result.success else "fail",
                "tiers_passed": result.tiers_passed,
                "tiers_failed": result.tiers_failed,
                "plays_passed": result.plays_passed,
                "plays_failed": result.plays_failed,
                "indicators_covered": result.indicators_covered,
                "duration_seconds": result.duration_seconds,
            }
            print(json.dumps(output, indent=2))
        else:
            print_suite_report(result)

    return 0 if result.success else 1


def handle_test_parity(args) -> int:
    """Handle `test parity` subcommand - incremental vs vectorized parity check."""
    import json

    bars = getattr(args, "bars", 2000)
    tolerance = getattr(args, "tolerance", 1e-6)
    seed = getattr(args, "seed", 42)

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]INCREMENTAL vs VECTORIZED PARITY[/]\n"
            f"Bars: {bars} | Tolerance: {tolerance} | Seed: {seed}",
            border_style="cyan"
        ))

    from src.testing_agent.runner import run_parity_check
    from src.testing_agent.reporting import print_parity_report

    result = run_parity_check(bars=bars, tolerance=tolerance, seed=seed)

    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "indicators_passed": result.indicators_passed,
            "indicators_failed": result.indicators_failed,
            "max_diff": result.max_diff,
            "mean_diff": result.mean_diff,
        }
        print(json.dumps(output, indent=2))
    else:
        print_parity_report(result)

    return 0 if result.success else 1


def handle_test_live_parity(args) -> int:
    """Handle `test live-parity` subcommand - live vs backtest comparison."""
    import json

    tier = getattr(args, "tier", "tier19")
    fix_gaps = getattr(args, "fix_gaps", True)

    if not args.json_output:
        console.print(Panel(
            f"[bold cyan]LIVE vs BACKTEST PARITY[/]\n"
            f"Tier: {tier} | Fix gaps: {fix_gaps}",
            border_style="cyan"
        ))

    from src.testing_agent.runner import run_live_parity
    from src.testing_agent.reporting import print_live_parity_report

    result = run_live_parity(tier=tier, fix_gaps=fix_gaps)

    if args.json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "tier": tier,
            "plays_passed": result.plays_passed,
            "plays_failed": result.plays_failed,
        }
        print(json.dumps(output, indent=2))
    else:
        print_live_parity_report(result, tier)

    return 0 if result.success else 1


def handle_test_agent(args) -> int:
    """Handle `test agent` subcommand - run full testing agent."""
    import json

    mode = getattr(args, "mode", "full")
    fix_gaps = getattr(args, "fix_gaps", True)

    if not args.json_output:
        mode_desc = {
            "full": "Full Suite (BTC + L2 alts)",
            "btc": "BTC Baseline",
            "l2": "L2 Alts (ETH, SOL, LTC, AVAX)",
        }.get(mode, mode)

        console.print(Panel(
            f"[bold cyan]TESTING AGENT[/]\n"
            f"Mode: {mode_desc} | Fix gaps: {fix_gaps}",
            border_style="cyan"
        ))

    from src.testing_agent.runner import run_agent
    from src.testing_agent.reporting import print_agent_report, format_agent_report_json

    result = run_agent(mode=mode, fix_gaps=fix_gaps)

    if args.json_output:
        print(json.dumps(format_agent_report_json(result), indent=2))
    else:
        print_agent_report(result)

    return 0 if result.success else 1
