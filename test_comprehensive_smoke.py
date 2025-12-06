#!/usr/bin/env python3
"""
Comprehensive Smoke Test for TRADE Bot - Bybit Unified Trading Account
=======================================================================

Tests ALL order tools and position management features.

Usage:
    python test_comprehensive_smoke.py

Features Tested:
1. Account & Balance
2. Leverage & Risk Configuration
3. Market Orders (Long/Short)
4. Position TP/SL Management
5. Trailing Stops
6. Limit Orders
7. Stop Orders (Conditional)
8. Order Management (Get/Cancel/Amend)
9. Partial Position Closes
10. Batch Orders
11. Panic Close All
"""

import sys
import time

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from src.tools import (
    # Account
    get_account_balance_tool,
    get_account_info_tool,
    get_portfolio_snapshot_tool,
    # Position tools
    list_open_positions_tool,
    get_position_detail_tool,
    set_stop_loss_tool,
    remove_stop_loss_tool,
    set_take_profit_tool,
    remove_take_profit_tool,
    set_trailing_stop_tool,
    set_trailing_stop_by_percent_tool,
    close_position_tool,
    panic_close_all_tool,
    # Order tools - Market
    set_leverage_tool,
    market_buy_tool,
    market_sell_tool,
    market_buy_with_tpsl_tool,
    market_sell_with_tpsl_tool,
    # Order tools - Limit
    limit_buy_tool,
    limit_sell_tool,
    partial_close_position_tool,
    # Order tools - Stop (conditional)
    stop_market_buy_tool,
    stop_market_sell_tool,
    stop_limit_buy_tool,
    stop_limit_sell_tool,
    # Order tools - Management
    get_open_orders_tool,
    cancel_order_tool,
    amend_order_tool,
    cancel_all_orders_tool,
    # Order tools - Batch
    batch_market_orders_tool,
    batch_limit_orders_tool,
    batch_cancel_orders_tool,
    # Market data
    get_price_tool,
)

# Configuration
SYMBOL = "SOLUSDT"
MARGIN_USD = 1000
LEVERAGE = 5


class TestRunner:
    """Clean test runner with formatted output."""
    
    def __init__(self):
        self.tests_passed = 0
        self.tests_failed = 0
        self.tests_warned = 0
        self.current_price = 0.0
        
    def header(self, title: str):
        """Print section header."""
        print()
        print("=" * 70)
        print(f"  {title}")
        print("=" * 70)
    
    def subheader(self, title: str):
        """Print subsection header."""
        print()
        print(f"--- {title} ---")
    
    def test(self, name: str, result, expect_success: bool = True, warn_on_fail: bool = False):
        """Record and display test result."""
        success = result.success if hasattr(result, 'success') else bool(result)
        
        if expect_success:
            if success:
                print(f"  [PASS] {name}")
                if hasattr(result, 'message') and result.message:
                    print(f"         -> {result.message}")
                self.tests_passed += 1
                return True
            elif warn_on_fail:
                print(f"  [WARN] {name}")
                if hasattr(result, 'error') and result.error:
                    print(f"         -> {result.error}")
                self.tests_warned += 1
                return False
            else:
                print(f"  [FAIL] {name}")
                if hasattr(result, 'error') and result.error:
                    print(f"         -> {result.error}")
                self.tests_failed += 1
                return False
        else:
            # Expecting failure (negative test)
            if not success:
                print(f"  [PASS] {name} (expected failure)")
                self.tests_passed += 1
                return True
            else:
                print(f"  [FAIL] {name} (expected failure but succeeded)")
                self.tests_failed += 1
                return False
    
    def wait(self, seconds: float = 1.0):
        """Wait between operations."""
        time.sleep(seconds)
    
    def get_current_price(self) -> float:
        """Get current price for calculations."""
        result = get_price_tool(SYMBOL)
        if result.success:
            self.current_price = result.data.get("price", 0)
        return self.current_price
    
    def ensure_no_position(self):
        """Make sure no position is open before starting."""
        result = list_open_positions_tool()
        if result.success:
            for pos in result.data.get("positions", []):
                if pos.get("symbol") == SYMBOL:
                    close_position_tool(SYMBOL)
                    self.wait()
    
    def summary(self):
        """Print final summary."""
        print()
        print("=" * 70)
        print("  TEST SUMMARY")
        print("=" * 70)
        total = self.tests_passed + self.tests_failed + self.tests_warned
        print(f"  Passed:  {self.tests_passed}/{total}")
        print(f"  Failed:  {self.tests_failed}/{total}")
        print(f"  Warned:  {self.tests_warned}/{total}")
        print("=" * 70)
        
        if self.tests_failed == 0:
            print("  ALL TESTS PASSED!")
        else:
            print(f"  {self.tests_failed} TEST(S) FAILED")
        print("=" * 70)


def run_tests():
    """Run all comprehensive tests."""
    
    t = TestRunner()
    
    # =========================================================================
    # SECTION 1: ACCOUNT & BALANCE
    # =========================================================================
    t.header("1. ACCOUNT & BALANCE")
    
    t.test("Get account balance", get_account_balance_tool())
    t.test("Get account info", get_account_info_tool())
    t.test("Get portfolio snapshot", get_portfolio_snapshot_tool())
    
    # =========================================================================
    # SECTION 2: MARKET DATA & SETUP
    # =========================================================================
    t.header("2. MARKET DATA & SETUP")
    
    price_result = get_price_tool(SYMBOL)
    t.test(f"Get {SYMBOL} price", price_result)
    
    if price_result.success:
        t.current_price = price_result.data.get("price", 0)
        print(f"         Current price: ${t.current_price:.4f}")
    else:
        print(f"  [FATAL] Cannot get price for {SYMBOL}")
        return
    
    t.test(f"Set leverage to {LEVERAGE}x", set_leverage_tool(SYMBOL, LEVERAGE), warn_on_fail=True)
    t.wait()
    
    # Clean up any existing position
    t.ensure_no_position()
    cancel_all_orders_tool(SYMBOL)
    t.wait()
    
    # =========================================================================
    # SECTION 3: MARKET ORDERS - LONG POSITION
    # =========================================================================
    t.header("3. MARKET ORDERS - LONG POSITION")
    
    # Open LONG position
    result = market_buy_tool(SYMBOL, MARGIN_USD)
    t.test(f"Market BUY ${MARGIN_USD} (open LONG)", result)
    
    if not result.success:
        print("  [FATAL] Cannot proceed without position")
        t.summary()
        return
    
    t.wait(2)
    
    # Verify position opened
    pos_result = get_position_detail_tool(SYMBOL)
    t.test("Verify LONG position opened", pos_result)
    if pos_result.success:
        pos = pos_result.data
        print(f"         Side: {pos.get('side', 'N/A')}, Size: {pos.get('size', 'N/A')}")
    
    t.wait()
    
    # =========================================================================
    # SECTION 4: TAKE PROFIT & STOP LOSS
    # =========================================================================
    t.header("4. TAKE PROFIT & STOP LOSS")
    
    price = t.get_current_price()
    tp_price = round(price * 1.05, 4)  # +5% take profit
    sl_price = round(price * 0.95, 4)  # -5% stop loss
    
    t.subheader("Set TP/SL")
    t.test(f"Set take profit @ ${tp_price:.4f}", set_take_profit_tool(SYMBOL, tp_price))
    t.wait()
    t.test(f"Set stop loss @ ${sl_price:.4f}", set_stop_loss_tool(SYMBOL, sl_price))
    t.wait()
    
    t.subheader("Verify TP/SL")
    pos_result = get_position_detail_tool(SYMBOL)
    if pos_result.success:
        tp = pos_result.data.get("take_profit", 0)
        sl = pos_result.data.get("stop_loss", 0)
        print(f"         TP: ${tp}, SL: ${sl}")
    
    t.subheader("Remove TP/SL")
    t.test("Remove take profit", remove_take_profit_tool(SYMBOL))
    t.wait()
    # Note: SL might already be cleared when TP was removed, so warn on fail
    t.test("Remove stop loss", remove_stop_loss_tool(SYMBOL), warn_on_fail=True)
    t.wait()
    
    # =========================================================================
    # SECTION 5: TRAILING STOPS
    # =========================================================================
    t.header("5. TRAILING STOPS")
    
    price = t.get_current_price()
    
    t.subheader("Set Trailing Stop by Callback Rate")
    # 3% callback rate
    t.test("Set trailing stop 3% callback", set_trailing_stop_by_percent_tool(SYMBOL, 3.0), warn_on_fail=True)
    t.wait()
    
    t.subheader("Verify Trailing Stop")
    pos_result = get_position_detail_tool(SYMBOL)
    if pos_result.success:
        ts = pos_result.data.get("trailing_stop")
        print(f"         Trailing Stop: {ts}")
    
    t.subheader("Set Trailing Stop by Distance")
    distance = round(price * 0.02, 4)  # $0.02 per unit distance
    t.test(f"Set trailing stop ${distance:.4f} distance", 
           set_trailing_stop_tool(SYMBOL, distance), warn_on_fail=True)
    t.wait()
    
    # Remove trailing stop (set to 0)
    t.test("Remove trailing stop", set_trailing_stop_tool(SYMBOL, 0), warn_on_fail=True)
    t.wait()
    
    # =========================================================================
    # SECTION 6: CLOSE LONG POSITION
    # =========================================================================
    t.header("6. CLOSE LONG POSITION")
    
    t.test("Close LONG position (market)", close_position_tool(SYMBOL))
    t.wait(2)
    
    # Verify closed
    pos_result = get_position_detail_tool(SYMBOL)
    if pos_result.success and pos_result.data.get("is_open"):
        t.tests_failed += 1
        print("  [FAIL] Position still open after close")
    else:
        print("  [PASS] Position confirmed closed")
        t.tests_passed += 1
    
    # =========================================================================
    # SECTION 7: MARKET ORDERS - SHORT POSITION
    # =========================================================================
    t.header("7. MARKET ORDERS - SHORT POSITION")
    
    result = market_sell_tool(SYMBOL, MARGIN_USD)
    t.test(f"Market SELL ${MARGIN_USD} (open SHORT)", result)
    
    if not result.success:
        print("  [FATAL] Cannot proceed without position")
        t.summary()
        return
    
    t.wait(2)
    
    # Verify SHORT position
    pos_result = get_position_detail_tool(SYMBOL)
    t.test("Verify SHORT position opened", pos_result)
    if pos_result.success:
        pos = pos_result.data
        print(f"         Side: {pos.get('side', 'N/A')}, Size: {pos.get('size', 'N/A')}")
    
    # Set TP/SL for SHORT (reversed directions)
    price = t.get_current_price()
    tp_price = round(price * 0.95, 4)  # -5% take profit (price falls)
    sl_price = round(price * 1.05, 4)  # +5% stop loss (price rises)
    
    t.test(f"Set SHORT take profit @ ${tp_price:.4f}", set_take_profit_tool(SYMBOL, tp_price))
    t.wait()
    t.test(f"Set SHORT stop loss @ ${sl_price:.4f}", set_stop_loss_tool(SYMBOL, sl_price))
    t.wait()
    
    # Close SHORT
    t.test("Close SHORT position", close_position_tool(SYMBOL))
    t.wait(2)
    
    # =========================================================================
    # SECTION 8: MARKET ORDERS WITH TP/SL
    # =========================================================================
    t.header("8. MARKET ORDERS WITH TP/SL")
    
    price = t.get_current_price()
    tp_price = round(price * 1.05, 4)
    sl_price = round(price * 0.95, 4)
    
    result = market_buy_with_tpsl_tool(SYMBOL, MARGIN_USD, take_profit=tp_price, stop_loss=sl_price)
    t.test(f"Market BUY with TP=${tp_price:.4f}, SL=${sl_price:.4f}", result)
    t.wait(2)
    
    # Verify TP/SL set
    pos_result = get_position_detail_tool(SYMBOL)
    if pos_result.success:
        tp = pos_result.data.get("take_profit", 0)
        sl = pos_result.data.get("stop_loss", 0)
        print(f"         TP: ${tp}, SL: ${sl}")
    
    # Close position
    close_position_tool(SYMBOL)
    t.wait(2)
    
    # =========================================================================
    # SECTION 9: LIMIT ORDERS
    # =========================================================================
    t.header("9. LIMIT ORDERS")
    
    price = t.get_current_price()
    buy_price = round(price * 0.95, 4)   # 5% below market (won't fill immediately)
    sell_price = round(price * 1.05, 4)  # 5% above market (won't fill immediately)
    
    t.subheader("Place Limit Orders")
    buy_result = limit_buy_tool(SYMBOL, MARGIN_USD / 2, buy_price)
    t.test(f"Limit BUY @ ${buy_price:.4f}", buy_result)
    t.wait()
    
    sell_result = limit_sell_tool(SYMBOL, MARGIN_USD / 2, sell_price)
    t.test(f"Limit SELL @ ${sell_price:.4f}", sell_result)
    t.wait()
    
    t.subheader("Query Open Orders")
    orders_result = get_open_orders_tool(SYMBOL)
    t.test("Get open orders", orders_result)
    if orders_result.success:
        count = orders_result.data.get("count", 0)
        print(f"         Found {count} open orders")
    t.wait()
    
    # Cancel specific order
    if buy_result.success:
        order_id = buy_result.data.get("order_id")
        if order_id:
            t.test(f"Cancel order {order_id[:12]}...", cancel_order_tool(SYMBOL, order_id=order_id))
            t.wait()
    
    # Cancel all remaining orders
    t.test("Cancel all orders", cancel_all_orders_tool(SYMBOL))
    t.wait()
    
    # =========================================================================
    # SECTION 10: STOP ORDERS (CONDITIONAL)
    # =========================================================================
    t.header("10. STOP ORDERS (CONDITIONAL)")
    
    price = t.get_current_price()
    trigger_above = round(price * 1.03, 4)  # Trigger when price rises 3%
    trigger_below = round(price * 0.97, 4)  # Trigger when price falls 3%
    limit_price = round(price * 0.96, 4)    # Limit price for stop-limit
    
    t.subheader("Stop Market Orders")
    # Stop market buy - triggers when price RISES to trigger (breakout entry)
    result = stop_market_buy_tool(SYMBOL, MARGIN_USD / 2, trigger_above, trigger_direction=1)
    t.test(f"Stop Market BUY trigger @ ${trigger_above:.4f} (rise)", result)
    t.wait()
    
    # Stop market sell - triggers when price FALLS to trigger (breakdown entry)
    result = stop_market_sell_tool(SYMBOL, MARGIN_USD / 2, trigger_below, trigger_direction=2)
    t.test(f"Stop Market SELL trigger @ ${trigger_below:.4f} (fall)", result)
    t.wait()
    
    t.subheader("Stop Limit Orders")
    # Stop limit buy - triggers limit order when price rises
    result = stop_limit_buy_tool(SYMBOL, MARGIN_USD / 4, trigger_above, trigger_above + 0.1, trigger_direction=1)
    t.test(f"Stop Limit BUY trigger @ ${trigger_above:.4f}", result)
    t.wait()
    
    # Stop limit sell - triggers limit order when price falls
    result = stop_limit_sell_tool(SYMBOL, MARGIN_USD / 4, trigger_below, trigger_below - 0.1, trigger_direction=2)
    t.test(f"Stop Limit SELL trigger @ ${trigger_below:.4f}", result)
    t.wait()
    
    t.subheader("Verify Conditional Orders")
    orders_result = get_open_orders_tool(SYMBOL)
    t.test("Get open conditional orders", orders_result)
    if orders_result.success:
        count = orders_result.data.get("count", 0)
        print(f"         Found {count} conditional orders")
    
    # Cancel all conditional orders
    t.test("Cancel all orders", cancel_all_orders_tool(SYMBOL))
    t.wait()
    
    # =========================================================================
    # SECTION 11: ORDER AMENDMENT
    # =========================================================================
    t.header("11. ORDER AMENDMENT")
    
    price = t.get_current_price()
    buy_price = round(price * 0.95, 4)
    new_price = round(price * 0.94, 4)
    
    # Place a limit order
    result = limit_buy_tool(SYMBOL, MARGIN_USD / 2, buy_price)
    t.test(f"Place limit order @ ${buy_price:.4f}", result)
    t.wait()
    
    if result.success:
        order_id = result.data.get("order_id")
        
        # Amend the order
        amend_result = amend_order_tool(SYMBOL, order_id=order_id, price=new_price)
        t.test(f"Amend order price to ${new_price:.4f}", amend_result, warn_on_fail=True)
        t.wait()
    
    # Cleanup
    cancel_all_orders_tool(SYMBOL)
    t.wait()
    
    # =========================================================================
    # SECTION 12: PARTIAL CLOSE
    # =========================================================================
    t.header("12. PARTIAL CLOSE")
    
    # Open position for partial close test
    result = market_buy_tool(SYMBOL, MARGIN_USD)
    t.test("Open position for partial close test", result)
    t.wait(2)
    
    if result.success:
        t.subheader("Partial Close - Market")
        # Close 50% at market
        t.test("Partial close 50% (market)", partial_close_position_tool(SYMBOL, 50.0))
        t.wait(2)
        
        # Verify remaining
        pos_result = get_position_detail_tool(SYMBOL)
        if pos_result.success:
            size = pos_result.data.get("size", 0)
            print(f"         Remaining size: {size}")
        
        t.subheader("Partial Close - Limit")
        price = t.get_current_price()
        limit_price = round(price * 1.001, 4)  # Slightly above market
        t.test(f"Partial close 25% @ ${limit_price:.4f} (limit)", 
               partial_close_position_tool(SYMBOL, 25.0, price=limit_price), warn_on_fail=True)
        t.wait()
        
        # Cancel any pending limit closes and close remaining
        cancel_all_orders_tool(SYMBOL)
        close_position_tool(SYMBOL)
        t.wait(2)
    
    # =========================================================================
    # SECTION 13: BATCH ORDERS
    # =========================================================================
    t.header("13. BATCH ORDERS")
    
    price = t.get_current_price()
    
    t.subheader("Batch Limit Orders")
    limit_orders = [
        {"symbol": SYMBOL, "side": "Buy", "usd_amount": 100, "price": round(price * 0.95, 4)},
        {"symbol": SYMBOL, "side": "Buy", "usd_amount": 100, "price": round(price * 0.94, 4)},
        {"symbol": SYMBOL, "side": "Sell", "usd_amount": 100, "price": round(price * 1.05, 4)},
    ]
    
    result = batch_limit_orders_tool(limit_orders)
    t.test(f"Batch place {len(limit_orders)} limit orders", result)
    t.wait()
    
    if result.success:
        success_count = result.data.get("success_count", 0)
        print(f"         Placed: {success_count}/{len(limit_orders)}")
    
    t.subheader("Verify Batch Orders")
    orders_result = get_open_orders_tool(SYMBOL)
    if orders_result.success:
        count = orders_result.data.get("count", 0)
        print(f"         Found {count} orders")
    
    # Cleanup batch orders
    t.test("Cancel all batch orders", cancel_all_orders_tool(SYMBOL))
    t.wait()
    
    # =========================================================================
    # SECTION 14: PANIC CLOSE ALL
    # =========================================================================
    t.header("14. PANIC CLOSE ALL")
    
    # Open a position for panic close test
    result = market_buy_tool(SYMBOL, MARGIN_USD / 2)
    t.test("Open position for panic close test", result)
    t.wait(2)
    
    if result.success:
        t.test("PANIC CLOSE ALL", panic_close_all_tool(reason="Smoke test"))
        t.wait(2)
        
        # Verify all closed
        pos_result = list_open_positions_tool()
        if pos_result.success:
            positions = pos_result.data.get("positions", [])
            if len(positions) == 0:
                print("  [PASS] All positions confirmed closed")
                t.tests_passed += 1
            else:
                print(f"  [FAIL] Still have {len(positions)} open positions")
                t.tests_failed += 1
    
    # =========================================================================
    # FINAL CLEANUP
    # =========================================================================
    t.header("FINAL CLEANUP")
    
    cancel_all_orders_tool(SYMBOL)
    t.ensure_no_position()
    print("  Cleanup complete")
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    t.summary()
    
    return t.tests_failed == 0


if __name__ == "__main__":
    print()
    print("=" * 70)
    print("  TRADE BOT - COMPREHENSIVE SMOKE TEST")
    print("  Bybit Unified Trading Account - All Order Types")
    print("=" * 70)
    print(f"  Symbol: {SYMBOL}")
    print(f"  Margin: ${MARGIN_USD}")
    print(f"  Leverage: {LEVERAGE}x")
    print("=" * 70)
    
    success = run_tests()
    sys.exit(0 if success else 1)

