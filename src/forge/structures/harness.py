"""
Structure Development Harness for testing incremental detectors.

Provides synthetic data generation and validation tools for developing
market structure detectors in a controlled environment.
"""

import numpy as np
from typing import Any

from src.backtest.incremental.batch_wrapper import run_detector_batch
from src.backtest.incremental.registry import STRUCTURE_REGISTRY, list_structure_types


class StructureDevelopmentHarness:
    """Development harness for testing incremental structure detectors."""
    
    def __init__(self, seed: int | None = 42):
        """Initialize harness with optional random seed."""
        self.seed = seed
        if seed is not None:
            np.random.seed(seed)
    
    def generate_random_walk(
        self,
        n_bars: int = 100,
        start_price: float = 100.0,
        volatility: float = 0.02,
        trend: float = 0.0,
    ) -> dict[str, np.ndarray]:
        """Generate random walk OHLCV data."""
        if self.seed is not None:
            np.random.seed(self.seed)
        
        returns = np.random.normal(trend, volatility, n_bars)
        prices = start_price * np.exp(np.cumsum(returns))
        close = prices
        open_prices = np.roll(close, 1)
        open_prices[0] = start_price
        spread = volatility * start_price
        high = np.maximum(open_prices, close) + np.abs(np.random.normal(0, spread, n_bars))
        low = np.minimum(open_prices, close) - np.abs(np.random.normal(0, spread, n_bars))
        volume = np.random.uniform(1000, 5000, n_bars)
        
        return {"open": open_prices, "high": high, "low": low, "close": close, "volume": volume}
    
    def generate_swing_pattern(
        self,
        n_bars: int = 100,
        swing_period: int = 20,
        amplitude: float = 10.0,
        base_price: float = 100.0,
        noise: float = 0.5,
    ) -> dict[str, np.ndarray]:
        """Generate OHLCV data with clear swing high/low patterns."""
        if self.seed is not None:
            np.random.seed(self.seed)
        
        t = np.arange(n_bars)
        wave = amplitude * np.sin(2 * np.pi * t / swing_period)
        close = base_price + wave + np.random.normal(0, noise, n_bars)
        open_prices = np.roll(close, 1)
        open_prices[0] = close[0]
        spread = amplitude * 0.1
        high = np.maximum(open_prices, close) + np.abs(np.random.normal(0, spread, n_bars))
        low = np.minimum(open_prices, close) - np.abs(np.random.normal(0, spread, n_bars))
        volume = np.random.uniform(1000, 5000, n_bars)
        
        return {"open": open_prices, "high": high, "low": low, "close": close, "volume": volume}
    
    def generate_trend_pattern(
        self,
        n_bars: int = 100,
        trend_strength: float = 0.5,
        pullback_depth: float = 0.3,
        noise: float = 0.2,
    ) -> dict[str, np.ndarray]:
        """Generate OHLCV data with clear trend (HH/HL or LL/LH)."""
        if self.seed is not None:
            np.random.seed(self.seed)
        
        close = np.zeros(n_bars)
        close[0] = 100.0
        for i in range(1, n_bars):
            trend_move = trend_strength * np.random.uniform(0.5, 1.5)
            if np.random.random() < 0.2:
                pullback = -np.sign(trend_strength) * pullback_depth * abs(trend_strength)
                close[i] = close[i-1] + pullback + np.random.normal(0, noise)
            else:
                close[i] = close[i-1] + trend_move + np.random.normal(0, noise)
        
        open_prices = np.roll(close, 1)
        open_prices[0] = close[0]
        spread = abs(trend_strength) * 0.5
        high = np.maximum(open_prices, close) + np.abs(np.random.normal(0, spread, n_bars))
        low = np.minimum(open_prices, close) - np.abs(np.random.normal(0, spread, n_bars))
        volume = np.random.uniform(1000, 5000, n_bars)
        
        return {"open": open_prices, "high": high, "low": low, "close": close, "volume": volume}
    
    def run_detector(
        self,
        detector_type: str,
        ohlcv: dict[str, np.ndarray],
        params: dict[str, Any] | None = None,
    ) -> dict[str, np.ndarray]:
        """Run an incremental detector in batch mode."""
        params = params or {}
        return run_detector_batch(detector_type, ohlcv, params)
    
    def list_detectors(self) -> list[str]:
        """List all registered detector types."""
        return list_structure_types()
    
    def get_detector_info(self, detector_type: str) -> dict[str, Any]:
        """Get info about a detector type."""
        if detector_type not in STRUCTURE_REGISTRY:
            raise ValueError(f"Unknown detector: {detector_type}")
        detector_class = STRUCTURE_REGISTRY[detector_type]
        return {"type": detector_type, "class": detector_class.__name__, "doc": detector_class.__doc__}
    
    def validate_outputs(
        self,
        results: dict[str, np.ndarray],
        expected_keys: list[str] | None = None,
        no_all_nan: bool = True,
    ) -> bool:
        """Validate detector outputs."""
        if expected_keys:
            for key in expected_keys:
                assert key in results, f"Missing expected key: {key}"
        if no_all_nan:
            for key, arr in results.items():
                assert not np.all(np.isnan(arr)), f"Output {key} is all NaN"
        return True
    
    def test_determinism(
        self,
        detector_type: str,
        ohlcv: dict[str, np.ndarray],
        params: dict[str, Any] | None = None,
        runs: int = 3,
    ) -> bool:
        """Test that detector produces identical outputs on repeated runs."""
        params = params or {}
        results_list = [self.run_detector(detector_type, ohlcv, params) for _ in range(runs)]
        first = results_list[0]
        for i, other in enumerate(results_list[1:], 2):
            for key in first:
                assert key in other, f"Run {i} missing key: {key}"
                first_arr = first[key]
                other_arr = other[key]
                nan_match = np.isnan(first_arr) == np.isnan(other_arr)
                val_match = np.where(np.isnan(first_arr), True, first_arr == other_arr)
                assert np.all(nan_match & val_match), f"Run {i} differs for key {key}"
        return True
    
    def summarize_outputs(self, results: dict[str, np.ndarray]) -> dict[str, dict]:
        """Generate summary statistics for detector outputs."""
        summary = {}
        for key, arr in results.items():
            valid = arr[~np.isnan(arr)]
            summary[key] = {
                "count": len(arr),
                "valid": len(valid),
                "nan_pct": (len(arr) - len(valid)) / len(arr) * 100,
                "min": float(np.min(valid)) if len(valid) > 0 else None,
                "max": float(np.max(valid)) if len(valid) > 0 else None,
                "mean": float(np.mean(valid)) if len(valid) > 0 else None,
            }
        return summary
