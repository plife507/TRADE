"""
Portfolio management tools — full UTA control via ToolResult.

Every function returns ToolResult and is registered in ToolRegistry.
CLI, AI agents, and future web UI all call the same functions.

Categories:
  portfolio.state — snapshot, wallet, risk, exposure
  portfolio.instruments — resolve, list
  portfolio.subs — create, fund, withdraw, balance, positions, freeze, delete, list
  portfolio.deploy — deploy, stop, status, rebalance, list_active, recall
  portfolio.collateral — tiers, toggle
"""

from __future__ import annotations

import asyncio
import threading

from ..utils.logger import get_module_logger
from .shared import ToolResult

logger = get_module_logger(__name__)


def _run_async(coro):
    """Run an async coroutine from sync context safely."""
    try:
        asyncio.get_running_loop()
        # Already in async context — run in a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        # No event loop — safe to use asyncio.run
        return asyncio.run(coro)

_pm_lock = threading.Lock()


# ── Lazy Initialization ─────────────────────────────────

def _get_portfolio_manager():
    """Lazy-init the PortfolioManager singleton. Thread-safe."""
    if not hasattr(_get_portfolio_manager, "_instance"):
        with _pm_lock:
            if not hasattr(_get_portfolio_manager, "_instance"):
                from ..config.config import get_config
                from ..exchanges.bybit_client import BybitClient
                from ..core.instrument_registry import InstrumentRegistry
                from ..core.sub_account_manager import SubAccountManager
                from ..core.portfolio_manager import PortfolioManager

                config = get_config()
                api_key, api_secret = config.bybit.get_credentials()
                client = BybitClient(api_key=api_key, api_secret=api_secret)
                registry = InstrumentRegistry.get_instance(client)
                sub_mgr = SubAccountManager(client)
                sub_mgr.load_state()
                _get_portfolio_manager._instance = PortfolioManager(client, registry, sub_mgr)
    return _get_portfolio_manager._instance


# ── Portfolio State ─────────────────────────────────────

def get_uta_snapshot_tool() -> ToolResult:
    """Get complete UTA portfolio snapshot (main + all sub-accounts)."""
    try:
        pm = _get_portfolio_manager()
        snap = pm.get_snapshot()

        if snap.main_error:
            return ToolResult(
                success=False,
                error=f"Main account query failed: {snap.main_error}",
                data=snap.to_dict(),
            )

        return ToolResult(
            success=True,
            message=f"Equity: ${snap.total_equity:,.2f} | Available: ${snap.total_available_balance:,.2f} | Subs: {len(snap.sub_accounts)} | Plays: {snap.active_plays}",
            data=snap.to_dict(),
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Portfolio snapshot failed: {e}")


def get_portfolio_wallet_tool() -> ToolResult:
    """Get all wallet coins with balances and collateral status."""
    try:
        pm = _get_portfolio_manager()
        snap = pm.get_snapshot()
        return ToolResult(
            success=True,
            message=f"{len(snap.main_coins)} coins, equity ${snap.total_equity:,.4f}",
            data={
                "coins": snap.main_coins,
                "total_equity": snap.total_equity,
                "total_wallet_balance": snap.total_wallet_balance,
                "total_available_balance": snap.total_available_balance,
            },
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Wallet query failed: {e}")


def get_portfolio_risk_tool() -> ToolResult:
    """Get account-level risk metrics."""
    try:
        pm = _get_portfolio_manager()
        snap = pm.get_snapshot()
        return ToolResult(
            success=True,
            message=f"Risk: {snap.liquidation_risk_level} | Margin: {snap.margin_utilization_pct:.1f}%",
            data={
                "margin_utilization_pct": snap.margin_utilization_pct,
                "liquidation_risk_level": snap.liquidation_risk_level,
                "total_initial_margin": snap.total_initial_margin,
                "total_maintenance_margin": snap.total_maintenance_margin,
                "total_available_balance": snap.total_available_balance,
                "account_im_rate": snap.account_im_rate,
                "account_mm_rate": snap.account_mm_rate,
            },
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Risk query failed: {e}")


def get_portfolio_exposure_tool() -> ToolResult:
    """Get exposure breakdown by category and settle coin."""
    try:
        pm = _get_portfolio_manager()
        snap = pm.get_snapshot()
        return ToolResult(
            success=True,
            message=f"Positions: {snap.total_positions} | UPL: ${snap.total_unrealized_pnl:,.2f}",
            data={
                "by_settle_coin": snap.exposure_by_settle_coin,
                "by_category": snap.position_count_by_category,
                "total_positions": snap.total_positions,
                "total_unrealized_pnl": snap.total_unrealized_pnl,
                "total_deployed_equity": snap.total_deployed_equity,
            },
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Exposure query failed: {e}")


# ── Instrument Discovery ────────────────────────────────

def resolve_instrument_tool(symbol: str) -> ToolResult:
    """Resolve a symbol to its full instrument specification."""
    try:
        pm = _get_portfolio_manager()
        spec = pm.instrument_registry.resolve(symbol)
        return ToolResult(
            success=True,
            message=f"{symbol}: {spec.category}/{spec.settle_coin} ({spec.contract_type})",
            data=spec.to_dict(),
            symbol=symbol,
            source="cache",
        )
    except KeyError:
        return ToolResult(success=False, error=f"Symbol '{symbol}' not found in instrument registry")
    except Exception as e:
        return ToolResult(success=False, error=f"Resolve failed: {e}")


def list_instruments_tool(category: str | None = None, settle_coin: str | None = None) -> ToolResult:
    """List available instruments with optional filters."""
    try:
        pm = _get_portfolio_manager()
        specs = pm.instrument_registry.get_all_specs(category=category, settle_coin=settle_coin)
        instruments = [s.to_dict() for s in specs]
        return ToolResult(
            success=True,
            message=f"{len(instruments)} instruments" + (f" (category={category})" if category else "") + (f" (settle={settle_coin})" if settle_coin else ""),
            data={"instruments": instruments, "count": len(instruments)},
            source="cache",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"List instruments failed: {e}")


# ── Sub-Account Management ──────────────────────────────

def list_sub_accounts_tool() -> ToolResult:
    """List all managed sub-accounts."""
    try:
        pm = _get_portfolio_manager()
        subs = pm.sub_account_manager.list()
        return ToolResult(
            success=True,
            message=f"{len(subs)} sub-account(s)",
            data={"sub_accounts": [s.to_safe_dict() for s in subs], "count": len(subs)},
            source="local",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"List sub-accounts failed: {e}")


def create_sub_account_tool(username: str) -> ToolResult:
    """Create a new sub-account with API keys."""
    try:
        pm = _get_portfolio_manager()
        info = pm.sub_account_manager.create(username)
        return ToolResult(
            success=True,
            message=f"Created sub-account uid={info.uid}, username={info.username}",
            data=info.to_safe_dict(),
            source="rest_api",
        )
    except ValueError as e:
        return ToolResult(success=False, error=f"Invalid username: {e}")
    except Exception as e:
        return ToolResult(success=False, error=f"Create sub-account failed: {e}")


def fund_sub_account_tool(uid: int, coin: str, amount: float) -> ToolResult:
    """Transfer funds from main account to sub-account (internal transfer, stays on Bybit)."""
    try:
        pm = _get_portfolio_manager()
        transfer_id = pm.sub_account_manager.fund(uid, coin, amount)
        return ToolResult(
            success=True,
            message=f"Transferred {amount} {coin} to sub uid={uid}",
            data={"transfer_id": transfer_id, "uid": uid, "coin": coin, "amount": amount},
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Fund sub-account failed: {e}")


def withdraw_sub_account_tool(uid: int, coin: str, amount: float) -> ToolResult:
    """Transfer funds from sub-account back to main (internal transfer, stays on Bybit)."""
    try:
        pm = _get_portfolio_manager()
        transfer_id = pm.sub_account_manager.withdraw(uid, coin, amount)
        return ToolResult(
            success=True,
            message=f"Withdrew {amount} {coin} from sub uid={uid}",
            data={"transfer_id": transfer_id, "uid": uid, "coin": coin, "amount": amount},
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Withdraw from sub-account failed: {e}")


def get_sub_account_balance_tool(uid: int) -> ToolResult:
    """Get sub-account wallet balance."""
    try:
        pm = _get_portfolio_manager()
        balances = {}
        for coin in ("USDT", "USDC"):
            bal = pm.sub_account_manager.get_balance(uid, coin)
            if bal.get("wallet_balance", 0) > 0:
                balances[coin] = bal
        return ToolResult(
            success=True,
            message=f"Sub uid={uid} balance queried",
            data={"uid": uid, "balances": balances},
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Sub-account balance query failed: {e}")


def get_sub_account_positions_tool(uid: int) -> ToolResult:
    """Get sub-account open positions."""
    try:
        pm = _get_portfolio_manager()
        positions = pm.sub_account_manager.get_positions(uid)
        return ToolResult(
            success=True,
            message=f"Sub uid={uid}: {len(positions)} position(s)",
            data={"uid": uid, "positions": positions, "count": len(positions)},
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Sub-account positions query failed: {e}")


def freeze_sub_account_tool(uid: int) -> ToolResult:
    """Freeze a sub-account (stop trading)."""
    try:
        pm = _get_portfolio_manager()
        pm.sub_account_manager.freeze(uid)
        return ToolResult(
            success=True,
            message=f"Sub uid={uid} frozen",
            data={"uid": uid, "status": "frozen"},
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Freeze sub-account failed: {e}")


def delete_sub_account_tool(uid: int) -> ToolResult:
    """Delete a sub-account (must have zero balance)."""
    try:
        pm = _get_portfolio_manager()
        pm.sub_account_manager.delete(uid)
        return ToolResult(
            success=True,
            message=f"Sub uid={uid} deleted",
            data={"uid": uid, "status": "deleted"},
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Delete sub-account failed: {e}")


# ── Play Deployment ─────────────────────────────────────

def _get_deployer():
    """Lazy-init the PlayDeployer."""
    if not hasattr(_get_deployer, "_instance"):
        with _pm_lock:
            if not hasattr(_get_deployer, "_instance"):
                from ..core.play_deployer import PlayDeployer
                _get_deployer._instance = PlayDeployer(_get_portfolio_manager())
    return _get_deployer._instance


def deploy_play_tool(play_id: str, symbol: str, capital: float, confirm: bool = False) -> ToolResult:
    """Deploy a proven play into a sub-account."""
    if not confirm:
        return ToolResult(
            success=False,
            error="Deployment requires confirm=True. This creates a sub-account and transfers real funds.",
        )
    try:
        deployer = _get_deployer()
        uid = _run_async(deployer.deploy(play_id, capital))
        return ToolResult(
            success=True,
            message=f"Play {play_id} deployed to sub uid={uid}",
            data={"uid": uid, "play_id": play_id, "symbol": symbol, "capital": capital},
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Deploy failed: {e}")


def stop_play_tool(uid: int, close_positions: bool = True, confirm: bool = False) -> ToolResult:
    """Stop a deployed play."""
    if not confirm:
        return ToolResult(
            success=False,
            error="Stop play requires confirm=True. This stops a live play and may close positions.",
        )
    try:
        deployer = _get_deployer()
        _run_async(deployer.stop(uid, close_positions))
        return ToolResult(
            success=True,
            message=f"Play stopped on sub uid={uid}",
            data={"uid": uid, "close_positions": close_positions},
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Stop failed: {e}")


def get_play_status_tool(uid: int) -> ToolResult:
    """Get status of a deployed play."""
    try:
        deployer = _get_deployer()
        status = deployer.get_status(uid)
        return ToolResult(
            success=True,
            message=f"Play {status['play_id']} on sub uid={uid}: {status['status']}",
            data=status,
            source="local",
        )
    except KeyError:
        return ToolResult(success=False, error=f"No deployment found for sub uid={uid}")
    except Exception as e:
        return ToolResult(success=False, error=f"Status query failed: {e}")


def rebalance_play_tool(uid: int, new_capital: float, confirm: bool = False) -> ToolResult:
    """Add/remove capital from a deployed play."""
    if not confirm:
        return ToolResult(
            success=False,
            error="Rebalance requires confirm=True. This transfers real funds between accounts.",
        )
    try:
        pm = _get_portfolio_manager()
        deployer = _get_deployer()
        status = deployer.get_status(uid)
        old_capital = status.get("capital", 0)
        diff = new_capital - old_capital

        # Use the sub's actual funded coin, not hardcoded USDT
        sub_info = pm.sub_account_manager.get(uid)
        coin = sub_info.funded_coin if sub_info.funded_coin else "USDT"
        if not sub_info.funded_coin:
            logger.warning(
                "Sub uid=%d has no funded_coin recorded, falling back to USDT", uid
            )

        if diff > 0:
            pm.sub_account_manager.fund(uid, coin, diff)
        elif diff < 0:
            pm.sub_account_manager.withdraw(uid, coin, abs(diff))
        # Update tracked capital on the deployment
        deployment = deployer._deployments.get(uid)
        if deployment:
            deployment.capital = new_capital
        return ToolResult(
            success=True,
            message=f"Rebalanced sub uid={uid}: ${old_capital:.2f} → ${new_capital:.2f} ({coin})",
            data={"uid": uid, "old_capital": old_capital, "new_capital": new_capital, "transfer": diff, "coin": coin},
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Rebalance failed: {e}")


def list_active_plays_tool() -> ToolResult:
    """List all running plays."""
    try:
        pm = _get_portfolio_manager()
        subs = pm.sub_account_manager.list()
        active = [s.to_safe_dict() for s in subs if s.play_id]
        return ToolResult(
            success=True,
            message=f"{len(active)} active play(s)",
            data={"plays": active, "count": len(active)},
            source="local",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"List active plays failed: {e}")


# ── Emergency ───────────────────────────────────────────

def recall_all_tool(confirm: bool = False) -> ToolResult:
    """Emergency: stop all plays, close all positions, sweep funds to main."""
    if not confirm:
        return ToolResult(
            success=False,
            error="recall_all requires confirm=True. This closes ALL positions and sweeps ALL funds.",
        )
    try:
        pm = _get_portfolio_manager()
        result = pm.recall_all()
        return ToolResult(
            success=True,
            message=f"Recalled: {result['plays_stopped']} plays, {result['positions_closed']} positions, ${result['funds_recalled']:,.2f}",
            data=result,
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Recall all failed: {e}")


# ── Collateral ──────────────────────────────────────────

def get_collateral_tiers_tool(currency: str | None = None) -> ToolResult:
    """Get tiered collateral ratios."""
    try:
        pm = _get_portfolio_manager()
        tiers = pm._main_client.get_collateral_info(
            currency=currency.upper() if currency else None,
        )
        return ToolResult(
            success=True,
            message=f"{len(tiers)} collateral tier(s)",
            data={"tiers": tiers, "count": len(tiers)},
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Collateral tiers query failed: {e}")


def toggle_collateral_tool(coin: str, enabled: bool) -> ToolResult:
    """Enable/disable a coin as collateral."""
    try:
        pm = _get_portfolio_manager()
        switch = "ON" if enabled else "OFF"
        pm._main_client.set_collateral_coin(coin=coin.upper(), switch=switch)
        return ToolResult(
            success=True,
            message=f"Collateral for {coin.upper()}: {switch}",
            data={"coin": coin.upper(), "collateral_switch": enabled},
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"Toggle collateral failed: {e}")
