# Windows Unicode/ASCII Encoding Investigation

**Date**: 2026-01-05
**Status**: INVESTIGATION COMPLETE - FIX PROPOSED
**Related Bug**: P2-08 in `docs/audits/OPEN_BUGS.md`

---

## Problem Summary

When running CLI commands through certain Windows environments (e.g., Command Prompt, PowerShell with legacy codepage), emoji characters cause:

```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2728' in position 30
```

The module `src/data/historical_data_store.py` has an `ActivityEmoji` class that attempts to detect ASCII mode at module load time, but the detection logic fails in some Windows environments.

---

## 1. Emoji Usage Locations

### 1.1 ActivityEmoji Class (Primary Source)

**Location**: `src/data/historical_data_store.py:65-96`

```python
class ActivityEmoji:
    """Fun emojis for different activities. Falls back to ASCII on Windows."""
    # Data operations
    SYNC = "[SYNC]" if _USE_ASCII else "📡"
    DOWNLOAD = "[DL]" if _USE_ASCII else "⬇️"
    UPLOAD = "[UL]" if _USE_ASCII else "⬆️"
    CANDLE = "[C]" if _USE_ASCII else "🕯️"
    CHART = "[CHART]" if _USE_ASCII else "📊"
    DATABASE = "[DB]" if _USE_ASCII else "🗄️"

    # ... (18 total emoji definitions)

    # Progress spinners (ASCII-safe versions)
    SPINNERS = ["|", "/", "-", "\\"] if _USE_ASCII else ["◐", "◓", "◑", "◒"]
    BARS = ["#"] * 8 if _USE_ASCII else ["▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]
    DOTS = ["."] * 10 if _USE_ASCII else ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
```

### 1.2 Files Using ActivityEmoji

| File | Usage Count | Risk Level |
|------|-------------|------------|
| `src/data/historical_data_store.py` | 38 | HIGH - many stdout.write calls |
| `src/data/historical_sync.py` | 18 | HIGH - sync operations |
| `src/data/historical_maintenance.py` | 20 | HIGH - maintenance operations |

### 1.3 CLI Icons (Separate System)

**Location**: `src/cli/styles.py:56-92`

```python
class CLIIcons:
    SETTINGS = "⚙️ "
    QUIT = "🚪 "
    WARNING = "⚠️ "
    ERROR = "❌ "
    SUCCESS = "✅ "
    # ... (27 total icons)
```

These are rendered through Rich library which has its own handling, but they also pose risk on Windows.

### 1.4 diagnostics_tools.py (Already Fixed Pattern)

**Location**: `src/tools/diagnostics_tools.py:13-21`

```python
# Windows-safe symbols (avoid Unicode encoding errors on legacy consoles)
_USE_ASCII = (
    sys.platform == "win32"
    and os.environ.get("PYTHONIOENCODING", "").lower() != "utf-8"
    and not os.environ.get("WT_SESSION")
)
_OK = "[OK]" if _USE_ASCII else "✓"
_FAIL = "[X]" if _USE_ASCII else "✗"
```

This module correctly checks for `PYTHONIOENCODING` environment variable.

---

## 2. Detection Logic Analysis

### 2.1 Current Detection Code

**Location**: `src/data/historical_data_store.py:46-62`

```python
def _detect_ascii_mode() -> bool:
    """Check if we should use ASCII fallbacks."""
    if sys.platform != "win32":
        return False
    # Windows Terminal supports UTF-8
    if os.environ.get("WT_SESSION"):
        return False
    # Check if stdout can encode unicode
    try:
        if sys.stdout.encoding:
            "✨".encode(sys.stdout.encoding)
            return False
    except (UnicodeEncodeError, LookupError, AttributeError):
        pass
    return True  # Default to ASCII on Windows if uncertain

_USE_ASCII = _detect_ascii_mode()
```

### 2.2 Why Detection Fails

The detection logic has several failure modes:

1. **Encoding Name Mismatch**: `sys.stdout.encoding` returns encoding names like `"cp1252"` or `"UTF-8"`. The `.encode()` call tests if the string CAN be encoded, but this doesn't guarantee the console can DISPLAY it.

2. **Stdout Reconfiguration After Module Load**: If stdout is reconfigured after module import, `_USE_ASCII` is already computed with stale values.

3. **Subprocess/Piped Execution**: When the script is run via subprocess or piped, `sys.stdout.encoding` may return `None` or a different encoding than the actual terminal.

4. **Encoding vs Display**: A string encoding to bytes successfully doesn't mean the console will display it. Windows Command Prompt with cp1252 cannot display emoji even if Python can encode them.

### 2.3 What `sys.stdout.encoding` Returns

| Environment | `sys.stdout.encoding` | Emoji Works? |
|-------------|----------------------|--------------|
| Windows Terminal | `"utf-8"` | Yes |
| PowerShell 7+ | `"utf-8"` | Yes |
| Command Prompt | `"cp1252"` or `"cp437"` | No |
| PowerShell 5.x | `"cp1252"` | No |
| Git Bash | `"utf-8"` | Sometimes |
| VS Code Terminal | `"utf-8"` | Yes |
| Redirected Output | `None` or varies | No |

### 2.4 Key Finding

The current test:
```python
"✨".encode(sys.stdout.encoding)
```

This SUCCEEDS even on cp1252 because:
1. Python can encode emoji as bytes using error handlers
2. The test should check if the encoding SUPPORTS the codepoint, not just encode

The correct test would be:
```python
"✨".encode(sys.stdout.encoding, errors="strict")
```

But even this can succeed if the encoding is incorrectly reported as UTF-8.

---

## 3. Error Trace Analysis

### 3.1 Error Origin

The error originates from `sys.stdout.write()` calls that contain emoji:

**Example paths**:

1. `historical_data_store.py:733`:
```python
sys.stdout.write(f"\r    {ActivityEmoji.DOWNLOAD} {dots} {symbol} funding: Fetching...")
```

2. `historical_data_store.py:104-130` (ActivitySpinner._spin):
```python
sys.stdout.write(f"\r  {emoji} {frame} {self.message}...   ")
```

### 3.2 Error Propagation

```
sync() → _sync_symbol_timeframe() → sys.stdout.write() with emoji
       ↓
UnicodeEncodeError: 'charmap' codec can't encode character '\u2728'
       ↓
Exception bubbles up
       ↓
"Failed to sync SOLUSDT_4h: 'charmap' codec can't encode character..."
```

### 3.3 Try/Except Handling (Partial)

The `ActivitySpinner` class has try/except handling:

```python
def _spin(self):
    """Spinner animation loop."""
    use_ascii = False
    while self.running:
        try:
            sys.stdout.write(f"\r  {emoji} {frame} {self.message}...   ")
        except UnicodeEncodeError:
            # Switch to ASCII mode permanently for this spinner
            use_ascii = True
```

But this is:
1. Only in the spinner class
2. Not in the many direct `sys.stdout.write()` calls elsewhere

---

## 4. Proposed Fixes

### 4.1 Fix Option A: Force ASCII on Windows (Recommended - Simplest)

**Impact**: Low effort, reliable, no runtime overhead

```python
def _detect_ascii_mode() -> bool:
    """Check if we should use ASCII fallbacks."""
    if sys.platform != "win32":
        return False

    # Windows Terminal is known UTF-8 safe
    if os.environ.get("WT_SESSION"):
        return False

    # VS Code integrated terminal
    if os.environ.get("TERM_PROGRAM") == "vscode":
        return False

    # PYTHONIOENCODING explicitly set to UTF-8
    if os.environ.get("PYTHONIOENCODING", "").lower() == "utf-8":
        return False

    # Default: ASCII on Windows (conservative approach)
    return True
```

**Pros**: Simple, reliable, no runtime exceptions
**Cons**: Users in modern terminals lose emojis (acceptable)

### 4.2 Fix Option B: Reconfigure stdout at Startup

**Impact**: Medium effort, changes global behavior

Add to `trade_cli.py` or an early-imported module:

```python
import sys
import io

if sys.platform == "win32":
    # Reconfigure stdout to use UTF-8 with replacement for unencodable chars
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
```

**Pros**: Enables UTF-8 globally, emojis work in capable terminals
**Cons**:
- May break piped output in some scenarios
- `reconfigure()` requires Python 3.7+
- Replacement character `�` appears for failures

### 4.3 Fix Option C: Safe Print Wrapper (Most Robust)

**Impact**: Medium effort, safest

Create `src/utils/safe_print.py`:

```python
import sys

def safe_write(text: str, end: str = "", flush: bool = True) -> None:
    """Write to stdout with automatic fallback for encoding errors."""
    try:
        sys.stdout.write(text)
        if end:
            sys.stdout.write(end)
        if flush:
            sys.stdout.flush()
    except UnicodeEncodeError:
        # Strip non-ASCII characters and retry
        ascii_text = text.encode('ascii', errors='replace').decode('ascii')
        sys.stdout.write(ascii_text)
        if end:
            sys.stdout.write(end)
        if flush:
            sys.stdout.flush()
```

Then replace all `sys.stdout.write()` calls with `safe_write()`.

**Pros**: Graceful degradation at runtime, no global state changes
**Cons**: Requires updating many call sites

### 4.4 Fix Option D: Hybrid Approach (Recommended)

Combine Options A + partial C:

1. Improve detection logic (Option A) to be more conservative
2. Add try/except wrapper to the few remaining stdout.write calls that use emojis directly
3. Keep ActivitySpinner's existing fallback behavior

---

## 5. Implementation Recommendation

### Phase 1: Immediate Fix (P2-08 Resolution)

Update `_detect_ascii_mode()` in `src/data/historical_data_store.py`:

```python
def _detect_ascii_mode() -> bool:
    """Check if we should use ASCII fallbacks.

    Conservative approach: default to ASCII on Windows unless we're
    confident the terminal supports UTF-8.
    """
    if sys.platform != "win32":
        return False

    # Windows Terminal explicitly sets WT_SESSION
    if os.environ.get("WT_SESSION"):
        return False

    # VS Code integrated terminal
    if os.environ.get("TERM_PROGRAM") == "vscode":
        return False

    # ConEmu/Cmder set ConEmuANSI
    if os.environ.get("ConEmuANSI") == "ON":
        return False

    # User explicitly requested UTF-8
    if os.environ.get("PYTHONIOENCODING", "").lower() == "utf-8":
        return False

    # Check stdout encoding as last resort
    try:
        if sys.stdout.encoding and sys.stdout.encoding.lower() == "utf-8":
            return False
    except AttributeError:
        pass

    # Default: ASCII on Windows (conservative)
    return True
```

### Phase 2: Additional Hardening

1. Wrap remaining direct `sys.stdout.write()` calls in try/except blocks
2. Update `src/cli/styles.py` CLIIcons to use same pattern
3. Consider using Rich console exclusively (has built-in encoding handling)

---

## 6. Files Requiring Updates

### Critical (Fix P2-08)

| File | Change |
|------|--------|
| `src/data/historical_data_store.py:46-62` | Update `_detect_ascii_mode()` |

### Recommended (Hardening)

| File | Change |
|------|--------|
| `src/data/historical_data_store.py:731-789` | Add try/except to stdout.write in sync loops |
| `src/data/historical_data_store.py:985-1041` | Add try/except to stdout.write in OI sync loops |
| `src/cli/styles.py:56-92` | Add ASCII fallbacks to CLIIcons |
| `src/cli/art_stylesheet.py:77-85` | Guard pattern_border characters |

---

## 7. Testing the Fix

### Test Commands

```bash
# Test in Command Prompt (legacy)
cmd.exe /c "python trade_cli.py --smoke data"

# Test in PowerShell 5.x
powershell.exe -Command "python trade_cli.py --smoke data"

# Force ASCII mode via environment
set PYTHONIOENCODING=ascii && python trade_cli.py --smoke data
```

### Verification Checklist

- [ ] Data sync completes without UnicodeEncodeError
- [ ] Progress spinners display (ASCII or emoji depending on terminal)
- [ ] No mojibake (garbled characters) in output
- [ ] Windows Terminal still shows emojis (if user prefers)
- [ ] Works in piped/redirected scenarios

---

## 8. Appendix: Unicode Character Codes

| Emoji | Unicode | Name | Usage |
|-------|---------|------|-------|
| ✨ | U+2728 | SPARKLES | SPARKLE constant |
| ✅ | U+2705 | CHECK MARK BUTTON | SUCCESS constant |
| ❌ | U+274C | CROSS MARK | ERROR constant |
| ⚠️ | U+26A0 | WARNING SIGN | WARNING constant |
| 📡 | U+1F4E1 | SATELLITE ANTENNA | SYNC constant |
| 📊 | U+1F4CA | BAR CHART | CHART constant |
| 💰 | U+1F4B0 | MONEY BAG | MONEY_BAG constant |
| 🔧 | U+1F527 | WRENCH | REPAIR constant |

These are all outside the Windows-1252 (cp1252) codepage range.
