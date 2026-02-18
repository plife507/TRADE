"""
Subcommand handlers for TRADE CLI.

All handle_* functions are module-level and accept an `args` namespace.
They are dispatched from main() in trade_cli.py.

Sections:
- Backtest handlers (handle_backtest_*)
- Debug handlers (handle_debug_*)
- Play handlers (handle_play_*)
- Account/Position handlers
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from rich.panel import Panel
from rich.table import Table

from src.cli.utils import console, BACK

if TYPE_CHECKING:
    from datetime import datetime


# =============================================================================
# SHARED HELPERS
# =============================================================================

def _parse_datetime(dt_str: str) -> datetime:
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
    """Handle synthetic backtest run (no DB access).

    Bars are auto-computed: warmup(play) + 300 trading bars.
    Pattern comes from play's validation: block (CLI can override).
    """
    import json
    import yaml
    from pathlib import Path
    from src.backtest.play import load_play, Play
    from src.backtest.runner import run_backtest_with_gates, RunnerConfig
    from src.backtest.execution_validation import compute_synthetic_bars
    from src.forge.validation import generate_synthetic_candles
    from src.forge.validation.synthetic_data import PatternType
    from src.forge.validation.synthetic_provider import SyntheticCandlesProvider

    plays_dir = Path(args.plays_dir) if getattr(args, "plays_dir", None) else None

    # Load Play - check if it's a file path first
    play_path = Path(args.play)
    if play_path.exists() and play_path.is_file():
        with open(play_path, "r", encoding="utf-8", newline='\n') as f:
            raw = yaml.safe_load(f)
        play = Play.from_dict(raw)
    else:
        play = load_play(args.play, base_dir=plays_dir)

    # Require validation: block in play YAML
    if play.validation is None:
        console.print(
            f"[bold red]ERROR:[/] Play '{args.play}' has no validation: block.\n"
            f"Add a validation: section with pattern: to the play YAML.",
        )
        return 1

    # CLI overrides (optional)
    cli_bars = getattr(args, "synthetic_bars", None)
    cli_seed = getattr(args, "synthetic_seed", None)
    cli_pattern = getattr(args, "synthetic_pattern", None)

    # Auto-compute bars from indicator/structure warmup requirements
    synthetic_bars = cli_bars if cli_bars is not None else compute_synthetic_bars(play)
    synthetic_seed = cli_seed if cli_seed is not None else 42
    synthetic_pattern = cli_pattern if cli_pattern is not None else play.validation.pattern

    exec_tf = play.exec_tf
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

    has_cli_overrides = any(x is not None for x in [cli_bars, cli_seed, cli_pattern])
    source = "play+CLI" if has_cli_overrides else "auto (from indicator/structure warmup)"
    if not getattr(args, "json_output", False):
        console.print(Panel(
            f"[bold cyan]BACKTEST RUN (SYNTHETIC)[/]\n"
            f"Play: {args.play}\n"
            f"Bars: {synthetic_bars} | Seed: {synthetic_seed} | Pattern: {synthetic_pattern} ({source})\n"
            f"TFs: {sorted(required_tfs)}",
            border_style="cyan"
        ))

    # Generate synthetic candles
    candles = generate_synthetic_candles(
        symbol=play.symbol_universe[0] if play.symbol_universe else "BTCUSDT",
        timeframes=list(required_tfs),
        bars_per_tf=synthetic_bars,
        seed=synthetic_seed,
        pattern=cast(PatternType, synthetic_pattern),
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
    import logging
    from pathlib import Path
    from src.tools.backtest_play_tools import backtest_run_play_tool
    from src.tools.shared import ToolResult

    # 7.2/7.5: Enable debug tracing if --debug flag on backtest run
    if getattr(args, "debug", False):
        from src.utils.debug import enable_debug
        enable_debug(True)
        # Set console handler to DEBUG so trace output is visible
        trade_logger = logging.getLogger("trade")
        trade_logger.setLevel(logging.DEBUG)
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setLevel(logging.DEBUG)

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
        sync=args.sync,
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

    if result.data and result.data.get("preflight"):
        _print_preflight_diagnostics(result.data["preflight"])

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

    if args.sync and not args.json_output:
        console.print("[dim]Auto-sync enabled: will fetch missing data if needed[/]")

    result = backtest_preflight_play_tool(
        play_id=args.play,
        env=args.data_env,
        start=start,
        end=end,
        sync=args.sync,
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
            f"Sync to now: {args.sync_to_now} | Sync: {args.sync} | Heal: {args.heal}",
            border_style="cyan"
        ))

    result = backtest_data_fix_tool(
        play_id=args.play,
        env=args.data_env,
        start=start,
        sync_to_now=args.sync_to_now,
        sync=args.sync,
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
        assert result.data is not None
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


# =============================================================================
# DEBUG SUBCOMMAND HANDLERS
# =============================================================================

def handle_debug_math_parity(args) -> int:
    """Handle `debug math-parity` subcommand - indicator math parity audit."""
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


def handle_debug_snapshot_plumbing(args) -> int:
    """Handle `debug snapshot-plumbing` subcommand - Phase 4 plumbing parity."""
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
            console.print(f"  high_tf_idx: {mismatch.get('high_tf_idx')}")
            console.print(f"  target_idx: {mismatch.get('target_idx')}")
        return 1


def handle_debug_determinism(args) -> int:
    """Handle `debug determinism` subcommand - Phase 3 hash-based verification."""
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
            sync=args.sync,
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


def handle_debug_metrics(args) -> int:
    """Handle `debug metrics` subcommand - standalone metrics audit."""
    import json
    from src.cli.validate import _gate_metrics_audit

    result = _gate_metrics_audit()

    if getattr(args, "json_output", False):
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.passed else 1

    status = "[bold green]PASS[/]" if result.passed else "[bold red]FAIL[/]"
    console.print(f"\n{status} Metrics Audit: {result.checked} scenarios")
    if result.failures:
        for f in result.failures:
            console.print(f"  [red]{f}[/]")
    return 0 if result.passed else 1


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

    # G15.1: Auto-run pre-live validation gate for live mode
    if mode == "live":
        from src.cli.validate import run_validation, Tier
        console.print("[cyan]Running pre-live validation gate...[/]")
        gate_result = run_validation(Tier.PRE_LIVE, play_id=args.play)
        if gate_result != 0:
            console.print("[bold red]Pre-live validation FAILED. Cannot start live trading.[/]")
            return 1
        console.print("[green]Pre-live validation passed.[/]")

    from src.backtest.play import Play, load_play

    plays_dir = Path(args.plays_dir) if getattr(args, "plays_dir", None) else None
    play_path = Path(args.play)

    try:
        if play_path.exists() and play_path.is_file():
            with open(play_path, "r", encoding="utf-8", newline='\n') as f:
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
        f"[dim]Symbol: {symbol_str} | Exec TF: {play.exec_tf}[/]",
        border_style="cyan"
    ))

    from src.utils.debug import is_debug_enabled
    if is_debug_enabled() and mode in ("demo", "live"):
        console.print(Panel(
            "[bold yellow]DEBUG MODE ACTIVE[/]\n"
            "[dim]Full tracebacks, indicator snapshots, and rule evaluation details enabled.\n"
            "Log level: DEBUG | All output goes to console + log file.[/]",
            border_style="yellow"
        ))

    # Backtest mode: delegate to backtest_run_play_tool (golden path)
    # No need to create PlayEngineFactory engine -- the tool creates its own
    # via create_engine_from_play + run_engine_with_play.
    if mode == "backtest":
        return _run_play_backtest(play, args)

    from src.engine import PlayEngineFactory, EngineManager

    if mode == "shadow":
        # Shadow mode: factory creates engine directly (no manager)
        try:
            engine = PlayEngineFactory.create(
                play, mode=mode, confirm_live=False,
            )
        except Exception as e:
            from src.utils.debug import is_debug_enabled
            if is_debug_enabled():
                import traceback
                console.print(f"[red]Failed to create engine:[/]")
                console.print(f"[red]{traceback.format_exc()}[/]")
            else:
                console.print(f"[red]Failed to create engine: {e}[/]")
            return 1
        return _run_play_shadow(engine, play, args)
    elif mode in ("demo", "live"):
        # C5: Manager creates the engine -- do NOT create one here via factory
        # (the old code created a factory engine that was thrown away)
        return _run_play_live(play, args, manager=EngineManager.get_instance())

    return 0


def _run_play_backtest(play, args) -> int:
    """Run Play in backtest mode via backtest_run_play_tool (golden path).

    Delegates to the same tool that ``backtest run`` uses, so behaviour is
    identical regardless of which CLI entry-point the user chooses.
    """
    import json
    from pathlib import Path
    from src.tools.backtest_play_tools import backtest_run_play_tool

    start = _parse_datetime(args.start) if args.start else None
    end = _parse_datetime(args.end) if args.end else None
    plays_dir = Path(args.plays_dir) if getattr(args, "plays_dir", None) else None
    json_output = getattr(args, "json_output", False)

    result = backtest_run_play_tool(
        play_id=play.id,
        env=getattr(args, "data_env", "live"),
        start=start,
        end=end,
        smoke=getattr(args, "smoke", False),
        write_artifacts=not getattr(args, "no_artifacts", False),
        plays_dir=plays_dir,
        emit_snapshots=getattr(args, "emit_snapshots", False),
        sync=getattr(args, "sync", True),
    )

    if json_output:
        output = {
            "status": "pass" if result.success else "fail",
            "message": result.message if result.success else result.error,
            "data": result.data,
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if result.success else 1

    if result.data and "preflight" in result.data:
        _print_preflight_diagnostics(result.data["preflight"])

    if result.success:
        console.print(f"\n[bold green]OK {result.message}[/]")
        if result.data and "artifact_dir" in result.data:
            console.print(f"[dim]Artifacts: {result.data['artifact_dir']}[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {result.error}[/]")
        return 1


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
    """Run Play in live or demo mode via EngineManager.

    Launches the engine in a background thread and runs the Rich Live
    dashboard in the main thread for flicker-free rendering.
    """
    import asyncio
    import logging
    import signal
    import threading
    from src.engine import EngineManager
    from src.cli.live_dashboard import (
        DashboardLogHandler,
        DashboardState,
        populate_play_meta,
        run_dashboard,
    )

    mode = args.mode
    if manager is None:
        manager = EngineManager.get_instance()

    symbol = play.symbol_universe[0] if play.symbol_universe else "N/A"

    # --- Dashboard state (shared between engine thread + display thread) ---
    dash_state = DashboardState(
        play_name=play.name,
        description=play.description.split("\n")[0].strip() if play.description else "",
        symbol=symbol,
        mode=mode.upper(),
        exec_tf=play.exec_tf,
        leverage=play.account.max_leverage,
    )

    # --- Populate static play metadata ---
    populate_play_meta(dash_state, play)

    # --- Log handler: intercept logger output for the dashboard ---
    dash_handler = DashboardLogHandler(max_lines=50, max_actions=20)
    dash_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))

    # Attach to the main trading logger and suppress its console handler
    trade_logger = logging.getLogger("trade")
    original_handlers = list(trade_logger.handlers)
    console_handlers = [h for h in trade_logger.handlers if isinstance(h, logging.StreamHandler)
                        and not isinstance(h, logging.FileHandler)]
    for h in console_handlers:
        trade_logger.removeHandler(h)
    trade_logger.addHandler(dash_handler)

    stop_event = threading.Event()
    instance_id: str | None = None
    engine_error: Exception | None = None
    captured_info: object = None
    captured_runner_stats: dict | None = None

    def _engine_thread():
        """Run the async engine in a background thread.

        Watches stop_event and performs graceful shutdown on its OWN
        event loop (avoids 'Future attached to a different loop').
        """
        nonlocal instance_id, engine_error, captured_info, captured_runner_stats
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async def _run():
                nonlocal instance_id, captured_info, captured_runner_stats
                instance_id = await manager.start(play, mode=mode)
                instance = manager._instances.get(instance_id)
                if not instance or not instance.task:
                    return

                # Wait for engine task OR stop signal from dashboard
                while not instance.task.done():
                    if stop_event.is_set():
                        captured_info = manager.get(instance_id)
                        captured_runner_stats = manager.get_runner_stats(instance_id)
                        try:
                            await asyncio.wait_for(
                                manager.stop(instance_id), timeout=15.0
                            )
                        except (asyncio.TimeoutError, Exception):
                            pass
                        return
                    await asyncio.sleep(0.25)

            loop.run_until_complete(_run())
        except Exception as e:
            engine_error = e
        finally:
            loop.close()
            stop_event.set()

    # --- Start engine in background thread ---
    engine_thread = threading.Thread(target=_engine_thread, daemon=True)
    engine_thread.start()

    # --- Run dashboard in main thread (blocks until stop_event) ---
    try:
        run_dashboard(
            manager=manager,
            state=dash_state,
            handler=dash_handler,
            stop_event=stop_event,
            refresh_hz=4.0,
        )
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()  # Signal engine thread to shut down

    # Wait for engine thread to finish (it handles its own stop on its loop)
    engine_thread.join(timeout=20.0)

    # --- Restore logger handlers ---
    trade_logger.removeHandler(dash_handler)
    for h in console_handlers:
        trade_logger.addHandler(h)

    # --- Print final summary ---
    if engine_error:
        from src.utils.debug import is_debug_enabled
        if is_debug_enabled():
            import traceback as tb
            console.print(f"\n[red]{mode.upper()} mode error:[/]")
            console.print(f"[red]{tb.format_exception(engine_error)}[/]")
        else:
            console.print(f"\n[red]{mode.upper()} mode error: {engine_error}[/]")
        return 1

    if captured_info:
        console.print(f"\n[green]{mode.upper()} run complete:[/]")
        console.print(f"  Bars: {captured_info.bars_processed}")
        console.print(f"  Signals: {captured_info.signals_generated}")
        if captured_runner_stats:
            fills = captured_runner_stats.get("orders_filled", 0)
            if fills:
                console.print(f"  Fills: {fills}")
    else:
        console.print(f"\n[green]{mode.upper()} run complete.[/]")

    return 0


def handle_play_status(args) -> int:
    """Handle `play status` subcommand - show running instances."""
    import json
    from src.engine import EngineManager

    manager = EngineManager.get_instance()
    instances = manager.list_all()

    # Filter by play ID if specified
    play_filter = getattr(args, "play", None)
    if play_filter:
        instances = [i for i in instances if i.play_id == play_filter or i.instance_id == play_filter]

    if not instances:
        if getattr(args, "json_output", False):
            console.print(json.dumps({"instances": []}))
        else:
            console.print("[dim]No running Play instances.[/]")
        return 0

    if getattr(args, "json_output", False):
        data = []
        for info in instances:
            entry = info.to_dict()
            stats = manager.get_runner_stats(info.instance_id)
            if stats:
                entry["stats"] = stats
            data.append(entry)
        console.print(json.dumps({"instances": data}, indent=2))
        return 0

    table = Table(title="Running Play Instances")
    table.add_column("Instance ID", style="cyan")
    table.add_column("Play", style="white")
    table.add_column("Symbol", style="yellow")
    table.add_column("Mode", style="green")
    table.add_column("Status", style="white")
    table.add_column("Bars", justify="right")
    table.add_column("Signals", justify="right")
    table.add_column("Orders", justify="right", style="dim")
    table.add_column("Reconnects", justify="right", style="dim")
    table.add_column("Duration", style="dim")
    table.add_column("Last Candle", style="dim")

    for info in instances:
        stats = manager.get_runner_stats(info.instance_id)
        orders_str = ""
        reconnects_str = ""
        duration_str = ""
        last_candle_str = ""

        if stats:
            submitted = stats.get("orders_submitted", 0)
            filled = stats.get("orders_filled", 0)
            failed = stats.get("orders_failed", 0)
            orders_str = f"{submitted}/{filled}/{failed}"
            reconnects_str = str(stats.get("reconnect_count", 0))
            secs = stats.get("duration_seconds", 0)
            mins, s = divmod(int(secs), 60)
            hrs, m = divmod(mins, 60)
            duration_str = f"{hrs}h{m:02d}m" if hrs else f"{m}m{s:02d}s"
            last_candle_str = stats.get("last_candle_ts", "")[:19] if stats.get("last_candle_ts") else ""

        table.add_row(
            info.instance_id,
            info.play_id,
            info.symbol,
            info.mode.value.upper(),
            info.status,
            str(info.bars_processed),
            str(info.signals_generated),
            orders_str,
            reconnects_str,
            duration_str,
            last_candle_str,
        )

    console.print(table)
    return 0


def handle_play_stop(args) -> int:
    """Handle `play stop` subcommand - stop a running instance."""
    import asyncio
    from src.engine import EngineManager

    manager = EngineManager.get_instance()

    # If --all flag, stop everything
    if getattr(args, "all", False):
        instances = manager.list()
        if not instances:
            console.print("[dim]No running instances to stop.[/]")
            return 0

        # Check for positions if --close-positions
        if getattr(args, "close_positions", False):
            try:
                from src.tools.position_tools import list_open_positions_tool
                result = list_open_positions_tool()
                if result.success and result.data:
                    positions = result.data.get("positions", [])
                    if positions:
                        console.print(f"[yellow]Closing {len(positions)} open position(s) first...[/]")
                        from src.tools.position_tools import panic_close_all_tool
                        close_result = panic_close_all_tool(reason="play stop --all --close-positions")
                        if close_result.success:
                            console.print("[green]All positions closed.[/]")
                        else:
                            console.print(f"[red]Failed to close positions: {close_result.error}[/]")
            except Exception as e:
                console.print(f"[yellow]Could not check positions: {e}[/]")

        count = asyncio.run(manager.stop_all())
        console.print(f"[green]Stopped {count} instance(s).[/]")
        return 0

    target = getattr(args, "play", None)
    if not target:
        console.print("[red]Specify --play ID or --all to stop instances.[/]")
        return 1

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

    # Check for open positions unless --force
    if not getattr(args, "force", False) and not getattr(args, "close_positions", False):
        try:
            from src.tools.position_tools import list_open_positions_tool
            result = list_open_positions_tool(symbol=match.symbol)
            if result.success and result.data:
                positions = result.data.get("positions", [])
                if positions:
                    console.print(f"[yellow]Warning: {len(positions)} open position(s) for {match.symbol}[/]")
                    for pos in positions:
                        side = pos.get("side", "?")
                        size = pos.get("size", "?")
                        pnl = pos.get("unrealized_pnl", "?")
                        console.print(f"  {side} {size} (PnL: {pnl})")
                    console.print("[dim]Use --force to stop anyway, or --close-positions to close first.[/]")
                    return 1
        except Exception:
            pass  # If we can't check positions, proceed with stop

    # Close positions if requested
    if getattr(args, "close_positions", False):
        try:
            from src.tools.position_tools import close_position_tool
            close_result = close_position_tool(symbol=match.symbol)
            if close_result.success:
                console.print(f"[green]Position closed for {match.symbol}.[/]")
            else:
                console.print(f"[yellow]No position to close or close failed: {close_result.error}[/]")
        except Exception as e:
            console.print(f"[yellow]Could not close position: {e}[/]")

    stopped = asyncio.run(manager.stop(match.instance_id))
    if stopped:
        console.print(f"[green]Stopped instance: {match.instance_id}[/]")
        return 0
    else:
        console.print(f"[red]Failed to stop instance: {match.instance_id}[/]")
        return 1


def handle_play_watch(args) -> int:
    """Handle `play watch` subcommand - live dashboard for running instances."""
    import json
    import time as _time
    from src.engine import EngineManager
    from rich.live import Live
    from rich.layout import Layout

    manager = EngineManager.get_instance()
    interval = getattr(args, "interval", 2.0)
    play_filter = getattr(args, "play", None)

    def _build_display() -> Table:
        """Build the dashboard table."""
        instances = manager.list()
        if play_filter:
            instances = [i for i in instances if i.play_id == play_filter or i.instance_id == play_filter]

        if not instances:
            table = Table(title="Play Watch -- No Running Instances", border_style="dim")
            table.add_column("Info")
            table.add_row("[dim]Waiting for instances... (Ctrl+C to exit)[/]")
            return table

        table = Table(title="Play Watch (live)", border_style="cyan")
        table.add_column("Play", style="cyan")
        table.add_column("Symbol", style="yellow")
        table.add_column("Mode", style="green")
        table.add_column("Status", style="white")
        table.add_column("Bars", justify="right")
        table.add_column("Signals", justify="right")
        table.add_column("Orders (sub/fill/fail)", justify="right", style="dim")
        table.add_column("Reconnects", justify="right")
        table.add_column("Duration", style="dim")
        table.add_column("Last Candle", style="dim")

        for info in instances:
            stats = manager.get_runner_stats(info.instance_id)
            orders_str = ""
            reconnects_str = ""
            duration_str = ""
            last_candle_str = ""

            if stats:
                sub = stats.get("orders_submitted", 0)
                fill = stats.get("orders_filled", 0)
                fail = stats.get("orders_failed", 0)
                orders_str = f"{sub}/{fill}/{fail}"
                reconnects_str = str(stats.get("reconnect_count", 0))
                secs = stats.get("duration_seconds", 0)
                mins, s = divmod(int(secs), 60)
                hrs, m = divmod(mins, 60)
                duration_str = f"{hrs}h{m:02d}m" if hrs else f"{m}m{s:02d}s"
                lc = stats.get("last_candle_ts")
                last_candle_str = lc[:19] if lc else ""

            table.add_row(
                info.play_id,
                info.symbol,
                info.mode.value.upper(),
                info.status,
                str(info.bars_processed),
                str(info.signals_generated),
                orders_str,
                reconnects_str,
                duration_str,
                last_candle_str,
            )

        return table

    console.print("[dim]Press Ctrl+C to exit watch (does not stop the engine)[/]")

    try:
        with Live(_build_display(), console=console, refresh_per_second=1) as live:
            while True:
                _time.sleep(interval)
                live.update(_build_display())
    except KeyboardInterrupt:
        console.print("\n[dim]Watch stopped.[/]")

    return 0


def handle_play_logs(args) -> int:
    """Handle `play logs` subcommand - stream journal/log for an instance."""
    import json
    import time as _time
    from pathlib import Path

    play_id = args.play
    follow = getattr(args, "follow", False)
    num_lines = getattr(args, "lines", 50)

    # Find journal file in ~/.trade/journal/
    journal_dir = Path.home() / ".trade" / "journal"
    if not journal_dir.exists():
        console.print("[dim]No journal directory found.[/]")
        return 0

    # Find matching journal file
    matches = list(journal_dir.glob(f"*{play_id}*.jsonl"))
    if not matches:
        # Also check instance files to resolve play_id -> instance_id
        instances_dir = Path.home() / ".trade" / "instances"
        if instances_dir.exists():
            for path in instances_dir.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if data.get("play_id") == play_id:
                        iid = data.get("instance_id", "")
                        matches = list(journal_dir.glob(f"*{iid}*.jsonl"))
                        break
                except Exception:
                    continue

    if not matches:
        console.print(f"[dim]No logs found for '{play_id}'.[/]")
        return 0

    journal_path = matches[0]
    console.print(f"[dim]Reading: {journal_path}[/]")

    # Read last N lines
    try:
        lines = journal_path.read_text(encoding="utf-8").strip().split("\n")
        display_lines = lines[-num_lines:] if len(lines) > num_lines else lines

        for line in display_lines:
            try:
                entry = json.loads(line)
                ts = entry.get("timestamp", "")[:19]
                event = entry.get("event", "?")
                symbol = entry.get("symbol", "")
                direction = entry.get("direction", "")
                if event == "fill":
                    price = entry.get("fill_price", "?")
                    console.print(f"  {ts} [green]FILL[/] {symbol} {direction} @ {price}")
                elif event == "signal":
                    size = entry.get("size_usdt", "?")
                    console.print(f"  {ts} [cyan]SIGNAL[/] {symbol} {direction} ${size}")
                elif event == "error":
                    err = entry.get("error", "?")
                    console.print(f"  {ts} [red]ERROR[/] {symbol} {err}")
                else:
                    console.print(f"  {ts} {event} {line[:80]}")
            except json.JSONDecodeError:
                console.print(f"  {line[:100]}")

    except Exception as e:
        console.print(f"[red]Error reading logs: {e}[/]")
        return 1

    # Follow mode
    if follow:
        console.print("[dim]Following... (Ctrl+C to stop)[/]")
        try:
            with open(journal_path, "r", encoding="utf-8") as f:
                f.seek(0, 2)  # Seek to end
                while True:
                    line = f.readline()
                    if line:
                        try:
                            entry = json.loads(line)
                            ts = entry.get("timestamp", "")[:19]
                            event = entry.get("event", "?")
                            symbol = entry.get("symbol", "")
                            console.print(f"  {ts} [{event}] {symbol} {line.strip()[:80]}")
                        except json.JSONDecodeError:
                            console.print(f"  {line.strip()[:100]}")
                    else:
                        _time.sleep(0.5)
        except KeyboardInterrupt:
            console.print("\n[dim]Stopped following.[/]")

    return 0


def handle_play_pause(args) -> int:
    """Handle `play pause` subcommand."""
    import json
    from pathlib import Path

    play_id = args.play
    pause_dir = Path.home() / ".trade" / "instances"
    pause_dir.mkdir(parents=True, exist_ok=True)

    # Find matching instance
    for path in pause_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("play_id") == play_id or data.get("instance_id") == play_id:
                instance_id = data.get("instance_id", play_id)
                pause_file = pause_dir / f"{instance_id}.pause"
                pause_file.touch()
                console.print(f"[yellow]Paused: {instance_id}[/]")
                console.print("[dim]Indicators continue updating. Use 'play resume' to resume signal evaluation.[/]")
                return 0
        except Exception:
            continue

    console.print(f"[red]No running instance found matching '{play_id}'.[/]")
    return 1


def handle_play_resume(args) -> int:
    """Handle `play resume` subcommand."""
    import json
    from pathlib import Path

    play_id = args.play
    pause_dir = Path.home() / ".trade" / "instances"

    if not pause_dir.exists():
        console.print(f"[red]No running instance found matching '{play_id}'.[/]")
        return 1

    # Find and remove matching pause file
    for path in pause_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("play_id") == play_id or data.get("instance_id") == play_id:
                instance_id = data.get("instance_id", play_id)
                pause_file = pause_dir / f"{instance_id}.pause"
                if pause_file.exists():
                    pause_file.unlink()
                    console.print(f"[green]Resumed: {instance_id}[/]")
                else:
                    console.print(f"[dim]{instance_id} was not paused.[/]")
                return 0
        except Exception:
            continue

    console.print(f"[red]No running instance found matching '{play_id}'.[/]")
    return 1


# =============================================================================
# ACCOUNT SUBCOMMAND HANDLERS (G15.6)
# =============================================================================

def handle_account_balance(args) -> int:
    """Handle `account balance` subcommand."""
    import json
    from src.tools.account_tools import get_account_balance_tool

    result = get_account_balance_tool()
    if not result.success:
        console.print(f"[red]Failed to get balance: {result.error}[/]")
        return 1

    if getattr(args, "json_output", False):
        console.print(json.dumps(result.data, indent=2))
    else:
        data = result.data or {}
        equity = data.get("equity", "N/A")
        available = data.get("available_balance", "N/A")
        wallet = data.get("wallet_balance", "N/A")
        console.print(f"[bold]Account Balance[/]")
        console.print(f"  Equity:    ${equity}")
        console.print(f"  Available: ${available}")
        console.print(f"  Wallet:    ${wallet}")
    return 0


def handle_account_exposure(args) -> int:
    """Handle `account exposure` subcommand."""
    import json
    from src.tools.account_tools import get_total_exposure_tool

    result = get_total_exposure_tool()
    if not result.success:
        console.print(f"[red]Failed to get exposure: {result.error}[/]")
        return 1

    if getattr(args, "json_output", False):
        console.print(json.dumps(result.data, indent=2))
    else:
        data = result.data or {}
        total = data.get("exposure_usd", "N/A")
        console.print(f"[bold]Total Exposure:[/] ${total}")
    return 0


def handle_position_list(args) -> int:
    """Handle `position list` subcommand."""
    import json
    from src.tools.position_tools import list_open_positions_tool

    result = list_open_positions_tool()
    if not result.success:
        console.print(f"[red]Failed to list positions: {result.error}[/]")
        return 1

    if getattr(args, "json_output", False):
        console.print(json.dumps(result.data, indent=2))
        return 0

    positions = (result.data or {}).get("positions", [])
    if not positions:
        console.print("[dim]No open positions.[/]")
        return 0

    table = Table(title="Open Positions")
    table.add_column("Symbol", style="cyan")
    table.add_column("Side", style="white")
    table.add_column("Size", justify="right")
    table.add_column("Entry", justify="right")
    table.add_column("Current", justify="right")
    table.add_column("PnL", justify="right")
    table.add_column("PnL %", justify="right")

    for pos in positions:
        pnl = float(pos.get("unrealized_pnl", 0))
        pnl_style = "green" if pnl >= 0 else "red"
        table.add_row(
            pos.get("symbol", "?"),
            pos.get("side", "?"),
            str(pos.get("size", "?")),
            f"${float(pos.get('entry_price', 0)):,.2f}",
            f"${float(pos.get('current_price', 0)):,.2f}",
            f"[{pnl_style}]${pnl:,.2f}[/]",
            f"[{pnl_style}]{float(pos.get('unrealized_pnl_percent', 0)):.2f}%[/]",
        )

    console.print(table)
    return 0


def handle_position_close(args) -> int:
    """Handle `position close SYMBOL` subcommand."""
    from src.tools.position_tools import close_position_tool

    symbol = args.symbol.upper()
    console.print(f"[yellow]Closing position for {symbol}...[/]")

    result = close_position_tool(symbol=symbol)
    if result.success:
        console.print(f"[green]Position closed for {symbol}.[/]")
        return 0
    else:
        console.print(f"[red]Failed to close position: {result.error}[/]")
        return 1


def handle_panic(args) -> int:
    """Handle `panic` subcommand - emergency close all."""
    if not getattr(args, "confirm", False):
        console.print(Panel(
            "[bold red]EMERGENCY PANIC CLOSE[/]\n"
            "[red]This will cancel ALL orders and close ALL positions immediately.[/]\n"
            "[dim]Add --confirm to proceed.[/]",
            border_style="red"
        ))
        return 1

    from src.tools.position_tools import panic_close_all_tool

    console.print("[bold red]PANIC: Closing all positions and cancelling all orders...[/]")
    result = panic_close_all_tool(reason="CLI panic command")
    if result.success:
        console.print("[green]All positions closed, all orders cancelled.[/]")
        return 0
    else:
        console.print(f"[red]Panic close encountered errors: {result.error}[/]")
        return 1
