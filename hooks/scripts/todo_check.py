#!/usr/bin/env python3
"""
Pre-edit hook: Remind about TODO-driven development.

TRADE rule: MUST NOT write code before TODO exists.
"""

import sys
import json


def main():
    input_data = json.load(sys.stdin)

    file_path = input_data.get("file_path", "")

    # Only remind for Python source files
    if file_path.endswith(".py") and "src/" in file_path:
        print(json.dumps({
            "status": "continue",
            "message": (
                "TRADE Rule Reminder: Ensure TODO exists in docs/todos/TODO.md "
                "before writing code. Every code change maps to a TODO checkbox."
            )
        }))
    else:
        print(json.dumps({"status": "continue"}))


if __name__ == "__main__":
    main()
