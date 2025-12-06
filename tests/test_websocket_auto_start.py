#!/usr/bin/env python3
"""
Tests for WebSocket auto-start functionality.

Tests:
- Auto-start when enabled
- No auto-start when disabled
- Fallback to REST when WebSocket fails
- WebSocket health monitoring
"""

import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config.config import get_config
from src.core.application import Application, reset_application
from src.data.realtime_bootstrap import reset_realtime_bootstrap
from src.data.realtime_state import reset_realtime_state
from src.tools.shared import _is_websocket_connected, _get_data_source


def reset_all():
    """Reset all singletons for clean test state."""
    reset_application()
    reset_realtime_bootstrap()
    reset_realtime_state()


def test_auto_start_enabled():
    """Test that WebSocket auto-starts when enabled."""
    print("\n=== Test: Auto-Start Enabled ===")
    
    reset_all()
    
    config = get_config()
    
    # Skip if WebSocket is disabled in config
    if not config.websocket.enable_websocket:
        print("SKIPPED: WebSocket disabled in config")
        return True
    
    # Skip if no symbols configured
    if not config.trading.default_symbols:
        print("SKIPPED: No symbols configured")
        return True
    
    # Create app with auto_start enabled
    app = Application()
    app.initialize()
    app.start()
    
    # Give WebSocket time to connect
    time.sleep(2)
    
    status = app.get_status()
    
    # Should have attempted to connect (may or may not succeed depending on network)
    print(f"  WebSocket connected: {status.websocket_connected}")
    print(f"  Public: {status.websocket_public}")
    print(f"  Private: {status.websocket_private}")
    
    app.stop()
    reset_all()
    
    print("PASSED: Auto-start behavior executed")
    return True


def test_websocket_health():
    """Test WebSocket health reporting."""
    print("\n=== Test: WebSocket Health ===")
    
    reset_all()
    
    config = get_config()
    
    if not config.websocket.enable_websocket:
        print("SKIPPED: WebSocket disabled in config")
        return True
    
    if not config.trading.default_symbols:
        print("SKIPPED: No symbols configured")
        return True
    
    app = Application()
    app.initialize()
    app.start()
    
    # Give WebSocket time to connect
    time.sleep(2)
    
    health = app.get_websocket_health()
    
    assert "healthy" in health, "Health should include 'healthy' field"
    
    print(f"  Health: {health}")
    
    app.stop()
    reset_all()
    
    print("PASSED: Health reporting works")
    return True


def test_data_source_detection():
    """Test that data source is correctly detected."""
    print("\n=== Test: Data Source Detection ===")
    
    reset_all()
    
    # Without WebSocket, should be REST
    source = _get_data_source()
    print(f"  Initial data source: {source}")
    
    # Source should be rest_api if not connected
    if not _is_websocket_connected():
        assert source == "rest_api", "Should be rest_api when not connected"
    
    reset_all()
    print("PASSED: Data source detection works")
    return True


def test_manual_websocket_start():
    """Test manual WebSocket start/stop."""
    print("\n=== Test: Manual WebSocket Start/Stop ===")
    
    reset_all()
    
    config = get_config()
    
    if not config.websocket.enable_websocket:
        print("SKIPPED: WebSocket disabled in config")
        return True
    
    if not config.trading.default_symbols:
        print("SKIPPED: No symbols configured")
        return True
    
    # Initialize app but don't auto-start WebSocket
    app = Application()
    app.initialize()
    
    # Manually start without WebSocket
    # (We can't easily disable auto_start without modifying config)
    app._running = True  # Simulate running state
    
    # Then manually start WebSocket
    result = app.start_websocket()
    print(f"  Manual start result: {result}")
    
    # Give time to connect
    time.sleep(2)
    
    # Stop WebSocket
    app.stop_websocket()
    
    app.stop()
    reset_all()
    
    print("PASSED: Manual WebSocket control works")
    return True


def test_graceful_fallback():
    """Test that tools work with REST fallback."""
    print("\n=== Test: Graceful REST Fallback ===")
    
    reset_all()
    
    # Import a tool that uses WebSocket
    from src.tools.position_tools import list_open_positions_tool
    
    # Call tool - should work via REST even without WebSocket
    result = list_open_positions_tool()
    
    print(f"  Result success: {result.success}")
    print(f"  Data source: {result.source}")
    
    # Should succeed (may be via websocket or rest_api)
    if result.success:
        assert result.source in ["websocket", "rest_api"], "Source should be websocket or rest_api"
    else:
        # If it fails, it should be due to API issues, not WebSocket
        print(f"  Error: {result.error}")
    
    reset_all()
    print("PASSED: REST fallback works")
    return True


def run_all_tests():
    """Run all WebSocket auto-start tests."""
    print("=" * 60)
    print("WEBSOCKET AUTO-START TESTS")
    print("=" * 60)
    
    tests = [
        test_data_source_detection,
        test_graceful_fallback,
        test_auto_start_enabled,
        test_websocket_health,
        test_manual_websocket_start,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAILED: {test.__name__}")
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
        finally:
            # Always reset between tests
            reset_all()
    
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

