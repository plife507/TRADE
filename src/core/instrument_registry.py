"""
Instrument Registry — resolves any Bybit symbol to routing metadata.

Singleton cache of instrument specifications across all categories.
Thread-safe, TTL-based refresh, lazy-loaded.

Usage:
    from src.core.instrument_registry import InstrumentRegistry

    registry = InstrumentRegistry(client)
    registry.refresh()  # Loads linear + inverse

    spec = registry.resolve("BTCPERP")
    # InstrumentSpec(symbol='BTCPERP', category='linear', settle_coin='USDC', ...)

    routing = registry.get_routing("BTCPERP")
    # {"category": "linear", "settleCoin": "USDC"}
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..utils.logger import get_module_logger

if TYPE_CHECKING:
    from ..exchanges.bybit_client import BybitClient

logger = get_module_logger(__name__)

# Categories to load — inverse deferred for now but wired
SUPPORTED_CATEGORIES: list[str] = ["linear", "inverse"]

# Cache TTL — instruments rarely change but exchange can update specs
DEFAULT_TTL_SECONDS: float = 3600.0  # 1 hour


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    """Immutable instrument specification from Bybit."""

    symbol: str
    category: str           # "linear", "inverse"
    settle_coin: str        # "USDT", "USDC", "BTC", "ETH", ...
    base_coin: str          # "BTC", "ETH", "SOL", ...
    quote_coin: str         # "USDT", "USDC", "USD"
    contract_type: str      # "LinearPerpetual", "InversePerpetual", ...
    status: str             # "Trading", "Settling", "PreLaunch"
    tick_size: float
    qty_step: float
    min_order_qty: float
    max_order_qty: float
    max_mkt_order_qty: float
    min_notional: float
    max_leverage: float
    funding_interval: int   # minutes (480 = 8h)

    def to_dict(self) -> dict:
        """Serialize for ToolResult / JSON output."""
        return {
            "symbol": self.symbol,
            "category": self.category,
            "settle_coin": self.settle_coin,
            "base_coin": self.base_coin,
            "quote_coin": self.quote_coin,
            "contract_type": self.contract_type,
            "status": self.status,
            "tick_size": self.tick_size,
            "qty_step": self.qty_step,
            "min_order_qty": self.min_order_qty,
            "max_order_qty": self.max_order_qty,
            "max_mkt_order_qty": self.max_mkt_order_qty,
            "min_notional": self.min_notional,
            "max_leverage": self.max_leverage,
            "funding_interval": self.funding_interval,
        }

    @classmethod
    def from_bybit(cls, data: dict, category: str) -> InstrumentSpec:
        """Parse a single Bybit instrument info response into InstrumentSpec."""
        lot = data.get("lotSizeFilter", {})
        price = data.get("priceFilter", {})
        lev = data.get("leverageFilter", {})

        return cls(
            symbol=data["symbol"],
            category=category,
            settle_coin=data.get("settleCoin", ""),
            base_coin=data.get("baseCoin", ""),
            quote_coin=data.get("quoteCoin", ""),
            contract_type=data.get("contractType", ""),
            status=data.get("status", ""),
            tick_size=float(price.get("tickSize", 0) or 0),
            qty_step=float(lot.get("qtyStep", 0) or 0),
            min_order_qty=float(lot.get("minOrderQty", 0) or 0),
            max_order_qty=float(lot.get("maxOrderQty", 0) or 0),
            max_mkt_order_qty=float(lot.get("maxMktOrderQty", 0) or 0),
            min_notional=float(lot.get("minNotionalValue", 0) or 0),
            max_leverage=float(lev.get("maxLeverage", 1) or 1),
            funding_interval=int(data.get("fundingInterval", 0) or 0),
        )


class InstrumentRegistry:
    """
    Singleton cache of all Bybit instrument specs.

    Thread-safe. Lazy-loaded per category. TTL-based refresh.
    Resolves any symbol to its full specification and API routing params.
    """

    _instance: InstrumentRegistry | None = None
    _instance_lock = threading.Lock()

    def __init__(self, client: BybitClient, ttl: float = DEFAULT_TTL_SECONDS):
        self._client = client
        self._ttl = ttl
        self._cache: dict[str, InstrumentSpec] = {}
        self._lock = threading.RLock()
        self._last_refresh: float = 0.0
        self._categories_loaded: set[str] = set()
        self._refreshing = threading.Event()  # Guards against thundering herd

    @classmethod
    def get_instance(cls, client: BybitClient | None = None, ttl: float = DEFAULT_TTL_SECONDS) -> InstrumentRegistry:
        """
        Get or create the singleton instance.

        NOTE: If the instance already exists, `client` and `ttl` are ignored.
        Call `reset()` first if you need to reconfigure.
        """
        with cls._instance_lock:
            if cls._instance is None:
                if client is None:
                    raise RuntimeError("InstrumentRegistry not initialized — pass a BybitClient on first call")
                cls._instance = cls(client, ttl)
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        with cls._instance_lock:
            cls._instance = None

    def resolve(self, symbol: str) -> InstrumentSpec:
        """
        Resolve a symbol to its full instrument specification.

        Auto-refreshes if cache is empty or expired.

        Args:
            symbol: Bybit symbol (e.g., "BTCUSDT", "BTCPERP", "BTCUSD")

        Returns:
            InstrumentSpec with all routing and filter metadata

        Raises:
            KeyError: Symbol not found in any loaded category
        """
        self._ensure_loaded()

        with self._lock:
            spec = self._cache.get(symbol)

        if spec is None:
            raise KeyError(
                f"Symbol '{symbol}' not found in instrument registry. "
                f"Loaded categories: {sorted(self._categories_loaded)}. "
                f"Total instruments: {len(self._cache)}"
            )
        return spec

    def get_routing(self, symbol: str) -> dict[str, str]:
        """
        Get API routing parameters for a symbol.

        Returns Bybit-native camelCase keys for direct API pass-through:
            {"category": "linear"|"inverse", "settleCoin": "USDT"|"USDC"|...}
        """
        spec = self.resolve(symbol)
        return {"category": spec.category, "settleCoin": spec.settle_coin}

    def refresh(self, categories: list[str] | None = None) -> int:
        """
        Refresh instrument cache from Bybit REST API.

        Uses atomic swap: builds a new cache dict, then swaps it in
        under the lock only if ALL categories loaded successfully.
        On partial failure, the old cache is preserved.

        Args:
            categories: Categories to load. Default: all supported.

        Returns:
            Total number of instruments loaded across all categories.
        """
        cats = categories or SUPPORTED_CATEGORIES
        new_cache: dict[str, InstrumentSpec] = {}
        new_categories: set[str] = set()
        total = 0

        for category in cats:
            try:
                count = self._load_category_into(category, new_cache)
            except RuntimeError:
                logger.exception("Failed to load category=%s — skipping", category)
                continue
            if count > 0:
                new_categories.add(category)
            total += count
            logger.info(
                "InstrumentRegistry loaded %d instruments for category=%s",
                count, category,
            )

        if total == 0:
            logger.warning("InstrumentRegistry refresh loaded 0 instruments — keeping old cache")
            return 0

        # Atomic swap: replace entire cache at once
        with self._lock:
            self._cache = new_cache
            self._categories_loaded = new_categories
            self._last_refresh = time.time()

        logger.info(
            "InstrumentRegistry refresh complete: %d total instruments across %s",
            total, cats,
        )
        return total

    def list_symbols(
        self,
        category: str | None = None,
        settle_coin: str | None = None,
        status: str = "Trading",
    ) -> list[str]:
        """
        List symbols with optional filters.

        Args:
            category: Filter by category ("linear", "inverse")
            settle_coin: Filter by settlement coin ("USDT", "USDC", "BTC")
            status: Filter by status (default "Trading")

        Returns:
            Sorted list of matching symbol names
        """
        self._ensure_loaded()

        with self._lock:
            results = []
            for spec in self._cache.values():
                if category and spec.category != category:
                    continue
                if settle_coin and spec.settle_coin != settle_coin:
                    continue
                if status and spec.status != status:
                    continue
                results.append(spec.symbol)

        return sorted(results)

    def get_all_specs(
        self,
        category: str | None = None,
        settle_coin: str | None = None,
    ) -> list[InstrumentSpec]:
        """Get all specs matching filters."""
        self._ensure_loaded()

        with self._lock:
            results = []
            for spec in self._cache.values():
                if category and spec.category != category:
                    continue
                if settle_coin and spec.settle_coin != settle_coin:
                    continue
                results.append(spec)

        return sorted(results, key=lambda s: s.symbol)

    def is_loaded(self) -> bool:
        """Whether the cache has been populated."""
        with self._lock:
            return len(self._cache) > 0

    @property
    def size(self) -> int:
        """Number of cached instruments."""
        with self._lock:
            return len(self._cache)

    def _ensure_loaded(self) -> None:
        """Auto-refresh if cache is empty or TTL expired. Single-refresh guard."""
        with self._lock:
            if self._cache and (time.time() - self._last_refresh) <= self._ttl:
                return  # Cache is fresh

        # Only one thread performs the refresh; others wait
        if self._refreshing.is_set():
            # Another thread is already refreshing — wait for it
            self._refreshing.wait(timeout=30.0)
            return

        self._refreshing.set()
        try:
            self.refresh()
        finally:
            self._refreshing.clear()

    def _load_category_into(self, category: str, target: dict[str, InstrumentSpec]) -> int:
        """
        Load all instruments for a category into the target dict.

        Does NOT modify self._cache — caller handles atomic swap.
        On API failure, raises so caller can decide whether to proceed.

        Returns:
            Number of instruments loaded (0 is valid for empty categories).

        Raises:
            RuntimeError: If the API call fails.
        """
        count = 0
        cursor = ""

        while True:
            self._client._public_limiter.acquire()
            kwargs: dict = {"category": category, "limit": 1000}
            if cursor:
                kwargs["cursor"] = cursor

            try:
                response = self._client._session.get_instruments_info(**kwargs)
            except Exception as exc:
                raise RuntimeError(f"API call failed for category={category}") from exc

            result = self._client._extract_result(response)
            instruments = result.get("list", [])

            for raw in instruments:
                if raw.get("status") not in ("Trading", "PreLaunch"):
                    continue
                try:
                    spec = InstrumentSpec.from_bybit(raw, category)
                except (ValueError, KeyError):
                    logger.warning("Skipping malformed instrument: %s", raw.get("symbol", "?"))
                    continue
                target[spec.symbol] = spec
                count += 1

            # Check pagination
            next_cursor = result.get("nextPageCursor", "")
            if not next_cursor or not instruments:
                break
            cursor = next_cursor

        return count
