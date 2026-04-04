# Deployment Guide

> Production deployment strategy for TRADE on Hostinger VPS (KVM 2).
> Written 2026-03-28. Revisit when building the browser dashboard.

## Infrastructure

**VPS:** Hostinger KVM 2 — 2 vCPU, 8GB RAM, 100GB NVMe, Ubuntu 24.04
**Pre-installed:** Docker, Traefik (auto-SSL, reverse proxy, WS support)
**Coexists with:** OpenClaw (AI assistant, ~1.5GB RAM)
**Available for TRADE:** ~6GB RAM, 67GB disk

## Architecture

```
Internet
  |
  Traefik (already running, auto-SSL via Let's Encrypt)
  |
  +-- openclaw container        (~1.5GB) -- existing
  +-- trade-api container       (~300MB) -- FastAPI dashboard + REST + WebSocket
  +-- trade-shadow container    (~500MB) -- ShadowDaemon + N engines
  |
  /data/ volume (persistent)
  +-- shadow/shadow_performance.duckdb
  +-- shadow/state/orchestrator.state.json
  +-- shadow/{instance_id}/events.jsonl
  +-- backtest_results/
  +-- journal/
  +-- runtime/instances/
```

Traefik routes by domain:
- `openclaw.yourdomain.com` -> OpenClaw
- `trade.yourdomain.com` -> trade-api (dashboard + API)

## Resource Budget

| Component | RAM | Notes |
|-----------|-----|-------|
| OS + Docker + Traefik | ~500MB | Already running |
| OpenClaw | ~1.5GB | Already running |
| trade-api (FastAPI + uvicorn) | ~300MB | Stateless, restart freely |
| trade-shadow (daemon + 5 engines) | ~500MB | Stateful, careful restarts |
| trade-shadow (20 engines) | ~1.5GB | ~50MB per engine |
| DuckDB queries | ~200-500MB | Spikes during reads |
| **Total (20 engines + API)** | **~4.5GB** | **~3.5GB headroom** |

## Docker Compose Structure

```yaml
services:
  trade-api:
    build: .
    command: uvicorn src.api.main:app --host 0.0.0.0 --port 8000
    volumes:
      - ./data:/app/data
      - ./plays:/app/plays
      - ./backtests:/app/backtests
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.trade.rule=Host(`trade.yourdomain.com`)"
      - "traefik.http.routers.trade.tls.certresolver=letsencrypt"
    restart: unless-stopped

  trade-shadow:
    build: .
    command: python -m src.shadow.daemon --config config/shadow.yml
    volumes:
      - ./data:/app/data
      - ./plays:/app/plays
    restart: unless-stopped
    # No Traefik labels -- not exposed to internet
```

## Git Workflow

```
YOUR LAPTOP (develop)       GITHUB (truth)          YOUR VPS (run)
-------------------         --------------          ---------------
Write code                  Stores everything       Runs the bot
Run backtests               Tracks history          Shadow engines
Validate plays              Never loses work        Dashboard
      |                           |                       |
      +---- git push ----------->-+                       |
                                  +------ git pull ------>-+
```

### Branches

| Branch | Rule | Who uses it |
|--------|------|-------------|
| `main` | Always works. VPS runs this. | VPS pulls from main |
| `feature/*` | Sandbox. Break things freely. | Laptop only |

### Daily workflow

```bash
# Laptop: develop on feature branch
git checkout -b feature/my-change
# ... write code, test, validate ...
git add <files>
git commit -m "feat: description"

# Laptop: merge to main when ready
git checkout main
git merge feature/my-change
git push

# VPS: update (SSH in)
cd TRADE && git pull
docker-compose up -d --build trade-api        # safe, any time
docker-compose up -d --build trade-shadow      # careful, see below
```

## The Restart Problem

Shadow engines are stateful. Restarting the container resets engine state.

### What survives a restart

| State | Graceful | Crash |
|-------|----------|-------|
| Completed trades (DuckDB) | YES | YES (if flushed) |
| Equity snapshots (DuckDB) | YES | YES (if flushed) |
| Instance ID + config | YES | YES (state file) |
| Journal audit trail | YES | YES (flushed per event) |
| **Open positions** | **LOST** | **LOST** |
| **Pending orders** | **LOST** | **LOST** |
| **Signal/indicator state** | **LOST** | **LOST** |
| **Unflushed buffer (~60s)** | Flushed | **LOST** |

### Current behavior on restart

1. Daemon saves instance configs to `orchestrator.state.json` (atomic write)
2. Orchestrator flushes all DB buffers
3. On startup, daemon restores configs and recreates engines
4. Engines warm up indicators from DuckDB/REST data
5. Open positions are NOT restored -- engines start flat

### Update strategies

**Strategy A: Maintenance window (use now)**

```bash
# 1. Check no critical positions open (via dashboard or CLI)
# 2. Graceful stop (flushes DB, saves state)
docker-compose stop trade-shadow
# 3. Pull + rebuild
git pull
docker-compose up -d --build trade-shadow
# 4. Engines restart, warm up (~2min), resume
```

Good enough for paper-trading. Losing a shadow position mid-trade costs data, not money.

**Strategy B: Position checkpoint (build before live trading)**

Extend save/restore to include open position state:

```
On shutdown (extend _save_state):
  1. Save instance config           -- already done
  2. Flush DB buffers               -- already done
  3. Save open position state       -- NEW: price, size, side, SL, TP
  4. Save SimExchange ledger state  -- NEW: cash, equity, margin

On startup (extend _restore_state):
  1. Restore instance config        -- already done
  2. Warm up indicators             -- already done
  3. Inject position into SimExchange -- NEW
  4. Resume signal evaluation        -- automatic
```

~100 lines of code. SimExchange state is already dataclass fields.

**Strategy C: Hot code reload (future, complex)**

SIGHUP already reloads config (add/remove plays). Extending to reload
strategy logic without restarting engines is possible but non-trivial.

### Which strategy when

| Phase | Strategy | When |
|-------|----------|------|
| Shadow paper-trading | A (maintenance window) | Now |
| Pre-live deployment | B (position checkpoint) | Before real money |
| Mature production | C (hot reload) | When A/B feel limiting |

## Separated Container Updates

The key insight: **API and shadow are separate containers.**

| Action | Command | Shadow engines affected? |
|--------|---------|------------------------|
| Update dashboard/API | `docker-compose up -d --build trade-api` | NO -- untouched |
| Update play YAML files | `git pull` (no rebuild needed) | NO -- read on next engine start |
| Update shadow engine code | `docker-compose up -d --build trade-shadow` | YES -- restart required |
| Update indicators/structures | `docker-compose up -d --build trade-shadow` | YES -- restart required |
| Add new shadow play | SIGHUP or config reload | NO -- hot-add supported |
| Remove shadow play | SIGHUP or config reload | Only removed engine |

## API Layer (to be built)

FastAPI wrapping existing data surfaces:

| Endpoint | Source | Notes |
|----------|--------|-------|
| `GET /api/shadow/instances` | ShadowPerformanceDB | List all engines + status |
| `GET /api/shadow/{id}/equity` | `get_equity_curve()` | Timestamped equity series |
| `GET /api/shadow/{id}/trades` | `get_trades()` | Trade history |
| `GET /api/shadow/leaderboard` | `get_leaderboard()` | Ranked by performance |
| `GET /api/backtest/{run_hash}` | `result.json` artifact | 76-field summary |
| `GET /api/backtest/{run_hash}/trades` | `trades.parquet` | Trade-by-trade data |
| `GET /api/backtest/{run_hash}/equity` | `equity.parquet` | Equity curve |
| `GET /api/data/{symbol}/{tf}` | DuckDB historical | OHLCV for charting |
| `GET /api/instances` | EngineManager | Running live instances |
| `WS /ws/shadow` | Orchestrator callbacks | Real-time equity + trade stream |

All data surfaces already exist with `.to_dict()` or query methods.
The API layer is thin -- mostly wrapping existing functions behind HTTP.

## Frontend (to be built)

Priority pages:

1. **Shadow dashboard** -- multi-engine equity curves, trade feed, leaderboard
2. **Backtest viewer** -- OHLCV chart with trade overlays, metrics summary
3. **Instance manager** -- start/stop engines, view positions
4. **Structure visualizer** -- extend `market-structure-explorer.html` prototype

## Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default command (overridden in docker-compose per service)
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## First Deployment Checklist

- [ ] Push to GitHub (private repo)
- [ ] SSH into VPS, `git clone`
- [ ] Create `.env` with Bybit API keys
- [ ] Create `config/shadow.yml` with play configs
- [ ] `docker-compose up -d`
- [ ] Verify Traefik routes to dashboard
- [ ] Start shadow engines via config
- [ ] Verify DuckDB data persists across container restarts

## Security Notes

- `.env` with API keys must NOT be in git (already in `.gitignore`)
- Bybit API keys should have IP whitelist set to VPS IP
- Shadow engines are paper-trading -- no real money at risk
- Traefik handles SSL automatically (Let's Encrypt)
- trade-shadow container has no Traefik labels (not exposed to internet)
- DuckDB files in persistent volume survive container rebuilds
