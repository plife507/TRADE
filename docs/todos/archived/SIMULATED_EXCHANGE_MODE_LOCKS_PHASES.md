# TODO Phases — SimulatedExchange Mode Locks (Isolated + USDT Perp Only)

Phase checklists for locking SimulatedExchange to isolated margin mode and USDT-quoted perpetual pairs only.

**Scope**: Backtest/simulator module (`src/backtest/`) only. This is a simulator constraint, not a global platform decision.

A phase is "done" only when ALL items are checked and acceptance criteria pass.

**STATUS: ALL PHASES COMPLETE** (December 2025)

---

## Phase 1 — Config Schema & Validation Functions ✅

### Config Schema Extensions

- [x] Add `margin_mode: str = "isolated"` field to `RiskProfileConfig` in `src/backtest/system_config.py`
- [x] Add `position_mode: str = "oneway"` field to `RiskProfileConfig`
- [x] Add `quote_ccy: str = "USDT"` field to `RiskProfileConfig`
- [x] Add `instrument_type: str = "perp"` field to `RiskProfileConfig`
- [x] Update `RiskProfileConfig` docstring to document new fields

### Validation Functions

- [x] Create `validate_usdt_pair(symbol: str) -> tuple[str, str]` function in `src/backtest/system_config.py`
  - [x] Rejects symbols not ending with "USDT"
  - [x] Rejects empty base currency
  - [x] Rejects non-alphanumeric base currency (strict BASEUSDT format)
  - [x] Returns (base, quote) tuple for valid symbols
  - [x] Clear error messages for invalid symbols

- [x] Create `validate_margin_mode_isolated(config: SystemConfig) -> None` function
  - [x] Validates `config.risk_profile.margin_mode == "isolated"`
  - [x] Clear error message for unsupported margin modes

- [x] Create `validate_quote_ccy_and_instrument_type(config: SystemConfig) -> None` function
  - [x] Validates `config.risk_profile.quote_ccy == "USDT"`
  - [x] Validates `config.risk_profile.instrument_type in {"perp", "linear_perp"}`
  - [x] Clear error messages for unsupported values

### Extension Point Enums (Non-Functional)

- [x] Add `MarginMode` enum with only `ISOLATED = "isolated"` (commented placeholders for future)
- [x] Add `PositionMode` enum with only `ONEWAY = "oneway"` (commented placeholders for future)
- [x] Add `InstrumentType` enum with `PERP = "perp"` and `LINEAR_PERP = "linear_perp"` (commented placeholders for future)

### Acceptance Criteria

- [x] All validation functions raise `ValueError` with clear, actionable error messages
- [x] `validate_usdt_pair("BTCUSDT")` succeeds and returns `("BTC", "USDT")`
- [x] `validate_usdt_pair("BTCUSD")` raises `ValueError`
- [x] `validate_usdt_pair("BTCUSDC")` raises `ValueError`
- [x] `validate_usdt_pair("BTCUSD_PERP")` raises `ValueError` (rejects suffixes)
- [x] `validate_margin_mode_isolated()` with `margin_mode="cross"` raises `ValueError`
- [x] `validate_quote_ccy_and_instrument_type()` with `quote_ccy="USDC"` raises `ValueError`
- [x] `validate_quote_ccy_and_instrument_type()` with `instrument_type="spot"` raises `ValueError`

---

## Phase 2 — Config Parsing & Validation Integration ✅

### Config Loader Updates

- [x] Update `load_system_config()` in `src/backtest/system_config.py` to parse new fields:
  - [x] Parse `margin_mode` from YAML (default "isolated")
  - [x] Parse `position_mode` from YAML (default "oneway")
  - [x] Parse `quote_ccy` from YAML (default "USDT")
  - [x] Parse `instrument_type` from YAML (default "perp")

- [x] Add validation calls in `load_system_config()` after parsing:
  - [x] Call `validate_usdt_pair(config.symbol)` after parsing symbol
  - [x] Call `validate_margin_mode_isolated(config)` after parsing risk_profile
  - [x] Call `validate_quote_ccy_and_instrument_type(config)` after parsing risk_profile

### Acceptance Criteria

- [x] Loading config with `symbol: "BTCUSDT"` succeeds
- [x] Loading config with `symbol: "BTCUSD"` fails at config load with clear error
- [x] Loading config with `margin_mode: "cross"` fails at config load with clear error
- [x] Loading config with `quote_ccy: "USDC"` fails at config load with clear error
- [x] All validation errors include actionable messages (what was passed vs what is required)

---

## Phase 3 — Engine Validation Integration ✅

### BacktestEngine Updates

- [x] Add validation calls in `BacktestEngine.__init__()` in `src/backtest/engine.py`:
  - [x] Call `validate_usdt_pair(self.config.symbol)` (defense in depth)
  - [x] Call `validate_margin_mode_isolated(self.config)` (defense in depth)

- [x] Add validation calls in `BacktestEngine.prepare_backtest_frame()` **BEFORE** `store.get_ohlcv()`:
  - [x] Call `validate_usdt_pair(self.config.symbol)` (fail fast without downloading data)
  - [x] Call `validate_margin_mode_isolated(self.config)` (fail fast without downloading data)

### Acceptance Criteria

- [x] Invalid symbol fails in `BacktestEngine.__init__()` with clear error
- [x] Invalid margin_mode fails in `BacktestEngine.__init__()` with clear error
- [x] Invalid symbol fails in `prepare_backtest_frame()` **before** any data fetch
- [x] Invalid margin_mode fails in `prepare_backtest_frame()` **before** any data fetch
- [x] No wasted data downloads for invalid configs

---

## Phase 4 — Exchange Validation Integration ✅

### SimulatedExchange Updates

- [x] Add validation call in `SimulatedExchange.__init__()` in `src/backtest/sim/exchange.py`:
  - [x] Call `validate_usdt_pair(symbol)` parameter (final validation)

### Acceptance Criteria

- [x] Creating exchange with `symbol="BTCUSD"` fails with clear error
- [x] Creating exchange with `symbol="BTCUSDT"` succeeds
- [x] Error message clearly indicates this is a simulator constraint

---

## Phase 5 — Currency Normalization (USD → USDT) ✅

### Documentation & Comments

- [x] Update `src/backtest/system_config.py`:
  - [x] Change docstring: "Starting capital in USD" → "Starting capital in USDT"
  - [x] Update comments: "USD" → "USDT" where referring to quote currency
  - [x] Add comment clarifying `*_usd` variable names are USDT values (backward compat)

- [x] Update `src/backtest/sim/exchange.py`:
  - [x] Change docstring: "Starting capital in USD" → "Starting capital in USDT"
  - [x] Update comments: "USD" → "USDT" where referring to quote currency

- [x] Update `src/backtest/engine.py`:
  - [x] Update log messages: clarify "USDT" where referring to quote currency
  - [x] Update comments: "USD" → "USDT" where referring to quote currency

- [x] Update `src/backtest/types.py`:
  - [x] Update docstrings: clarify `*_usd` fields are in USDT (quote currency)
  - [x] Update comments: "USD" → "USDT" where referring to quote currency

- [x] Update `docs/architecture/SIMULATED_EXCHANGE.md`:
  - [x] Update all "USD" references to "USDT" in user-facing documentation
  - [x] Add section: "Currency Model: USDT-Only"
  - [x] Clarify: "1 USDT ≈ 1 USD" but we use USDT as the quote currency

### Acceptance Criteria

- [x] No user-facing "USD" or "$" strings in backtest/sim code paths (except variable names with `_usd` suffix)
- [x] All docstrings and comments referring to quote currency use "USDT"
- [x] Variable names with `_usd` suffix are documented as USDT values (backward compatibility)

---

## Phase 6 — Test Coverage ✅

### Test File Creation

- [x] Create `tests/test_simulated_exchange_mode_locks.py`

### Test Cases

- [x] `test_margin_mode_cross_fails()` - margin_mode="cross" fails before simulation starts
- [x] `test_symbol_usdc_fails()` - non-USDT quote currency fails
- [x] `test_symbol_usd_fails()` - USD quote currency fails
- [x] `test_symbol_btcusdt_succeeds()` - valid USDT pair succeeds
- [x] `test_symbol_rejects_suffixes()` - symbols with suffixes (e.g., BTCUSD_PERP) fail
- [x] `test_symbol_rejects_separators()` - symbols with separators (e.g., BTC-USDT) fail
- [x] `test_quote_ccy_non_usdt_fails()` - quote_ccy != "USDT" fails
- [x] `test_instrument_type_invalid_fails()` - invalid instrument_type fails
- [x] `test_instrument_type_perp_succeeds()` - "perp" and "linear_perp" succeed
- [x] `test_validation_before_data_fetch()` - invalid config fails before data fetch
- [x] `test_min_trade_notional_is_usdt()` - min_trade_usd=1.0 is interpreted as 1 USDT

### Acceptance Criteria

- [x] All tests pass (42 tests)
- [x] Tests cover all validation paths (config load, engine init, before data fetch, exchange init)
- [x] Tests verify fail-fast behavior (no data download for invalid configs)

---

## Phase 7 — Validation & Cleanup ✅

### Grep Validation

- [x] Run grep check: `grep -r "USD\|\\$" src/backtest --include="*.py" | grep -v "usdt\|USDT" | grep -v "#.*USD"`
- [x] Verify only variable names with `_usd` suffix remain (acceptable for backward compat)
- [x] Verify no user-facing "USD" or "$" strings in comments/logs

### Final Acceptance Criteria

- [x] Passing `margin_mode="cross"` fails **at config load** and **before data fetch** with clear error
- [x] Passing `symbol="BTCUSD"` or `symbol="BTCUSDC"` fails **at config load** and **before data fetch** with clear error
- [x] Passing `symbol="BTCUSDT"` succeeds
- [x] Invalid symbol/mode fails **before historical data fetch** (no wasted data download)
- [x] All user-facing "USD/$" strings removed from backtest/sim paths (variable suffixes `_usd` allowed, but documented as USDT)
- [x] `min_trade_usd=1.0` is interpreted as 1 USDT minimum
- [x] Validation happens at: config load, engine init, **before data fetch**, and exchange init
- [x] Extension point enums exist (minimal, only implemented values)
- [x] Tests cover all validation paths including pre-fetch validation
- [x] Grep check: no USD/$ in simulator code paths (except variable names and excluded patterns)
- [x] `validate_usdt_pair()` rejects anything not strict `BASEUSDT` format (no suffixes, separators, or variations)
- [x] `quote_ccy` validation enforces exactly "USDT"
- [x] `instrument_type` validation enforces `{"perp", "linear_perp"}` only

---

## Deferred (Explicitly Out of Scope)

**Do NOT implement** (deferred to future phases):

- [ ] Demo/live environment configs (`market_data_env`, `execution_env`, `stream vs historical`)
- [ ] Demo/live adapters or parity gates
- [ ] Global platform-level margin mode or symbol validation (keep this backtest-only)

**Rationale**: This plan is scoped to backtest/simulator constraints only. Environment routing and demo/live parity are separate concerns.

---

## Notes

- **Fail-fast philosophy**: Validation happens at config load, engine init, before data fetch, and exchange init (defense in depth)
- **Error messages**: Clear, actionable errors telling user what they passed vs what is required
- **Backward compatibility**: Keep `_usd` suffix in variable names (Phase 1 compatibility), but clarify in docs/comments these are USDT values
- **Extension points**: Enums and validation functions are structured to allow adding cross/hedge later without refactor
- **No silent coercion**: All validation raises `ValueError` with clear messages

---

## Implementation Summary

**Completed**: December 2025

### Files Created
- `tests/test_simulated_exchange_mode_locks.py` - 42 tests covering all validation paths

### Files Modified
- `src/backtest/system_config.py` - Enums, validation functions, config fields, parsing
- `src/backtest/engine.py` - Validation in __init__ and prepare_backtest_frame
- `src/backtest/sim/exchange.py` - Validation in __init__
- `src/backtest/types.py` - Currency model documentation
- `src/backtest/sim/types.py` - Currency model documentation
- `src/backtest/sim/ledger.py` - Currency model documentation
- `src/backtest/sim/metrics/metrics.py` - Currency model documentation
- `src/backtest/sim/execution/slippage_model.py` - Currency model documentation
- `src/backtest/sim/execution/liquidity_model.py` - Currency model documentation
- `src/backtest/sim/execution/impact_model.py` - Currency model documentation
- `src/backtest/sim/constraints/constraints.py` - Currency model documentation
- `docs/architecture/SIMULATED_EXCHANGE.md` - Currency Model section added

### Test Results
- 42 new tests passing
- All existing tests passing (67+ tests)
