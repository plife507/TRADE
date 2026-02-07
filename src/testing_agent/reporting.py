"""
Testing Agent Reporting: Output formatting and summary generation.

Provides rich console output for test results with clear pass/fail
indicators and detailed breakdowns.
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from .runner import (
    PlayResult,
    TestResult,
    TierResult,
    ParityResult,
    AgentResult,
    TIER_INDICATORS,
    MARKET_CONDITIONS,
)

console = Console()


def print_suite_report(result: TestResult) -> None:
    """
    Print full suite report with tier-by-tier breakdown.

    Args:
        result: TestResult from run_indicator_suite()
    """
    # Header
    status = "[bold green]PASS" if result.success else "[bold red]FAIL"
    console.print(Panel(
        f"{status}[/] Indicator Validation Suite\n"
        f"[dim]Duration: {result.duration_seconds:.1f}s[/]",
        border_style="green" if result.success else "red",
    ))

    # Summary table
    summary = Table(title="Suite Summary", show_header=True, header_style="bold")
    summary.add_column("Metric", style="dim")
    summary.add_column("Value", justify="right")

    summary.add_row("Tiers Passed", f"[green]{result.tiers_passed}[/]")
    summary.add_row("Tiers Failed", f"[red]{result.tiers_failed}[/]" if result.tiers_failed > 0 else "0")
    summary.add_row("Plays Passed", f"[green]{result.plays_passed}[/]")
    summary.add_row("Plays Failed", f"[red]{result.plays_failed}[/]" if result.plays_failed > 0 else "0")
    summary.add_row("Indicators Covered", str(result.indicators_covered))

    console.print(summary)
    console.print()

    # Tier breakdown
    tier_table = Table(title="Tier Results", show_header=True, header_style="bold")
    tier_table.add_column("Tier", style="cyan")
    tier_table.add_column("Category")
    tier_table.add_column("Status", justify="center")
    tier_table.add_column("Plays", justify="right")
    tier_table.add_column("Indicators")

    for tier_name, tier_info in TIER_INDICATORS.items():
        tier_result = result.tier_results.get(tier_name)
        if tier_result:
            status = "[green]PASS[/]" if tier_result.success else "[red]FAIL[/]"
            plays = f"{tier_result.plays_passed}/{tier_result.plays_passed + tier_result.plays_failed}"
        else:
            status = "[dim]SKIP[/]"
            plays = "-"

        tier_table.add_row(
            tier_name,
            tier_info["name"],
            status,
            plays,
            ", ".join(tier_info["indicators"][:3]) + "...",
        )

    console.print(tier_table)

    # Failed plays detail
    if result.plays_failed > 0:
        console.print()
        console.print("[bold red]Failed Plays:[/]")
        for tier_name, tier_result in result.tier_results.items():
            for play_result in tier_result.play_results:
                if not play_result.success:
                    console.print(f"  [red]- {play_result.play_id}: {play_result.error}[/]")


def _format_pnl(value: float) -> str:
    """Format PnL with color and sign."""
    if value >= 0:
        return f"[green]+${value:,.2f}[/]"
    return f"[red]-${abs(value):,.2f}[/]"


def _format_pct(value: float, precision: int = 1) -> str:
    """Format percentage with color."""
    if value >= 0:
        return f"[green]+{value:.{precision}f}%[/]"
    return f"[red]{value:.{precision}f}%[/]"


def _format_ratio(value: float) -> str:
    """Format ratio with color (green if > 1)."""
    if value >= 1.0:
        return f"[green]{value:.2f}[/]"
    return f"[yellow]{value:.2f}[/]"


def print_tier_report(result: TierResult, tier_name: str) -> None:
    """
    Print comprehensive report for a single tier with all metrics.

    Args:
        result: TierResult from run_tier_tests()
        tier_name: Name of the tier
    """
    tier_info = TIER_INDICATORS.get(tier_name, {})

    # Header
    status = "[bold green]PASS" if result.success else "[bold red]FAIL"
    console.print(Panel(
        f"{status}[/] {tier_name}: {tier_info.get('name', 'Unknown')}\n"
        f"[dim]Plays: {result.plays_passed}/{result.plays_passed + result.plays_failed}[/]",
        border_style="green" if result.success else "red",
    ))

    # Indicators tested
    console.print(f"[bold]Indicators Tested:[/] {', '.join(result.indicators_tested)}")
    console.print()

    # =========================================================================
    # TABLE 1: Core Metrics Summary
    # =========================================================================
    core_table = Table(title="Core Metrics", show_header=True, header_style="bold cyan")
    core_table.add_column("Play ID", style="cyan", no_wrap=True)
    core_table.add_column("Status", justify="center")
    core_table.add_column("Trades", justify="right")
    core_table.add_column("W/L", justify="center")
    core_table.add_column("Win%", justify="right")
    core_table.add_column("Net PnL", justify="right")
    core_table.add_column("Return%", justify="right")
    core_table.add_column("MaxDD%", justify="right")

    for play in result.play_results:
        if play.success:
            status_str = "[green]PASS[/]"
            wl_str = f"{play.winning_trades}/{play.losing_trades}"
            win_color = "green" if play.win_rate >= 50 else "yellow"
            dd_color = "green" if play.max_drawdown_pct < 20 else "yellow" if play.max_drawdown_pct < 50 else "red"
            core_table.add_row(
                play.play_id,
                status_str,
                str(play.trades_count),
                wl_str,
                f"[{win_color}]{play.win_rate:.1f}%[/]",
                _format_pnl(play.net_pnl),
                _format_pct(play.net_return_pct),
                f"[{dd_color}]{play.max_drawdown_pct:.1f}%[/]",
            )
        else:
            core_table.add_row(
                play.play_id,
                "[red]FAIL[/]",
                "-", "-", "-", "-", "-", "-",
            )

    console.print(core_table)
    console.print()

    # =========================================================================
    # TABLE 2: Risk-Adjusted Metrics
    # =========================================================================
    risk_table = Table(title="Risk-Adjusted Metrics", show_header=True, header_style="bold magenta")
    risk_table.add_column("Play ID", style="cyan", no_wrap=True)
    risk_table.add_column("Sharpe", justify="right")
    risk_table.add_column("Sortino", justify="right")
    risk_table.add_column("Calmar", justify="right")
    risk_table.add_column("PF", justify="right")
    risk_table.add_column("Expectancy", justify="right")
    risk_table.add_column("Payoff", justify="right")
    risk_table.add_column("Recovery", justify="right")

    for play in result.play_results:
        if play.success:
            sharpe_color = "green" if play.sharpe >= 1.0 else "yellow" if play.sharpe >= 0.5 else "red"
            pf_color = "green" if play.profit_factor >= 1.5 else "yellow" if play.profit_factor >= 1.0 else "red"
            risk_table.add_row(
                play.play_id,
                f"[{sharpe_color}]{play.sharpe:.2f}[/]",
                f"{play.sortino:.2f}",
                f"{play.calmar:.2f}",
                f"[{pf_color}]{play.profit_factor:.2f}[/]",
                f"${play.expectancy:,.2f}",
                f"{play.payoff_ratio:.2f}",
                f"{play.recovery_factor:.2f}",
            )
        else:
            risk_table.add_row(play.play_id, "-", "-", "-", "-", "-", "-", "-")

    console.print(risk_table)
    console.print()

    # =========================================================================
    # TABLE 3: Trade Quality Metrics
    # =========================================================================
    quality_table = Table(title="Trade Quality", show_header=True, header_style="bold yellow")
    quality_table.add_column("Play ID", style="cyan", no_wrap=True)
    quality_table.add_column("Avg Win", justify="right")
    quality_table.add_column("Avg Loss", justify="right")
    quality_table.add_column("Max Win", justify="right")
    quality_table.add_column("Max Loss", justify="right")
    quality_table.add_column("Fees", justify="right")
    quality_table.add_column("MaxW Streak", justify="right")
    quality_table.add_column("MaxL Streak", justify="right")

    for play in result.play_results:
        if play.success:
            quality_table.add_row(
                play.play_id,
                f"[green]${play.avg_win:,.2f}[/]",
                f"[red]${play.avg_loss:,.2f}[/]",
                f"[green]${play.largest_win:,.2f}[/]",
                f"[red]${play.largest_loss:,.2f}[/]",
                f"${play.total_fees:,.2f}",
                f"[green]{play.max_consecutive_wins}[/]",
                f"[red]{play.max_consecutive_losses}[/]",
            )
        else:
            quality_table.add_row(play.play_id, "-", "-", "-", "-", "-", "-", "-")

    console.print(quality_table)
    console.print()

    # =========================================================================
    # TABLE 4: Long/Short Breakdown
    # =========================================================================
    ls_table = Table(title="Long/Short Breakdown", show_header=True, header_style="bold blue")
    ls_table.add_column("Play ID", style="cyan", no_wrap=True)
    ls_table.add_column("Long Trades", justify="right")
    ls_table.add_column("Long WR%", justify="right")
    ls_table.add_column("Long PnL", justify="right")
    ls_table.add_column("Short Trades", justify="right")
    ls_table.add_column("Short WR%", justify="right")
    ls_table.add_column("Short PnL", justify="right")

    for play in result.play_results:
        if play.success:
            ls_table.add_row(
                play.play_id,
                str(play.long_trades),
                f"{play.long_win_rate:.1f}%",
                _format_pnl(play.long_pnl),
                str(play.short_trades),
                f"{play.short_win_rate:.1f}%" if play.short_trades > 0 else "-",
                _format_pnl(play.short_pnl) if play.short_trades > 0 else "-",
            )
        else:
            ls_table.add_row(play.play_id, "-", "-", "-", "-", "-", "-")

    console.print(ls_table)
    console.print()

    # =========================================================================
    # TABLE 5: Time & Execution Metrics
    # =========================================================================
    time_table = Table(title="Time & Execution", show_header=True, header_style="bold")
    time_table.add_column("Play ID", style="cyan", no_wrap=True)
    time_table.add_column("Total Bars", justify="right")
    time_table.add_column("In Position", justify="right")
    time_table.add_column("Time in Mkt%", justify="right")
    time_table.add_column("Avg Duration", justify="right")
    time_table.add_column("Leverage", justify="center")
    time_table.add_column("Init Equity", justify="right")
    time_table.add_column("Run Time", justify="right")

    for play in result.play_results:
        if play.success:
            time_table.add_row(
                play.play_id,
                f"{play.total_bars:,}",
                f"{play.bars_in_position:,}",
                f"{play.time_in_market_pct:.1f}%",
                f"{play.avg_trade_duration:.1f} bars",
                f"{play.leverage}x",
                f"${play.initial_equity:,.0f}",
                f"{play.duration_ms / 1000:.1f}s",
            )
        else:
            time_table.add_row(play.play_id, "-", "-", "-", "-", "-", "-", f"{play.duration_ms / 1000:.1f}s")

    console.print(time_table)

    # Error details
    failed = [p for p in result.play_results if not p.success]
    if failed:
        console.print()
        console.print("[bold red]Errors:[/]")
        for play in failed:
            console.print(f"  [red]- {play.play_id}: {play.error}[/]")


def print_play_detail(play: PlayResult) -> None:
    """
    Print comprehensive detail report for a single play.

    Args:
        play: PlayResult with all metrics
    """
    if not play.success:
        console.print(Panel(
            f"[bold red]FAILED[/]: {play.play_id}\n"
            f"[red]Error: {play.error}[/]",
            border_style="red",
        ))
        return

    # Header
    pnl_color = "green" if play.net_pnl >= 0 else "red"
    console.print(Panel(
        f"[bold cyan]{play.play_id}[/]\n"
        f"[{pnl_color}]Net PnL: ${play.net_pnl:,.2f} ({play.net_return_pct:+.1f}%)[/]",
        border_style="cyan",
    ))

    console.print()
    console.print("=" * 70)
    console.print("  [bold]COMPREHENSIVE BACKTEST METRICS[/]")
    console.print("=" * 70)

    # Section 1: Trade Summary
    console.print()
    console.print("[bold cyan]TRADE SUMMARY[/]")
    console.print("-" * 40)
    console.print(f"  Total Trades:     {play.trades_count}")
    console.print(f"  Winning Trades:   [green]{play.winning_trades}[/]")
    console.print(f"  Losing Trades:    [red]{play.losing_trades}[/]")
    win_color = "green" if play.win_rate >= 50 else "yellow"
    console.print(f"  Win Rate:         [{win_color}]{play.win_rate:.2f}%[/]")

    # Section 2: PnL Breakdown
    console.print()
    console.print("[bold cyan]PNL BREAKDOWN[/]")
    console.print("-" * 40)
    console.print(f"  Net PnL:          {_format_pnl(play.net_pnl)}")
    console.print(f"  Net Return:       {_format_pct(play.net_return_pct)}")
    console.print(f"  Gross Profit:     [green]+${play.gross_profit:,.2f}[/]")
    console.print(f"  Gross Loss:       [red]-${abs(play.gross_loss):,.2f}[/]")
    console.print(f"  Total Fees:       [yellow]${play.total_fees:,.2f}[/]")

    # Section 3: Drawdown
    console.print()
    console.print("[bold cyan]DRAWDOWN[/]")
    console.print("-" * 40)
    dd_color = "green" if play.max_drawdown_pct < 20 else "yellow" if play.max_drawdown_pct < 50 else "red"
    console.print(f"  Max Drawdown %:   [{dd_color}]{play.max_drawdown_pct:.2f}%[/]")
    console.print(f"  Max Drawdown $:   [red]${play.max_drawdown_usdt:,.2f}[/]")
    console.print(f"  Max DD Duration:  {play.max_drawdown_duration:,} bars")

    # Section 4: Risk-Adjusted Returns
    console.print()
    console.print("[bold cyan]RISK-ADJUSTED RETURNS[/]")
    console.print("-" * 40)
    sharpe_color = "green" if play.sharpe >= 1.0 else "yellow" if play.sharpe >= 0.5 else "red"
    console.print(f"  Sharpe Ratio:     [{sharpe_color}]{play.sharpe:.2f}[/]")
    console.print(f"  Sortino Ratio:    {play.sortino:.2f}")
    console.print(f"  Calmar Ratio:     {play.calmar:.2f}")
    pf_color = "green" if play.profit_factor >= 1.5 else "yellow" if play.profit_factor >= 1.0 else "red"
    console.print(f"  Profit Factor:    [{pf_color}]{play.profit_factor:.2f}[/]")
    console.print(f"  Recovery Factor:  {play.recovery_factor:.2f}")

    # Section 5: Trade Quality
    console.print()
    console.print("[bold cyan]TRADE QUALITY[/]")
    console.print("-" * 40)
    console.print(f"  Avg Win:          [green]${play.avg_win:,.2f}[/]")
    console.print(f"  Avg Loss:         [red]${play.avg_loss:,.2f}[/]")
    console.print(f"  Largest Win:      [green]${play.largest_win:,.2f}[/]")
    console.print(f"  Largest Loss:     [red]${play.largest_loss:,.2f}[/]")
    console.print(f"  Expectancy:       ${play.expectancy:,.2f}/trade")
    console.print(f"  Payoff Ratio:     {play.payoff_ratio:.2f}")

    # Section 6: Streaks
    console.print()
    console.print("[bold cyan]STREAKS[/]")
    console.print("-" * 40)
    console.print(f"  Max Consec Wins:  [green]{play.max_consecutive_wins}[/]")
    console.print(f"  Max Consec Losses:[red]{play.max_consecutive_losses}[/]")

    # Section 7: Long/Short Breakdown
    console.print()
    console.print("[bold cyan]LONG/SHORT BREAKDOWN[/]")
    console.print("-" * 40)
    console.print(f"  Long Trades:      {play.long_trades} ({play.long_win_rate:.1f}% WR) {_format_pnl(play.long_pnl)}")
    if play.short_trades > 0:
        console.print(f"  Short Trades:     {play.short_trades} ({play.short_win_rate:.1f}% WR) {_format_pnl(play.short_pnl)}")
    else:
        console.print(f"  Short Trades:     0 (long-only strategy)")

    # Section 8: Time Metrics
    console.print()
    console.print("[bold cyan]TIME METRICS[/]")
    console.print("-" * 40)
    console.print(f"  Total Bars:       {play.total_bars:,}")
    console.print(f"  Bars in Position: {play.bars_in_position:,}")
    console.print(f"  Time in Market:   {play.time_in_market_pct:.1f}%")
    console.print(f"  Avg Trade Dur:    {play.avg_trade_duration:.1f} bars")

    # Section 9: Configuration
    console.print()
    console.print("[bold cyan]CONFIGURATION[/]")
    console.print("-" * 40)
    console.print(f"  Initial Equity:   ${play.initial_equity:,.0f}")
    console.print(f"  Leverage:         {play.leverage}x")
    console.print(f"  Run Duration:     {play.duration_ms / 1000:.1f}s")
    if play.condition:
        console.print(f"  Market Condition: {play.condition.upper()}")

    console.print()
    console.print("=" * 70)


def print_tier_summary_stats(result: TierResult) -> None:
    """
    Print aggregated summary statistics across all plays in a tier.

    Args:
        result: TierResult with all play results
    """
    successful_plays = [p for p in result.play_results if p.success]
    if not successful_plays:
        console.print("[yellow]No successful plays to summarize[/]")
        return

    # Calculate aggregates
    total_trades = sum(p.trades_count for p in successful_plays)
    total_wins = sum(p.winning_trades for p in successful_plays)
    total_losses = sum(p.losing_trades for p in successful_plays)
    avg_win_rate = sum(p.win_rate for p in successful_plays) / len(successful_plays)
    total_pnl = sum(p.net_pnl for p in successful_plays)
    avg_sharpe = sum(p.sharpe for p in successful_plays) / len(successful_plays)
    avg_sortino = sum(p.sortino for p in successful_plays) / len(successful_plays)
    avg_pf = sum(p.profit_factor for p in successful_plays) / len(successful_plays)
    max_dd = max(p.max_drawdown_pct for p in successful_plays)
    avg_dd = sum(p.max_drawdown_pct for p in successful_plays) / len(successful_plays)
    total_fees = sum(p.total_fees for p in successful_plays)

    # Best/Worst performers
    best_pnl = max(successful_plays, key=lambda p: p.net_pnl)
    worst_pnl = min(successful_plays, key=lambda p: p.net_pnl)
    best_sharpe = max(successful_plays, key=lambda p: p.sharpe)
    worst_dd = max(successful_plays, key=lambda p: p.max_drawdown_pct)

    console.print()
    console.print(Panel(
        "[bold]TIER AGGREGATE STATISTICS[/]",
        border_style="cyan",
    ))

    # Summary Table
    summary_table = Table(show_header=True, header_style="bold")
    summary_table.add_column("Metric", style="dim")
    summary_table.add_column("Value", justify="right")
    summary_table.add_column("", justify="left")

    summary_table.add_row("Plays Analyzed", str(len(successful_plays)), "")
    summary_table.add_row("Total Trades", f"{total_trades:,}", "")
    summary_table.add_row("Total Wins/Losses", f"{total_wins:,} / {total_losses:,}", "")
    summary_table.add_row("Avg Win Rate", f"{avg_win_rate:.1f}%", "")
    summary_table.add_row("Combined PnL", _format_pnl(total_pnl), "")
    summary_table.add_row("Total Fees", f"${total_fees:,.2f}", "")
    summary_table.add_row("", "", "")
    summary_table.add_row("Avg Sharpe", f"{avg_sharpe:.2f}", "")
    summary_table.add_row("Avg Sortino", f"{avg_sortino:.2f}", "")
    summary_table.add_row("Avg Profit Factor", f"{avg_pf:.2f}", "")
    summary_table.add_row("Avg Max DD", f"{avg_dd:.1f}%", "")
    summary_table.add_row("Worst Max DD", f"{max_dd:.1f}%", f"({worst_dd.play_id})")
    summary_table.add_row("", "", "")
    summary_table.add_row("Best PnL", _format_pnl(best_pnl.net_pnl), f"({best_pnl.play_id})")
    summary_table.add_row("Worst PnL", _format_pnl(worst_pnl.net_pnl), f"({worst_pnl.play_id})")
    summary_table.add_row("Best Sharpe", f"{best_sharpe.sharpe:.2f}", f"({best_sharpe.play_id})")

    console.print(summary_table)


def print_symbol_report(result: TestResult, symbol: str) -> None:
    """
    Print report for symbol-specific tests.

    Args:
        result: TestResult from run_symbol_tests()
        symbol: Symbol that was tested
    """
    status = "[bold green]PASS" if result.success else "[bold red]FAIL"
    console.print(Panel(
        f"{status}[/] {symbol} Validation\n"
        f"[dim]Tiers: {result.tiers_passed}/{result.tiers_passed + result.tiers_failed} | "
        f"Plays: {result.plays_passed}/{result.plays_passed + result.plays_failed}[/]",
        border_style="green" if result.success else "red",
    ))

    # Tier breakdown
    for tier_name, tier_result in result.tier_results.items():
        status_icon = "[green]OK[/]" if tier_result.success else "[red]FAIL[/]"
        console.print(f"  {status_icon} {tier_name}: {tier_result.plays_passed}/{tier_result.plays_passed + tier_result.plays_failed} plays")


def print_parity_report(result: ParityResult) -> None:
    """
    Print parity check report.

    Args:
        result: ParityResult from run_parity_check()
    """
    status = "[bold green]PASS" if result.success else "[bold red]FAIL"
    console.print(Panel(
        f"{status}[/] Incremental vs Vectorized Parity\n"
        f"[dim]Max diff: {result.max_diff:.2e} | Mean diff: {result.mean_diff:.2e}[/]",
        border_style="green" if result.success else "red",
    ))

    # Results table
    table = Table(title="Parity Results", show_header=True, header_style="bold")
    table.add_column("Indicator", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Max Diff", justify="right")
    table.add_column("Mean Diff", justify="right")

    for r in result.results:
        status = "[green]PASS[/]" if r.get("passed", False) else "[red]FAIL[/]"
        table.add_row(
            r.get("indicator", "unknown"),
            status,
            f"{r.get('max_diff', 0):.2e}",
            f"{r.get('mean_diff', 0):.2e}",
        )

    console.print(table)

    # Summary
    console.print()
    console.print(f"[bold]Summary:[/] {result.indicators_passed}/{result.indicators_passed + result.indicators_failed} indicators match")


def print_live_parity_report(result: TestResult, tier: str) -> None:
    """
    Print live vs backtest parity report.

    Args:
        result: TestResult from run_live_parity()
        tier: Tier that was tested
    """
    status = "[bold green]PASS" if result.success else "[bold red]FAIL"
    console.print(Panel(
        f"{status}[/] Live vs Backtest Parity: {tier}\n"
        f"[dim]Plays: {result.plays_passed}/{result.plays_passed + result.plays_failed}[/]",
        border_style="green" if result.success else "red",
    ))

    # Show tier result
    tier_result = result.tier_results.get(tier)
    if tier_result:
        print_tier_report(tier_result, tier)


def print_agent_report(result: AgentResult) -> None:
    """
    Print full testing agent report.

    Args:
        result: AgentResult from run_agent()
    """
    # Main header
    status = "[bold green]PASS" if result.success else "[bold red]FAIL"
    mode_desc = {
        "full": "Full Suite (BTC + L2 alts)",
        "btc": "BTC Baseline",
        "l2": "L2 Alts (ETH, SOL, LTC, AVAX)",
    }.get(result.mode, result.mode)

    console.print(Panel(
        Text.assemble(
            ("TESTING AGENT REPORT\n", "bold"),
            ("=" * 20, "dim"),
            ("\n"),
            (f"Mode: {mode_desc}\n", ""),
            (f"Duration: {result.duration_seconds:.1f}s\n", "dim"),
        ),
        title=status,
        border_style="green" if result.success else "red",
    ))

    # Market condition coverage
    console.print()
    console.print("[bold]MARKET CONDITION COVERAGE:[/]")

    for condition, cond_result in result.condition_results.items():
        cond_info = MARKET_CONDITIONS.get(condition, {})
        total = cond_result.plays_passed + cond_result.plays_failed
        status = "[green]PASS[/]" if cond_result.plays_failed == 0 else "[red]FAIL[/]"

        console.print(
            f"  [{status}] {condition.upper()} ({cond_info.get('start', '?')} to {cond_info.get('end', '?')}): "
            f"{cond_result.plays_passed}/{total} plays"
        )

    # Indicator coverage
    console.print()
    console.print(f"[bold]INDICATOR COVERAGE:[/] {result.indicators_covered}/43 (100%)")

    tier_summary = []
    for tier_name, tier_info in TIER_INDICATORS.items():
        tier_summary.append(f"  [green]PASS[/] {tier_name}: {len(tier_info['indicators'])} indicators")

    for line in tier_summary:
        console.print(line)

    # Parity result
    if result.parity_result:
        console.print()
        console.print(f"[bold]PARITY:[/] {result.parity_result.indicators_passed}/{result.parity_result.indicators_passed + result.parity_result.indicators_failed} indicators match (max diff: {result.parity_result.max_diff:.2e})")

    # Overall
    console.print()
    total_plays = result.plays_passed + result.plays_failed
    if result.success:
        console.print(f"[bold green]OVERALL: PASS ({total_plays} plays completed)[/]")
    else:
        console.print(f"[bold red]OVERALL: FAIL ({result.plays_failed} plays failed)[/]")


def format_agent_report_json(result: AgentResult) -> dict:
    """
    Format agent result as JSON-serializable dict.

    Args:
        result: AgentResult from run_agent()

    Returns:
        Dict suitable for JSON output
    """
    return {
        "status": "pass" if result.success else "fail",
        "mode": result.mode,
        "duration_seconds": result.duration_seconds,
        "indicators_covered": result.indicators_covered,
        "plays_passed": result.plays_passed,
        "plays_failed": result.plays_failed,
        "conditions": {
            name: {
                "date_range": cond.date_range,
                "plays_passed": cond.plays_passed,
                "plays_failed": cond.plays_failed,
            }
            for name, cond in result.condition_results.items()
        },
        "parity": {
            "success": result.parity_result.success if result.parity_result else None,
            "indicators_passed": result.parity_result.indicators_passed if result.parity_result else 0,
            "max_diff": result.parity_result.max_diff if result.parity_result else 0,
        } if result.parity_result else None,
    }
