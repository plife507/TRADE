#!/usr/bin/env python3
"""
Tests for strict trading mode to API environment mapping.

Canonical Contract:
- PAPER mode MUST use DEMO API (BYBIT_USE_DEMO=true)
- REAL mode MUST use LIVE API (BYBIT_USE_DEMO=false)
- Any other combination is INVALID and must be rejected

These tests ensure the safety guardrails prevent misconfiguration.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config.config import Config, get_config, TradingMode


def reset_config():
    """Reset the Config singleton for testing."""
    Config._instance = None


def test_valid_paper_demo_combination():
    """Test that PAPER + DEMO is a valid combination."""
    print("\n=== Test: Valid PAPER + DEMO Combination ===")
    
    reset_config()
    config = get_config()
    
    # Set PAPER mode with DEMO API (valid)
    config.trading.mode = TradingMode.PAPER
    config.bybit.use_demo = True
    
    # Validation should pass
    is_valid, messages = config.validate_trading_mode_consistency()
    
    assert is_valid, f"PAPER+DEMO should be valid, but got errors: {messages}"
    assert len(messages) == 0, f"Should have no error messages, got: {messages}"
    
    print("PASSED: PAPER + DEMO is correctly accepted as valid")
    reset_config()
    return True


def test_valid_real_live_combination():
    """Test that REAL + LIVE is a valid combination."""
    print("\n=== Test: Valid REAL + LIVE Combination ===")
    
    reset_config()
    config = get_config()
    
    # Set REAL mode with LIVE API (valid)
    config.trading.mode = TradingMode.REAL
    config.bybit.use_demo = False
    
    # Validation should pass
    is_valid, messages = config.validate_trading_mode_consistency()
    
    assert is_valid, f"REAL+LIVE should be valid, but got errors: {messages}"
    assert len(messages) == 0, f"Should have no error messages, got: {messages}"
    
    print("PASSED: REAL + LIVE is correctly accepted as valid")
    reset_config()
    return True


def test_invalid_real_demo_combination():
    """Test that REAL + DEMO is rejected as invalid."""
    print("\n=== Test: Invalid REAL + DEMO Combination ===")
    
    reset_config()
    config = get_config()
    
    # Set REAL mode with DEMO API (INVALID)
    config.trading.mode = TradingMode.REAL
    config.bybit.use_demo = True
    
    # Validation should FAIL
    is_valid, messages = config.validate_trading_mode_consistency()
    
    assert not is_valid, "REAL+DEMO should be INVALID"
    assert len(messages) > 0, "Should have error message"
    assert "INVALID" in messages[0] or "ERROR" in messages[0], f"Error message should indicate invalid: {messages[0]}"
    assert "REAL" in messages[0] and "DEMO" in messages[0], f"Error should mention REAL and DEMO: {messages[0]}"
    
    print(f"PASSED: REAL + DEMO is correctly rejected with: {messages[0][:80]}...")
    reset_config()
    return True


def test_invalid_paper_live_combination():
    """Test that PAPER + LIVE is rejected as invalid."""
    print("\n=== Test: Invalid PAPER + LIVE Combination ===")
    
    reset_config()
    config = get_config()
    
    # Set PAPER mode with LIVE API (INVALID)
    config.trading.mode = TradingMode.PAPER
    config.bybit.use_demo = False
    
    # Validation should FAIL
    is_valid, messages = config.validate_trading_mode_consistency()
    
    assert not is_valid, "PAPER+LIVE should be INVALID"
    assert len(messages) > 0, "Should have error message"
    assert "INVALID" in messages[0] or "ERROR" in messages[0], f"Error message should indicate invalid: {messages[0]}"
    assert "PAPER" in messages[0] or "paper" in messages[0], f"Error should mention PAPER: {messages[0]}"
    
    print(f"PASSED: PAPER + LIVE is correctly rejected with: {messages[0][:80]}...")
    reset_config()
    return True


def test_validate_also_rejects_invalid():
    """Test that the main validate() method also catches invalid combinations."""
    print("\n=== Test: Main validate() Also Rejects Invalid ===")
    
    reset_config()
    config = get_config()
    
    # Set invalid combination
    config.trading.mode = TradingMode.PAPER
    config.bybit.use_demo = False
    
    # Main validation should FAIL
    is_valid, messages = config.validate()
    
    assert not is_valid, "validate() should also catch PAPER+LIVE as invalid"
    
    # Find the specific error about mode mismatch
    found_error = any("PAPER" in msg or "paper" in msg for msg in messages)
    assert found_error, f"validate() should mention PAPER mode issue: {messages}"
    
    print("PASSED: Main validate() also catches invalid mode/API combinations")
    reset_config()
    return True


def test_validate_for_trading_blocks_invalid():
    """Test that validate_for_trading() blocks invalid combinations."""
    print("\n=== Test: validate_for_trading() Blocks Invalid ===")
    
    reset_config()
    config = get_config()
    
    # Set invalid combination (REAL mode but DEMO API)
    config.trading.mode = TradingMode.REAL
    config.bybit.use_demo = True
    
    # Also need to set credentials since strict mode requires them
    # (otherwise it fails on missing key before checking mode consistency)
    config.bybit.demo_api_key = "test_key"
    config.bybit.demo_api_secret = "test_secret"
    
    # Trading validation should FAIL on mode mismatch
    can_trade, reason = config.validate_for_trading()
    
    assert not can_trade, "validate_for_trading() should block REAL+DEMO"
    assert "INVALID" in reason or "SAFETY" in reason or "failed" in reason.lower(), \
        f"Reason should explain the block: {reason}"
    
    print(f"PASSED: validate_for_trading() blocks with: {reason[:60]}...")
    reset_config()
    return True


def test_websocket_endpoints_match_mode():
    """Test that WebSocket endpoints correctly match the trading mode."""
    print("\n=== Test: WebSocket Endpoints Match Mode ===")
    
    reset_config()
    config = get_config()
    
    # DEMO mode
    config.bybit.use_demo = True
    config.trading.mode = TradingMode.PAPER
    
    env = config.bybit.get_api_environment_summary()
    assert "stream-demo.bybit.com" in env["websocket"]["public_url"], \
        f"DEMO should use demo WS: {env['websocket']['public_url']}"
    
    # LIVE mode
    config.bybit.use_demo = False
    config.trading.mode = TradingMode.REAL
    
    env = config.bybit.get_api_environment_summary()
    assert "stream.bybit.com" in env["websocket"]["public_url"], \
        f"LIVE should use live WS: {env['websocket']['public_url']}"
    assert "stream-demo" not in env["websocket"]["public_url"], \
        f"LIVE should NOT use demo WS"
    
    print("PASSED: WebSocket endpoints correctly match trading mode")
    reset_config()
    return True


def test_data_always_live_regardless_of_mode():
    """Test that data API is always LIVE regardless of trading mode."""
    print("\n=== Test: Data API Always LIVE ===")
    
    reset_config()
    config = get_config()
    
    # Test with DEMO trading mode
    config.bybit.use_demo = True
    config.trading.mode = TradingMode.PAPER
    
    env1 = config.bybit.get_api_environment_summary()
    assert env1["data"]["mode"] == "LIVE", "Data should be LIVE even with DEMO trading"
    assert "api.bybit.com" in env1["data"]["base_url"], "Data URL should be live API"
    
    # Test with LIVE trading mode
    config.bybit.use_demo = False
    config.trading.mode = TradingMode.REAL
    
    env2 = config.bybit.get_api_environment_summary()
    assert env2["data"]["mode"] == "LIVE", "Data should be LIVE with LIVE trading"
    assert "api.bybit.com" in env2["data"]["base_url"], "Data URL should be live API"
    
    # Data config should be identical in both cases
    assert env1["data"] == env2["data"], "Data config must be identical regardless of trading mode"
    
    print("PASSED: Data API always uses LIVE regardless of trading mode")
    reset_config()
    return True


def run_all_tests():
    """Run all strict mapping tests."""
    print("=" * 70)
    print("Trading Mode to API Environment Strict Mapping Tests")
    print("=" * 70)
    print("\nCanonical Contract:")
    print("  - PAPER + DEMO = VALID (demo account, fake funds)")
    print("  - REAL  + LIVE = VALID (live account, real funds)")
    print("  - REAL  + DEMO = INVALID (blocked)")
    print("  - PAPER + LIVE = INVALID (blocked)")
    print("=" * 70)
    
    tests = [
        test_valid_paper_demo_combination,
        test_valid_real_live_combination,
        test_invalid_real_demo_combination,
        test_invalid_paper_live_combination,
        test_validate_also_rejects_invalid,
        test_validate_for_trading_blocks_invalid,
        test_websocket_endpoints_match_mode,
        test_data_always_live_regardless_of_mode,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
                print(f"FAILED: {test.__name__}")
        except Exception as e:
            failed += 1
            print(f"ERROR in {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

