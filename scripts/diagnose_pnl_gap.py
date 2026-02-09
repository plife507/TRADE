"""
Diagnose the ~$7/trade PnL discrepancy between sum(trades.net_pnl) and result.json net_pnl.

Theory: The gap comes from equity_curve[-1] capturing unrealized PnL (at mark_price = bar.close,
no slippage) while trade records use fill prices (with slippage applied).

This script reads actual backtest artifacts and traces the exact gap per trade.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def analyze_play(play_stem: str) -> None:
    """Analyze PnL gap for a play's most recent run."""
    # Find artifacts (directory names are lowercase)
    base = ROOT / "backtests" / "_validation" / play_stem.lower()
    if not base.exists():
        print(f"No artifacts for {play_stem} (tried {base})")
        return

    artifact_dir = None
    for symbol_dir in sorted(base.iterdir()):
        if symbol_dir.is_dir():
            # Sort by modification time (newest first)
            run_dirs = [d for d in symbol_dir.iterdir() if d.is_dir() and (d / "result.json").exists()]
            run_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
            if run_dirs:
                artifact_dir = run_dirs[0]
                break

    if artifact_dir is None:
        print(f"No result.json found for {play_stem}")
        return

    # Load result.json
    with open(artifact_dir / "result.json") as f:
        result = json.load(f)

    # Load trades (parquet or csv)
    trades_parquet = artifact_dir / "trades.parquet"
    trades_csv = artifact_dir / "trades.csv"
    if trades_parquet.exists():
        df = pd.read_parquet(trades_parquet)
    elif trades_csv.exists():
        df = pd.read_csv(trades_csv)
    else:
        print(f"No trades file for {play_stem}")
        return

    if len(df) == 0:
        print(f"No trades in {play_stem}")
        return

    # Load equity curve (parquet or csv)
    equity_parquet = artifact_dir / "equity.parquet"
    equity_csv = artifact_dir / "equity_curve.csv"
    equity_df = None
    if equity_parquet.exists():
        equity_df = pd.read_parquet(equity_parquet)
    elif equity_csv.exists():
        equity_df = pd.read_csv(equity_csv)

    # Key values
    initial_equity = result.get("initial_equity", 10000.0)
    final_equity = result.get("final_equity", 0.0)
    net_pnl_result = result.get("net_pnl_usdt", 0.0)

    # Compute sum of trades
    trade_sum_net_pnl = df["net_pnl"].sum() if "net_pnl" in df.columns else 0.0
    trade_sum_realized = df["realized_pnl"].sum() if "realized_pnl" in df.columns else 0.0
    trade_sum_fees = df["fees_paid"].sum() if "fees_paid" in df.columns else 0.0

    # The gap
    gap = net_pnl_result - trade_sum_net_pnl
    gap_per_trade = gap / len(df) if len(df) > 0 else 0.0

    print(f"\n{'='*70}")
    print(f"Play: {play_stem}")
    print(f"Trades: {len(df)}")
    print(f"{'='*70}")
    print(f"\nresult.json:")
    print(f"  initial_equity:  {initial_equity:.2f}")
    print(f"  final_equity:    {final_equity:.2f}")
    print(f"  net_pnl_usdt:    {net_pnl_result:.2f}  (= final - initial)")
    print(f"\ntrades.csv:")
    print(f"  sum(net_pnl):    {trade_sum_net_pnl:.2f}")
    print(f"  sum(realized):   {trade_sum_realized:.2f}")
    print(f"  sum(fees):       {trade_sum_fees:.2f}")
    print(f"  computed net:    {trade_sum_realized - trade_sum_fees:.2f}")
    print(f"\nGAP:")
    print(f"  result - trades: {gap:.2f}")
    print(f"  gap per trade:   {gap_per_trade:.2f}")

    # Check equity curve
    if equity_df is not None and len(equity_df) > 0:
        last_eq_point = equity_df.iloc[-1]["equity"] if "equity" in equity_df.columns else None
        if last_eq_point is not None:
            print(f"\nEquity curve:")
            print(f"  equity_curve[-1]: {last_eq_point:.2f}")
            print(f"  final_equity:     {final_equity:.2f}")
            print(f"  difference:       {final_equity - last_eq_point:.2f}")

    # Per-trade breakdown
    print(f"\nPer-Trade Details:")
    print(f"{'ID':>8} {'Side':>5} {'Entry':>12} {'Exit':>12} {'Reason':>8} "
          f"{'Realized':>10} {'Fees':>10} {'NetPnL':>10} {'Slippage':>10}")
    print("-" * 100)

    for _, row in df.iterrows():
        trade_id = row.get("trade_id", "?")
        side = row.get("side", "?")
        entry_p = row.get("entry_price", 0.0)
        exit_p = row.get("exit_price", 0.0)
        reason = row.get("exit_reason", "?")
        realized = row.get("realized_pnl", 0.0)
        fees = row.get("fees_paid", 0.0)
        net = row.get("net_pnl", 0.0)
        # Check if slippage column exists
        slippage = row.get("slippage", 0.0) if "slippage" in df.columns else 0.0

        # Compute expected realized pnl from prices
        size = row.get("entry_size", 0.0)
        if side == "long":
            expected_realized = (exit_p - entry_p) * size
        else:
            expected_realized = (entry_p - exit_p) * size

        pnl_diff = realized - expected_realized

        print(f"{trade_id:>8} {side:>5} {entry_p:>12.2f} {exit_p:>12.2f} {reason:>8} "
              f"{realized:>10.2f} {fees:>10.2f} {net:>10.2f} {slippage:>10.4f}")

        if abs(pnl_diff) > 0.01:
            print(f"         *** realized vs expected diff: {pnl_diff:.4f}")

    # Check for end_of_data exits
    eod_trades = df[df["exit_reason"] == "end_of_data"] if "exit_reason" in df.columns else pd.DataFrame()
    if len(eod_trades) > 0:
        print(f"\n*** {len(eod_trades)} end_of_data trade(s) detected ***")
        print("   These close at last bar with slippage but equity_curve[-1] uses mark price (no slippage)")

        # Compute the expected gap from the end_of_data trade
        for _, eod in eod_trades.iterrows():
            entry_p = eod.get("entry_price", 0.0)
            exit_p = eod.get("exit_price", 0.0)
            size = eod.get("entry_size", 0.0)
            side = eod.get("side", "long")
            fees = eod.get("fees_paid", 0.0)
            net = eod.get("net_pnl", 0.0)

            # equity_curve[-1] has unrealized PnL at mark_price (close, no slippage)
            # The force_close applies slippage via fill_exit, so fill_price != mark_price
            # For equity_curve: unrealized = (mark_price - entry) * size  [long]
            # For trade: realized = (fill_price - entry) * size
            # But mark_price = bar.close and fill_price = bar.close + slippage
            # For long exit: fill_price = close - slippage (adverse)
            # So: gap = slippage * size + exit_fee
            # Wait: equity_curve already includes entry fee (cash was reduced)
            # But equity_curve doesn't include exit fee (not closed yet when recorded)

            if equity_df is not None and len(equity_df) > 0:
                last_eq = equity_df.iloc[-1]["equity"] if "equity" in equity_df.columns else 0
                # equity_curve[-1] = cash_before_exit + unrealized_pnl
                # cash_before_exit = initial - entry_fee + sum(prev_trades_realized) - sum(prev_trades_exit_fee)
                # unrealized = (mark_price - entry) * size
                #
                # After force close:
                # cash_after = cash_before + realized_pnl - exit_fee
                # where realized_pnl = (fill_price - entry) * size [fill_price has slippage]
                #
                # Gap = equity_before - equity_after
                # = (cash_before + unrealized) - (cash_before + realized - exit_fee)
                # = unrealized - realized + exit_fee
                # = ((mark - entry)*size) - ((fill - entry)*size) + exit_fee
                # = (mark - fill)*size + exit_fee
                # = slippage_amount * size + exit_fee

                # We can compute entry_fee from fees - exit_fee
                # exit_fee = exit_notional * fee_rate = size * fill_price * fee_rate
                # But we don't have fee_rate directly. Let's back-compute:
                exit_notional = size * exit_p
                # From the overall fee structure: entry_notional * rate + exit_notional * rate = total_fees_this_trade
                # entry_notional = size * entry_price (approximately, entry also has slippage)
                entry_notional = size * entry_p
                if entry_notional + exit_notional > 0:
                    implied_fee_rate = fees / (entry_notional + exit_notional)
                else:
                    implied_fee_rate = 0.0

                exit_fee_est = exit_notional * implied_fee_rate

                print(f"\n   End-of-data trade analysis:")
                print(f"     entry_price:     {entry_p:.2f}")
                print(f"     exit_price:      {exit_p:.2f}  (includes slippage)")
                print(f"     size:            {size:.6f}")
                print(f"     total fees:      {fees:.2f}")
                print(f"     implied fee_rate:{implied_fee_rate*100:.4f}%")
                print(f"     est exit_fee:    {exit_fee_est:.2f}")
                print(f"     total gap:       {gap:.2f}")
                print(f"     gap - exit_fee:  {gap - exit_fee_est:.2f} (= slippage cost)")
    else:
        print(f"\n*** No end_of_data trades - all positions closed by TP/SL/signal ***")
        print("   If gap still exists, it's NOT from end_of_data force close")


def main():
    plays = [
        "RV_001_btc_accum_ema_zone",
        "RV_002_eth_accum_bbands_squeeze",
        "RV_003_sol_accum_rsi_macd_mfi",
        "RV_008_btc_accum_cases_metadata",  # Most trades (57)
        "RV_017_eth_markup_macd_trend",
        "RV_052_solusdt_md_structure",  # Most trades (37) in markdown
    ]

    # Allow CLI override
    if len(sys.argv) > 1:
        plays = sys.argv[1:]

    for play in plays:
        try:
            analyze_play(play)
        except Exception as e:
            print(f"\nERROR analyzing {play}: {e}")


if __name__ == "__main__":
    main()
