"""
Unified validation for TRADE.

Single entry point: python trade_cli.py validate [tier]

Tiers:
  quick     (~10s)  - pre-commit: YAML parse, registry, parity, 5 core plays
  standard  (~2min) - pre-merge: + structures, rollup, sim, suites, metrics audit
  full      (~10min)- pre-release: + full indicator/pattern suites, determinism
  pre-live          - connectivity + readiness gate for a specific play
  exchange  (~30s)  - exchange integration (API, account, market data, order flow)
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

    suite_dir = Path("plays") / suite_name
    play_files = sorted(suite_dir.glob("*.yml"))
    checked = len(play_files)

    for pf in play_files:
        pid = pf.stem
        try:
            play = load_play(pid)

            # All validation plays have a validation: block with pattern
            # Engine factory auto-computes warmup + bars from play
            engine = create_engine_from_play(play, use_synthetic=True)

            result = run_engine_with_play(engine, play)
            trades = len(result.trades) if hasattr(result, "trades") else 0
            total_trades += trades
            # Fail on zero trades — validation plays should always generate trades
            if trades == 0 and play.validation is not None:
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


def _gate_determinism() -> GateResult:
    """G14: Engine determinism - same input = same output."""
    start = time.perf_counter()
    failures: list[str] = []

    from src.backtest.play import load_play
    from src.backtest.engine_factory import create_engine_from_play, run_engine_with_play
    from src.backtest.artifacts.hashes import compute_trades_hash

    checked = 0
    for pid in CORE_PLAY_IDS:
        checked += 1
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

    # Suppress noisy logging for validation runs (except exchange tier which needs app init)
    if tier != Tier.EXCHANGE:
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
    elif tier == Tier.EXCHANGE:
        gates = [
            _gate_exchange_connectivity,
            _gate_exchange_account,
            _gate_exchange_market_data,
            _gate_exchange_order_flow,
            _gate_exchange_diagnostics,
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
            # standard adds: G5-G11
            gates.extend([
                _gate_structure_parity,
                _gate_rollup_parity,
                _gate_sim_orders,
                lambda: _gate_play_suite("validation/operators", "G8", "Operator Suite"),
                lambda: _gate_play_suite("validation/structures", "G9", "Structure Suite"),
                lambda: _gate_play_suite("validation/complexity", "G10", "Complexity Ladder"),
                _gate_metrics_audit,
            ])

        if tier == Tier.FULL:
            # full adds: G12-G14
            gates.extend([
                lambda: _gate_play_suite("validation/indicators", "G12", "Indicator Suite"),
                lambda: _gate_play_suite("validation/patterns", "G13", "Pattern Suite"),
                _gate_determinism,
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
