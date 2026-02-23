#!/usr/bin/env python3
"""
Run P12 manual verification: health check + WebSocket tri-state from terminal.

Usage (from project root):
  python scripts/run_ws_verification.py              # Health + WS status only
  python scripts/run_ws_verification.py --symbol X   # Use symbol for health check (default BTCUSDT)

No play is started; WS state should show "not started".
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Project root
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from src.tools.diagnostics_tools import exchange_health_check_tool, get_websocket_status_tool


def main() -> int:
    ap = argparse.ArgumentParser(description="Health check + WS tri-state (no play)")
    ap.add_argument("--symbol", default="BTCUSDT", help="Symbol for exchange health check")
    args = ap.parse_args()

    print("=== Health check (exchange) ===")
    result = exchange_health_check_tool(symbol=args.symbol)
    print(f"  Success: {result.success}")
    print(f"  Message: {result.message}")
    if result.error:
        print(f"  Error: {result.error}")
    if result.data:
        for k, v in (result.data or {}).items():
            if k not in ("tests", "checks"):
                print(f"  {k}: {v}")
        if "tests" in (result.data or {}):
            for t in (result.data or {}).get("tests", []):
                if isinstance(t, dict):
                    print(f"  - {t.get('name', '?')}: {t.get('passed', '?')}")
                else:
                    print(f"  - {t}")

    print("\n=== WebSocket status (tri-state) ===")
    ws_result = get_websocket_status_tool()
    print(f"  Success: {ws_result.success}")
    print(f"  Message: {ws_result.message}")
    if ws_result.data:
        d = ws_result.data
        print(f"  websocket_connected: {d.get('websocket_connected')}")
        print(f"  ws_not_started: {d.get('ws_not_started')}")
        print(f"  using_rest_fallback: {d.get('using_rest_fallback')}")
        for stream in ("public", "private"):
            if stream in d and isinstance(d[stream], dict):
                print(f"  {stream}.state: {d[stream].get('state')}")

    print("\nExpected when no play is running: ws_not_started=True, state=not_started")
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
