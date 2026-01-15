"""
Forge structure development module.

Provides synthetic data generation and validation harness for developing
new market structure detectors using the incremental/ framework.

Usage:
    from src.forge.structures import StructureDevelopmentHarness

    harness = StructureDevelopmentHarness()
    ohlcv = harness.generate_swing_pattern(n_bars=100)
    results = harness.run_detector("swing", ohlcv, {"lookback": 10})
    assert harness.validate_outputs(results, expected_keys=["high_level", "low_level"])
"""

from src.forge.structures.harness import StructureDevelopmentHarness

__all__ = ["StructureDevelopmentHarness"]
