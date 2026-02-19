"""
Unified validation for TRADE.

Single entry point: python trade_cli.py validate [tier]

Tiers:
  quick     (~2min) - pre-commit: YAML parse, registry, parity, 5 core plays, 9 risk plays
  standard  (~4min) - pre-merge: + structures, rollup, sim, suites, metrics audit
  full      (~6min) - pre-release: + full indicator/pattern suites, determinism
  real      (~2min) - real-data: sync-once then parallel 61 RV plays
  module            - run a single validation module independently
  pre-live          - connectivity + readiness gate for a specific play
  exchange  (~30s)  - exchange integration (API, account, market data, order flow)

Parallelism:
  - Play suites (G8-G13) run plays in parallel via ProcessPoolExecutor
  - Independent gates within a stage run concurrently via ThreadPoolExecutor
  - Real-data tier: sync DuckDB once (serial), then all plays in parallel (read-only)

Timeouts:
  - Per-play timeout: 120s default (--timeout to override)
  - Per-gate timeout: 300s default
  - Hung plays/gates report as FAIL with TIMEOUT error, never block forever

Incremental reporting:
  - Each gate result prints immediately as it completes
  - Partial report written to .validate_report.json after each gate
  - If process hangs/dies, partial results are on disk
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from concurrent.futures import (
    Future,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    TimeoutError as FuturesTimeoutError,
    as_completed,
)
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from rich.console import Console

console = Console()

# ── Timeout defaults ─────────────────────────────────────────────────

PLAY_TIMEOUT_SEC = 120    # per-play timeout (synthetic or real)
GATE_TIMEOUT_SEC = 600    # per-gate timeout (G4 core plays can take ~330s sequential)

# ── Report file (incremental checkpoint) ─────────────────────────────

REPORT_FILE = Path(".validate_report.json")

# ── Core validation play IDs ──────────────────────────────────────────

CORE_PLAY_IDS = [
    "V_CORE_001_indicator_cross",
    "V_CORE_002_structure_chain",
    "V_CORE_003_cases_metadata",
    "V_CORE_004_multi_tf",
    "V_CORE_005_arithmetic_window",
]

# Risk plays: expected to stop with specific terminal reasons
RISK_PLAY_EXPECTATIONS: dict[str, str] = {
    "V_RISK_001_drawdown_5pct": "max_drawdown_hit",
    "V_RISK_002_drawdown_10pct": "max_drawdown_hit",
    "V_RISK_003_drawdown_50pct": "max_drawdown_hit",
    "V_RISK_004_liquidation": "liquidated",
    "V_RISK_005_short_drawdown_5pct": "max_drawdown_hit",
    "V_RISK_006_short_drawdown_50pct": "max_drawdown_hit",
    "V_RISK_007_short_liquidation": "liquidated",
    "V_RISK_008_longshort_drawdown": "max_drawdown_hit",
    "V_RISK_009_longshort_liquidation": "liquidated",
}


# ── Real-data sync manifest ──────────────────────────────────────────
# Covers all 61 RV plays with warmup buffer. Sync once, then read-only.

REAL_DATA_SYNC_MANIFEST: list[dict[str, Any]] = [
    {"symbol": "BTCUSDT", "timeframes": ["1m", "15m", "1h", "D"], "start": "2024-12-15", "end": "2026-01-19"},
    {"symbol": "ETHUSDT", "timeframes": ["1m", "15m", "1h", "D"], "start": "2025-02-01", "end": "2025-12-19"},
    {"symbol": "SOLUSDT", "timeframes": ["1m", "15m", "1h", "D"], "start": "2025-04-20", "end": "2026-01-22"},
    {"symbol": "LTCUSDT", "timeframes": ["1m", "15m", "1h"], "start": "2025-10-15", "end": "2026-01-15"},
]

REAL_DATA_PHASES = ["accumulation", "markup", "distribution", "markdown"]


# ── Data structures ───────────────────────────────────────────────────

class Tier(str, Enum):
    QUICK = "quick"
    STANDARD = "standard"
    FULL = "full"
    REAL = "real"
    MODULE = "module"
    PRE_LIVE = "pre-live"
    EXCHANGE = "exchange"


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


# ── Incremental reporting ─────────────────────────────────────────────

def _print_gate_result(gate: GateResult) -> None:
    """Print a single gate result immediately to console."""
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


def _checkpoint_report(tier: str, gates: list[GateResult], start_time: float) -> None:
    """Write partial report to disk after each gate completes."""
    report = {
        "tier": tier,
        "status": "in_progress",
        "duration_sec": round(time.perf_counter() - start_time, 2),
        "gates_completed": len(gates),
        "gates_passed": sum(1 for g in gates if g.passed),
        "gates_failed": sum(1 for g in gates if not g.passed),
        "gates": [g.to_dict() for g in gates],
    }
    try:
        REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    except Exception:
        pass  # non-critical


def _finalize_report(tier: str, gates: list[GateResult], start_time: float) -> None:
    """Write final report to disk."""
    all_passed = all(g.passed for g in gates)
    report = {
        "tier": tier,
        "status": "passed" if all_passed else "failed",
        "duration_sec": round(time.perf_counter() - start_time, 2),
        "gates_completed": len(gates),
        "gates_passed": sum(1 for g in gates if g.passed),
        "gates_failed": sum(1 for g in gates if not g.passed),
        "gates": [g.to_dict() for g in gates],
    }
    try:
        REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    except Exception:
        pass


# ── Module-level worker functions (must be top-level for Windows spawn) ──

def _run_single_play_synthetic(play_id: str) -> tuple[str, int, str | None]:
    """Run a single synthetic play. Returns (play_id, trade_count, error_or_None).

    Must be a module-level function for ProcessPoolExecutor on Windows (spawn).
    """
    from src.utils.logger import suppress_for_validation
    suppress_for_validation()

    try:
        from src.backtest.play import load_play
        from src.backtest.engine_factory import create_engine_from_play, run_engine_with_play

        play = load_play(play_id)
        engine = create_engine_from_play(play, use_synthetic=True)
        result = run_engine_with_play(engine, play)
        trades = len(result.trades) if hasattr(result, "trades") else 0
        if trades == 0 and play.validation is not None:
            return (play_id, 0, f"{play_id}: zero trades")
        return (play_id, trades, None)
    except Exception as e:
        return (play_id, 0, f"{play_id}: {type(e).__name__}: {e}")


def _run_single_risk_play(
    play_id: str, expected: str,
) -> tuple[str, str | None]:
    """Run a single risk play and validate stop classification.

    Returns (play_id, error_or_None).
    Must be module-level for ProcessPoolExecutor on Windows (spawn).
    """
    from src.utils.logger import suppress_for_validation
    suppress_for_validation()

    try:
        from src.backtest.play import load_play
        from src.backtest.engine_factory import create_engine_from_play, run_engine_with_play

        play = load_play(play_id)
        engine = create_engine_from_play(play, use_synthetic=True)
        result = run_engine_with_play(engine, play)
        if not result.stopped_early:
            return (play_id, f"{play_id}: expected stopped_early=True, got False")
        if result.stop_classification != expected:
            return (play_id, f"{play_id}: expected {expected}, got {result.stop_classification}")
        return (play_id, None)
    except Exception as e:
        return (play_id, f"{play_id}: {type(e).__name__}: {e}")


def _run_single_play_real(play_id: str, start: str, end: str) -> tuple[str, int, str | None]:
    """Run a single real-data play. Returns (play_id, trade_count, error_or_None).

    Must be a module-level function for ProcessPoolExecutor on Windows (spawn).
    Assumes data is already synced -- runs with sync=False.
    """
    from src.utils.logger import suppress_for_validation
    suppress_for_validation()

    try:
        from src.backtest.play import load_play
        from src.backtest.engine_factory import create_engine_from_play, run_engine_with_play
        from datetime import datetime

        play = load_play(play_id)
        window_start = datetime.strptime(start, "%Y-%m-%d")
        window_end = datetime.strptime(end, "%Y-%m-%d")
        engine = create_engine_from_play(play, window_start=window_start, window_end=window_end)
        result = run_engine_with_play(engine, play)
        trades = len(result.trades) if hasattr(result, "trades") else 0
        return (play_id, trades, None)
    except Exception as e:
        return (play_id, 0, f"{play_id}: {type(e).__name__}: {e}")


# ── Parallel play suite helper ────────────────────────────────────────

def _get_max_workers() -> int:
    """Get default max workers: cpu_count - 1, minimum 1."""
    cpu = os.cpu_count() or 4
    return max(1, cpu - 1)


def _collect_futures_with_timeout(
    futures: dict[Future, str],
    play_timeout: int,
    gate_label: str = "",
) -> tuple[int, list[str]]:
    """Collect results from play futures with per-play timeout.

    Prints progress as each play completes.
    Returns (total_trades, failures).
    """
    total_trades = 0
    failures: list[str] = []
    total = len(futures)
    done = 0

    try:
        for future in as_completed(futures, timeout=play_timeout * total):
            pid = futures[future]
            done += 1
            try:
                _, trades, error = future.result(timeout=play_timeout)
                total_trades += trades
                status = "[red]FAIL[/]" if error else "[green]ok[/]"
                if error:
                    failures.append(error)
            except FuturesTimeoutError:
                status = "[red]TIMEOUT[/]"
                failures.append(f"{pid}: TIMEOUT after {play_timeout}s")
            except Exception as e:
                status = "[red]ERROR[/]"
                failures.append(f"{pid}: {type(e).__name__}: {e}")
            console.print(f"       [dim]{gate_label}[/] {done}/{total} {pid} {status}", highlight=False)
    except FuturesTimeoutError:
        # Overall as_completed timeout -- mark remaining as timed out
        for future, pid in futures.items():
            if not future.done():
                failures.append(f"{pid}: TIMEOUT (pool deadline)")
                console.print(f"       [dim]{gate_label}[/] {pid} [red]TIMEOUT[/]", highlight=False)

    return total_trades, failures


def _gate_play_suite(
    suite_name: str,
    gate_id: str,
    gate_name: str,
    max_workers: int | None = None,
    play_timeout: int = PLAY_TIMEOUT_SEC,
) -> GateResult:
    """Run all plays in a suite directory through the engine in parallel."""
    start = time.perf_counter()
    failures: list[str] = []
    total_trades = 0

    suite_dir = Path("plays") / suite_name
    play_files = sorted(suite_dir.glob("*.yml"))
    play_ids = [pf.stem for pf in play_files]
    checked = len(play_ids)

    if checked == 0:
        return GateResult(
            gate_id=gate_id, name=gate_name, passed=True,
            checked=0, duration_sec=time.perf_counter() - start,
            detail="no plays found", failures=[],
        )

    workers = max_workers or _get_max_workers()

    # For small suites (<=3 plays), run sequentially to avoid process overhead
    if checked <= 3:
        for i, pid in enumerate(play_ids, 1):
            console.print(f"       [dim]{gate_id}[/] {i}/{checked} {pid}...", highlight=False)
            _, trades, error = _run_single_play_synthetic(pid)
            total_trades += trades
            if error:
                failures.append(error)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_run_single_play_synthetic, pid): pid for pid in play_ids}
            trades, fails = _collect_futures_with_timeout(futures, play_timeout, gate_id)
            total_trades += trades
            failures.extend(fails)

    return GateResult(
        gate_id=gate_id,
        name=gate_name,
        passed=len(failures) == 0,
        checked=checked,
        duration_sec=time.perf_counter() - start,
        detail=f"{checked} plays, {total_trades} trades",
        failures=sorted(failures),
    )


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
    """G4: Run 5 core validation plays through engine (synthetic data, parallel)."""
    start = time.perf_counter()
    failures: list[str] = []
    total_trades = 0
    workers = _get_max_workers()

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run_single_play_synthetic, pid): pid for pid in CORE_PLAY_IDS}
        trades, fails = _collect_futures_with_timeout(futures, PLAY_TIMEOUT_SEC, "G4")
        total_trades += trades
        failures.extend(fails)

    return GateResult(
        gate_id="G4",
        name="Core Engine Plays",
        passed=len(failures) == 0,
        checked=len(CORE_PLAY_IDS),
        duration_sec=time.perf_counter() - start,
        detail=f"{len(CORE_PLAY_IDS)} plays, {total_trades} trades",
        failures=failures,
    )


def _gate_risk_stops() -> GateResult:
    """G4b: Verify terminal risk events fire correctly on synthetic data (parallel)."""
    start = time.perf_counter()
    failures: list[str] = []
    workers = _get_max_workers()

    total = len(RISK_PLAY_EXPECTATIONS)
    done = 0

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_run_single_risk_play, pid, expected): pid
            for pid, expected in RISK_PLAY_EXPECTATIONS.items()
        }
        try:
            for future in as_completed(futures, timeout=PLAY_TIMEOUT_SEC * total):
                pid = futures[future]
                done += 1
                try:
                    _, error = future.result(timeout=PLAY_TIMEOUT_SEC)
                    status = "[red]FAIL[/]" if error else "[green]ok[/]"
                    if error:
                        failures.append(error)
                except FuturesTimeoutError:
                    status = "[red]TIMEOUT[/]"
                    failures.append(f"{pid}: TIMEOUT after {PLAY_TIMEOUT_SEC}s")
                except Exception as e:
                    status = "[red]ERROR[/]"
                    failures.append(f"{pid}: {type(e).__name__}: {e}")
                console.print(f"       [dim]G4b[/] {done}/{total} {pid} {status}", highlight=False)
        except FuturesTimeoutError:
            for future, pid in futures.items():
                if not future.done():
                    failures.append(f"{pid}: TIMEOUT (pool deadline)")
                    console.print(f"       [dim]G4b[/] {pid} [red]TIMEOUT[/]", highlight=False)

    return GateResult(
        gate_id="G4b",
        name="Risk Stops",
        passed=len(failures) == 0,
        checked=len(RISK_PLAY_EXPECTATIONS),
        duration_sec=time.perf_counter() - start,
        detail=f"{len(RISK_PLAY_EXPECTATIONS)} risk plays",
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


def _gate_metrics_audit() -> GateResult:
    """G11: Financial metrics calculation correctness."""
    start = time.perf_counter()
    failures: list[str] = []
    checked = 0

    from datetime import datetime as dt
    from src.backtest.metrics import (
        _compute_drawdown_metrics,
        _compute_cagr,
        _compute_calmar,
        get_bars_per_year,
        normalize_tf_string,
    )
    from src.backtest.types import EquityPoint

    # Test 1: Drawdown Independent Maxima
    checked += 1
    try:
        equity_curve = [
            EquityPoint(timestamp=dt(2024, 1, 1, 0, 0), equity=10.0),
            EquityPoint(timestamp=dt(2024, 1, 1, 1, 0), equity=1.0),
            EquityPoint(timestamp=dt(2024, 1, 1, 2, 0), equity=1000.0),
            EquityPoint(timestamp=dt(2024, 1, 1, 3, 0), equity=900.0),
        ]
        max_dd_abs, max_dd_pct, _ = _compute_drawdown_metrics(equity_curve)
        if not (abs(max_dd_abs - 100.0) < 0.01 and abs(max_dd_pct - 0.90) < 0.01):
            failures.append(f"Drawdown: max_dd_abs={max_dd_abs:.2f}, max_dd_pct={max_dd_pct:.4f}")
    except Exception as e:
        failures.append(f"Drawdown: {e}")

    # Test 2: CAGR Geometric Formula
    checked += 1
    try:
        cagr = _compute_cagr(initial_equity=10000.0, final_equity=12100.0, total_bars=365, bars_per_year=365)
        if not abs(cagr - 0.21) < 0.01:
            failures.append(f"CAGR: got {cagr:.4f}, expected ~0.21")
    except Exception as e:
        failures.append(f"CAGR: {e}")

    # Test 3: Calmar Uses CAGR
    checked += 1
    try:
        calmar = _compute_calmar(
            initial_equity=10000.0, final_equity=12100.0,
            max_dd_pct_decimal=0.10, total_bars=365, tf="D", strict_tf=True,
        )
        if not abs(calmar - 2.1) < 0.1:
            failures.append(f"Calmar: got {calmar:.2f}, expected ~2.1")
    except Exception as e:
        failures.append(f"Calmar: {e}")

    # Test 4: TF Strict Mode (Unknown TF Raises)
    checked += 1
    try:
        try:
            get_bars_per_year("unknown_tf", strict=True)
            failures.append("TF strict: expected ValueError, got none")
        except ValueError:
            pass  # correct
    except Exception as e:
        failures.append(f"TF strict: {e}")

    # Test 5: TF Normalization
    checked += 1
    try:
        cases = [("60", "1h"), ("240", "4h"), ("D", "D"), ("1h", "1h")]
        for inp, expected in cases:
            if normalize_tf_string(inp) != expected:
                failures.append(f"TF normalize: {inp} -> {normalize_tf_string(inp)}, expected {expected}")
                break
        try:
            normalize_tf_string("1d")
            failures.append("TF normalize: '1d' should raise ValueError")
        except ValueError:
            pass  # correct
    except Exception as e:
        failures.append(f"TF normalize: {e}")

    # Test 6: Zero Max DD (Calmar capped)
    checked += 1
    try:
        calmar = _compute_calmar(
            initial_equity=10000.0, final_equity=12100.0,
            max_dd_pct_decimal=0.0, total_bars=365, tf="D", strict_tf=True,
        )
        if calmar != 100.0:
            failures.append(f"Zero DD Calmar: got {calmar}, expected 100.0")
    except Exception as e:
        failures.append(f"Zero DD Calmar: {e}")

    return GateResult(
        gate_id="G11",
        name="Metrics Audit",
        passed=len(failures) == 0,
        checked=checked,
        duration_sec=time.perf_counter() - start,
        detail=f"{checked} scenarios",
        failures=failures,
    )


def _gate_coverage_check() -> GateResult:
    """G15: Check that all registered indicators and structures have validation plays."""
    import yaml

    start = time.perf_counter()
    failures: list[str] = []

    # ── Gather registered indicators ──
    from src.backtest.indicator_registry import get_registry

    registry = get_registry()
    registered_indicators = set(registry.list_indicators())

    # ── Gather registered structures ──
    from src.structures.registry import list_structure_types

    registered_structures = set(list_structure_types())

    # ── Scan indicator validation plays for indicator names ──
    covered_indicators: set[str] = set()
    ind_dir = Path("plays/validation/indicators")
    if ind_dir.exists():
        for play_file in ind_dir.glob("*.yml"):
            try:
                with open(play_file, encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
                features = raw.get("features", {})
                if isinstance(features, dict):
                    for feat in features.values():
                        if isinstance(feat, dict) and "indicator" in feat:
                            covered_indicators.add(feat["indicator"])
            except Exception:
                pass

    # ── Scan structure validation plays for structure types ──
    covered_structures: set[str] = set()
    str_dir = Path("plays/validation/structures")
    if str_dir.exists():
        for play_file in str_dir.glob("*.yml"):
            try:
                with open(play_file, encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
                structures = raw.get("structures", {})
                if isinstance(structures, dict):
                    for tf_structs in structures.values():
                        if isinstance(tf_structs, list):
                            for s in tf_structs:
                                if isinstance(s, dict) and "type" in s:
                                    covered_structures.add(s["type"])
            except Exception:
                pass

    # ── Compute gaps ──
    missing_indicators = sorted(registered_indicators - covered_indicators)
    missing_structures = sorted(registered_structures - covered_structures)

    for ind in missing_indicators:
        failures.append(f"Missing validation: indicator '{ind}' has no play in plays/validation/indicators/")
    for st in missing_structures:
        failures.append(f"Missing validation: structure '{st}' has no play in plays/validation/structures/")

    checked = len(registered_indicators) + len(registered_structures)

    return GateResult(
        gate_id="G15",
        name="Coverage Check",
        passed=len(failures) == 0,
        checked=checked,
        duration_sec=time.perf_counter() - start,
        detail=f"{len(registered_indicators)} indicators, {len(registered_structures)} structures; "
               f"{len(missing_indicators)} indicator gaps, {len(missing_structures)} structure gaps",
        failures=failures,
    )


def _gate_determinism() -> GateResult:
    """G14: Engine determinism - same input = same output."""
    start = time.perf_counter()
    failures: list[str] = []

    from src.backtest.play import load_play
    from src.backtest.engine_factory import create_engine_from_play, run_engine_with_play
    from src.backtest.artifacts.hashes import compute_trades_hash

    checked = 0
    total = len(CORE_PLAY_IDS)
    for pid in CORE_PLAY_IDS:
        checked += 1
        console.print(f"       [dim]G14[/] {checked}/{total} {pid} (run A+B)...", highlight=False)
        try:
            # Run A
            play_a = load_play(pid)
            engine_a = create_engine_from_play(play_a)
            result_a = run_engine_with_play(engine_a, play_a)

            # Run B
            play_b = load_play(pid)
            engine_b = create_engine_from_play(play_b)
            result_b = run_engine_with_play(engine_b, play_b)

            # Compare using canonical hash function
            trades_a = result_a.trades if hasattr(result_a, "trades") else []
            trades_b = result_b.trades if hasattr(result_b, "trades") else []
            hash_a = compute_trades_hash(trades_a)
            hash_b = compute_trades_hash(trades_b)

            if hash_a != hash_b:
                failures.append(f"{pid}: hash mismatch {hash_a} != {hash_b}")
        except Exception as e:
            failures.append(f"{pid}: {type(e).__name__}: {e}")

    return GateResult(
        gate_id="G14",
        name="Determinism",
        passed=len(failures) == 0,
        checked=checked,
        duration_sec=time.perf_counter() - start,
        detail=f"{checked} plays x2 runs",
        failures=failures,
    )


# ── Exchange gates (EX1-EX5) ─────────────────────────────────────────

def _gate_exchange_connectivity() -> GateResult:
    """EX1: Bybit API connectivity + server time offset."""
    start = time.perf_counter()
    failures: list[str] = []
    checked = 0

    try:
        from src.tools import test_connection_tool, get_server_time_offset_tool

        checked += 1
        result = test_connection_tool()
        if not result.success:
            failures.append(f"API connectivity: {result.error}")

        checked += 1
        result = get_server_time_offset_tool()
        if not result.success:
            failures.append(f"Server time: {result.error}")
        elif result.data:
            offset_ms = abs(result.data.get("offset_ms", 0))
            if offset_ms > 5000:
                failures.append(f"Server time offset too large: {offset_ms}ms")
    except Exception as e:
        failures.append(f"Connectivity: {e}")

    return GateResult(
        gate_id="EX1",
        name="API Connectivity",
        passed=len(failures) == 0,
        checked=checked,
        duration_sec=time.perf_counter() - start,
        detail="connection + server time",
        failures=failures,
    )


def _gate_exchange_account() -> GateResult:
    """EX2: Account balance, exposure, account info, portfolio, collateral."""
    start = time.perf_counter()
    failures: list[str] = []
    checked = 0

    try:
        from src.tools import (
            get_account_balance_tool,
            get_total_exposure_tool,
            get_account_info_tool,
            get_portfolio_snapshot_tool,
            get_collateral_info_tool,
        )

        for name, tool_fn in [
            ("balance", get_account_balance_tool),
            ("exposure", get_total_exposure_tool),
            ("account_info", get_account_info_tool),
            ("portfolio", get_portfolio_snapshot_tool),
            ("collateral", get_collateral_info_tool),
        ]:
            checked += 1
            result = tool_fn()
            if not result.success:
                failures.append(f"{name}: {result.error}")
    except Exception as e:
        failures.append(f"Account: {e}")

    return GateResult(
        gate_id="EX2",
        name="Account & Balance",
        passed=len(failures) == 0,
        checked=checked,
        duration_sec=time.perf_counter() - start,
        detail=f"{checked} endpoints",
        failures=failures,
    )


def _gate_exchange_market_data() -> GateResult:
    """EX3: Prices, OHLCV, funding, open interest, orderbook."""
    start = time.perf_counter()
    failures: list[str] = []
    checked = 0

    try:
        from src.config.config import get_config
        from src.tools import (
            get_price_tool,
            get_ohlcv_tool,
            get_funding_rate_tool,
            get_open_interest_tool,
            get_orderbook_tool,
        )

        config = get_config()
        symbol = config.smoke.symbols[0] if config.smoke.symbols else "BTCUSDT"

        for name, tool_fn, kwargs in [
            ("price", get_price_tool, {"symbol": symbol}),
            ("ohlcv", get_ohlcv_tool, {"symbol": symbol, "interval": "60", "limit": 5}),
            ("funding", get_funding_rate_tool, {"symbol": symbol}),
            ("open_interest", get_open_interest_tool, {"symbol": symbol}),
            ("orderbook", get_orderbook_tool, {"symbol": symbol, "limit": 5}),
        ]:
            checked += 1
            result = tool_fn(**kwargs)
            if not result.success:
                failures.append(f"{name}: {result.error}")
    except Exception as e:
        failures.append(f"Market data: {e}")

    return GateResult(
        gate_id="EX3",
        name="Market Data",
        passed=len(failures) == 0,
        checked=checked,
        duration_sec=time.perf_counter() - start,
        detail=f"{checked} endpoints",
        failures=failures,
    )


def _gate_exchange_order_flow() -> GateResult:
    """EX4: Place limit buy -> get open orders -> cancel (demo mode)."""
    start = time.perf_counter()
    failures: list[str] = []
    checked = 0

    try:
        from src.config.config import get_config
        from src.tools import (
            get_price_tool,
            limit_buy_tool,
            get_open_orders_tool,
            cancel_all_orders_tool,
            set_leverage_tool,
        )

        config = get_config()
        if not config.bybit.use_demo:
            return GateResult(
                gate_id="EX4",
                name="Order Flow",
                passed=True,
                checked=0,
                duration_sec=time.perf_counter() - start,
                detail="skipped (not demo mode)",
                failures=[],
            )

        symbol = config.smoke.symbols[-1] if config.smoke.symbols else "SOLUSDT"
        usd_size = config.smoke.usd_size

        # Set leverage
        checked += 1
        set_leverage_tool(symbol, 2)

        # Get price
        checked += 1
        price_result = get_price_tool(symbol)
        if not price_result.success or not price_result.data:
            failures.append(f"get price: {price_result.error}")
            return GateResult(
                gate_id="EX4", name="Order Flow", passed=False,
                checked=checked, duration_sec=time.perf_counter() - start,
                detail="price fetch failed", failures=failures,
            )

        current_price = float(price_result.data.get("price", 0))
        limit_price = round(current_price * 0.90, 2)  # 10% below for safety

        # Place limit buy
        checked += 1
        buy_result = limit_buy_tool(symbol, usd_size, limit_price)
        if not buy_result.success:
            failures.append(f"limit buy: {buy_result.error}")
        else:
            # Verify open orders
            checked += 1
            orders_result = get_open_orders_tool(symbol=symbol)
            if not orders_result.success:
                failures.append(f"open orders: {orders_result.error}")

            # Cancel all
            checked += 1
            cancel_result = cancel_all_orders_tool(symbol=symbol)
            if not cancel_result.success:
                failures.append(f"cancel: {cancel_result.error}")

    except Exception as e:
        failures.append(f"Order flow: {e}")

    return GateResult(
        gate_id="EX4",
        name="Order Flow",
        passed=len(failures) == 0,
        checked=checked,
        duration_sec=time.perf_counter() - start,
        detail=f"{checked} steps",
        failures=failures,
    )


def _gate_exchange_diagnostics() -> GateResult:
    """EX5: Rate limits, WebSocket status, health check, API environment."""
    start = time.perf_counter()
    failures: list[str] = []
    checked = 0

    try:
        from src.config.config import get_config
        from src.tools import (
            get_rate_limit_status_tool,
            get_websocket_status_tool,
            exchange_health_check_tool,
            get_api_environment_tool,
        )

        config = get_config()
        symbol = config.smoke.symbols[0] if config.smoke.symbols else "BTCUSDT"

        checked += 1
        result = get_rate_limit_status_tool()
        if not result.success:
            failures.append(f"rate limits: {result.error}")

        checked += 1
        result = get_websocket_status_tool()
        # WebSocket is optional, don't fail
        if not result.success:
            pass  # optional check

        checked += 1
        result = exchange_health_check_tool(symbol=symbol)
        if not result.success:
            failures.append(f"health check: {result.error}")

        checked += 1
        result = get_api_environment_tool()
        if not result.success:
            failures.append(f"api environment: {result.error}")

    except Exception as e:
        failures.append(f"Diagnostics: {e}")

    return GateResult(
        gate_id="EX5",
        name="Diagnostics",
        passed=len(failures) == 0,
        checked=checked,
        duration_sec=time.perf_counter() - start,
        detail=f"{checked} checks",
        failures=failures,
    )


# ── Pre-live gates ───────────────────────────────────────────────────

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
            available = float(result.data.get("available", 0))
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
            positions: list[dict[str, Any]] = (
                raw_data.get("positions", []) if isinstance(raw_data, dict)
                else raw_data if isinstance(raw_data, list)
                else []
            )
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


def _gate_pre_live_explicit_config(play_id: str) -> GateResult:
    """PL4: Play YAML must have explicit values for all critical account fields."""
    start = time.perf_counter()
    failures: list[str] = []

    try:
        from src.backtest.play import load_play
        import yaml

        play = load_play(play_id)

        plays_dir = Path("plays")
        play_path = plays_dir / f"{play_id}.yml"
        if not play_path.exists():
            matches = list(plays_dir.rglob(f"{play_id}.yml"))
            if matches:
                play_path = matches[0]

        if play_path.exists():
            with open(play_path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}

            account_raw = raw.get("account", {})
            if not account_raw:
                failures.append("No explicit 'account' section in Play YAML")
            else:
                required_fields = {
                    "starting_equity_usdt": "Starting capital",
                    "max_leverage": "Maximum leverage",
                    "max_drawdown_pct": "Max drawdown percentage",
                    "slippage_bps": "Slippage in basis points",
                }
                for field_name, label in required_fields.items():
                    if field_name not in account_raw:
                        failures.append(f"Missing explicit '{field_name}' ({label})")

                if "fee_model" not in account_raw or not account_raw.get("fee_model"):
                    failures.append("Missing explicit 'fee_model' (taker_bps, maker_bps)")
        else:
            failures.append(f"Play YAML not found: {play_path}")

    except Exception as e:
        failures.append(f"Config check: {e}")

    return GateResult(
        gate_id="PL4",
        name="Explicit Config (No Defaults)",
        passed=len(failures) == 0,
        checked=1,
        duration_sec=time.perf_counter() - start,
        detail=f"Play: {play_id}",
        failures=failures,
    )


# ── Real-data gates ──────────────────────────────────────────────────

def _extract_dates_from_play(play_path: Path) -> tuple[str, str] | None:
    """Extract --start and --end dates from play description field.

    Looks for pattern: Window: --start YYYY-MM-DD --end YYYY-MM-DD
    """
    import yaml
    try:
        with open(play_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        desc = raw.get("description", "")
        match = re.search(r"--start\s+(\d{4}-\d{2}-\d{2})\s+--end\s+(\d{4}-\d{2}-\d{2})", desc)
        if match:
            return (match.group(1), match.group(2))
    except Exception:
        pass
    return None


def _sync_real_data_manifest() -> GateResult:
    """Sync all data needed by RV plays. Serial DuckDB writes."""
    start = time.perf_counter()
    failures: list[str] = []
    checked = 0

    try:
        from datetime import datetime as dt
        from src.tools import sync_range_tool

        for entry in REAL_DATA_SYNC_MANIFEST:
            checked += 1
            symbol = entry["symbol"]
            try:
                result = sync_range_tool(
                    symbols=[symbol],
                    start=dt.strptime(entry["start"], "%Y-%m-%d"),
                    end=dt.strptime(entry["end"], "%Y-%m-%d"),
                    timeframes=entry["timeframes"],
                )
                if not result.success:
                    failures.append(f"{symbol}: {result.error}")
            except Exception as e:
                failures.append(f"{symbol}: {type(e).__name__}: {e}")
    except Exception as e:
        failures.append(f"Sync setup: {e}")

    return GateResult(
        gate_id="RD0",
        name="Real Data Sync",
        passed=len(failures) == 0,
        checked=checked,
        duration_sec=time.perf_counter() - start,
        detail=f"{checked} symbol/TF pairs",
        failures=failures,
    )


def _gate_real_data_phase(
    phase: str,
    gate_id: str,
    max_workers: int | None = None,
    play_timeout: int = PLAY_TIMEOUT_SEC,
) -> GateResult:
    """Run all real-data plays in a phase directory in parallel."""
    start = time.perf_counter()
    failures: list[str] = []
    total_trades = 0

    phase_dir = Path("plays") / "validation" / "real_data" / phase
    play_files = sorted(phase_dir.glob("*.yml"))
    checked = len(play_files)

    if checked == 0:
        return GateResult(
            gate_id=gate_id, name=f"Real {phase.title()}",
            passed=True, checked=0,
            duration_sec=time.perf_counter() - start,
            detail="no plays found", failures=[],
        )

    # Build (play_id, start, end) tuples
    tasks: list[tuple[str, str, str]] = []
    for pf in play_files:
        dates = _extract_dates_from_play(pf)
        if dates is None:
            failures.append(f"{pf.stem}: no date window in description")
            continue
        tasks.append((pf.stem, dates[0], dates[1]))

    workers = max_workers or _get_max_workers()

    if len(tasks) <= 2:
        for i, (pid, s, e) in enumerate(tasks, 1):
            console.print(f"       [dim]{gate_id}[/] {i}/{len(tasks)} {pid}...", highlight=False)
            _, trades, error = _run_single_play_real(pid, s, e)
            total_trades += trades
            if error:
                failures.append(error)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_run_single_play_real, pid, s, e): pid
                for pid, s, e in tasks
            }
            trades, fails = _collect_futures_with_timeout(futures, play_timeout, gate_id)
            total_trades += trades
            failures.extend(fails)

    return GateResult(
        gate_id=gate_id,
        name=f"Real {phase.title()}",
        passed=len(failures) == 0,
        checked=checked,
        duration_sec=time.perf_counter() - start,
        detail=f"{checked} plays, {total_trades} trades",
        failures=sorted(failures),
    )


# ── Staged gate orchestration ────────────────────────────────────────

def _run_staged_gates(
    schedule: list[list[Callable[[], GateResult]]],
    fail_fast: bool = True,
    tier: str = "",
    start_time: float = 0.0,
    json_output: bool = False,
    gate_timeout: int = GATE_TIMEOUT_SEC,
) -> list[GateResult]:
    """Run gates in stages. Gates within a stage run concurrently.

    Each gate result is printed immediately and checkpointed to disk.

    Args:
        schedule: List of stages. Each stage is a list of gate functions.
        fail_fast: If True, stop after a stage with any failure.
        tier: Tier name for checkpoint reporting.
        start_time: perf_counter() at validation start, for checkpoint timing.
        json_output: If True, suppress incremental console output.
        gate_timeout: Timeout in seconds for each gate in a concurrent stage.

    Returns:
        All GateResults from all completed stages.
    """
    all_results: list[GateResult] = []

    for stage in schedule:
        if len(stage) == 0:
            continue

        if len(stage) == 1:
            # Single gate -- run directly, no thread overhead
            result = stage[0]()
            all_results.append(result)
            if not json_output:
                _print_gate_result(result)
            _checkpoint_report(tier, all_results, start_time)
        else:
            # Multiple gates -- run concurrently in threads with timeout
            with ThreadPoolExecutor(max_workers=len(stage)) as pool:
                futures = {pool.submit(fn): fn for fn in stage}
                try:
                    for future in as_completed(futures, timeout=gate_timeout):
                        try:
                            result = future.result()
                            all_results.append(result)
                            if not json_output:
                                _print_gate_result(result)
                            _checkpoint_report(tier, all_results, start_time)
                        except Exception as e:
                            timeout_result = GateResult(
                                gate_id="??",
                                name="ERROR",
                                passed=False,
                                checked=0,
                                duration_sec=gate_timeout,
                                detail=f"gate error: {e}",
                                failures=[str(e)],
                            )
                            all_results.append(timeout_result)
                            if not json_output:
                                _print_gate_result(timeout_result)
                            _checkpoint_report(tier, all_results, start_time)
                except (FuturesTimeoutError, TimeoutError):
                    # as_completed raises TimeoutError when deadline is hit
                    # and there are still unfinished futures
                    unfinished = [f for f in futures if not f.done()]
                    for future in unfinished:
                        fn = futures[future]
                        name = getattr(fn, '__name__', '??')
                        timeout_result = GateResult(
                            gate_id="??",
                            name=f"TIMEOUT ({name})",
                            passed=False,
                            checked=0,
                            duration_sec=gate_timeout,
                            detail=f"gate exceeded {gate_timeout}s",
                            failures=[f"TIMEOUT after {gate_timeout}s"],
                        )
                        all_results.append(timeout_result)
                        if not json_output:
                            _print_gate_result(timeout_result)
                    _checkpoint_report(tier, all_results, start_time)

        # Check for failures in this stage
        if fail_fast and any(not r.passed for r in all_results):
            break

    return all_results


def _run_gates(
    gates: list,
    fail_fast: bool = True,
    tier: str = "",
    start_time: float = 0.0,
    json_output: bool = False,
) -> list[GateResult]:
    """Run a list of gate functions sequentially with incremental reporting."""
    results: list[GateResult] = []
    for gate_fn in gates:
        result = gate_fn()
        results.append(result)
        if not json_output:
            _print_gate_result(result)
        _checkpoint_report(tier, results, start_time)
        if not result.passed and fail_fast:
            break
    return results


# ── Module definitions ───────────────────────────────────────────────

def _make_module_definitions(
    max_workers: int | None = None,
    play_timeout: int = PLAY_TIMEOUT_SEC,
) -> dict[str, list[Callable[[], GateResult]]]:
    """Build module name -> gate function list mapping.

    Uses closures to capture max_workers and play_timeout for play suite gates.
    """
    w = max_workers
    t = play_timeout

    return {
        "core": [_gate_core_plays],
        "risk": [_gate_risk_stops],
        "audits": [_gate_registry_contract, _gate_incremental_parity],
        "operators": [lambda: _gate_play_suite("validation/operators", "G8", "Operator Suite", w, t)],
        "structures": [lambda: _gate_play_suite("validation/structures", "G9", "Structure Suite", w, t)],
        "complexity": [lambda: _gate_play_suite("validation/complexity", "G10", "Complexity Ladder", w, t)],
        "indicators": [lambda: _gate_play_suite("validation/indicators", "G12", "Indicator Suite", w, t)],
        "patterns": [lambda: _gate_play_suite("validation/patterns", "G13", "Pattern Suite", w, t)],
        "parity": [_gate_structure_parity, _gate_rollup_parity],
        "sim": [_gate_sim_orders],
        "metrics": [_gate_metrics_audit],
        "determinism": [_gate_determinism],
        "coverage": [_gate_coverage_check],
        # Real-data modules
        "real-accumulation": [lambda: _gate_real_data_phase("accumulation", "RD1", w, t)],
        "real-markup": [lambda: _gate_real_data_phase("markup", "RD2", w, t)],
        "real-distribution": [lambda: _gate_real_data_phase("distribution", "RD3", w, t)],
        "real-markdown": [lambda: _gate_real_data_phase("markdown", "RD4", w, t)],
    }


MODULE_NAMES = [
    "core", "risk", "audits", "operators", "structures", "complexity",
    "indicators", "patterns", "parity", "sim", "metrics", "determinism",
    "coverage",
    "real-accumulation", "real-markup", "real-distribution", "real-markdown",
]


# ── Module validation entry point ────────────────────────────────────

def run_module_validation(
    module_name: str,
    max_workers: int | None = None,
    json_output: bool = False,
    play_timeout: int = PLAY_TIMEOUT_SEC,
) -> int:
    """Run a single validation module independently.

    Returns:
        Exit code: 0 if all gates pass, 1 if any fail.
    """
    from src.utils.logger import suppress_for_validation
    suppress_for_validation()

    modules = _make_module_definitions(max_workers, play_timeout)
    if module_name not in modules:
        console.print(f"[bold red]Unknown module: {module_name}[/]")
        console.print(f"[dim]Available: {', '.join(MODULE_NAMES)}[/]")
        return 1

    start = time.perf_counter()
    tier_label = f"module:{module_name}"

    if not json_output:
        console.print(f"\n[bold cyan]TRADE VALIDATION[/]  [dim]\\[module: {module_name}][/]")
        console.print(f"[dim]{'=' * 54}[/]")

    gate_fns = modules[module_name]
    results: list[GateResult] = []
    for fn in gate_fns:
        result = fn()
        results.append(result)
        if not json_output:
            _print_gate_result(result)
        _checkpoint_report(tier_label, results, start)

    report = ValidationReport(
        tier=tier_label,
        gates=results,
        duration_sec=time.perf_counter() - start,
    )

    _finalize_report(tier_label, results, start)

    if json_output:
        console.print(json.dumps(report.to_dict(), indent=2))
    else:
        _print_summary(report)

    return 0 if report.passed else 1


# ── Tier orchestration ────────────────────────────────────────────────

def run_validation(
    tier: Tier,
    play_id: str | None = None,
    fail_fast: bool = True,
    json_output: bool = False,
    max_workers: int | None = None,
    module_name: str | None = None,
    play_timeout: int = PLAY_TIMEOUT_SEC,
    gate_timeout: int = GATE_TIMEOUT_SEC,
) -> int:
    """
    Run the unified validation suite at the specified tier.

    Returns:
        Exit code: 0 if all gates pass, 1 if any fail.
    """
    # Module tier delegates to run_module_validation
    if tier == Tier.MODULE:
        if not module_name:
            console.print("[bold red]module tier requires --module[/]")
            return 1
        return run_module_validation(
            module_name, max_workers=max_workers,
            json_output=json_output, play_timeout=play_timeout,
        )

    # Suppress noisy logging for validation runs (except exchange tier which needs app init)
    if tier != Tier.EXCHANGE:
        from src.utils.logger import suppress_for_validation
        suppress_for_validation()

    start = time.perf_counter()
    w = max_workers
    t = play_timeout

    if not json_output:
        console.print(f"\n[bold cyan]TRADE VALIDATION[/]  [dim]\\[{tier.value}][/]")
        console.print(f"[dim]{'=' * 54}[/]")

    # Build gate schedule based on tier
    if tier == Tier.PRE_LIVE:
        if not play_id:
            console.print("[bold red]pre-live tier requires --play[/]")
            return 1
        gates = [
            lambda: _gate_pre_live_explicit_config(play_id),
            _gate_pre_live_connectivity,
            lambda: _gate_pre_live_balance(play_id),
            lambda: _gate_pre_live_no_conflicts(play_id),
            _gate_yaml_parse,
            _gate_core_plays,
        ]
        results = _run_gates(
            gates, fail_fast=fail_fast,
            tier=tier.value, start_time=start, json_output=json_output,
        )

    elif tier == Tier.EXCHANGE:
        gates = [
            _gate_exchange_connectivity,
            _gate_exchange_account,
            _gate_exchange_market_data,
            _gate_exchange_order_flow,
            _gate_exchange_diagnostics,
        ]
        results = _run_gates(
            gates, fail_fast=fail_fast,
            tier=tier.value, start_time=start, json_output=json_output,
        )

    elif tier == Tier.REAL:
        # Real-data tier: sync phase (serial) then run phase (parallel)
        results = []

        # Phase 1: Sync all data
        if not json_output:
            console.print(" [dim]Syncing real data...[/]")
        sync_result = _sync_real_data_manifest()
        results.append(sync_result)
        if not json_output:
            _print_gate_result(sync_result)
        _checkpoint_report(tier.value, results, start)

        if not sync_result.passed and fail_fast:
            pass  # skip run phase
        else:
            # Phase 2: Run all phases in parallel with timeout
            phase_gates = [
                lambda: _gate_real_data_phase("accumulation", "RD1", w, t),
                lambda: _gate_real_data_phase("markup", "RD2", w, t),
                lambda: _gate_real_data_phase("distribution", "RD3", w, t),
                lambda: _gate_real_data_phase("markdown", "RD4", w, t),
            ]
            # Run all 4 phase gates concurrently with timeout
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {pool.submit(fn): fn for fn in phase_gates}
                try:
                    for future in as_completed(futures, timeout=gate_timeout):
                        try:
                            result = future.result()
                            results.append(result)
                            if not json_output:
                                _print_gate_result(result)
                            _checkpoint_report(tier.value, results, start)
                        except Exception as e:
                            timeout_result = GateResult(
                                gate_id="RD?",
                                name="Real Data ERROR",
                                passed=False,
                                checked=0,
                                duration_sec=gate_timeout,
                                detail=f"phase error: {e}",
                                failures=[str(e)],
                            )
                            results.append(timeout_result)
                            if not json_output:
                                _print_gate_result(timeout_result)
                            _checkpoint_report(tier.value, results, start)
                except (FuturesTimeoutError, TimeoutError):
                    unfinished = [f for f in futures if not f.done()]
                    for future in unfinished:
                        timeout_result = GateResult(
                            gate_id="RD?",
                            name="Real Data TIMEOUT",
                            passed=False,
                            checked=0,
                            duration_sec=gate_timeout,
                            detail=f"phase exceeded {gate_timeout}s",
                            failures=[f"TIMEOUT after {gate_timeout}s"],
                        )
                        results.append(timeout_result)
                        if not json_output:
                            _print_gate_result(timeout_result)
                    _checkpoint_report(tier.value, results, start)

    else:
        # Staged schedule for quick/standard/full
        # Each stage is a list of gates that can run concurrently
        schedule: list[list[Callable[[], GateResult]]] = []

        # Stage 0: YAML parse (fast, sequential)
        schedule.append([_gate_yaml_parse])

        # Stage 1: registry + parity audits (parallel)
        schedule.append([_gate_registry_contract, _gate_incremental_parity])

        # Stage 2: core + risk plays (parallel)
        schedule.append([_gate_core_plays, _gate_risk_stops])

        if tier in (Tier.STANDARD, Tier.FULL):
            # Stage 3: structure/rollup/sim (parallel)
            schedule.append([_gate_structure_parity, _gate_rollup_parity, _gate_sim_orders])

            # Stage 4: operator/structure/complexity suites (parallel, each internally parallel)
            schedule.append([
                lambda: _gate_play_suite("validation/operators", "G8", "Operator Suite", w, t),
                lambda: _gate_play_suite("validation/structures", "G9", "Structure Suite", w, t),
                lambda: _gate_play_suite("validation/complexity", "G10", "Complexity Ladder", w, t),
            ])

            # Stage 5: metrics
            schedule.append([_gate_metrics_audit])

        if tier == Tier.FULL:
            # Stage 6: indicator + pattern suites (parallel, each internally parallel)
            schedule.append([
                lambda: _gate_play_suite("validation/indicators", "G12", "Indicator Suite", w, t),
                lambda: _gate_play_suite("validation/patterns", "G13", "Pattern Suite", w, t),
            ])

            # Stage 7: determinism
            schedule.append([_gate_determinism])

        results = _run_staged_gates(
            schedule, fail_fast=fail_fast,
            tier=tier.value, start_time=start,
            json_output=json_output, gate_timeout=gate_timeout,
        )

    report = ValidationReport(
        tier=tier.value,
        gates=results,
        duration_sec=time.perf_counter() - start,
    )

    _finalize_report(tier.value, results, start)

    if json_output:
        console.print(json.dumps(report.to_dict(), indent=2))
    else:
        _print_summary(report)

    return 0 if report.passed else 1


# ── Reporting ─────────────────────────────────────────────────────────

def _print_summary(report: ValidationReport) -> None:
    """Print final summary line (gate lines already printed incrementally)."""
    console.print(f"[dim]{'=' * 54}[/]")

    if report.passed:
        console.print(
            f" [bold green]RESULT: ALL {len(report.gates)} GATES PASSED[/]"
            f"  [dim]({report.duration_sec:.1f}s)[/]"
        )
    else:
        console.print(
            f" [bold red]RESULT: {report.failed_count} of {len(report.gates)} GATES FAILED[/]"
            f"  [dim]({report.duration_sec:.1f}s)[/]"
        )

    console.print()
