"""
Tests for HistoricalDataStore functionality.

These tests verify the core data store operations including sync_forward.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import pandas as pd

from src.data.historical_data_store import HistoricalDataStore


class TestSyncForward:
    """Tests for sync_forward method."""
    
    @pytest.fixture
    def mock_store(self):
        """Create a store with mocked dependencies."""
        with patch("src.data.historical_data_store.get_config") as mock_config, \
             patch("src.data.historical_data_store.get_logger") as mock_logger, \
             patch("src.data.historical_data_store.BybitClient") as mock_client, \
             patch("src.data.historical_data_store.duckdb") as mock_duckdb:
            
            # Setup config mock
            mock_config.return_value.bybit.get_live_data_credentials.return_value = ("key", "secret")
            
            # Setup duckdb mock
            mock_conn = MagicMock()
            mock_duckdb.connect.return_value = mock_conn
            
            store = HistoricalDataStore(db_path=":memory:")
            store.client = MagicMock()
            
            yield store
    
    def test_sync_forward_no_existing_data_returns_zero(self, mock_store):
        """If no existing data, sync_forward should return 0."""
        # Mock no existing data
        mock_store.conn.execute.return_value.fetchone.return_value = (None,)
        
        result = mock_store._sync_forward_symbol_timeframe("BTCUSDT", "15m")
        
        # Should return 0 since there's nothing to sync forward from
        assert result == 0
    
    def test_sync_forward_already_current_returns_zero(self, mock_store):
        """If data is already current, should return 0."""
        # Mock existing data that is very recent (within one interval)
        recent_ts = datetime.now() - timedelta(minutes=5)  # 5 min ago for 15m TF
        mock_store.conn.execute.return_value.fetchone.return_value = (recent_ts,)
        
        result = mock_store._sync_forward_symbol_timeframe("BTCUSDT", "15m")
        
        # Should return 0 since start would be >= end
        assert result == 0
    
    def test_sync_forward_fetches_new_data(self, mock_store):
        """Should fetch and store new data after last timestamp."""
        # Mock existing data from 1 hour ago
        old_ts = datetime.now() - timedelta(hours=1)
        mock_store.conn.execute.return_value.fetchone.return_value = (old_ts,)
        
        # Mock API returning new candles
        new_df = pd.DataFrame({
            "timestamp": [datetime.now() - timedelta(minutes=45), datetime.now() - timedelta(minutes=30)],
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1000.0, 1100.0],
        })
        
        with patch.object(mock_store, "_fetch_from_api", return_value=new_df) as mock_fetch, \
             patch.object(mock_store, "_store_dataframe") as mock_store_df, \
             patch.object(mock_store, "_update_metadata") as mock_update:
            
            result = mock_store._sync_forward_symbol_timeframe("BTCUSDT", "15m")
            
            # Should have fetched new data
            mock_fetch.assert_called_once()
            
            # Should have stored new data
            mock_store_df.assert_called_once()
            
            # Should return count of new candles
            assert result == 2
    
    def test_sync_forward_normalizes_symbol(self, mock_store):
        """Should normalize symbol to uppercase."""
        mock_store.conn.execute.return_value.fetchone.return_value = (None,)
        
        mock_store._sync_forward_symbol_timeframe("btcusdt", "15m")
        
        # Check that queries use uppercase symbol
        call_args = mock_store.conn.execute.call_args_list
        # The query should have used BTCUSDT
        assert any("BTCUSDT" in str(call) for call in call_args)


class TestSyncForwardIntegration:
    """Integration tests for sync_forward method."""
    
    def test_sync_forward_calls_internal_method_for_each_combo(self):
        """Should call internal method for each symbol/timeframe combination."""
        with patch("src.data.historical_data_store.get_config") as mock_config, \
             patch("src.data.historical_data_store.get_logger") as mock_logger, \
             patch("src.data.historical_data_store.BybitClient") as mock_client, \
             patch("src.data.historical_data_store.duckdb") as mock_duckdb:
            
            mock_config.return_value.bybit.get_live_data_credentials.return_value = ("key", "secret")
            mock_duckdb.connect.return_value = MagicMock()
            
            store = HistoricalDataStore(db_path=":memory:")
            
            # Mock the internal method
            with patch.object(store, "_sync_forward_symbol_timeframe", return_value=5) as mock_internal:
                results = store.sync_forward(
                    ["BTCUSDT", "ETHUSDT"],
                    timeframes=["15m", "1h"],
                    show_spinner=False,
                )
                
                # Should have called for each combination
                assert mock_internal.call_count == 4  # 2 symbols x 2 timeframes
                
                # Should return results for each combination
                assert len(results) == 4
                assert results["BTCUSDT_15m"] == 5
                assert results["BTCUSDT_1h"] == 5
                assert results["ETHUSDT_15m"] == 5
                assert results["ETHUSDT_1h"] == 5


class TestPeriodParsing:
    """Tests for period string parsing."""
    
    def test_parse_period_days(self):
        """Should parse day periods correctly."""
        result = HistoricalDataStore.parse_period("7D")
        assert result == timedelta(days=7)
    
    def test_parse_period_weeks(self):
        """Should parse week periods correctly."""
        result = HistoricalDataStore.parse_period("2W")
        assert result == timedelta(days=14)
    
    def test_parse_period_months(self):
        """Should parse month periods correctly."""
        result = HistoricalDataStore.parse_period("3M")
        assert result == timedelta(days=90)
    
    def test_parse_period_years(self):
        """Should parse year periods correctly."""
        result = HistoricalDataStore.parse_period("1Y")
        assert result == timedelta(days=365)
    
    def test_parse_period_hours(self):
        """Should parse hour periods correctly."""
        result = HistoricalDataStore.parse_period("24H")
        assert result == timedelta(days=1)
    
    def test_parse_period_invalid_raises(self):
        """Should raise ValueError for invalid periods."""
        with pytest.raises(ValueError):
            HistoricalDataStore.parse_period("5X")

