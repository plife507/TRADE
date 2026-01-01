# Audit Tests Index

**PURPOSE:** Index of audit-related test plans, smoke tests, parity tests

---

## Smoke Tests

| Test | Command | Description | Review |
|------|---------|-------------|--------|
| Full Smoke | `--smoke full` | Complete CLI validation: data + trading + diagnostics | [Review](SMOKE_TEST_SYSTEM_REVIEW.md) |
| Data Smoke | `--smoke data` | Data builder operations only | [Review](SMOKE_TEST_SYSTEM_REVIEW.md) |
| Data Extensive | `--smoke data_extensive` | Clean DB, build history, fill gaps, sync | [Review](SMOKE_TEST_SYSTEM_REVIEW.md) |
| Orders Smoke | `--smoke orders` | All order types on DEMO | [Review](SMOKE_TEST_SYSTEM_REVIEW.md) |
| Backtest Smoke | `--smoke backtest` | Backtest pipeline validation | [Review](SMOKE_TEST_SYSTEM_REVIEW.md) |
| Metadata Smoke | `backtest metadata-smoke` | Indicator metadata system | [Review](SMOKE_TEST_SYSTEM_REVIEW.md) |

---

## Parity Tests

| Test | Source File | Description |
|------|-------------|-------------|
| Math Parity | `src/backtest/audit_math_parity.py` | FeatureFrameBuilder vs pandas_ta |
| Snapshot Plumbing | `src/backtest/audit_snapshot_plumbing_parity.py` | RuntimeSnapshotView accessor correctness |
| In-Memory Parity | `src/backtest/audit_in_memory_parity.py` | In-memory vs computed values |
| Artifact Parity | `src/backtest/artifact_parity_verifier.py` | Artifact consistency |

---

## Validation IdeaCards

Located in `configs/idea_cards/verify/`:

| Card | Symbol | TF | Purpose |
|------|--------|-----|---------|
| `BTCUSDT_15m_verify_ema_atr.yml` | BTCUSDT | 15m | EMA + ATR verification |
| `BTCUSDT_15m_verify_stochrsi.yml` | BTCUSDT | 15m | StochRSI verification |
| `BTCUSDT_1h_verify_rsi_bbands.yml` | BTCUSDT | 1h | RSI + BBands verification |
| `BTCUSDT_1h_verify_macd_ema_filter.yml` | BTCUSDT | 1h | MACD + EMA verification |
| (10 total) | — | — | Various indicator combinations |

---

## Reference Backtests

Located in `backtests/`:

| Backtest | Purpose | Bars | Trades |
|----------|---------|------|--------|
| `BTCUSDT_1h_system_validation_1year` | Long-horizon validation | 35,041 | 47 |
| `BTCUSDT_5m_stress_test_indicator_dense` | Low-TF stress test | 12,385 | 27 |
| `BTCUSDT_15m_mtf_tradeproof` | MTF validation | — | — |

---

