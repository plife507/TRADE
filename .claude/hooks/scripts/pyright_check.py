#!/usr/bin/env python3
"""
PostToolUse hook: Run pyright on edited Python files.

Exit 2 + stderr = blocking feedback shown to Claude.
"""

import sys
import json
import subprocess


def main():
    data = json.load(sys.stdin)
    file_path = data.get("tool_input", {}).get("file_path", "")
    cwd = data.get("cwd", ".")

    if not file_path.endswith(".py"):
        sys.exit(0)

    try:
        result = subprocess.run(
            ["pyright", file_path],
            capture_output=True,
            text=True,
            timeout=25,
            cwd=cwd,
        )
    except Exception as e:
        print(f"pyright hook error: {e}", file=sys.stderr)
        sys.exit(0)

    if result.returncode != 0:
        lines = result.stdout.strip().split("\n")
        errors = [ln.strip() for ln in lines if "- error:" in ln]
        if errors:
            msg = f"pyright: {len(errors)} error(s)\n" + "\n".join(errors)
            print(msg, file=sys.stderr)
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
