"""
Run the full indicator/operator/structure/pattern test suite.

Runs all plays sequentially on synthetic or real data.
Outputs a summary CSV and identifies failures, zero-trade plays, and bugs.

Synthetic mode uses each play's validation: block for pattern.
Bars are auto-computed from warmup requirements (warmup + 300 trading bars).
Override with --synthetic-bars to force a fixed bar count.

Usage:
    python scripts/run_full_suite.py [--suite SUITE]
    python scripts/run_full_suite.py --synthetic-bars 800  # force bar count
    python scripts/run_full_suite.py --real --start 2025-10-01 --end 2026-01-01
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
import time
from pathlib import Path


def get_play_pattern(play_stem: str) -> str:
    """Read the validation pattern from a play's YAML file.

    Falls back to 'trending' if no validation: block found.
    """
    plays_root = Path("plays") / "validation"
    # Search all subdirectories
    for yml in plays_root.rglob(f"{play_stem}.yml"):
        try:
            content = yml.read_text(encoding="utf-8")
            m = re.search(r'validation:\s*\n\s+pattern:\s*"?([^"\n]+)"?', content)
            if m:
                return m.group(1).strip()
        except Exception:
            pass
    return "trending"


def discover_plays(suite_dirs: list[Path]) -> list[str]:
    """Discover all play file stems from suite directories."""
    plays = []
    for d in suite_dirs:
        if d.exists():
            for f in sorted(d.glob("*.yml")):
                plays.append(f.stem)
    return plays


def run_play(
    play_stem: str,
    max_retries: int = 5,
    real_data: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
    synthetic_bars: int | None = None,
) -> dict:
    """Run a single play and return results. Retries on DuckDB lock."""
    pattern = get_play_pattern(play_stem)

    if real_data:
        cmd = [
            sys.executable, "trade_cli.py", "backtest", "run",
            "--play", play_stem,
            "--sync",
        ]
        if start_date:
            cmd.extend(["--start", start_date])
        if end_date:
            cmd.extend(["--end", end_date])
    else:
        cmd = [
            sys.executable, "trade_cli.py", "backtest", "run",
            "--play", play_stem,
            "--synthetic",
            "--no-artifacts",
        ]
        if synthetic_bars is not None:
            cmd.extend(["--synthetic-bars", str(synthetic_bars)])

    timeout_s = 600 if real_data else 120

    for attempt in range(max_retries):
        start_time = time.time()
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_s,
                cwd=str(Path(__file__).parent.parent),
                encoding="utf-8", errors="replace",
            )
            elapsed = time.time() - start_time

            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.returncode

            # Retry on DuckDB lock
            if exit_code != 0 and "being used by another process" in stderr:
                if attempt < max_retries - 1:
                    wait = 3 * (attempt + 1)
                    print(f"DB locked, retry {attempt+1}/{max_retries} in {wait}s...", end=" ", flush=True)
                    time.sleep(wait)
                    continue

            # Parse trade count and PnL from output
            trades = 0
            pnl = 0.0
            m = re.search(r"Trades:\s*(\d+)", stdout)
            if m:
                trades = int(m.group(1))
            m = re.search(r"PnL:\s*([-\d.]+)", stdout)
            if m:
                pnl = float(m.group(1))

            # Check for errors in stderr
            error_count = stderr.count("ERROR") + stderr.count("Error")
            warn_count = stderr.count("WARNING") + stderr.count("Warning")

            return {
                "play": play_stem,
                "pattern": pattern,
                "exit_code": exit_code,
                "trades": trades,
                "pnl": pnl,
                "elapsed_s": round(elapsed, 1),
                "errors": error_count,
                "warnings": warn_count,
                "status": "PASS" if exit_code == 0 else "FAIL",
                "error_msg": stderr[-200:] if exit_code != 0 else "",
            }

        except subprocess.TimeoutExpired:
            return {
                "play": play_stem,
                "pattern": pattern,
                "exit_code": -1,
                "trades": 0,
                "pnl": 0.0,
                "elapsed_s": float(timeout_s),
                "errors": 1,
                "warnings": 0,
                "status": "TIMEOUT",
                "error_msg": f"Timed out after {timeout_s}s",
            }
        except Exception as e:
            return {
                "play": play_stem,
                "pattern": pattern,
                "exit_code": -2,
                "trades": 0,
                "pnl": 0.0,
                "elapsed_s": 0,
                "errors": 1,
                "warnings": 0,
                "status": "ERROR",
                "error_msg": str(e)[:200],
            }

    # All retries exhausted (DuckDB lock)
    return {
        "play": play_stem,
        "pattern": pattern,
        "exit_code": -3,
        "trades": 0,
        "pnl": 0.0,
        "elapsed_s": 0,
        "errors": 1,
        "warnings": 0,
        "status": "DB_LOCKED",
        "error_msg": f"DuckDB locked after {max_retries} retries",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full test suite")
    parser.add_argument(
        "--suite", choices=["all", "indicator", "operator", "structure", "pattern", "cl"],
        default="all", help="Which suite(s) to run",
    )
    parser.add_argument("--synthetic-bars", type=int, default=None, help="Override auto-computed bar count")
    parser.add_argument("--start-from", type=str, default=None, help="Start from play ID")
    parser.add_argument("--real", action="store_true", help="Use real market data instead of synthetic")
    parser.add_argument("--start", type=str, default="2025-10-01", help="Start date for real data")
    parser.add_argument("--end", type=str, default="2026-01-01", help="End date for real data")
    args = parser.parse_args()

    plays_root = Path("plays") / "validation"
    suite_map = {
        "cl": [plays_root / "complexity"],
        "indicator": [plays_root / "indicators"],
        "operator": [plays_root / "operators"],
        "structure": [plays_root / "structures"],
        "pattern": [plays_root / "patterns"],
    }

    if args.suite == "all":
        dirs = []
        for v in suite_map.values():
            dirs.extend(v)
    else:
        dirs = suite_map[args.suite]

    plays = discover_plays(dirs)

    if args.start_from:
        idx = next((i for i, p in enumerate(plays) if p == args.start_from), 0)
        plays = plays[idx:]

    if args.real:
        mode = "real data"
    elif args.synthetic_bars:
        mode = f"synthetic data ({args.synthetic_bars} bars, forced)"
    else:
        mode = "synthetic data (bars auto-computed per play from indicator/structure warmup requirements)"
    print(f"Running {len(plays)} plays on {mode}...")
    if args.real:
        print(f"  Date range: {args.start} to {args.end}")
    print("=" * 80)

    results = []
    pass_count = 0
    fail_count = 0
    zero_trade_count = 0

    for i, play in enumerate(plays, 1):
        pattern = get_play_pattern(play)
        label = f"{args.start}..{args.end}" if args.real else pattern
        print(f"[{i}/{len(plays)}] {play} ({label})...", end=" ", flush=True)

        result = run_play(
            play,
            real_data=args.real,
            start_date=args.start if args.real else None,
            end_date=args.end if args.real else None,
            synthetic_bars=args.synthetic_bars,
        )
        results.append(result)

        status = result["status"]
        trades = result["trades"]
        elapsed = result["elapsed_s"]

        if status == "PASS":
            pass_count += 1
            if trades == 0:
                zero_trade_count += 1
                print(f"WARN 0-trades ({elapsed}s)")
            else:
                print(f"OK {trades} trades ({elapsed}s)")
        else:
            fail_count += 1
            print(f"FAIL: {result['error_msg'][:80]}")

    # Write CSV report
    report_name = "suite_report_real.csv" if args.real else "suite_report.csv"
    report_path = Path("backtests") / report_name
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", newline="\n") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "play", "pattern", "status", "exit_code", "trades", "pnl",
            "elapsed_s", "errors", "warnings", "error_msg",
        ])
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    # Summary
    print("\n" + "=" * 80)
    print(f"SUMMARY: {len(plays)} plays")
    print(f"  PASS:       {pass_count}")
    print(f"  FAIL:       {fail_count}")
    print(f"  0-trades:   {zero_trade_count}")
    print(f"  Report:     {report_path}")

    if fail_count > 0:
        print("\nFAILED PLAYS:")
        for r in results:
            if r["status"] != "PASS":
                print(f"  {r['play']}: {r['error_msg'][:100]}")

    if zero_trade_count > 0:
        print("\nZERO-TRADE PLAYS:")
        for r in results:
            if r["status"] == "PASS" and r["trades"] == 0:
                print(f"  {r['play']} ({r['pattern']})")


if __name__ == "__main__":
    main()
