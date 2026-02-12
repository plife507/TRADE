"""
Unified validation for TRADE.

Single entry point: python trade_cli.py validate [tier]

Tiers:
  quick    (~10s)  - pre-commit: YAML parse, registry, parity, 5 core plays
  standard (~2min) - pre-merge: + structures, rollup, sim, operator/structure/complexity suites
  full     (~10min)- pre-release: + full indicator/pattern suites, math verification, determinism
  pre-live         - connectivity + readiness gate for a specific play
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()

# ── Core validation play IDs ──────────────────────────────────────────

CORE_PLAY_IDS = [
    "V_CORE_001_indicator_cross",
    "V_CORE_002_structure_chain",
    "V_CORE_003_cases_metadata",
    "V_CORE_004_multi_tf",
    "V_CORE_005_arithmetic_window",
]


# ── Data structures ───────────────────────────────────────────────────

class Tier(str, Enum):
    QUICK = "quick"
    STANDARD = "standard"
    FULL = "full"
    PRE_LIVE = "pre-live"


@dataclass
class GateResult:
    """Result from a single validation gate."""

    gate_id: str
    name: str
    passed: bool
    checked: int
    duration_sec: float
    detail: str = ""
    failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "gate_id": self.gate_id,
            "name": self.name,
            "passed": self.passed,
            "checked": self.checked,
            "duration_sec": round(self.duration_sec, 2),
            "detail": self.detail,
            "failures": self.failures,
        }


@dataclass
class ValidationReport:
    """Complete validation report."""

    tier: str
    gates: list[GateResult] = field(default_factory=list)
    duration_sec: float = 0.0

    @property
    def passed(self) -> bool:
        return all(g.passed for g in self.gates)

    @property
    def total_checked(self) -> int:
        return sum(g.checked for g in self.gates)

    @property
    def failed_count(self) -> int:
        return sum(1 for g in self.gates if not g.passed)

    def to_dict(self) -> dict:
        return {
            "tier": self.tier,
            "duration_sec": round(self.duration_sec, 2),
            "passed": self.passed,
            "total_checked": self.total_checked,
            "failed_gates": self.failed_count,
            "gates": [g.to_dict() for g in self.gates],
        }


# ── Gate implementations ──────────────────────────────────────────────

def _gate_yaml_parse() -> GateResult:
    """G1: Parse and validate core validation plays."""
    start = time.perf_counter()
    failures: list[str] = []

    from src.backtest.play import load_play

    for pid in CORE_PLAY_IDS:
        try:
            play = load_play(pid)
            play.validate()
        except Exception as e:
            failures.append(f"{pid}: {e}")

    return GateResult(
        gate_id="G1",
        name="YAML Parse",
        passed=len(failures) == 0,
        checked=len(CORE_PLAY_IDS),
        duration_sec=time.perf_counter() - start,
        detail=f"{len(CORE_PLAY_IDS)} plays",
        failures=failures,
    )


def _gate_registry_contract() -> GateResult:
    """G2: Indicator registry contract audit (44 indicators)."""
    start = time.perf_counter()
    failures: list[str] = []

    from src.forge.audits.toolkit_contract_audit import run_toolkit_contract_audit

    result = run_toolkit_contract_audit(sample_bars=2000, seed=1337, strict=True)

    checked = result.total_indicators
    if not result.success:
        for r in result.indicator_results:
            if not r.passed:
                failures.append(f"{r.indicator_type}: {r.error_message or 'contract breach'}")

    return GateResult(
        gate_id="G2",
        name="Registry Contract",
        passed=result.success,
        checked=checked,
        duration_sec=time.perf_counter() - start,
        detail=f"{checked} indicators",
        failures=failures,
    )


def _gate_incremental_parity() -> GateResult:
    """G3: Incremental vs vectorized indicator parity (43 indicators)."""
    start = time.perf_counter()
    failures: list[str] = []

    from src.forge.audits.audit_incremental_parity import run_incremental_parity_audit

    result = run_incremental_parity_audit(bars=1000, tolerance=1e-6, seed=42)

    checked = result.total_indicators
    if not result.success:
        for r in result.results:
            if not r.passed:
                failures.append(f"{r.indicator}: max_diff={r.max_abs_diff:.2e} ({r.error_message or ''})")

    return GateResult(
        gate_id="G3",
        name="Incremental Parity",
        passed=result.success,
        checked=checked,
        duration_sec=time.perf_counter() - start,
        detail=f"{checked} indicators",
        failures=failures,
    )


def _gate_core_plays() -> GateResult:
    """G4: Run 5 core validation plays through engine (synthetic data)."""
    start = time.perf_counter()
    failures: list[str] = []
    total_trades = 0

    from src.backtest.play import load_play
    from src.backtest.engine_factory import create_engine_from_play, run_engine_with_play

    for pid in CORE_PLAY_IDS:
        try:
            play = load_play(pid)
            engine = create_engine_from_play(play)
            result = run_engine_with_play(engine, play)
            trades = len(result.trades) if hasattr(result, "trades") else 0
            total_trades += trades
            if trades == 0:
                failures.append(f"{pid}: zero trades")
        except Exception as e:
            failures.append(f"{pid}: {type(e).__name__}: {e}")

    return GateResult(
        gate_id="G4",
        name="Core Engine Plays",
        passed=len(failures) == 0,
        checked=len(CORE_PLAY_IDS),
        duration_sec=time.perf_counter() - start,
        detail=f"{len(CORE_PLAY_IDS)} plays, {total_trades} trades",
        failures=failures,
    )


def _gate_structure_parity() -> GateResult:
    """G5: Structure detector vectorized vs incremental parity (7 detectors)."""
    start = time.perf_counter()
    failures: list[str] = []

    from src.forge.audits.audit_structure_parity import run_structure_parity_audit

    result = run_structure_parity_audit(bars=2000, tolerance=1e-10, seed=42)

    checked = result.total_detectors
    if not result.success:
        for r in result.results:
            if not r.passed:
                failures.append(f"{r.detector}/{r.dataset}: max_diff={r.max_abs_diff:.2e}")

    return GateResult(
        gate_id="G5",
        name="Structure Parity",
        passed=result.success,
        checked=checked,
        duration_sec=time.perf_counter() - start,
        detail=f"{checked} detectors",
        failures=failures,
    )


def _gate_rollup_parity() -> GateResult:
    """G6: 1m rollup bucket parity audit."""
    start = time.perf_counter()
    failures: list[str] = []

    from src.forge.audits.audit_rollup_parity import run_rollup_parity_audit

    result = run_rollup_parity_audit(n_intervals=10, quotes_per_interval=15, seed=1337, tolerance=1e-10)

    checked = result.total_comparisons
    if not result.success:
        failures.append(f"{result.failed_comparisons}/{checked} comparisons failed")

    return GateResult(
        gate_id="G6",
        name="Rollup Parity",
        passed=result.success,
        checked=checked,
        duration_sec=time.perf_counter() - start,
        detail=f"{checked} comparisons",
        failures=failures,
    )


def _gate_sim_orders() -> GateResult:
    """G7: Simulator order type smoke tests."""
    start = time.perf_counter()
    failures: list[str] = []

    from src.cli.smoke_tests.sim_orders import run_sim_orders_smoke

    failure_count = run_sim_orders_smoke(verbose=False)

    return GateResult(
        gate_id="G7",
        name="Sim Order Types",
        passed=failure_count == 0,
        checked=6,
        duration_sec=time.perf_counter() - start,
        detail="6 order types",
        failures=[f"{failure_count} test(s) failed"] if failure_count > 0 else [],
    )


def _gate_play_suite(suite_name: str, gate_id: str, gate_name: str) -> GateResult:
    """Run all plays in a suite directory through the engine."""
    start = time.perf_counter()
    failures: list[str] = []
    total_trades = 0

    from src.backtest.play import load_play
    from src.backtest.engine_factory import create_engine_from_play, run_engine_with_play
    from src.forge.validation.synthetic_data import generate_synthetic_candles
    from src.forge.validation.synthetic_provider import SyntheticCandlesProvider

    suite_dir = Path("plays") / suite_name
    play_files = sorted(suite_dir.glob("*.yml"))
    checked = len(play_files)

    for pf in play_files:
        pid = pf.stem
        try:
            play = load_play(pid)

            # Plays without embedded synthetic config need an external provider
            has_own_synthetic = play.synthetic is not None
            if not has_own_synthetic:
                symbol = play.symbol_universe[0] if play.symbol_universe else "BTCUSDT"
                required_tfs = {"1m"}
                for tf in (play.low_tf, play.med_tf, play.high_tf):
                    if tf:
                        required_tfs.add(tf)
                candles = generate_synthetic_candles(
                    symbol=symbol,
                    timeframes=sorted(required_tfs),
                    bars_per_tf=500,
                    seed=42,
                    pattern="trending",
                )
                provider = SyntheticCandlesProvider(candles)
                engine = create_engine_from_play(play, synthetic_provider=provider)
            else:
                engine = create_engine_from_play(play)

            result = run_engine_with_play(engine, play)
            trades = len(result.trades) if hasattr(result, "trades") else 0
            total_trades += trades
            # Only fail on zero trades for plays with their own synthetic config
            # (those patterns are designed to generate trades). Generic "trending"
            # pattern won't match all play conditions.
            if trades == 0 and has_own_synthetic:
                failures.append(f"{pid}: zero trades")
        except Exception as e:
            failures.append(f"{pid}: {type(e).__name__}: {e}")

    return GateResult(
        gate_id=gate_id,
        name=gate_name,
        passed=len(failures) == 0,
        checked=checked,
        duration_sec=time.perf_counter() - start,
        detail=f"{checked} plays, {total_trades} trades",
        failures=failures,
    )


def _gate_pre_live_connectivity() -> GateResult:
    """PL1: Bybit API connectivity check."""
    start = time.perf_counter()
    failures: list[str] = []

    try:
        from src.tools import test_connection_tool
        result = test_connection_tool()
        if not result.success:
            failures.append(f"API connectivity: {result.error}")
    except Exception as e:
        failures.append(f"Connection test: {e}")

    return GateResult(
        gate_id="PL1",
        name="API Connectivity",
        passed=len(failures) == 0,
        checked=1,
        duration_sec=time.perf_counter() - start,
        detail="Bybit API",
        failures=failures,
    )


def _gate_pre_live_balance(play_id: str) -> GateResult:
    """PL2: Sufficient account balance for play."""
    start = time.perf_counter()
    failures: list[str] = []

    try:
        from src.backtest.play import load_play
        from src.tools import get_account_balance_tool

        play = load_play(play_id)
        result = get_account_balance_tool()
        if not result.success:
            failures.append(f"Balance check: {result.error}")
        elif result.data:
            available = float(result.data.get("available_balance", 0))
            assert play.account is not None
            required = play.account.starting_equity_usdt
            if available < required:
                failures.append(f"Insufficient balance: {available:.2f} < {required:.2f} USDT")
    except Exception as e:
        failures.append(f"Balance check: {e}")

    return GateResult(
        gate_id="PL2",
        name="Account Balance",
        passed=len(failures) == 0,
        checked=1,
        duration_sec=time.perf_counter() - start,
        detail=f"Play: {play_id}",
        failures=failures,
    )


def _gate_pre_live_no_conflicts(play_id: str) -> GateResult:
    """PL3: No conflicting open positions."""
    start = time.perf_counter()
    failures: list[str] = []

    try:
        from src.backtest.play import load_play
        from src.tools import list_open_positions_tool

        play = load_play(play_id)
        symbol = play.symbol_universe[0]
        result = list_open_positions_tool()
        if result.success and result.data:
            raw_data = result.data
            positions: list[dict[str, Any]] = raw_data if isinstance(raw_data, list) else []
            for pos in positions:
                if isinstance(pos, dict) and pos.get("symbol") == symbol:
                    failures.append(f"Open position exists for {symbol}")
    except Exception as e:
        failures.append(f"Position check: {e}")

    return GateResult(
        gate_id="PL3",
        name="No Position Conflicts",
        passed=len(failures) == 0,
        checked=1,
        duration_sec=time.perf_counter() - start,
        detail=f"Symbol: {play_id}",
        failures=failures,
    )


# ── Tier orchestration ────────────────────────────────────────────────

def _run_gates(gates: list, fail_fast: bool = True) -> list[GateResult]:
    """Run a list of gate functions, optionally stopping on first failure."""
    results: list[GateResult] = []
    for gate_fn in gates:
        result = gate_fn()
        results.append(result)
        if not result.passed and fail_fast:
            break
    return results


def run_validation(
    tier: Tier,
    play_id: str | None = None,
    fail_fast: bool = True,
    json_output: bool = False,
) -> int:
    """
    Run the unified validation suite at the specified tier.

    Returns:
        Exit code: 0 if all gates pass, 1 if any fail.
    """
    import logging
    import os

    os.environ["TRADE_LOG_LEVEL"] = "WARNING"
    logging.disable(logging.INFO)
    for name in ["src", "src.backtest", "src.engine", "src.data", "src.indicators"]:
        logging.getLogger(name).setLevel(logging.WARNING)

    start = time.perf_counter()

    if not json_output:
        console.print(f"\n[bold cyan]TRADE VALIDATION[/]  [dim]\\[{tier.value}][/]")
        console.print(f"[dim]{'=' * 54}[/]")

    # Build gate list based on tier
    gates: list = []

    if tier == Tier.PRE_LIVE:
        if not play_id:
            console.print("[bold red]pre-live tier requires --play[/]")
            return 1
        gates = [
            _gate_pre_live_connectivity,
            lambda: _gate_pre_live_balance(play_id),
            lambda: _gate_pre_live_no_conflicts(play_id),
            _gate_yaml_parse,
            _gate_core_plays,
        ]
    else:
        # quick tier: G1-G4
        gates = [
            _gate_yaml_parse,
            _gate_registry_contract,
            _gate_incremental_parity,
            _gate_core_plays,
        ]

        if tier in (Tier.STANDARD, Tier.FULL):
            # standard adds: G5-G10
            gates.extend([
                _gate_structure_parity,
                _gate_rollup_parity,
                _gate_sim_orders,
                lambda: _gate_play_suite("operator_suite", "G8", "Operator Suite"),
                lambda: _gate_play_suite("structure_suite", "G9", "Structure Suite"),
                lambda: _gate_play_suite("complexity_ladder", "G10", "Complexity Ladder"),
            ])

        if tier == Tier.FULL:
            # full adds: G11-G12
            gates.extend([
                lambda: _gate_play_suite("indicator_suite", "G11", "Indicator Suite"),
                lambda: _gate_play_suite("pattern_suite", "G12", "Pattern Suite"),
            ])

    # Run gates
    results = _run_gates(gates, fail_fast=fail_fast)

    report = ValidationReport(
        tier=tier.value,
        gates=results,
        duration_sec=time.perf_counter() - start,
    )

    if json_output:
        console.print(json.dumps(report.to_dict(), indent=2))
    else:
        _print_report(report)

    return 0 if report.passed else 1


# ── Reporting ─────────────────────────────────────────────────────────

def _print_report(report: ValidationReport) -> None:
    """Print rich console report."""
    for gate in report.gates:
        status = "[bold green]PASS[/]" if gate.passed else "[bold red]FAIL[/]"
        name_padded = f"{gate.name} ".ljust(26, ".")
        detail = f"[dim]{gate.detail}[/]"
        timing = f"[dim]{gate.duration_sec:.1f}s[/]"
        console.print(f" {gate.gate_id:4s} {name_padded} {status}  {detail:30s} {timing}")

        if gate.failures:
            for f in gate.failures[:5]:
                console.print(f"       [red]{f}[/]")
            if len(gate.failures) > 5:
                console.print(f"       [dim]... and {len(gate.failures) - 5} more[/]")

    console.print(f"[dim]{'=' * 54}[/]")

    passed_count = sum(1 for g in report.gates if g.passed)
    total_count = len(report.gates)

    if report.passed:
        console.print(
            f" [bold green]RESULT: ALL {total_count} GATES PASSED[/]"
            f"  [dim]({report.duration_sec:.1f}s)[/]"
        )
    else:
        console.print(
            f" [bold red]RESULT: {report.failed_count} of {total_count} GATES FAILED[/]"
            f"  [dim]({report.duration_sec:.1f}s)[/]"
        )

    console.print()
