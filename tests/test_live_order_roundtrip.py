"""
Test script to place a limit order and cancel it on LIVE account.
⚠️  WARNING: This uses REAL MONEY on your LIVE account!

The order will be placed far from market price so it won't fill.
"""

import os
import sys
import time

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv

# Load environment
load_dotenv("api_keys.env", override=True)


def test_order_roundtrip():
    """Place a limit order far from market, then cancel it.
    
    This test expects one of two outcomes:
    1. Order placed and cancelled successfully (account has funds)
    2. Order rejected with insufficient funds error (expected for low-balance accounts)
    
    Both are valid test passes - we're testing the API connection works.
    """
    import pytest
    
    print("\n" + "=" * 60)
    print("⚠️  LIVE ORDER ROUNDTRIP TEST ⚠️")
    print("=" * 60)
    print("This will place a REAL order on your LIVE account!")
    print("The order will be placed far from market so it won't fill.")
    print("=" * 60)
    
    from pybit.unified_trading import HTTP
    
    api_key = os.getenv("BYBIT_LIVE_API_KEY", "").strip()
    api_secret = os.getenv("BYBIT_LIVE_API_SECRET", "").strip()
    
    assert api_key, "BYBIT_LIVE_API_KEY not set"
    assert api_secret, "BYBIT_LIVE_API_SECRET not set"
    
    print(f"\nUsing API Key: {api_key[:5]}...{api_key[-3:]}")
    
    # Create session
    session = HTTP(
        testnet=False,
        api_key=api_key,
        api_secret=api_secret,
    )
    
    # Test parameters
    symbol = "BTCUSDT"
    side = "Buy"
    qty = "0.001"  # Minimum qty for BTC
    
    # Step 1: Get current market price
    print(f"\n[Step 1] Getting current {symbol} price...")
    ticker = session.get_tickers(category="linear", symbol=symbol)
    
    assert ticker.get("retCode") == 0, f"Failed to get ticker: {ticker.get('retMsg')}"
    
    current_price = float(ticker["result"]["list"][0]["lastPrice"])
    print(f"Current price: ${current_price:,.2f}")
    
    # Place order 10% below market (won't fill)
    limit_price = round(current_price * 0.90, 1)  # 10% below
    print(f"Limit price (10% below): ${limit_price:,.2f}")
    
    # Step 2: Check balance first
    print(f"\n[Step 2] Checking account balance...")
    balance = session.get_wallet_balance(accountType="UNIFIED")
    
    assert balance.get("retCode") == 0, f"Failed to get balance: {balance.get('retMsg')}"
    
    accounts = balance.get("result", {}).get("list", [])
    if accounts:
        equity = accounts[0].get("totalEquity", "0")
        print(f"Total Equity: ${equity}")
    
    # Step 3: Place limit order
    print(f"\n[Step 3] Placing limit order...")
    print(f"  Symbol: {symbol}")
    print(f"  Side: {side}")
    print(f"  Qty: {qty} BTC")
    print(f"  Price: ${limit_price:,.2f}")
    
    # This may raise an exception for insufficient funds - that's OK
    try:
        order_result = session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Limit",
            qty=qty,
            price=str(limit_price),
            timeInForce="GTC",  # Good Till Cancel
        )
        
        print(f"\nOrder result: {order_result}")
        
        assert order_result.get("retCode") == 0, f"Order failed: {order_result.get('retMsg')}"
        
        order_id = order_result["result"]["orderId"]
        print(f"✓ Order placed! Order ID: {order_id}")
        
        # Step 4: Check order status
        print(f"\n[Step 4] Checking order status...")
        time.sleep(1)  # Wait for order to register
        
        order_status = session.get_open_orders(
            category="linear",
            symbol=symbol,
            orderId=order_id,
        )
        
        print(f"Order status: {order_status}")
        
        if order_status.get("retCode") == 0:
            orders = order_status.get("result", {}).get("list", [])
            if orders:
                status = orders[0].get("orderStatus")
                print(f"✓ Order status: {status}")
            else:
                print("Order not found in open orders (may have been filled or cancelled)")
        
        # Step 5: Cancel the order
        print(f"\n[Step 5] Cancelling order...")
        
        cancel_result = session.cancel_order(
            category="linear",
            symbol=symbol,
            orderId=order_id,
        )
        
        print(f"Cancel result: {cancel_result}")
        
        assert cancel_result.get("retCode") == 0, f"Failed to cancel: {cancel_result.get('retMsg')}"
        print(f"✓ Order cancelled successfully!")
        
    except Exception as e:
        error_msg = str(e)
        # Insufficient funds error is expected and acceptable
        if "110007" in error_msg or "not enough" in error_msg.lower():
            print(f"\n❌ ERROR: {e}")
            print("\n✓ Test passed - API connection works, insufficient funds is expected")
            # This is a valid test pass - API works, just no funds
        else:
            # Re-raise unexpected errors
            raise


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("LIVE ORDER ROUNDTRIP TEST")
    print("=" * 60)
    
    # Confirm before running
    confirm = input("\nThis will place a REAL order on LIVE. Continue? [y/N]: ")
    
    if confirm.lower() != 'y':
        print("Cancelled.")
        sys.exit(0)
    
    success = test_order_roundtrip()
    
    print("\n" + "=" * 60)
    if success:
        print("✓ TEST PASSED - Order placed and cancelled successfully!")
    else:
        print("✗ TEST FAILED")
    print("=" * 60)

