#!/usr/bin/env python3
"""
PostToolUse hook: Remind to run validation after editing backtest code.

Non-blocking reminder (exit 0 with stdout message).
"""

import sys
import json


def main():
    input_data = json.load(sys.stdin)

    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    # Check if this is backtest-related code
    if "src/backtest" in file_path or "src/tools/backtest" in file_path:
        print(
            "Backtest code modified. Run /validate or:\n"
            "  python trade_cli.py backtest play-normalize-batch --dir tests/functional/plays\n"
            "  python trade_cli.py backtest audit-toolkit\n"
            "  python trade_cli.py --smoke backtest"
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
