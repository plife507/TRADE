# Global Indicator & Strategy Verification Phases

## Overview
Deterministic CLI-only verification suite: 5 verification IdeaCards, batch normalization, snapshot-emitting backtests, and a pandas_ta parity audit driven from emitted snapshot artifacts.

## Constraints
- **CLI-only validation** (no pytest, no ad-hoc scripts).
- **Fail-loud**: unknown indicators/params, undeclared keys, base-key multi-output misuse, missing artifacts → non-zero exit.
- **Determinism**: fixed window **2024-01-01 → 2025-01-01**, one symbol **BTCUSDT**.
- **IdeaCard as source of truth**: all runtime inputs used in verification (account/risk/indicator params) declared in IdeaCards.

## Phase 0 — Add canonical TODO doc (required before edits)
- [x] Create `docs/todos/GLOBAL_INDICATOR_STRATEGY_VERIFICATION_PHASES.md` with phases and checkboxes mapping 1:1 to the items below.

## Phase 1 — Add 5 verification IdeaCards (schema-correct)
Create these files under `configs/idea_cards/verify/` (IDs match filenames):

- [x] `BTCUSDT_15m_verify_ema_atr.yml` (**EMA + ATR**, single TF)
- [x] `BTCUSDT_1h_verify_rsi_bbands.yml` (**RSI + BBANDS**, BBANDS is multi-output)
- [x] `BTCUSDT_1h_verify_macd_ema_filter.yml` (**MACD + EMA trend filter**, MACD multi-output)
- [x] `BTCUSDT_15m_verify_stochrsi.yml` (**STOCHRSI**, multi-output stress)
- [x] `BTCUSDT_15m_verify_exec_htf_ema_crossover.yml` (**Multi-TF exec+htf EMA crossover**)

IdeaCard requirements we’ll bake into all 5:
- `account:` fully explicit (starting equity, max leverage, margin_mode, fee_model, slippage, min_trade_notional).
- `symbol_universe: [BTCUSDT]`.
- Canonical TF strings only (`15m`, `1h`, `4h`).
- Multi-output references in `signal_rules` use **expanded keys only** (e.g., `macd_histogram`, `bb_lower`, `stochrsi_k`).

## Phase 2 — Batch normalize + combined JSON report (fail-loud)
Add a CLI batch entrypoint that normalizes **all IdeaCards in a directory** and returns a combined JSON report.

Implementation:
- Extend `trade_cli.py` to support batch normalization (new subcommand or new `--all-in-dir` mode).
- Implement tool-layer batch function in `src/tools/backtest_cli_wrapper.py` that:
  - loads every `*.yml/*.yaml` in `configs/idea_cards/verify/`
  - runs the existing normalizer (`normalize_idea_card_yaml(..., auto_generate_required=True)`)
  - **writes in-place** when `--write` is set
  - returns a single JSON payload: per-card `PASS/FAIL`, errors, and written paths

We will also tighten normalization to satisfy your spec:
- Validate `indicator_type` against **registry** *and* that it’s callable in **pandas_ta** (fail loud).
- Validate params using registry (strict) plus a pandas_ta existence check (no guessing).

## Phase 3 — Backtest run with snapshot emission
Add `--emit-snapshots` to `python trade_cli.py backtest run`.

Implementation:
- Wire `trade_cli.py` → `src/tools/backtest_cli_wrapper.py` → `src/backtest/runner.py`.
- Add `pyarrow` to `requirements.txt` to enable lossless Parquet snapshot frames.
- Add snapshot artifact writing under each run directory (only when `--emit-snapshots` is set), e.g.:
  - `snapshots/snapshot_manifest.json`
  - `snapshots/exec_frame.parquet`
  - `snapshots/htf_frame.parquet` (when present)
  - `snapshots/mtf_frame.parquet` (when present)

Snapshot manifest will include (per TF):

Manifest additions:
- `frame_format: "parquet"`
- `float_precision: "lossless"`
- (recommended) per TF: `feature_specs_resolved` (indicator_type + params)
- (recommended) per TF: `input_source_map` (series passed: close/high/low/volume)

- OHLCV slice used (timestamps + row counts)
- computed indicator columns list
- first-non-NaN index for the required indicator set
- alignment metadata (requested/effective window, sim_start_index, TF mapping)

Note: to avoid CSV rounding causing false mismatches at tolerance (<= 1e-8), we will write frames as **Parquet** (lossless float storage). We will use **pyarrow** (or a DuckDB parquet writer) and write timestamps consistently (project standard: UTC-naive).

## Phase 4 — Snapshot-based math parity audit (new CLI mode)
Add:

```bash
python trade_cli.py backtest indicators --audit-math-from-snapshots --run-dir <path> --json
```

Implementation:
- Extend `trade_cli.py` `backtest indicators` parser/handler to accept:
  - `--audit-math-from-snapshots`
  - `--run-dir <path>`
- Implement tool-layer audit in `src/tools/backtest_cli_wrapper.py`.
- Implement audit logic in a small backtest module (new file under `src/backtest/`), which:
  - loads `snapshot_manifest.json` + the saved frames (Parquet)
  - recomputes each declared indicator via **direct `pandas_ta` calls**
  - normalizes pandas_ta outputs through the **same canonicalization implementation** used by `src/backtest/indicator_vendor.py` / `src/backtest/indicator_registry.py`
  - compares **canonical output key -> snapshot column**; if missing after canonicalization: FAIL loud with `CANONICAL_OUTPUT_MISSING` and include raw pandas_ta cols, canonicalized cols, expected snapshot cols
  - compares per indicator column:
    - NaN mask identical
    - max abs diff <= 1e-8
    - mean diff reported
    - first valid index reported
    - PASS/FAIL per column + overall

## Phase 5 — One deterministic global PASS/FAIL report
Add a single CLI command that runs the whole workflow non-interactively:

```bash
python trade_cli.py backtest verify-suite \
  --dir configs/idea_cards/verify \
  --data-env live \
  --start 2024-01-01 \
  --end 2025-01-01 \
  --strict \
  --emit-snapshots \
  --json
```

Behavior:
- Normalizes all 5 cards (write-in-place) → **STOP on any failure**.
- Runs all 5 backtests (strict) with snapshot emission → **STOP on any failure**.
- Runs math parity audit from each produced run dir → **STOP on any mismatch**.
- Outputs one combined JSON report:
  - Card → Normalize PASS/FAIL
  - Card → Backtest PASS/FAIL (+ run_dir)
  - Indicator column → Parity PASS/FAIL (max/mean diff, first valid)

## Files we'll touch
- CLI wiring: `trade_cli.py`
- Tool layer: `src/tools/backtest_cli_wrapper.py`
- Runner/snapshot artifacts: `src/backtest/runner.py`, plus a small new snapshot/audit module under `src/backtest/`
- New IdeaCards: `configs/idea_cards/verify/`
- New TODO doc: `docs/todos/GLOBAL_INDICATOR_STRATEGY_VERIFICATION_PHASES.md`
- Dependencies: `requirements.txt` (add `pyarrow`)

---

## Completion Status: DONE (2024-12-14)

All phases completed and verified:

**Phase 0**: TODO doc created
**Phase 1**: 5 verification IdeaCards created and normalized
**Phase 2**: `backtest idea-card-normalize-batch` command implemented
**Phase 3**: `--emit-snapshots` flag + Parquet snapshot artifacts
**Phase 4**: `backtest indicators --audit-math-from-snapshots` command
**Phase 5**: `backtest verify-suite` orchestrating all phases

### Final Verification Run Results

```
python trade_cli.py backtest verify-suite \
  --dir configs/idea_cards/verify \
  --data-env live \
  --start 2024-01-01 --end 2025-01-01 --strict --json
```

**Results (1-year window: 2024-01-01 to 2025-01-01):**

| IdeaCard | Backtest | Audit | Columns | Max Diff |
|----------|----------|-------|---------|----------|
| BTCUSDT_15m_verify_ema_atr | PASS (3 trades) | PASS | 3/3 | 0.0 |
| BTCUSDT_15m_verify_exec_htf_ema_crossover | PASS (453 trades) | PASS | 3/3 | 0.0 |
| BTCUSDT_15m_verify_stochrsi | PASS (1446 trades) | PASS | 2/2 | 0.0 |
| BTCUSDT_1h_verify_macd_ema_filter | PASS (192 trades) | PASS | 4/4 | 0.0 |
| BTCUSDT_1h_verify_rsi_bbands | PASS (0 trades) | PASS | 6/6 | 0.0 |

**Overall: PASS** - All 5 cards normalized, backtested, and math parity verified.

### Bug Fixes Applied During Implementation

1. **BBands output key mismatch**: Fixed `"middle"` → `"mid"` in `indicator_vendor.py`
2. **BBands column naming**: Updated for pandas_ta format `BBL_{length}_{lower_std}_{upper_std}`
3. **MACD canonicalization**: Fixed `_canonicalize_column_name()` to detect `macdh`/`macds` prefixes

---

## Phase 6 — Production Hardening: Fail Loud + Canonical Naming

### Phase 6.1 — Remove unsupported-indicator fallback (fail loud)
- [x] Remove heuristic `else:` branch in `compute_indicator()` that hardcodes `needs_hlc`/`needs_volume` sets
- [x] If `not registry.is_supported(indicator_name)` → raise `ValueError` with error code prefix `UNSUPPORTED_INDICATOR_TYPE`

### Phase 6.2 — Rename canonical `mid` → `middle` for production clarity
- [x] Update `IndicatorRegistry` (`src/backtest/indicator_registry.py`):
  - `bbands.output_keys`: `mid` → `middle`
  - `bbands.primary_output`: `mid` → `middle`
  - `donchian.output_keys`: `mid` → `middle`
  - `donchian.primary_output`: `mid` → `middle`
- [x] Update vendor normalization (`src/backtest/indicator_vendor.py`):
  - `bbm: mid` → `bbm: middle`
  - `dcm: mid` → `dcm: middle`
- [x] Update `FeatureSpec.MULTI_OUTPUT_KEYS` (`src/backtest/features/feature_spec.py`):
  - BBANDS, DONCHIAN, ACCBANDS, HWC, TOS_STDEVALL → use `middle` instead of `mid`
- [x] Update audit canonicalizer (`src/backtest/audit_math_parity.py`)
- [x] Update IdeaCards/templates: `*_mid` → `*_middle`
- [x] Re-run verify-suite and confirm PASS

### Phase 6 Results (2024-12-14)

Verification suite passed with all production hardening changes:
- **Fail Loud**: Unsupported indicators now raise `UNSUPPORTED_INDICATOR_TYPE` immediately
- **Canonical Naming**: `mid` → `middle` for BBANDS, DONCHIAN, ACCBANDS, HWC, TOS_STDEVALL
- All 5 verification cards: PASS (normalization, backtest, math parity audit)
- Max absolute diff across all indicators: 0.0

---

## Phase 7 — Gate 1: Toolkit Contract Audit (All Registry Indicators)

**Invariant**: The registry is the contract. Vendor outputs must exactly match registry-declared canonical outputs.

### Phase 7.1 — Single Canonicalizer with Structured Output
- [x] Implement `canonicalize_indicator_outputs()` in `src/backtest/indicator_vendor.py` returning:
  - `raw_columns`, `raw_to_canonical`, `canonical_columns`, `declared_columns`
  - `extras_dropped`, `missing_declared`, `collisions`
- [x] Add error codes: `CANONICAL_COLLISION`, `MISSING_DECLARED_OUTPUTS`
- [x] Update vendor multi-output normalization to use this canonicalizer
- [x] Update `src/backtest/audit_math_parity.py` to use the shared canonicalizer (remove duplicated mapping)

### Phase 7.2 — Vendor Contract Enforcement
- [x] Vendor drops extras (record `extras_dropped`)
- [x] Vendor fails loud on missing declared outputs (`MISSING_DECLARED_OUTPUTS`)
- [x] Vendor fails loud on canonical collisions (`CANONICAL_COLLISION`)
- [x] Return only registry-declared outputs to engine

### Phase 7.3 — Toolkit Contract Audit CLI
- [x] Implement `src/backtest/toolkit_contract_audit.py`:
  - Deterministic synthetic OHLCV generator (2000 bars, seed 1337)
  - OHLC constraints: `high >= max(open, close)`, `low <= min(open, close)`
  - Non-zero volume, regime changes (trend/range/spike)
  - Input wiring validation (registry-defined inputs only)
- [x] Add CLI flags to `trade_cli.py`:
  - `--audit-toolkit`, `--sample-bars`, `--seed`, `--fail-on-extras`
- [x] Wire to `src/tools/backtest_cli_wrapper.py`

### Phase 7.4 — Manifest-Driven Snapshots (Role-Keyed)
- [x] Update `src/backtest/snapshot_artifacts.py`:
  - Role-keyed frames: `exec_frame.parquet`, `htf_frame.parquet`, `mtf_frame.parquet`
  - Manifest includes per-role: `outputs_expected_by_registry`, `outputs_written`, `extras_dropped`
- [x] Manifest becomes source of truth for audit comparisons

### Phase 7.5 — Manifest-Driven Parity Audit
- [x] Update `src/backtest/audit_math_parity.py`:
  - Compare only `outputs_written` from manifest (no hardcoded output counts)
  - Use shared canonicalizer for recompute comparison

### Phase 7.6 — Verify-Suite Preflight Wiring
- [x] `verify-suite` runs toolkit audit first by default
- [x] Add `--skip-toolkit-audit` flag to bypass
- [x] Hard-stop on toolkit audit failure

### Phase 7 Results (2024-12-15)
- **Gate 1 (Toolkit Contract Audit)**: 42/42 indicators PASS
- **Gate 2 (Verify-Suite)**: 10/10 cards PASS
  - Normalization: PASS
  - Backtests: PASS
  - Math parity audits: PASS (0.0 max diff across all indicators)
- **Runtime**: ~15s for toolkit audit (2000 bars, 42 indicators)

### Acceptance Criteria — ALL MET
- [x] Gate 1 runs in < 30s locally with 2000 bars
- [x] Zero canonical collisions across all registry indicators
- [x] Zero missing declared outputs
- [x] Extras consistently dropped + recorded
- [x] `--fail-on-extras` optionally fails on any extras
- [x] `verify-suite` hard-stops on Gate 1 failure unless skipped
