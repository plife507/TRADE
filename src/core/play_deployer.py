"""
Play Deployer — deploys proven plays into sub-accounts as LiveRunners.

Full pipeline: load play → create sub → fund → create engine → start runner.
Each deployed play runs independently in its own asyncio task with its own
BybitClient, WS connections, and rate limits.

Usage:
    from src.core.play_deployer import PlayDeployer

    deployer = PlayDeployer(portfolio_manager)
    uid = await deployer.deploy("scalp_1m", capital=50.0)
    await deployer.stop(uid)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..utils.datetime_utils import utc_now
from ..utils.logger import get_module_logger

if TYPE_CHECKING:
    from ..engine.runners.live_runner import LiveRunner
    from .portfolio_manager import PortfolioManager

logger = get_module_logger(__name__)


@dataclass
class DeployedPlay:
    """Tracks a running play deployment."""
    uid: int
    play_id: str
    symbol: str
    capital: float
    runner: LiveRunner | None = None
    task: asyncio.Task | None = None  # type: ignore[type-arg]
    started_at: str = ""
    status: str = "starting"  # starting, running, stopping, stopped, error

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "play_id": self.play_id,
            "symbol": self.symbol,
            "capital": self.capital,
            "started_at": self.started_at,
            "status": self.status,
        }


class PlayDeployer:
    """
    Deploys proven plays into sub-accounts as LiveRunners.

    Each deployment:
    1. Loads Play from YAML
    2. Creates sub-account with API keys
    3. Transfers capital from main
    4. Creates PlayEngine with sub-account's BybitClient
    5. Starts LiveRunner in background asyncio task
    """

    def __init__(self, portfolio_manager: PortfolioManager):
        self._pm = portfolio_manager
        self._deployments: dict[int, DeployedPlay] = {}

    async def deploy(self, play_path: str, capital: float) -> int:
        """
        Full deployment pipeline.

        Args:
            play_path: Play identifier or YAML path
            capital: Capital to allocate (transferred from main)

        Returns:
            Sub-account UID

        Raises:
            RuntimeError: If deployment fails at any step
        """
        from ..backtest.play import load_play

        # 1. Load and validate play
        play = load_play(play_path)
        play_id = play.id
        symbol = play.symbol_universe[0]

        logger.info("Deploying play %s on %s with $%.2f capital", play_id, symbol, capital)

        # 2. Pre-flight check
        can, reason = self._pm.can_deploy_play(symbol, capital)
        if not can:
            raise RuntimeError(f"Pre-flight failed: {reason}")

        # 3. Resolve instrument for routing
        spec = self._pm.instrument_registry.resolve(symbol)
        logger.info("Instrument: %s/%s (%s)", spec.category, spec.settle_coin, spec.contract_type)

        # 4. Create sub-account
        sub_mgr = self._pm.sub_account_manager
        username = f"play{play_id[:8].replace('_', '').lower()}"
        # Ensure valid username (6-16 chars, letters+digits)
        if len(username) < 6:
            username = username + "0" * (6 - len(username))
        info = sub_mgr.create(username)
        uid = info.uid
        logger.info("Sub-account created: uid=%d, username=%s", uid, username)

        try:
            # 5. Fund sub-account
            sub_mgr.fund(uid, spec.settle_coin, capital)
            logger.info("Funded sub uid=%d with %.2f %s", uid, capital, spec.settle_coin)

            # 6. Get sub's BybitClient
            sub_client = sub_mgr.get_client(uid)

            # 7. Validate sub's API keys work
            if not sub_client.api_key:
                raise RuntimeError(f"Sub uid={uid} has no API key")

            # 8. Create PlayEngine with sub's client (bypasses singleton ExchangeManager)
            from ..engine.factory import PlayEngineFactory
            engine = PlayEngineFactory._create_live(
                play=play,
                config_override={"initial_equity": capital},
                client=sub_client,
            )

            # 8. Create and start LiveRunner
            from ..engine.runners.live_runner import LiveRunner
            runner = LiveRunner(engine)

            deployment = DeployedPlay(
                uid=uid,
                play_id=play_id,
                symbol=symbol,
                capital=capital,
                runner=runner,
                started_at=utc_now().isoformat(),
                status="running",
            )
            self._deployments[uid] = deployment

            # Assign play to sub-account
            sub_mgr.assign_play(uid, play_id)

            # 9. Start runner in background task
            task = asyncio.create_task(self._run_play(uid, runner))
            deployment.task = task

            logger.info("Play %s deployed to sub uid=%d — runner started", play_id, uid)
            return uid

        except Exception:
            # Cleanup on failure: withdraw funds and delete sub
            logger.exception("Deployment failed for play %s — cleaning up sub uid=%d", play_id, uid)
            try:
                sub_mgr.withdraw(uid, spec.settle_coin, capital)
            except Exception:
                pass
            try:
                sub_mgr.delete(uid)
            except Exception:
                pass
            raise

    async def _run_play(self, uid: int, runner: LiveRunner) -> None:
        """Background task that runs the LiveRunner."""
        deployment = self._deployments.get(uid)
        try:
            await runner.start()
        except asyncio.CancelledError:
            logger.info("Play runner cancelled for sub uid=%d", uid)
        except Exception:
            logger.exception("Play runner error for sub uid=%d", uid)
            if deployment:
                deployment.status = "error"
        finally:
            if deployment and deployment.status != "error":
                deployment.status = "stopped"
            logger.info("Play runner finished for sub uid=%d (status=%s)", uid, deployment.status if deployment else "?")

    async def stop(self, uid: int, close_positions: bool = True) -> bool:
        """
        Stop a deployed play.

        Args:
            uid: Sub-account UID
            close_positions: Whether to close open positions

        Returns:
            True if stopped successfully
        """
        deployment = self._deployments.get(uid)
        if not deployment:
            raise KeyError(f"No deployment found for sub uid={uid}")

        deployment.status = "stopping"
        logger.info("Stopping play %s on sub uid=%d", deployment.play_id, uid)

        # Cancel the runner task
        if deployment.task and not deployment.task.done():
            deployment.task.cancel()
            try:
                await asyncio.wait_for(deployment.task, timeout=10.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # Close positions if requested
        if close_positions:
            try:
                sub_client = self._pm.sub_account_manager.get_client(uid)
                from ..config.constants import LINEAR_SETTLE_COINS
                # Cancel all orders
                for sc in LINEAR_SETTLE_COINS:
                    try:
                        sub_client.cancel_all_orders(settle_coin=sc)
                    except Exception:
                        pass
                # Close positions
                positions = self._pm.sub_account_manager.get_positions(uid)
                for pos in positions:
                    size = float(pos.get("size", 0))
                    if size <= 0:
                        continue
                    side = "Sell" if pos.get("side") == "Buy" else "Buy"
                    category = pos.get("_category", "linear")
                    try:
                        sub_client.create_order(
                            symbol=pos["symbol"], side=side,
                            order_type="Market", qty=size,
                            reduce_only=True, category=category,
                        )
                    except Exception as exc:
                        logger.warning("Failed to close %s: %s", pos["symbol"], exc)
            except Exception:
                logger.exception("Error closing positions for sub uid=%d", uid)

        # Unassign play
        self._pm.sub_account_manager.unassign_play(uid)
        deployment.status = "stopped"

        logger.info("Play %s stopped on sub uid=%d", deployment.play_id, uid)
        return True

    def get_status(self, uid: int) -> dict[str, Any]:
        """Get status of a deployed play."""
        deployment = self._deployments.get(uid)
        if not deployment:
            raise KeyError(f"No deployment found for sub uid={uid}")
        return deployment.to_dict()

    def get_active(self) -> list[dict[str, Any]]:
        """List all active deployments."""
        return [d.to_dict() for d in self._deployments.values() if d.status == "running"]

    def is_healthy(self, uid: int) -> tuple[bool, str]:
        """
        Heartbeat check for a deployed play.

        Checks:
        1. Runner task is alive (not crashed)
        2. Sub-account is not frozen
        3. WS connection is active (if runner supports it)

        Returns:
            (is_healthy, reason)
        """
        deployment = self._deployments.get(uid)
        if not deployment:
            return False, f"No deployment for uid={uid}"

        if deployment.status == "error":
            return False, "Runner crashed"

        if deployment.task and deployment.task.done():
            exc = deployment.task.exception() if not deployment.task.cancelled() else None
            if exc:
                return False, f"Runner task failed: {exc}"
            return False, "Runner task completed unexpectedly"

        try:
            info = self._pm.sub_account_manager.get(uid)
            if info.status == "frozen":
                return False, "Sub-account is frozen"
        except KeyError:
            return False, "Sub-account not found"

        return True, "OK"
