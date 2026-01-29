"""
Concurrency Auditor Agent - Finds thread safety and race condition issues.

Focus areas:
- Shared state without locks
- Check-then-act race conditions
- Lock ordering violations
- Blocking in async context
"""

from .base import AgentDefinition, SeverityRule, register_agent
from ..types import FindingCategory, Severity


CONCURRENCY_AUDITOR = register_agent(AgentDefinition(
    name="concurrency_auditor",
    display_name="Concurrency Auditor",
    category=FindingCategory.CONCURRENCY,
    description="Identifies thread safety issues, race conditions, and async/await problems.",
    id_prefix="CONC",
    target_paths=[
        "src/core/",
        "src/data/",
        "src/exchanges/",
        "src/engine/",
    ],
    file_patterns=["*.py"],
    severity_rules=[
        SeverityRule(
            pattern="Shared mutable state accessed without locks",
            severity=Severity.HIGH,
            examples=["self.positions[symbol] = pos (in threaded context)", "global_state.update(...)"],
        ),
        SeverityRule(
            pattern="Check-then-act race conditions",
            severity=Severity.HIGH,
            examples=["if key in dict: dict[key] (between threads)", "if file.exists(): file.read()"],
        ),
        SeverityRule(
            pattern="Lock ordering violations (potential deadlock)",
            severity=Severity.HIGH,
            examples=["lock_a.acquire(); lock_b.acquire() vs lock_b.acquire(); lock_a.acquire()"],
        ),
        SeverityRule(
            pattern="Blocking calls in async context",
            severity=Severity.HIGH,
            examples=["await asyncio.sleep(0); time.sleep(1)", "requests.get() in async def"],
        ),
        SeverityRule(
            pattern="Missing lock on class with threading",
            severity=Severity.MEDIUM,
            examples=["Class with Thread but no Lock", "Daemon thread updating shared state"],
        ),
        SeverityRule(
            pattern="Using threading.Lock instead of threading.RLock for reentrant code",
            severity=Severity.MEDIUM,
            examples=["Lock used in recursive function", "Lock held when calling method that needs same lock"],
        ),
        SeverityRule(
            pattern="Forgotten await on coroutine",
            severity=Severity.MEDIUM,
            examples=["async_method()  # missing await", "result = coro()  # coroutine not awaited"],
        ),
    ],
    system_prompt="""You are a concurrency auditor for a cryptocurrency trading bot. Your job is to find
thread safety issues and race conditions that could cause data corruption.

## Primary Focus Areas

1. **Shared State Without Locks**
   - Mutable instance variables accessed from multiple threads
   - Global state modified without synchronization
   - Cache updates without thread safety
   - Position/order state modified concurrently

2. **Check-Then-Act Race Conditions**
   - `if key in dict: use dict[key]` between threads
   - `if balance > amount: withdraw(amount)` without lock
   - `if order.status == X: order.status = Y` without atomicity
   - File existence checks before reads

3. **Lock Issues**
   - Inconsistent lock ordering (deadlock potential)
   - Lock not released in exception paths
   - Using Lock when RLock needed (recursive calls)
   - Locks held during I/O (blocking others)

4. **Async/Await Issues**
   - Blocking calls (time.sleep, requests.get) in async functions
   - Missing await on coroutines
   - Mixing asyncio with threading incorrectly
   - Event loop blocking

## Trading-Specific Concurrency Concerns
- Position state must be thread-safe (multiple order callbacks)
- Balance updates from different WebSocket streams
- Order ID tracking during concurrent order placement
- Rate limiter state shared across threads

## What to Look For
- Classes with `threading.Thread` but no `threading.Lock`
- Methods modifying `self.*` in classes used by multiple threads
- Pattern `if ... in self.*: self.*[...]` without lock
- `time.sleep` or `requests.*` inside `async def`
- Coroutine calls without `await`

## False Positive Prevention
- Single-threaded code (check for Thread/Process usage)
- Immutable shared state (frozen dataclasses, tuples)
- Thread-local storage is OK
- Queue-based communication is thread-safe
- asyncio.Lock used correctly is OK
""",
))
