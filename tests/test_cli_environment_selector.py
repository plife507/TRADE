#!/usr/bin/env python3
"""
Tests for CLI Trading Environment Selector.

Tests:
- Config singleton modification affects downstream components
- get_api_environment_summary() reflects runtime changes
- DEMO and LIVE mode settings propagate correctly
- Data API stays on LIVE regardless of trading mode

These tests verify the session-level environment selection
implemented in trade_cli.py works as expected.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config.config import Config, get_config, TradingMode


def reset_config():
    """Reset the Config singleton for testing."""
    Config._instance = None
    Config._instance = None


def test_config_singleton_modification():
    """Test that modifying config singleton affects all references."""
    print("\n=== Test: Config Singleton Modification ===")
    
    reset_config()
    
    # Get config and record initial values
    config = get_config()
    initial_use_demo = config.bybit.use_demo
    initial_trading_mode = config.trading.mode
    
    print(f"Initial: use_demo={initial_use_demo}, trading_mode={initial_trading_mode}")
    
    # Modify in-memory (simulating CLI selector behavior)
    config.bybit.use_demo = True
    config.trading.mode = "paper"
    
    # Get another reference - should see the same modified values
    config2 = get_config()
    
    assert config2.bybit.use_demo == True, "Second reference should see use_demo=True"
    assert config2.trading.mode == "paper", "Second reference should see mode=paper"
    assert config is config2, "Should be the same singleton instance"
    
    print("PASSED: Config singleton modification works correctly")
    reset_config()
    return True


def test_demo_mode_environment_summary():
    """Test that DEMO mode is correctly reflected in environment summary."""
    print("\n=== Test: DEMO Mode Environment Summary ===")
    
    reset_config()
    config = get_config()
    
    # Set DEMO mode (simulating CLI selector)
    config.bybit.use_demo = True
    config.trading.mode = "paper"
    
    # Get environment summary
    env = config.get_api_environment_summary()
    
    # Verify trading section
    assert env["trading"]["mode"] == "DEMO", f"Expected DEMO, got {env['trading']['mode']}"
    assert env["trading"]["is_demo"] == True, "is_demo should be True"
    assert env["trading"]["is_live"] == False, "is_live should be False"
    assert env["trading"]["trading_mode"] == "paper", "trading_mode should be paper"
    assert "api-demo.bybit.com" in env["trading"]["base_url"], "Should use demo URL"
    
    # Verify data section (ALWAYS LIVE)
    assert env["data"]["mode"] == "LIVE", f"Data should ALWAYS be LIVE, got {env['data']['mode']}"
    assert "api.bybit.com" in env["data"]["base_url"], "Data should use live URL"
    
    # Verify websocket section (matches trading mode)
    assert env["websocket"]["mode"] == "DEMO", "WebSocket should match trading mode"
    assert "stream-demo.bybit.com" in env["websocket"]["public_url"], "WS should use demo stream"
    
    print("PASSED: DEMO mode environment summary is correct")
    reset_config()
    return True


def test_live_mode_environment_summary():
    """Test that LIVE mode is correctly reflected in environment summary."""
    print("\n=== Test: LIVE Mode Environment Summary ===")
    
    reset_config()
    config = get_config()
    
    # Set LIVE mode (simulating CLI selector after double confirmation)
    config.bybit.use_demo = False
    config.trading.mode = "real"
    
    # Get environment summary
    env = config.get_api_environment_summary()
    
    # Verify trading section
    assert env["trading"]["mode"] == "LIVE", f"Expected LIVE, got {env['trading']['mode']}"
    assert env["trading"]["is_demo"] == False, "is_demo should be False"
    assert env["trading"]["is_live"] == True, "is_live should be True"
    assert env["trading"]["trading_mode"] == "real", "trading_mode should be real"
    assert "api.bybit.com" in env["trading"]["base_url"], "Should use live URL"
    assert "api-demo" not in env["trading"]["base_url"], "Should NOT use demo URL"
    
    # Verify data section (ALWAYS LIVE)
    assert env["data"]["mode"] == "LIVE", f"Data should ALWAYS be LIVE, got {env['data']['mode']}"
    assert "api.bybit.com" in env["data"]["base_url"], "Data should use live URL"
    
    # Verify websocket section (matches trading mode)
    assert env["websocket"]["mode"] == "LIVE", "WebSocket should match trading mode"
    assert "stream.bybit.com" in env["websocket"]["public_url"], "WS should use live stream"
    assert "stream-demo" not in env["websocket"]["public_url"], "WS should NOT use demo stream"
    
    print("PASSED: LIVE mode environment summary is correct")
    reset_config()
    return True


def test_data_api_always_live():
    """Test that data API credentials always return LIVE regardless of use_demo."""
    print("\n=== Test: Data API Always LIVE ===")
    
    reset_config()
    config = get_config()
    
    # Test with DEMO mode
    config.bybit.use_demo = True
    env_demo = config.bybit.get_api_environment_summary()
    
    assert env_demo["data"]["mode"] == "LIVE", "Data should be LIVE even in DEMO mode"
    assert "api.bybit.com" in env_demo["data"]["base_url"], "Data URL should be live"
    
    # Test with LIVE mode  
    config.bybit.use_demo = False
    env_live = config.bybit.get_api_environment_summary()
    
    assert env_live["data"]["mode"] == "LIVE", "Data should be LIVE in LIVE mode"
    assert "api.bybit.com" in env_live["data"]["base_url"], "Data URL should be live"
    
    # Data config should be identical regardless of trading mode
    assert env_demo["data"] == env_live["data"], "Data config should be identical in both modes"
    
    print("PASSED: Data API always uses LIVE regardless of trading mode")
    reset_config()
    return True


def test_mode_switch_propagation():
    """Test switching between DEMO and LIVE modes during a session."""
    print("\n=== Test: Mode Switch Propagation ===")
    
    reset_config()
    config = get_config()
    
    # Start in DEMO
    config.bybit.use_demo = True
    config.trading.mode = "paper"
    
    env1 = config.get_api_environment_summary()
    assert env1["trading"]["mode"] == "DEMO", "Should start in DEMO"
    
    # Switch to LIVE
    config.bybit.use_demo = False
    config.trading.mode = "real"
    
    env2 = config.get_api_environment_summary()
    assert env2["trading"]["mode"] == "LIVE", "Should switch to LIVE"
    
    # Switch back to DEMO
    config.bybit.use_demo = True
    config.trading.mode = "paper"
    
    env3 = config.get_api_environment_summary()
    assert env3["trading"]["mode"] == "DEMO", "Should switch back to DEMO"
    
    # Throughout all switches, data should stay LIVE
    assert env1["data"]["mode"] == "LIVE", "Data should stay LIVE"
    assert env2["data"]["mode"] == "LIVE", "Data should stay LIVE"
    assert env3["data"]["mode"] == "LIVE", "Data should stay LIVE"
    
    print("PASSED: Mode switches propagate correctly, data stays LIVE")
    reset_config()
    return True


def test_bybit_config_helpers():
    """Test BybitConfig helper methods reflect runtime changes."""
    print("\n=== Test: BybitConfig Helper Methods ===")
    
    reset_config()
    config = get_config()
    
    # Set DEMO mode
    config.bybit.use_demo = True
    
    assert config.bybit.is_demo == True, "is_demo should be True"
    assert config.bybit.is_live == False, "is_live should be False"
    assert config.bybit.get_mode_name() == "DEMO", "get_mode_name should return DEMO"
    assert "DEMO" in config.bybit.get_mode_display(), "get_mode_display should contain DEMO"
    assert "api-demo.bybit.com" in config.bybit.get_base_url(), "get_base_url should return demo URL"
    
    # Switch to LIVE mode
    config.bybit.use_demo = False
    
    assert config.bybit.is_demo == False, "is_demo should be False"
    assert config.bybit.is_live == True, "is_live should be True"
    assert config.bybit.get_mode_name() == "LIVE", "get_mode_name should return LIVE"
    assert "LIVE" in config.bybit.get_mode_display(), "get_mode_display should contain LIVE"
    assert "api.bybit.com" in config.bybit.get_base_url(), "get_base_url should return live URL"
    assert "api-demo" not in config.bybit.get_base_url(), "get_base_url should NOT return demo URL"
    
    print("PASSED: BybitConfig helper methods reflect runtime changes")
    reset_config()
    return True


def test_trading_config_helpers():
    """Test TradingConfig helper methods reflect runtime changes."""
    print("\n=== Test: TradingConfig Helper Methods ===")
    
    reset_config()
    config = get_config()
    
    # Set paper mode
    config.trading.mode = "paper"
    
    assert config.trading.is_paper == True, "is_paper should be True"
    assert config.trading.is_real == False, "is_real should be False"
    
    # Switch to real mode
    config.trading.mode = "real"
    
    assert config.trading.is_paper == False, "is_paper should be False"
    assert config.trading.is_real == True, "is_real should be True"
    
    print("PASSED: TradingConfig helper methods reflect runtime changes")
    reset_config()
    return True


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("CLI Environment Selector Tests")
    print("=" * 60)
    
    tests = [
        test_config_singleton_modification,
        test_demo_mode_environment_summary,
        test_live_mode_environment_summary,
        test_data_api_always_live,
        test_mode_switch_propagation,
        test_bybit_config_helpers,
        test_trading_config_helpers,
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
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

