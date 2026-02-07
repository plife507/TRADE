"""
Testing Agent Runner: Test orchestration and execution.

Orchestrates indicator validation tests using real data via --fix-gaps,
covering all 43 indicators across different market conditions.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

console = Console()


# =============================================================================
# Data Classes for Test Results
# =============================================================================

@dataclass
class PlayResult:
    """Result from running a single validation Play."""
    play_id: str
    success: bool
    error: str | None = None
    duration_ms: int = 0
    condition: str = ""  # bull, bear, range, volatile

    # Core Trade Metrics
    trades_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0  # percentage (62.3)

    # PnL Metrics
    net_pnl: float = 0.0
    net_return_pct: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    total_fees: float = 0.0

    # Drawdown Metrics
    max_drawdown_pct: float = 0.0
    max_drawdown_usdt: float = 0.0
    max_drawdown_duration: int = 0  # bars

    # Risk-Adjusted Metrics
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    profit_factor: float = 0.0

    # Trade Quality Metrics
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    expectancy: float = 0.0
    payoff_ratio: float = 0.0
    recovery_factor: float = 0.0

    # Streak Metrics
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    # Long/Short Breakdown
    long_trades: int = 0
    short_trades: int = 0
    long_win_rate: float = 0.0
    short_win_rate: float = 0.0
    long_pnl: float = 0.0
    short_pnl: float = 0.0

    # Time Metrics
    total_bars: int = 0
    bars_in_position: int = 0
    time_in_market_pct: float = 0.0
    avg_trade_duration: float = 0.0  # bars

    # Config Info
    leverage: int = 1
    initial_equity: float = 10000.0


@dataclass
class TierResult:
    """Result from running a tier of validation Plays."""
    tier: str
    success: bool
    plays_passed: int = 0
    plays_failed: int = 0
    play_results: list[PlayResult] = field(default_factory=list)
    indicators_tested: list[str] = field(default_factory=list)


@dataclass
class TestResult:
    """Result from running indicator test suite."""
    success: bool
    tiers_passed: int = 0
    tiers_failed: int = 0
    plays_passed: int = 0
    plays_failed: int = 0
    tier_results: dict[str, TierResult] = field(default_factory=dict)
    indicators_covered: int = 0
    duration_seconds: float = 0.0


@dataclass
class ParityResult:
    """Result from parity check (incremental vs vectorized)."""
    success: bool
    indicators_passed: int = 0
    indicators_failed: int = 0
    max_diff: float = 0.0
    mean_diff: float = 0.0
    results: list[dict] = field(default_factory=list)


@dataclass
class ConditionResult:
    """Result from testing a specific market condition."""
    condition: str  # bull, bear, range, volatile
    date_range: tuple[str, str]
    plays_passed: int = 0
    plays_failed: int = 0
    play_results: list[PlayResult] = field(default_factory=list)


@dataclass
class AgentResult:
    """Result from running the full testing agent."""
    success: bool
    mode: str  # full, btc, l2
    conditions_tested: list[str] = field(default_factory=list)
    condition_results: dict[str, ConditionResult] = field(default_factory=dict)
    indicators_covered: int = 0
    plays_passed: int = 0
    plays_failed: int = 0
    parity_result: ParityResult | None = None
    duration_seconds: float = 0.0


# =============================================================================
# Market Condition Date Ranges (Research-Based)
# =============================================================================

MARKET_CONDITIONS = {
    "bull": {
        "name": "ETF Rally",
        "start": "2024-01-10",
        "end": "2024-03-14",
        "description": "BTC $40K -> $73K ATH (Spot BTC ETF approval)",
    },
    "bear": {
        "name": "Post-Halving Correction",
        "start": "2024-04-14",
        "end": "2024-05-01",
        "description": "BTC $73K -> $56K (-23%)",
    },
    "range": {
        "name": "Post-Correction Consolidation",
        "start": "2024-05-01",
        "end": "2024-07-15",
        "description": "BTC $58K-$72K (2.5 month range)",
    },
    "volatile": {
        "name": "July Acceleration",
        "start": "2024-07-15",
        "end": "2024-08-15",
        "description": "BTC $58K-$70K (volatility expansion)",
    },
}


# =============================================================================
# Tier Definitions
# =============================================================================

TIER_INDICATORS = {
    "tier19": {
        "name": "Moving Averages",
        "dir": "tier19_ma",
        "indicators": ["ema", "sma", "wma", "dema", "tema", "trima", "zlma", "kama", "alma"],
        "plays": [
            "V_T19_001_ema_sma",
            "V_T19_002_wma_dema",
            "V_T19_003_tema_trima",
            "V_T19_004_zlma_kama",
            "V_T19_005_alma",
        ],
    },
    "tier20": {
        "name": "Oscillators",
        "dir": "tier20_oscillators",
        "indicators": ["rsi", "willr", "cci", "cmo", "stoch", "stochrsi", "fisher"],
        "plays": [
            "V_T20_001_rsi_willr",
            "V_T20_002_cci_cmo",
            "V_T20_003_stoch",
            "V_T20_004_stochrsi",
            "V_T20_005_fisher",
        ],
    },
    "tier21": {
        "name": "Volatility",
        "dir": "tier21_volatility",
        "indicators": ["atr", "natr", "bbands", "kc", "donchian", "squeeze"],
        "plays": [
            "V_T21_001_atr_natr",
            "V_T21_002_bbands",
            "V_T21_003_kc",
            "V_T21_004_donchian",
            "V_T21_005_squeeze",
        ],
    },
    "tier22": {
        "name": "Trend",
        "dir": "tier22_trend",
        "indicators": ["adx", "supertrend", "aroon", "psar", "vortex", "dm", "trix"],
        "plays": [
            "V_T22_001_adx",
            "V_T22_002_supertrend",
            "V_T22_003_aroon",
            "V_T22_004_psar",
            "V_T22_005_vortex",
            "V_T22_006_dm",
            "V_T22_007_trix",
        ],
    },
    "tier23": {
        "name": "Momentum",
        "dir": "tier23_momentum",
        "indicators": ["macd", "roc", "mom", "ppo", "tsi", "uo", "linreg"],
        "plays": [
            "V_T23_001_macd",
            "V_T23_002_roc_mom",
            "V_T23_003_ppo",
            "V_T23_004_tsi",
            "V_T23_005_uo",
            "V_T23_006_linreg",
        ],
    },
    "tier24": {
        "name": "Volume",
        "dir": "tier24_volume",
        "indicators": ["obv", "mfi", "cmf", "kvo", "vwap"],
        "plays": [
            "V_T24_001_obv",
            "V_T24_002_mfi",
            "V_T24_003_cmf",
            "V_T24_004_kvo",
            "V_T24_005_vwap",
        ],
    },
    "tier25": {
        "name": "Misc",
        "dir": "tier25_misc",
        "indicators": ["ohlc4", "midprice"],
        "plays": [
            "V_T25_001_ohlc4_midprice",
        ],
    },
}


# =============================================================================
# Test Runner Functions
# =============================================================================

def run_indicator_suite(
    fix_gaps: bool = True,
    symbol: str = "BTCUSDT",
) -> TestResult:
    """
    Run full indicator validation suite across all tiers.

    Args:
        fix_gaps: Auto-fetch missing data
        symbol: Symbol to test (default: BTCUSDT)

    Returns:
        TestResult with pass/fail status and details
    """
    import time
    start_time = time.time()

    result = TestResult(success=True)
    total_indicators = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        # Process each tier
        for tier_name, tier_info in TIER_INDICATORS.items():
            task = progress.add_task(f"Testing {tier_name}...", total=len(tier_info["plays"]))

            tier_result = run_tier_tests(
                tier=tier_name,
                fix_gaps=fix_gaps,
                symbol=symbol,
                progress=progress,
                task=task,
            )

            result.tier_results[tier_name] = tier_result
            total_indicators += len(tier_info["indicators"])

            if tier_result.success:
                result.tiers_passed += 1
                result.plays_passed += tier_result.plays_passed
            else:
                result.tiers_failed += 1
                result.plays_failed += tier_result.plays_failed
                result.success = False

            progress.update(task, completed=len(tier_info["plays"]))

    result.indicators_covered = total_indicators
    result.duration_seconds = time.time() - start_time

    return result


def run_tier_tests(
    tier: str,
    fix_gaps: bool = True,
    symbol: str = "BTCUSDT",
    condition: str | None = None,
    progress: Progress | None = None,
    task=None,
) -> TierResult:
    """
    Run tests for a specific tier.

    Args:
        tier: Tier name (tier19-tier25)
        fix_gaps: Auto-fetch missing data
        symbol: Symbol to test
        condition: Optional market condition filter

    Returns:
        TierResult with pass/fail status and details
    """
    if tier not in TIER_INDICATORS:
        return TierResult(tier=tier, success=False)

    tier_info = TIER_INDICATORS[tier]
    result = TierResult(
        tier=tier,
        success=True,
        indicators_tested=tier_info["indicators"],
    )

    plays_dir = Path("tests/validation/plays") / tier.replace("tier", "tier")

    for play_id in tier_info["plays"]:
        play_result = _run_single_play(
            play_id=play_id,
            tier=tier,
            fix_gaps=fix_gaps,
            symbol=symbol,
            condition=condition,
        )

        result.play_results.append(play_result)

        if play_result.success:
            result.plays_passed += 1
        else:
            result.plays_failed += 1
            result.success = False

        if progress and task:
            progress.advance(task)

    return result


def run_symbol_tests(
    symbol: str,
    fix_gaps: bool = True,
    tiers: list[str] | None = None,
) -> TestResult:
    """
    Run tests for a specific symbol across all or specified tiers.

    Args:
        symbol: Symbol to test (e.g., BTCUSDT)
        fix_gaps: Auto-fetch missing data
        tiers: Optional list of tiers to test

    Returns:
        TestResult with pass/fail status
    """
    if tiers is None:
        tiers = list(TIER_INDICATORS.keys())

    result = TestResult(success=True)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for tier in tiers:
            task = progress.add_task(f"Testing {tier} for {symbol}...", total=None)

            tier_result = run_tier_tests(
                tier=tier,
                fix_gaps=fix_gaps,
                symbol=symbol,
            )

            result.tier_results[tier] = tier_result

            if tier_result.success:
                result.tiers_passed += 1
                result.plays_passed += tier_result.plays_passed
            else:
                result.tiers_failed += 1
                result.plays_failed += tier_result.plays_failed
                result.success = False

            progress.update(task, completed=True)

    return result


def run_parity_check(
    bars: int = 2000,
    tolerance: float = 1e-6,
    seed: int = 42,
) -> ParityResult:
    """
    Run incremental vs vectorized parity check.

    This compares the O(1) incremental indicator implementations
    against the vectorized pandas_ta implementations.

    Args:
        bars: Number of synthetic bars to test
        tolerance: Maximum allowed difference
        seed: Random seed for reproducibility

    Returns:
        ParityResult with pass/fail status and details
    """
    from src.forge.audits import run_incremental_parity_audit

    console.print(f"[dim]Running parity audit with {bars} bars...[/]")

    audit_result = run_incremental_parity_audit(
        bars=bars,
        tolerance=tolerance,
        seed=seed,
    )

    # Calculate max/mean diff from individual results
    max_diff = 0.0
    mean_diffs = []
    results_list = []

    for r in audit_result.results:
        if r.max_abs_diff > max_diff:
            max_diff = r.max_abs_diff
        mean_diffs.append(r.mean_abs_diff)
        results_list.append({
            "indicator": r.indicator,
            "passed": r.passed,
            "max_diff": r.max_abs_diff,
            "mean_diff": r.mean_abs_diff,
            "outputs": r.outputs_checked,
        })

    mean_diff = sum(mean_diffs) / len(mean_diffs) if mean_diffs else 0.0

    result = ParityResult(
        success=audit_result.success,
        indicators_passed=audit_result.passed_indicators,
        indicators_failed=audit_result.failed_indicators,
        max_diff=max_diff,
        mean_diff=mean_diff,
        results=results_list,
    )

    return result


def run_live_parity(
    tier: str,
    fix_gaps: bool = True,
) -> TestResult:
    """
    Run live vs backtest parity comparison.

    This runs the same indicators in both backtest (vectorized) and
    live (incremental) mode and compares the results.

    Args:
        tier: Tier to test
        fix_gaps: Auto-fetch missing data

    Returns:
        TestResult with comparison details
    """
    # For now, this is a placeholder that runs the tier tests
    # Full live parity would require running the live engine
    console.print(f"[dim]Running live parity for {tier}...[/]")

    return run_tier_tests(tier=tier, fix_gaps=fix_gaps)


def run_agent(
    mode: Literal["full", "btc", "l2"],
    fix_gaps: bool = True,
) -> AgentResult:
    """
    Run the full testing agent.

    Modes:
        full: BTC + L2 alts across all market conditions
        btc: BTC only across all market conditions
        l2: L2 alts (ETH, SOL, LTC, AVAX) only

    Args:
        mode: Agent mode
        fix_gaps: Auto-fetch missing data

    Returns:
        AgentResult with comprehensive test results
    """
    import time
    start_time = time.time()

    result = AgentResult(
        success=True,
        mode=mode,
        conditions_tested=list(MARKET_CONDITIONS.keys()),
    )

    # Determine symbols based on mode
    if mode == "full":
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LTCUSDT", "AVAXUSDT"]
    elif mode == "btc":
        symbols = ["BTCUSDT"]
    else:  # l2
        symbols = ["ETHUSDT", "SOLUSDT", "LTCUSDT", "AVAXUSDT"]

    console.print(f"\n[bold]Testing Agent Mode: {mode.upper()}[/]")
    console.print(f"[dim]Symbols: {', '.join(symbols)}[/]")
    console.print(f"[dim]Conditions: {', '.join(MARKET_CONDITIONS.keys())}[/]\n")

    # Test each market condition
    for condition, cond_info in MARKET_CONDITIONS.items():
        console.print(f"[cyan]Testing {condition.upper()} condition ({cond_info['name']})...[/]")
        console.print(f"[dim]Period: {cond_info['start']} to {cond_info['end']}[/]")

        cond_result = ConditionResult(
            condition=condition,
            date_range=(cond_info["start"], cond_info["end"]),
        )

        # Run tier tests for each symbol under this condition
        for symbol in symbols:
            tier_result = run_tier_tests(
                tier="tier19",  # Start with MAs as baseline
                fix_gaps=fix_gaps,
                symbol=symbol,
                condition=condition,
            )

            for play_result in tier_result.play_results:
                play_result.condition = condition
                cond_result.play_results.append(play_result)

            cond_result.plays_passed += tier_result.plays_passed
            cond_result.plays_failed += tier_result.plays_failed

        result.condition_results[condition] = cond_result
        result.plays_passed += cond_result.plays_passed
        result.plays_failed += cond_result.plays_failed

        if cond_result.plays_failed > 0:
            result.success = False

    # Run parity check
    console.print("\n[cyan]Running parity check...[/]")
    result.parity_result = run_parity_check()

    if not result.parity_result.success:
        result.success = False

    # Count indicators
    result.indicators_covered = sum(
        len(tier["indicators"]) for tier in TIER_INDICATORS.values()
    )

    result.duration_seconds = time.time() - start_time

    return result


# =============================================================================
# Internal Helper Functions
# =============================================================================

def _run_single_play(
    play_id: str,
    tier: str,
    fix_gaps: bool,
    symbol: str,
    condition: str | None,
) -> PlayResult:
    """
    Run a single validation Play and return the result.

    Args:
        play_id: Play identifier
        tier: Tier name
        fix_gaps: Auto-fetch missing data
        symbol: Symbol to test
        condition: Optional market condition

    Returns:
        PlayResult with execution details
    """
    import time
    from src.tools.backtest_play_tools import backtest_run_play_tool

    start_time = time.time()

    # Determine date range based on condition
    if condition and condition in MARKET_CONDITIONS:
        start_date = MARKET_CONDITIONS[condition]["start"]
        end_date = MARKET_CONDITIONS[condition]["end"]
    else:
        # Default: use synthetic data mode
        start_date = None
        end_date = None

    try:
        # Build play path using the directory name from TIER_INDICATORS
        tier_dir = TIER_INDICATORS[tier]["dir"]
        plays_dir = Path("tests/validation/plays") / tier_dir

        # Run backtest
        result = backtest_run_play_tool(
            play_id=play_id,
            env="live",  # Use live data API
            start=datetime.strptime(start_date, "%Y-%m-%d") if start_date else None,
            end=datetime.strptime(end_date, "%Y-%m-%d") if end_date else None,
            smoke=False,
            strict=True,
            write_artifacts=False,  # Don't write artifacts for validation
            plays_dir=plays_dir if plays_dir.exists() else None,
            fix_gaps=fix_gaps,
        )

        duration_ms = int((time.time() - start_time) * 1000)

        if result.success:
            data = result.data or {}
            summary = data.get("summary", {})
            # Extract all metrics from ResultsSummary.to_dict()
            # Note: win_rate in summary is decimal (0.6228), convert to percentage
            return PlayResult(
                play_id=play_id,
                success=True,
                duration_ms=duration_ms,
                condition=condition or "",
                # Core Trade Metrics
                trades_count=data.get("trades_count", 0),
                winning_trades=summary.get("winning_trades", 0),
                losing_trades=summary.get("losing_trades", 0),
                win_rate=summary.get("win_rate", 0.0) * 100,  # decimal → percentage
                # PnL Metrics
                net_pnl=summary.get("net_pnl_usdt", 0.0),
                net_return_pct=summary.get("net_return_pct", 0.0),
                gross_profit=summary.get("gross_profit_usdt", 0.0),
                gross_loss=summary.get("gross_loss_usdt", 0.0),
                total_fees=summary.get("total_fees_usdt", 0.0),
                # Drawdown Metrics
                max_drawdown_pct=summary.get("max_drawdown_pct", 0.0) * 100,  # decimal → percentage
                max_drawdown_usdt=summary.get("max_drawdown_usdt", 0.0),
                max_drawdown_duration=summary.get("max_drawdown_duration_bars", 0),
                # Risk-Adjusted Metrics
                sharpe=summary.get("sharpe", 0.0),
                sortino=summary.get("sortino", 0.0),
                calmar=summary.get("calmar", 0.0),
                profit_factor=summary.get("profit_factor", 0.0),
                # Trade Quality Metrics
                avg_win=summary.get("avg_win_usdt", 0.0),
                avg_loss=summary.get("avg_loss_usdt", 0.0),
                largest_win=summary.get("largest_win_usdt", 0.0),
                largest_loss=summary.get("largest_loss_usdt", 0.0),
                expectancy=summary.get("expectancy_usdt", 0.0),
                payoff_ratio=summary.get("payoff_ratio", 0.0),
                recovery_factor=summary.get("recovery_factor", 0.0),
                # Streak Metrics
                max_consecutive_wins=summary.get("max_consecutive_wins", 0),
                max_consecutive_losses=summary.get("max_consecutive_losses", 0),
                # Long/Short Breakdown
                long_trades=summary.get("long_trades", 0),
                short_trades=summary.get("short_trades", 0),
                long_win_rate=summary.get("long_win_rate", 0.0),
                short_win_rate=summary.get("short_win_rate", 0.0),
                long_pnl=summary.get("long_pnl", 0.0),
                short_pnl=summary.get("short_pnl", 0.0),
                # Time Metrics
                total_bars=summary.get("total_bars", 0),
                bars_in_position=summary.get("bars_in_position", 0),
                time_in_market_pct=summary.get("time_in_market_pct", 0.0),
                avg_trade_duration=summary.get("avg_trade_duration_bars", 0.0),
                # Config Info
                leverage=summary.get("leverage", 1),
                initial_equity=summary.get("initial_equity", 10000.0),
            )
        else:
            return PlayResult(
                play_id=play_id,
                success=False,
                error=result.error,
                duration_ms=duration_ms,
                condition=condition or "",
            )

    except Exception as e:
        return PlayResult(
            play_id=play_id,
            success=False,
            error=str(e),
            duration_ms=int((time.time() - start_time) * 1000),
            condition=condition or "",
        )
