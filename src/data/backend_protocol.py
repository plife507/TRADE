"""
Backend Protocol for Historical Data Storage.

This module defines the interface that all historical data backends must implement.
Currently DuckDB is the primary backend, with MongoDB planned for the future.

The protocol ensures that all higher-level code (tools, sessions, warm-up, backtests)
depends only on this interface and not on backend-specific implementations.

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │              Historical Data Interface                       │
    │  (get_ohlcv, append_ohlcv, get_funding, get_oi, etc.)       │
    └─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
    ┌─────────▼─────────┐         ┌──────────▼─────────┐
    │   DuckDBBackend   │         │   MongoBackend     │
    │   (current)       │         │   (future)         │
    └───────────────────┘         └────────────────────┘

Usage:
    # All code should use the interface functions, not backends directly
    from src.data.historical_data_store import get_ohlcv, append_ohlcv
    
    # Backend selection happens at initialization via config
    # HIST_BACKEND=duckdb or HIST_BACKEND=mongo
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
import pandas as pd

from ..config.constants import DataEnv


class HistoricalBackend(ABC):
    """
    Abstract base class for historical data storage backends.
    
    This protocol defines the methods that all backends must implement
    to be used by HistoricalDataStore and higher-level data interfaces.
    
    Backends are responsible for:
    - OHLCV candle storage and retrieval
    - Funding rate storage and retrieval
    - Open interest storage and retrieval
    - Metadata management
    - Database-specific optimizations
    
    Backends are NOT responsible for:
    - API fetching (done by HistoricalDataStore)
    - Environment routing (done by HistoricalDataStore)
    - Caching (done by higher layers)
    """
    
    # ==========================================================================
    # Connection Management
    # ==========================================================================
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to the database.
        
        Returns:
            True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    def close(self):
        """Close the database connection."""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connected to the database."""
        pass
    
    # ==========================================================================
    # OHLCV Data
    # ==========================================================================
    
    @abstractmethod
    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """
        Get OHLCV data for a symbol/timeframe.
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            timeframe: Candle timeframe (e.g., "15m", "1h")
            start: Start datetime (inclusive)
            end: End datetime (inclusive)
            
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
            Sorted by timestamp ascending
        """
        pass
    
    @abstractmethod
    def append_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
    ) -> int:
        """
        Append OHLCV data for a symbol/timeframe.
        
        Should handle upserts (update existing, insert new).
        
        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe
            df: DataFrame with OHLCV data
            
        Returns:
            Number of rows written
        """
        pass
    
    @abstractmethod
    def get_ohlcv_range(
        self,
        symbol: str,
        timeframe: str,
    ) -> dict[str, Any]:
        """
        Get the time range of stored OHLCV data.
        
        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe
            
        Returns:
            Dict with keys: first_timestamp, last_timestamp, count
        """
        pass
    
    # ==========================================================================
    # Funding Rate Data
    # ==========================================================================
    
    @abstractmethod
    def get_funding(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """
        Get funding rate data for a symbol.
        
        Args:
            symbol: Trading symbol
            start: Start datetime
            end: End datetime
            
        Returns:
            DataFrame with columns: timestamp, funding_rate
        """
        pass
    
    @abstractmethod
    def append_funding(
        self,
        symbol: str,
        df: pd.DataFrame,
    ) -> int:
        """
        Append funding rate data for a symbol.
        
        Args:
            symbol: Trading symbol
            df: DataFrame with funding rate data
            
        Returns:
            Number of rows written
        """
        pass
    
    # ==========================================================================
    # Open Interest Data
    # ==========================================================================
    
    @abstractmethod
    def get_open_interest(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """
        Get open interest data for a symbol.
        
        Args:
            symbol: Trading symbol
            start: Start datetime
            end: End datetime
            
        Returns:
            DataFrame with columns: timestamp, open_interest
        """
        pass
    
    @abstractmethod
    def append_open_interest(
        self,
        symbol: str,
        df: pd.DataFrame,
    ) -> int:
        """
        Append open interest data for a symbol.
        
        Args:
            symbol: Trading symbol
            df: DataFrame with open interest data
            
        Returns:
            Number of rows written
        """
        pass
    
    # ==========================================================================
    # Metadata and Maintenance
    # ==========================================================================
    
    @abstractmethod
    def get_symbol_list(self) -> list[str]:
        """
        Get list of all symbols with stored data.

        Returns:
            List of symbol strings
        """
        pass
    
    @abstractmethod
    def get_database_stats(self) -> dict[str, Any]:
        """
        Get database statistics.

        Returns:
            Dict with storage stats (symbols, candle counts, size, etc.)
        """
        pass
    
    @abstractmethod
    def delete_symbol(self, symbol: str) -> int:
        """
        Delete all data for a symbol.
        
        Args:
            symbol: Symbol to delete
            
        Returns:
            Number of records deleted
        """
        pass
    
    @abstractmethod
    def vacuum(self):
        """Reclaim space after deletions (if applicable)."""
        pass


class MongoBackend(HistoricalBackend):
    """
    MongoDB backend for historical data storage (placeholder for future implementation).
    
    This backend will use MongoDB time-series collections for efficient
    storage and querying of OHLCV, funding, and open interest data.
    
    Collection Schema (planned):
    
    ohlcv_live / ohlcv_demo:
        {
            "symbol": str,
            "timeframe": str,
            "timestamp": datetime,  # Time field for time-series
            "open": float,
            "high": float,
            "low": float,
            "close": float,
            "volume": float,
        }
        Index: (symbol, timeframe, timestamp) - unique
        Time-series: metaField="symbol", timeField="timestamp"
    
    funding_rates_live / funding_rates_demo:
        {
            "symbol": str,
            "timestamp": datetime,
            "funding_rate": float,
        }
        Index: (symbol, timestamp) - unique
    
    open_interest_live / open_interest_demo:
        {
            "symbol": str,
            "timestamp": datetime,
            "open_interest": float,
        }
        Index: (symbol, timestamp) - unique
    
    Configuration:
        MONGO_URI: MongoDB connection string
        MONGO_DATABASE: Database name (default: "trade_data")
        HIST_BACKEND: Set to "mongo" to use this backend
    
    Migration:
        A migration tool will be provided to copy data from DuckDB to MongoDB.
        See docs/architecture/LIVE_VS_DEMO_DATA.md for migration instructions.
    """
    
    def __init__(self, env: DataEnv, connection_string: str | None = None, database: str | None = None):
        """
        Initialize MongoDB backend.
        
        Args:
            env: Data environment ("live" or "demo")
            connection_string: MongoDB connection string (from config if None)
            database: Database name (from config if None)
        """
        self.env = env
        self.connection_string = connection_string
        self.database = database
        
        # Collection names are env-specific
        self.collection_ohlcv = f"ohlcv_{env}"
        self.collection_funding = f"funding_rates_{env}"
        self.collection_oi = f"open_interest_{env}"
        
        # MongoDB client (lazy init)
        self._client = None
        self._db = None
    
    def connect(self) -> bool:
        """Connect to MongoDB."""
        # TODO: Implement when MongoDB backend is needed
        raise NotImplementedError(
            "MongoDB backend not yet implemented. "
            "Set HIST_BACKEND=duckdb to use DuckDB."
        )
    
    def close(self):
        """Close MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
    
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._client is not None
    
    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Get OHLCV data from MongoDB."""
        raise NotImplementedError("MongoDB backend not yet implemented")
    
    def append_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
    ) -> int:
        """Append OHLCV data to MongoDB."""
        raise NotImplementedError("MongoDB backend not yet implemented")
    
    def get_ohlcv_range(
        self,
        symbol: str,
        timeframe: str,
    ) -> dict[str, Any]:
        """Get OHLCV time range from MongoDB."""
        raise NotImplementedError("MongoDB backend not yet implemented")
    
    def get_funding(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Get funding rate data from MongoDB."""
        raise NotImplementedError("MongoDB backend not yet implemented")
    
    def append_funding(
        self,
        symbol: str,
        df: pd.DataFrame,
    ) -> int:
        """Append funding rate data to MongoDB."""
        raise NotImplementedError("MongoDB backend not yet implemented")
    
    def get_open_interest(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Get open interest data from MongoDB."""
        raise NotImplementedError("MongoDB backend not yet implemented")
    
    def append_open_interest(
        self,
        symbol: str,
        df: pd.DataFrame,
    ) -> int:
        """Append open interest data to MongoDB."""
        raise NotImplementedError("MongoDB backend not yet implemented")
    
    def get_symbol_list(self) -> list[str]:
        """Get symbol list from MongoDB."""
        raise NotImplementedError("MongoDB backend not yet implemented")
    
    def get_database_stats(self) -> dict[str, Any]:
        """Get database stats from MongoDB."""
        raise NotImplementedError("MongoDB backend not yet implemented")
    
    def delete_symbol(self, symbol: str) -> int:
        """Delete symbol data from MongoDB."""
        raise NotImplementedError("MongoDB backend not yet implemented")
    
    def vacuum(self):
        """No-op for MongoDB (automatic cleanup)."""
        pass


# ==============================================================================
# Backend Factory
# ==============================================================================

def get_backend(env: DataEnv, backend_type: str = "duckdb") -> HistoricalBackend:
    """
    Factory function to get the appropriate backend.
    
    Args:
        env: Data environment ("live" or "demo")
        backend_type: Backend type ("duckdb" or "mongo")
        
    Returns:
        HistoricalBackend instance
        
    Raises:
        ValueError: If backend_type is not supported
    """
    if backend_type == "duckdb":
        # DuckDB is currently implemented directly in HistoricalDataStore
        # This factory will be used when we refactor to separate the backend
        raise NotImplementedError(
            "Use HistoricalDataStore directly for DuckDB backend"
        )
    elif backend_type == "mongo":
        return MongoBackend(env=env)
    else:
        raise ValueError(f"Unknown backend type: {backend_type}")

