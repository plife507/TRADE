# Audit Engine Review

> **Comprehensive review** of the TRADE audit engine system, covering math parity validation, toolkit contract auditing, and snapshot artifact management.

---

## Executive Summary

The TRADE audit engine provides **verification and validation** of indicator computations and system correctness:

1. **Math Parity Audit** - Validates that backtest indicator computations match pandas_ta exactly
2. **Toolkit Contract Audit** - Ensures registry-vendor contract compliance for all indicators
3. **Snapshot Artifacts** - Lossless snapshot system for audit reconstruction

**Purpose:** Ensure no implementation drift, bugs, or contract violations in the indicator computation pipeline.

---

## 1. Audit Engine Architecture

### 1.1 Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Audit Engine System                       │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Math Parity     │  │ Toolkit Contract│  │ Snapshot        │
│ Audit           │  │ Audit           │  │ Artifacts       │
│                 │  │                 │  │                 │
│ Validates:      │  │ Validates:      │  │ Provides:       │
│ - Indicator     │  │ - Registry      │  │ - Lossless      │
│   computation   │  │   contract      │  │   snapshots     │
│   matches       │  │   compliance    │  │ - Manifest      │
│   pandas_ta     │  │ - Output        │  │   metadata      │
│ - No drift      │  │   correctness   │  │ - Reconstruction│
│ - NaN patterns  │  │ - No collisions │  │   data          │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

### 1.2 Audit Flow

```
Backtest Execution
    ↓
Snapshot Artifacts Emitted (Parquet + Manifest)
    ↓
Math Parity Audit (recompute with pandas_ta)
    ↓
Compare: Snapshot vs Fresh Computation
    ↓
Report: Pass/Fail with detailed statistics
```

---

## 2. Math Parity Audit

### 2.1 Purpose

**Validates that indicator computations in the backtest engine match pandas_ta exactly**, ensuring:
- No implementation drift
- No bugs in indicator computation
- Correct NaN handling
- Proper multi-output indicator expansion

### 2.2 How It Works

**Location:** `src/backtest/audit_math_parity.py`

**Process:**
1. Load snapshot artifacts from backtest run directory
2. For each indicator in the manifest:
   - Extract feature specs (indicator_type, params, input_source)
   - Recompute using fresh pandas_ta computation
   - Compare snapshot values vs recomputed values
3. Report pass/fail with detailed statistics

**Example:**
```python
from src.backtest.audit_math_parity import audit_math_parity_from_snapshots
from pathlib import Path

# Run audit on a backtest run directory
run_dir = Path("backtests/BTCUSDT_15m_mtf_tradeproof/BTCUSDT/run-001")
result = audit_math_parity_from_snapshots(run_dir)

if result.success:
    print("✅ All indicators match pandas_ta exactly")
    print(f"Total columns: {result.data['summary']['total_columns']}")
    print(f"Passed: {result.data['summary']['passed_columns']}")
else:
    print("❌ Math parity audit failed")
    print(f"Failed columns: {result.data['summary']['failed_columns']}")
```

### 2.3 Comparison Logic

**Tolerance:** `1e-8` (very strict - essentially exact match)

**Checks:**
1. **NaN Mask Identity**: NaN patterns must be identical
2. **Value Comparison**: All non-NaN values must match within tolerance
3. **Column Alignment**: Series are aligned by index before comparison

**Per-Column Results:**
```python
@dataclass
class ColumnAuditResult:
    column: str                    # Column name
    passed: bool                   # Pass/fail
    max_abs_diff: float           # Maximum absolute difference
    mean_abs_diff: float          # Mean absolute difference
    nan_mask_identical: bool      # NaN patterns match
    snapshot_values: int          # Number of valid values in snapshot
    pandas_ta_values: int        # Number of valid values in recomputed
    error_message: Optional[str] # Error if computation failed
```

### 2.4 Manifest-Driven Comparison

**Key Feature:** Only compares columns listed in `outputs_written` from the manifest.

**Why:**
- No hardcoded indicator output counts
- Uses manifest as source of truth
- Handles multi-output indicators correctly
- Supports legacy manifests (fallback to `feature_columns`)

**Manifest Structure:**
```json
{
  "frames": {
    "exec": {
      "outputs_written": {
        "ema_fast": ["ema_fast"],
        "macd": ["macd_macd", "macd_signal", "macd_histogram"]
      },
      "feature_specs_resolved": [
        {
          "indicator_type": "ema",
          "output_key": "ema_fast",
          "params": {"length": 9},
          "input_source": "close"
        }
      ]
    }
  }
}
```

### 2.5 Multi-Timeframe Support

**Role-Based Processing:**
- Processes each frame by **role** (exec/htf/mtf), not timeframe
- Each role gets its own comparison
- Supports MTF strategies with separate indicator sets per TF

**Example:**
```python
# Exec TF: ema_fast, ema_slow, atr
# HTF: ema_trend
# MTF: rsi

# Audit compares:
# - exec frame: ema_fast, ema_slow, atr vs pandas_ta
# - htf frame: ema_trend vs pandas_ta
# - mtf frame: rsi vs pandas_ta
```

### 2.6 CLI Usage

```bash
# Run math parity audit on a backtest run
python trade_cli.py backtest verify-suite --run-dir backtests/BTCUSDT_15m_mtf_tradeproof/BTCUSDT/run-001

# Or via tool
from src.tools.backtest_cli_wrapper import backtest_audit_math_from_snapshots_tool

result = backtest_audit_math_from_snapshots_tool(
    run_dir=Path("backtests/.../run-001")
)
```

---

## 3. Toolkit Contract Audit

### 3.1 Purpose

**Gate 1 of the verification suite** - ensures the registry is the contract:
- Every indicator produces exactly registry-declared canonical outputs
- No canonical collisions
- No missing declared outputs
- Extras are dropped + recorded

### 3.2 How It Works

**Location:** `src/backtest/toolkit_contract_audit.py`

**Process:**
1. Generate deterministic synthetic OHLCV data
2. For each indicator in the registry:
   - Get registry-declared outputs
   - Compute indicator using vendor
   - Compare produced outputs vs declared outputs
3. Report pass/fail with detailed results

**Example:**
```python
from src.backtest.toolkit_contract_audit import run_toolkit_contract_audit

# Run audit over all registry indicators
result = run_toolkit_contract_audit(
    sample_bars=2000,
    seed=1337,
    fail_on_extras=False,
    strict=True
)

if result.success:
    print(f"✅ All {result.total_indicators} indicators passed")
    print(f"Passed: {result.passed_indicators}")
    print(f"With extras: {result.indicators_with_extras}")
else:
    print(f"❌ {result.failed_indicators} indicators failed")
```

### 3.3 Synthetic Data Generation

**Purpose:** Deterministic, reproducible test data

**Features:**
- Valid OHLC constraints: `high >= max(open, close)`, `low <= min(open, close)`
- Non-zero volume
- Regime changes: trend → range → spike → mean-revert
- Configurable seed for reproducibility

**Regimes:**
1. **Trend Up**: Gradual price increase with noise
2. **Range-Bound**: Oscillating around center
3. **Spike**: High volatility with large moves
4. **Mean-Revert**: Returns to baseline

**Example:**
```python
from src.backtest.toolkit_contract_audit import generate_synthetic_ohlcv

# Generate 2000 bars with seed 1337
df = generate_synthetic_ohlcv(n_bars=2000, seed=1337)

# Columns: timestamp, open, high, low, close, volume
print(df.head())
```

### 3.4 Contract Validation

**Per-Indicator Results:**
```python
@dataclass
class IndicatorAuditResult:
    indicator_type: str              # Indicator name
    passed: bool                     # Pass/fail
    declared_outputs: List[str]      # Registry-declared outputs
    produced_outputs: List[str]      # Vendor-produced outputs
    extras_dropped: List[str]        # Extras that were dropped
    missing_outputs: List[str]       # Missing declared outputs
    collisions: Dict[str, List[str]] # Canonical collisions
    error_message: Optional[str]     # Error if computation failed
```

**Validation Rules:**
- ✅ **Pass**: No missing outputs, no collisions
- ⚠️ **Extras**: Allowed (dropped by vendor, recorded)
- ❌ **Fail**: Missing declared outputs or collisions

### 3.5 Single-Output vs Multi-Output

**Single-Output Indicators:**
- No output validation needed (registry doesn't declare outputs)
- Pass if computation succeeds

**Multi-Output Indicators:**
- Registry declares expected outputs (e.g., `macd` → `macd`, `signal`, `histogram`)
- Vendor must produce all declared outputs
- Extras are dropped (recorded but not errors)

**Example:**
```python
# MACD indicator
declared_outputs = ["macd", "signal", "histogram"]
produced_outputs = ["macd", "signal", "histogram", "extra_col"]  # extra_col dropped

# Result: passed=True, extras_dropped=["extra_col"]
```

### 3.6 CLI Usage

```bash
# Run toolkit contract audit
python trade_cli.py backtest audit-toolkit

# With options
python trade_cli.py backtest audit-toolkit \
    --sample-bars 2000 \
    --seed 1337 \
    --fail-on-extras \
    --strict

# JSON output for CI
python trade_cli.py backtest audit-toolkit --json
```

**Output:**
```
TOOLKIT CONTRACT AUDIT (Gate 1)
Sample: 2000 bars | Seed: 1337
Strict: True | Fail on extras: False

✅ PASS All indicators passed contract validation
Total indicators: 150
Passed: 150
With extras dropped: 5
```

---

## 4. Snapshot Artifacts

### 4.1 Purpose

**Lossless snapshot system** for audit reconstruction:
- Emits OHLCV DataFrames with computed indicators
- Manifest with metadata for audit reconstruction
- Parquet format to avoid float rounding issues

### 4.2 Artifact Structure

**Location:** `backtests/{system}/{symbol}/run-{id}/snapshots/`

**Files:**
```
snapshots/
├── exec_frame.parquet      # Exec TF DataFrame (OHLCV + indicators)
├── htf_frame.parquet       # HTF DataFrame (if MTF strategy)
├── mtf_frame.parquet       # MTF DataFrame (if MTF strategy)
└── snapshot_manifest.json  # Metadata for reconstruction
```

### 4.3 Manifest Format

**Structure:**
```json
{
  "idea_card_id": "BTCUSDT_15m_mtf_tradeproof",
  "symbol": "BTCUSDT",
  "window_start": "2024-01-01T00:00:00",
  "window_end": "2024-12-31T23:59:59",
  "exec_tf": "15m",
  "htf": "4h",
  "mtf": "1h",
  "frame_format": "parquet",
  "float_precision": "lossless",
  "created_at": "2024-12-14T10:00:00",
  "frames": {
    "exec": {
      "role": "exec",
      "tf": "15m",
      "row_count": 35040,
      "column_count": 8,
      "timestamp_range": ["2024-01-01T00:00:00", "2024-12-31T23:45:00"],
      "columns_present": ["timestamp", "open", "high", "low", "close", "volume", "ema_fast", "ema_slow"],
      "feature_specs_resolved": [
        {
          "indicator_type": "ema",
          "output_key": "ema_fast",
          "params": {"length": 9},
          "input_source": "close"
        }
      ],
      "outputs_expected_by_registry": {
        "ema_fast": ["ema_fast"],
        "ema_slow": ["ema_slow"]
      },
      "outputs_written": {
        "ema_fast": ["ema_fast"],
        "ema_slow": ["ema_slow"]
      },
      "extras_dropped": {
        "ema_fast": [],
        "ema_slow": []
      }
    }
  }
}
```

### 4.4 Role-Based Naming

**Key Feature:** Frames are keyed by **role** (exec/htf/mtf), not timeframe.

**Why:**
- Supports MTF strategies with same TF for different roles
- Clear semantic meaning (exec vs htf vs mtf)
- Easier audit processing

**Example:**
```python
# MTF strategy with:
# - exec: 15m
# - htf: 4h
# - mtf: 1h

# Files:
# - exec_frame.parquet (15m data)
# - htf_frame.parquet (4h data)
# - mtf_frame.parquet (1h data)
```

### 4.5 Contract Tracking

**Tracks:**
- `outputs_expected_by_registry`: What registry declares
- `outputs_written`: What was actually written to frame
- `extras_dropped`: Extras that vendor dropped (recorded)

**Purpose:**
- Enables audit reconstruction
- Validates contract compliance
- Records any extras for analysis

### 4.6 Loading Artifacts

**Usage:**
```python
from src.backtest.snapshot_artifacts import load_snapshot_artifacts
from pathlib import Path

run_dir = Path("backtests/.../run-001")
artifacts = load_snapshot_artifacts(run_dir)

if artifacts:
    manifest = artifacts["manifest"]
    exec_df = artifacts["frames"]["exec"]
    htf_df = artifacts["frames"].get("htf")
    mtf_df = artifacts["frames"].get("mtf")
    
    # Use for audit reconstruction
    print(f"Exec TF: {manifest['exec_tf']}")
    print(f"Columns: {exec_df.columns.tolist()}")
```

### 4.7 Emission During Backtest

**Automatic:** Snapshot artifacts are emitted automatically during backtest execution.

**Trigger:** When backtest completes successfully.

**Location:** `BacktestEngine.run()` → `emit_snapshot_artifacts()`

**Data Included:**
- OHLCV columns (timestamp, open, high, low, close, volume)
- All computed indicator columns
- Feature specs metadata
- Contract tracking information

---

## 5. Verification Suite

### 5.1 Complete Suite

**Gate 1: Toolkit Contract Audit**
- Validates registry-vendor contract
- Uses synthetic data
- No database required

**Gate 2: Math Parity Audit**
- Validates indicator computation correctness
- Uses snapshot artifacts from backtest
- Requires completed backtest run

**Usage:**
```bash
# Run complete verification suite
python trade_cli.py backtest verify-suite --run-dir backtests/.../run-001

# Skip Gate 1 (toolkit audit)
python trade_cli.py backtest verify-suite --run-dir ... --skip-toolkit-audit

# JSON output
python trade_cli.py backtest verify-suite --run-dir ... --json
```

### 5.2 Suite Results

**Output Format:**
```json
{
  "status": "pass",
  "gates": {
    "gate_1_toolkit_contract": {
      "status": "pass",
      "total_indicators": 150,
      "passed_indicators": 150
    },
    "gate_2_math_parity": {
      "status": "pass",
      "total_columns": 5,
      "passed_columns": 5,
      "max_abs_diff": 0.0
    }
  }
}
```

---

## 6. Key Design Principles

### 6.1 Manifest-Driven

**Principle:** Manifest is the source of truth for audit reconstruction.

**Benefits:**
- No hardcoded indicator counts
- Handles multi-output indicators correctly
- Supports legacy manifests (backward compatible)
- Clear contract tracking

### 6.2 Lossless Storage

**Principle:** Parquet format preserves float precision.

**Why:**
- Avoids float rounding issues
- Enables exact comparison
- Reproducible audits

### 6.3 Role-Based Organization

**Principle:** Frames keyed by role (exec/htf/mtf), not timeframe.

**Benefits:**
- Clear semantic meaning
- Supports MTF strategies
- Easier audit processing

### 6.4 Deterministic Testing

**Principle:** Synthetic data uses fixed seed for reproducibility.

**Benefits:**
- Consistent test results
- Debuggable failures
- CI/CD friendly

### 6.5 Contract as Registry

**Principle:** Registry defines the contract, vendor must comply.

**Benefits:**
- Single source of truth
- Clear validation rules
- Extensible (add indicators = update registry)

---

## 7. Usage Examples

### 7.1 Run Toolkit Audit

```python
from src.backtest.toolkit_contract_audit import run_toolkit_contract_audit

result = run_toolkit_contract_audit(
    sample_bars=2000,
    seed=1337,
    strict=True
)

if result.success:
    print(f"✅ All {result.total_indicators} indicators passed")
else:
    print(f"❌ {result.failed_indicators} indicators failed")
    for r in result.indicator_results:
        if not r.passed:
            print(f"  - {r.indicator_type}: {r.error_message}")
```

### 7.2 Run Math Parity Audit

```python
from src.backtest.audit_math_parity import audit_math_parity_from_snapshots
from pathlib import Path

run_dir = Path("backtests/BTCUSDT_15m_mtf_tradeproof/BTCUSDT/run-001")
result = audit_math_parity_from_snapshots(run_dir)

if result.success:
    summary = result.data["summary"]
    print(f"✅ Math parity: {summary['passed_columns']}/{summary['total_columns']} columns passed")
    print(f"Max diff: {summary['max_abs_diff']}")
else:
    print(f"❌ Math parity failed: {result.error_message}")
```

### 7.3 Load and Inspect Artifacts

```python
from src.backtest.snapshot_artifacts import load_snapshot_artifacts
from pathlib import Path

run_dir = Path("backtests/.../run-001")
artifacts = load_snapshot_artifacts(run_dir)

if artifacts:
    manifest = artifacts["manifest"]
    exec_df = artifacts["frames"]["exec"]
    
    print(f"IdeaCard: {manifest['idea_card_id']}")
    print(f"Symbol: {manifest['symbol']}")
    print(f"Window: {manifest['window_start']} to {manifest['window_end']}")
    print(f"Exec TF: {manifest['exec_tf']}")
    print(f"Columns: {exec_df.columns.tolist()}")
    
    # Inspect indicator values
    print(f"\nEMA Fast (first 10):")
    print(exec_df["ema_fast"].head(10))
```

### 7.4 CLI Commands

```bash
# Toolkit contract audit
python trade_cli.py backtest audit-toolkit

# Math parity audit (requires backtest run)
python trade_cli.py backtest verify-suite --run-dir backtests/.../run-001

# Complete verification suite
python trade_cli.py backtest verify-suite --run-dir backtests/.../run-001 --json
```

---

## 8. Summary

**Audit Engine provides:**

1. **Math Parity Audit** - Validates indicator computations match pandas_ta exactly
2. **Toolkit Contract Audit** - Ensures registry-vendor contract compliance
3. **Snapshot Artifacts** - Lossless snapshot system for audit reconstruction

**Key Features:**

- **Manifest-driven** - Manifest is source of truth
- **Lossless storage** - Parquet format preserves precision
- **Role-based** - Frames keyed by role (exec/htf/mtf)
- **Deterministic** - Synthetic data with fixed seed
- **Contract as registry** - Registry defines contract

**Usage:**

- **Toolkit Audit**: `python trade_cli.py backtest audit-toolkit`
- **Math Parity**: `python trade_cli.py backtest verify-suite --run-dir ...`
- **Complete Suite**: Both audits in sequence

**Benefits:**

- Catches implementation drift early
- Validates contract compliance
- Enables reproducible audits
- CI/CD friendly (JSON output)

---

**Document Version:** 1.0  
**Last Updated:** 2024  
**Status:** Comprehensive Audit Engine Review

