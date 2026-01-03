"""
Backtest tool specifications.

NO LEGACY FALLBACKS - Forward coding only.
"""


def get_imports():
    """Return dict of function_name -> import path."""
    from .. import (
        backtest_list_systems_tool,
        backtest_get_system_tool,
        backtest_run_tool,
        backtest_prepare_data_tool,
        backtest_verify_data_tool,
        backtest_list_strategies_tool,
        backtest_preflight_idea_card_tool,
        backtest_run_idea_card_tool,
        backtest_data_fix_tool,
        backtest_list_idea_cards_tool,
        backtest_indicators_tool,
        backtest_idea_card_normalize_tool,
        backtest_audit_toolkit_tool,
        backtest_audit_rollup_parity_tool,
        backtest_math_parity_tool,
        backtest_audit_snapshot_plumbing_tool,
        verify_artifact_parity_tool,
    )
    return {
        "backtest_list_systems": backtest_list_systems_tool,
        "backtest_get_system": backtest_get_system_tool,
        "backtest_run": backtest_run_tool,
        "backtest_prepare_data": backtest_prepare_data_tool,
        "backtest_verify_data": backtest_verify_data_tool,
        "backtest_list_strategies": backtest_list_strategies_tool,
        "backtest_list_idea_cards": backtest_list_idea_cards_tool,
        "backtest_preflight": backtest_preflight_idea_card_tool,
        "backtest_run_idea_card": backtest_run_idea_card_tool,
        "backtest_data_fix": backtest_data_fix_tool,
        "backtest_indicators": backtest_indicators_tool,
        "backtest_normalize_idea_card": backtest_idea_card_normalize_tool,
        "backtest_audit_toolkit": backtest_audit_toolkit_tool,
        "backtest_audit_rollup": backtest_audit_rollup_parity_tool,
        "backtest_audit_math_parity": backtest_math_parity_tool,
        "backtest_audit_snapshot_plumbing": backtest_audit_snapshot_plumbing_tool,
        "backtest_verify_artifacts": verify_artifact_parity_tool,
    }


SPECS = [
    # System tools
    {
        "name": "backtest_list_systems",
        "description": "List all available backtest system configurations",
        "category": "backtest.systems",
        "parameters": {},
        "required": [],
    },
    {
        "name": "backtest_get_system",
        "description": "Get detailed information about a system configuration",
        "category": "backtest.systems",
        "parameters": {
            "system_id": {"type": "string", "description": "System configuration ID"},
        },
        "required": ["system_id"],
    },
    {
        "name": "backtest_run",
        "description": "Run a backtest for a system configuration",
        "category": "backtest.run",
        "parameters": {
            "system_id": {"type": "string", "description": "System configuration ID"},
            "window_name": {"type": "string", "description": "Window to run (hygiene or test)", "default": "hygiene"},
            "write_artifacts": {"type": "boolean", "description": "Whether to write run artifacts", "default": True},
        },
        "required": ["system_id"],
    },
    {
        "name": "backtest_prepare_data",
        "description": "Prepare data for backtesting based on system config",
        "category": "backtest.data",
        "parameters": {
            "system_id": {"type": "string", "description": "System configuration ID"},
            "fresh_db": {"type": "boolean", "description": "If true, delete all data first (opt-in reset)", "default": False},
        },
        "required": ["system_id"],
    },
    {
        "name": "backtest_verify_data",
        "description": "Verify data quality for a backtest run",
        "category": "backtest.data",
        "parameters": {
            "system_id": {"type": "string", "description": "System configuration ID"},
            "window_name": {"type": "string", "description": "Window to verify data for", "default": "hygiene"},
            "heal_gaps": {"type": "boolean", "description": "If true, attempt to heal gaps", "default": True},
        },
        "required": ["system_id"],
    },
    {
        "name": "backtest_list_strategies",
        "description": "List all available strategies",
        "category": "backtest.strategies",
        "parameters": {},
        "required": [],
    },
    # IdeaCard tools (Golden Path)
    {
        "name": "backtest_list_idea_cards",
        "description": "List all available IdeaCards for backtesting",
        "category": "backtest.ideacard",
        "parameters": {
            "idea_cards_dir": {"type": "string", "description": "Override IdeaCard directory", "optional": True},
        },
        "required": [],
    },
    {
        "name": "backtest_preflight",
        "description": "Run preflight check for an IdeaCard backtest (data coverage, warmup)",
        "category": "backtest.ideacard",
        "parameters": {
            "idea_card_id": {"type": "string", "description": "IdeaCard identifier"},
            "env": {"type": "string", "description": "Data environment ('live' or 'demo')", "default": "live"},
            "symbol": {"type": "string", "description": "Override symbol", "optional": True},
            "start": {"type": "string", "description": "Window start datetime", "optional": True},
            "end": {"type": "string", "description": "Window end datetime", "optional": True},
            "fix_gaps": {"type": "boolean", "description": "Auto-fetch missing data", "default": False},
        },
        "required": ["idea_card_id"],
    },
    {
        "name": "backtest_run_idea_card",
        "description": "Run a backtest for an IdeaCard (Golden Path)",
        "category": "backtest.ideacard",
        "parameters": {
            "idea_card_id": {"type": "string", "description": "IdeaCard identifier"},
            "env": {"type": "string", "description": "Data environment ('live' or 'demo')", "default": "live"},
            "symbol": {"type": "string", "description": "Override symbol", "optional": True},
            "start": {"type": "string", "description": "Window start datetime", "optional": True},
            "end": {"type": "string", "description": "Window end datetime", "optional": True},
            "smoke": {"type": "boolean", "description": "Run in smoke mode (small window)", "default": False},
            "fix_gaps": {"type": "boolean", "description": "Auto-fetch missing data", "default": True},
        },
        "required": ["idea_card_id"],
    },
    {
        "name": "backtest_data_fix",
        "description": "Fix data for an IdeaCard backtest (sync/heal)",
        "category": "backtest.ideacard",
        "parameters": {
            "idea_card_id": {"type": "string", "description": "IdeaCard identifier"},
            "env": {"type": "string", "description": "Data environment", "default": "live"},
            "symbol": {"type": "string", "description": "Override symbol", "optional": True},
            "start": {"type": "string", "description": "Sync from this date", "optional": True},
            "end": {"type": "string", "description": "Sync to this date", "optional": True},
            "max_lookback_days": {"type": "integer", "description": "Max lookback days", "default": 7},
            "sync_to_now": {"type": "boolean", "description": "Sync to current time", "default": False},
            "fill_gaps": {"type": "boolean", "description": "Fill gaps after sync", "default": True},
            "heal": {"type": "boolean", "description": "Run full heal", "default": False},
        },
        "required": ["idea_card_id"],
    },
    {
        "name": "backtest_indicators",
        "description": "Discover indicator keys for an IdeaCard",
        "category": "backtest.ideacard",
        "parameters": {
            "idea_card_id": {"type": "string", "description": "IdeaCard identifier"},
            "data_env": {"type": "string", "description": "Data environment", "default": "live"},
            "symbol": {"type": "string", "description": "Override symbol", "optional": True},
            "compute_values": {"type": "boolean", "description": "Compute actual values", "default": False},
        },
        "required": ["idea_card_id"],
    },
    {
        "name": "backtest_normalize_idea_card",
        "description": "Normalize and validate an IdeaCard YAML",
        "category": "backtest.ideacard",
        "parameters": {
            "idea_card_id": {"type": "string", "description": "IdeaCard identifier"},
            "idea_cards_dir": {"type": "string", "description": "Override directory", "optional": True},
            "write_in_place": {"type": "boolean", "description": "Write normalized YAML", "default": False},
        },
        "required": ["idea_card_id"],
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
            "idea_card": {"type": "string", "description": "Path to IdeaCard YAML"},
            "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
            "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
            "output_dir": {"type": "string", "description": "Output directory for diffs", "optional": True},
        },
        "required": ["idea_card", "start_date", "end_date"],
    },
    {
        "name": "backtest_audit_snapshot_plumbing",
        "description": "Run snapshot plumbing parity audit (validates data flow)",
        "category": "backtest.audit",
        "parameters": {
            "idea_card_id": {"type": "string", "description": "IdeaCard identifier"},
            "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
            "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
            "symbol": {"type": "string", "description": "Override symbol", "optional": True},
            "max_samples": {"type": "integer", "description": "Max samples", "default": 2000},
            "tolerance": {"type": "number", "description": "Float tolerance", "default": 1e-12},
        },
        "required": ["idea_card_id", "start_date", "end_date"],
    },
    {
        "name": "backtest_verify_artifacts",
        "description": "Verify backtest artifact integrity",
        "category": "backtest.audit",
        "parameters": {
            "idea_card_id": {"type": "string", "description": "IdeaCard ID", "optional": True},
            "symbol": {"type": "string", "description": "Trading symbol", "optional": True},
            "run_id": {"type": "string", "description": "Specific run ID", "optional": True},
            "base_dir": {"type": "string", "description": "Base backtests directory", "optional": True},
            "run_dir": {"type": "string", "description": "Direct path to run directory", "optional": True},
        },
        "required": [],
    },
]
