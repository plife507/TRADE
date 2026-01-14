#!/usr/bin/env python3
"""
Pre-edit hook: Block potential secrets in code.
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

    content = input_data.get("content", "")
    file_path = input_data.get("file_path", "")

    # Skip .env files (they're supposed to have secrets)
    if ".env" in file_path:
        print(json.dumps({"status": "continue"}))
        return

    # Check for secret patterns
    for pattern, description in SECRET_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            print(json.dumps({
                "status": "block",
                "reason": f"SECURITY: {description} detected in {file_path}. Use environment variables instead."
            }))
            return

    print(json.dumps({"status": "continue"}))


if __name__ == "__main__":
    main()
