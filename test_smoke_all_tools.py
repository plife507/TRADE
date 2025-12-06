#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive smoke test for all position and order tools with SOLUSDT.

Tests all Unified Trading Account operations:
- Order execution (market buy/sell)
- Position management (TP/SL, trailing stops, close)
- Position configuration (risk limits, margin mode, TP/SL mode)
- Account operations (balance, transaction log, collateral)
"""

import sys
import time
import io

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
from src.tools import (
    # Order tools
    set_leverage_tool,
    market_buy_tool,
    market_sell_tool,
    market_buy_with_tpsl_tool,
    market_sell_with_tpsl_tool,
    limit_buy_tool,
    limit_sell_tool,
    partial_close_position_tool,
    cancel_all_orders_tool,
    
    # Position tools
    list_open_positions_tool,
    get_position_detail_tool,
    set_stop_loss_tool,
    remove_stop_loss_tool,
    set_take_profit_tool,
    set_position_tpsl_tool,
    set_trailing_stop_tool,
    set_trailing_stop_by_percent_tool,
    close_position_tool,
    panic_close_all_tool,
    
    # Position configuration tools
    set_risk_limit_tool,
    get_risk_limits_tool,
    set_tp_sl_mode_tool,
    set_auto_add_margin_tool,
    modify_position_margin_tool,
    switch_margin_mode_tool,
    switch_position_mode_tool,
    
    # Account tools
    get_account_balance_tool,
    get_transaction_log_tool,
    get_closed_pnl_tool,
    get_collateral_info_tool,
    get_transferable_amount_tool,
    
    # Market data tools
    get_price_tool,
)

from src.config import get_config


def print_test(name: str):
    """Print test section header."""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print('='*60)


def print_result(result, label: str = ""):
    """Print tool result."""
    status = "[OK]" if result.success else "[FAIL]"
    print(f"{status} {label}: {result.message}")
    if result.error:
        print(f"  Error: {result.error}")
    if result.data and isinstance(result.data, dict):
        # Print key metrics
        if "positions" in result.data:
            print(f"  Positions: {len(result.data['positions'])}")
        if "count" in result.data:
            print(f"  Count: {result.data['count']}")


def wait_for_position(symbol: str, max_wait: int = 10) -> bool:
    """Wait for position to appear."""
    for _ in range(max_wait):
        result = list_open_positions_tool(symbol)
        if result.success and result.data:
            positions = result.data.get("positions", [])
            if any(p.get("symbol") == symbol for p in positions):
                return True
        time.sleep(1)
    return False


def get_current_price(symbol: str) -> float:
    """Get current price for a symbol."""
    result = get_price_tool(symbol)
    if result.success and result.data:
        return float(result.data.get("price", 0))
    return 0.0


def calculate_tp_sl_prices(entry_price: float, tp_percent: float, sl_percent: float, is_long: bool = True) -> tuple:
    """Calculate TP and SL prices from percentages."""
    if is_long:
        tp_price = entry_price * (1 + tp_percent / 100)
        sl_price = entry_price * (1 - sl_percent / 100)
    else:
        tp_price = entry_price * (1 - tp_percent / 100)
        sl_price = entry_price * (1 + sl_percent / 100)
    return tp_price, sl_price


def main():
    """Run comprehensive smoke tests."""
    config = get_config()
    
    print("\n" + "="*60)
    print("COMPREHENSIVE SMOKE TEST - ALL POSITION & ORDER TOOLS")
    print("="*60)
    print(f"Environment: {config.summary_short()}")
    
    # Safety check
    if config.bybit.is_live:
        print("\n[WARNING] Running in LIVE mode!")
        response = input("Continue? (yes/no): ")
        if response.lower() != "yes":
            print("Aborted.")
            return
    
    symbol = "SOLUSDT"
    amount = 1000.0  # USD notional
    
    print(f"\nTesting with: {symbol} @ ${amount} notional")
    print("="*60)
    
    # ========================================================================
    # TEST 1: Account & Balance Tools
    # ========================================================================
    print_test("Account & Balance Tools")
    
    result = get_account_balance_tool()
    print_result(result, "Account Balance")
    
    result = get_collateral_info_tool()
    print_result(result, "Collateral Info")
    
    result = get_transferable_amount_tool("USDT")
    print_result(result, "Transferable Amount (USDT)")
    
    # ========================================================================
    # TEST 2: Position Configuration (Before Opening Positions)
    # ========================================================================
    print_test("Position Configuration Tools")
    
    # Get risk limits
    result = get_risk_limits_tool(symbol)
    print_result(result, "Get Risk Limits")
    risk_id = None
    if result.success and result.data:
        risk_limits = result.data.get("risk_limits", [])
        if risk_limits:
            risk_id = risk_limits[0].get("id")
            print(f"  Using Risk ID: {risk_id}")
    
    # Set leverage
    result = set_leverage_tool(symbol, 2)
    print_result(result, "Set Leverage (2x)")
    
    # Switch to cross margin (may not be supported in demo)
    result = switch_margin_mode_tool(symbol, isolated=False, leverage=2)
    if "not supported" in result.error.lower() if result.error else "":
        print(f"  [WARN] Cross margin switch not supported in demo (expected)")
    else:
        print_result(result, "Switch to Cross Margin")
    
    # Set TP/SL mode to Full (may already be set)
    result = set_tp_sl_mode_tool(symbol, full_mode=True)
    if "same tp sl mode" in result.error.lower() if result.error else "":
        print(f"  [WARN] TP/SL mode already set (expected)")
    else:
        print_result(result, "Set TP/SL Mode (Full)")
    
    # Disable auto-add margin (may not be supported in demo)
    result = set_auto_add_margin_tool(symbol, enabled=False)
    if "not modified" in result.error.lower() if result.error else "":
        print(f"  [WARN] Auto-add margin already disabled (expected)")
    else:
        print_result(result, "Disable Auto-Add Margin")
    
    # ========================================================================
    # TEST 3: Market Buy (LONG Position)
    # ========================================================================
    print_test("Market Buy - Open LONG Position")
    
    result = market_buy_tool(symbol, amount)
    print_result(result, f"Market Buy ${amount}")
    
    if not result.success:
        print("  [WARN] Buy failed, skipping position tests")
        return
    
    # Wait for position
    print("\n  Waiting for position to appear...")
    if wait_for_position(symbol):
        print("  ✓ Position detected")
    else:
        print("  [WARN] Position not detected, continuing anyway...")
    
    # List positions
    result = list_open_positions_tool(symbol)
    print_result(result, "List Open Positions")
    
    # Get position detail
    result = get_position_detail_tool(symbol)
    print_result(result, "Get Position Detail")
    
    # ========================================================================
    # TEST 4: Position Management (LONG)
    # ========================================================================
    print_test("Position Management - LONG")
    
    # Get current price and position entry
    current_price = get_current_price(symbol)
    result = get_position_detail_tool(symbol)
    entry_price = current_price
    if result.success and result.data:
        pos_data = result.data.get("position", {})
        entry_price = float(pos_data.get("entry_price", current_price))
    
    # Calculate TP/SL prices (1% each)
    tp_price, sl_price = calculate_tp_sl_prices(entry_price, 1.0, 1.0, is_long=True)
    
    # Set TP/SL together
    result = set_position_tpsl_tool(symbol, take_profit=tp_price, stop_loss=sl_price)
    print_result(result, f"Set TP/SL Together (TP: ${tp_price:.2f}, SL: ${sl_price:.2f})")
    
    # Set trailing stop by percent
    result = set_trailing_stop_by_percent_tool(symbol, percent=0.8)
    print_result(result, "Set Trailing Stop (0.8%)")
    
    # Set trailing stop by distance
    trailing_dist = current_price * 0.01  # 1% of price
    result = set_trailing_stop_tool(symbol, trailing_distance=trailing_dist)
    print_result(result, f"Set Trailing Stop (${trailing_dist:.2f})")
    
    # Modify margin (add $10)
    result = modify_position_margin_tool(symbol, 10.0)
    print_result(result, "Add Margin (+$10)")
    
    # Modify margin (reduce $5)
    result = modify_position_margin_tool(symbol, -5.0)
    print_result(result, "Reduce Margin (-$5)")
    
    # Set individual TP (2%)
    tp_price_2, _ = calculate_tp_sl_prices(entry_price, 2.0, 0, is_long=True)
    result = set_take_profit_tool(symbol, take_profit_price=tp_price_2)
    print_result(result, f"Set Take Profit (${tp_price_2:.2f})")
    
    # Set individual SL (1.5%)
    _, sl_price_15 = calculate_tp_sl_prices(entry_price, 0, 1.5, is_long=True)
    result = set_stop_loss_tool(symbol, stop_price=sl_price_15)
    print_result(result, f"Set Stop Loss (${sl_price_15:.2f})")
    
    # ========================================================================
    # TEST 5: Close LONG Position
    # ========================================================================
    print_test("Close LONG Position")
    
    result = close_position_tool(symbol)
    print_result(result, "Close Position")
    
    # Verify closed
    result = list_open_positions_tool(symbol)
    print_result(result, "List Positions (should be empty)")
    
    # ========================================================================
    # TEST 6: Market Sell (SHORT Position)
    # ========================================================================
    print_test("Market Sell - Open SHORT Position")
    
    result = market_sell_tool(symbol, amount)
    print_result(result, f"Market Sell ${amount}")
    
    if not result.success:
        print("  [WARN] Sell failed, skipping short position tests")
        return
    
    # Wait for position
    print("\n  Waiting for position to appear...")
    if wait_for_position(symbol):
        print("  ✓ Position detected")
    
    # List positions
    result = list_open_positions_tool(symbol)
    print_result(result, "List Open Positions")
    
    # ========================================================================
    # TEST 7: Position Management (SHORT)
    # ========================================================================
    print_test("Position Management - SHORT")
    
    # Get current price and position entry
    current_price = get_current_price(symbol)
    result = get_position_detail_tool(symbol)
    entry_price = current_price
    if result.success and result.data:
        pos_data = result.data.get("position", {})
        entry_price = float(pos_data.get("entry_price", current_price))
    
    # Calculate TP/SL prices (1% each for SHORT)
    tp_price, sl_price = calculate_tp_sl_prices(entry_price, 1.0, 1.0, is_long=False)
    
    # Set TP/SL
    result = set_position_tpsl_tool(symbol, take_profit=tp_price, stop_loss=sl_price)
    print_result(result, f"Set TP/SL Together (TP: ${tp_price:.2f}, SL: ${sl_price:.2f})")
    
    # Set trailing stop
    result = set_trailing_stop_by_percent_tool(symbol, percent=0.8)
    print_result(result, "Set Trailing Stop (0.8%)")
    
    # Switch to isolated margin (may not be supported in demo)
    result = switch_margin_mode_tool(symbol, isolated=True, leverage=2)
    if "not supported" in result.error.lower() if result.error else "":
        print(f"  [WARN] Isolated margin switch not supported in demo (expected)")
    else:
        print_result(result, "Switch to Isolated Margin")
    
    # Enable auto-add margin (may not be supported in demo)
    result = set_auto_add_margin_tool(symbol, enabled=True)
    if "not modified" in result.error.lower() if result.error else "":
        print(f"  [WARN] Auto-add margin already enabled or not supported (expected)")
    else:
        print_result(result, "Enable Auto-Add Margin")
    
    # Set risk limit (if we got one earlier)
    if risk_id:
        result = set_risk_limit_tool(symbol, risk_id)
        print_result(result, f"Set Risk Limit (ID: {risk_id})")
    
    # ========================================================================
    # TEST 8: Market Buy/Sell with TP/SL
    # ========================================================================
    print_test("Market Orders with TP/SL")
    
    # Close current position first
    close_position_tool(symbol)
    time.sleep(2)
    
    # Get current price for TP/SL calculation
    current_price = get_current_price(symbol)
    tp_price, sl_price = calculate_tp_sl_prices(current_price, 1.5, 1.0, is_long=True)
    
    # Buy with TP/SL
    result = market_buy_with_tpsl_tool(
        symbol, 
        usd_amount=amount,
        take_profit=tp_price,
        stop_loss=sl_price
    )
    print_result(result, f"Market Buy with TP/SL (TP: ${tp_price:.2f}, SL: ${sl_price:.2f})")
    
    if result.success:
        time.sleep(2)
        close_position_tool(symbol)
        time.sleep(2)
    
    # Calculate TP/SL for SHORT
    tp_price_short, sl_price_short = calculate_tp_sl_prices(current_price, 1.5, 1.0, is_long=False)
    
    # Sell with TP/SL
    result = market_sell_with_tpsl_tool(
        symbol,
        usd_amount=amount,
        take_profit=tp_price_short,
        stop_loss=sl_price_short
    )
    print_result(result, f"Market Sell with TP/SL (TP: ${tp_price_short:.2f}, SL: ${sl_price_short:.2f})")
    
    if result.success:
        time.sleep(2)
        close_position_tool(symbol)
    
    # ========================================================================
    # TEST 9: Comprehensive Trailing Stop Tests
    # ========================================================================
    print_test("Trailing Stop - Comprehensive Tests")
    
    # Close any existing position first
    close_position_tool(symbol)
    time.sleep(2)
    
    # Get current price
    current_price = get_current_price(symbol)
    
    # ===== LONG Position Trailing Stops =====
    print("\n  --- LONG Position Trailing Stops ---")
    
    # Open LONG position
    result = market_buy_tool(symbol, amount)
    print_result(result, "Open LONG for trailing stop test")
    
    if result.success:
        time.sleep(2)
        
        # Test 1: Trailing stop by percentage (small - tight)
        result = set_trailing_stop_by_percent_tool(symbol, percent=0.5)
        print_result(result, "Trailing Stop 0.5% (tight)")
        time.sleep(1)
        
        # Test 2: Trailing stop by percentage (medium)
        result = set_trailing_stop_by_percent_tool(symbol, percent=1.0)
        print_result(result, "Trailing Stop 1.0% (medium)")
        time.sleep(1)
        
        # Test 3: Trailing stop by percentage (wide)
        result = set_trailing_stop_by_percent_tool(symbol, percent=2.0)
        print_result(result, "Trailing Stop 2.0% (wide)")
        time.sleep(1)
        
        # Test 4: Trailing stop by distance (small)
        trailing_dist_small = current_price * 0.005  # 0.5% of price
        result = set_trailing_stop_tool(symbol, trailing_distance=trailing_dist_small)
        print_result(result, f"Trailing Stop ${trailing_dist_small:.2f} distance (small)")
        time.sleep(1)
        
        # Test 5: Trailing stop by distance (medium)
        trailing_dist_medium = current_price * 0.01  # 1% of price
        result = set_trailing_stop_tool(symbol, trailing_distance=trailing_dist_medium)
        print_result(result, f"Trailing Stop ${trailing_dist_medium:.2f} distance (medium)")
        time.sleep(1)
        
        # Test 6: Trailing stop by distance (large)
        trailing_dist_large = current_price * 0.02  # 2% of price
        result = set_trailing_stop_tool(symbol, trailing_distance=trailing_dist_large)
        print_result(result, f"Trailing Stop ${trailing_dist_large:.2f} distance (large)")
        time.sleep(1)
        
        # Test 7: Trailing stop with active price (only activates above price)
        active_price = current_price * 1.01  # 1% above current
        result = set_trailing_stop_tool(symbol, trailing_distance=trailing_dist_medium, active_price=active_price)
        print_result(result, f"Trailing Stop with active price ${active_price:.2f}")
        time.sleep(1)
        
        # Verify position still has trailing stop
        result = get_position_detail_tool(symbol)
        if result.success and result.data:
            pos_data = result.data.get("position", {})
            trailing_stop = pos_data.get("trailing_stop", None)
            if trailing_stop:
                print(f"  [OK] Trailing stop active: {trailing_stop}")
            else:
                print(f"  [INFO] Trailing stop status: {pos_data.get('stop_loss', 'Not set')}")
        
        # Close LONG position
        close_position_tool(symbol)
        time.sleep(2)
    
    # ===== SHORT Position Trailing Stops =====
    print("\n  --- SHORT Position Trailing Stops ---")
    
    # Open SHORT position
    result = market_sell_tool(symbol, amount)
    print_result(result, "Open SHORT for trailing stop test")
    
    if result.success:
        time.sleep(2)
        
        # Test 8: Trailing stop by percentage for SHORT
        result = set_trailing_stop_by_percent_tool(symbol, percent=0.8)
        print_result(result, "Trailing Stop 0.8% (SHORT)")
        time.sleep(1)
        
        # Test 9: Trailing stop by distance for SHORT
        trailing_dist = current_price * 0.015  # 1.5% of price
        result = set_trailing_stop_tool(symbol, trailing_distance=trailing_dist)
        print_result(result, f"Trailing Stop ${trailing_dist:.2f} distance (SHORT)")
        time.sleep(1)
        
        # Test 10: Update trailing stop (change distance)
        trailing_dist_new = current_price * 0.01  # 1% of price
        result = set_trailing_stop_tool(symbol, trailing_distance=trailing_dist_new)
        print_result(result, f"Update Trailing Stop to ${trailing_dist_new:.2f}")
        time.sleep(1)
        
        # Test 11: Update trailing stop (change percentage)
        result = set_trailing_stop_by_percent_tool(symbol, percent=1.5)
        print_result(result, "Update Trailing Stop to 1.5%")
        time.sleep(1)
        
        # Verify position still has trailing stop
        result = get_position_detail_tool(symbol)
        if result.success and result.data:
            pos_data = result.data.get("position", {})
            trailing_stop = pos_data.get("trailing_stop", None)
            if trailing_stop:
                print(f"  [OK] Trailing stop active: {trailing_stop}")
        
        # Close SHORT position
        close_position_tool(symbol)
        time.sleep(2)
    
    # ===== Trailing Stop with TP/SL Combination =====
    print("\n  --- Trailing Stop + TP/SL Combination ---")
    
    # Open position
    result = market_buy_tool(symbol, amount)
    print_result(result, "Open position for trailing + TP/SL test")
    
    if result.success:
        time.sleep(2)
        
        # Set TP/SL first
        entry_price = get_current_price(symbol)
        tp_price, sl_price = calculate_tp_sl_prices(entry_price, 2.0, 1.5, is_long=True)
        result = set_position_tpsl_tool(symbol, take_profit=tp_price, stop_loss=sl_price)
        print_result(result, "Set TP/SL first")
        time.sleep(1)
        
        # Then add trailing stop
        result = set_trailing_stop_by_percent_tool(symbol, percent=1.0)
        print_result(result, "Add Trailing Stop 1.0% (with existing TP/SL)")
        time.sleep(1)
        
        # Verify all are set
        result = get_position_detail_tool(symbol)
        if result.success and result.data:
            pos_data = result.data.get("position", {})
            print(f"  [INFO] TP: ${pos_data.get('take_profit', 0):.2f}, "
                  f"SL: ${pos_data.get('stop_loss', 0):.2f}, "
                  f"Trailing: {pos_data.get('trailing_stop', 'N/A')}")
        
        # Close position
        close_position_tool(symbol)
        time.sleep(2)
    
    # ===== Remove Trailing Stop =====
    print("\n  --- Remove Trailing Stop ---")
    
    # Open position
    result = market_buy_tool(symbol, amount)
    print_result(result, "Open position for remove trailing test")
    
    if result.success:
        time.sleep(2)
        
        # Set trailing stop
        result = set_trailing_stop_by_percent_tool(symbol, percent=1.0)
        print_result(result, "Set Trailing Stop 1.0%")
        time.sleep(1)
        
        # Remove trailing stop by removing stop loss
        # Note: In Bybit, removing stop loss also removes trailing stop
        result = remove_stop_loss_tool(symbol)
        print_result(result, "Remove SL/Trailing Stop")
        time.sleep(1)
        
        # Close position
        close_position_tool(symbol)
        time.sleep(2)
    
    print("\n  [OK] All trailing stop tests completed")
    
    # ========================================================================
    # TEST 10: Limit Orders
    # ========================================================================
    print_test("Limit Orders")
    
    # Close any existing position first
    close_position_tool(symbol)
    time.sleep(2)
    
    # Get current price
    current_price = get_current_price(symbol)
    
    # Place limit buy order (below market)
    limit_buy_price = current_price * 0.99  # 1% below market
    result = limit_buy_tool(symbol, amount, limit_buy_price, time_in_force="GTC")
    print_result(result, f"Limit Buy Order @ ${limit_buy_price:.2f}")
    
    if result.success:
        # Cancel the limit order
        time.sleep(1)
        result = cancel_all_orders_tool(symbol)
        print_result(result, "Cancel Limit Buy Order")
        time.sleep(1)
    
    # Place limit sell order (above market) - for opening short
    limit_sell_price = current_price * 1.01  # 1% above market
    result = limit_sell_tool(symbol, amount, limit_sell_price, time_in_force="GTC")
    print_result(result, f"Limit Sell Order @ ${limit_sell_price:.2f}")
    
    if result.success:
        # Cancel the limit order
        time.sleep(1)
        result = cancel_all_orders_tool(symbol)
        print_result(result, "Cancel Limit Sell Order")
        time.sleep(1)
    
    # ========================================================================
    # TEST 11: Partial Close Positions
    # ========================================================================
    print_test("Partial Close Positions")
    
    # Open a position first
    result = market_buy_tool(symbol, amount)
    print_result(result, f"Open LONG position for partial close test")
    
    if result.success:
        time.sleep(2)
        
        # Get position before partial close
        result = get_position_detail_tool(symbol)
        if result.success and result.data:
            pos_before = result.data.get("position", {})
            size_before = float(pos_before.get("size_usd", 0))
            print(f"  Position size before: ${size_before:.2f}")
        
        # Partial close 50% with market order
        result = partial_close_position_tool(symbol, close_percent=50.0)
        print_result(result, "Partial Close 50% (Market)")
        
        if result.success:
            time.sleep(2)
            
            # Get position after partial close
            result = get_position_detail_tool(symbol)
            if result.success and result.data:
                pos_after = result.data.get("position", {})
                size_after = float(pos_after.get("size_usd", 0))
                print(f"  Position size after: ${size_after:.2f}")
            
            # Partial close 30% with limit order
            current_price = get_current_price(symbol)
            limit_close_price = current_price * 1.005  # 0.5% above current
            result = partial_close_position_tool(symbol, close_percent=30.0, price=limit_close_price)
            print_result(result, f"Partial Close 30% (Limit @ ${limit_close_price:.2f})")
            
            if result.success:
                time.sleep(1)
                # Cancel the limit order if still open
                cancel_all_orders_tool(symbol)
        
        # Close remaining position
        time.sleep(1)
        close_position_tool(symbol)
        time.sleep(2)
    
    # Test partial close on SHORT position
    result = market_sell_tool(symbol, amount)
    print_result(result, f"Open SHORT position for partial close test")
    
    if result.success:
        time.sleep(2)
        
        # Partial close 40% with market order
        result = partial_close_position_tool(symbol, close_percent=40.0)
        print_result(result, "Partial Close 40% SHORT (Market)")
        
        # Close remaining position
        time.sleep(1)
        close_position_tool(symbol)
        time.sleep(2)
    
    # ========================================================================
    # TEST 12: Multiple Partial Closes (Scaling Out)
    # ========================================================================
    print_test("Multiple Partial Closes (Scaling Out)")
    
    # Open a larger position
    large_amount = amount * 2  # $2000
    result = market_buy_tool(symbol, large_amount)
    print_result(result, f"Open large LONG position (${large_amount})")
    
    if result.success:
        time.sleep(2)
        
        # Scale out in multiple steps
        close_percentages = [25, 25, 30]  # Total 80%
        
        for i, pct in enumerate(close_percentages, 1):
            result = partial_close_position_tool(symbol, close_percent=pct)
            print_result(result, f"Scale Out #{i}: Close {pct}%")
            time.sleep(2)
        
        # Get final position size
        result = get_position_detail_tool(symbol)
        if result.success and result.data:
            pos_final = result.data.get("position", {})
            size_final = float(pos_final.get("size_usd", 0))
            print(f"  Final position size: ${size_final:.2f} (should be ~20% of original)")
        
        # Close remaining position
        close_position_tool(symbol)
        time.sleep(2)
    
    # ========================================================================
    # TEST 13: Cancel All Orders
    # ========================================================================
    print_test("Cancel All Orders")
    
    result = cancel_all_orders_tool()
    print_result(result, "Cancel All Orders")
    
    # ========================================================================
    # TEST 14: Position Mode Switching
    # ========================================================================
    print_test("Position Mode Configuration")
    
    # Switch to one-way mode
    result = switch_position_mode_tool(hedge_mode=False)
    print_result(result, "Switch to One-Way Mode")
    
    # Switch to hedge mode
    result = switch_position_mode_tool(hedge_mode=True)
    print_result(result, "Switch to Hedge Mode")
    
    # ========================================================================
    # TEST 15: Transaction Log & Closed PnL
    # ========================================================================
    print_test("Transaction Log & Closed PnL")
    
    result = get_transaction_log_tool(limit=10)
    print_result(result, "Transaction Log")
    
    result = get_closed_pnl_tool(symbol=symbol, limit=10)
    print_result(result, "Closed PnL")
    
    # ========================================================================
    # TEST 16: Panic Close (Final Cleanup)
    # ========================================================================
    print_test("Panic Close All (Final Cleanup)")
    
    result = panic_close_all_tool(reason="Smoke test cleanup")
    print_result(result, "Panic Close All")
    
    # ========================================================================
    # SUMMARY
    # ========================================================================
    print("\n" + "="*60)
    print("SMOKE TEST COMPLETE")
    print("="*60)
    print("\nAll position and order tools have been tested.")
    print("Check the results above for any failures ([FAIL]).")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[WARNING] Test interrupted by user")
        print("Running panic close...")
        panic_close_all_tool(reason="Test interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[FAIL] Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        print("\nRunning panic close...")
        panic_close_all_tool(reason="Test error")
        sys.exit(1)

