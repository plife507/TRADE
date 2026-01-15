#!/usr/bin/env python3
"""
PreToolUse hook: Remind about TODO-driven development.

TRADE rule: MUST NOT write code before TODO exists.
Non-blocking reminder (exit 0 with stdout message).
"""

import sys
import json


def main():
    input_data = json.load(sys.stdin)

    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    # Only remind for Python source files in src/
    if file_path.endswith(".py") and "src/" in file_path:
        # Print reminder - Claude will see this as context
        print(
            "TRADE Rule: Ensure TODO exists in docs/todos/TODO.md "
            "before writing code. Every code change maps to a TODO checkbox."
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
