# Bybit Sub-Account Strategy Isolation

**Date:** 2026-02-13
**Status:** Brainstorm / investigation complete, no code written

## Concept

One Bybit sub-account per Play. Each strategy runs with its own isolated equity, positions, and risk boundaries. The master account handles capital allocation via universal transfers.

## Why

- **No cross-contamination** -- a blown stop on Play A can't margin-call Play B
- **Independent risk** -- each Play has its own drawdown circuit breaker, equity curve, leverage
- **Clean accounting** -- PnL per strategy is just the sub-account balance delta
- **Concurrent execution** -- multiple LiveRunners, each with their own API keys, no position conflicts
- **Kill switch per strategy** -- freeze a sub-account to halt one Play without touching others

## Architecture Mapping

```
Master Account (capital pool, no trading)
  ├── Sub-Account: sol_ema_triple_long
  │     ├── API key pair (dedicated)
  │     ├── Equity: $2,000 (allocated from master)
  │     ├── Play: sol_ema_triple_long.yml
  │     └── LiveRunner instance
  │
  ├── Sub-Account: btc_swing_short
  │     ├── API key pair (dedicated)
  │     ├── Equity: $5,000
  │     ├── Play: btc_swing_short.yml
  │     └── LiveRunner instance
  │
  └── Sub-Account: eth_range_mean_revert
        ├── API key pair (dedicated)
        ├── Equity: $3,000
        ├── Play: eth_range_mean_revert.yml
        └── LiveRunner instance
```

## What Already Fits

| Component | Current State | Sub-Account Ready? |
|-----------|--------------|-------------------|
| PlayEngine | One engine per Play | Yes -- no changes |
| LiveRunner | One runner per Play | Yes -- just needs its own API keys |
| RiskManager | Per-Play risk checks | Yes -- equity is naturally isolated |
| SizingModel | Sizes against equity | Yes -- sub-account equity = Play equity |
| OrderExecutor | Submits via ExchangeManager | Yes -- each gets its own BybitClient |
| TP/SL | Exchange-native conditionals | Yes -- scoped to sub-account positions |
| Max Drawdown | Circuit breaker per runner | Yes -- sub-account equity is the reference |

## What Would Need to Change

### 1. Configuration: Multi-Credential Support

Currently `BybitConfig` holds one set of credentials. Need to support N credential sets.

```yaml
# Option A: Credentials in Play YAML
# plays/sol_ema_triple_long.yml
account:
  sub_account: "sol_ema_001"
  api_key_env: "BYBIT_SUB_SOL_EMA_KEY"
  api_secret_env: "BYBIT_SUB_SOL_EMA_SECRET"

# Option B: Credential registry in config
# config/sub_accounts.yml (gitignored)
sub_accounts:
  sol_ema_001:
    api_key_env: "BYBIT_SUB_SOL_EMA_KEY"
    api_secret_env: "BYBIT_SUB_SOL_EMA_SECRET"
    allocated_equity: 2000
  btc_swing_001:
    api_key_env: "BYBIT_SUB_BTC_SWING_KEY"
    api_secret_env: "BYBIT_SUB_BTC_SWING_SECRET"
    allocated_equity: 5000
```

Option B is better -- keeps secrets out of Play YAML, centralizes allocation.

### 2. ExchangeManager: Per-Play Client Instances

Currently a singleton. Needs to become one-per-Play (or one-per-sub-account).

```python
# Current: single global client
exchange = ExchangeManager(config)

# New: factory creates per-sub-account client
exchange = ExchangeManager.for_sub_account("sol_ema_001", config)
```

Each instance holds its own `BybitClient` with dedicated API keys.

### 3. Capital Allocation Tool

CLI command to move funds from master to sub-accounts:

```bash
# Allocate capital
python trade_cli.py account allocate --sub sol_ema_001 --amount 2000 --coin USDT

# Recall capital
python trade_cli.py account recall --sub sol_ema_001 --amount 500 --coin USDT

# View all allocations
python trade_cli.py account status
```

Uses `POST /v5/asset/transfer/universal-transfer` under the hood.

### 4. Multi-Runner Orchestrator (Optional)

Run all Plays concurrently from a single process or supervisor:

```bash
# Run one Play (current)
python trade_cli.py play run --play sol_ema_triple_long --mode demo

# Run all active Plays (new)
python trade_cli.py play run-all --mode demo
```

Each Play spawns its own LiveRunner with its own WebSocket connections and API keys.

### 5. Aggregate Dashboard (Optional)

Query all sub-accounts from master to show combined state:

```bash
python trade_cli.py account dashboard
```
```
Sub-Account          Play                    Equity    PnL Today   DD%    Status
sol_ema_001          sol_ema_triple_long     $2,150    +$150       0.0%   RUNNING
btc_swing_001        btc_swing_short         $4,820    -$180       3.6%   RUNNING
eth_range_001        eth_range_mean_revert   $3,045    +$45        0.0%   PAUSED
─────────────────────────────────────────────────────────────────────────
TOTAL                                        $10,015   +$15        1.8%
```

## Bybit Sub-Account API Reference

| Operation | Endpoint | pybit Method |
|-----------|----------|-------------|
| Create sub-account | `POST /v5/user/create-sub-member` | `session.create_sub_uid()` |
| Create API key | `POST /v5/user/create-sub-api` | `session.create_sub_api_key()` |
| List sub-accounts | `GET /v5/user/query-sub-members` | `session.get_sub_uid_list()` |
| Transfer funds | `POST /v5/asset/transfer/universal-transfer` | `session.create_universal_transfer()` |
| Freeze sub-account | `POST /v5/user/frozen-sub-member` | `session.freeze_sub_uid()` |
| Delete sub-account | `POST /v5/user/del-submember` | `session.delete_sub_uid()` |

## Sub-Account Limits

- **Default limit:** ~20 sub-accounts (from broker API example; regular account limit undocumented)
- **Pagination APIs exist for 10k+** sub-accounts, suggesting institutional accounts can scale high
- **No documented leverage/margin restrictions** vs main account
- **All sub-UIDs auto-enabled** for universal transfers (no manual setup)
- **Each sub-account** can have its own API keys with granular permissions

## Rate Limit Considerations

- Rate limits are **shared across main + all sub-accounts** at the UID level
- Default sub-account API rate is NOT counted in institutional-level limits
- With N Plays each running their own WebSocket + REST polling, stay under aggregate limits
- Current limits: 120 RPS public, 50 RPS private, 10 RPS orders (per UID aggregate)
- For 5 concurrent Plays, each gets effectively ~24 RPS public, ~10 RPS private, ~2 RPS orders

## Implementation Priority

1. **Phase 1:** Multi-credential config + per-Play ExchangeManager (required)
2. **Phase 2:** Capital allocation CLI tool (required)
3. **Phase 3:** Sub-account creation/management CLI (nice to have -- can do manually on Bybit)
4. **Phase 4:** Multi-runner orchestrator (nice to have)
5. **Phase 5:** Aggregate dashboard (nice to have)

## Demo Mode Limitations (IMPORTANT)

Demo trading and sub-accounts are **independent, separate concepts** on Bybit:

- **Demo account** = isolated fake-money account on `api-demo.bybit.com`
- **Sub-accounts** = real accounts under your master on `api.bybit.com`

The hierarchy:
```
Master Account (real, api.bybit.com)
  ├── Demo Account (fake money, api-demo.bybit.com)
  ├── Sub-Account A (real)
  │     └── Demo Account A (fake money)
  ├── Sub-Account B (real)
  │     └── Demo Account B (fake money)
```

**Demo API does NOT support sub-account management:**
- No `create-sub-member`, `universal-transfer`, `frozen-sub-member`, etc.
- Demo only covers: Market, Trade, Position, Account, limited Asset, WS Private
- Orders on demo expire after 7 days
- Rate limits on demo are default and not upgradable

**Consequence:** You cannot test the full multi-sub-account workflow on demo. Each sub-account CAN have its own demo account for testing individual Play trading, but the capital allocation / transfer / orchestration layer must be tested with real sub-accounts using small real capital.

**Testing strategy:**
1. Test individual Play trading logic on demo (current workflow, no changes needed)
2. Test sub-account creation + transfers + multi-runner orchestration on real with minimal capital ($10-50 per sub-account)
3. Scale up capital allocation once orchestration is validated

## Risks / Open Questions

- **Rate limit sharing** -- N concurrent Plays share one UID's rate limits. May need to throttle polling intervals or reduce WebSocket reconnect frequency
- **Sub-account limit** -- unknown for regular accounts. Need to test or ask Bybit support
- **Demo mode** -- sub-account management APIs are NOT available on demo (see above)
- **WebSocket connections** -- each sub-account needs its own private WS connection. Bybit may limit concurrent WS connections per UID
- **Credential management** -- N API key pairs means N env vars. Consider a secrets manager or encrypted config file
