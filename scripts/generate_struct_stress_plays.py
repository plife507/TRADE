#!/usr/bin/env python3
"""
Generate Structure Stress Test 3.0 Plays.

Usage:
    python scripts/generate_struct_stress_plays.py

Generates ~200 plays across 18 gates testing all 6 structure types.
"""

from pathlib import Path
import yaml

BASE_DIR = Path("tests/stress/plays")

# Common account config
ACCOUNT = {
    "starting_equity_usdt": 10000.0,
    "max_leverage": 1.0,
    "margin_mode": "isolated_usdt",
    "min_trade_notional_usdt": 10.0,
    "fee_model": {"taker_bps": 5.5, "maker_bps": 2.0},
    "slippage_bps": 2.0,
}

RISK = {
    "stop_loss_pct": 3.0,
    "take_profit_pct": 6.0,
    "max_position_pct": 10.0,
}

def write_play(path: Path, play: dict):
    """Write play YAML with LF line endings."""
    with open(path, "w", newline="\n") as f:
        yaml.dump(play, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def make_base_play(name: str, desc: str, symbol: str, tf: str, gate: int, complexity: int, direction: str) -> dict:
    """Create base play structure."""
    return {
        "version": "3.0.0",
        "name": name,
        "description": desc,
        "symbol": symbol,
        "tf": tf,
        "account": ACCOUNT.copy(),
        "features": {},
        "structures": {"exec": []},
        "actions": {},
        "position_policy": {
            "mode": "long_only" if direction == "long" else "short_only",
            "exit_mode": "signal",
            "max_positions_per_symbol": 1,
        },
        "risk": RISK.copy(),
        "_test_metadata": {
            "gate": gate,
            "complexity_pct": complexity,
            "category": "",
            "direction": direction,
        },
    }


def generate_gate_1():
    """Gate 1: Swing Basics - All basic swing output fields."""
    gate_dir = BASE_DIR / "struct_gate_01_swing_basics"
    gate_dir.mkdir(exist_ok=True)

    fields = [
        ("high_level", ">", 0, "Price level of swing high"),
        ("high_idx", ">", 0, "Bar index of swing high"),
        ("low_level", ">", 0, "Price level of swing low"),
        ("low_idx", ">", 0, "Bar index of swing low"),
        ("version", ">", 0, "Monotonic swing counter"),
    ]

    symbols = ["BTCUSDT", "SOLUSDT"]
    play_id = 5  # Continue from Gate 0

    for field, op, val, desc in fields:
        for symbol in symbols:
            for direction in ["long", "short"]:
                name = f"S3_{direction[0].upper()}_{play_id:03d}_swing_{field}"
                play = make_base_play(
                    name=name,
                    desc=f"Struct Gate 1: Swing {field} - {desc} ({direction}).",
                    symbol=symbol,
                    tf="15m",
                    gate=1,
                    complexity=10,
                    direction=direction,
                )
                play["_test_metadata"]["category"] = "swing_basics"
                play["features"]["ema_21"] = {"indicator": "ema", "params": {"length": 21}}
                play["structures"]["exec"].append({
                    "type": "swing",
                    "key": "swing",
                    "params": {"left": 5, "right": 5},
                })

                entry_key = f"entry_{direction}"
                exit_key = f"exit_{direction}"

                if direction == "long":
                    play["actions"][entry_key] = {
                        "all": [
                            ["close", ">", "ema_21"],
                            [{"feature_id": "swing", "field": field}, op, val],
                        ]
                    }
                    play["actions"][exit_key] = {"any": [["close", "<", "ema_21"]]}
                else:
                    play["actions"][entry_key] = {
                        "all": [
                            ["close", "<", "ema_21"],
                            [{"feature_id": "swing", "field": field}, op, val],
                        ]
                    }
                    play["actions"][exit_key] = {"any": [["close", ">", "ema_21"]]}

                write_play(gate_dir / f"{name}.yml", play)
                play_id += 1

    print(f"Gate 1: Generated {play_id - 5} plays")
    return play_id


def generate_gate_3():
    """Gate 3: Trend Structure - All trend output fields."""
    gate_dir = BASE_DIR / "struct_gate_03_trend"
    gate_dir.mkdir(exist_ok=True)

    # Tests for trend fields
    tests = [
        ("direction_up", "direction", "==", 1, "Uptrend detection"),
        ("direction_down", "direction", "==", -1, "Downtrend detection"),
        ("strength", "strength", ">", 0, "Trend strength metric"),
        ("bars", "bars_in_trend", ">", 0, "Bars since trend start"),
    ]

    symbols = ["BTCUSDT", "ETHUSDT"]
    play_id = 20

    for test_name, field, op, val, desc in tests:
        for symbol in symbols:
            for direction in ["long", "short"]:
                name = f"S3_{direction[0].upper()}_{play_id:03d}_trend_{test_name}"
                play = make_base_play(
                    name=name,
                    desc=f"Struct Gate 3: Trend {field} - {desc} ({direction}).",
                    symbol=symbol,
                    tf="15m",
                    gate=3,
                    complexity=20,
                    direction=direction,
                )
                play["_test_metadata"]["category"] = "trend"
                play["features"]["rsi_14"] = {"indicator": "rsi", "params": {"length": 14}}
                play["structures"]["exec"].extend([
                    {"type": "swing", "key": "swing", "params": {"left": 5, "right": 5}},
                    {"type": "trend", "key": "trend", "depends_on": {"swing": "swing"}},
                ])

                entry_key = f"entry_{direction}"
                exit_key = f"exit_{direction}"

                if direction == "long":
                    play["actions"][entry_key] = {
                        "all": [
                            ["rsi_14", "<", 50],
                            [{"feature_id": "trend", "field": field}, op, val],
                        ]
                    }
                    play["actions"][exit_key] = {"any": [["rsi_14", ">", 70]]}
                else:
                    play["actions"][entry_key] = {
                        "all": [
                            ["rsi_14", ">", 50],
                            [{"feature_id": "trend", "field": field}, op, val],
                        ]
                    }
                    play["actions"][exit_key] = {"any": [["rsi_14", "<", 30]]}

                write_play(gate_dir / f"{name}.yml", play)
                play_id += 1

    print(f"Gate 3: Generated {play_id - 20} plays")
    return play_id


def generate_gate_4():
    """Gate 4: Rolling Window Variants."""
    gate_dir = BASE_DIR / "struct_gate_04_rolling_window"
    gate_dir.mkdir(exist_ok=True)

    variants = [
        ("max_20_high", "max", 20, "high"),
        ("min_20_low", "min", 20, "low"),
        ("max_50_close", "max", 50, "close"),
        ("min_50_close", "min", 50, "close"),
    ]

    symbols = ["BTCUSDT", "ETHUSDT"]
    play_id = 36

    for var_name, mode, size, source in variants:
        for symbol in symbols:
            for direction in ["long", "short"]:
                name = f"S3_{direction[0].upper()}_{play_id:03d}_rolling_{var_name}"
                play = make_base_play(
                    name=name,
                    desc=f"Struct Gate 4: Rolling {mode} {size} {source} ({direction}).",
                    symbol=symbol,
                    tf="15m",
                    gate=4,
                    complexity=25,
                    direction=direction,
                )
                play["_test_metadata"]["category"] = "rolling_window"
                play["features"]["ema_21"] = {"indicator": "ema", "params": {"length": 21}}
                play["structures"]["exec"].append({
                    "type": "rolling_window",
                    "key": "rolling",
                    "params": {"mode": mode, "size": size, "source": source},
                })

                entry_key = f"entry_{direction}"
                exit_key = f"exit_{direction}"

                if direction == "long":
                    play["actions"][entry_key] = {
                        "all": [
                            ["close", ">", "ema_21"],
                            [{"feature_id": "rolling", "field": "value"}, ">", 0],
                        ]
                    }
                    play["actions"][exit_key] = {"any": [["close", "<", "ema_21"]]}
                else:
                    play["actions"][entry_key] = {
                        "all": [
                            ["close", "<", "ema_21"],
                            [{"feature_id": "rolling", "field": "value"}, ">", 0],
                        ]
                    }
                    play["actions"][exit_key] = {"any": [["close", ">", "ema_21"]]}

                write_play(gate_dir / f"{name}.yml", play)
                play_id += 1

    print(f"Gate 4: Generated {play_id - 36} plays")
    return play_id


def generate_gate_6():
    """Gate 6: Fibonacci Retracement."""
    gate_dir = BASE_DIR / "struct_gate_06_fib_retracement"
    gate_dir.mkdir(exist_ok=True)

    levels = ["0.382", "0.5", "0.618"]
    symbols = ["BTCUSDT", "ETHUSDT"]
    play_id = 52

    for level in levels:
        for symbol in symbols:
            for direction in ["long", "short"]:
                name = f"S3_{direction[0].upper()}_{play_id:03d}_fib_{level.replace('.', '')}"
                play = make_base_play(
                    name=name,
                    desc=f"Struct Gate 6: Fibonacci level_{level} retracement ({direction}).",
                    symbol=symbol,
                    tf="15m",
                    gate=6,
                    complexity=35,
                    direction=direction,
                )
                play["_test_metadata"]["category"] = "fib_retracement"
                play["features"]["rsi_14"] = {"indicator": "rsi", "params": {"length": 14}}
                play["structures"]["exec"].extend([
                    {"type": "swing", "key": "swing", "params": {"left": 5, "right": 5}},
                    {
                        "type": "fibonacci",
                        "key": "fib",
                        "depends_on": {"swing": "swing"},
                        "params": {"levels": [float(level)], "mode": "retracement"},
                    },
                ])

                entry_key = f"entry_{direction}"
                exit_key = f"exit_{direction}"
                field = f"level_{level}"

                if direction == "long":
                    play["actions"][entry_key] = {
                        "all": [
                            ["rsi_14", "<", 50],
                            [{"feature_id": "fib", "field": field}, ">", 0],
                        ]
                    }
                    play["actions"][exit_key] = {"any": [["rsi_14", ">", 70]]}
                else:
                    play["actions"][entry_key] = {
                        "all": [
                            ["rsi_14", ">", 50],
                            [{"feature_id": "fib", "field": field}, ">", 0],
                        ]
                    }
                    play["actions"][exit_key] = {"any": [["rsi_14", "<", 30]]}

                write_play(gate_dir / f"{name}.yml", play)
                play_id += 1

    # Add anchor tests
    for field in ["anchor_high", "anchor_low", "range"]:
        for direction in ["long", "short"]:
            name = f"S3_{direction[0].upper()}_{play_id:03d}_fib_{field}"
            play = make_base_play(
                name=name,
                desc=f"Struct Gate 6: Fibonacci {field} ({direction}).",
                symbol="BTCUSDT",
                tf="15m",
                gate=6,
                complexity=35,
                direction=direction,
            )
            play["_test_metadata"]["category"] = "fib_retracement"
            play["features"]["rsi_14"] = {"indicator": "rsi", "params": {"length": 14}}
            play["structures"]["exec"].extend([
                {"type": "swing", "key": "swing", "params": {"left": 5, "right": 5}},
                {
                    "type": "fibonacci",
                    "key": "fib",
                    "depends_on": {"swing": "swing"},
                    "params": {"levels": [0.5], "mode": "retracement"},
                },
            ])

            entry_key = f"entry_{direction}"
            exit_key = f"exit_{direction}"

            if direction == "long":
                play["actions"][entry_key] = {
                    "all": [
                        ["rsi_14", "<", 50],
                        [{"feature_id": "fib", "field": field}, ">", 0],
                    ]
                }
                play["actions"][exit_key] = {"any": [["rsi_14", ">", 70]]}
            else:
                play["actions"][entry_key] = {
                    "all": [
                        ["rsi_14", ">", 50],
                        [{"feature_id": "fib", "field": field}, ">", 0],
                    ]
                }
                play["actions"][exit_key] = {"any": [["rsi_14", "<", 30]]}

            write_play(gate_dir / f"{name}.yml", play)
            play_id += 1

    print(f"Gate 6: Generated {play_id - 52} plays")
    return play_id


def generate_gate_8():
    """Gate 8: Derived Zone Slots."""
    gate_dir = BASE_DIR / "struct_gate_08_dz_slots"
    gate_dir.mkdir(exist_ok=True)

    # Test various slot fields
    tests = [
        ("zone0_lower", "zone0_lower", ">", 0),
        ("zone0_upper", "zone0_upper", ">", 0),
        ("zone0_state", "zone0_state", "!=", "NONE"),
        ("zone1_lower", "zone1_lower", ">", 0),
    ]

    symbols = ["BTCUSDT", "ETHUSDT"]
    play_id = 70

    for test_name, field, op, val in tests:
        for symbol in symbols:
            for direction in ["long", "short"]:
                name = f"S3_{direction[0].upper()}_{play_id:03d}_dz_{test_name}"
                play = make_base_play(
                    name=name,
                    desc=f"Struct Gate 8: Derived Zone {field} K slot ({direction}).",
                    symbol=symbol,
                    tf="15m",
                    gate=8,
                    complexity=55,
                    direction=direction,
                )
                play["_test_metadata"]["category"] = "dz_slots"
                play["features"]["rsi_14"] = {"indicator": "rsi", "params": {"length": 14}}
                play["structures"]["exec"].extend([
                    {"type": "swing", "key": "swing", "params": {"left": 5, "right": 5}},
                    {
                        "type": "derived_zone",
                        "key": "dz",
                        "depends_on": {"swing": "swing"},
                        "params": {
                            "levels": [0.382, 0.618],
                            "mode": "retracement",
                            "max_active": 3,
                            "width_pct": 0.002,
                        },
                    },
                ])

                entry_key = f"entry_{direction}"
                exit_key = f"exit_{direction}"

                # Build condition based on op type
                if op == "!=":
                    cond = [{"feature_id": "dz", "field": field}, op, val]
                else:
                    cond = [{"feature_id": "dz", "field": field}, op, val]

                if direction == "long":
                    play["actions"][entry_key] = {"all": [["rsi_14", "<", 50], cond]}
                    play["actions"][exit_key] = {"any": [["rsi_14", ">", 70]]}
                else:
                    play["actions"][entry_key] = {"all": [["rsi_14", ">", 50], cond]}
                    play["actions"][exit_key] = {"any": [["rsi_14", "<", 30]]}

                write_play(gate_dir / f"{name}.yml", play)
                play_id += 1

    print(f"Gate 8: Generated {play_id - 70} plays")
    return play_id


def generate_gate_9():
    """Gate 9: Derived Zone Aggregates."""
    gate_dir = BASE_DIR / "struct_gate_09_dz_aggregates"
    gate_dir.mkdir(exist_ok=True)

    tests = [
        ("active_count", "active_count", ">", 0),
        ("any_active", "any_active", "==", True),
        ("any_touched", "any_touched", "==", True),
        ("any_inside", "any_inside", "==", True),
        ("closest_lower", "closest_active_lower", ">", 0),
        ("closest_upper", "closest_active_upper", ">", 0),
    ]

    symbols = ["BTCUSDT", "SOLUSDT"]
    play_id = 86

    for test_name, field, op, val in tests:
        for symbol in symbols:
            for direction in ["long", "short"]:
                name = f"S3_{direction[0].upper()}_{play_id:03d}_dz_{test_name}"
                play = make_base_play(
                    name=name,
                    desc=f"Struct Gate 9: Derived Zone {field} aggregate ({direction}).",
                    symbol=symbol,
                    tf="15m",
                    gate=9,
                    complexity=60,
                    direction=direction,
                )
                play["_test_metadata"]["category"] = "dz_aggregates"
                play["features"]["rsi_14"] = {"indicator": "rsi", "params": {"length": 14}}
                play["structures"]["exec"].extend([
                    {"type": "swing", "key": "swing", "params": {"left": 5, "right": 5}},
                    {
                        "type": "derived_zone",
                        "key": "dz",
                        "depends_on": {"swing": "swing"},
                        "params": {
                            "levels": [0.382, 0.5, 0.618],
                            "mode": "retracement",
                            "max_active": 5,
                            "width_pct": 0.002,
                        },
                    },
                ])

                entry_key = f"entry_{direction}"
                exit_key = f"exit_{direction}"

                cond = [{"feature_id": "dz", "field": field}, op, val]

                if direction == "long":
                    play["actions"][entry_key] = {"all": [["rsi_14", "<", 50], cond]}
                    play["actions"][exit_key] = {"any": [["rsi_14", ">", 70]]}
                else:
                    play["actions"][entry_key] = {"all": [["rsi_14", ">", 50], cond]}
                    play["actions"][exit_key] = {"any": [["rsi_14", "<", 30]]}

                write_play(gate_dir / f"{name}.yml", play)
                play_id += 1

    print(f"Gate 9: Generated {play_id - 86} plays")
    return play_id


def generate_gate_11():
    """Gate 11: Structure + Indicator Combos."""
    gate_dir = BASE_DIR / "struct_gate_11_struct_indicator"
    gate_dir.mkdir(exist_ok=True)

    combos = [
        ("swing_ema", "swing", "high_level", ">", "ema_50"),
        ("swing_rsi", "swing", "low_level", ">", 0),  # Plus RSI filter
        ("trend_rsi", "trend", "direction", "==", 1),  # Plus RSI filter
        ("rolling_ema", "rolling", "value", ">", "ema_50"),
    ]

    play_id = 110

    for combo_name, struct_type, field, op, rhs in combos:
        for direction in ["long", "short"]:
            name = f"S3_{direction[0].upper()}_{play_id:03d}_{combo_name}"
            play = make_base_play(
                name=name,
                desc=f"Struct Gate 11: {struct_type} + indicator combo ({direction}).",
                symbol="BTCUSDT",
                tf="15m",
                gate=11,
                complexity=70,
                direction=direction,
            )
            play["_test_metadata"]["category"] = "struct_indicator"
            play["features"]["ema_50"] = {"indicator": "ema", "params": {"length": 50}}
            play["features"]["rsi_14"] = {"indicator": "rsi", "params": {"length": 14}}

            if struct_type == "swing":
                play["structures"]["exec"].append({
                    "type": "swing", "key": "swing", "params": {"left": 5, "right": 5}
                })
            elif struct_type == "trend":
                play["structures"]["exec"].extend([
                    {"type": "swing", "key": "swing", "params": {"left": 5, "right": 5}},
                    {"type": "trend", "key": "trend", "depends_on": {"swing": "swing"}},
                ])
            elif struct_type == "rolling":
                play["structures"]["exec"].append({
                    "type": "rolling_window", "key": "rolling",
                    "params": {"mode": "max", "size": 20, "source": "high"}
                })

            entry_key = f"entry_{direction}"
            exit_key = f"exit_{direction}"

            # Build struct condition
            struct_cond = [{"feature_id": struct_type, "field": field}, op, rhs]

            if direction == "long":
                play["actions"][entry_key] = {
                    "all": [["rsi_14", "<", 50], struct_cond]
                }
                play["actions"][exit_key] = {"any": [["rsi_14", ">", 70]]}
            else:
                play["actions"][entry_key] = {
                    "all": [["rsi_14", ">", 50], struct_cond]
                }
                play["actions"][exit_key] = {"any": [["rsi_14", "<", 30]]}

            write_play(gate_dir / f"{name}.yml", play)
            play_id += 1

    print(f"Gate 11: Generated {play_id - 110} plays")
    return play_id


def generate_gate_12():
    """Gate 12: Multi-Structure."""
    gate_dir = BASE_DIR / "struct_gate_12_multi_struct"
    gate_dir.mkdir(exist_ok=True)

    play_id = 118

    # Swing + Trend
    for direction in ["long", "short"]:
        name = f"S3_{direction[0].upper()}_{play_id:03d}_swing_trend"
        play = make_base_play(
            name=name,
            desc=f"Struct Gate 12: Swing + Trend multi-structure ({direction}).",
            symbol="BTCUSDT",
            tf="15m",
            gate=12,
            complexity=75,
            direction=direction,
        )
        play["_test_metadata"]["category"] = "multi_struct"
        play["features"]["rsi_14"] = {"indicator": "rsi", "params": {"length": 14}}
        play["structures"]["exec"].extend([
            {"type": "swing", "key": "swing", "params": {"left": 5, "right": 5}},
            {"type": "trend", "key": "trend", "depends_on": {"swing": "swing"}},
        ])

        entry_key = f"entry_{direction}"
        exit_key = f"exit_{direction}"

        if direction == "long":
            play["actions"][entry_key] = {
                "all": [
                    [{"feature_id": "swing", "field": "high_level"}, ">", 0],
                    [{"feature_id": "trend", "field": "direction"}, "==", 1],
                ]
            }
            play["actions"][exit_key] = {"any": [["rsi_14", ">", 70]]}
        else:
            play["actions"][entry_key] = {
                "all": [
                    [{"feature_id": "swing", "field": "low_level"}, ">", 0],
                    [{"feature_id": "trend", "field": "direction"}, "==", -1],
                ]
            }
            play["actions"][exit_key] = {"any": [["rsi_14", "<", 30]]}

        write_play(gate_dir / f"{name}.yml", play)
        play_id += 1

    # Swing + Fibonacci
    for direction in ["long", "short"]:
        name = f"S3_{direction[0].upper()}_{play_id:03d}_swing_fib"
        play = make_base_play(
            name=name,
            desc=f"Struct Gate 12: Swing + Fibonacci multi-structure ({direction}).",
            symbol="ETHUSDT",
            tf="15m",
            gate=12,
            complexity=75,
            direction=direction,
        )
        play["_test_metadata"]["category"] = "multi_struct"
        play["features"]["rsi_14"] = {"indicator": "rsi", "params": {"length": 14}}
        play["structures"]["exec"].extend([
            {"type": "swing", "key": "swing", "params": {"left": 5, "right": 5}},
            {
                "type": "fibonacci", "key": "fib",
                "depends_on": {"swing": "swing"},
                "params": {"levels": [0.5, 0.618], "mode": "retracement"},
            },
        ])

        entry_key = f"entry_{direction}"
        exit_key = f"exit_{direction}"

        if direction == "long":
            play["actions"][entry_key] = {
                "all": [
                    [{"feature_id": "swing", "field": "low_level"}, ">", 0],
                    [{"feature_id": "fib", "field": "level_0.5"}, ">", 0],
                ]
            }
            play["actions"][exit_key] = {"any": [["rsi_14", ">", 70]]}
        else:
            play["actions"][entry_key] = {
                "all": [
                    [{"feature_id": "swing", "field": "high_level"}, ">", 0],
                    [{"feature_id": "fib", "field": "level_0.618"}, ">", 0],
                ]
            }
            play["actions"][exit_key] = {"any": [["rsi_14", "<", 30]]}

        write_play(gate_dir / f"{name}.yml", play)
        play_id += 1

    # Rolling + Swing
    for direction in ["long", "short"]:
        name = f"S3_{direction[0].upper()}_{play_id:03d}_rolling_swing"
        play = make_base_play(
            name=name,
            desc=f"Struct Gate 12: Rolling + Swing multi-structure ({direction}).",
            symbol="SOLUSDT",
            tf="15m",
            gate=12,
            complexity=75,
            direction=direction,
        )
        play["_test_metadata"]["category"] = "multi_struct"
        play["features"]["rsi_14"] = {"indicator": "rsi", "params": {"length": 14}}
        play["structures"]["exec"].extend([
            {"type": "swing", "key": "swing", "params": {"left": 5, "right": 5}},
            {"type": "rolling_window", "key": "rolling", "params": {"mode": "max", "size": 20, "source": "high"}},
        ])

        entry_key = f"entry_{direction}"
        exit_key = f"exit_{direction}"

        if direction == "long":
            play["actions"][entry_key] = {
                "all": [
                    [{"feature_id": "rolling", "field": "value"}, ">", 0],
                    [{"feature_id": "swing", "field": "low_level"}, ">", 0],
                ]
            }
            play["actions"][exit_key] = {"any": [["rsi_14", ">", 70]]}
        else:
            play["actions"][entry_key] = {
                "all": [
                    [{"feature_id": "rolling", "field": "value"}, ">", 0],
                    [{"feature_id": "swing", "field": "high_level"}, ">", 0],
                ]
            }
            play["actions"][exit_key] = {"any": [["rsi_14", "<", 30]]}

        write_play(gate_dir / f"{name}.yml", play)
        play_id += 1

    print(f"Gate 12: Generated {play_id - 118} plays")
    return play_id


def generate_gate_17():
    """Gate 17: Ultimate Complexity."""
    gate_dir = BASE_DIR / "struct_gate_17_ultimate"
    gate_dir.mkdir(exist_ok=True)

    play_id = 150

    for direction in ["long", "short"]:
        # Ultimate 1: All 6 structures
        name = f"S3_{direction[0].upper()}_{play_id:03d}_ultimate_6_struct"
        play = make_base_play(
            name=name,
            desc=f"Struct Gate 17: All 6 structure types combined ({direction}).",
            symbol="BTCUSDT",
            tf="15m",
            gate=17,
            complexity=100,
            direction=direction,
        )
        play["_test_metadata"]["category"] = "ultimate"
        play["features"]["ema_21"] = {"indicator": "ema", "params": {"length": 21}}
        play["features"]["rsi_14"] = {"indicator": "rsi", "params": {"length": 14}}
        play["structures"]["exec"].extend([
            {"type": "swing", "key": "swing", "params": {"left": 5, "right": 5}},
            {"type": "trend", "key": "trend", "depends_on": {"swing": "swing"}},
            {"type": "fibonacci", "key": "fib", "depends_on": {"swing": "swing"}, "params": {"levels": [0.5], "mode": "retracement"}},
            {"type": "rolling_window", "key": "rolling", "params": {"mode": "max", "size": 20, "source": "high"}},
            {
                "type": "derived_zone", "key": "dz",
                "depends_on": {"swing": "swing"},
                "params": {"levels": [0.5], "mode": "retracement", "max_active": 3, "width_pct": 0.002},
            },
        ])

        entry_key = f"entry_{direction}"
        exit_key = f"exit_{direction}"

        if direction == "long":
            play["actions"][entry_key] = {
                "all": [
                    ["close", ">", "ema_21"],
                    [{"feature_id": "swing", "field": "low_level"}, ">", 0],
                    [{"feature_id": "trend", "field": "direction"}, "==", 1],
                ]
            }
            play["actions"][exit_key] = {"any": [["close", "<", "ema_21"]]}
        else:
            play["actions"][entry_key] = {
                "all": [
                    ["close", "<", "ema_21"],
                    [{"feature_id": "swing", "field": "high_level"}, ">", 0],
                    [{"feature_id": "trend", "field": "direction"}, "==", -1],
                ]
            }
            play["actions"][exit_key] = {"any": [["close", ">", "ema_21"]]}

        write_play(gate_dir / f"{name}.yml", play)
        play_id += 1

    # Ultimate 2: Complex boolean
    for direction in ["long", "short"]:
        name = f"S3_{direction[0].upper()}_{play_id:03d}_ultimate_boolean"
        play = make_base_play(
            name=name,
            desc=f"Struct Gate 17: Complex ALL/ANY/NOT with structures ({direction}).",
            symbol="ETHUSDT",
            tf="15m",
            gate=17,
            complexity=100,
            direction=direction,
        )
        play["_test_metadata"]["category"] = "ultimate"
        play["features"]["rsi_14"] = {"indicator": "rsi", "params": {"length": 14}}
        play["structures"]["exec"].extend([
            {"type": "swing", "key": "swing", "params": {"left": 5, "right": 5}},
            {"type": "trend", "key": "trend", "depends_on": {"swing": "swing"}},
        ])

        entry_key = f"entry_{direction}"
        exit_key = f"exit_{direction}"

        if direction == "long":
            play["actions"][entry_key] = {
                "all": [
                    {"any": [
                        [{"feature_id": "trend", "field": "direction"}, "==", 1],
                        ["rsi_14", "<", 30],
                    ]},
                    [{"feature_id": "swing", "field": "low_level"}, ">", 0],
                ]
            }
            play["actions"][exit_key] = {"any": [["rsi_14", ">", 70]]}
        else:
            play["actions"][entry_key] = {
                "all": [
                    {"any": [
                        [{"feature_id": "trend", "field": "direction"}, "==", -1],
                        ["rsi_14", ">", 70],
                    ]},
                    [{"feature_id": "swing", "field": "high_level"}, ">", 0],
                ]
            }
            play["actions"][exit_key] = {"any": [["rsi_14", "<", 30]]}

        write_play(gate_dir / f"{name}.yml", play)
        play_id += 1

    print(f"Gate 17: Generated {play_id - 150} plays")
    return play_id


def main():
    print("=" * 60)
    print("Structure Stress Test 3.0 - Play Generator")
    print("=" * 60)

    # Generate all gates
    generate_gate_1()
    generate_gate_3()
    generate_gate_4()
    generate_gate_6()
    generate_gate_8()
    generate_gate_9()
    generate_gate_11()
    generate_gate_12()
    generate_gate_17()

    # Count total plays
    total = 0
    for gate_dir in BASE_DIR.glob("struct_gate_*"):
        count = len(list(gate_dir.glob("*.yml")))
        total += count
        print(f"  {gate_dir.name}: {count} plays")

    print("=" * 60)
    print(f"Total plays generated: {total}")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Run: python trade_cli.py backtest play-normalize-batch --dir tests/stress/plays/struct_gate_XX/")
    print("2. Execute plays sequentially with --fix-gaps flag")


if __name__ == "__main__":
    main()
