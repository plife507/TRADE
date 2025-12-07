"""
Tests for Strict API Key Architecture (No Fallbacks)

CANONICAL KEY CONTRACT:
- Trading: BYBIT_DEMO_API_KEY (demo) or BYBIT_LIVE_API_KEY (live) - NO fallback to BYBIT_API_KEY
- Data: BYBIT_LIVE_DATA_API_KEY (always LIVE) - NO fallback to trading keys or generic keys
- Generic keys (BYBIT_API_KEY, BYBIT_DATA_API_KEY) are IGNORED for behavior

This test file verifies that:
1. Mode-specific keys are required (no generic fallback)
2. Data keys are strictly BYBIT_LIVE_DATA_API_KEY (no fallback chain)
3. Missing keys cause hard errors in validation
4. Key source reporting shows only canonical keys
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.config.config import Config, BybitConfig, get_config


def reset_config():
    """Reset config singleton for testing."""
    Config._instance = None


def test_demo_mode_requires_demo_key():
    """DEMO mode must use BYBIT_DEMO_API_KEY, not generic BYBIT_API_KEY."""
    print("\n=== Test: DEMO mode requires BYBIT_DEMO_API_KEY ===")
    reset_config()
    
    # Create config with ONLY generic key set (no demo-specific key)
    bybit = BybitConfig(
        demo_api_key="",  # Empty - not set
        demo_api_secret="",
        api_key="generic_key",  # Has generic key
        api_secret="generic_secret",
        use_demo=True,
    )
    
    # get_credentials should return empty (no fallback to generic)
    key, secret = bybit.get_credentials()
    
    assert key == "", f"Expected empty key, got '{key}' - fallback to generic key is NOT allowed"
    assert secret == "", f"Expected empty secret, got '{secret}'"
    
    print("PASSED: DEMO mode returns empty when BYBIT_DEMO_API_KEY not set (no generic fallback)")
    return True


def test_live_mode_requires_live_key():
    """LIVE mode must use BYBIT_LIVE_API_KEY, not generic BYBIT_API_KEY."""
    print("\n=== Test: LIVE mode requires BYBIT_LIVE_API_KEY ===")
    reset_config()
    
    # Create config with ONLY generic key set (no live-specific key)
    bybit = BybitConfig(
        live_api_key="",  # Empty - not set
        live_api_secret="",
        api_key="generic_key",  # Has generic key
        api_secret="generic_secret",
        use_demo=False,
    )
    
    # get_credentials should return empty (no fallback to generic)
    key, secret = bybit.get_credentials()
    
    assert key == "", f"Expected empty key, got '{key}' - fallback to generic key is NOT allowed"
    assert secret == "", f"Expected empty secret, got '{secret}'"
    
    print("PASSED: LIVE mode returns empty when BYBIT_LIVE_API_KEY not set (no generic fallback)")
    return True


def test_data_key_requires_live_data_key():
    """Data operations must use BYBIT_LIVE_DATA_API_KEY, not trading keys."""
    print("\n=== Test: Data requires BYBIT_LIVE_DATA_API_KEY ===")
    reset_config()
    
    # Create config with trading keys but no data key
    bybit = BybitConfig(
        live_data_api_key="",  # Empty - not set
        live_data_api_secret="",
        live_api_key="live_trading_key",  # Has trading key (should NOT be used)
        live_api_secret="live_trading_secret",
        api_key="generic_key",  # Has generic key (should NOT be used)
        api_secret="generic_secret",
        data_api_key="generic_data_key",  # Has generic data key (should NOT be used)
        data_api_secret="generic_data_secret",
        use_demo=False,
    )
    
    # get_live_data_credentials should return empty (no fallback chain)
    key, secret = bybit.get_live_data_credentials()
    
    assert key == "", f"Expected empty key, got '{key}' - fallback to trading/generic keys is NOT allowed"
    assert secret == "", f"Expected empty secret, got '{secret}'"
    
    print("PASSED: Data returns empty when BYBIT_LIVE_DATA_API_KEY not set (no fallback chain)")
    return True


def test_has_live_data_credentials_strict():
    """has_live_data_credentials only checks live_data_api_key, not fallbacks."""
    print("\n=== Test: has_live_data_credentials is strict ===")
    reset_config()
    
    # Config with trading keys but no data key
    bybit_no_data_key = BybitConfig(
        live_data_api_key="",
        live_data_api_secret="",
        live_api_key="trading_key",
        live_api_secret="trading_secret",
        use_demo=False,
    )
    
    assert not bybit_no_data_key.has_live_data_credentials(), \
        "has_live_data_credentials should be False when live_data_api_key is not set"
    
    # Config with data key set
    bybit_with_data_key = BybitConfig(
        live_data_api_key="data_key",
        live_data_api_secret="data_secret",
        use_demo=False,
    )
    
    assert bybit_with_data_key.has_live_data_credentials(), \
        "has_live_data_credentials should be True when live_data_api_key is set"
    
    print("PASSED: has_live_data_credentials only checks canonical data key")
    return True


def test_key_source_reporting_no_fallback():
    """get_api_environment_summary reports only canonical keys, no fallback strings."""
    print("\n=== Test: Key source reporting shows canonical keys only ===")
    reset_config()
    
    # Config with canonical keys set
    bybit = BybitConfig(
        demo_api_key="demo_key",
        demo_api_secret="demo_secret",
        live_data_api_key="live_data_key",
        live_data_api_secret="live_data_secret",
        use_demo=True,
    )
    
    summary = bybit.get_api_environment_summary()
    
    # Check trading key source
    trading_source = summary["trading"]["key_source"]
    assert "(fallback)" not in trading_source, \
        f"Trading key source should not contain '(fallback)', got: {trading_source}"
    assert trading_source == "BYBIT_DEMO_API_KEY", \
        f"Trading key source should be 'BYBIT_DEMO_API_KEY', got: {trading_source}"
    
    # Check data key source
    data_source = summary["data"]["key_source"]
    assert "(fallback)" not in data_source, \
        f"Data key source should not contain '(fallback)', got: {data_source}"
    assert data_source == "BYBIT_LIVE_DATA_API_KEY", \
        f"Data key source should be 'BYBIT_LIVE_DATA_API_KEY', got: {data_source}"
    
    print("PASSED: Key source reporting shows only canonical keys")
    return True


def test_missing_keys_show_required_message():
    """Missing keys show 'MISSING (required)' in key source reporting."""
    print("\n=== Test: Missing keys show REQUIRED message ===")
    reset_config()
    
    # Config with no keys set
    bybit = BybitConfig(
        use_demo=True,
    )
    
    summary = bybit.get_api_environment_summary()
    
    # Check trading key source shows MISSING
    trading_source = summary["trading"]["key_source"]
    assert "MISSING" in trading_source, \
        f"Trading key source should show MISSING when key not set, got: {trading_source}"
    assert "BYBIT_DEMO_API_KEY" in trading_source, \
        f"Trading key source should mention required key name, got: {trading_source}"
    
    # Check data key source shows MISSING
    data_source = summary["data"]["key_source"]
    assert "MISSING" in data_source, \
        f"Data key source should show MISSING when key not set, got: {data_source}"
    assert "BYBIT_LIVE_DATA_API_KEY" in data_source, \
        f"Data key source should mention required key name, got: {data_source}"
    
    print("PASSED: Missing keys show REQUIRED message in reporting")
    return True


def test_generic_only_config_fails_validation():
    """Config with only generic keys (no canonical keys) fails validation."""
    print("\n=== Test: Generic-only config fails validation ===")
    reset_config()
    
    # Manually create a config-like scenario with only generic keys
    bybit = BybitConfig(
        demo_api_key="",
        demo_api_secret="",
        live_api_key="",
        live_api_secret="",
        live_data_api_key="",
        live_data_api_secret="",
        api_key="generic_key",  # Has generic but not canonical
        api_secret="generic_secret",
        use_demo=True,
    )
    
    # Check that has_credentials returns False (generic not used)
    assert not bybit.has_credentials(), \
        "has_credentials should be False when only generic keys are set"
    
    # Check that get_credentials returns empty
    key, secret = bybit.get_credentials()
    assert key == "" and secret == "", \
        "get_credentials should return empty when only generic keys are set"
    
    print("PASSED: Generic-only config is not valid for trading")
    return True


def test_demo_mode_with_correct_key():
    """DEMO mode works correctly when BYBIT_DEMO_API_KEY is set."""
    print("\n=== Test: DEMO mode with correct key ===")
    reset_config()
    
    bybit = BybitConfig(
        demo_api_key="correct_demo_key",
        demo_api_secret="correct_demo_secret",
        api_key="generic_key",  # Also has generic (should be ignored)
        api_secret="generic_secret",
        use_demo=True,
    )
    
    key, secret = bybit.get_credentials()
    
    assert key == "correct_demo_key", f"Expected 'correct_demo_key', got '{key}'"
    assert secret == "correct_demo_secret", f"Expected 'correct_demo_secret', got '{secret}'"
    assert bybit.has_credentials(), "has_credentials should be True"
    
    print("PASSED: DEMO mode uses BYBIT_DEMO_API_KEY correctly")
    return True


def test_live_mode_with_correct_key():
    """LIVE mode works correctly when BYBIT_LIVE_API_KEY is set."""
    print("\n=== Test: LIVE mode with correct key ===")
    reset_config()
    
    bybit = BybitConfig(
        live_api_key="correct_live_key",
        live_api_secret="correct_live_secret",
        api_key="generic_key",  # Also has generic (should be ignored)
        api_secret="generic_secret",
        use_demo=False,
    )
    
    key, secret = bybit.get_credentials()
    
    assert key == "correct_live_key", f"Expected 'correct_live_key', got '{key}'"
    assert secret == "correct_live_secret", f"Expected 'correct_live_secret', got '{secret}'"
    assert bybit.has_credentials(), "has_credentials should be True"
    
    print("PASSED: LIVE mode uses BYBIT_LIVE_API_KEY correctly")
    return True


def test_data_with_correct_key():
    """Data operations work correctly when BYBIT_LIVE_DATA_API_KEY is set."""
    print("\n=== Test: Data with correct key ===")
    reset_config()
    
    bybit = BybitConfig(
        live_data_api_key="correct_data_key",
        live_data_api_secret="correct_data_secret",
        live_api_key="trading_key",  # Also has trading key (should be ignored)
        live_api_secret="trading_secret",
        use_demo=True,  # Even in demo mode, data uses LIVE
    )
    
    key, secret = bybit.get_live_data_credentials()
    
    assert key == "correct_data_key", f"Expected 'correct_data_key', got '{key}'"
    assert secret == "correct_data_secret", f"Expected 'correct_data_secret', got '{secret}'"
    assert bybit.has_live_data_credentials(), "has_live_data_credentials should be True"
    
    print("PASSED: Data uses BYBIT_LIVE_DATA_API_KEY correctly")
    return True


if __name__ == "__main__":
    tests = [
        test_demo_mode_requires_demo_key,
        test_live_mode_requires_live_key,
        test_data_key_requires_live_data_key,
        test_has_live_data_credentials_strict,
        test_key_source_reporting_no_fallback,
        test_missing_keys_show_required_message,
        test_generic_only_config_fails_validation,
        test_demo_mode_with_correct_key,
        test_live_mode_with_correct_key,
        test_data_with_correct_key,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"FAILED with exception: {e}")
            failed += 1
    
    print(f"\n{'='*50}")
    print(f"RESULTS: {passed} passed, {failed} failed")
    print(f"{'='*50}")
    
    sys.exit(0 if failed == 0 else 1)

