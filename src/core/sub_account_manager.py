"""
Sub-Account Manager — full lifecycle management for Bybit sub-accounts.

Creates, funds, monitors, freezes, and deletes sub-accounts programmatically.
Each sub-account gets its own BybitClient with independent API keys and rate limits.

Usage:
    from src.core.sub_account_manager import SubAccountManager

    mgr = SubAccountManager(main_client)
    mgr.load_state()  # Reconnect to existing subs

    info = mgr.create("play_btc_01")   # Create sub + API keys
    mgr.fund(info.uid, "USDT", 100.0)  # Transfer from main
    client = mgr.get_client(info.uid)   # Get sub's BybitClient
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pybit.exceptions import InvalidRequestError

from ..config.constants import PROJECT_ROOT
from ..utils.datetime_utils import utc_now
from ..utils.logger import get_module_logger

if TYPE_CHECKING:
    from ..exchanges.bybit_client import BybitClient

logger = get_module_logger(__name__)

# Bybit hard limit: max 20 sub-accounts per master UID
MAX_SUB_ACCOUNTS = 20

# State persistence path (inside data/ which is gitignored)
STATE_DIR = PROJECT_ROOT / "data" / "runtime"
STATE_FILE = STATE_DIR / "sub_accounts.json"


@dataclass
class SubAccountInfo:
    """Managed sub-account metadata and credentials."""

    uid: int
    username: str
    api_key: str
    api_secret: str
    status: str = "active"          # "active", "frozen", "deleted"
    play_id: str | None = None      # Currently deployed play
    created_at: str = ""            # ISO format
    funded_coin: str = ""           # Primary funding coin
    funded_amount: float = 0.0      # Cumulative transferred in
    withdrawn_amount: float = 0.0   # Cumulative transferred out

    def __repr__(self) -> str:
        """Safe repr — never exposes secrets in tracebacks or logs."""
        return f"SubAccountInfo(uid={self.uid}, username={self.username!r}, status={self.status!r})"

    def to_dict(self) -> dict[str, Any]:
        """Serialize for persistence (includes secrets)."""
        return {
            "uid": self.uid,
            "username": self.username,
            "api_key": self.api_key,
            "api_secret": self.api_secret,
            "status": self.status,
            "play_id": self.play_id,
            "created_at": self.created_at,
            "funded_coin": self.funded_coin,
            "funded_amount": self.funded_amount,
            "withdrawn_amount": self.withdrawn_amount,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubAccountInfo:
        """Deserialize from persistence."""
        return cls(
            uid=data["uid"],
            username=data["username"],
            api_key=data["api_key"],
            api_secret=data["api_secret"],
            status=data.get("status", "active"),
            play_id=data.get("play_id"),
            created_at=data.get("created_at", ""),
            funded_coin=data.get("funded_coin", ""),
            funded_amount=data.get("funded_amount", 0.0),
            withdrawn_amount=data.get("withdrawn_amount", 0.0),
        )

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize WITHOUT secrets (for logging/display)."""
        return {
            "uid": self.uid,
            "username": self.username,
            "status": self.status,
            "play_id": self.play_id,
            "created_at": self.created_at,
            "funded_coin": self.funded_coin,
            "funded_amount": self.funded_amount,
            "withdrawn_amount": self.withdrawn_amount,
            "net_funded": self.funded_amount - self.withdrawn_amount,
        }


class SubAccountManager:
    """
    Lifecycle management for Bybit sub-accounts.

    Uses the main account's API key to:
    - Create sub-accounts (POST /v5/user/create-sub-member)
    - Generate API keys for subs (POST /v5/user/create-sub-api)
    - Transfer funds between main and sub (POST /v5/asset/transfer/universal-transfer)
    - Query sub-account balances (GET /v5/asset/transfer/query-account-coin-balance)
    - Freeze/delete sub-accounts

    Each sub gets its own BybitClient with independent rate limits (10/s per UID).
    State is persisted to data/runtime/sub_accounts.json.
    """

    def __init__(self, main_client: BybitClient, main_uid: int | None = None):
        self._main_client = main_client
        self._main_uid = main_uid or self._resolve_main_uid()
        self._sub_accounts: dict[int, SubAccountInfo] = {}
        self._sub_clients: dict[int, BybitClient] = {}
        self._lock = threading.RLock()

    def _resolve_main_uid(self) -> int:
        """Get main account UID from API key info."""
        try:
            result = self._main_client.session.get_api_key_information()
            info = self._main_client._extract_result(result)
            uid = int(info.get("userID", 0))
            if uid == 0:
                raise ValueError("Could not determine main account UID from API key info")
            logger.info("Resolved main account UID: %d", uid)
            return uid
        except Exception:
            logger.exception("Failed to resolve main account UID")
            raise

    # ── Sub-Account Creation ────────────────────────────────

    def create(self, username: str) -> SubAccountInfo:
        """
        Create a new sub-account with API keys.

        Steps:
        1. Create sub-account via POST /v5/user/create-sub-member
        2. Create API key for sub via POST /v5/user/create-sub-api
        3. Store info and persist to disk

        Args:
            username: 6-16 chars, must include numbers AND letters.

        Returns:
            SubAccountInfo with credentials.

        Raises:
            ValueError: If username format is invalid.
            RuntimeError: If creation or API key generation fails.
        """
        # M2: Validate username format locally before API call
        if not (6 <= len(username) <= 16):
            raise ValueError(f"Username must be 6-16 chars, got {len(username)}: {username!r}")
        if not any(c.isalpha() for c in username) or not any(c.isdigit() for c in username):
            raise ValueError(f"Username must include both letters and digits: {username!r}")

        # Bug 3: Pre-check max 20 sub-account limit (Bybit hard limit)
        with self._lock:
            active_count = sum(
                1 for info in self._sub_accounts.values()
                if info.status != "deleted"
            )
        if active_count >= MAX_SUB_ACCOUNTS:
            raise RuntimeError(
                f"Cannot create sub-account: already at Bybit limit of {MAX_SUB_ACCOUNTS} "
                f"sub-accounts ({active_count} active). Delete unused subs first."
            )

        # Step 1: Create sub-account
        logger.info("Creating sub-account: username=%s", username)
        try:
            create_resp = self._main_client.session.create_sub_uid(
                username=username,
                memberType=1,  # Normal sub-account (always UTA)
            )
        except InvalidRequestError as e:
            # Bug 2: Handle "username already exists" — find and return the existing sub
            err_msg = str(e.message) if hasattr(e, "message") else str(e)
            if "already exist" in err_msg.lower() or "duplicate" in err_msg.lower():
                logger.warning(
                    "Username %r already exists on exchange, looking up existing sub",
                    username,
                )
                return self._find_existing_sub(username)
            raise RuntimeError(f"Sub-account creation failed: {err_msg}") from e

        create_result = self._main_client._extract_result(create_resp)

        uid = int(create_result.get("uid", 0))
        if uid == 0:
            raise RuntimeError(f"Sub-account creation failed: {create_result}")

        logger.info("Sub-account created: uid=%d, username=%s", uid, username)

        # Step 2: Create API key for the sub-account
        # C1: If this fails, clean up the orphaned sub-account
        permissions = {
            "ContractTrade": ["Order", "Position"],
            "Spot": ["SpotTrade"],
            "Wallet": ["AccountTransfer", "SubMemberTransferList"],
            "Options": ["OptionsTrade"],
            "Exchange": ["ExchangeHistory"],
        }

        try:
            api_resp = self._main_client.session.create_sub_api_key(
                subuid=uid,
                readOnly=0,  # Read+Write
                permissions=permissions,
                note=f"TRADE-bot-{username}",
            )
            api_result = self._main_client._extract_result(api_resp)

            api_key = api_result.get("apiKey", "")
            api_secret = api_result.get("secret", "")
            if not api_key or not api_secret:
                raise RuntimeError(f"API key creation returned empty credentials: {api_result}")
        except Exception:
            logger.error("API key creation failed for sub uid=%d; cleaning up orphan", uid)
            try:
                self._main_client.session.delete_sub_uid(subMemberId=uid)
                logger.info("Cleaned up orphaned sub uid=%d", uid)
            except Exception:
                logger.error("Cleanup also failed — orphaned sub uid=%d remains on exchange", uid)
            raise

        logger.info("API key created for sub uid=%d", uid)

        # Step 3: Store and persist
        info = SubAccountInfo(
            uid=uid,
            username=username,
            api_key=api_key,
            api_secret=api_secret,
            status="active",
            created_at=utc_now().isoformat(),
        )

        with self._lock:
            self._sub_accounts[uid] = info

        self.save_state()
        return info

    def _find_existing_sub(self, username: str) -> SubAccountInfo:
        """
        Find an existing sub-account by username after a 'username already exists' error.

        Checks local state first, then syncs from exchange. If found but missing
        API keys, raises with a helpful message.

        Raises:
            RuntimeError: If the sub cannot be found or has no API keys.
        """
        # Check local state first
        with self._lock:
            for info in self._sub_accounts.values():
                if info.username == username and info.status != "deleted":
                    logger.info(
                        "Found existing sub uid=%d for username=%s in local state",
                        info.uid, username,
                    )
                    return info

        # Not in local state — sync from exchange and try again
        self.sync_from_exchange()

        with self._lock:
            for info in self._sub_accounts.values():
                if info.username == username and info.status != "deleted":
                    if not info.api_key:
                        raise RuntimeError(
                            f"Sub-account username={username!r} (uid={info.uid}) exists on "
                            f"exchange but has no API keys in local state. "
                            f"Generate keys manually or delete and re-create."
                        )
                    logger.info(
                        "Found existing sub uid=%d for username=%s via exchange sync",
                        info.uid, username,
                    )
                    return info

        raise RuntimeError(
            f"Sub-account username={username!r} reportedly exists on exchange "
            f"but could not be found via API. It may have been deleted previously "
            f"(Bybit reserves deleted usernames). Choose a different username."
        )

    # ── Client Management ───────────────────────────────────

    def get_client(self, uid: int) -> BybitClient:
        """
        Get or create a BybitClient for a sub-account.

        Lazily creates the client on first access. Cached per UID.

        Args:
            uid: Sub-account UID

        Returns:
            BybitClient authenticated with the sub's API key

        Raises:
            KeyError: Sub-account not found
        """
        with self._lock:
            if uid in self._sub_clients:
                return self._sub_clients[uid]

            info = self._sub_accounts.get(uid)
            if info is None:
                raise KeyError(f"Sub-account uid={uid} not found")

        # Create client outside lock (BybitClient.__init__ calls _sync_server_time)
        from ..exchanges.bybit_client import BybitClient
        client = BybitClient(
            api_key=info.api_key,
            api_secret=info.api_secret,
        )

        # Double-check: another thread may have created it while we were blocked
        with self._lock:
            if uid in self._sub_clients:
                return self._sub_clients[uid]
            self._sub_clients[uid] = client

        logger.info("BybitClient created for sub uid=%d", uid)
        return client

    # ── Fund Transfers ──────────────────────────────────────

    def fund(self, uid: int, coin: str, amount: float) -> str:
        """
        Transfer funds from main account to sub-account.

        Args:
            uid: Sub-account UID
            coin: Coin to transfer (e.g., "USDT")
            amount: Amount to transfer

        Returns:
            Transfer ID string

        Raises:
            KeyError: Sub-account not found
            RuntimeError: Transfer failed
        """
        with self._lock:
            info = self._sub_accounts.get(uid)
            if info is None:
                raise KeyError(f"Sub-account uid={uid} not found")

        transfer_id = str(uuid.uuid4())

        logger.info(
            "Transferring %s %s: main(%d) → sub(%d), transfer_id=%s",
            amount, coin, self._main_uid, uid, transfer_id,
        )

        resp = self._main_client.session.create_universal_transfer(
            transferId=transfer_id,
            coin=coin.upper(),
            amount=str(amount),
            fromMemberId=self._main_uid,
            toMemberId=uid,
            fromAccountType="UNIFIED",
            toAccountType="UNIFIED",
        )
        result = self._main_client._extract_result(resp)

        status = result.get("status", "")
        if status not in ("SUCCESS", "PENDING"):
            raise RuntimeError(f"Transfer failed: status={status}, result={result}")

        # Optimistic accounting — update on both SUCCESS and PENDING.
        # If PENDING transfer fails, manual reconciliation needed via sync_from_exchange().
        # Not saving on PENDING risks losing track of the transfer entirely if the process crashes.
        with self._lock:
            info.funded_coin = coin.upper()
            info.funded_amount += amount
        self.save_state()
        if status == "PENDING":
            logger.warning(
                "Transfer PENDING for sub uid=%d — optimistic accounting applied, "
                "reconcile via sync_from_exchange() if transfer fails",
                uid,
            )

        logger.info("Transfer %s: %s %s to sub uid=%d", status, amount, coin, uid)
        return transfer_id

    def withdraw(self, uid: int, coin: str, amount: float) -> str:
        """
        Transfer funds from sub-account back to main account.

        Args:
            uid: Sub-account UID
            coin: Coin to transfer
            amount: Amount to transfer

        Returns:
            Transfer ID string
        """
        with self._lock:
            info = self._sub_accounts.get(uid)
            if info is None:
                raise KeyError(f"Sub-account uid={uid} not found")

        transfer_id = str(uuid.uuid4())

        logger.info(
            "Withdrawing %s %s: sub(%d) → main(%d), transfer_id=%s",
            amount, coin, uid, self._main_uid, transfer_id,
        )

        resp = self._main_client.session.create_universal_transfer(
            transferId=transfer_id,
            coin=coin.upper(),
            amount=str(amount),
            fromMemberId=uid,
            toMemberId=self._main_uid,
            fromAccountType="UNIFIED",
            toAccountType="UNIFIED",
        )
        result = self._main_client._extract_result(resp)

        status = result.get("status", "")
        if status not in ("SUCCESS", "PENDING"):
            raise RuntimeError(f"Withdrawal failed: status={status}, result={result}")

        # Optimistic accounting — update on both SUCCESS and PENDING.
        # If PENDING transfer fails, manual reconciliation needed via sync_from_exchange().
        with self._lock:
            info.withdrawn_amount += amount
        self.save_state()
        if status == "PENDING":
            logger.warning(
                "Withdrawal PENDING for sub uid=%d — optimistic accounting applied, "
                "reconcile via sync_from_exchange() if transfer fails",
                uid,
            )

        logger.info("Withdrawal %s: %s %s from sub uid=%d", status, amount, coin, uid)
        return transfer_id

    # ── Balance Queries ─────────────────────────────────────

    def get_balance(self, uid: int, coin: str = "USDT") -> dict[str, Any]:
        """
        Query sub-account balance via main account API key.

        Args:
            uid: Sub-account UID
            coin: Coin to query

        Returns:
            Dict with coin, walletBalance, transferBalance
        """
        resp = self._main_client.session.get_coin_balance(
            memberId=str(uid),
            accountType="UNIFIED",
            coin=coin.upper(),
        )
        result = self._main_client._extract_result(resp)
        balance = result.get("balance", {})
        return {
            "uid": uid,
            "coin": balance.get("coin", coin),
            "wallet_balance": float(balance.get("walletBalance", 0) or 0),
            "transfer_balance": float(balance.get("transferBalance", 0) or 0),
            "bonus": float(balance.get("bonus", 0) or 0),
        }

    def get_positions(self, uid: int) -> list[dict]:
        """
        Query sub-account positions using the sub's own BybitClient.

        Can't query sub positions from main — must use sub's API key.

        Args:
            uid: Sub-account UID

        Returns:
            List of position dicts from Bybit API
        """
        from ..config.constants import LINEAR_SETTLE_COINS

        client = self.get_client(uid)
        positions: list[dict] = []

        # Linear: query each settle coin (Bybit requires symbol or settleCoin)
        for settle_coin in LINEAR_SETTLE_COINS:
            try:
                raw = client.get_positions(settle_coin=settle_coin, category="linear")
                for pos in raw:
                    if float(pos.get("size", 0)) > 0:
                        pos["_category"] = "linear"
                        sym = pos.get("symbol", "")
                        pos["_settle_coin"] = "USDC" if sym.endswith("PERP") or sym.endswith("USDC") else "USDT"
                        positions.append(pos)
            except Exception:
                logger.warning("Failed to query linear/%s positions for sub uid=%d", settle_coin, uid)

        # Inverse: single query (no settleCoin needed for inverse category)
        try:
            raw = client.get_positions(category="inverse")
            for pos in raw:
                if float(pos.get("size", 0)) > 0:
                    pos["_category"] = "inverse"
                    # Inverse settle coin = base coin (from symbol: BTCUSD → BTC, ETHUSD → ETH)
                    sym = pos.get("symbol", "")
                    pos["_settle_coin"] = sym.replace("USD", "").rstrip("HMUZ0123456789")  # Strip futures suffix
                    positions.append(pos)
        except Exception:
            logger.warning("Failed to query inverse positions for sub uid=%d", uid)

        return positions

    # ── Lifecycle Management ────────────────────────────────

    def freeze(self, uid: int) -> bool:
        """Freeze a sub-account (stop trading)."""
        with self._lock:
            info = self._sub_accounts.get(uid)
            if info is None:
                raise KeyError(f"Sub-account uid={uid} not found")

        logger.info("Freezing sub-account uid=%d", uid)

        resp = self._main_client.session.freeze_sub_uid(
            subuid=uid,
            frozen=1,
        )
        self._main_client._extract_result(resp)

        with self._lock:
            info.status = "frozen"

        self.save_state()
        logger.info("Sub-account uid=%d frozen", uid)
        return True

    def unfreeze(self, uid: int) -> bool:
        """Unfreeze a sub-account."""
        with self._lock:
            info = self._sub_accounts.get(uid)
            if info is None:
                raise KeyError(f"Sub-account uid={uid} not found")

        logger.info("Unfreezing sub-account uid=%d", uid)

        resp = self._main_client.session.freeze_sub_uid(
            subuid=uid,
            frozen=0,
        )
        self._main_client._extract_result(resp)

        with self._lock:
            info.status = "active"

        self.save_state()
        logger.info("Sub-account uid=%d unfrozen", uid)
        return True

    def delete(self, uid: int) -> bool:
        """
        Delete a sub-account. Must have zero balance.

        Checks balance first, cleans up cached client and local state.
        """
        with self._lock:
            info = self._sub_accounts.get(uid)
            if info is None:
                raise KeyError(f"Sub-account uid={uid} not found")

        # M1: Verify zero balance before attempting delete
        try:
            balance = self.get_balance(uid, "USDT")
            if balance["wallet_balance"] > 0:
                raise RuntimeError(
                    f"Cannot delete sub uid={uid}: USDT balance={balance['wallet_balance']}. Withdraw first."
                )
        except KeyError:
            pass  # Balance query failed — proceed with delete, Bybit will reject if non-empty

        logger.info("Deleting sub-account uid=%d (username=%s)", uid, info.username)

        resp = self._main_client.session.delete_sub_uid(
            subMemberId=uid,
        )
        self._main_client._extract_result(resp)

        # M3: Remove from dict entirely (not just mark deleted)
        with self._lock:
            self._sub_accounts.pop(uid, None)
            self._sub_clients.pop(uid, None)

        self.save_state()
        logger.info("Sub-account uid=%d deleted", uid)
        return True

    # ── Listing & Lookup ────────────────────────────────────

    def list(self) -> list[SubAccountInfo]:
        """List all managed sub-accounts (excludes deleted)."""
        with self._lock:
            return [
                info for info in self._sub_accounts.values()
                if info.status != "deleted"
            ]

    def get(self, uid: int) -> SubAccountInfo:
        """Get sub-account info by UID."""
        with self._lock:
            info = self._sub_accounts.get(uid)
            if info is None:
                raise KeyError(f"Sub-account uid={uid} not found")
            return info

    def assign_play(self, uid: int, play_id: str) -> None:
        """Assign a play to a sub-account."""
        with self._lock:
            info = self._sub_accounts.get(uid)
            if info is None:
                raise KeyError(f"Sub-account uid={uid} not found")
            info.play_id = play_id
        self.save_state()

    def unassign_play(self, uid: int) -> None:
        """Clear play assignment from a sub-account."""
        with self._lock:
            info = self._sub_accounts.get(uid)
            if info is None:
                raise KeyError(f"Sub-account uid={uid} not found")
            info.play_id = None
        self.save_state()

    # ── State Persistence ───────────────────────────────────

    def save_state(self) -> None:
        """Persist sub-account registry to disk."""
        STATE_DIR.mkdir(parents=True, exist_ok=True)

        with self._lock:
            data = {
                "main_uid": self._main_uid,
                "sub_accounts": {
                    str(uid): info.to_dict()
                    for uid, info in self._sub_accounts.items()
                },
            }

        # Atomic write (temp + rename) with owner-only permissions (C2: secrets at rest)
        tmp_path = STATE_FILE.with_suffix(".tmp")
        with open(tmp_path, "w", newline="\n") as f:
            json.dump(data, f, indent=2)
        tmp_path.replace(STATE_FILE)
        try:
            os.chmod(STATE_FILE, 0o600)
        except OSError as e:
            logger.warning("Could not set 0o600 on state file: %s", e)

        logger.debug("Sub-account state saved: %d accounts", len(data["sub_accounts"]))

    def load_state(self) -> int:
        """
        Load sub-account registry from disk.

        Returns:
            Number of sub-accounts loaded.
        """
        if not STATE_FILE.exists():
            logger.info("No sub-account state file found at %s", STATE_FILE)
            return 0

        with open(STATE_FILE, newline="\n") as f:
            data = json.load(f)

        loaded = 0
        with self._lock:
            for _uid_str, info_dict in data.get("sub_accounts", {}).items():
                info = SubAccountInfo.from_dict(info_dict)
                if info.status != "deleted":
                    self._sub_accounts[info.uid] = info
                    loaded += 1

        logger.info("Loaded %d sub-accounts from state file", loaded)
        return loaded

    # ── Sync with Exchange ──────────────────────────────────

    def sync_from_exchange(self) -> int:
        """
        Discover existing sub-accounts from Bybit and merge with local state.

        Finds subs that exist on exchange but not in local state (e.g., created
        manually or from a previous session without state persistence).

        Returns:
            Number of newly discovered sub-accounts.
        """
        resp = self._main_client.session.get_sub_uid_list()
        result = self._main_client._extract_result(resp)
        exchange_subs = result.get("subMembers", [])

        discovered = 0
        with self._lock:
            for sub in exchange_subs:
                uid = int(sub.get("uid", 0))
                if uid == 0:
                    continue
                if uid not in self._sub_accounts:
                    # H1: Map Bybit integer status to internal string
                    bybit_status = sub.get("status", 1)
                    if bybit_status == 4:
                        status = "frozen"
                    elif bybit_status == 2:
                        status = "login_banned"
                    else:
                        status = "active"

                    info = SubAccountInfo(
                        uid=uid,
                        username=sub.get("username", ""),
                        api_key="",       # No key — was created externally
                        api_secret="",    # Must regenerate if needed
                        status=status,
                        created_at=sub.get("createTime", ""),
                    )
                    self._sub_accounts[uid] = info
                    discovered += 1
                    logger.info(
                        "Discovered sub-account: uid=%d, username=%s (no API keys — create manually)",
                        uid, info.username,
                    )

        if discovered > 0:
            self.save_state()
        return discovered

    @property
    def main_uid(self) -> int:
        """Main account UID."""
        return self._main_uid
