#!/usr/bin/env python3
"""
Tests for Application lifecycle management.

Tests:
- Application initialization
- Component dependency order
- WebSocket auto-start
- Graceful shutdown
- Error handling
"""

import os
import sys
import time
import threading

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config.config import get_config
from src.core.application import Application, get_application, reset_application


def test_application_initialization():
    """Test that Application initializes correctly."""
    print("\n=== Test: Application Initialization ===")
    
    # Reset any existing instance
    reset_application()
    
    # Create new instance
    app = Application()
    
    assert not app.is_initialized, "App should not be initialized yet"
    assert not app.is_running, "App should not be running yet"
    
    # Initialize
    result = app.initialize()
    
    assert result, "Initialization should succeed"
    assert app.is_initialized, "App should be initialized"
    assert app.exchange_manager is not None, "ExchangeManager should be initialized"
    assert app.risk_manager is not None, "RiskManager should be initialized"
    assert app.position_manager is not None, "PositionManager should be initialized"
    assert app.realtime_state is not None, "RealtimeState should be initialized"
    
    # Cleanup
    app.stop()
    reset_application()
    
    print("PASSED: Application initialization works correctly")
    return True


def test_application_start_stop():
    """Test Application start and stop lifecycle."""
    print("\n=== Test: Application Start/Stop ===")
    
    reset_application()
    app = Application()
    
    # Should fail to start without initialization
    result = app.start()
    assert not result, "Start should fail without initialization"
    
    # Initialize and start
    app.initialize()
    result = app.start()
    
    assert result, "Start should succeed after initialization"
    assert app.is_running, "App should be running"
    
    # Stop
    app.stop()
    
    assert not app.is_running, "App should not be running after stop"
    
    reset_application()
    print("PASSED: Application start/stop works correctly")
    return True


def test_context_manager():
    """Test Application as context manager."""
    print("\n=== Test: Context Manager ===")
    
    reset_application()
    
    with Application() as app:
        assert app.is_initialized, "App should be initialized in context"
        assert app.is_running, "App should be running in context"
    
    # After context exit
    assert not app.is_running, "App should not be running after context exit"
    
    reset_application()
    print("PASSED: Context manager works correctly")
    return True


def test_get_status():
    """Test Application status reporting."""
    print("\n=== Test: Status Reporting ===")
    
    reset_application()
    
    app = Application()
    app.initialize()
    app.start()
    
    status = app.get_status()
    
    assert status.initialized, "Status should show initialized"
    assert status.running, "Status should show running"
    assert isinstance(status.symbols, list), "Symbols should be a list"
    
    app.stop()
    
    status = app.get_status()
    assert not status.running, "Status should show not running after stop"
    
    reset_application()
    print("PASSED: Status reporting works correctly")
    return True


def test_shutdown_callbacks():
    """Test shutdown callbacks."""
    print("\n=== Test: Shutdown Callbacks ===")
    
    reset_application()
    
    callback_called = [False]  # Use list to avoid closure issues
    
    def my_callback():
        callback_called[0] = True
    
    app = Application()
    app.initialize()
    app.start()
    app.on_shutdown(my_callback)
    app.stop()
    
    assert callback_called[0], "Shutdown callback should have been called"
    
    reset_application()
    print("PASSED: Shutdown callbacks work correctly")
    return True


def test_singleton_pattern():
    """Test that get_application returns singleton."""
    print("\n=== Test: Singleton Pattern ===")
    
    reset_application()
    
    app1 = get_application()
    app2 = get_application()
    
    assert app1 is app2, "get_application should return same instance"
    
    reset_application()
    print("PASSED: Singleton pattern works correctly")
    return True


def test_double_initialization():
    """Test that double initialization is handled gracefully."""
    print("\n=== Test: Double Initialization ===")
    
    reset_application()
    
    app = Application()
    
    result1 = app.initialize()
    result2 = app.initialize()
    
    assert result1, "First initialization should succeed"
    assert result2, "Second initialization should also return True (no-op)"
    
    app.stop()
    reset_application()
    print("PASSED: Double initialization handled correctly")
    return True


def test_double_stop():
    """Test that double stop is handled gracefully."""
    print("\n=== Test: Double Stop ===")
    
    reset_application()
    
    app = Application()
    app.initialize()
    app.start()
    
    # Stop twice - should not raise
    app.stop()
    app.stop()  # This should be a no-op
    
    reset_application()
    print("PASSED: Double stop handled correctly")
    return True


def run_all_tests():
    """Run all Application lifecycle tests."""
    print("=" * 60)
    print("APPLICATION LIFECYCLE TESTS")
    print("=" * 60)
    
    tests = [
        test_application_initialization,
        test_application_start_stop,
        test_context_manager,
        test_get_status,
        test_shutdown_callbacks,
        test_singleton_pattern,
        test_double_initialization,
        test_double_stop,
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
            failed += 1
        finally:
            # Always reset between tests
            reset_application()
    
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

