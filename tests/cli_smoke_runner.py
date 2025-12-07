#!/usr/bin/env python3
"""
CLI Smoke Test Runner

A terminal-oriented driver script that runs the TRADE CLI smoke test suite.
This script invokes `python trade_cli.py --smoke [data|full]` via subprocess,
allowing the agent to run end-to-end tests through the real terminal.

Usage:
    python tests/cli_smoke_runner.py data   # Run data builder smoke test
    python tests/cli_smoke_runner.py full   # Run full CLI smoke test
    python tests/cli_smoke_runner.py        # Default: run full smoke test

Environment variables (optional overrides):
    TRADE_SMOKE_SYMBOLS     Comma-separated symbols (default: BTCUSDT,ETHUSDT,SOLUSDT)
    TRADE_SMOKE_PERIOD      Data pull period (default: 1Y)
    TRADE_SMOKE_USD_SIZE    Demo trade size in USD (default: 5)
"""

import os
import sys
import subprocess
import argparse
from datetime import datetime
from pathlib import Path


def get_project_root() -> Path:
    """Get the project root directory."""
    # This script is in tests/, so parent is project root
    return Path(__file__).parent.parent.resolve()


def run_smoke_test(mode: str = "full", verbose: bool = True) -> int:
    """
    Run the smoke test suite via subprocess.
    
    Args:
        mode: "data" for data builder only, "full" for all CLI features
        verbose: Print detailed output
    
    Returns:
        Exit code from the CLI (0 = success, non-zero = failure)
    """
    project_root = get_project_root()
    trade_cli_path = project_root / "trade_cli.py"
    
    if not trade_cli_path.exists():
        print(f"ERROR: trade_cli.py not found at {trade_cli_path}")
        return 1
    
    # Build command
    cmd = [sys.executable, str(trade_cli_path), "--smoke", mode]
    
    # Prepare environment (inherit current env, can be overridden)
    env = os.environ.copy()
    
    # Ensure DEMO/PAPER mode (redundant since CLI enforces this, but explicit)
    env.setdefault("BYBIT_USE_DEMO", "true")
    env.setdefault("TRADING_MODE", "paper")
    
    # Default smoke test settings if not set
    env.setdefault("TRADE_SMOKE_SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT")
    env.setdefault("TRADE_SMOKE_PERIOD", "1Y")
    env.setdefault("TRADE_SMOKE_USD_SIZE", "5")
    env.setdefault("TRADE_SMOKE_ENABLE_GAP_TESTING", "true")
    
    # Print header
    print("=" * 70)
    print(f"TRADE CLI SMOKE TEST RUNNER")
    print(f"Mode: {mode.upper()}")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Command: {' '.join(cmd)}")
    print("=" * 70)
    print()
    
    # Run the CLI
    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            env=env,
            # Stream output in real-time
            stdout=None if verbose else subprocess.PIPE,
            stderr=None if verbose else subprocess.PIPE,
        )
        exit_code = result.returncode
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Smoke test cancelled by user")
        return 130
    except Exception as e:
        print(f"\n[ERROR] Failed to run smoke test: {e}")
        return 1
    
    # Print footer
    print()
    print("=" * 70)
    print(f"SMOKE TEST COMPLETE")
    print(f"Finished: {datetime.now().isoformat()}")
    print(f"Exit Code: {exit_code}")
    if exit_code == 0:
        print("[PASSED] All tests completed successfully")
    else:
        print(f"[FAILED] Smoke test failed with exit code {exit_code}")
    print("=" * 70)
    
    return exit_code


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="TRADE CLI Smoke Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python tests/cli_smoke_runner.py data   # Data builder tests only
    python tests/cli_smoke_runner.py full   # Full CLI smoke test
    
Environment variables:
    TRADE_SMOKE_SYMBOLS     Symbols to test (default: BTCUSDT,ETHUSDT,SOLUSDT)
    TRADE_SMOKE_PERIOD      Data period (default: 1Y)
    TRADE_SMOKE_USD_SIZE    Demo trade size (default: 5)
        """
    )
    
    parser.add_argument(
        "mode",
        nargs="?",
        choices=["data", "full"],
        default="full",
        help="Smoke test mode: 'data' for data builder only, 'full' for all CLI features"
    )
    
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress detailed output (only show summary)"
    )
    
    args = parser.parse_args()
    
    # Run the smoke test
    exit_code = run_smoke_test(mode=args.mode, verbose=not args.quiet)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

