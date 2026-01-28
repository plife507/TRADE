#!/usr/bin/env python
"""
Run the full TRADE validation suite (125 plays).

Usage:
    python scripts/run_validation_suite.py [--tier TIER] [--quick]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Suppress logging noise before imports
os.environ['TRADE_LOG_LEVEL'] = 'WARNING'
logging.disable(logging.INFO)
for name in ['src', 'src.backtest', 'src.engine', 'src.data', 'src.indicators']:
    logging.getLogger(name).setLevel(logging.WARNING)

from src.backtest.play import load_play
from src.backtest.engine_factory import create_engine_from_play, run_engine_with_play


@dataclass
class PlayResult:
    """Result of running a single validation play."""
    play_id: str
    success: bool
    trades: int
    final_equity: float
    duration_sec: float
    error: str | None = None


def find_validation_plays(tier: str | None = None) -> list[Path]:
    """Find all validation play files."""
    base_dir = Path("tests/validation/plays")

    if tier:
        # Find specific tier
        tier_dirs = list(base_dir.glob(f"tier{tier}*"))
        if not tier_dirs:
            tier_dirs = list(base_dir.glob(f"*{tier}*"))
    else:
        tier_dirs = sorted(base_dir.iterdir())

    plays = []
    for tier_dir in tier_dirs:
        if tier_dir.is_dir():
            plays.extend(sorted(tier_dir.glob("*.yml")))

    return plays


def run_single_play(play_path: Path) -> PlayResult:
    """Run a single validation play and return result."""
    play_id = play_path.stem
    start = time.perf_counter()

    try:
        play = load_play(play_id)
        engine = create_engine_from_play(play)
        result = run_engine_with_play(engine, play)

        # Extract metrics from result
        trades = len(result.trades) if hasattr(result, 'trades') else 0

        # Get final equity from equity curve
        final_equity = 0.0
        if hasattr(result, 'equity') and result.equity:
            last_eq = result.equity[-1]
            if isinstance(last_eq, dict):
                final_equity = last_eq.get('equity', 0)
            elif hasattr(last_eq, 'equity'):
                final_equity = last_eq.equity
            else:
                final_equity = float(last_eq) if last_eq else 0.0

        duration = time.perf_counter() - start

        return PlayResult(
            play_id=play_id,
            success=True,
            trades=trades,
            final_equity=final_equity,
            duration_sec=duration,
        )
    except Exception as e:
        duration = time.perf_counter() - start
        return PlayResult(
            play_id=play_id,
            success=False,
            trades=0,
            final_equity=0.0,
            duration_sec=duration,
            error=str(e),
        )


def main():
    parser = argparse.ArgumentParser(description="Run TRADE validation suite")
    parser.add_argument("--tier", help="Run specific tier (e.g., '0', '5')")
    parser.add_argument("--quick", action="store_true", help="Run only tier0 smoke test")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    args = parser.parse_args()

    if args.quick:
        args.tier = "0"

    # Find plays
    plays = find_validation_plays(args.tier)

    if not plays:
        print(f"No validation plays found")
        return 1

    print(f"\n{'='*70}")
    print(f"TRADE VALIDATION SUITE")
    print(f"{'='*70}")
    print(f"Found {len(plays)} validation plays\n")

    # Run each play
    results: list[PlayResult] = []
    passed = 0
    failed = 0

    for i, play_path in enumerate(plays, 1):
        play_id = play_path.stem
        tier = play_path.parent.name

        print(f"[{i:3d}/{len(plays)}] {tier}/{play_id}...", end=" ", flush=True)

        result = run_single_play(play_path)
        results.append(result)

        if result.success:
            passed += 1
            print(f"PASS  ({result.trades:4d} trades, eq={result.final_equity:8.2f}, {result.duration_sec:.1f}s)")
        else:
            failed += 1
            print(f"FAIL  ({result.error})")

    # Summary
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"Total:  {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    total_time = sum(r.duration_sec for r in results)
    print(f"Time:   {total_time:.1f}s")

    if failed > 0:
        print(f"\nFailed plays:")
        for r in results:
            if not r.success:
                print(f"  - {r.play_id}: {r.error}")
        return 1

    print(f"\n{'='*70}")
    print(f"ALL {passed} PLAYS PASSED")
    print(f"{'='*70}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
