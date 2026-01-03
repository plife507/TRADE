#!/usr/bin/env python3
"""
Post-edit hook: Remind to run validation after editing backtest code.
"""

import sys
import json


def main():
    # Read hook input from stdin
    input_data = json.load(sys.stdin)

    file_path = input_data.get("file_path", "")

    # Check if this is backtest-related code
    if "src/backtest" in file_path or "src/tools/backtest" in file_path:
        print(json.dumps({
            "status": "continue",
            "message": (
                "Backtest code modified. Remember to validate:\n"
                "  python trade_cli.py backtest audit-toolkit\n"
                "  python trade_cli.py backtest idea-card-normalize-batch --dir configs/idea_cards/_validation\n"
                "  python trade_cli.py --smoke backtest"
            )
        }))
    else:
        print(json.dumps({"status": "continue"}))


if __name__ == "__main__":
    main()
