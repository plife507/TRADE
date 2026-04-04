"""
Forge tool specifications (stress testing, synthetic data, parity checks).

NO LEGACY FALLBACKS - Forward coding only.
"""


def get_imports():
    """Return dict of function_name -> import path."""
    from .. import (
        forge_stress_test_tool,
        forge_generate_synthetic_data_tool,
        forge_structure_parity_tool,
        forge_indicator_parity_tool,
    )
    return {
        "forge_stress_test": forge_stress_test_tool,
        "forge_generate_synthetic_data": forge_generate_synthetic_data_tool,
        "forge_structure_parity": forge_structure_parity_tool,
        "forge_indicator_parity": forge_indicator_parity_tool,
    }


SPECS = [
    {
        "name": "forge_stress_test",
        "description": "Run complete Forge stress test suite with hash tracing (audits + backtest validation)",
        "category": "forge",
        "parameters": {
            "validation_plays_dir": {"type": "string", "description": "Directory containing validation plays", "optional": True},
            "skip_audits": {"type": "boolean", "description": "Skip audit steps (registry, structure, indicator, rollup)", "default": False},
            "skip_backtest": {"type": "boolean", "description": "Skip backtest steps (play execution, artifact verify)", "default": False},
            "trace_hashes": {"type": "boolean", "description": "Enable hash tracing for debugging", "default": True},
            "use_synthetic_data": {"type": "boolean", "description": "Use synthetic data for parity checks", "default": True},
            "seed": {"type": "integer", "description": "Random seed for synthetic data", "default": 42},
            "bars_per_tf": {"type": "integer", "description": "Bars per timeframe", "default": 1000},
            "pattern": {"type": "string", "description": "Synthetic data pattern: trending, ranging, volatile, multi_tf_aligned", "default": "trending"},
            "timeframes": {
                "type": "array",
                "description": "Timeframes to generate (default: 1m, 5m, 15m, 1h, 4h)",
                "items": {"type": "string"},
                "optional": True,
            },
        },
        "required": [],
    },
    {
        "name": "forge_generate_synthetic_data",
        "description": "Generate deterministic synthetic candle data for testing",
        "category": "forge",
        "parameters": {
            "symbol": {"type": "string", "description": "Trading symbol", "default": "BTCUSDT"},
            "timeframes": {
                "type": "array",
                "description": "Timeframes to generate (default: 1m, 5m, 15m, 1h, 4h)",
                "items": {"type": "string"},
                "optional": True,
            },
            "bars_per_tf": {"type": "integer", "description": "Number of bars per timeframe", "default": 1000},
            "seed": {"type": "integer", "description": "Random seed for reproducibility", "default": 42},
            "pattern": {"type": "string", "description": "Price pattern: trending, ranging, volatile, multi_tf_aligned", "default": "trending"},
        },
        "required": [],
    },
    {
        "name": "forge_structure_parity",
        "description": "Run structure parity check on all structures in STRUCTURE_REGISTRY",
        "category": "forge",
        "parameters": {
            "seed": {"type": "integer", "description": "Random seed for synthetic data", "default": 42},
            "bars_per_tf": {"type": "integer", "description": "Bars per timeframe", "default": 1000},
            "pattern": {"type": "string", "description": "Synthetic data pattern", "default": "trending"},
        },
        "required": [],
    },
    {
        "name": "forge_indicator_parity",
        "description": "Run indicator parity check on all indicators in INDICATOR_REGISTRY",
        "category": "forge",
        "parameters": {
            "seed": {"type": "integer", "description": "Random seed for synthetic data", "default": 42},
            "bars_per_tf": {"type": "integer", "description": "Bars per timeframe", "default": 1000},
            "pattern": {"type": "string", "description": "Synthetic data pattern", "default": "trending"},
        },
        "required": [],
    },
]
