"""
Artifact writing module for backtest results.

This module handles artifact generation and output:
- calculate_drawdowns_impl: Calculate drawdown values for equity curve
- write_artifacts_impl: Write run artifacts to run_dir
- Supports Parquet format for trades, equity, account_curve
- JSON for result.json with artifact hashes

All functions accept data as parameters and are used by BacktestRunner.

Schema Contract:
- Field names and types defined in src/viz/schemas/artifact_schema.py
- Timestamps stored as BOTH ISO strings AND epoch seconds for efficiency
- Currency fields use *_usdt suffix per CLAUDE.md convention
"""

import json
import hashlib
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .artifacts.parquet_writer import write_parquet
from .metrics import compute_time_based_returns

if TYPE_CHECKING:
    from .types import BacktestResult, EquityPoint


def _to_epoch(dt: datetime | None) -> int | None:
    """Convert datetime to Unix epoch seconds."""
    if dt is None:
        return None
    return int(dt.timestamp())


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

    # Write trades.parquet (Schema: src/viz/schemas/artifact_schema.py)
    # Dual timestamps: ISO string for human readability, epoch for viz efficiency
    trades_path = run_dir / "trades.parquet"
    if result.trades:
        trades_df = pd.DataFrame([
            {
                # Identity
                "trade_id": t.trade_id,
                "symbol": t.symbol,
                "side": t.side.lower(),  # Standardized: "long"/"short"
                # Timestamps - dual format
                "entry_time": t.entry_time.isoformat(),
                "entry_ts": _to_epoch(t.entry_time),
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                "exit_ts": _to_epoch(t.exit_time),
                # Prices
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                # Sizing (USDT standard per CLAUDE.md)
                "entry_size_usdt": t.entry_size_usdt,
                # PnL
                "net_pnl": t.net_pnl,
                "pnl_pct": t.pnl_pct,
                # Risk levels
                "stop_loss": t.stop_loss,
                "take_profit": t.take_profit,
                # Exit metadata
                "exit_reason": t.exit_reason,
                "exit_price_source": t.exit_price_source,
                # Bar indices
                "entry_bar_index": t.entry_bar_index,
                "exit_bar_index": t.exit_bar_index,
                "duration_bars": t.duration_bars,
                # Trade quality
                "mae_pct": getattr(t, "mae_pct", 0.0),
                "mfe_pct": getattr(t, "mfe_pct", 0.0),
                # Funding
                "funding_pnl": getattr(t, "funding_pnl", 0.0),
            }
            for t in result.trades
        ])
    else:
        # Write empty file with canonical schema columns
        trades_df = pd.DataFrame(columns=[
            "trade_id", "symbol", "side",
            "entry_time", "entry_ts", "exit_time", "exit_ts",
            "entry_price", "exit_price", "entry_size_usdt",
            "net_pnl", "pnl_pct",
            "stop_loss", "take_profit",
            "exit_reason", "exit_price_source",
            "entry_bar_index", "exit_bar_index", "duration_bars",
            "mae_pct", "mfe_pct", "funding_pnl",
        ])
    write_parquet(trades_df, trades_path)

    # Write equity.parquet (Schema: src/viz/schemas/artifact_schema.py)
    # Dual timestamps: ISO string for human readability, epoch for viz efficiency
    equity_path = run_dir / "equity.parquet"
    equity_df = pd.DataFrame([
        {
            "timestamp": e.timestamp.isoformat(),  # ISO string for readability
            "ts": _to_epoch(e.timestamp),  # Epoch seconds for viz efficiency
            "equity": e.equity,
            "drawdown": e.drawdown,
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
