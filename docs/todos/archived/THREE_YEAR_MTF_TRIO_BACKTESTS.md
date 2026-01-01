# THREE_YEAR_MTF_TRIO_BACKTESTS

## Goal

Create **3 IdeaCards** and run **3-year** backtests (MTF enabled) for:
- **BTCUSDT**
- **ETHUSDT**
- **SOLUSDT**

Primary acceptance: **the strategy executes trades** (not optimized for win rate).

## Status: ✅ COMPLETE

All phases completed successfully. All three IdeaCards created and validated with 3-year backtests producing trades.

## Phase 1 — IdeaCards (Configs)

### Risk/Account constants (applies to all 3)
- [x] `account.starting_equity_usdt = 10000.0`
- [x] `account.max_leverage = 3.0`
- [x] `risk_model.stop_loss = atr_multiple(0.5)` using exec ATR key
- [x] `risk_model.take_profit = atr_multiple(1.5)` (adjustable)

### Deliverables
- [x] `configs/idea_cards/BTCUSDT_15m_mtf_tradeproof.yml`
- [x] `configs/idea_cards/ETHUSDT_15m_mtf_tradeproof.yml`
- [x] `configs/idea_cards/SOLUSDT_15m_mtf_tradeproof.yml`
- [x] Normalize each IdeaCard YAML in-place via CLI (`backtest idea-card-normalize --write`)

## Phase 2 — CLI Validation (Real Interfaces Only)

For each IdeaCard:
- [x] `python trade_cli.py backtest indicators --idea-card <ID> --print-keys`
- [x] `python trade_cli.py backtest preflight --idea-card <ID> --start <3y_start> --end <end>`
- [x] `python trade_cli.py backtest run --idea-card <ID> --start <3y_start> --end <end>`

### Acceptance Criteria
- [x] Each run completes successfully
- [x] Each run produces **at least 1 trade**
- [x] Artifacts are written (trades list + equity curve)


