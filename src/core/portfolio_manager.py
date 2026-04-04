"""
Portfolio Manager — THE one manager for the entire Bybit UTA.

Aggregates main account (treasury) + all sub-accounts into a single
coherent view. No fallbacks — this is the single source of truth.

Sub-accounts are queried in parallel via ThreadPoolExecutor, each with
its own BybitClient and independent rate limits (10/s per UID).

Usage:
    from src.core.portfolio_manager import PortfolioManager

    pm = PortfolioManager(main_client, instrument_registry, sub_account_manager)

    snapshot = pm.get_snapshot()
    print(f"Total equity: ${snapshot.total_equity:.2f}")
    print(f"Active plays: {snapshot.active_plays}")
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..config.constants import LINEAR_SETTLE_COINS
from ..utils.datetime_utils import utc_now
from ..utils.logger import get_module_logger

if TYPE_CHECKING:
    from ..exchanges.bybit_client import BybitClient
    from .instrument_registry import InstrumentRegistry
    from .sub_account_manager import SubAccountManager, SubAccountInfo

logger = get_module_logger(__name__)


@dataclass
class SubAccountSnapshot:
    """Point-in-time state of a single sub-account."""

    uid: int
    username: str
    play_id: str | None
    status: str
    equity: float = 0.0
    wallet_balance: float = 0.0
    available_balance: float = 0.0
    positions: list[dict] = field(default_factory=list)
    position_count: int = 0
    unrealized_pnl: float = 0.0
    error: str | None = None  # Set if query failed

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "username": self.username,
            "play_id": self.play_id,
            "status": self.status,
            "equity": self.equity,
            "wallet_balance": self.wallet_balance,
            "available_balance": self.available_balance,
            "position_count": self.position_count,
            "unrealized_pnl": self.unrealized_pnl,
            "positions": self.positions,
            "error": self.error,
        }


@dataclass
class PortfolioSnapshot:
    """Complete point-in-time UTA portfolio state."""

    timestamp: datetime

    # Main account (treasury)
    main_equity: float = 0.0
    main_wallet_balance: float = 0.0
    main_available_balance: float = 0.0
    main_coins: list[dict] = field(default_factory=list)

    # Account-wide UTA metrics
    total_equity: float = 0.0
    total_wallet_balance: float = 0.0
    total_margin_balance: float = 0.0
    total_available_balance: float = 0.0
    total_initial_margin: float = 0.0
    total_maintenance_margin: float = 0.0
    account_im_rate: float = 0.0
    account_mm_rate: float = 0.0
    margin_utilization_pct: float = 0.0
    liquidation_risk_level: str = "LOW"

    # Sub-accounts
    sub_accounts: list[SubAccountSnapshot] = field(default_factory=list)

    # Aggregates
    total_deployed_equity: float = 0.0
    total_undeployed: float = 0.0
    active_plays: int = 0
    total_positions: int = 0
    total_unrealized_pnl: float = 0.0

    # Exposure breakdown
    exposure_by_settle_coin: dict[str, float] = field(default_factory=dict)
    position_count_by_category: dict[str, int] = field(default_factory=dict)

    source: str = "rest"
    main_error: str | None = None  # Set if main account query failed (fail-closed)

    def __post_init__(self) -> None:
        assert self.timestamp.tzinfo is None, (
            f"PortfolioSnapshot.timestamp must be UTC-naive, got tzinfo={self.timestamp.tzinfo}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "main": {
                "equity": self.main_equity,
                "wallet_balance": self.main_wallet_balance,
                "available_balance": self.main_available_balance,
                "coins": self.main_coins,
            },
            "account_metrics": {
                "total_equity": self.total_equity,
                "total_wallet_balance": self.total_wallet_balance,
                "total_margin_balance": self.total_margin_balance,
                "total_available_balance": self.total_available_balance,
                "total_initial_margin": self.total_initial_margin,
                "total_maintenance_margin": self.total_maintenance_margin,
                "account_im_rate": self.account_im_rate,
                "account_mm_rate": self.account_mm_rate,
                "margin_utilization_pct": self.margin_utilization_pct,
                "liquidation_risk_level": self.liquidation_risk_level,
            },
            "sub_accounts": [s.to_dict() for s in self.sub_accounts],
            "aggregates": {
                "total_deployed_equity": self.total_deployed_equity,
                "total_undeployed": self.total_undeployed,
                "active_plays": self.active_plays,
                "total_positions": self.total_positions,
                "total_unrealized_pnl": self.total_unrealized_pnl,
            },
            "exposure": {
                "by_settle_coin": self.exposure_by_settle_coin,
                "by_category": self.position_count_by_category,
            },
            "source": self.source,
            "main_error": self.main_error,
        }


class PortfolioManager:
    """
    THE one manager for the entire Bybit UTA.

    Owns:
    - Main account BybitClient (treasury operations, balance queries)
    - InstrumentRegistry (symbol resolution)
    - SubAccountManager (sub-account lifecycle)

    Provides:
    - get_snapshot(): complete portfolio state, parallel sub queries
    - get_margin_headroom(): available capital for new deployments
    - can_deploy_play(): pre-flight check before deployment
    """

    def __init__(
        self,
        main_client: BybitClient,
        instrument_registry: InstrumentRegistry,
        sub_account_manager: SubAccountManager,
    ):
        self._main_client = main_client
        self._registry = instrument_registry
        self._sub_mgr = sub_account_manager

    @property
    def instrument_registry(self) -> InstrumentRegistry:
        return self._registry

    @property
    def sub_account_manager(self) -> SubAccountManager:
        return self._sub_mgr

    # ── Portfolio Snapshot ──────────────────────────────────

    def get_snapshot(self) -> PortfolioSnapshot:
        """
        Build complete portfolio state.

        Queries main account balance + all sub-account balances/positions
        in parallel. Each sub has its own BybitClient with independent
        rate limits, so parallel queries don't interfere.

        Returns:
            PortfolioSnapshot with main + all subs + aggregates
        """
        snap = PortfolioSnapshot(timestamp=utc_now())

        # 1. Main account balance (UTA-wide)
        self._fill_main_account(snap)

        # 2. Sub-account snapshots (parallel)
        subs = self._sub_mgr.list()
        if subs:
            snap.sub_accounts = self._query_subs_parallel(subs)

        # 3. Compute aggregates
        self._compute_aggregates(snap)

        return snap

    def _fill_main_account(self, snap: PortfolioSnapshot) -> None:
        """Populate main account fields from REST."""
        try:
            balance = self._main_client.get_balance()

            # Account-level totals
            snap.total_equity = balance.get("totalEquity", 0)
            snap.total_wallet_balance = balance.get("totalWalletBalance", 0)
            snap.total_margin_balance = balance.get("totalMarginBalance", 0)
            snap.total_available_balance = balance.get("totalAvailableBalance", 0)
            snap.total_initial_margin = balance.get("totalInitialMargin", 0)
            snap.total_maintenance_margin = balance.get("totalMaintenanceMargin", 0)
            snap.account_im_rate = balance.get("accountIMRate", 0)
            snap.account_mm_rate = balance.get("accountMMRate", 0)

            # Parse floats
            for attr in (
                "total_equity", "total_wallet_balance", "total_margin_balance",
                "total_available_balance", "total_initial_margin",
                "total_maintenance_margin", "account_im_rate", "account_mm_rate",
            ):
                val = getattr(snap, attr)
                if isinstance(val, str):
                    setattr(snap, attr, float(val) if val else 0.0)

            # Margin utilization
            if snap.total_margin_balance > 0:
                snap.margin_utilization_pct = (snap.total_initial_margin / snap.total_margin_balance) * 100
            if snap.account_mm_rate > 0.9:
                snap.liquidation_risk_level = "CRITICAL"
            elif snap.account_mm_rate > 0.7:
                snap.liquidation_risk_level = "HIGH"
            elif snap.account_mm_rate > 0.5:
                snap.liquidation_risk_level = "MEDIUM"

            # Main account = treasury view
            snap.main_equity = snap.total_equity
            snap.main_wallet_balance = snap.total_wallet_balance
            snap.main_available_balance = snap.total_available_balance

            # Per-coin breakdown
            coins = balance.get("coin", [])
            for coin_data in coins:
                equity = float(coin_data.get("equity", 0) or 0)
                if equity > 0 or float(coin_data.get("walletBalance", 0) or 0) > 0:
                    snap.main_coins.append({
                        "coin": coin_data.get("coin", ""),
                        "equity": equity,
                        "wallet_balance": float(coin_data.get("walletBalance", 0) or 0),
                        "usd_value": float(coin_data.get("usdValue", 0) or 0),
                        "borrow_amount": float(coin_data.get("borrowAmount", 0) or 0),
                        "collateral_switch": bool(coin_data.get("collateralSwitch", True)),
                        "margin_collateral": bool(coin_data.get("marginCollateral", True)),
                    })

        except Exception as exc:
            snap.main_error = str(exc)
            logger.exception("Failed to query main account balance — snapshot is fail-closed")

    def _query_subs_parallel(self, subs: list[SubAccountInfo]) -> list[SubAccountSnapshot]:
        """Query all sub-account balances and positions in parallel."""
        results: list[SubAccountSnapshot] = []

        with ThreadPoolExecutor(max_workers=min(len(subs), 8)) as pool:
            futures = {
                pool.submit(self._query_single_sub, info): info
                for info in subs
            }

            try:
                for future in as_completed(futures, timeout=30.0):
                    info = futures[future]
                    try:
                        snap = future.result(timeout=5.0)
                        results.append(snap)
                    except Exception as exc:
                        logger.warning("Sub uid=%d query failed: %s", info.uid, exc)
                        results.append(SubAccountSnapshot(
                            uid=info.uid,
                            username=info.username,
                            play_id=info.play_id,
                            status=info.status,
                            error=str(exc),
                        ))
            except TimeoutError:
                # Some subs didn't respond in 30s — mark them as errors
                for future, info in futures.items():
                    if not future.done():
                        future.cancel()
                        results.append(SubAccountSnapshot(
                            uid=info.uid,
                            username=info.username,
                            play_id=info.play_id,
                            status=info.status,
                            error="Query timed out (30s)",
                        ))
                logger.warning("Sub-account queries timed out — %d subs incomplete", sum(1 for f in futures if not f.done()))

        return sorted(results, key=lambda s: s.uid)

    def _query_single_sub(self, info: SubAccountInfo) -> SubAccountSnapshot:
        """Query a single sub-account's balance and positions."""
        snap = SubAccountSnapshot(
            uid=info.uid,
            username=info.username,
            play_id=info.play_id,
            status=info.status,
        )

        # Balance via main account API key (sequential — shared rate limiter on main client)
        try:
            for coin in ("USDT", "USDC"):
                bal = self._sub_mgr.get_balance(info.uid, coin)
                snap.wallet_balance += bal.get("wallet_balance", 0)
        except Exception as exc:
            snap.error = f"Balance query failed: {exc}"
            return snap

        # Positions via sub's own client (independent rate limiter)
        try:
            positions = self._sub_mgr.get_positions(info.uid)
            snap.positions = positions
            snap.position_count = len(positions)
            total_position_margin = 0.0
            for pos in positions:
                snap.unrealized_pnl += float(pos.get("unrealisedPnl", 0) or 0)
                total_position_margin += float(pos.get("positionIM", 0) or 0)
            snap.equity = snap.wallet_balance + snap.unrealized_pnl
            snap.available_balance = max(0.0, snap.wallet_balance - total_position_margin)
        except Exception as exc:
            snap.error = f"Position query failed: {exc}"

        return snap

    def _compute_aggregates(self, snap: PortfolioSnapshot) -> None:
        """Compute aggregate metrics from sub-account snapshots."""
        deployed_equity = 0.0
        total_positions = 0
        total_upl = 0.0
        active_plays = 0
        exposure_by_settle: dict[str, float] = {}
        count_by_category: dict[str, int] = {}

        for sub in snap.sub_accounts:
            deployed_equity += sub.equity
            total_positions += sub.position_count
            total_upl += sub.unrealized_pnl
            if sub.play_id and sub.status == "active":
                active_plays += 1

            # Aggregate exposure from positions
            for pos in sub.positions:
                pos_value = float(pos.get("positionValue", 0) or 0)
                settle = pos.get("_settle_coin", "USDT")
                category = pos.get("_category", "linear")
                exposure_by_settle[settle] = exposure_by_settle.get(settle, 0) + pos_value
                count_by_category[category] = count_by_category.get(category, 0) + 1

        snap.total_deployed_equity = deployed_equity
        # total_available_balance already excludes funds transferred to subs
        # (Bybit UTA: sub transfers reduce main available balance)
        snap.total_undeployed = snap.total_available_balance
        snap.active_plays = active_plays
        snap.total_positions = total_positions
        snap.total_unrealized_pnl = total_upl
        snap.exposure_by_settle_coin = exposure_by_settle
        snap.position_count_by_category = count_by_category

    # ── Pre-Flight Checks ──────────────────────────────────

    def get_margin_headroom(self) -> float:
        """Available capital for new deployments (main account available balance)."""
        try:
            balance = self._main_client.get_balance()
            return float(balance.get("totalAvailableBalance", 0) or 0)
        except Exception:
            logger.exception("Failed to get margin headroom")
            return 0.0

    def can_deploy_play(self, symbol: str, capital_required: float) -> tuple[bool, str]:
        """
        Pre-flight check: can this play be deployed?

        Checks:
        1. Symbol exists in InstrumentRegistry
        2. Main account has sufficient available balance
        3. Symbol is in "Trading" status

        Returns:
            (can_deploy, reason)
        """
        # Check symbol exists and is tradeable
        try:
            spec = self._registry.resolve(symbol)
        except KeyError:
            return False, f"Symbol '{symbol}' not found in instrument registry"

        if spec.status != "Trading":
            return False, f"Symbol '{symbol}' status is '{spec.status}', not 'Trading'"

        # Check capital
        headroom = self.get_margin_headroom()
        if capital_required > headroom:
            return False, (
                f"Insufficient margin: need ${capital_required:.2f}, "
                f"available ${headroom:.2f}"
            )

        return True, f"OK: {symbol} ({spec.category}/{spec.settle_coin}), ${capital_required:.2f} of ${headroom:.2f} available"

    # ── Recall All (Emergency) ─────────────────────────────

    def recall_all(self) -> dict[str, Any]:
        """
        Emergency: stop all plays, close all sub-account positions, sweep funds to main.

        Returns summary of actions taken.
        """
        results: dict[str, Any] = {
            "plays_stopped": 0,
            "positions_closed": 0,
            "funds_recalled": 0.0,
            "errors": [],
        }

        subs = self._sub_mgr.list()
        for info in subs:
            try:
                # Close all positions via sub's client
                client = self._sub_mgr.get_client(info.uid)

                # Cancel all orders — linear (all settle coins) + inverse
                for settle_coin in LINEAR_SETTLE_COINS:
                    try:
                        client.cancel_all_orders(settle_coin=settle_coin, category="linear")
                    except Exception:
                        pass
                # Cancel inverse orders — query positions first to find settle coins
                try:
                    inv_positions = self._sub_mgr.get_positions(info.uid)
                    inv_settle_coins = {p.get("_settle_coin", "") for p in inv_positions if p.get("_category") == "inverse"}
                    for sc in inv_settle_coins:
                        if sc:
                            try:
                                client.cancel_all_orders(settle_coin=sc, category="inverse")
                            except Exception:
                                pass
                except Exception:
                    pass

                # Close positions (get_positions already queries linear + inverse)
                positions = self._sub_mgr.get_positions(info.uid)
                for pos in positions:
                    size = float(pos.get("size", 0))
                    if size <= 0:
                        continue
                    side = "Sell" if pos.get("side") == "Buy" else "Buy"
                    category = pos.get("_category", "linear")
                    try:
                        client.create_order(
                            symbol=pos["symbol"],
                            side=side,
                            order_type="Market",
                            qty=size,
                            reduce_only=True,
                            category=category,
                        )
                        results["positions_closed"] += 1
                    except Exception as exc:
                        results["errors"].append(f"Close {pos['symbol']} sub={info.uid}: {exc}")

                # Withdraw all coins (USDT, USDC, and any inverse settle coins like BTC/ETH)
                withdraw_coins = ["USDT", "USDC"]
                for pos in positions:
                    sc = pos.get("_settle_coin", "")
                    if sc and sc not in withdraw_coins:
                        withdraw_coins.append(sc)
                for coin in withdraw_coins:
                    try:
                        bal = self._sub_mgr.get_balance(info.uid, coin)
                        amount = bal.get("transfer_balance", 0)
                        if amount > 0:
                            self._sub_mgr.withdraw(info.uid, coin, amount)
                            results["funds_recalled"] += amount
                    except Exception:
                        pass

                if info.play_id:
                    results["plays_stopped"] += 1

            except Exception as exc:
                results["errors"].append(f"Recall sub={info.uid}: {exc}")

        logger.warning(
            "RECALL ALL complete: %d plays stopped, %d positions closed, $%.2f recalled, %d errors",
            results["plays_stopped"], results["positions_closed"],
            results["funds_recalled"], len(results["errors"]),
        )
        return results
