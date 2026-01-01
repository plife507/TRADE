# Exception Hierarchy Review

> **Date**: 2025-12-27
> **Scope**: `src/` directory
> **Status**: Review complete, recommendations pending implementation

---

## Executive Summary

The TRADE codebase uses a **flat, pragmatic exception model** with only 3 custom exception classes. While functional, the current approach lacks domain-specific hierarchy, making it difficult to catch and handle errors by category.

| Metric | Current State |
|--------|---------------|
| Custom exceptions | 3 |
| Hierarchy depth | 1 (all inherit directly from `Exception`) |
| Bare `except Exception` usage | ~95% of catch blocks |
| Domain-specific error types | None |

---

## Current Custom Exceptions

### 1. `BybitAPIError` (`src/exchanges/bybit_client.py:42-60`)

Wraps pybit library exceptions for backward compatibility.

```python
class BybitAPIError(Exception):
    def __init__(self, code: int, message: str, response: dict = None, original: Exception = None):
        self.code = code
        self.message = message
        self.response = response
        self.original = original
        super().__init__(message)

    @classmethod
    def from_pybit(cls, e: Exception) -> "BybitAPIError":
        ...
```

**Strengths**: Factory method, preserves original exception, stores response context.

### 2. `TradingEnvMismatchError` (`src/tools/shared.py:96-98`)

Raised when tool's trading environment doesn't match process config.

```python
class TradingEnvMismatchError(Exception):
    pass
```

**Weakness**: No custom attributes or context.

### 3. `GateFailure` (`src/backtest/runner.py:81-83`)

Raised when a backtest gate (preflight, artifact validation) fails.

```python
class GateFailure(Exception):
    pass
```

**Weakness**: No distinction between gate types, no failure context.

---

## Exception Usage Patterns

### Raising Patterns

| Exception Type | Count | Primary Use |
|----------------|-------|-------------|
| `ValueError` | 90+ | Config validation, invalid parameters |
| `KeyError` | Frequent | Missing indicator keys (`TFContext.get_indicator_strict()`) |
| `TypeError` | Moderate | Type mismatches |
| `RuntimeError` | 3-5 | State violations |
| Custom types | <1% | Rarely used |

### Catching Patterns

| Pattern | Frequency | Assessment |
|---------|-----------|------------|
| `except Exception as e:` | ~95% | Too broad |
| `except (ValueError, TypeError):` | ~5% | Appropriate |
| Specific custom exceptions | <1% | Underutilized |
| Bare `except Exception:` (no binding) | ~30% | Loses context |

---

## Anti-Patterns Identified

### 1. Bare `except Exception` - Too Broad

**Files affected**: `src/core/exchange_positions.py`, `src/core/exchange_orders_*.py`, `src/tools/*.py`

```python
# Current (problematic)
except Exception as e:
    self.logger.error(f"Failed to close position: {e}")
    return False
```

**Problem**: Catches `SystemExit`, `KeyboardInterrupt`, masks programming errors.

**Fix**:
```python
except (BybitAPIError, ValueError, KeyError) as e:
    self.logger.error(f"Failed to close position: {e}")
    return False
```

### 2. Silent Exception Suppression

**Files affected**: `src/core/safety.py:51`, `src/utils/logger.py:470`

```python
# Current (problematic)
except Exception:
    pass
```

**Problem**: Bugs hide silently, no debugging trail.

**Fix**:
```python
except Exception as e:
    logger.debug(f"Suppressed callback error: {e}")
```

### 3. String Conversion Loses Type Information

```python
# Current (problematic)
error=str(e)  # Cannot distinguish error types programmatically
```

**Fix**:
```python
error_type=type(e).__name__
error_message=str(e)
```

### 4. No Exception Chaining

```python
# Current (problematic)
except SomeError as e:
    raise ValueError(f"Failed: {e}")  # Loses original traceback
```

**Fix**:
```python
except SomeError as e:
    raise ValueError(f"Failed: {e}") from e  # Preserves chain
```

---

## Recommended Exception Hierarchy

### Proposed Structure

```
src/exceptions.py (new file)

TradeError (base)
├── LiveTradingError
│   ├── OrderExecutionError
│   ├── PositionError
│   └── ExchangeConnectionError
├── BacktestError
│   ├── GateError
│   │   ├── PreflightGateError
│   │   └── ArtifactGateError
│   ├── SimulationError
│   │   ├── InsufficientMarginError
│   │   └── InvalidSignalError
│   └── StrategyError
├── DataError
│   ├── DataValidationError
│   ├── DataGapError
│   └── DataSyncError
└── ConfigError
    ├── IdeaCardValidationError
    └── EnvironmentMismatchError
```

### Implementation

```python
# src/exceptions.py

class TradeError(Exception):
    """Base exception for all TRADE errors."""
    pass


# === Live Trading Domain ===

class LiveTradingError(TradeError):
    """Errors during live trading operations."""
    pass

class OrderExecutionError(LiveTradingError):
    """Order failed to execute."""
    def __init__(self, symbol: str, reason: str, order_id: str | None = None):
        self.symbol = symbol
        self.reason = reason
        self.order_id = order_id
        super().__init__(f"{symbol}: {reason}")

class PositionError(LiveTradingError):
    """Position operation failed."""
    pass

class ExchangeConnectionError(LiveTradingError):
    """Cannot connect to exchange."""
    pass


# === Backtest Domain ===

class BacktestError(TradeError):
    """Errors during backtest operations."""
    pass

class GateError(BacktestError):
    """Gate validation failed."""
    def __init__(self, gate_name: str, reason: str, suggestions: list[str] | None = None):
        self.gate_name = gate_name
        self.reason = reason
        self.suggestions = suggestions or []
        super().__init__(f"[{gate_name}] {reason}")

class PreflightGateError(GateError):
    """Preflight gate failed."""
    def __init__(self, reason: str, suggestions: list[str] | None = None):
        super().__init__("preflight", reason, suggestions)

class ArtifactGateError(GateError):
    """Artifact validation gate failed."""
    def __init__(self, reason: str, suggestions: list[str] | None = None):
        super().__init__("artifact", reason, suggestions)

class SimulationError(BacktestError):
    """Error during simulation execution."""
    pass

class InsufficientMarginError(SimulationError):
    """Not enough margin for operation."""
    def __init__(self, required: float, available: float, symbol: str):
        self.required = required
        self.available = available
        self.symbol = symbol
        super().__init__(f"{symbol}: need {required:.2f} USDT, have {available:.2f}")

class InvalidSignalError(SimulationError):
    """Strategy produced invalid signal."""
    pass

class StrategyError(BacktestError):
    """Strategy execution error."""
    pass


# === Data Domain ===

class DataError(TradeError):
    """Errors related to data operations."""
    pass

class DataValidationError(DataError):
    """Data failed validation."""
    pass

class DataGapError(DataError):
    """Data has gaps that cannot be filled."""
    def __init__(self, symbol: str, timeframe: str, gap_start: str, gap_end: str):
        self.symbol = symbol
        self.timeframe = timeframe
        self.gap_start = gap_start
        self.gap_end = gap_end
        super().__init__(f"{symbol} {timeframe}: gap from {gap_start} to {gap_end}")

class DataSyncError(DataError):
    """Data sync operation failed."""
    pass


# === Config Domain ===

class ConfigError(TradeError):
    """Configuration-related errors."""
    pass

class IdeaCardValidationError(ConfigError):
    """IdeaCard YAML validation failed."""
    def __init__(self, card_path: str, errors: list[str]):
        self.card_path = card_path
        self.errors = errors
        msg = f"{card_path}: {len(errors)} validation error(s)"
        super().__init__(msg)

class EnvironmentMismatchError(ConfigError):
    """Environment configuration mismatch."""
    pass
```

---

## Migration Strategy

### Phase 1: Add Hierarchy (Non-Breaking)

1. Create `src/exceptions.py` with new hierarchy
2. Keep existing 3 custom exceptions as aliases
3. Add new exceptions alongside existing code

### Phase 2: Migrate Raises

1. Replace `raise ValueError(...)` with domain-specific exceptions where appropriate
2. Update `GateFailure` to `GateError` subclasses
3. Add context to exception instantiation

### Phase 3: Migrate Catches

1. Replace `except Exception` with specific catches in critical paths
2. Keep `except Exception` at top-level entry points (CLI, tool handlers)
3. Add exception chaining with `from e`

### Phase 4: Document Contracts

Add `Raises:` sections to docstrings:

```python
def run_backtest(idea_card: IdeaCard) -> RunnerResult:
    """Run backtest simulation.

    Raises:
        PreflightGateError: Data coverage or warmup validation failed
        ArtifactGateError: Artifact generation or validation failed
        StrategyError: Strategy execution raised an error
        ConfigError: IdeaCard configuration is invalid
    """
```

---

## Utility Functions

```python
# src/exceptions.py (continued)

def is_retryable(e: Exception) -> bool:
    """Check if error is transient and operation can be retried."""
    if isinstance(e, ExchangeConnectionError):
        return True
    if isinstance(e, BybitAPIError) and e.code in (10002, 10006):  # Rate limit, timeout
        return True
    return False

def is_user_fixable(e: Exception) -> bool:
    """Check if user action can resolve the error."""
    return isinstance(e, (ConfigError, DataGapError, EnvironmentMismatchError))

def get_error_context(e: Exception) -> dict:
    """Extract structured context from exception for logging/reporting."""
    context = {
        "type": type(e).__name__,
        "message": str(e),
        "is_trade_error": isinstance(e, TradeError),
    }

    if isinstance(e, GateError):
        context["gate_name"] = e.gate_name
        context["suggestions"] = e.suggestions

    if isinstance(e, DataGapError):
        context["symbol"] = e.symbol
        context["timeframe"] = e.timeframe
        context["gap_range"] = f"{e.gap_start} to {e.gap_end}"

    return context
```

---

## Best Practices Going Forward

### Do

- Catch specific exceptions, not bare `Exception`
- Chain exceptions with `from e` to preserve traceback
- Add context attributes to custom exceptions
- Document exception contracts in docstrings
- Use `is_retryable()` for retry logic

### Don't

- Suppress exceptions silently (`except Exception: pass`)
- Convert exceptions to strings and lose type info
- Catch `Exception` when you mean specific error types
- Create empty exception classes without semantic meaning

---

## Files Requiring Updates

| Priority | File | Issue |
|----------|------|-------|
| High | `src/core/exchange_positions.py` | 40+ bare `except Exception` |
| High | `src/tools/*.py` | 30+ bare `except Exception` |
| Medium | `src/backtest/runner.py` | Replace `GateFailure` with hierarchy |
| Medium | `src/tools/shared.py` | Replace `TradingEnvMismatchError` |
| Low | `src/core/safety.py` | Silent suppression in callbacks |
| Low | `src/utils/logger.py` | Silent suppression in cleanup |

---

## Summary

The current exception handling is functional but flat. Implementing a domain-based hierarchy will:

1. Enable catching errors by category (all backtest errors, all data errors)
2. Preserve context through exception attributes
3. Improve debugging with exception chaining
4. Support programmatic error handling for agents/orchestrators
5. Document error contracts through types

**Recommended first step**: Create `src/exceptions.py` with the base hierarchy (Phase 1), then incrementally migrate high-impact files.
