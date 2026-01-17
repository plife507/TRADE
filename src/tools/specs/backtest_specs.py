"""
Backtest tool specifications.

NO LEGACY FALLBACKS - Forward coding only.
"""


def get_imports():
    """Return dict of function_name -> import path."""
    from .. import (
        backtest_preflight_play_tool,
        backtest_run_play_tool,
        backtest_data_fix_tool,
        backtest_list_plays_tool,
        backtest_indicators_tool,
        backtest_play_normalize_tool,
        backtest_audit_toolkit_tool,
        backtest_audit_rollup_parity_tool,
        backtest_math_parity_tool,
        backtest_audit_snapshot_plumbing_tool,
        verify_artifact_parity_tool,
    )
    return {
        "backtest_list_plays": backtest_list_plays_tool,
        "backtest_preflight": backtest_preflight_play_tool,
        "backtest_run_play": backtest_run_play_tool,
        "backtest_data_fix": backtest_data_fix_tool,
        "backtest_indicators": backtest_indicators_tool,
        "backtest_normalize_play": backtest_play_normalize_tool,
        "backtest_audit_toolkit": backtest_audit_toolkit_tool,
        "backtest_audit_rollup": backtest_audit_rollup_parity_tool,
        "backtest_audit_math_parity": backtest_math_parity_tool,
        "backtest_audit_snapshot_plumbing": backtest_audit_snapshot_plumbing_tool,
        "backtest_verify_artifacts": verify_artifact_parity_tool,
    }


SPECS = [
    # Play tools (Golden Path)
    {
        "name": "backtest_list_plays",
        "description": "List all available Plays for backtesting",
        "category": "backtest.play",
        "parameters": {
            "plays_dir": {"type": "string", "description": "Override Play directory", "optional": True},
        },
        "required": [],
    },
    {
        "name": "backtest_preflight",
        "description": "Run preflight check for an Play backtest (data coverage, warmup). Symbol comes from Play.",
        "category": "backtest.play",
        "parameters": {
            "play_id": {"type": "string", "description": "Play identifier"},
            "env": {"type": "string", "description": "Data environment ('live' or 'demo')", "default": "live"},
            "start": {"type": "string", "description": "Window start datetime", "optional": True},
            "end": {"type": "string", "description": "Window end datetime", "optional": True},
            "fix_gaps": {"type": "boolean", "description": "Auto-fetch missing data", "default": False},
        },
        "required": ["play_id"],
    },
    {
        "name": "backtest_run_play",
        "description": "Run a backtest for an Play (Golden Path). Symbol comes from Play.",
        "category": "backtest.play",
        "parameters": {
            "play_id": {"type": "string", "description": "Play identifier"},
            "env": {"type": "string", "description": "Data environment ('live' or 'demo')", "default": "live"},
            "start": {"type": "string", "description": "Window start datetime", "optional": True},
            "end": {"type": "string", "description": "Window end datetime", "optional": True},
            "smoke": {"type": "boolean", "description": "Run in smoke mode (small window)", "default": False},
            "fix_gaps": {"type": "boolean", "description": "Auto-fetch missing data", "default": True},
        },
        "required": ["play_id"],
    },
    {
        "name": "backtest_data_fix",
        "description": "Fix data for an Play backtest (sync/heal). Symbol comes from Play.",
        "category": "backtest.play",
        "parameters": {
            "play_id": {"type": "string", "description": "Play identifier"},
            "env": {"type": "string", "description": "Data environment", "default": "live"},
            "start": {"type": "string", "description": "Sync from this date", "optional": True},
            "end": {"type": "string", "description": "Sync to this date", "optional": True},
            "max_lookback_days": {"type": "integer", "description": "Max lookback days", "default": 7},
            "sync_to_now": {"type": "boolean", "description": "Sync to current time", "default": False},
            "fill_gaps": {"type": "boolean", "description": "Fill gaps after sync", "default": True},
            "heal": {"type": "boolean", "description": "Run full heal", "default": False},
        },
        "required": ["play_id"],
    },
    {
        "name": "backtest_indicators",
        "description": "Discover indicator keys for an Play. Symbol comes from Play.",
        "category": "backtest.play",
        "parameters": {
            "play_id": {"type": "string", "description": "Play identifier"},
            "data_env": {"type": "string", "description": "Data environment", "default": "live"},
            "compute_values": {"type": "boolean", "description": "Compute actual values", "default": False},
        },
        "required": ["play_id"],
    },
    {
        "name": "backtest_normalize_play",
        "description": "Normalize and validate an Play YAML",
        "category": "backtest.play",
        "parameters": {
            "play_id": {"type": "string", "description": "Play identifier"},
            "plays_dir": {"type": "string", "description": "Override directory", "optional": True},
            "write_in_place": {"type": "boolean", "description": "Write normalized YAML", "default": False},
        },
        "required": ["play_id"],
    },
    # Audit tools
    {
        "name": "backtest_audit_toolkit",
        "description": "Run toolkit contract audit (validates all 42 indicators)",
        "category": "backtest.audit",
        "parameters": {
            "sample_bars": {"type": "integer", "description": "Synthetic OHLCV bars", "default": 2000},
            "seed": {"type": "integer", "description": "Random seed", "default": 1337},
            "fail_on_extras": {"type": "boolean", "description": "Fail if extras found", "default": False},
            "strict": {"type": "boolean", "description": "Fail on any breach", "default": True},
        },
        "required": [],
    },
    {
        "name": "backtest_audit_rollup",
        "description": "Run rollup parity audit (validates 1m price feed accumulation)",
        "category": "backtest.audit",
        "parameters": {
            "n_intervals": {"type": "integer", "description": "Number of intervals", "default": 10},
            "quotes_per_interval": {"type": "integer", "description": "Quotes per interval", "default": 15},
            "seed": {"type": "integer", "description": "Random seed", "default": 1337},
            "tolerance": {"type": "number", "description": "Float tolerance", "default": 1e-10},
        },
        "required": [],
    },
    {
        "name": "backtest_audit_math_parity",
        "description": "Run math parity audit (contract + in-memory parity)",
        "category": "backtest.audit",
        "parameters": {
            "play": {"type": "string", "description": "Path to Play YAML"},
            "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
            "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
            "output_dir": {"type": "string", "description": "Output directory for diffs", "optional": True},
        },
        "required": ["play", "start_date", "end_date"],
    },
    {
        "name": "backtest_audit_snapshot_plumbing",
        "description": "Run snapshot plumbing parity audit (validates data flow). Symbol comes from Play.",
        "category": "backtest.audit",
        "parameters": {
            "play_id": {"type": "string", "description": "Play identifier"},
            "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
            "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
            "max_samples": {"type": "integer", "description": "Max samples", "default": 2000},
            "tolerance": {"type": "number", "description": "Float tolerance", "default": 1e-12},
        },
        "required": ["play_id", "start_date", "end_date"],
    },
    {
        "name": "backtest_verify_artifacts",
        "description": "Verify backtest artifact integrity",
        "category": "backtest.audit",
        "parameters": {
            "play_id": {"type": "string", "description": "Play ID", "optional": True},
            "symbol": {"type": "string", "description": "Trading symbol", "optional": True},
            "run_id": {"type": "string", "description": "Specific run ID", "optional": True},
            "base_dir": {"type": "string", "description": "Base backtests directory", "optional": True},
            "run_dir": {"type": "string", "description": "Direct path to run directory", "optional": True},
        },
        "required": [],
    },
]
