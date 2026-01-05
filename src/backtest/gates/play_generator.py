"""
Play Generator - Creates randomized valid Plays with blocks DSL v3.0.0.

Gate D.2 requirement: Generate valid Plays with randomized indicators,
selecting symbols from available local data only.

All generated Plays use blocks DSL v3.0.0 format (NO legacy signal_rules).

Rules:
- Deterministic seed for reproducibility
- 2-4 indicators per Play on execution TF
- Indicators from IndicatorRegistry
- Single direction per card (long_only OR short_only)
- Mixed directions across batch
- All generated YAMLs must pass normalization
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml
import numpy as np

from ..indicator_registry import get_registry


# Indicator templates with conservative period bounds for warmup
INDICATOR_TEMPLATES = [
    {"type": "ema", "params": {"length": (5, 50)}},
    {"type": "sma", "params": {"length": (5, 50)}},
    {"type": "rsi", "params": {"length": (7, 21)}},
    {"type": "atr", "params": {"length": (7, 21)}},
    {"type": "macd", "params": {"fast": (8, 16), "slow": (20, 30), "signal": (7, 12)}, "multi_output": True},
    {"type": "bbands", "params": {"length": (14, 26), "std": (1.5, 2.5)}, "multi_output": True},
    {"type": "stoch", "params": {"k": (9, 18), "d": (3, 6), "smooth_k": (3, 6)}, "multi_output": True},
    {"type": "adx", "params": {"length": (10, 20)}, "multi_output": True},
]

DIRECTIONS = ["long_only", "short_only"]
EXECUTION_TFS = ["1h"]  # Only 1h has verified data coverage


@dataclass
class GeneratorConfig:
    """Configuration for Play generation."""
    seed: int = 42
    num_plays: int = 5
    min_indicators: int = 2
    max_indicators: int = 4
    output_dir: Path = field(default_factory=lambda: Path("configs/plays/_generated"))


@dataclass
class GeneratedPlay:
    """Result of Play generation."""
    id: str
    symbol: str
    direction: str
    exec_tf: str
    indicators: list[dict[str, Any]]
    yaml_path: Path
    yaml_content: str


def get_available_symbols(env: str = "live") -> list[str]:
    """Get symbols available in local DuckDB data."""
    try:
        from src.data.historical_data_store import get_historical_store
        store = get_historical_store(env=env)
        table_name = f"ohlcv_{env}"
        result = store.conn.execute(f"""
            SELECT DISTINCT symbol
            FROM {table_name}
            WHERE symbol LIKE '%USDT'
            ORDER BY symbol
        """).fetchall()

        symbols = [row[0] for row in result]
        known_good = {"BTCUSDT", "SOLUSDT"}
        symbols = [s for s in symbols if s in known_good]
        return symbols if symbols else ["BTCUSDT", "SOLUSDT"]
    except Exception:
        return ["BTCUSDT", "SOLUSDT"]


def _generate_random_indicator(
    rng: np.random.Generator,
    used_types: set[str],
    exec_tf: str,
) -> dict[str, Any]:
    """Generate a random indicator spec in blocks DSL format."""
    available = [t for t in INDICATOR_TEMPLATES if t["type"] not in used_types]
    if not available:
        available = INDICATOR_TEMPLATES

    template = available[int(rng.integers(0, len(available)))]
    ind_type = template["type"]

    # Generate random params
    params: dict[str, Any] = {}
    for param_name, bounds in template["params"].items():
        if isinstance(bounds, tuple):
            if isinstance(bounds[0], int):
                params[param_name] = int(rng.integers(bounds[0], bounds[1] + 1))
            else:
                params[param_name] = round(float(rng.uniform(bounds[0], bounds[1])), 2)
        else:
            params[param_name] = bounds

    # Generate feature ID
    length = params.get("length", params.get("fast", 14))
    feature_id = f"{ind_type}_{length}"

    return {
        "id": feature_id,
        "tf": exec_tf,
        "type": "indicator",
        "indicator_type": ind_type,
        "params": params,
        "_is_multi_output": template.get("multi_output", False),
    }


def _generate_blocks(
    direction: str,
    indicators: list[dict[str, Any]],
    rng: np.random.Generator,
) -> list[dict[str, Any]]:
    """Generate blocks DSL v3.0.0 entry/exit rules."""
    registry = get_registry()

    # Pick first indicator for entry/exit logic
    ind = indicators[0]
    feature_id = ind["id"]
    ind_type = ind["indicator_type"]

    # Get correct key for multi-output indicators
    if ind.get("_is_multi_output") and registry.is_multi_output(ind_type):
        primary = registry.get_primary_output(ind_type)
        feature_id = f"{feature_id}_{primary}"

    # Build entry condition
    if direction == "long_only":
        entry_action = "entry_long"
        exit_action = "exit_long"
        entry_op = "gt"
        exit_op = "lt"
    else:
        entry_action = "entry_short"
        exit_action = "exit_short"
        entry_op = "lt"
        exit_op = "gt"

    # Use second indicator for comparison if available, else use threshold
    if len(indicators) >= 2:
        ind2 = indicators[1]
        feature_id_2 = ind2["id"]
        ind_type_2 = ind2["indicator_type"]

        if ind2.get("_is_multi_output") and registry.is_multi_output(ind_type_2):
            primary2 = registry.get_primary_output(ind_type_2)
            feature_id_2 = f"{feature_id_2}_{primary2}"

        entry_rhs: dict[str, Any] | float = {"feature_id": feature_id_2}
        exit_rhs: dict[str, Any] | float = {"feature_id": feature_id_2}
    else:
        # Threshold comparison
        entry_rhs = 0.0
        exit_rhs = 0.0

    blocks = [
        {
            "id": "entry",
            "cases": [
                {
                    "when": {
                        "lhs": {"feature_id": feature_id},
                        "op": entry_op,
                        "rhs": entry_rhs,
                    },
                    "emit": [{"action": entry_action}],
                }
            ],
            "else": {"emit": [{"action": "no_action"}]},
        },
        {
            "id": "exit",
            "cases": [
                {
                    "when": {
                        "lhs": {"feature_id": feature_id},
                        "op": exit_op,
                        "rhs": exit_rhs,
                    },
                    "emit": [{"action": exit_action}],
                }
            ],
        },
    ]

    return blocks


def _build_play_dict(
    play_id: str,
    symbol: str,
    direction: str,
    exec_tf: str,
    indicators: list[dict[str, Any]],
    rng: np.random.Generator,
) -> dict[str, Any]:
    """Build a complete Play dict in blocks DSL v3.0.0 format."""
    # Build features list (remove internal _is_multi_output flag)
    features = []
    for ind in indicators:
        feature = {
            "id": ind["id"],
            "tf": ind["tf"],
            "type": ind["type"],
            "indicator_type": ind["indicator_type"],
            "params": ind["params"],
        }
        features.append(feature)

    # Generate blocks
    blocks = _generate_blocks(direction, indicators, rng)

    return {
        "id": play_id,
        "version": "3.0.0",
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
        "execution_tf": exec_tf,
        "features": features,
        "position_policy": {
            "mode": direction,
            "max_positions_per_symbol": 1,
            "allow_flip": False,
            "allow_scale_in": False,
            "allow_scale_out": False,
        },
        "blocks": blocks,
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
            },
        },
    }


def generate_plays(config: GeneratorConfig) -> list[GeneratedPlay]:
    """
    Generate randomized Plays with blocks DSL v3.0.0.

    Args:
        config: Generator configuration

    Returns:
        List of generated Plays
    """
    rng = np.random.default_rng(config.seed)
    symbols = get_available_symbols()

    config.output_dir.mkdir(parents=True, exist_ok=True)

    results: list[GeneratedPlay] = []

    for i in range(config.num_plays):
        symbol = str(rng.choice(symbols))
        direction = DIRECTIONS[i % 2]
        exec_tf = str(rng.choice(EXECUTION_TFS))

        # Generate indicators
        num_indicators = int(rng.integers(config.min_indicators, config.max_indicators + 1))
        indicators: list[dict[str, Any]] = []
        used_types: set[str] = set()

        for _ in range(num_indicators):
            ind = _generate_random_indicator(rng, used_types, exec_tf)
            indicators.append(ind)
            used_types.add(ind["indicator_type"])

        # Build Play
        play_id = f"generated_{symbol.lower()}_{exec_tf}_{i+1:02d}"
        play_dict = _build_play_dict(play_id, symbol, direction, exec_tf, indicators, rng)

        # Dump to YAML
        yaml_content = yaml.dump(play_dict, sort_keys=False, default_flow_style=False)

        # Write file
        yaml_path = config.output_dir / f"{play_id}.yml"
        with open(yaml_path, "w", newline="\n") as f:
            f.write(yaml_content)

        results.append(GeneratedPlay(
            id=play_id,
            symbol=symbol,
            direction=direction,
            exec_tf=exec_tf,
            indicators=indicators,
            yaml_path=yaml_path,
            yaml_content=yaml_content,
        ))

    return results


def cleanup_generated_plays(output_dir: Path = Path("configs/plays/_generated")) -> None:
    """Remove all generated Plays."""
    if output_dir.exists():
        for f in output_dir.glob("*.yml"):
            f.unlink()
