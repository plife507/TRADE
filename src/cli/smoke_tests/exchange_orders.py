"""
Live exchange order lifecycle smoke test.

Tests the full order lifecycle against the real Bybit API:
  Place → Verify → Amend → Verify → Cancel → Verify

Safety: All limit orders placed 50% from market price.
They will NEVER fill. Cleanup guaranteed via try/finally.
Orders tagged with SMOKE_ prefix — cleanup never touches production orders.

Tiers:
  EX4 (Tier 1): Order lifecycle — zero cost, zero risk
  PL5 (Tier 2): Position lifecycle — costs ~$0.02 in fees, requires --confirm

Sub-account isolation: When a smoke test sub-account exists, EX4 runs
against that sub-account instead of main, providing complete capital isolation.
"""

import time
import uuid

from src.core import exchange_instruments as inst
from src.core.exchange_instruments import OrderSizeError
from src.config.config import get_config
from src.utils.logger import get_module_logger

logger = get_module_logger(__name__)

SMOKE_ORDER_PREFIX = "SMOKE_"
SAFE_PRICE_FACTOR = 0.50  # 50% away from market
MIN_BALANCE_FOR_ORDER_TEST = 1.0  # $1 minimum for Tier 1
MIN_BALANCE_FOR_POSITION_TEST = 5.0  # $5 minimum for Tier 2
SMOKE_SUB_USERNAME = "smoke_test"  # Dedicated sub-account name


# ── Helpers ──────────────────────────────────────────────────────────


def _generate_smoke_link_id() -> str:
    """Generate a unique order_link_id with SMOKE_ prefix."""
    return f"{SMOKE_ORDER_PREFIX}{uuid.uuid4().hex[:12]}"


def _compute_safe_buy_price(manager, symbol: str, market_price: float) -> float:
    """Compute a limit buy price that will NEVER fill.

    Places the order 50% below current market, rounded to tick size.
    For BTC at $84k → ~$42k. Will not execute in any realistic scenario
    during the ~5 second test window.
    """
    raw = market_price * SAFE_PRICE_FACTOR
    tick = inst.get_tick_size(manager, symbol)
    raw = max(raw, tick)
    return inst.round_price(manager, symbol, raw)


def _compute_safe_sell_price(manager, symbol: str, market_price: float) -> float:
    """Compute a limit sell price that will NEVER fill.

    Places the order 50% above current market, rounded to tick size.
    """
    raw = market_price * (1.0 + SAFE_PRICE_FACTOR)
    return inst.round_price(manager, symbol, raw)


def _get_smoke_manager():
    """Get ExchangeManager for smoke testing.

    Prefers a dedicated smoke test sub-account if it exists.
    Falls back to main account ExchangeManager.
    """
    from src.tools.shared import _get_exchange_manager

    main_manager = _get_exchange_manager()

    # Try to use dedicated smoke sub-account
    try:
        from src.core.sub_account_manager import SubAccountManager
        sub_mgr = SubAccountManager(main_manager.bybit, main_uid=None)
        sub_mgr.load_state()
        # Look up by username since .get() takes uid
        sub_info = next(
            (s for s in sub_mgr.list() if s.username == SMOKE_SUB_USERNAME),
            None,
        )
        if sub_info and sub_info.status == "active":
            smoke_client = sub_mgr.get_client(sub_info.uid)
            from src.core.exchange_manager import ExchangeManager
            smoke_manager = ExchangeManager(client=smoke_client)
            logger.info("Using smoke test sub-account (UID: %s)", sub_info.uid)
            return smoke_manager, True  # (manager, is_sub_account)
    except Exception as e:
        logger.debug("No smoke sub-account available: %s", e)

    return main_manager, False


def _cleanup_smoke_orders(manager, symbol: str) -> None:
    """Guarantee no orphaned SMOKE_ orders remain.

    Defense in depth:
    1. Query open orders for symbol
    2. Cancel only SMOKE_-prefixed orders (never touches production)
    3. Verify none remain
    """
    try:
        open_orders = manager.get_open_orders(symbol=symbol)
        smoke_orders = [
            o for o in open_orders
            if o.order_link_id and o.order_link_id.startswith(SMOKE_ORDER_PREFIX)
        ]

        if smoke_orders:
            logger.warning(
                "Cleaning up %d orphaned smoke orders for %s",
                len(smoke_orders), symbol,
            )
            for o in smoke_orders:
                try:
                    manager.cancel_order(symbol=symbol, order_id=o.order_id)
                except Exception:
                    pass  # Best effort

        # Final verification
        remaining = manager.get_open_orders(symbol=symbol)
        remaining_smoke = [
            o for o in remaining
            if o.order_link_id and o.order_link_id.startswith(SMOKE_ORDER_PREFIX)
        ]
        if remaining_smoke:
            logger.error(
                "SMOKE CLEANUP FAILED: %d smoke orders still open for %s",
                len(remaining_smoke), symbol,
            )
            # Nuclear: only if ALL remaining are smoke orders
            if len(remaining_smoke) == len(remaining):
                manager.cancel_all_orders(symbol=symbol)
    except Exception as e:
        logger.error("Smoke cleanup error: %s", e)


# ── Tier 1: Order Lifecycle (EX4) ───────────────────────────────────


def run_order_lifecycle_smoke() -> dict:
    """Run the full order lifecycle smoke test against real Bybit API.

    Place limit buy 50% below market → verify → amend → verify → cancel → verify.
    Order never fills. Cleanup guaranteed.

    Returns:
        dict with keys: checked, failures, skipped, skip_reason
    """
    config = get_config()
    symbol = config.smoke.symbols[0] if config.smoke.symbols else "BTCUSDT"

    manager, is_sub = _get_smoke_manager()
    account_label = "smoke sub-account" if is_sub else "main account"

    # Pre-check: sufficient balance
    try:
        balance = manager.get_balance()
        available = balance.get("available", 0.0)
        if available < MIN_BALANCE_FOR_ORDER_TEST:
            return {
                "checked": 0,
                "failures": [],
                "skipped": True,
                "skip_reason": (
                    f"{account_label} balance ${available:.2f} "
                    f"< ${MIN_BALANCE_FOR_ORDER_TEST:.2f} minimum"
                ),
            }
    except Exception as e:
        return {
            "checked": 0,
            "failures": [f"Balance check failed ({account_label}): {e}"],
            "skipped": False,
            "skip_reason": None,
        }

    failures: list[str] = []
    checked = 0
    order_id: str | None = None
    order_link_id = _generate_smoke_link_id()

    try:
        # === STEP 1: Get market price ===
        checked += 1
        market_price = manager.get_price(symbol)
        if market_price <= 0:
            failures.append(f"Invalid market price: {market_price}")
            return _result(checked, failures)

        # === STEP 2: Compute safe price ===
        checked += 1
        safe_price = _compute_safe_buy_price(manager, symbol, market_price)

        # Sanity: verify price is actually far from market
        distance_pct = abs(market_price - safe_price) / market_price * 100
        if distance_pct < 30:
            failures.append(
                f"Safe price too close to market: {distance_pct:.1f}% (need >30%)"
            )
            return _result(checked, failures)

        # === STEP 3: Calculate quantity ===
        checked += 1
        usd_size = min(config.smoke.usd_size, 100.0)
        try:
            _qty = inst.calculate_qty(manager, symbol, usd_size, safe_price)
        except OrderSizeError:
            # Fallback: try minimum qty
            min_qty = inst.get_min_qty(manager, symbol)
            min_usd = min_qty * safe_price
            if min_usd > available:
                return {
                    "checked": checked,
                    "failures": [],
                    "skipped": True,
                    "skip_reason": f"Min order ${min_usd:.2f} > available ${available:.2f}",
                }

        # === STEP 4: Place limit buy far below market ===
        checked += 1
        place_result = manager.limit_buy(
            symbol=symbol,
            usd_amount=usd_size,
            price=safe_price,
            time_in_force="GTC",
            order_link_id=order_link_id,
        )
        if not place_result.success:
            failures.append(f"Place limit buy: {place_result.error}")
            return _result(checked, failures)

        order_id = place_result.order_id
        if not order_id:
            failures.append("Place succeeded but no order_id returned")
            return _result(checked, failures)

        logger.info(
            "Smoke order placed: %s %s @ $%.2f (market $%.2f, -%0.f%%)",
            symbol, order_id, safe_price, market_price, distance_pct,
        )

        # === STEP 5: Verify order in open orders ===
        checked += 1
        time.sleep(0.5)
        open_orders = manager.get_open_orders(symbol=symbol)
        found = any(o.order_id == order_id for o in open_orders)
        if not found:
            failures.append(f"Order {order_id} not found in open orders")

        # === STEP 6: Amend order price ===
        checked += 1
        tick = inst.get_tick_size(manager, symbol)
        amended_price = inst.round_price(manager, symbol, safe_price - tick * 10)
        if amended_price == safe_price:
            amended_price = inst.round_price(manager, symbol, safe_price - tick)

        amend_ok = manager.amend_order(
            symbol=symbol,
            order_id=order_id,
            price=amended_price,
        )
        if not amend_ok:
            failures.append(f"Amend order {order_id} failed")

        # === STEP 7: Verify amendment ===
        checked += 1
        time.sleep(0.5)
        open_orders = manager.get_open_orders(symbol=symbol)
        amended_order = next(
            (o for o in open_orders if o.order_id == order_id), None
        )
        if amended_order is None:
            failures.append(f"Order {order_id} disappeared after amend")
        elif (
            amended_order.price is not None
            and abs(amended_order.price - amended_price) > tick
        ):
            failures.append(
                f"Amend price mismatch: expected {amended_price}, "
                f"got {amended_order.price}"
            )

        # === STEP 8: Cancel order ===
        checked += 1
        cancel_ok = manager.cancel_order(symbol=symbol, order_id=order_id)
        if not cancel_ok:
            failures.append(f"Cancel order {order_id} failed")

        # === STEP 9: Verify cancellation ===
        checked += 1
        time.sleep(0.5)
        open_orders = manager.get_open_orders(symbol=symbol)
        still_there = any(o.order_id == order_id for o in open_orders)
        if still_there:
            failures.append(f"Order {order_id} still open after cancel")

    except Exception as e:
        failures.append(f"Unexpected: {type(e).__name__}: {e}")

    finally:
        _cleanup_smoke_orders(manager, symbol)

    return _result(checked, failures)


# ── Tier 2: Position Lifecycle (PL5) ────────────────────────────────


def run_position_lifecycle_smoke(play_id: str) -> dict:
    """Open minimum position, set TP/SL, close immediately.

    COSTS MONEY (~$0.01-0.02 in taker fees). Requires explicit --confirm.
    Uses smoke sub-account if available, otherwise main account.

    Returns:
        dict with keys: checked, failures, skipped, skip_reason, cost_usd
    """
    from src.backtest.play import load_play

    play = load_play(play_id)
    symbol = play.symbol_universe[0]

    manager, is_sub = _get_smoke_manager()
    account_label = "smoke sub-account" if is_sub else "main account"

    # Pre-check: sufficient balance
    try:
        balance = manager.get_balance()
        available = balance.get("available", 0.0)
        if available < MIN_BALANCE_FOR_POSITION_TEST:
            return {
                "checked": 0, "failures": [], "skipped": True,
                "skip_reason": (
                    f"{account_label} balance ${available:.2f} "
                    f"< ${MIN_BALANCE_FOR_POSITION_TEST:.2f} minimum"
                ),
                "cost_usd": 0.0,
            }
    except Exception as e:
        return {
            "checked": 0,
            "failures": [f"Balance check failed: {e}"],
            "skipped": False, "skip_reason": None, "cost_usd": 0.0,
        }

    failures: list[str] = []
    checked = 0
    cost_usd = 0.0

    try:
        # Step 1: Get price
        checked += 1
        market_price = manager.get_price(symbol)

        # Step 2: Calculate minimum viable size
        checked += 1
        min_qty = inst.get_min_qty(manager, symbol)
        min_usd = min_qty * market_price
        test_usd = max(min_usd * 1.1, 5.0)

        if test_usd > available * 0.5:
            return {
                "checked": checked, "failures": [], "skipped": True,
                "skip_reason": f"Test size ${test_usd:.2f} > 50% of available ${available:.2f}",
                "cost_usd": 0.0,
            }

        # Step 3: Open minimum long position
        checked += 1
        buy_result = manager.market_buy(symbol=symbol, usd_amount=test_usd)
        if not buy_result.success:
            failures.append(f"Market buy: {buy_result.error}")
            return {
                "checked": checked, "failures": failures,
                "skipped": False, "skip_reason": None, "cost_usd": 0.0,
            }

        # Step 4: Verify position exists
        checked += 1
        time.sleep(1.0)
        position = manager.get_position(symbol)
        if position is None:
            failures.append("Position not found after market buy")
        else:
            # Step 5: Set TP/SL
            checked += 1
            entry_price = position.entry_price or market_price
            tp_price = inst.round_price(manager, symbol, entry_price * 1.05)
            sl_price = inst.round_price(manager, symbol, entry_price * 0.95)

            try:
                from src.core import exchange_positions as pos
                pos.set_position_tpsl(
                    manager, symbol,
                    take_profit=tp_price,
                    stop_loss=sl_price,
                )
            except Exception as e:
                failures.append(f"Set TP/SL: {e}")

        # Step 6: Close position immediately
        checked += 1
        from src.core import exchange_orders_manage as manage
        close_ok = manage.close_position(manager, symbol)
        if not close_ok:
            failures.append("Close position failed")

        # Step 7: Verify position closed
        checked += 1
        time.sleep(1.0)
        position = manager.get_position(symbol)
        if position is not None and position.size and abs(position.size) > 0:
            failures.append(f"Position still open: size={position.size}")

        # Step 8: Estimate cost
        checked += 1
        taker_bps = 5.5  # Bybit non-VIP taker fee
        cost_usd = test_usd * (taker_bps / 10000) * 2  # entry + exit

    except Exception as e:
        failures.append(f"Position lifecycle: {type(e).__name__}: {e}")
    finally:
        # Emergency: ensure position is closed
        try:
            pos_check = manager.get_position(symbol)
            if pos_check is not None and pos_check.size and abs(pos_check.size) > 0:
                logger.warning("Emergency close of smoke position for %s", symbol)
                from src.core import exchange_orders_manage as manage
                manage.close_position(manager, symbol)
        except Exception:
            pass

    return {
        "checked": checked,
        "failures": failures,
        "skipped": False,
        "skip_reason": None,
        "cost_usd": cost_usd,
    }


# ── Sub-account setup ───────────────────────────────────────────────


def ensure_smoke_sub_account() -> dict:
    """Create the dedicated smoke test sub-account if it doesn't exist.

    Returns:
        dict with keys: created (bool), uid (int), funded (bool), error (str|None)
    """
    from src.tools.shared import _get_exchange_manager
    from src.core.sub_account_manager import SubAccountManager

    main_manager = _get_exchange_manager()
    sub_mgr = SubAccountManager(main_manager.bybit, main_uid=None)
    sub_mgr.load_state()

    # Check if already exists (look up by username)
    existing = next(
        (s for s in sub_mgr.list() if s.username == SMOKE_SUB_USERNAME),
        None,
    )
    if existing and existing.status == "active":
        return {
            "created": False,
            "uid": existing.uid,
            "funded": existing.funded_amount > 0,
            "error": None,
        }

    # Create new sub-account
    try:
        sub_info = sub_mgr.create(SMOKE_SUB_USERNAME)
        return {
            "created": True,
            "uid": sub_info.uid,
            "funded": False,
            "error": None,
        }
    except Exception as e:
        return {
            "created": False,
            "uid": 0,
            "funded": False,
            "error": str(e),
        }


# ── Internal helpers ────────────────────────────────────────────────


def _result(checked: int, failures: list[str]) -> dict:
    """Build standard result dict."""
    return {
        "checked": checked,
        "failures": failures,
        "skipped": False,
        "skip_reason": None,
    }
