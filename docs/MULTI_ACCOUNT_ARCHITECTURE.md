# Multi-Account Architecture: Process-per-Account

## Problem

The system needs to run multiple live plays across separate Bybit sub-accounts simultaneously, with full isolation (crash containment, margin isolation, independent risk limits), controllable from both CLI/agents and a future Node.js UI.

## Decision: Process-per-Account (not singleton refactoring)

Each Bybit sub-account runs as its own OS process. A supervisor process manages them all. This avoids refactoring ~15 singletons in the existing codebase.

**Why process isolation over DI refactoring:**
- Zero changes to existing code (singletons work as-is, one per process)
- OS enforces isolation (crash in account "beta" doesn't touch "alpha")
- Bybit requires one private WebSocket per API key anyway
- Memory per account is ~100MB (capped by systemd)
- Adding an account = adding a process, not threading context through 15 components

## Bybit Sub-Account Capabilities

| Feature | Status | Details |
|---------|--------|---------|
| Sub-accounts | Supported | `/v5/user/create-sub-member`, types: normal, custodial |
| Separate API keys | Yes | Per sub-account, granular permissions, IP binding |
| Position isolation | Yes | Sub-account A's positions cannot affect B |
| Margin isolation | Yes | Sub-account A's liquidation cannot affect B |
| UTA per account | Yes | Each account independently configures UTA 1.0/2.0/Classic |
| Rate limits | Per API key | Configurable per UID |
| WebSocket | One per key | Private streams require separate connections per account |
| Fund transfers | Yes | Universal transfer between any accounts (master key) |

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    SUPERVISOR PROCESS                      │
│                                                            │
│  Reads: config/accounts.yml                               │
│  Manages: N child processes (one per account)             │
│  Provides: unified status, health, fund transfers         │
│  Exposes: JSON CLI + future HTTP API                      │
│                                                            │
├───────────┬───────────┬───────────┬───────────────────────┤
│           │           │           │                        │
│  Account  │  Account  │  Account  │  Account               │
│  "alpha"  │  "beta"   │  "gamma"  │  "shadow"              │
│           │           │           │                        │
│  PID 1001 │  PID 1002 │  PID 1003 │  PID 1004              │
│  1 play   │  2 plays  │  1 play   │  50 plays (shadow)     │
│  LIVE     │  LIVE     │  LIVE     │  SIM (no API orders)   │
│           │           │           │                        │
│  Own WS   │  Own WS   │  Own WS   │  SharedFeedHub         │
│  Own risk │  Own risk │  Own risk │  Own SimExchanges      │
│  Own PnL  │  Own PnL  │  Own PnL  │  Own perf DB           │
│           │           │           │                        │
└───────────┴───────────┴───────────┴───────────────────────┘
                          │
                    DuckDB (per-account)
                    data/accounts/{name}/
```

## Config Schema

```yaml
# config/accounts.yml
accounts:
  shadow:
    type: shadow                     # SimExchange, no real orders
    api_key_env: BYBIT_LIVE_API_KEY  # For market data WS only
    equity: 10000
    plays:
      - plays/shadow/*.yml
    limits:
      max_engines: 50

  alpha:
    type: live
    sub_account_uid: "123456"
    api_key_env: BYBIT_ALPHA_API_KEY
    api_secret_env: BYBIT_ALPHA_API_SECRET
    plays:
      - plays/live/sol_ema_cross.yml
    risk:
      max_daily_loss_usd: 500
      max_drawdown_pct: 10
      max_leverage: 3

  beta:
    type: live
    sub_account_uid: "789012"
    api_key_env: BYBIT_BETA_API_KEY
    api_secret_env: BYBIT_BETA_API_SECRET
    plays:
      - plays/live/sol_ict_sweep.yml
      - plays/live/btc_ema_trend.yml
    risk:
      max_daily_loss_usd: 1000
      max_drawdown_pct: 15
      max_leverage: 5
```

## New Modules

```
src/supervisor/
    supervisor.py       # Spawns/monitors/restarts account processes
    account_process.py  # Entry point for each account child process
    config.py           # Loads accounts.yml, validates
    fund_manager.py     # Cross-account fund transfers (master key)
    status.py           # Aggregates status across all accounts
```

## Disk Layout

```
data/
  accounts/
    shadow/
      heartbeat.json              # PID, uptime, bars_processed, last_error
      performance.duckdb          # Shadow performance (existing schema)
      journal/                    # Per-engine JSONL (existing)
    alpha/
      heartbeat.json
      performance.duckdb
      journal/
    beta/
      heartbeat.json
      performance.duckdb
      journal/
  market_data_live.duckdb         # Shared read-only across account processes
  runtime/
    supervisor.pid
    accounts/
      alpha.pid
      beta.pid
      shadow.pid
```

## Heartbeat Contract

Every long-running process writes this atomically every 30 seconds:

```json
{
  "pid": 12345,
  "account": "alpha",
  "status": "running",
  "last_heartbeat": "2026-03-30T14:22:00",
  "uptime_seconds": 3847,
  "plays_active": 1,
  "bars_processed": 24301,
  "trades_today": 3,
  "pnl_today_usdt": 47.20,
  "last_error": null
}
```

Supervisor reads heartbeat files to determine health. If `last_heartbeat` is older than 2 minutes, the process is considered dead/frozen and gets restarted.

## CLI Commands

```bash
# Supervisor
trade_cli.py supervisor start                          # Start all accounts
trade_cli.py supervisor stop                           # Graceful stop all
trade_cli.py supervisor status --json                  # All accounts overview
trade_cli.py supervisor restart --account alpha        # Restart one account

# Per-account queries
trade_cli.py account balance --account alpha --json
trade_cli.py account balance --all --json

# Fund management (master API key)
trade_cli.py funds transfer --from alpha --to beta --amount 500 --coin USDT
trade_cli.py funds balances --json

# Graduation (shadow -> live)
trade_cli.py graduate --play sol_ema_cross --to alpha --confirm
```

## Existing Singletons (No Changes Needed)

Each account process gets its own instances of these singletons. Process isolation means they don't conflict:

| Singleton | Current scope | Multi-account behavior |
|-----------|--------------|----------------------|
| ExchangeManager | One per process | Each account process has its own |
| RiskManager | One per process | Per-account risk limits |
| DailyLossTracker | One per process | Per-account daily loss |
| RealtimeState | One per process | Per-account positions/orders |
| RealtimeBootstrap | One per process | Per-account private WebSocket |
| GlobalRiskView | One per process | Per-account risk view |
| Application | One per process | Per-account lifecycle |
| MarketData | One per process | Can share read-only DuckDB |

## Implementation Phases

### Phase 1: Heartbeat + Account Process Entry Point
- Standardize heartbeat JSON for all long-running processes (shadow daemon, play run)
- Create `account_process.py` entry point that loads account config and runs plays
- Add `--account` flag to existing commands for account-scoped queries
- **GATE**: Shadow daemon writes heartbeat, status command reads it

### Phase 2: Supervisor
- `supervisor.py` reads `accounts.yml`, spawns/monitors/restarts child processes
- `trade_cli.py supervisor start/stop/status` commands
- systemd service for supervisor (replaces per-daemon services)
- **GATE**: Supervisor manages 2+ accounts, restarts crashed process within 30s

### Phase 3: Fund Management + Graduation
- `fund_manager.py` uses master API key for universal transfers
- `graduate` command: creates sub-account, transfers equity, starts play
- Per-account performance tracking in separate DuckDB files
- **GATE**: Graduate shadow play to live sub-account end-to-end

### Phase 4: Node.js Integration
- Supervisor exposes HTTP API (or Node.js reads heartbeat/status files)
- Dashboard shows all accounts, per-account P&L, graduation pipeline
- **GATE**: Node.js UI displays multi-account status in real-time

## Key Design Decisions

1. **Process isolation over shared memory**: Crash containment, zero singleton refactoring, matches Bybit's one-WS-per-key requirement.

2. **Filesystem as IPC**: Heartbeat files + DuckDB, not sockets or message queues. Simple, debuggable, survives crashes.

3. **Master key for fund management only**: Account processes use sub-account keys. Only the supervisor/fund_manager touches the master key.

4. **Shadow stays as-is**: Shadow daemon is already process-isolated with SimExchange. It becomes just another account in `accounts.yml`.

5. **Graduated autonomy**: Shadow trains plays → graduation scores plays → promote to sub-account → supervisor manages lifecycle. The pipeline is: shadow DB → graduation criteria → fund transfer → account process spawn.
