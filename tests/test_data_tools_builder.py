"""
Tests for enhanced data tools (builder, sync-to-now, timeframe ranges).

These tests verify the ToolResult shapes and basic functionality of new data tools.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from src.tools import ToolResult
from src.tools.data_tools import (
    get_symbol_timeframe_ranges_tool,
    build_symbol_history_tool,
    sync_to_now_tool,
    sync_to_now_and_fill_gaps_tool,
)


class TestGetSymbolTimeframeRangesTool:
    """Tests for get_symbol_timeframe_ranges_tool."""
    
    def test_returns_tool_result(self):
        """Should return a ToolResult object."""
        with patch("src.tools.data_tools._get_historical_store") as mock_store:
            mock_store.return_value.status.return_value = {}
            result = get_symbol_timeframe_ranges_tool()
            assert isinstance(result, ToolResult)
    
    def test_empty_database_returns_success(self):
        """Empty database should return success with empty list."""
        with patch("src.tools.data_tools._get_historical_store") as mock_store:
            mock_store.return_value.status.return_value = {}
            result = get_symbol_timeframe_ranges_tool()
            assert result.success is True
            assert result.data == {"ranges": [], "count": 0}
    
    def test_returns_flat_list_for_table_display(self):
        """Should return data as a flat list for table rendering."""
        mock_status = {
            "BTCUSDT_15m": {
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "first_timestamp": datetime(2024, 1, 1),
                "last_timestamp": datetime(2024, 12, 1),
                "candle_count": 1000,
                "gaps": 2,
                "is_current": True,
            },
            "BTCUSDT_1h": {
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "first_timestamp": datetime(2024, 1, 1),
                "last_timestamp": datetime(2024, 12, 1),
                "candle_count": 250,
                "gaps": 0,
                "is_current": True,
            },
        }
        
        with patch("src.tools.data_tools._get_historical_store") as mock_store:
            mock_store.return_value.status.return_value = mock_status
            result = get_symbol_timeframe_ranges_tool()
            
            assert result.success is True
            assert isinstance(result.data, list)
            assert len(result.data) == 2
            
            # Check structure of each row
            for row in result.data:
                assert "symbol" in row
                assert "timeframe" in row
                assert "first_timestamp" in row
                assert "last_timestamp" in row
                assert "candle_count" in row
                assert "gaps" in row
                assert "is_current" in row
    
    def test_filters_by_symbol(self):
        """Should filter results when symbol is provided."""
        with patch("src.tools.data_tools._get_historical_store") as mock_store:
            mock_store.return_value.status.return_value = {}
            result = get_symbol_timeframe_ranges_tool(symbol="BTCUSDT")
            
            # Should call status with the symbol
            mock_store.return_value.status.assert_called_once_with("BTCUSDT")


class TestBuildSymbolHistoryTool:
    """Tests for build_symbol_history_tool."""
    
    def test_returns_tool_result(self):
        """Should return a ToolResult object."""
        with patch("src.tools.data_tools.sync_symbols_tool") as mock_ohlcv, \
             patch("src.tools.data_tools.sync_funding_tool") as mock_funding, \
             patch("src.tools.data_tools.sync_open_interest_tool") as mock_oi:
            
            mock_ohlcv.return_value = ToolResult(success=True, message="OK", data={"total_synced": 100, "results": {}})
            mock_funding.return_value = ToolResult(success=True, message="OK", data={"total_synced": 50, "results": {}})
            mock_oi.return_value = ToolResult(success=True, message="OK", data={"total_synced": 25, "results": {}})
            
            result = build_symbol_history_tool(["BTCUSDT"])
            assert isinstance(result, ToolResult)
    
    def test_requires_symbols(self):
        """Should fail if no symbols provided."""
        result = build_symbol_history_tool([])
        assert result.success is False
        assert "No symbols provided" in result.error
    
    def test_combines_all_data_types(self):
        """Should sync OHLCV, funding, and open interest."""
        with patch("src.tools.data_tools.sync_symbols_tool") as mock_ohlcv, \
             patch("src.tools.data_tools.sync_funding_tool") as mock_funding, \
             patch("src.tools.data_tools.sync_open_interest_tool") as mock_oi:
            
            mock_ohlcv.return_value = ToolResult(success=True, message="OK", data={"total_synced": 100, "results": {}})
            mock_funding.return_value = ToolResult(success=True, message="OK", data={"total_synced": 50, "results": {}})
            mock_oi.return_value = ToolResult(success=True, message="OK", data={"total_synced": 25, "results": {}})
            
            result = build_symbol_history_tool(["BTCUSDT"], period="1M")
            
            assert result.success is True
            assert result.data["ohlcv"]["total_synced"] == 100
            assert result.data["funding"]["total_synced"] == 50
            assert result.data["open_interest"]["total_synced"] == 25
            assert result.data["total_records"] == 175
    
    def test_reports_partial_success(self):
        """Should report partial success if some syncs fail."""
        with patch("src.tools.data_tools.sync_symbols_tool") as mock_ohlcv, \
             patch("src.tools.data_tools.sync_funding_tool") as mock_funding, \
             patch("src.tools.data_tools.sync_open_interest_tool") as mock_oi:
            
            mock_ohlcv.return_value = ToolResult(success=True, message="OK", data={"total_synced": 100, "results": {}})
            mock_funding.return_value = ToolResult(success=False, error="API error")
            mock_oi.return_value = ToolResult(success=True, message="OK", data={"total_synced": 25, "results": {}})
            
            result = build_symbol_history_tool(["BTCUSDT"])
            
            # Should still be success if we got some data
            assert result.success is True
            assert result.data["ohlcv"]["success"] is True
            assert result.data["funding"]["success"] is False
            assert result.data["open_interest"]["success"] is True
            assert result.data["errors"] is not None


class TestSyncToNowTool:
    """Tests for sync_to_now_tool."""
    
    def test_returns_tool_result(self):
        """Should return a ToolResult object."""
        with patch("src.tools.data_tools._get_historical_store") as mock_store:
            mock_store.return_value.sync_forward.return_value = {"BTCUSDT_15m": 10}
            result = sync_to_now_tool(["BTCUSDT"])
            assert isinstance(result, ToolResult)
    
    def test_requires_symbols(self):
        """Should fail if no symbols provided."""
        result = sync_to_now_tool([])
        assert result.success is False
        assert "No symbols provided" in result.error
    
    def test_reports_already_current(self):
        """Should indicate when symbols are already current."""
        with patch("src.tools.data_tools._get_historical_store") as mock_store:
            mock_store.return_value.sync_forward.return_value = {"BTCUSDT_15m": 0, "BTCUSDT_1h": 0}
            result = sync_to_now_tool(["BTCUSDT"])
            
            assert result.success is True
            assert result.data["total_synced"] == 0
            assert result.data["already_current"] == 2
            assert "already current" in result.message.lower()


class TestSyncToNowAndFillGapsTool:
    """Tests for sync_to_now_and_fill_gaps_tool."""
    
    def test_returns_tool_result(self):
        """Should return a ToolResult object."""
        with patch("src.tools.data_tools.sync_to_now_tool") as mock_sync, \
             patch("src.tools.data_tools.fill_gaps_tool") as mock_fill:
            
            mock_sync.return_value = ToolResult(success=True, message="OK", data={"total_synced": 10, "results": {}})
            mock_fill.return_value = ToolResult(success=True, message="OK", data={"total_filled": 5, "results": {}})
            
            result = sync_to_now_and_fill_gaps_tool(["BTCUSDT"])
            assert isinstance(result, ToolResult)
    
    def test_requires_symbols(self):
        """Should fail if no symbols provided."""
        result = sync_to_now_and_fill_gaps_tool([])
        assert result.success is False
        assert "No symbols provided" in result.error
    
    def test_combines_sync_and_fill(self):
        """Should combine sync forward and gap fill operations."""
        with patch("src.tools.data_tools.sync_to_now_tool") as mock_sync, \
             patch("src.tools.data_tools.fill_gaps_tool") as mock_fill:
            
            mock_sync.return_value = ToolResult(success=True, message="OK", data={"total_synced": 10, "results": {}})
            # fill_gaps_tool returns results in a different structure
            mock_fill.return_value = ToolResult(success=True, message="OK", data={"results": {"BTCUSDT_1h": 5}, "total_filled": 5})
            
            result = sync_to_now_and_fill_gaps_tool(["BTCUSDT"])
            
            assert result.success is True
            assert result.data["sync_forward"]["total_synced"] == 10
            # Gap fill extracts values from results dict
            assert result.data["gap_fill"]["total_filled"] == 5


class TestToolRegistry:
    """Tests for data tools in ToolRegistry."""
    
    def test_data_tools_registered(self):
        """All new data tools should be registered."""
        from src.tools.tool_registry import get_registry
        
        registry = get_registry()
        
        # Check info tools
        assert registry.get_tool_info("get_database_stats") is not None
        assert registry.get_tool_info("list_cached_symbols") is not None
        assert registry.get_tool_info("get_symbol_status") is not None
        assert registry.get_tool_info("get_symbol_summary") is not None
        assert registry.get_tool_info("get_symbol_timeframe_ranges") is not None
        
        # Check sync tools
        assert registry.get_tool_info("sync_symbols") is not None
        assert registry.get_tool_info("sync_range") is not None
        assert registry.get_tool_info("sync_funding") is not None
        assert registry.get_tool_info("sync_open_interest") is not None
        assert registry.get_tool_info("sync_to_now") is not None
        assert registry.get_tool_info("sync_to_now_and_fill_gaps") is not None
        assert registry.get_tool_info("build_symbol_history") is not None
        
        # Check maintenance tools
        assert registry.get_tool_info("fill_gaps") is not None
        assert registry.get_tool_info("heal_data") is not None
        assert registry.get_tool_info("delete_symbol") is not None
        assert registry.get_tool_info("cleanup_empty_symbols") is not None
        assert registry.get_tool_info("vacuum_database") is not None
    
    def test_data_categories_exist(self):
        """Data tool categories should be present."""
        from src.tools.tool_registry import get_registry
        
        registry = get_registry()
        categories = registry.list_categories()
        
        assert "data.info" in categories
        assert "data.sync" in categories
        assert "data.maintenance" in categories
    
    def test_list_tools_by_category(self):
        """Should be able to filter tools by data categories."""
        from src.tools.tool_registry import get_registry
        
        registry = get_registry()
        
        data_info_tools = registry.list_tools(category="data.info")
        assert len(data_info_tools) >= 4
        
        data_sync_tools = registry.list_tools(category="data.sync")
        assert len(data_sync_tools) >= 6
        
        data_maint_tools = registry.list_tools(category="data.maintenance")
        assert len(data_maint_tools) >= 4

