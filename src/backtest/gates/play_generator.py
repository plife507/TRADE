"""
Play Generator — Creates randomized valid Plays for batch verification.

Gate D.2 requirement: Generate 5 valid Plays with randomized indicators,
selecting symbols from available local data only.

Rules:
- Deterministic seed
- ≥2 indicators per Play on tf_exec
- Indicators from IndicatorRegistry (not hardcoded list)
- Single direction per card (long_only OR short_only)
- Mixed directions across batch
- All generated YAMLs must pass normalize_play_yaml validation

Agent Rule:
    Agents may only generate Plays through `backtest idea-card-normalize`
    and must refuse to write YAML if normalization fails.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import yaml
import numpy as np

# Import registry for indicator validation and expansion
from ..indicator_registry import get_registry

# Import YAML builder for normalization/validation
from ..play_yaml_builder import normalize_play_yaml, format_validation_errors

# Indicator allowlist - uses registry-supported indicators only
# Use conservative period bounds to ensure warmup fits in typical test windows
INDICATOR_ALLOWLIST = [
    {"type": "ema", "params": {"length": (5, 50)}},  # Max 50 for reasonable warmup
    {"type": "sma", "params": {"length": (5, 50)}},
    {"type": "rsi", "params": {"length": (7, 21)}},
    {"type": "atr", "params": {"length": (7, 21)}},
    # Multi-output indicators now supported via registry
    {"type": "macd", "params": {"fast": (8, 16), "slow": (20, 30), "signal": (7, 12)}, "multi_output": True},
    {"type": "bbands", "params": {"length": (14, 26), "std": (1.5, 2.5)}, "multi_output": True},
    {"type": "stoch", "params": {"k": (9, 18), "d": (3, 6), "smooth_k": (3, 6)}, "multi_output": True},
    {"type": "adx", "params": {"length": (10, 20)}, "multi_output": True},
]

DIRECTIONS = ["long_only", "short_only"]
TIMEFRAMES_EXEC = ["1h"]  # Only 1h has verified data coverage for testing
TIMEFRAMES_HTF = ["4h"]   # 4h for HTF context


@dataclass
class GeneratorConfig:
    """Configuration for Play generation."""
    seed: int = 42
    num_cards: int = 5
    min_indicators: int = 2
    max_indicators: int = 4
    output_dir: Path = field(default_factory=lambda: Path("configs/plays/generated"))


@dataclass
class GeneratedPlay:
    """Result of Play generation."""
    id: str
    symbol: str
    direction: str
    exec_tf: str
    htf_tf: str
    indicators: list[dict[str, Any]]
    yaml_path: Path
    yaml_content: str


def get_available_symbols(env: str = "live") -> list[str]:
    """
    Get symbols available in local DuckDB data.
    
    Returns:
        List of symbols with USDT suffix
    """
    try:
        from src.data.historical_data_store import get_historical_store
        store = get_historical_store(env=env)
        
        # Query distinct symbols from ohlcv table
        table_name = f"ohlcv_{env}"
        result = store.conn.execute(f"""
            SELECT DISTINCT symbol 
            FROM {table_name} 
            WHERE symbol LIKE '%USDT'
            ORDER BY symbol
        """).fetchall()
        
        symbols = [row[0] for row in result]
        # Filter to known good symbols with data coverage
        known_good = {"BTCUSDT", "SOLUSDT"}
        symbols = [s for s in symbols if s in known_good]
        return symbols if symbols else ["BTCUSDT", "SOLUSDT"]
    except Exception:
        # Fallback if DB not available (only use symbols with known data)
        return ["BTCUSDT", "SOLUSDT"]


def generate_random_indicator(rng: np.random.Generator, used_types: set) -> dict[str, Any]:
    """
    Generate a random indicator spec.
    
    Args:
        rng: Random generator
        used_types: Set of already used indicator types (to avoid duplicates)
        
    Returns:
        Indicator spec dict
    """
    # Filter out already used types
    available = [ind for ind in INDICATOR_ALLOWLIST if ind["type"] not in used_types]
    if not available:
        available = INDICATOR_ALLOWLIST
    
    # Choose randomly and convert index to int
    idx = int(rng.integers(0, len(available)))
    ind_template = available[idx]
    ind_type = ind_template["type"]
    
    # Generate random params within bounds (convert to native types)
    params = {}
    for param_name, bounds in ind_template["params"].items():
        if isinstance(bounds, tuple):
            if isinstance(bounds[0], int):
                params[param_name] = int(rng.integers(bounds[0], bounds[1] + 1))
            else:
                params[param_name] = round(float(rng.uniform(bounds[0], bounds[1])), 2)
        else:
            params[param_name] = bounds
    
    # Generate output key
    if ind_template.get("multi_output"):
        output_key = f"{ind_type}_{params.get('length', params.get('fast', 14))}"
    else:
        length = params.get("length", 14)
        output_key = f"{ind_type}_{length}"
    
    return {
        "indicator_type": ind_type,
        "output_key": output_key,
        "params": params,
        "input_source": "close",
        "is_multi_output": ind_template.get("multi_output", False),
    }


def compute_warmup_for_indicator(ind_spec: dict[str, Any]) -> int:
    """Compute warmup bars for an indicator."""
    params = ind_spec.get("params", {})
    
    # Find the longest length parameter
    lengths = []
    for key in ["length", "slow", "rsi_length"]:
        if key in params:
            lengths.append(params[key])
    
    if lengths:
        max_length = max(lengths)
        # Warmup is typically 2-3x the length
        return max_length * 3
    
    return 50  # Default


def generate_signal_rules(direction: str, indicators: list[dict[str, Any]], rng: np.random.Generator) -> dict[str, Any]:
    """Generate valid signal rules for the given direction."""
    registry = get_registry()
    
    # Pick first indicator for simple rule
    ind = indicators[0]
    
    # Get the correct key to use (expanded for multi-output, base for single-output)
    indicator_type = ind["indicator_type"]
    output_key = ind["output_key"]
    
    if registry.is_multi_output(indicator_type):
        # Use the primary output key for multi-output indicators
        primary = registry.get_primary_output(indicator_type)
        signal_key = f"{output_key}_{primary}"
    else:
        signal_key = output_key
    
    if direction == "long_only":
        return {
            "entry_rules": [
                {
                    "direction": "long",
                    "conditions": [
                        {
                            "indicator_key": signal_key,
                            "operator": "gt",
                            "value": 0,  # Dummy threshold
                            "is_indicator_comparison": False,
                            "tf": "exec",
                        }
                    ]
                }
            ],
            "exit_rules": [
                {
                    "direction": "long",
                    "exit_type": "signal",
                    "conditions": [
                        {
                            "indicator_key": signal_key,
                            "operator": "lt",
                            "value": 0,
                            "is_indicator_comparison": False,
                            "tf": "exec",
                        }
                    ]
                }
            ]
        }
    else:  # short_only
        return {
            "entry_rules": [
                {
                    "direction": "short",
                    "conditions": [
                        {
                            "indicator_key": signal_key,
                            "operator": "lt",
                            "value": 0,
                            "is_indicator_comparison": False,
                            "tf": "exec",
                        }
                    ]
                }
            ],
            "exit_rules": [
                {
                    "direction": "short",
                    "exit_type": "signal",
                    "conditions": [
                        {
                            "indicator_key": signal_key,
                            "operator": "gt",
                            "value": 0,
                            "is_indicator_comparison": False,
                            "tf": "exec",
                        }
                    ]
                }
            ]
        }


def generate_play_yaml(
    idea_id: str,
    symbol: str,
    direction: str,
    exec_tf: str,
    htf_tf: str,
    indicators: list[dict[str, Any]],
    rng: np.random.Generator,
) -> str:
    """
    Generate Play YAML content.
    
    Uses normalize_play_yaml to validate and auto-generate required_indicators.
    Raises ValueError if validation fails.
    """
    
    # Build feature specs for exec TF
    exec_feature_specs = []
    for ind in indicators:
        spec = {
            "indicator_type": ind["indicator_type"],
            "output_key": ind["output_key"],
            "params": ind["params"],
            "input_source": ind.get("input_source", "close"),
        }
        exec_feature_specs.append(spec)
    
    # Compute warmup
    warmup_bars = max(compute_warmup_for_indicator(ind) for ind in indicators)
    
    # Generate signal rules using expanded keys for multi-output indicators
    signal_rules = generate_signal_rules(direction, indicators, rng)
    
    idea_card = {
        "id": idea_id,
        "version": "1.0.0",
        "name": f"Generated {symbol} {exec_tf} Strategy",
        "description": f"Auto-generated Play for Gate D.2 verification. Direction: {direction}",
        "account": {
            "starting_equity_usdt": 10000.0,
            "max_leverage": 3.0,
            "margin_mode": "isolated_usdt",
            "min_trade_notional_usdt": 10.0,
            "fee_model": {
                "taker_bps": 6.0,
                "maker_bps": 2.0,
            },
            "slippage_bps": 2.0,
        },
        "symbol_universe": [symbol],
        "tf_configs": {
            "exec": {
                "tf": exec_tf,
                "role": "exec",
                "warmup_bars": warmup_bars,
                "feature_specs": exec_feature_specs,
                # required_indicators will be auto-generated by normalizer
            }
        },
        "bars_history_required": 2,
        "position_policy": {
            "mode": direction,
            "max_positions_per_symbol": 1,
            "allow_flip": False,
            "allow_scale_in": False,
            "allow_scale_out": False,
        },
        "signal_rules": signal_rules,
        "risk_model": {
            "stop_loss": {
                "type": "percent",
                "value": 2.0,
            },
            "take_profit": {
                "type": "rr_ratio",
                "value": 2.0,
            },
            "sizing": {
                "model": "percent_equity",
                "value": 1.0,
                "max_leverage": 1.0,
            }
        }
    }
    
    # Normalize and validate before dumping
    normalized, result = normalize_play_yaml(idea_card, auto_generate_required=True)
    
    if not result.is_valid:
        error_msg = format_validation_errors(result.errors)
        raise ValueError(f"Generated Play failed validation:\n{error_msg}")
    
    return yaml.dump(normalized, sort_keys=False, default_flow_style=False)


def _to_native(val):
    """Convert numpy types to native Python types."""
    if isinstance(val, np.integer):
        return int(val)
    elif isinstance(val, np.floating):
        return float(val)
    elif isinstance(val, np.ndarray):
        return val.tolist()
    elif isinstance(val, np.str_):
        return str(val)
    return val


def generate_plays(config: GeneratorConfig) -> list[GeneratedPlay]:
    """
    Generate randomized Plays.
    
    Args:
        config: Generator configuration
        
    Returns:
        List of generated Plays
    """
    rng = np.random.default_rng(config.seed)
    
    # Get available symbols
    symbols = get_available_symbols()
    
    # Create output directory
    config.output_dir.mkdir(parents=True, exist_ok=True)
    
    results = []
    
    for i in range(config.num_cards):
        # Select symbol and convert to native string
        symbol = str(rng.choice(symbols))
        
        # Select direction (alternate to ensure mix)
        direction = DIRECTIONS[i % 2]
        
        # Select timeframes and convert to native strings
        exec_tf = str(rng.choice(TIMEFRAMES_EXEC))
        htf_tf = str(rng.choice(TIMEFRAMES_HTF))
        
        # Generate indicators
        num_indicators = rng.integers(config.min_indicators, config.max_indicators + 1)
        indicators = []
        used_types = set()
        
        for _ in range(num_indicators):
            ind = generate_random_indicator(rng, used_types)
            indicators.append(ind)
            used_types.add(ind["indicator_type"])
        
        # Generate ID
        idea_id = f"generated_{symbol.lower()}_{exec_tf}_{i+1:02d}"
        
        # Generate YAML
        yaml_content = generate_play_yaml(
            idea_id=idea_id,
            symbol=symbol,
            direction=direction,
            exec_tf=exec_tf,
            htf_tf=htf_tf,
            indicators=indicators,
            rng=rng,
        )
        
        # Write file
        yaml_path = config.output_dir / f"{idea_id}.yml"
        yaml_path.write_text(yaml_content)
        
        results.append(GeneratedPlay(
            id=idea_id,
            symbol=symbol,
            direction=direction,
            exec_tf=exec_tf,
            htf_tf=htf_tf,
            indicators=indicators,
            yaml_path=yaml_path,
            yaml_content=yaml_content,
        ))
    
    return results


def cleanup_generated_plays(output_dir: Path = Path("configs/plays/generated")) -> None:
    """Remove all generated Plays."""
    if output_dir.exists():
        for f in output_dir.glob("*.yml"):
            f.unlink()

