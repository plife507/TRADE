#!/usr/bin/env python3
"""
PreToolUse hook: Block potential secrets in code.

Uses exit code 2 to block tool execution when secrets detected.
"""

import sys
import json
import re


# Patterns that indicate potential secrets
SECRET_PATTERNS = [
    (r'BYBIT_.*_API_KEY\s*=\s*["\'][^"\']+["\']', "Hardcoded Bybit API key"),
    (r'BYBIT_.*_SECRET\s*=\s*["\'][^"\']+["\']', "Hardcoded Bybit secret"),
    (r'api_key\s*=\s*["\'][a-zA-Z0-9]{20,}["\']', "Hardcoded API key"),
    (r'secret\s*=\s*["\'][a-zA-Z0-9]{20,}["\']', "Hardcoded secret"),
    (r'password\s*=\s*["\'][^"\']{8,}["\']', "Hardcoded password"),
]


def main():
    input_data = json.load(sys.stdin)

    # Get content from Edit or Write tool input
    tool_input = input_data.get("tool_input", {})
    content = tool_input.get("content", "") or tool_input.get("new_string", "")
    file_path = tool_input.get("file_path", "")

    # Skip .env files (they're supposed to have secrets)
    if ".env" in file_path:
        sys.exit(0)

    # Check for secret patterns
    for pattern, description in SECRET_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            # Exit code 2 = blocking error, stderr shown to Claude
            print(
                f"SECURITY BLOCK: {description} detected in {file_path}. "
                "Use environment variables instead.",
                file=sys.stderr
            )
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
