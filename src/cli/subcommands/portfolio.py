"""Portfolio subcommand handlers for TRADE CLI."""

from __future__ import annotations

from src.cli.subcommands._helpers import _json_result, _print_result


def handle_portfolio(args) -> int:
    """Route portfolio subcommands."""
    cmd = getattr(args, "portfolio_command", None)
    if not cmd:
        print("Usage: trade_cli.py portfolio <command>")
        print("Commands: snapshot, wallet, risk, exposure, instruments, resolve,")
        print("          subs, deploy, stop, status, plays, recall-all,")
        print("          collateral, toggle-collateral")
        return 1

    use_json = getattr(args, "json_output", False)
    handler = _HANDLERS.get(cmd)
    if not handler:
        print(f"Unknown portfolio command: {cmd}")
        return 1

    result = handler(args)
    return _json_result(result) if use_json else _print_result(result)


# ── Handler Functions ───────────────────────────────────

def _handle_snapshot(args):
    from src.tools.portfolio_tools import get_uta_snapshot_tool
    return get_uta_snapshot_tool()


def _handle_wallet(args):
    from src.tools.portfolio_tools import get_portfolio_wallet_tool
    return get_portfolio_wallet_tool()


def _handle_risk(args):
    from src.tools.portfolio_tools import get_portfolio_risk_tool
    return get_portfolio_risk_tool()


def _handle_exposure(args):
    from src.tools.portfolio_tools import get_portfolio_exposure_tool
    return get_portfolio_exposure_tool()


def _handle_instruments(args):
    from src.tools.portfolio_tools import list_instruments_tool
    return list_instruments_tool(
        category=getattr(args, "category", None),
        settle_coin=getattr(args, "settle_coin", None),
    )


def _handle_resolve(args):
    from src.tools.portfolio_tools import resolve_instrument_tool
    return resolve_instrument_tool(symbol=args.symbol)


def _handle_subs(args):
    """Route sub-account subcommands."""
    sub_cmd = getattr(args, "subs_command", None)
    if not sub_cmd:
        from src.tools.portfolio_tools import list_sub_accounts_tool
        return list_sub_accounts_tool()

    sub_handler = _SUB_HANDLERS.get(sub_cmd)
    if sub_handler:
        return sub_handler(args)

    from src.tools.shared import ToolResult
    return ToolResult(success=False, error=f"Unknown subs command: {sub_cmd}")


def _handle_subs_list(args):
    from src.tools.portfolio_tools import list_sub_accounts_tool
    return list_sub_accounts_tool()


def _handle_subs_create(args):
    from src.tools.portfolio_tools import create_sub_account_tool
    return create_sub_account_tool(username=args.username)


def _handle_subs_fund(args):
    from src.tools.portfolio_tools import fund_sub_account_tool
    return fund_sub_account_tool(uid=args.uid, coin=args.coin, amount=args.amount)


def _handle_subs_withdraw(args):
    from src.tools.portfolio_tools import withdraw_sub_account_tool
    return withdraw_sub_account_tool(uid=args.uid, coin=args.coin, amount=args.amount)


def _handle_subs_balance(args):
    from src.tools.portfolio_tools import get_sub_account_balance_tool
    return get_sub_account_balance_tool(uid=args.uid)


def _handle_subs_positions(args):
    from src.tools.portfolio_tools import get_sub_account_positions_tool
    return get_sub_account_positions_tool(uid=args.uid)


def _handle_subs_freeze(args):
    from src.tools.portfolio_tools import freeze_sub_account_tool
    return freeze_sub_account_tool(uid=args.uid)


def _handle_subs_delete(args):
    from src.tools.portfolio_tools import delete_sub_account_tool
    return delete_sub_account_tool(uid=args.uid)


def _handle_deploy(args):
    from src.tools.portfolio_tools import deploy_play_tool
    return deploy_play_tool(
        play_id=args.play,
        symbol=args.symbol,
        capital=args.capital,
        confirm=getattr(args, "confirm", False),
    )


def _handle_stop(args):
    from src.tools.portfolio_tools import stop_play_tool
    return stop_play_tool(
        uid=args.uid,
        close_positions=getattr(args, "close_positions", True),
    )


def _handle_status(args):
    from src.tools.portfolio_tools import get_play_status_tool
    return get_play_status_tool(uid=args.uid)


def _handle_rebalance(args):
    from src.tools.portfolio_tools import rebalance_play_tool
    return rebalance_play_tool(uid=args.uid, new_capital=args.capital)


def _handle_plays(args):
    from src.tools.portfolio_tools import list_active_plays_tool
    return list_active_plays_tool()


def _handle_recall_all(args):
    from src.tools.portfolio_tools import recall_all_tool
    return recall_all_tool(confirm=getattr(args, "confirm", False))


def _handle_collateral(args):
    from src.tools.portfolio_tools import get_collateral_tiers_tool
    return get_collateral_tiers_tool(currency=getattr(args, "currency", None))


def _handle_toggle_collateral(args):
    from src.tools.portfolio_tools import toggle_collateral_tool
    return toggle_collateral_tool(coin=args.coin, enabled=getattr(args, "enable", False))


# ── Handler Maps ────────────────────────────────────────

_HANDLERS = {
    "snapshot": _handle_snapshot,
    "wallet": _handle_wallet,
    "risk": _handle_risk,
    "exposure": _handle_exposure,
    "instruments": _handle_instruments,
    "resolve": _handle_resolve,
    "subs": _handle_subs,
    "deploy": _handle_deploy,
    "stop": _handle_stop,
    "status": _handle_status,
    "plays": _handle_plays,
    "rebalance": _handle_rebalance,
    "recall-all": _handle_recall_all,
    "collateral": _handle_collateral,
    "toggle-collateral": _handle_toggle_collateral,
}

_SUB_HANDLERS = {
    "list": _handle_subs_list,
    "create": _handle_subs_create,
    "fund": _handle_subs_fund,
    "withdraw": _handle_subs_withdraw,
    "balance": _handle_subs_balance,
    "positions": _handle_subs_positions,
    "freeze": _handle_subs_freeze,
    "delete": _handle_subs_delete,
}
