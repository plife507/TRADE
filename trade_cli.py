#!/usr/bin/env python3
"""
TRADE CLI — Headless agent/script interface.

Pure subcommand dispatch. No interactive menus. All operations go through
src/tools/* via handler functions in src/cli/subcommands/.

Usage:
  python trade_cli.py validate quick|standard|full|pre-live|exchange
  python trade_cli.py backtest run --play X
  python trade_cli.py debug math-parity|snapshot-plumbing|determinism|metrics
  python trade_cli.py play run --play X --mode demo

Verbosity:
  python trade_cli.py -q ...        # Quiet (WARNING only)
  python trade_cli.py -v ...        # Verbose (signal traces)
  python trade_cli.py --debug ...   # Debug (full hash tracing)
"""

import atexit
import os
import sys

# Windows: force UTF-8 for Rich Unicode output
if sys.platform == "win32":
    import io
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    if isinstance(sys.stderr, io.TextIOWrapper):
        sys.stderr.reconfigure(encoding="utf-8")

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.utils.logging_config import configure_logging, shutdown_logging
from src.cli.utils import console

# Subcommand handlers
from src.cli.subcommands import (
    handle_backtest_run,
    handle_backtest_preflight,
    handle_backtest_indicators,
    handle_backtest_data_fix,
    handle_backtest_list,
    handle_backtest_normalize,
    handle_backtest_normalize_batch,
    handle_debug_math_parity,
    handle_debug_snapshot_plumbing,
    handle_debug_determinism,
    handle_debug_metrics,
    handle_play_run,
    handle_play_status,
    handle_play_stop,
    handle_account_balance,
    handle_account_exposure,
    handle_account_info,
    handle_account_history,
    handle_account_pnl,
    handle_account_transactions,
    handle_account_collateral,
    handle_position_list,
    handle_position_close,
    handle_position_set_tp,
    handle_position_set_sl,
    handle_position_set_tpsl,
    handle_position_trailing,
    handle_position_partial_close,
    handle_position_margin,
    handle_position_risk_limit,
    handle_position_detail,
    handle_panic,
    handle_order_buy,
    handle_order_sell,
    handle_order_list,
    handle_order_amend,
    handle_order_cancel,
    handle_order_cancel_all,
    handle_order_leverage,
    handle_order_batch,
    handle_data_sync,
    handle_data_info,
    handle_data_symbols,
    handle_data_status,
    handle_data_summary,
    handle_data_query,
    handle_data_heal,
    handle_data_vacuum,
    handle_data_delete,
    handle_market_price,
    handle_market_ohlcv,
    handle_market_funding,
    handle_market_oi,
    handle_market_orderbook,
    handle_market_instruments,
    handle_health_check,
    handle_health_connection,
    handle_health_rate_limit,
    handle_health_ws,
    handle_health_environment,
)

from src.cli.argparser import setup_argparse


def main():
    """Parse args, configure logging, dispatch to subcommand handler."""
    args = setup_argparse()

    # Logging setup
    if getattr(args, "debug", False):
        os.environ["TRADE_DEBUG"] = "1"
    configure_logging()
    atexit.register(shutdown_logging)

    # Verbosity overrides
    if getattr(args, "quiet", False):
        from src.utils.logger import suppress_for_validation
        suppress_for_validation()
    elif getattr(args, "verbose", False):
        from src.utils.debug import enable_verbose
        enable_verbose(True)
    elif getattr(args, "debug", False):
        from src.utils.debug import enable_debug, enable_verbose
        enable_debug(True)
        enable_verbose(True)

    # ===== BACKTEST =====
    if args.command == "backtest":
        if args.backtest_command == "run":
            sys.exit(handle_backtest_run(args))
        elif args.backtest_command == "preflight":
            sys.exit(handle_backtest_preflight(args))
        elif args.backtest_command == "indicators":
            sys.exit(handle_backtest_indicators(args))
        elif args.backtest_command == "data-fix":
            sys.exit(handle_backtest_data_fix(args))
        elif args.backtest_command == "list":
            sys.exit(handle_backtest_list(args))
        elif args.backtest_command == "play-normalize":
            sys.exit(handle_backtest_normalize(args))
        elif args.backtest_command == "play-normalize-batch":
            sys.exit(handle_backtest_normalize_batch(args))
        else:
            console.print("[yellow]Usage: trade_cli.py backtest {run|preflight|indicators|data-fix|list|play-normalize|play-normalize-batch} --help[/]")
            sys.exit(1)

    # ===== DEBUG =====
    elif args.command == "debug":
        if args.debug_command == "math-parity":
            sys.exit(handle_debug_math_parity(args))
        elif args.debug_command == "snapshot-plumbing":
            sys.exit(handle_debug_snapshot_plumbing(args))
        elif args.debug_command == "determinism":
            sys.exit(handle_debug_determinism(args))
        elif args.debug_command == "metrics":
            sys.exit(handle_debug_metrics(args))
        else:
            console.print("[yellow]Usage: trade_cli.py debug {math-parity|snapshot-plumbing|determinism|metrics} --help[/]")
            sys.exit(1)

    # ===== PLAY =====
    elif args.command == "play":
        if args.play_command == "run":
            sys.exit(handle_play_run(args))
        elif args.play_command == "status":
            sys.exit(handle_play_status(args))
        elif args.play_command == "stop":
            sys.exit(handle_play_stop(args))
        elif args.play_command == "watch":
            from src.cli.subcommands import handle_play_watch
            sys.exit(handle_play_watch(args))
        elif args.play_command == "logs":
            from src.cli.subcommands import handle_play_logs
            sys.exit(handle_play_logs(args))
        elif args.play_command == "pause":
            from src.cli.subcommands import handle_play_pause
            sys.exit(handle_play_pause(args))
        elif args.play_command == "resume":
            from src.cli.subcommands import handle_play_resume
            sys.exit(handle_play_resume(args))
        else:
            console.print("[yellow]Usage: trade_cli.py play {run|status|stop|watch|logs|pause|resume} --help[/]")
            sys.exit(1)

    # ===== VALIDATE =====
    elif args.command == "validate":
        from src.cli.validate import run_validation, Tier
        tier = Tier(args.tier)
        sys.exit(run_validation(
            tier=tier,
            play_id=getattr(args, "play", None),
            fail_fast=not getattr(args, "no_fail_fast", False),
            json_output=getattr(args, "json_output", False),
            max_workers=getattr(args, "workers", None),
            module_name=getattr(args, "module", None),
            play_timeout=getattr(args, "timeout", 120),
            gate_timeout=getattr(args, "gate_timeout", 300),
        ))

    # ===== SHADOW =====
    elif args.command == "shadow":
        from src.cli.subcommands.shadow import handle_shadow
        sys.exit(handle_shadow(args))

    # ===== ACCOUNT =====
    elif args.command == "account":
        if args.account_command == "balance":
            sys.exit(handle_account_balance(args))
        elif args.account_command == "exposure":
            sys.exit(handle_account_exposure(args))
        elif args.account_command == "info":
            sys.exit(handle_account_info(args))
        elif args.account_command == "history":
            sys.exit(handle_account_history(args))
        elif args.account_command == "pnl":
            sys.exit(handle_account_pnl(args))
        elif args.account_command == "transactions":
            sys.exit(handle_account_transactions(args))
        elif args.account_command == "collateral":
            sys.exit(handle_account_collateral(args))
        else:
            console.print("[yellow]Usage: trade_cli.py account {balance|exposure|info|history|pnl|transactions|collateral} --help[/]")
            sys.exit(1)

    # ===== POSITION =====
    elif args.command == "position":
        if args.position_command == "list":
            sys.exit(handle_position_list(args))
        elif args.position_command == "close":
            sys.exit(handle_position_close(args))
        elif args.position_command == "detail":
            sys.exit(handle_position_detail(args))
        elif args.position_command == "set-tp":
            sys.exit(handle_position_set_tp(args))
        elif args.position_command == "set-sl":
            sys.exit(handle_position_set_sl(args))
        elif args.position_command == "set-tpsl":
            sys.exit(handle_position_set_tpsl(args))
        elif args.position_command == "trailing":
            sys.exit(handle_position_trailing(args))
        elif args.position_command == "partial-close":
            sys.exit(handle_position_partial_close(args))
        elif args.position_command == "margin":
            sys.exit(handle_position_margin(args))
        elif args.position_command == "risk-limit":
            sys.exit(handle_position_risk_limit(args))
        else:
            console.print("[yellow]Usage: trade_cli.py position {list|close|detail|set-tp|set-sl|set-tpsl|trailing|partial-close|margin|risk-limit} --help[/]")
            sys.exit(1)

    # ===== PANIC =====
    elif args.command == "panic":
        sys.exit(handle_panic(args))

    # ===== DATA =====
    elif args.command == "data":
        if args.data_command == "sync":
            sys.exit(handle_data_sync(args))
        elif args.data_command == "info":
            sys.exit(handle_data_info(args))
        elif args.data_command == "symbols":
            sys.exit(handle_data_symbols(args))
        elif args.data_command == "status":
            sys.exit(handle_data_status(args))
        elif args.data_command == "summary":
            sys.exit(handle_data_summary(args))
        elif args.data_command == "query":
            sys.exit(handle_data_query(args))
        elif args.data_command == "heal":
            sys.exit(handle_data_heal(args))
        elif args.data_command == "vacuum":
            sys.exit(handle_data_vacuum(args))
        elif args.data_command == "delete":
            sys.exit(handle_data_delete(args))
        else:
            console.print("[yellow]Usage: trade_cli.py data {sync|info|symbols|status|summary|query|heal|vacuum|delete} --help[/]")
            sys.exit(1)

    # ===== MARKET =====
    elif args.command == "market":
        if args.market_command == "price":
            sys.exit(handle_market_price(args))
        elif args.market_command == "ohlcv":
            sys.exit(handle_market_ohlcv(args))
        elif args.market_command == "funding":
            sys.exit(handle_market_funding(args))
        elif args.market_command == "oi":
            sys.exit(handle_market_oi(args))
        elif args.market_command == "orderbook":
            sys.exit(handle_market_orderbook(args))
        elif args.market_command == "instruments":
            sys.exit(handle_market_instruments(args))
        else:
            console.print("[yellow]Usage: trade_cli.py market {price|ohlcv|funding|oi|orderbook|instruments} --help[/]")
            sys.exit(1)

    # ===== ORDER =====
    elif args.command == "order":
        if args.order_command == "buy":
            sys.exit(handle_order_buy(args))
        elif args.order_command == "sell":
            sys.exit(handle_order_sell(args))
        elif args.order_command == "list":
            sys.exit(handle_order_list(args))
        elif args.order_command == "amend":
            sys.exit(handle_order_amend(args))
        elif args.order_command == "cancel":
            sys.exit(handle_order_cancel(args))
        elif args.order_command == "cancel-all":
            sys.exit(handle_order_cancel_all(args))
        elif args.order_command == "leverage":
            sys.exit(handle_order_leverage(args))
        elif args.order_command == "batch":
            sys.exit(handle_order_batch(args))
        else:
            console.print("[yellow]Usage: trade_cli.py order {buy|sell|list|amend|cancel|cancel-all|leverage|batch} --help[/]")
            sys.exit(1)

    # ===== HEALTH =====
    elif args.command == "health":
        if args.health_command == "check":
            sys.exit(handle_health_check(args))
        elif args.health_command == "connection":
            sys.exit(handle_health_connection(args))
        elif args.health_command == "rate-limit":
            sys.exit(handle_health_rate_limit(args))
        elif args.health_command == "ws":
            sys.exit(handle_health_ws(args))
        elif args.health_command == "environment":
            sys.exit(handle_health_environment(args))
        else:
            console.print("[yellow]Usage: trade_cli.py health {check|connection|rate-limit|ws|environment} --help[/]")
            sys.exit(1)

    # ===== NO COMMAND =====
    else:
        console.print("[yellow]No command specified. Run with --help for usage.[/]")
        sys.exit(1)


if __name__ == "__main__":
    main()
