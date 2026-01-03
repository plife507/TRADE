"""
Artifact writing module for BacktestEngine.

This module handles artifact generation and output:
- calculate_drawdowns_impl: Calculate drawdown values for equity curve
- write_artifacts_impl: Write run artifacts to run_dir
- Supports Parquet format for trades, equity, account_curve
- JSON for result.json with artifact hashes

All functions accept data as parameters.
The BacktestEngine delegates to these functions, maintaining the same public API.
"""

import json
import hashlib
import pandas as pd
from pathlib import Path
from typing import TYPE_CHECKING

from .artifacts.parquet_writer import write_parquet
from .metrics import compute_time_based_returns

if TYPE_CHECKING:
    from .types import BacktestResult, EquityPoint


def calculate_drawdowns_impl(equity_curve: list["EquityPoint"]) -> None:
    """
    Calculate drawdown values for equity curve.

    Modifies EquityPoint objects in place with drawdown and drawdown_pct.

    Args:
        equity_curve: List of EquityPoint objects to update
    """
    if not equity_curve:
        return

    peak = equity_curve[0].equity

    for point in equity_curve:
        if point.equity > peak:
            peak = point.equity

        point.drawdown = peak - point.equity
        point.drawdown_pct = (point.drawdown / peak * 100) if peak > 0 else 0.0


def write_artifacts_impl(
    result: "BacktestResult",
    run_dir: Path,
    logger=None,
) -> None:
    """
    Write run artifacts to run_dir.

    Phase 3.2: Parquet-only format for trades/equity/account_curve.
    JSON unchanged (result.json, pipeline_signature.json).

    Args:
        result: BacktestResult with trades, equity curve, etc.
        run_dir: Directory to write artifacts
        logger: Optional logger
    """
    if not run_dir:
        return

    run_dir.mkdir(parents=True, exist_ok=True)

    # Write trades.parquet (Phase 3.2: Parquet-only)
    trades_path = run_dir / "trades.parquet"
    if result.trades:
        trades_df = pd.DataFrame([
            {
                "trade_id": t.trade_id,
                "symbol": t.symbol,
                "side": t.side.upper(),
                "entry_time": t.entry_time.isoformat(),
                "exit_time": t.exit_time.isoformat() if t.exit_time else "",
                "entry_price": t.entry_price,
                "exit_price": t.exit_price or 0,
                "qty": t.entry_size,
                "pnl": t.net_pnl,
                "pnl_pct": t.pnl_pct,
                # Phase 4: Bar indices
                "entry_bar_index": t.entry_bar_index,
                "exit_bar_index": t.exit_bar_index,
                "duration_bars": t.duration_bars,
                # Phase 4: Exit trigger classification
                "exit_reason": t.exit_reason or "",
                "exit_price_source": t.exit_price_source or "",
                # Phase 4: Snapshot readiness at entry/exit
                "entry_ready": t.entry_ready,
                "exit_ready": t.exit_ready if t.exit_ready is not None else "",
                # Risk levels
                "stop_loss": t.stop_loss or "",
                "take_profit": t.take_profit or "",
            }
            for t in result.trades
        ])
    else:
        # Write empty file with headers
        trades_df = pd.DataFrame(columns=[
            "trade_id", "symbol", "side", "entry_time", "exit_time",
            "entry_price", "exit_price", "qty", "pnl", "pnl_pct",
            # Phase 4 fields
            "entry_bar_index", "exit_bar_index", "duration_bars",
            "exit_reason", "exit_price_source",
            "entry_ready", "exit_ready",
            "stop_loss", "take_profit"
        ])
    write_parquet(trades_df, trades_path)

    # Write equity.parquet (Phase 3.2: Parquet-only)
    equity_path = run_dir / "equity.parquet"
    equity_df = pd.DataFrame([
        {
            "ts": e.timestamp.isoformat(),
            "equity": e.equity,
            "drawdown_abs": e.drawdown,
            "drawdown_pct": e.drawdown_pct,
        }
        for e in result.equity_curve
    ])
    write_parquet(equity_df, equity_path)

    # Write account_curve.parquet (Phase 3.2: Parquet-only)
    account_curve_path = run_dir / "account_curve.parquet"
    if result.account_curve:
        account_df = pd.DataFrame([
            {
                "ts": a.timestamp.isoformat(),
                "equity_usdt": a.equity_usdt,
                "used_margin_usdt": a.used_margin_usdt,
                "free_margin_usdt": a.free_margin_usdt,
                "available_balance_usdt": a.available_balance_usdt,
                "maintenance_margin_usdt": a.maintenance_margin_usdt,
                "has_position": a.has_position,
                "entries_disabled": a.entries_disabled,
            }
            for a in result.account_curve
        ])
    else:
        account_df = pd.DataFrame(columns=[
            "ts", "equity_usdt", "used_margin_usdt", "free_margin_usdt",
            "available_balance_usdt", "maintenance_margin_usdt",
            "has_position", "entries_disabled"
        ])
    write_parquet(account_df, account_curve_path)

    # Write returns.json (Phase 4: Time-based analytics)
    # Compute daily/weekly/monthly returns from equity curve
    if result.equity_curve:
        time_based_returns = compute_time_based_returns(result.equity_curve)
        returns_path = run_dir / "returns.json"
        with open(returns_path, "w") as f:
            json.dump(time_based_returns.to_dict(), f, indent=2, sort_keys=True)

    # Compute artifact hashes for reproducibility (Parquet files)
    artifact_hashes = {}
    for path_name, path in [
        ("trades.parquet", trades_path),
        ("equity.parquet", equity_path),
        ("account_curve.parquet", account_curve_path),
    ]:
        if path.exists():
            with open(path, "rb") as f:
                artifact_hashes[path_name] = hashlib.sha256(f.read()).hexdigest()

    # Build result dict with artifact hashes
    result_dict = result.to_dict()
    result_dict["artifact_hashes"] = artifact_hashes
    result_dict["account_curve_path"] = "account_curve.parquet"

    # Write result.json
    result_path = run_dir / "result.json"
    with open(result_path, "w") as f:
        json.dump(result_dict, f, indent=2, sort_keys=True)

    if logger:
        logger.info(f"Artifacts written to {run_dir}")
