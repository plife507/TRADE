"""
Historical data capture module.

Runs as a background service to collect and store:
- OHLCV candles (multiple timeframes)
- Funding rates
- Open interest snapshots

Uses Bybit PUBLIC endpoints only - no impact on trading rate limits.
"""

import os
import time
import json
import threading
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from ..exchanges.bybit_client import BybitClient
from ..config.config import get_config
from ..utils.logger import get_logger
from ..utils.helpers import safe_float


class DataCapture:
    """
    Historical data collection service.
    
    Features:
    - Incremental updates (only fetches new data)
    - Multiple timeframes support
    - Handles gaps and backfills
    - Runs in background thread
    """
    
    def __init__(self):
        """Initialize data capture."""
        self.config = get_config()
        self.logger = get_logger()
        
        # Use separate DATA API key (read-only) to avoid rate limit conflicts
        data_key, data_secret = self.config.bybit.get_data_credentials()
        
        # Initialize client with official pybit library
        self.client = BybitClient(
            api_key=data_key if data_key else None,
            api_secret=data_secret if data_secret else None,
            use_demo=self.config.bybit.use_demo,  # Demo or live API
        )
        
        # Configuration
        self.symbols = self.config.data.capture_symbols
        self.timeframes = self.config.data.capture_timeframes
        self.interval = self.config.data.capture_interval_seconds
        
        # Storage paths
        self.base_dir = Path(self.config.data.data_dir)
        self.ohlcv_dir = Path(self.config.data.ohlcv_dir)
        self.funding_dir = Path(self.config.data.funding_dir)
        self.oi_dir = Path(self.config.data.oi_dir)
        
        # Create directories
        for dir_path in [self.ohlcv_dir, self.funding_dir, self.oi_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        # State
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._metadata = self._load_metadata()
    
    # ==================== Metadata Management ====================
    
    def _metadata_path(self) -> Path:
        return self.base_dir / "metadata.json"
    
    def _load_metadata(self) -> Dict:
        """Load capture metadata (last update times, etc.)."""
        path = self._metadata_path()
        if path.exists():
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"ohlcv": {}, "funding": {}, "oi": {}}
    
    def _save_metadata(self):
        """Save capture metadata."""
        try:
            with open(self._metadata_path(), "w") as f:
                json.dump(self._metadata, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Failed to save metadata: {e}")
    
    # ==================== OHLCV Capture ====================
    
    def _ohlcv_file(self, symbol: str, timeframe: str) -> Path:
        """Get OHLCV file path for symbol/timeframe."""
        return self.ohlcv_dir / f"{symbol}_{timeframe}.csv"
    
    def _capture_ohlcv(self, symbol: str, timeframe: str):
        """
        Capture OHLCV data for a symbol/timeframe.
        
        Performs incremental update - only fetches candles newer than last stored.
        """
        file_path = self._ohlcv_file(symbol, timeframe)
        meta_key = f"{symbol}_{timeframe}"
        
        # Load existing data
        existing_df = None
        last_ts = None
        
        if file_path.exists():
            try:
                existing_df = pd.read_csv(file_path, parse_dates=["timestamp"])
                if not existing_df.empty:
                    last_ts = existing_df["timestamp"].max()
            except Exception as e:
                self.logger.warning(f"Failed to load existing OHLCV for {meta_key}: {e}")
        
        # Fetch new data
        try:
            # Calculate start time (after last candle)
            start_ms = None
            if last_ts is not None:
                start_ms = int(last_ts.timestamp() * 1000) + 1
            
            new_df = self.client.get_klines(
                symbol=symbol,
                interval=timeframe,
                limit=1000,
                start=start_ms,
            )
            
            if new_df.empty:
                return
            
            # Merge with existing
            if existing_df is not None and not existing_df.empty:
                # Remove any overlap
                new_df = new_df[new_df["timestamp"] > last_ts]
                if not new_df.empty:
                    combined = pd.concat([existing_df, new_df], ignore_index=True)
                    combined = combined.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
                else:
                    combined = existing_df
            else:
                combined = new_df
            
            # Save
            combined.to_csv(file_path, index=False)
            
            # Update metadata
            self._metadata["ohlcv"][meta_key] = {
                "last_update": datetime.now().isoformat(),
                "rows": len(combined),
                "last_candle": combined["timestamp"].max().isoformat() if not combined.empty else None,
            }
            
            if not new_df.empty:
                self.logger.debug(f"Captured {len(new_df)} new candles for {meta_key}")
            
        except Exception as e:
            self.logger.warning(f"Failed to capture OHLCV for {meta_key}: {e}")
    
    # ==================== Funding Rate Capture ====================
    
    def _funding_file(self, symbol: str) -> Path:
        """Get funding rate file path."""
        return self.funding_dir / f"{symbol}.csv"
    
    def _capture_funding(self, symbol: str):
        """Capture funding rate data."""
        file_path = self._funding_file(symbol)
        
        # Load existing
        existing_df = None
        if file_path.exists():
            try:
                existing_df = pd.read_csv(file_path)
            except Exception:
                pass
        
        try:
            # Fetch recent funding rates
            data = self.client.get_funding_rate(symbol, limit=200)
            
            if not data:
                return
            
            # Convert to DataFrame
            records = []
            for entry in data:
                records.append({
                    "timestamp": datetime.fromtimestamp(int(entry.get("fundingRateTimestamp", 0)) / 1000),
                    "funding_rate": safe_float(entry.get("fundingRate")),
                    "symbol": symbol,
                })
            
            new_df = pd.DataFrame(records)
            
            if existing_df is not None and not existing_df.empty:
                existing_df["timestamp"] = pd.to_datetime(existing_df["timestamp"])
                combined = pd.concat([existing_df, new_df], ignore_index=True)
                combined = combined.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
            else:
                combined = new_df
            
            combined.to_csv(file_path, index=False)
            
            self._metadata["funding"][symbol] = {
                "last_update": datetime.now().isoformat(),
                "rows": len(combined),
            }
            
        except Exception as e:
            self.logger.warning(f"Failed to capture funding for {symbol}: {e}")
    
    # ==================== Open Interest Capture ====================
    
    def _oi_file(self, symbol: str) -> Path:
        """Get OI file path."""
        return self.oi_dir / f"{symbol}.csv"
    
    def _capture_oi(self, symbol: str):
        """Capture open interest snapshot."""
        file_path = self._oi_file(symbol)
        
        try:
            data = self.client.get_open_interest(symbol, limit=1)
            
            if not data:
                return
            
            entry = data[0]
            record = {
                "timestamp": datetime.now().isoformat(),
                "open_interest": safe_float(entry.get("openInterest")),
                "symbol": symbol,
            }
            
            # Append to file
            if file_path.exists():
                df = pd.read_csv(file_path)
                df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
            else:
                df = pd.DataFrame([record])
            
            df.to_csv(file_path, index=False)
            
            self._metadata["oi"][symbol] = {
                "last_update": datetime.now().isoformat(),
                "rows": len(df),
            }
            
        except Exception as e:
            self.logger.warning(f"Failed to capture OI for {symbol}: {e}")
    
    # ==================== Main Capture Loop ====================
    
    def _capture_cycle(self):
        """Run one capture cycle for all symbols/timeframes."""
        for symbol in self.symbols:
            # OHLCV for each timeframe
            for tf in self.timeframes:
                self._capture_ohlcv(symbol, tf)
                time.sleep(0.1)  # Small delay between requests
            
            # Funding rate
            self._capture_funding(symbol)
            time.sleep(0.1)
            
            # Open interest
            self._capture_oi(symbol)
            time.sleep(0.1)
        
        # Save metadata
        self._save_metadata()
    
    def _run_loop(self):
        """Background capture loop."""
        self.logger.info(f"Data capture started for {self.symbols}")
        
        while self._running:
            try:
                self._capture_cycle()
            except Exception as e:
                self.logger.error(f"Capture cycle error: {e}")
            
            # Wait for next interval
            for _ in range(int(self.interval)):
                if not self._running:
                    break
                time.sleep(1)
        
        self.logger.info("Data capture stopped")
    
    # ==================== Control Methods ====================
    
    def start(self):
        """Start background data capture."""
        if self._running:
            self.logger.warning("Data capture already running")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop background data capture."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
    
    def run_once(self):
        """Run a single capture cycle (blocking)."""
        self._capture_cycle()
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    def get_status(self) -> Dict:
        """Get capture status."""
        return {
            "running": self._running,
            "symbols": self.symbols,
            "timeframes": self.timeframes,
            "interval_seconds": self.interval,
            "metadata": self._metadata,
        }


# Singleton instance
_data_capture: Optional[DataCapture] = None


def get_data_capture() -> DataCapture:
    """Get or create the global DataCapture instance."""
    global _data_capture
    if _data_capture is None:
        _data_capture = DataCapture()
    return _data_capture

