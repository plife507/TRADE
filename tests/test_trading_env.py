"""Test trading environment validation implementation."""

import pytest


def test_trading_env_constants():
    """Test TradingEnv type and validation."""
    from src.config.constants import TradingEnv, TRADING_ENVS, validate_trading_env
    
    assert "demo" in TRADING_ENVS
    assert "live" in TRADING_ENVS
    assert validate_trading_env("demo") == "demo"
    assert validate_trading_env("LIVE") == "live"
    assert validate_trading_env("Demo") == "demo"
    
    with pytest.raises(ValueError):
        validate_trading_env("invalid")


def test_trading_env_mapping():
    """Test the environment mapping documentation."""
    from src.config.constants import get_trading_env_mapping
    
    mapping = get_trading_env_mapping()
    assert "demo" in mapping
    assert "live" in mapping
    assert mapping["demo"]["use_demo"] is True
    assert mapping["live"]["use_demo"] is False


def test_trading_env_param_constant():
    """Test TRADING_ENV_PARAM is defined in registry."""
    from src.tools.tool_registry import TRADING_ENV_PARAM
    
    assert TRADING_ENV_PARAM["type"] == "string"
    assert TRADING_ENV_PARAM["optional"] is True
    assert "demo" in TRADING_ENV_PARAM["description"]


def test_trading_tools_have_trading_env_param():
    """Test that trading tools expose trading_env parameter."""
    from src.tools.tool_registry import get_registry
    
    registry = get_registry()
    
    trading_tools = [
        "market_buy", "market_sell", "market_buy_with_tpsl", "market_sell_with_tpsl",
        "limit_buy", "limit_sell", "partial_close",
        "stop_market_buy", "stop_market_sell", "stop_limit_buy", "stop_limit_sell",
        "get_open_orders", "cancel_order", "amend_order", "cancel_all_orders",
        "list_positions", "get_position", "close_position",
        "set_take_profit", "set_stop_loss", "remove_take_profit", "remove_stop_loss",
        "set_trailing_stop", "set_trailing_stop_percent",
        "panic_close_all",
        "get_balance", "get_portfolio", "set_leverage",
        "get_order_history", "get_closed_pnl", "get_transaction_log", "get_borrow_history",
    ]
    
    for tool_name in trading_tools:
        info = registry.get_tool_info(tool_name)
        assert info is not None, f"Tool {tool_name} not found"
        params = info.get("parameters", {})
        assert "trading_env" in params, f"Tool {tool_name} missing trading_env parameter"


def test_validate_trading_env_or_error():
    """Test the convenience validation helper."""
    from src.tools.shared import validate_trading_env_or_error
    
    # None should pass (no validation)
    result = validate_trading_env_or_error(None)
    assert result is None
    
    # Invalid env should return error
    result = validate_trading_env_or_error("invalid")
    assert result is not None
    assert result.success is False
    assert "Invalid" in result.error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

