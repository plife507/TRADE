"""
Error Handler Reviewer Agent - Validates exception handling patterns.

Focus areas:
- Silent failures (except: pass)
- Lost stack traces
- Missing error logging on critical paths
- Resource cleanup in finally blocks
"""

from .base import AgentDefinition, SeverityRule, register_agent
from ..types import FindingCategory, Severity


ERROR_HANDLER_REVIEWER = register_agent(AgentDefinition(
    name="error_handler_reviewer",
    display_name="Error Handler Reviewer",
    category=FindingCategory.ERROR_HANDLING,
    description="Validates exception handling, error logging, and resource cleanup patterns.",
    id_prefix="ERR",
    target_paths=[
        "src/core/",
        "src/backtest/sim/",
        "src/exchanges/",
        "src/data/",
    ],
    file_patterns=["*.py"],
    severity_rules=[
        SeverityRule(
            pattern="Silent failures: except: pass or except Exception: pass",
            severity=Severity.HIGH,
            examples=["except: pass", "except Exception: pass", "except: continue"],
        ),
        SeverityRule(
            pattern="Lost stack traces: except as e: raise NewError(str(e))",
            severity=Severity.HIGH,
            examples=["raise RuntimeError(str(e))", "raise ValueError(e.args[0])"],
        ),
        SeverityRule(
            pattern="Missing error logging on critical paths (orders, positions)",
            severity=Severity.HIGH,
            examples=["Order execution without error logging", "Position updates without error tracking"],
        ),
        SeverityRule(
            pattern="Bare except clause (catches SystemExit, KeyboardInterrupt)",
            severity=Severity.MEDIUM,
            examples=["except:", "try: ... except:"],
        ),
        SeverityRule(
            pattern="Missing finally block for resource cleanup",
            severity=Severity.MEDIUM,
            examples=["File handle without try/finally", "DB connection without cleanup"],
        ),
        SeverityRule(
            pattern="Overly broad exception catching",
            severity=Severity.MEDIUM,
            examples=["except Exception:", "except BaseException:"],
        ),
        SeverityRule(
            pattern="Error messages without context",
            severity=Severity.LOW,
            examples=["raise ValueError('Invalid')", "logger.error('Failed')"],
        ),
    ],
    system_prompt="""You are an error handling reviewer for a cryptocurrency trading bot. Your job is
to find error handling issues that could cause silent failures or lost information.

## Primary Focus Areas

1. **Silent Failures**
   - `except: pass` - completely swallows errors
   - `except Exception: pass` - silently ignores all exceptions
   - `except: continue` - skips errors in loops
   - Empty except blocks with only logging but no re-raise

2. **Lost Stack Traces**
   - `raise NewError(str(e))` - loses original traceback
   - `raise NewError(e.args[0])` - loses context
   - Should use `raise NewError(...) from e` to preserve chain

3. **Critical Path Error Handling**
   - Order execution MUST log errors before propagating
   - Position updates MUST have error handling
   - Balance checks MUST handle API failures gracefully
   - WebSocket disconnects MUST be logged

4. **Resource Cleanup**
   - File handles need try/finally or context managers
   - Database connections need cleanup
   - Network connections need timeout handling
   - Locks need release in finally blocks

## Trading-Specific Error Concerns
- Order failures that don't get logged could cause position drift
- Silent API errors could leave orders in unknown state
- WebSocket errors need reconnection logic
- Rate limit errors need backoff handling

## What to Look For
- Pattern `except:` or `except Exception:` followed by `pass`
- Pattern `raise SomeError(str(e))` without `from e`
- Try blocks without finally for file/connection handling
- Order/position methods without error logging

## False Positive Prevention
- `except Exception as e: logger.error(...); raise` is OK (logs then propagates)
- Test code with intentional error swallowing is OK
- `except SpecificError:` with appropriate handling is OK
- `except: pass` in cleanup code where errors are expected is sometimes OK
""",
))
