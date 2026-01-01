# TRADE Backtest Engine v1: Architecture Design Review

**Date**: December 18, 2025  
**Purpose**: Comprehensive review of core design decisions, contracts, and scope boundaries  
**Status**: Current State Assessment

---

## Executive Summary

This document provides a systematic review of the TRADE backtest engine's core architecture, answering fundamental questions about scope, contracts, data alignment, simulator parity, risk models, determinism, artifacts, and future agent integration. Each section maps to explicit design decisions documented in code, architecture docs, and project rules.

**Key Findings:**
- ✅ **v1 Scope**: Strategy research + sim parity (not live execution automation)
- ✅ **Market Type**: USDT perps, isolated margin only (mode locks enforced)
- ✅ **IdeaCard Schema**: Immutable core fields, explicit validation, no silent defaults
- ✅ **Data Alignment**: Closed-candle only, TradingView-style MTF, deterministic warmup
- ✅ **Simulator Parity**: Bybit-aligned margin model, funding, fees, liquidation
- ✅ **Determinism**: Proven via `verify-determinism` CLI, seed-based randomness
- ✅ **Artifacts**: Content-addressed run IDs, mandatory RunManifest, structured exports

---

## 1. Core Intent and Scope

### 1.1 What is the single primary goal for v1: sim parity, strategy research, or live execution?

**Answer**: **Strategy research with sim parity as a prerequisite.**

**Evidence:**
- From `CLAUDE.md`: "We are building the backtesting + strategy factory stack in phases"
- From `PROJECT_STATUS.md`: "Strategy Factory: ⚠️ Partial - IdeaCards work, promotion manual"
- Explicitly off-limits: "Demo/live automation for backtested strategies" (CLAUDE.md line 32)

**v1 Goal Hierarchy:**
1. **Primary**: Enable strategy research via IdeaCard → backtest → metrics pipeline
2. **Secondary**: Achieve Bybit-aligned simulator parity (margin, fees, funding, liquidation)
3. **Tertiary**: Provide audit gates and validation tooling (preflight, determinism, parity checks)

**Not in v1:**
- Automated strategy promotion to live trading
- Agent-driven strategy generation (future phase)
- Composite strategies or strategy selection policies
- Forecasting models / ML

---

### 1.2 What is explicitly out of scope for v1 (no matter how tempting)?

**Answer**: From `CLAUDE.md` lines 28-32:

**Explicitly Off-Limits:**
- Forecasting models / ML
- Composite strategies
- Strategy selection policies
- "Factory" orchestration beyond "run this system" (no automated promotions yet)
- Demo/live automation for backtested strategies

**Additional v1 Exclusions (from codebase):**
- Cross margin mode (isolated only)
- USDC perps or inverse contracts (USDT only)
- Hedge position mode (one-way only)
- Partial fills (full fill or reject in Phase 1)
- ADL (Auto-Deleveraging) in liquidation model
- Multi-symbol backtests (single-symbol only in current iteration)

---

### 1.3 What market type is v1-only (USDT perps, isolated margin, cross margin excluded)?

**Answer**: **USDT linear perpetuals, isolated margin mode only.**

**Mode Locks (from `CLAUDE.md` lines 155-163):**
- **Quote Currency**: USDT only (`validate_usdt_pair()` enforced)
- **Margin Mode**: Isolated only (`validate_margin_mode_isolated()` enforced)
- **Position Mode**: One-way only (hardcoded)
- **Instrument Type**: Linear perp only (symbol validation)

**Enforcement Points:**
1. Config load time (`IdeaCard.from_dict()` validation)
2. Engine init (`BacktestEngine.__init__()` re-validation)
3. Exchange init (`SimulatedExchange.__init__()`)

**Future Iterations:**
- USDC perps MAY be supported via config/version (not permanent restriction)
- Cross margin MAY be added in future versions (not in v1)

---

### 1.4 What "definition of done" means you can start Demo promotion?

**Answer**: **Not explicitly defined in v1 scope, but implicit gates exist.**

**Current Promotion Gates (from `PROJECT_STATUS.md`):**
- ✅ All smoke tests pass (`--smoke full`)
- ✅ Phase 6 backtest smoke tests pass (6/6 tests with determinism)
- ✅ Toolkit contract audit passes (42/42)
- ✅ Math parity audit passes
- ✅ Financial metrics audit passes (`backtest metrics-audit` 6/6)
- ✅ Snapshot plumbing audit passes
- ✅ Artifact validation gates active (automatic HARD FAIL)
- ✅ Determinism verification available (`verify-determinism --re-run`)
- ✅ Production pipeline validated (5 IdeaCards, all gates passed)

**Missing (Not in v1):**
- Explicit "Demo promotion" criteria document
- Automated promotion workflow
- OOS validation requirements
- Walk-forward validation requirements
- Minimum sample size thresholds

**Implicit Requirements (from architecture):**
- Strategy must pass all audit gates
- Artifacts must be valid (RunManifest, structured exports)
- Determinism must be proven (`verify-determinism --re-run` must pass)
- No P0 blockers in `PROJECT_STATUS.md`

---

## 2. Contracts and "Trading Language" (IdeaCards)

### 2.1 What is the minimal IdeaCard schema that must never change mid-run?

**Answer**: **Core identity fields + account config (immutable during run).**

**Immutable Core (from `src/backtest/idea_card.py` lines 800-824):**
```python
@dataclass
class IdeaCard:
    # Identity (REQUIRED, immutable)
    id: str
    version: str
    name: Optional[str] = None
    description: Optional[str] = None
    
    # Account configuration (REQUIRED, immutable)
    account: Optional[AccountConfig] = None  # No defaults allowed
    
    # Scope (REQUIRED, immutable)
    symbol_universe: tuple = field(default_factory=tuple)
    
    # Timeframes (exec required, immutable)
    tf_configs: Dict[str, TFConfig] = field(default_factory=dict)
```

**Validation Rules (from `idea_card.py` lines 832-866):**
- `id` and `version` are required (empty string triggers validation error)
- `account` section is REQUIRED (no hard-coded defaults)
- `symbol_universe` must have at least one symbol
- `exec` timeframe is required in `tf_configs`

**What Can Change (not in core schema):**
- `signal_rules` (strategy logic) - but changes require new IdeaCard version
- `risk_model` (SL/TP/sizing) - but changes require new IdeaCard version
- `feature_specs` (indicators) - but changes require new IdeaCard version

**Versioning Policy:**
- IdeaCard version bump required for any strategy change
- Hash-based identity ensures determinism (same hash = same strategy)

---

### 2.2 Which fields are hashed/canonicalized, and what is excluded from the hash?

**Answer**: **All strategy-defining fields are hashed; metadata excluded.**

**Hashed Fields (from `src/backtest/runner.py` and artifact standards):**
- `idea_card_id` (canonical identifier)
- `idea_card_hash` (full SHA256 of IdeaCard YAML)
- `symbol_universe` (sorted, uppercase)
- `tf_configs` (all TF roles: exec, htf, mtf)
- `window_start` / `window_end` (test window boundaries)
- `account` config (starting_equity_usdt, max_leverage, fees, slippage)
- `feature_specs` (all indicators per TF)
- `signal_rules` (entry/exit logic)
- `risk_model` (SL/TP/sizing)

**Excluded from Hash (metadata only):**
- `name` (display name)
- `description` (human-readable description)
- `category` (validation vs strategies)
- `attempt_id` (timestamp for strategies category)
- `run_id` (derived from hash, not part of hash)

**Hash Derivation (from `src/backtest/artifacts/artifact_standards.py`):**
- Full hash: SHA256 of canonicalized IdeaCard YAML
- Short hash: First 8 chars (or 12 for collision recovery)
- Hash algorithm: Explicitly stored in RunManifest (`hash_algorithm="sha256"`)

---

### 2.3 What is the exact allowed indicator/feature vocabulary (registry contract)?

**Answer**: **42 indicators registered in toolkit registry (from `PROJECT_STATUS.md`).**

**Registry Location:**
- `src/backtest/features/indicator_registry.py` (inferred from architecture)
- Toolkit contract audit: `backtest audit-toolkit` (42/42 pass)

**Indicator Declaration (from `idea_card.py` FeatureSpec):**
- Indicators MUST be declared via `FeatureSpec` in IdeaCard
- `indicator_type`: String matching registry key (e.g., "ema", "rsi", "atr")
- `params`: Dict of indicator parameters (e.g., `{"length": 14}`)
- `input_source`: OHLCV field (e.g., "close", "high", "volume")

**Validation Rules:**
- Undeclared indicators raise `KeyError` via `TFContext.get_indicator_strict()`
- No implicit defaults - indicators MUST be declared in FeatureSpec
- Multi-output indicators: Same `feature_spec_id`, different `indicator_key`

**Unknown Indicator Behavior:**
- If IdeaCard references unknown indicator → validation error at load time
- `validate_idea_card_features()` checks all indicators against registry
- Preflight gate fails if indicator not in registry

---

### 2.4 How do you validate TF compatibility for each indicator/feature?

**Answer**: **Per-TF validation via FeatureSpec + TFConfig.**

**Validation Flow (from `src/backtest/execution_validation.py`):**
1. `validate_idea_card_features()` checks all FeatureSpecs
2. Each FeatureSpec declares `indicator_type` and `params`
3. Registry lookup validates indicator exists
4. TF compatibility: Indicators can be declared on any TF (exec, htf, mtf)
5. No explicit TF restrictions in registry (indicators work on any TF)

**TF Role Mapping:**
- `exec`: Execution timeframe (required)
- `htf`: Higher timeframe (optional, for trend/bias)
- `mtf`: Medium timeframe (optional, for structure)

**Warmup Computation (per TF):**
- `compute_warmup_requirements()` computes warmup per TF role
- Formula: `max(feature_warmups[tf], rule_lookback_bars[tf], bars_history_required[tf])`
- Each indicator has TF-specific warmup (e.g., EMA on 5m vs 1h has different warmup bars)

---

### 2.5 What are the semantic misuse rules (what is forbidden usage)?

**Answer**: **Explicit validation rules prevent misuse.**

**Forbidden Usage (from `CLAUDE.md` and codebase):**

1. **Implicit Defaults:**
   - ❌ Using indicator without declaring in FeatureSpec
   - ❌ Missing `account` section (no hard-coded defaults)
   - ❌ Missing `exec` timeframe

2. **Lookahead:**
   - ❌ Accessing future bars in strategy
   - ❌ Computing indicators on partial candles
   - ❌ HTF/MTF indicators updating mid-bar (must wait for TF close)

3. **Mode Violations:**
   - ❌ Cross margin mode (isolated only)
   - ❌ Non-USDT symbols (BTCUSD, BTCUSDC rejected)
   - ❌ Hedge position mode (one-way only)

4. **Data Misuse:**
   - ❌ Using live API during backtest (simulator uses DuckDB only)
   - ❌ Modifying IdeaCard mid-run (immutable)
   - ❌ Accessing indicators not declared in FeatureSpec

5. **Risk Misuse:**
   - ❌ Bypassing risk manager (all orders go through risk checks)
   - ❌ Exceeding max_leverage (enforced at entry gate)
   - ❌ Negative equity (liquidation triggered)

**Enforcement:**
- Validation at IdeaCard load time
- Runtime assertions in engine
- Audit gates (preflight, determinism, parity)

---

### 2.6 What is the default behavior if an IdeaCard references an unknown feature?

**Answer**: **Hard fail at validation time (no silent defaults).**

**Behavior (from `CLAUDE.md` line 167):**
- `TFContext.get_indicator_strict()` raises `KeyError` for undeclared indicators
- `validate_idea_card_features()` fails if indicator not in registry
- Preflight gate fails with actionable error message

**Error Message Example:**
```
Invalid IdeaCard: Indicator 'unknown_indicator' not found in registry.
Available indicators: ema, rsi, atr, ...
```

**No Fallback:**
- No implicit indicator computation
- No default indicator values
- No "best guess" behavior
- Fail loud, fail fast

---

## 3. Data and Time Alignment

### 3.1 What is the source of truth for OHLCV and how is it versioned (DuckDB tables/partitions)?

**Answer**: **DuckDB is source of truth; versioning via data_source_id (not table partitions).**

**Source of Truth:**
- `data/market_data_live.duckdb` (LIVE data)
- `data/market_data_demo.duckdb` (DEMO data)
- Tables: `ohlcv_{symbol}_{tf}` (e.g., `ohlcv_BTCUSDT_5`)
- Historical data fetched via Bybit API (Data leg, not Trading leg)

**Versioning (from `RunManifest`):**
- `data_source_id`: String identifying data source (e.g., "bybit_live", "bybit_demo")
- `data_version`: Optional version string (currently `None` in manifests)
- No table-level versioning (single source of truth per symbol/TF)

**Data Provenance:**
- `candle_policy`: "closed_only" (explicitly stored in manifest)
- Data fetch: Via `HistoricalDataStore` (DuckDB operations)
- Sync: `sync_ohlcv` tool updates DuckDB tables
- Heal: `heal_data` tool fills gaps

**Future Versioning (not in v1):**
- Table partitions by date range (not implemented)
- Data version tracking per sync (not implemented)
- Snapshot-based versioning (not implemented)

---

### 3.2 What is your candle "close-time" rule and timezone rule?

**Answer**: **UTC timezone, close-time = bar end timestamp.**

**Timezone:**
- All timestamps in UTC (no timezone conversion)
- `ts_close`: Bar end timestamp (canonical bar close time)
- `ts_open`: Bar start timestamp (previous bar's close)

**Close-Time Rule (from `docs/architecture/ARCH_SNAPSHOT.md`):**
- Bar represents `[ts_open, ts_close)` interval
- Close-time = `ts_close` (exclusive end of interval)
- Strategy evaluates at `ts_close` (bar close)
- Fills occur at next bar's `ts_open`

**Canonical Bar Format:**
```python
@dataclass
class Bar:
    ts_open: datetime    # Bar start (UTC)
    ts_close: datetime   # Bar end (UTC)
    open: float
    high: float
    low: float
    close: float
    volume: float
```

**TradingView Alignment:**
- Close-time semantics match TradingView `lookahead_off`
- HTF/MTF bars close at TF boundary (e.g., 1h bar closes at :00)
- No partial candle computation

---

### 3.3 How do you guarantee closed-candle only (no lookahead) across all TFs?

**Answer**: **Multi-layer enforcement: data loading, indicator computation, snapshot access.**

**Enforcement Layers (from `CLAUDE.md` lines 114-119):**

1. **Data Loading:**
   - Only closed bars loaded from DuckDB
   - No partial candles in historical data

2. **Indicator Computation:**
   - Indicators computed on closed candles only (vectorized, outside hot loop)
   - HTF/MTF indicators compute only on TF close
   - Between closes, last-closed values forward-fill unchanged

3. **Snapshot Access:**
   - `RuntimeSnapshotView` provides O(1) array access
   - Snapshot `ts_close` must equal bar `ts_close` (asserted at runtime)
   - Strategy invoked ONLY at bar close (never mid-bar)

4. **MTF Alignment:**
   - HTF/MTF indices update only on TF close
   - Forward-fill semantics match TradingView `lookahead_off`
   - O(1) lookup via precomputed `ts_close_ms → index` mapping

**Runtime Assertions:**
- `snapshot.ts_close == bar.ts_close` (enforced in engine)
- Strategy never sees future bars (array bounds checked)
- HTF/MTF values constant until next TF close

---

### 3.4 What is the MTF alignment rule (forward-fill to exec TF close) and where is it enforced?

**Answer**: **TradingView-style forward-fill; enforced in TFContext and snapshot view.**

**MTF Alignment Rule (from `CLAUDE.md` lines 114-119):**
- HTF/MTF indicators compute only on TF close
- Between closes, last-closed values forward-fill unchanged
- Forward-fill until next TF close (no mid-bar updates)

**Enforcement Points:**

1. **TFContext (from `src/backtest/runtime/tf_context.py`):**
   - `get_indicator_strict()` returns last-closed value
   - HTF/MTF indices update only on TF close detection
   - Forward-fill via cached last-closed values

2. **RuntimeSnapshotView:**
   - HTF/MTF features accessed via `htf_*` / `mtf_*` properties
   - Values forward-filled from last closed bar
   - No mid-bar updates (values constant until next TF close)

3. **Engine Step Order:**
   - HTF/MTF caches refresh on TF close detection
   - Snapshot built after cache refresh
   - Strategy sees forward-filled values (not partial)

**Example:**
- 1h HTF bar closes at 10:00
- 5m exec bars: 10:00, 10:05, 10:10, 10:15, ...
- HTF indicator value remains constant across all 5m bars until 11:00 (next 1h close)

---

### 3.5 What is your warmup policy per TF (warmup_bars) and how is sufficiency computed?

**Answer**: **Variable warmup per TF; computed from indicator requirements + market structure.**

**Warmup Computation (from `src/backtest/execution_validation.py` lines 466-515):**

**Formula:**
```python
effective_warmup = max(
    max_feature_warmup,      # Max warmup from FeatureSpecs
    tf_config.warmup_bars,   # Explicit warmup in TFConfig
    idea_card.bars_history_required,  # Global history requirement
    structure_lookback,      # market_structure.lookback_bars
)
```

**Per-TF Warmup:**
- `warmup_by_role[role]`: Warmup bars for each TF role (exec, htf, mtf)
- `max_warmup_bars`: Maximum across all TFs
- `delay_by_role[role]`: Delay bars from `market_structure.delay_bars`

**Indicator Warmup (from `docs/session_reviews/2024-12-17_indicator_warmup_architecture.md`):**
- Variable warmup per indicator type:
  - EMA: `3 × length` bars
  - RSI: `length + 1` bars
  - ATR: `length` bars
  - Custom formulas per indicator type

**Sufficiency Check (from `src/backtest/runtime/preflight.py`):**
- Preflight computes `warmup_requirements` from IdeaCard
- Data window: `data_start = window_start - warmup_span - safety_buffer`
- Coverage check: Verify data exists for full warmup period
- Insufficient coverage → preflight fails with actionable error

**Delay Bars (separate from warmup):**
- `delay_bars`: Bars to skip at evaluation start (no-lookahead guarantee)
- `eval_start = aligned_start + delay_bars * tf_duration`
- Engine uses lookback for data loading, delay for evaluation offset

---

### 3.6 What happens when coverage is insufficient (backfill invocation, heal loop, hard fail)?

**Answer**: **Preflight gate with auto-sync option; hard fail if still insufficient.**

**Preflight Gate (from `src/backtest/runtime/preflight.py`):**

1. **Coverage Check:**
   - Compute required data window (warmup + test window)
   - Query DuckDB for available data
   - Identify gaps (missing bars, date ranges)

2. **Auto-Sync (if enabled):**
   - `auto_sync_missing=True` (default in Phase 6)
   - `--fix-gaps` flag triggers auto-sync
   - Bounded enforcement: Sync only missing ranges (not full history)

3. **Gap Detection:**
   - `gap_threshold_multiplier=3.0` (default)
   - Gaps > 3× TF duration flagged as insufficient
   - Small gaps (< threshold) tolerated

4. **Hard Fail (if still insufficient):**
   - Preflight returns `PreflightReport` with errors
   - Engine refuses to run if preflight fails
   - Actionable error message: "Insufficient data: missing bars in [date_range]"

**Heal Loop (not automatic):**
- `heal_data` tool manually fills gaps
- Not invoked automatically (user must run manually)
- Preflight suggests heal command if gaps detected

**Backfill (not in v1):**
- No automatic backfill loop
- User must run `sync_ohlcv` manually
- Future: Auto-backfill on preflight failure (not implemented)

---

## 4. Simulator / Exchange Parity

### 4.1 What exact margin model is implemented (IM/MM, isolated USDT, leverage rules)?

**Answer**: **Bybit-aligned isolated margin model with USDT accounting.**

**Margin Model (from `docs/architecture/ARCH_SNAPSHOT.md` lines 367-389):**

**Formulas:**
- **Initial Margin (IM)**: `position_value × IMR`
- **IMR**: `1 / leverage` (from IdeaCard `account.max_leverage`)
- **Maintenance Margin (MM)**: `position_value × MMR`
- **MMR**: Default `0.005` (0.5%, Bybit lowest tier)
- **Equity**: `cash_balance + unrealized_pnl`
- **Free Margin**: `equity - used_margin`
- **Available Balance**: `max(0, free_margin)`

**Currency:**
- All accounting in **USDT** (not USD)
- Simulator uses `usdt` suffix (e.g., `equity_usdt`, `cash_balance_usdt`)
- Live trading uses `size_usd` (exchange-native notional, different semantics)

**Leverage Rules:**
- `max_leverage`: From IdeaCard `account.max_leverage` (required, no default)
- Entry gate: `required_margin = position_value / max_leverage`
- Leverage enforced at entry (rejects if insufficient margin)

**Mode:**
- Isolated margin only (cross margin rejected)
- One-way position mode (hedge mode not supported)

---

### 4.2 How is liquidation defined and triggered (equity vs MM, bankruptcy price, fees)?

**Answer**: **Liquidation when equity <= maintenance_margin; fee applied at mark price.**

**Liquidation Condition (from `src/backtest/sim/liquidation/liquidation_model.py` lines 56-95):**
```python
if ledger_state.equity_usdt <= ledger_state.maintenance_margin_usdt:
    # Liquidation triggered
```

**Trigger Rules:**
- Position must exist (no position = no liquidation)
- Equity <= maintenance_margin (not <, uses <=)
- Liquidation at mark price (not bankruptcy price)
- Liquidation fee: `0.06%` of position value (configurable)

**Liquidation Fee:**
- `liquidation_fee_rate: 0.0006` (default)
- Applied to position value at liquidation
- Deducted from cash balance
- Tracked separately from trading fees

**No ADL:**
- Auto-Deleveraging (ADL) not implemented in Phase 1
- Future: ADL may be added (not in v1)

**Bankruptcy Price:**
- Not explicitly computed
- Liquidation occurs at mark price (simpler model)
- Future: Bankruptcy price calculation may be added

---

### 4.3 How are fees modeled (maker/taker, tiering, minimums)?

**Answer**: **Taker-only fees in v1; maker/taker rates configurable per IdeaCard.**

**Fee Model (from `src/backtest/idea_card.py` AccountConfig):**

**Fee Rates:**
- `taker_bps`: Taker fee rate in basis points (default: 6.0 = 0.06%)
- `maker_bps`: Maker fee rate in basis points (default: 2.0 = 0.02%)
- Configurable per IdeaCard (no global defaults)

**Fee Application:**
- Entry fee: `entry_notional × taker_fee_rate` (deducted from cash)
- Exit fee: `exit_notional × taker_fee_rate` (deducted from realized PnL)
- All fills use taker fee in Phase 1 (maker detection not implemented)

**Tiering:**
- No tiering in v1 (flat rate per IdeaCard)
- Future: Tier-based fees may be added (not implemented)

**Minimums:**
- No minimum fee in v1
- Fees computed as percentage of notional
- Future: Minimum fee enforcement may be added

---

### 4.4 How is funding applied (when, sign, rate source, schedule)?

**Answer**: **Every 8 hours at UTC boundaries; rate from DuckDB; positive = received.**

**Funding Schedule (from `docs/architecture/ARCH_SNAPSHOT.md` lines 400-406):**
- Timing: Every 8 hours (00:00, 08:00, 16:00 UTC)
- Basis: `position_value × funding_rate`
- Sign: Positive = received funding (long pays short), negative = paid funding

**Rate Source:**
- Historical funding rates from DuckDB (`funding_rates` table)
- Fetched via `sync_funding_rates` tool
- Rate applied at funding event time (8h boundaries)

**Funding Tracking:**
- Separate line items: `total_funding_paid_usdt`, `net_funding_usdt`
- Tracked separately from trading fees in financial metrics
- Applied to cash balance (not unrealized PnL)

**Funding Model (from `src/backtest/sim/funding/funding_model.py`):**
- Events generated at 8h boundaries within test window
- Rate interpolated from DuckDB data
- Applied only if position exists

---

### 4.5 How are partial fills, slippage, and spread handled (even if simplified)?

**Answer**: **Full fill or reject; slippage via configurable model; spread from bar OHLC.**

**Partial Fills:**
- **Not supported in Phase 1** (from `src/backtest/sim/execution/execution_model.py` line 128)
- Full fill or reject (no partial fills)
- Future: Partial fills may be added (not in v1)

**Slippage:**
- Configurable per IdeaCard: `account.slippage_bps` (basis points)
- Applied at fill time: `fill_price = bar.open ± slippage`
- Default: `2.0 bps` (0.02%)
- Slippage tracked separately in metrics

**Spread:**
- Modeled via `SpreadModel` (from `src/backtest/sim/pricing/spread_model.py`)
- Spread computed from bar OHLC: `spread = (high - low) / close * spread_multiplier`
- Applied to bid/ask prices: `bid = mark_price - spread/2`, `ask = mark_price + spread/2`
- Market orders fill at `ask` (long) or `bid` (short)

**Liquidity:**
- `LiquidityModel` checks max fillable size (from `execution_model.py` line 125)
- Partial fill rejection not implemented (full fill or reject)
- Future: Liquidity constraints may be added

---

### 4.6 What order types exist in sim (market/limit/stop), and what is intentionally omitted?

**Answer**: **Market orders only in v1; limit/stop intentionally omitted.**

**Supported Order Types:**
- **Market orders**: Fill at bar open with slippage
- Entry orders: Queue at bar close, fill at next bar open
- TP/SL: Checked within bar against OHLC

**Intentionally Omitted (Phase 1):**
- Limit orders (not implemented)
- Stop orders (not implemented)
- Trailing stops (not implemented)
- OCO orders (not implemented)
- Conditional orders (not implemented)

**TP/SL Handling:**
- TP/SL checked against bar OHLC (not separate order types)
- Deterministic tie-break: SL checked first (worst-case)
- Longs: SL checked before TP
- Shorts: SL checked before TP

**Future:**
- Limit orders may be added (not in v1)
- Stop orders may be added (not in v1)

---

### 4.7 What invariants must always hold (equity equation, balances non-negative, etc.)?

**Answer**: **Accounting invariants verified every bar; assertions in ledger.**

**Invariants (from `docs/architecture/ARCH_SNAPSHOT.md` lines 380-387):**
```python
# Equity equation
assert equity_usdt == cash_balance_usdt + unrealized_pnl_usdt

# Free margin
assert free_margin_usdt == equity_usdt - used_margin_usdt

# Available balance (non-negative)
assert available_balance_usdt == max(0.0, free_margin_usdt)
assert available_balance_usdt >= 0.0
```

**Additional Invariants (from `src/backtest/sim/ledger.py`):**
- `cash_balance_usdt >= 0.0` (after liquidation fee, may go negative temporarily)
- `used_margin_usdt >= 0.0`
- `maintenance_margin_usdt >= 0.0`
- `unrealized_pnl_usdt` can be negative (open loss)
- `equity_usdt` can be negative (account blown)

**Enforcement:**
- Invariants checked in `Ledger._recompute_derived()` (every bar)
- Assertions in ledger state (development mode)
- Metrics track violations (if any)

**Liquidation Invariant:**
- If `equity_usdt <= maintenance_margin_usdt` → liquidation triggered
- Position closed, liquidation fee applied
- Cash balance may go negative (account blown)

---

## 5. Risk Model

### 5.1 What is the risk unit (USDT risk per trade, % equity, or fixed notional)?

**Answer**: **Configurable per IdeaCard: percent_equity or fixed_notional (USDT).**

**Risk Units (from `src/backtest/idea_card.py` SizingRule):**

**Sizing Models:**
- `percent_equity`: Risk `value%` of equity per trade
- `fixed_notional`: Risk fixed `value` USDT per trade

**Risk Unit:**
- All risk in **USDT** (simulator currency)
- `value`: Float (percentage for `percent_equity`, USDT for `fixed_notional`)
- `max_leverage`: Maximum leverage allowed (enforced at entry gate)

**Example:**
- `percent_equity` with `value=2.0` → Risk 2% of equity per trade
- `fixed_notional` with `value=100.0` → Risk 100 USDT per trade

**Position Sizing:**
- Computed by `SimulatedRiskManager` (from risk model)
- Entry gate checks: `required_margin <= available_balance`
- Leverage enforced: `position_value / equity <= max_leverage`

---

### 5.2 What is the max risk per position and max portfolio exposure rule?

**Answer**: **Max leverage per IdeaCard; no explicit portfolio exposure limit in v1.**

**Max Risk Per Position:**
- `max_leverage`: From IdeaCard `account.max_leverage` (required)
- Entry gate: `position_value / equity <= max_leverage`
- Rejects if leverage would exceed max

**Portfolio Exposure:**
- **Not explicitly limited in v1** (single-symbol only)
- Future: Multi-symbol backtests may add portfolio exposure limits
- Current: Each position independently sized (no cross-position limits)

**Risk Per Trade:**
- Controlled by `SizingRule` (percent_equity or fixed_notional)
- No explicit "max risk per trade" cap (beyond leverage limit)
- Future: Max risk per trade cap may be added

---

### 5.3 What are stop rules (hard SL, trailing, time stop) and who owns them (strategy vs risk)?

**Answer**: **Hard SL/TP from IdeaCard risk_model; strategy owns signal exits.**

**Stop Rules (from `src/backtest/idea_card.py` RiskModel):**

**Stop Loss:**
- `StopLossRule`: Type (`atr_multiple`, `percent`, `fixed`), value
- Computed at entry time (from risk model)
- Enforced by simulator (checked every bar)
- Strategy does NOT own SL (risk model owns it)

**Take Profit:**
- `TakeProfitRule`: Type (`atr_multiple`, `percent`, `fixed`), value
- Computed at entry time (from risk model)
- Enforced by simulator (checked every bar)
- Strategy does NOT own TP (risk model owns it)

**Signal Exits:**
- `ExitRule` in `SignalRules`: Strategy-defined exit conditions
- Checked by strategy (not risk model)
- Strategy owns signal exits (separate from SL/TP)

**Trailing Stops:**
- **Not implemented in v1**
- Future: Trailing stops may be added (not in v1)

**Time Stops:**
- **Not implemented in v1**
- Future: Time-based stops may be added (not in v1)

**Ownership:**
- **Risk Model**: SL/TP computation and enforcement
- **Strategy**: Signal exit rules (entry/exit conditions)
- **Simulator**: SL/TP checking (every bar, deterministic)

---

### 5.4 What is the "out of capital" stop condition and how is it enforced?

**Answer**: **Liquidation triggers account blown; no explicit "out of capital" stop.**

**Out of Capital Condition:**
- **Not explicitly defined as separate stop**
- Implicit: `equity_usdt <= maintenance_margin_usdt` → liquidation
- After liquidation: `cash_balance_usdt` may be negative (account blown)

**Enforcement:**
- Liquidation model checks every bar
- If `equity_usdt <= maintenance_margin_usdt` → position liquidated
- Liquidation fee applied (0.06% of position value)
- Account may be "blown" (negative equity)

**Entry Gate:**
- `available_balance_usdt < required_margin` → order rejected
- Prevents new positions when out of capital
- No explicit "stop trading" flag (rejects individual orders)

**Future:**
- Explicit "out of capital" stop may be added (not in v1)
- Circuit breaker for account blown (not implemented)

---

### 5.5 What is the maximum leverage allowed and who sets it (IdeaCard vs SystemConfig)?

**Answer**: **IdeaCard sets max_leverage; no SystemConfig override in v1.**

**Max Leverage Source:**
- `IdeaCard.account.max_leverage` (required, no default)
- No SystemConfig override (IdeaCard is source of truth)
- Enforced at entry gate: `position_value / equity <= max_leverage`

**Validation:**
- `max_leverage > 0` (validated at IdeaCard load)
- No upper bound (user can set any positive value)
- Future: Global max leverage cap may be added (not in v1)

**Enforcement:**
- Entry gate checks: `required_margin = position_value / max_leverage`
- Rejects if `available_balance < required_margin`
- Leverage computed: `position_value / equity` (must be <= max_leverage)

---

## 6. Engine Step Order and Determinism

### 6.1 What is the exact step order each tick (advance feeds → indicators → snapshot → eval → orders → fills → logs)?

**Answer**: **Deterministic step order per bar; documented in ARCH_SNAPSHOT.md.**

**Step Order (from `docs/architecture/ARCH_SNAPSHOT.md` lines 175-205):**

```python
def process_bar(bar, signal):
    # 1. Get prices for this bar
    prices = price_model.get_prices(bar)
    
    # 2. Apply funding (if funding time)
    funding = funding_model.apply(bar.ts_open)
    
    # 3. Update entry orders from previous bar
    entry_fills = execution_model.fill_entry_orders(bar)
    
    # 4. Check TP/SL for existing positions
    exit_fills = execution_model.check_tp_sl(bar, prices)
    
    # 5. Update ledger with fills and funding
    ledger.update(entry_fills + exit_fills, funding, prices)
    
    # 6. Check liquidation
    liquidation = liquidation_model.check(ledger.state, prices)
    
    # 7. Process new signal (queue for next bar)
    if signal:
        execution_model.queue_entry(signal)
    
    # 8. Record metrics
    metrics.record(...)
    
    return StepResult(...)
```

**Engine Step Order (from `src/backtest/engine.py`):**
1. **Advance feeds**: Load next bar from FeedStore
2. **Update HTF/MTF caches**: Refresh on TF close (if multi-TF)
3. **Build snapshot**: Create RuntimeSnapshotView (O(1) access)
4. **Evaluate strategy**: Invoke strategy function with snapshot
5. **Process signal**: Queue entry order (fills at next bar open)
6. **Process bar**: SimulatedExchange.process_bar() (fills, funding, liquidation)
7. **Update metrics**: Record equity, trades, PnL
8. **Log artifacts**: Write trades, equity curve (if enabled)

**Determinism Guarantees:**
- Same inputs → same outputs (proven via `verify-determinism`)
- No randomness in step order (deterministic)
- Slippage model may use seed (if implemented)

---

### 6.2 Is every run reproducible from (seed + inputs + data version)? What breaks determinism?

**Answer**: **Yes, reproducible; seed not used in v1 (deterministic by design).**

**Reproducibility (from `PROJECT_STATUS.md`):**
- ✅ Determinism verification: `backtest verify-determinism --run <path> --re-run`
- ✅ Same inputs → identical outputs (proven via CLI)
- ✅ RunManifest stores full hash (64-char SHA256)

**Inputs Required for Reproducibility:**
- IdeaCard YAML (full hash in manifest)
- Data window (window_start, window_end)
- Symbol universe
- Data source (DuckDB tables, data_source_id)
- Engine version (PIPELINE_VERSION in manifest)

**Seed:**
- **Not used in v1** (fully deterministic)
- Future: Seed may be added for slippage model (not implemented)
- Current: No randomness sources (deterministic by design)

**What Breaks Determinism:**
- **Data changes**: If DuckDB data changes between runs
- **Code changes**: If engine/simulator code changes
- **IdeaCard changes**: If IdeaCard YAML changes (different hash)
- **Time-dependent logic**: None in v1 (all deterministic)

**Verification:**
- `verify-determinism --re-run` compares outputs byte-for-byte
- Artifacts must match exactly (trades.csv, equity.csv, result.json)
- RunManifest hash must match (full hash comparison)

---

### 6.3 Where are randomness sources used (slippage model, fills, synthetic data) and how are they seeded?

**Answer**: **No randomness sources in v1; fully deterministic.**

**Randomness Sources:**
- **None in v1** (fully deterministic)
- Slippage: Fixed model (no randomness)
- Fills: Deterministic (full fill or reject)
- Synthetic data: Not used (real data only)

**Future Randomness (not in v1):**
- Slippage model: May use seed for random slippage (not implemented)
- Fill model: May use seed for partial fills (not implemented)
- Synthetic data: Not planned (real data only)

**Seeding (if added):**
- Seed would be stored in RunManifest (`seed` field, currently `None`)
- Seed used for slippage/fill randomness (not implemented)
- Reproducibility: Same seed + inputs → same outputs

---

### 6.4 How do you prevent warmup drift between preflight and engine execution?

**Answer**: **Shared warmup computation function; preflight and engine use same logic.**

**Warmup Consistency (from `src/backtest/runtime/windowing.py`):**

**Shared Function:**
- `compute_data_window()`: Canonical function for data fetch boundaries
- Used by both Preflight and Engine (same logic)
- Formula: `data_start = window_start - warmup_span - safety_buffer`

**Warmup Computation:**
- `compute_warmup_requirements()`: Canonical function (from `execution_validation.py`)
- Used by Preflight to compute warmup requirements
- Engine uses same function (no drift)

**Preflight Validation:**
- Preflight computes warmup requirements from IdeaCard
- Validates data coverage for full warmup period
- Engine uses same warmup requirements (no recomputation)

**Delay Bars:**
- `delay_bars` from `market_structure.delay_bars` (per TF)
- Preflight computes delay, engine uses same delay
- No drift: Same computation, same result

**Enforcement:**
- Preflight report includes warmup requirements
- Engine validates warmup sufficiency (matches preflight)
- Mismatch → hard fail (should never happen)

---

## 7. Artifacts, Logging, and Auditability

### 7.1 What artifacts are written every run (config hash, metrics, trades, equity, debug traces)?

**Answer**: **Mandatory RunManifest + structured exports; debug traces optional.**

**Mandatory Artifacts (from `src/backtest/artifacts/artifact_standards.py`):**

1. **RunManifest** (`run_manifest.json`):
   - Full hash (64-char SHA256)
   - Short hash (8 or 12 chars, folder name)
   - IdeaCard identity (id, hash)
   - Symbol universe, timeframes, window
   - Data provenance (data_source_id, candle_policy)
   - Engine versions (simulator_version, engine_version, etc.)

2. **BacktestResult** (`result.json`):
   - Structured metrics (CAGR, Sharpe, Max DD%, etc.)
   - Trade summary (count, win rate, avg PnL)
   - Equity curve summary
   - Stop reason (if early termination)

3. **Trades** (`trades.parquet` or `trades.csv`):
   - All closed trades (entry/exit, PnL, fees, funding)
   - Structured format (parquet preferred, CSV fallback)

4. **Equity Curve** (`equity.parquet` or `equity.csv`):
   - Equity points (timestamp, equity_usdt, cash, unrealized_pnl)
   - Structured format (parquet preferred, CSV fallback)

**Optional Artifacts:**
- Debug traces: Not written by default (optional)
- Event log: Not written by default (optional)
- Snapshot dumps: Not written by default (optional)

**Artifact Validation:**
- Automatic HARD FAIL if artifacts invalid (not warning)
- RunManifest must exist (mandatory)
- Artifacts must match RunManifest hash (validation gate)

---

### 7.2 What is the run ID scheme and how do you link runs to IdeaCard hashes and data versions?

**Answer**: **Content-addressed run IDs (hash-based); RunManifest links to IdeaCard and data.**

**Run ID Scheme (from `src/backtest/artifacts/artifact_standards.py`):**

**Folder Structure:**
```
{base_dir}/{category}/{idea_card_id}/{universe_id}/{run_hash}/
```

**Run Hash:**
- Default: 8-char short hash (first 8 chars of full hash)
- Collision recovery: 12-char extended hash (if collision detected)
- Full hash: 64-char SHA256 (stored in RunManifest)

**Hash Inputs:**
- IdeaCard YAML (canonicalized)
- Symbol universe (sorted, uppercase)
- Window boundaries (window_start, window_end)
- TF configs (all roles: exec, htf, mtf)
- Account config (starting_equity, max_leverage, fees)

**Linking (from RunManifest):**
- `idea_card_id`: IdeaCard identifier
- `idea_card_hash`: Full SHA256 of IdeaCard YAML
- `data_source_id`: Data source identifier (e.g., "bybit_live")
- `data_version`: Optional data version (currently `None`)
- `full_hash`: Full input hash (links run to all inputs)

**Discovery:**
- Hash-driven: Folder name = short hash
- Manifest-driven: Load RunManifest to get full hash
- No sequential IDs: All discovery via hash/manifest

---

### 7.3 What audit gates exist today (toolkit registry audit, parity audits, invariants)?

**Answer**: **6 audit gates; all accessible via CLI commands.**

**Audit Gates (from `PROJECT_STATUS.md` and CLI):**

1. **Toolkit Registry Audit** (`backtest audit-toolkit`):
   - Validates all 42 indicators in registry
   - Checks indicator computation correctness
   - Status: ✅ 42/42 pass

2. **Math Parity Audit** (`backtest math-parity`):
   - Validates simulator math matches Bybit formulas
   - Checks margin, fees, funding, liquidation
   - Status: ✅ Pass (P0 input-source bug fixed 2025-12-17)

3. **Financial Metrics Audit** (`backtest metrics-audit`):
   - Validates financial metrics computation (CAGR, Sharpe, Max DD%, etc.)
   - Checks 6/6 metrics pass
   - Status: ✅ 6/6 pass

4. **Snapshot Plumbing Audit** (`backtest audit-snapshot-plumbing`):
   - Validates snapshot access (O(1), no lookahead)
   - Checks MTF alignment
   - Status: ✅ Pass

5. **Determinism Verification** (`backtest verify-determinism --re-run`):
   - Validates run reproducibility
   - Compares outputs byte-for-byte
   - Status: ✅ Available

6. **Artifact Validation** (automatic after every run):
   - Validates RunManifest exists and is valid
   - Checks artifacts match RunManifest hash
   - Status: ✅ Automatic HARD FAIL if invalid

**Additional Gates (not in v1):**
- OOS validation: Not implemented
- Walk-forward validation: Not implemented
- Parameter robustness: Not implemented

---

### 7.4 What metrics are "promotion gates" vs "informational only"?

**Answer**: **No explicit promotion gates in v1; all metrics informational.**

**Promotion Gates:**
- **Not defined in v1** (promotion is manual)
- Future: Promotion gates may be added (not implemented)
- Current: All metrics are informational only

**Informational Metrics (from `BacktestMetrics`):**
- CAGR, Sharpe ratio, Calmar ratio
- Max drawdown %, win rate, avg PnL
- Total trades, profitable trades
- Total fees, total funding
- Equity curve statistics

**Future Promotion Gates (not in v1):**
- Minimum Sharpe ratio threshold
- Maximum drawdown % threshold
- Minimum trade count
- OOS validation threshold
- Walk-forward validation threshold

**Current Promotion:**
- Manual process (no automated gates)
- Human review of metrics
- No explicit "promote" vs "reject" criteria

---

### 7.5 What minimum debug trace is required to explain any trade decision?

**Answer**: **Trades.parquet contains entry/exit details; debug traces optional.**

**Minimum Debug Trace (from trades artifact):**

**Trades.parquet Fields:**
- `entry_timestamp`, `exit_timestamp`
- `entry_price`, `exit_price`
- `size_usdt`, `size` (base units)
- `realized_pnl_usdt`, `fees_paid_usdt`, `funding_paid_usdt`
- `entry_reason`, `exit_reason` (signal, stop_loss, take_profit)
- `stop_loss_price`, `take_profit_price`

**Missing (not in v1):**
- Snapshot state at entry/exit (not written)
- Indicator values at entry/exit (not written)
- Signal conditions met (not written)
- Strategy reasoning (not written)

**Optional Debug Traces:**
- Snapshot dumps: Not written by default
- Event log: Not written by default
- Strategy reasoning: Not written by default

**Future:**
- Debug trace mode may be added (not in v1)
- Snapshot dumps at entry/exit (not implemented)
- Strategy reasoning logs (not implemented)

---

## 8. Evaluation and Overfitting Controls (Pre-Agents)

### 8.1 What is your default split for IS/OOS or walk-forward (time-based, multiple segments)?

**Answer**: **Not implemented in v1; user must manually define windows.**

**IS/OOS Split:**
- **Not implemented in v1**
- User must manually define `window_start` and `window_end`
- No automatic split (user responsibility)

**Walk-Forward:**
- **Not implemented in v1**
- User must manually run multiple windows
- No automated walk-forward validation

**Future:**
- IS/OOS split may be added (not implemented)
- Walk-forward validation may be added (not implemented)
- Multiple segment validation may be added (not implemented)

---

### 8.2 What is your parameter search policy (ranges, step sizes, constraints, no edge hugging)?

**Answer**: **Not implemented in v1; manual parameter exploration only.**

**Parameter Search:**
- **Not implemented in v1**
- User must manually create IdeaCards with different parameters
- No automated parameter search

**Future:**
- Parameter search may be added (not implemented)
- Ranges, step sizes, constraints (not defined)
- Edge hugging prevention (not implemented)

---

### 8.3 What is your robustness test (cost sensitivity, parameter perturbation, regime slicing)?

**Answer**: **Not implemented in v1; manual robustness testing only.**

**Robustness Tests:**
- **Not implemented in v1**
- User must manually test different scenarios
- No automated robustness validation

**Future:**
- Cost sensitivity tests may be added (not implemented)
- Parameter perturbation may be added (not implemented)
- Regime slicing may be added (not implemented)

---

### 8.4 What are the auto-reject criteria (OOS decay, brittleness, liquidation proximity, etc.)?

**Answer**: **Not implemented in v1; no auto-reject criteria.**

**Auto-Reject Criteria:**
- **Not implemented in v1**
- No automated rejection (manual review only)
- No OOS decay checks
- No brittleness detection
- No liquidation proximity checks

**Future:**
- Auto-reject criteria may be added (not implemented)
- OOS decay thresholds (not defined)
- Brittleness detection (not implemented)
- Liquidation proximity checks (not implemented)

---

### 8.5 What is the minimum sample size for trades before trusting any metric?

**Answer**: **Not defined in v1; no minimum sample size requirement.**

**Minimum Sample Size:**
- **Not defined in v1**
- No automated checks for trade count
- User must manually assess statistical significance

**Future:**
- Minimum sample size may be added (not implemented)
- Statistical significance tests (not implemented)
- Trade count thresholds (not defined)

---

## 9. Modularity and Repo Structure

### 9.1 What are the top-level modules, and what is each one forbidden from importing?

**Answer**: **Domain-based modules with strict import boundaries.**

**Top-Level Modules (from `CLAUDE.md` lines 59-85):**

**SIMULATOR Domain (`src/backtest/`):**
- `engine.py`: Backtest orchestrator
- `sim/`: Simulated exchange (pricing, execution, ledger, constraints)
- `runtime/`: Snapshot, FeedStore, TFContext
- `features/`: FeatureSpec, FeatureFrameBuilder
- **Forbidden**: Must NOT import from `src/core/` or `src/exchanges/`

**LIVE Domain (`src/core/`, `src/exchanges/`):**
- `core/`: Trading logic, risk management, order execution
- `exchanges/`: Exchange-specific API wrappers (BybitClient)
- **Forbidden**: Must NOT import from `src/backtest/sim/` (domain isolation)

**SHARED Domain:**
- `config/`: Configuration (domain-agnostic)
- `data/`: Market data, DuckDB storage
- `tools/`: CLI/API surface (primary interface)
- `utils/`: Logging, rate limiting, helpers
- **Forbidden**: Must NOT contain trading logic or execution logic

**Import Rules:**
- SIMULATOR → SHARED: ✅ Allowed
- LIVE → SHARED: ✅ Allowed
- SIMULATOR → LIVE: ❌ Forbidden (domain isolation)
- LIVE → SIMULATOR: ❌ Forbidden (domain isolation)

---

### 9.2 What are the stable interfaces (Feed API, Exchange API, Risk API, Strategy API)?

**Answer**: **Stable interfaces per domain; documented in architecture docs.**

**Stable Interfaces:**

1. **Feed API** (`src/backtest/runtime/feed_store.py`):
   - `FeedStore`: O(1) array access for OHLCV + indicators
   - `get_feature(tf_role, indicator_key, offset)`: Get indicator value
   - Stable: Used by RuntimeSnapshotView

2. **Exchange API** (`src/backtest/sim/exchange.py`):
   - `SimulatedExchange.submit_order()`: Submit order
   - `SimulatedExchange.process_bar()`: Process bar (fills, funding, liquidation)
   - Stable: Used by engine

3. **Risk API** (`src/backtest/sim/risk/risk_policy.py`):
   - `RiskPolicy.compute_position_size()`: Compute position size from signal
   - `RiskPolicy.check_entry_gate()`: Check entry gate (margin, leverage)
   - Stable: Used by engine

4. **Strategy API** (`src/backtest/engine.py`):
   - Strategy function: `(snapshot, params) -> Optional[Signal]`
   - `RuntimeSnapshotView`: Read-only snapshot (O(1) access)
   - Stable: Used by all strategies

**Interface Stability:**
- v1 interfaces are stable (not changing mid-phase)
- Future changes: New phases, not breaking changes
- Backward compatibility: Not required (build-forward only)

---

### 9.3 Where do you see file bloat today, and what should be split first?

**Answer**: **No explicit bloat identified; files under 1500 lines (project rule).**

**File Size Rule:**
- Keep files under 1500 lines (from `CLAUDE.md`)
- Split into logical modules if larger

**Current State:**
- No files identified as bloated in review
- Architecture docs suggest modular design (no bloat)

**Future Splits (if needed):**
- `engine.py`: May split if exceeds 1500 lines
- `idea_card.py`: May split if exceeds 1500 lines
- `sim/exchange.py`: Already modular (delegates to specialized modules)

---

### 9.4 What is the boundary between "research/backtest" and "runtime/live"?

**Answer**: **Clear domain boundaries; IdeaCard is the bridge.**

**Boundary (from `CLAUDE.md`):**

**Research/Backtest (`src/backtest/`):**
- IdeaCard → FeatureSpec → FeatureFrames → FeedStores → Engine
- SimulatedExchange (no live API calls)
- DuckDB historical data (no live data)
- Artifacts (trades, equity, metrics)

**Runtime/Live (`src/core/`, `src/exchanges/`):**
- Strategy → Risk Manager → Order Executor → Exchange
- BybitClient (live API calls)
- Live market data (WebSocket, REST)
- Real-time position tracking

**Bridge:**
- **IdeaCard**: Declarative strategy spec (used by both)
- **Strategy logic**: Can be shared (entry/exit rules)
- **Risk model**: Different implementations (simulator vs live)

**Isolation:**
- Simulator MUST NOT call live tools
- Live trading MUST NOT use simulator exchange
- Shared utilities: Domain-agnostic only

---

## 10. Roadmap and Next Branch (Agents Later)

### 10.1 What exact outputs will agents be allowed to produce first (IdeaCards, test plans, parameter ranges)?

**Answer**: **Not defined in v1; agents not started (future phase).**

**Agent Outputs (Future):**
- **IdeaCards**: Agents may generate IdeaCard YAMLs (not in v1)
- **Test plans**: Agents may generate test plans (not in v1)
- **Parameter ranges**: Agents may generate parameter ranges (not in v1)

**Current State:**
- Agent module: ❌ Not started (from `PROJECT_STATUS.md`)
- No agent integration (manual process only)

**Future:**
- Agent outputs will be defined in future phases
- Safety constraints will be added (not defined)

---

### 10.2 What will agents never be allowed to do initially (modify engine/sim/risk code)?

**Answer**: **Not defined in v1; agents not started (future phase).**

**Agent Restrictions (Future):**
- **Engine code**: Agents may NOT modify engine code (not in v1)
- **Simulator code**: Agents may NOT modify simulator code (not in v1)
- **Risk code**: Agents may NOT modify risk code (not in v1)

**Current State:**
- No agent restrictions (agents not started)
- Manual process only (no automation)

**Future:**
- Agent restrictions will be defined in future phases
- Code modification boundaries will be enforced

---

### 10.3 What artifact format will agents consume (FitnessReport, RunManifest, failure reasons)?

**Answer**: **Not defined in v1; agents not started (future phase).**

**Agent Artifact Consumption (Future):**
- **RunManifest**: Agents may consume RunManifest (not in v1)
- **FitnessReport**: Not defined (may be added)
- **Failure reasons**: Not defined (may be added)

**Current Artifacts:**
- RunManifest: Exists (human-readable, not agent-optimized)
- BacktestResult: Exists (human-readable, not agent-optimized)
- Trades/Equity: Exists (structured, may be agent-consumable)

**Future:**
- Agent-optimized artifact formats may be added
- FitnessReport may be added (not defined)
- Failure reason extraction may be added (not defined)

---

### 10.4 What safety rollback rules exist when you eventually go Demo/Live?

**Answer**: **Not defined in v1; promotion is manual (no automation).**

**Safety Rollback Rules (Future):**
- **Not defined in v1** (promotion is manual)
- No automated rollback (manual process only)

**Current Promotion:**
- Manual process (human review)
- No automated gates (informational metrics only)
- No rollback rules (not implemented)

**Future:**
- Safety rollback rules may be added (not defined)
- Automated promotion gates may be added (not implemented)
- Circuit breakers may be added (not implemented)

---

## Summary

### Key Findings

1. **v1 Scope**: Strategy research + sim parity (not live execution automation)
2. **Market Type**: USDT perps, isolated margin only (mode locks enforced)
3. **IdeaCard Schema**: Immutable core, explicit validation, no silent defaults
4. **Data Alignment**: Closed-candle only, TradingView-style MTF, deterministic warmup
5. **Simulator Parity**: Bybit-aligned margin model, funding, fees, liquidation
6. **Determinism**: Proven via `verify-determinism`, seed not used (fully deterministic)
7. **Artifacts**: Content-addressed run IDs, mandatory RunManifest, structured exports
8. **Audit Gates**: 6 gates (toolkit, math parity, metrics, snapshot, determinism, artifacts)
9. **Evaluation**: Not implemented (manual process only)
10. **Agents**: Not started (future phase)

### Gaps Identified

1. **Promotion Criteria**: No explicit "Demo promotion" definition
2. **Evaluation Controls**: No IS/OOS split, walk-forward, parameter search
3. **Agent Integration**: Not started (future phase)
4. **Safety Rollback**: Not defined (manual process only)

### Recommendations

1. **Document Promotion Criteria**: Define explicit "Demo promotion" gates
2. **Add Evaluation Controls**: Implement IS/OOS split, walk-forward validation
3. **Define Agent Boundaries**: Specify what agents can/cannot do
4. **Add Safety Rollback**: Define rollback rules for Demo/Live promotion

---

**Document Status**: Complete  
**Last Updated**: December 18, 2025  
**Next Review**: When agent integration begins

