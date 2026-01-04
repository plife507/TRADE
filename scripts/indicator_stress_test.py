"""
Indicator Stress Test - Tests all 42 indicators with simple triggers.
Run: python scripts/indicator_stress_test.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile
import yaml
from pathlib import Path

# All 42 indicators with their required params and test config
INDICATORS = {
    # Single-output indicators (26)
    "ema": {"params": {"length": 14}, "threshold": 0, "compare_close": True},
    "sma": {"params": {"length": 14}, "threshold": 0, "compare_close": True},
    "rsi": {"params": {"length": 14}, "threshold": 50, "compare_close": False},
    "atr": {"params": {"length": 14}, "threshold": 0, "compare_close": False},
    "cci": {"params": {"length": 14}, "threshold": 0, "compare_close": False},
    "willr": {"params": {"length": 14}, "threshold": -50, "compare_close": False},
    "roc": {"params": {"length": 14}, "threshold": 0, "compare_close": False},
    "mom": {"params": {"length": 14}, "threshold": 0, "compare_close": False},
    "kama": {"params": {"length": 14}, "threshold": 0, "compare_close": True},
    "alma": {"params": {"length": 14, "sigma": 6.0, "offset": 0.85}, "threshold": 0, "compare_close": True},
    "wma": {"params": {"length": 14}, "threshold": 0, "compare_close": True},
    "dema": {"params": {"length": 14}, "threshold": 0, "compare_close": True},
    "tema": {"params": {"length": 14}, "threshold": 0, "compare_close": True},
    "trima": {"params": {"length": 14}, "threshold": 0, "compare_close": True},
    "zlma": {"params": {"length": 14}, "threshold": 0, "compare_close": True},
    "natr": {"params": {"length": 14}, "threshold": 0, "compare_close": False},
    "mfi": {"params": {"length": 14}, "threshold": 50, "compare_close": False},
    "obv": {"params": {}, "threshold": 0, "compare_close": False},
    "cmf": {"params": {"length": 14}, "threshold": 0, "compare_close": False},
    "cmo": {"params": {"length": 14}, "threshold": 0, "compare_close": False},
    "linreg": {"params": {"length": 14}, "threshold": 0, "compare_close": True},
    "midprice": {"params": {"length": 14}, "threshold": 0, "compare_close": True},
    "ohlc4": {"params": {}, "threshold": 0, "compare_close": True},
    "trix": {"params": {"length": 14}, "threshold": 0, "compare_close": False},
    "uo": {"params": {"fast": 7, "medium": 14, "slow": 28}, "threshold": 50, "compare_close": False},
    "ppo": {"params": {"fast": 12, "slow": 26, "signal": 9}, "threshold": 0, "compare_close": False},

    # Multi-output indicators (16) - using primary output
    "macd": {"params": {"fast": 12, "slow": 26, "signal": 9}, "output_key": "macd", "threshold": 0, "compare_close": False, "multi": True},
    "bbands": {"params": {"length": 20, "std": 2.0}, "output_key": "middle", "threshold": 0, "compare_close": True, "multi": True},
    "stoch": {"params": {"k": 14, "d": 3, "smooth_k": 3}, "output_key": "k", "threshold": 50, "compare_close": False, "multi": True},
    "stochrsi": {"params": {"length": 14, "rsi_length": 14, "k": 3, "d": 3}, "output_key": "k", "threshold": 50, "compare_close": False, "multi": True},
    "adx": {"params": {"length": 14}, "output_key": "adx", "threshold": 25, "compare_close": False, "multi": True},
    "aroon": {"params": {"length": 14}, "output_key": "osc", "threshold": 0, "compare_close": False, "multi": True},
    "kc": {"params": {"length": 20, "scalar": 2.0}, "output_key": "basis", "threshold": 0, "compare_close": True, "multi": True},
    "donchian": {"params": {"lower_length": 20, "upper_length": 20}, "output_key": "middle", "threshold": 0, "compare_close": True, "multi": True},
    "supertrend": {"params": {"length": 10, "multiplier": 3.0}, "output_key": "direction", "threshold": 0, "compare_close": False, "multi": True},
    "psar": {"params": {"af0": 0.02, "af": 0.02, "max_af": 0.2}, "output_key": "long", "threshold": 0, "compare_close": True, "multi": True},
    "squeeze": {"params": {"bb_length": 20, "bb_std": 2.0, "kc_length": 20, "kc_scalar": 1.5}, "output_key": "sqz", "threshold": 0, "compare_close": False, "multi": True},
    "vortex": {"params": {"length": 14}, "output_key": "vip", "threshold": 1.0, "compare_close": False, "multi": True},
    "dm": {"params": {"length": 14}, "output_key": "dmp", "threshold": 0, "compare_close": False, "multi": True},
    "fisher": {"params": {"length": 9}, "output_key": "fisher", "threshold": 0, "compare_close": False, "multi": True},
    "tsi": {"params": {"fast": 13, "slow": 25, "signal": 13}, "output_key": "tsi", "threshold": 0, "compare_close": False, "multi": True},
    "kvo": {"params": {"fast": 34, "slow": 55, "signal": 13}, "output_key": "kvo", "threshold": 0, "compare_close": False, "multi": True},
}


def generate_play(indicator_name: str, config: dict) -> dict:
    """Generate a simple Play for testing an indicator."""
    is_multi = config.get("multi", False)
    output_key = config.get("output_key", indicator_name)

    # For multi-output, the full key is indicator_outputkey (e.g., macd_macd)
    if is_multi:
        indicator_key = f"{indicator_name}_{output_key}"
    else:
        indicator_key = indicator_name

    # Build entry condition
    if config.get("compare_close", False):
        # Compare close > indicator (price above MA)
        entry_condition = {
            "tf": "exec",
            "indicator_key": "close",
            "operator": "gt",
            "value": indicator_key,
            "is_indicator_comparison": True,
        }
        exit_condition = {
            "tf": "exec",
            "indicator_key": "close",
            "operator": "lt",
            "value": indicator_key,
            "is_indicator_comparison": True,
        }
    else:
        # Compare indicator > threshold
        entry_condition = {
            "tf": "exec",
            "indicator_key": indicator_key,
            "operator": "gt",
            "value": config["threshold"],
            "is_indicator_comparison": False,
        }
        exit_condition = {
            "tf": "exec",
            "indicator_key": indicator_key,
            "operator": "lt",
            "value": config["threshold"],
            "is_indicator_comparison": False,
        }

    return {
        "id": f"stress_test_{indicator_name}",
        "version": "1.0.0",
        "name": f"Stress Test: {indicator_name}",
        "description": f"Auto-generated test for {indicator_name} indicator",
        "account": {
            "starting_equity_usdt": 10000.0,
            "max_leverage": 3.0,
            "margin_mode": "isolated_usdt",
            "min_trade_notional_usdt": 10.0,
            "fee_model": {"taker_bps": 6.0, "maker_bps": 2.0},
            "slippage_bps": 2.0,
        },
        "symbol_universe": ["BTCUSDT"],
        "timeframes": {"exec": "1h"},
        "tf_configs": {
            "exec": {
                "role": "exec",
                "warmup_bars": 100,
                "feature_specs": [
                    {
                        "indicator_type": indicator_name,
                        "output_key": indicator_name,
                        "params": config["params"],
                        "input_source": "close",
                    }
                ],
            }
        },
        "position_policy": {
            "mode": "long_only",
            "max_positions_per_symbol": 1,
            "allow_flip": False,
            "allow_scale_in": False,
            "allow_scale_out": False,
        },
        "signal_rules": {
            "entry_rules": [{"direction": "long", "conditions": [entry_condition]}],
            "exit_rules": [{"direction": "long", "conditions": [exit_condition]}],
        },
        "risk_model": {
            "stop_loss": {"type": "percent", "value": 5.0},
            "take_profit": {"type": "rr_ratio", "value": 2.0},
            "sizing": {"model": "percent_equity", "value": 2.0, "max_leverage": 3.0},
        },
    }


def run_test(indicator_name: str, config: dict, plays_dir: Path) -> tuple[bool, str, int]:
    """Run a single indicator test. Returns (success, message, trade_count)."""
    import subprocess
    import re

    try:
        # Generate Play
        card_dict = generate_play(indicator_name, config)

        # Write to plays directory
        card_path = plays_dir / f"stress_test_{indicator_name}.yml"
        with open(card_path, 'w') as f:
            yaml.dump(card_dict, f, default_flow_style=False)

        try:
            # Run via CLI
            result = subprocess.run(
                [
                    sys.executable,
                    str(plays_dir.parent.parent / "trade_cli.py"),
                    "backtest", "run",
                    "--idea-card", f"stress_test_{indicator_name}",
                    "--start", "2025-11-01",
                    "--end", "2025-12-01",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

            output = result.stdout + result.stderr

            # Check for success
            if "Backtest complete:" in output:
                # Extract trade count
                match = re.search(r"Trades:\s*(\d+)", output)
                trade_count = int(match.group(1)) if match else 0
                return True, "OK", trade_count
            elif "FAIL" in output or result.returncode != 0:
                # Extract error message
                fail_match = re.search(r"FAIL\s+(.+?)(?:\n|$)", output)
                error_match = re.search(r"\[ERROR\]\s*(.+?)(?:\n|$)", output)
                msg = fail_match.group(1) if fail_match else (error_match.group(1) if error_match else "Unknown")
                return False, msg[:80], 0
            else:
                return False, "No output", 0

        finally:
            # Cleanup
            if card_path.exists():
                card_path.unlink()

    except subprocess.TimeoutExpired:
        return False, "Timeout", 0
    except Exception as e:
        return False, str(e)[:80], 0


def main():
    print("=" * 70)
    print("INDICATOR STRESS TEST - Testing all 42 indicators")
    print("=" * 70)
    print()

    # Get plays directory
    script_dir = Path(__file__).parent
    plays_dir = script_dir.parent / "configs" / "plays"

    results = {"pass": [], "fail": []}

    for i, (name, config) in enumerate(INDICATORS.items(), 1):
        is_multi = config.get("multi", False)
        indicator_type = "multi" if is_multi else "single"

        print(f"[{i:2d}/42] Testing {name} ({indicator_type})... ", end="", flush=True)

        success, message, trades = run_test(name, config, plays_dir)

        if success:
            print(f"PASS ({trades} trades)")
            results["pass"].append((name, trades))
        else:
            print(f"FAIL: {message}")
            results["fail"].append((name, message))

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Passed: {len(results['pass'])}/42")
    print(f"Failed: {len(results['fail'])}/42")

    if results["fail"]:
        print()
        print("Failed indicators:")
        for name, msg in results["fail"]:
            print(f"  - {name}: {msg}")

    print()
    print("Trade counts by indicator:")
    for name, trades in sorted(results["pass"], key=lambda x: -x[1]):
        print(f"  {name}: {trades}")

    return 0 if not results["fail"] else 1


if __name__ == "__main__":
    sys.exit(main())
