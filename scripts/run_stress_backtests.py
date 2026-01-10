#!/usr/bin/env python3
"""Run all stress test backtests sequentially."""

import subprocess
import json
import sys
from pathlib import Path

GATES = [
    ("gate_22_indicator_edge_cases", 43),
    ("gate_23_structure_edge_cases", 18),
    ("gate_24_mixing", 24),
    ("gate_25_leverage_orders", 16),
]

def run_backtest(play_name: str, play_dir: str) -> dict:
    """Run a single backtest and return results."""
    cmd = [
        sys.executable, "trade_cli.py", "backtest", "run",
        "--play", play_name,
        "--dir", play_dir,
        "--fix-gaps",
        "--json"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        output = result.stdout + result.stderr
        # Try to parse JSON from output
        for line in output.split('\n'):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    pass
        # Try to find JSON block
        if '{' in output:
            start = output.rfind('{')
            end = output.rfind('}') + 1
            if start < end:
                try:
                    return json.loads(output[start:end])
                except json.JSONDecodeError:
                    pass
        return {"status": "error", "message": output[:500]}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "message": "Backtest timed out"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def main():
    base_dir = Path("tests/stress/plays")
    results = []
    zero_trade_plays = []
    errors = []

    print("=" * 70)
    print("STRESS TEST 3.0 - SEQUENTIAL BACKTEST RUN")
    print("=" * 70)
    print()

    total_plays = sum(count for _, count in GATES)
    completed = 0

    for gate_name, expected_count in GATES:
        gate_dir = base_dir / gate_name
        print(f"\n>>> Processing {gate_name} ({expected_count} plays)")
        print("-" * 50)

        plays = sorted(gate_dir.glob("*.yml"))

        for play_file in plays:
            play_name = play_file.stem
            completed += 1
            print(f"[{completed}/{total_plays}] {play_name}: ", end="", flush=True)

            result = run_backtest(play_name, str(gate_dir) + "/")

            status = result.get("status", "unknown")
            data = result.get("data", {})
            metrics = data.get("metrics", {}) if isinstance(data, dict) else {}

            trades = metrics.get("total_trades", 0)
            pnl = metrics.get("total_pnl", 0)

            results.append({
                "gate": gate_name,
                "play": play_name,
                "status": status,
                "trades": trades,
                "pnl": pnl,
            })

            if status == "success":
                if trades == 0:
                    print(f"OK (0 trades - INVESTIGATE)")
                    zero_trade_plays.append(play_name)
                else:
                    print(f"OK ({trades} trades, PnL: {pnl:.2f})")
            else:
                print(f"FAIL: {result.get('message', 'Unknown error')[:80]}")
                errors.append(play_name)

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    success_count = sum(1 for r in results if r["status"] == "success")
    fail_count = sum(1 for r in results if r["status"] != "success")

    print(f"Total Plays: {len(results)}")
    print(f"Success: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"Zero-trade plays: {len(zero_trade_plays)}")

    if zero_trade_plays:
        print()
        print("PLAYS WITH 0 TRADES (need investigation):")
        for p in zero_trade_plays:
            print(f"  - {p}")

    if errors:
        print()
        print("FAILED PLAYS:")
        for p in errors:
            print(f"  - {p}")

    # Save results
    results_file = Path("backtests/stress_test_3_results.json")
    results_file.parent.mkdir(parents=True, exist_ok=True)
    with open(results_file, 'w', newline='\n') as f:
        json.dump({
            "total": len(results),
            "success": success_count,
            "failed": fail_count,
            "zero_trades": zero_trade_plays,
            "errors": errors,
            "results": results,
        }, f, indent=2)
    print(f"\nResults saved to: {results_file}")

if __name__ == "__main__":
    main()
