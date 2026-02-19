"""Debug subcommand handlers for TRADE CLI."""

from __future__ import annotations

from rich.panel import Panel

from src.cli.utils import console


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
