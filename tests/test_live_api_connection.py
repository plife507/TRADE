"""
Test script to diagnose LIVE API connection issues.
Tests signature generation and authenticated endpoints.
"""

import os
import sys
import time
import hmac
import hashlib

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv

# Load environment
load_dotenv("api_keys.env", override=True)

def test_raw_signature():
    """Test signature generation manually."""
    print("\n=== Test 1: Raw Signature Generation ===")
    
    api_key = os.getenv("BYBIT_LIVE_API_KEY", "")
    api_secret = os.getenv("BYBIT_LIVE_API_SECRET", "")
    
    print(f"API Key length: {len(api_key)}")
    print(f"API Secret length: {len(api_secret)}")
    print(f"API Key: {api_key[:5]}...{api_key[-3:] if len(api_key) > 8 else ''}")
    
    # Check for whitespace issues
    if api_key != api_key.strip():
        print("WARNING: API key has leading/trailing whitespace!")
    if api_secret != api_secret.strip():
        print("WARNING: API secret has leading/trailing whitespace!")
    
    # Test signature generation
    timestamp = str(int(time.time() * 1000))
    recv_window = "20000"
    
    # For GET requests with no params
    param_str = ""
    sign_str = f"{timestamp}{api_key}{recv_window}{param_str}"
    
    print(f"\nSign string: {sign_str}")
    
    signature = hmac.new(
        api_secret.encode('utf-8'),
        sign_str.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    print(f"Generated signature: {signature}")
    return True


def test_pybit_direct():
    """Test using pybit directly."""
    print("\n=== Test 2: Direct pybit Connection ===")
    
    try:
        from pybit.unified_trading import HTTP
        
        api_key = os.getenv("BYBIT_LIVE_API_KEY", "").strip()
        api_secret = os.getenv("BYBIT_LIVE_API_SECRET", "").strip()
        
        print(f"Using API Key: {api_key[:5]}...{api_key[-3:]}")
        print(f"Secret length: {len(api_secret)}")
        
        # Create session
        session = HTTP(
            testnet=False,  # LIVE
            api_key=api_key,
            api_secret=api_secret,
        )
        
        # Test public endpoint first
        print("\nTesting public endpoint (server time)...")
        server_time = session.get_server_time()
        print(f"Server time: {server_time}")
        
        # Test authenticated endpoint
        print("\nTesting authenticated endpoint (wallet balance)...")
        balance = session.get_wallet_balance(accountType="UNIFIED")
        
        if balance.get("retCode") == 0:
            print("SUCCESS: Wallet balance retrieved!")
            result = balance.get("result", {})
            accounts = result.get("list", [])
            if accounts:
                total_equity = accounts[0].get("totalEquity", "N/A")
                print(f"Total Equity: ${total_equity}")
            return True
        else:
            print(f"FAILED: {balance.get('retMsg')}")
            print(f"Full response: {balance}")
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_with_stripped_keys():
    """Test with explicitly stripped keys."""
    print("\n=== Test 3: Stripped Keys Test ===")
    
    try:
        from pybit.unified_trading import HTTP
        
        # Get and strip keys
        api_key = os.getenv("BYBIT_LIVE_API_KEY", "")
        api_secret = os.getenv("BYBIT_LIVE_API_SECRET", "")
        
        # Strip all whitespace
        api_key_clean = api_key.strip().replace(" ", "").replace("\t", "").replace("\n", "")
        api_secret_clean = api_secret.strip().replace(" ", "").replace("\t", "").replace("\n", "")
        
        print(f"Original key length: {len(api_key)}, Cleaned: {len(api_key_clean)}")
        print(f"Original secret length: {len(api_secret)}, Cleaned: {len(api_secret_clean)}")
        
        if len(api_key) != len(api_key_clean):
            print("WARNING: Key had hidden whitespace characters!")
        if len(api_secret) != len(api_secret_clean):
            print("WARNING: Secret had hidden whitespace characters!")
        
        session = HTTP(
            testnet=False,
            api_key=api_key_clean,
            api_secret=api_secret_clean,
        )
        
        print("\nTesting with cleaned keys...")
        balance = session.get_wallet_balance(accountType="UNIFIED")
        
        if balance.get("retCode") == 0:
            print("SUCCESS with cleaned keys!")
            return True
        else:
            print(f"Still FAILED: {balance.get('retMsg')}")
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def test_key_permissions():
    """Check if key has correct permissions by trying different endpoints."""
    print("\n=== Test 4: Key Permissions Check ===")
    
    try:
        from pybit.unified_trading import HTTP
        
        api_key = os.getenv("BYBIT_LIVE_API_KEY", "").strip()
        api_secret = os.getenv("BYBIT_LIVE_API_SECRET", "").strip()
        
        session = HTTP(
            testnet=False,
            api_key=api_key,
            api_secret=api_secret,
        )
        
        # Test API key info endpoint
        print("Checking API key info...")
        try:
            key_info = session.get_api_key_information()
            print(f"API Key Info: {key_info}")
            if key_info.get("retCode") == 0:
                result = key_info.get("result", {})
                print(f"  Permissions: {result.get('permissions', {})}")
                print(f"  Read-only: {result.get('readOnly')}")
                return True
        except Exception as e:
            print(f"  Failed to get key info: {e}")
        
        return False
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def print_env_debug():
    """Print environment variable debug info."""
    print("\n=== Environment Debug ===")
    
    keys_to_check = [
        "BYBIT_LIVE_API_KEY",
        "BYBIT_LIVE_API_SECRET",
        "BYBIT_LIVE_DATA_API_KEY",
        "BYBIT_LIVE_DATA_API_SECRET",
    ]
    
    for key in keys_to_check:
        value = os.getenv(key, "")
        if value:
            # Show length and first/last chars (safe)
            print(f"{key}: length={len(value)}, value={value[:5]}...{value[-3:] if len(value) > 8 else ''}")
        else:
            print(f"{key}: NOT SET")


if __name__ == "__main__":
    print("=" * 60)
    print("LIVE API Connection Diagnostic")
    print("=" * 60)
    
    print_env_debug()
    
    tests = [
        ("Raw Signature", test_raw_signature),
        ("Direct pybit", test_pybit_direct),
        ("Stripped Keys", test_with_stripped_keys),
        ("Key Permissions", test_key_permissions),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n{name} crashed: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("RESULTS:")
    print("=" * 60)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")

