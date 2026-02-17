#!/usr/bin/env python3
"""
PostToolUse hook: Run pyright on edited Python files.

Exit 2 + stderr = blocking feedback shown to Claude.
Always runs from project root so pyrightconfig.json (reportMissingImports: none) is used.
"""

import sys
import json
import subprocess
from pathlib import Path


def find_project_root(start: Path) -> Path:
    """Walk up from start until we find a directory containing pyrightconfig.json."""
    for parent in [start, *start.parents]:
        if (parent / "pyrightconfig.json").exists():
            return parent
    return start


def main():
    data = json.load(sys.stdin)
    file_path = data.get("tool_input", {}).get("file_path", "")
    cwd = Path(data.get("cwd", ".")).resolve()

    if not file_path.endswith(".py"):
        sys.exit(0)

    project_root = find_project_root(cwd)
    # Use path relative to project root so pyright resolves imports correctly
    try:
        path = Path(file_path).resolve()
        root = project_root.resolve()
        if path.is_relative_to(root):
            file_path = str(path.relative_to(root))
    except (ValueError, OSError):
        pass

    try:
        result = subprocess.run(
            ["pyright", file_path],
            capture_output=True,
            text=True,
            timeout=25,
            cwd=str(project_root),
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
