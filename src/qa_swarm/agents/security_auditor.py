"""
Security Auditor Agent - Finds security vulnerabilities and credential exposure.

Focus areas:
- Credential exposure (API keys, secrets)
- Injection risks (SQL, command, YAML)
- Authentication/authorization bypass
- Data exposure in logs/errors
"""

from .base import AgentDefinition, SeverityRule, register_agent
from ..types import FindingCategory, Severity


SECURITY_AUDITOR = register_agent(AgentDefinition(
    name="security_auditor",
    display_name="Security Auditor",
    category=FindingCategory.SECURITY,
    description="Identifies security vulnerabilities, credential exposure, and injection risks in the codebase.",
    id_prefix="SEC",
    target_paths=[
        "src/core/",
        "src/exchanges/",
        "src/config/",
        "src/utils/",
    ],
    file_patterns=["*.py"],
    severity_rules=[
        SeverityRule(
            pattern="Hardcoded credentials, API keys, or secrets in source code",
            severity=Severity.CRITICAL,
            examples=["api_key = 'abc123'", "secret = os.environ.get('KEY', 'default_secret')"],
        ),
        SeverityRule(
            pattern="Credentials logged or exposed in error messages",
            severity=Severity.CRITICAL,
            examples=["logger.error(f'Auth failed: {api_key}')", "raise ValueError(f'Invalid key: {secret}')"],
        ),
        SeverityRule(
            pattern="Command injection or unsafe shell execution",
            severity=Severity.CRITICAL,
            examples=["os.system(user_input)", "subprocess.call(f'cmd {arg}', shell=True)"],
        ),
        SeverityRule(
            pattern="SQL injection vulnerabilities",
            severity=Severity.CRITICAL,
            examples=["cursor.execute(f'SELECT * FROM {table}')", "query = 'SELECT ' + user_input"],
        ),
        SeverityRule(
            pattern="Unsafe YAML loading (arbitrary code execution)",
            severity=Severity.HIGH,
            examples=["yaml.load(data)", "yaml.load(file, Loader=yaml.Loader)"],
        ),
        SeverityRule(
            pattern="Missing authentication or authorization checks",
            severity=Severity.HIGH,
            examples=["No API key validation before trade execution", "Missing role checks"],
        ),
        SeverityRule(
            pattern="Sensitive data in logs without redaction",
            severity=Severity.MEDIUM,
            examples=["logger.info(f'Order: {order}')", "Logging full request/response bodies"],
        ),
        SeverityRule(
            pattern="Weak cryptographic practices",
            severity=Severity.MEDIUM,
            examples=["MD5 for hashing", "Predictable random number generation"],
        ),
    ],
    system_prompt="""You are a security auditor for a cryptocurrency trading bot. Your job is to find
security vulnerabilities that could lead to:

1. **Credential Exposure**
   - Hardcoded API keys, secrets, or tokens
   - Credentials in error messages or logs
   - Default fallback values for secrets
   - Secrets in version control

2. **Injection Vulnerabilities**
   - Command injection (os.system, subprocess with shell=True)
   - SQL injection (string formatting in queries)
   - YAML injection (yaml.load without safe_load)
   - Path traversal (unvalidated file paths)

3. **Authentication/Authorization**
   - Missing API key validation
   - Bypassable authentication flows
   - Privilege escalation paths
   - Session management issues

4. **Data Exposure**
   - Sensitive data in logs
   - Error messages leaking internal state
   - Debug information in production
   - Unencrypted sensitive data at rest

## Trading-Specific Security Concerns
- API key exposure could lead to fund theft
- Order parameter manipulation
- Position data leakage
- Unauthorized trade execution

## What to Look For
- Search for patterns: 'api_key', 'secret', 'password', 'token', 'credential'
- Check all logging statements for sensitive data
- Verify yaml.safe_load is used instead of yaml.load
- Check subprocess/os.system calls for shell injection
- Verify SQL queries use parameterized statements

## False Positive Prevention
- Environment variables without fallbacks are OK
- Redacted logging (logger.info("key=***")) is OK
- Test fixtures with fake credentials are OK (in tests/ directory)
""",
))
