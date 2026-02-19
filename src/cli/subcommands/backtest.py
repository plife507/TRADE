"""Backtest subcommand handlers for TRADE CLI."""

from __future__ import annotations

from typing import cast

from rich.panel import Panel

from src.cli.utils import console
from src.cli.subcommands._helpers import _parse_datetime, _print_preflight_diagnostics


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
    from src.tools.backtest_play_tools import backtest_preflight_play_tool
    from src.tools.backtest_play_data_tools import backtest_data_fix_tool

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
    from src.tools.backtest_play_data_tools import backtest_indicators_tool

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
    from src.tools.backtest_play_data_tools import backtest_data_fix_tool

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
    from src.tools.backtest_play_data_tools import backtest_list_plays_tool

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
    from src.tools.backtest_play_normalize_tools import backtest_play_normalize_tool

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
    from src.tools.backtest_play_normalize_tools import backtest_play_normalize_batch_tool

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
