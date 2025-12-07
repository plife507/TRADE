# Brainstorming Notes: Agentic Trading Research Factory

## 1. Vision

Build a **research factory** where AI/agents:

- Read trading books and resources.
- Extract and formalize trading ideas into reusable components.
- Combine components into candidate systems.
- Test those systems via:
  - Offline backtesting.
  - Daily demo trading.
- Gradually promote successful systems to **low-risk live trading**.
- Scale capital only after live performance is proven.

Key principle:  
The whole pipeline is **continuous and supervised**. Agents propose, test, and analyze, but **hard-coded risk rules** and human oversight guard real capital.

---

## 2. Core Concept

Break the system into four persistent tracks:

1. **Knowledge Track** – Books/resources → structured knowledge (concept KB).
2. **Idea Track** – Knowledge → candidate strategy modules and full systems.
3. **Simulation/Demo Track** – Backtests + demo trading to validate ideas.
4. **Live Track** – Only the best, most stable systems trade with real money, with staged capital scaling.

Everything is stored as **JSON-like documents** in a database (MongoDB or similar) and connected through **status transitions** (candidate → demo → live_test → production).

RAG (Retrieval-Augmented Generation) is used to pull relevant knowledge and modules when designing or refining systems, but **never to look into the future**.

---

## 3. Track 1 – Knowledge: Books → Concept KB

### Inputs

- Trading books, PDFs, articles, notes:
  - Price action
  - Order flow
  - Risk management
  - System design
  - Game theory, etc.

### Process

1. **Ingestion + Chunking**
   - Split books/resources into text chunks.
   - Embed each chunk and store in a `kb_segments` collection (or vector DB).
   - Each segment has:
     - `source` (book, chapter, page)
     - `text`
     - `tags` (e.g., trend-following, OB, volatility)
     - `embedding`

2. **Concept Extraction (LLM Agents)**
   - Agents run prompts over groups of chunks to extract **concept cards**:
     - Name / label
     - Description
     - Typical timeframes (HTF/MTF/LTF)
     - Setup conditions
     - Entry/exit ideas
     - Risk constraints
   - Output structured JSON, stored as documents like `kb_concepts`.

3. **Module Proposal**
   - A second agent reads `kb_concepts` and proposes **strategy modules**:
     - Entry modules
     - Exit modules
     - Filters (session, volatility, trend)
     - Risk modules (position sizing, max DD rules)
   - Each module:
     - Has a **config schema** (fields, ranges, enums).
     - Links back to underlying concepts (traceability).
     - Gets its own `embedding` to make it retrievable via vector search.

### Output

- A structured **knowledge base** containing:
  - Concept cards
  - Module prototypes
  - Clear mapping from “book idea” → “machine-usable component”

---

## 4. Track 2 – Ideas: Modules → Candidate Systems

Agents operate like system designers using LEGO blocks.

### Inputs

- `kb_concepts` – conceptual definitions.
- `modules` – atomic building blocks with config schemas.
- Design goals (e.g., “BTC intraday,” “multi-asset swing,” “mean reversion only”).

### Process

1. **RAG for Design Context**
   - Agent queries the KB via vector search:
     - “Show me modules and concepts relevant to intraday BTC price action, HTF trend, LTF order blocks, and tight risk.”
   - Retrieves:
     - Applicable concepts.
     - Candidate modules (entries, exits, filters, risk).

2. **System Assembly**
   - Agent builds a **system config**:
     - Reference to selected modules:
       - `entry`, `exit`, `filters`, `risk`, `management`.
     - Timeframe mapping:
       - H (HTF), M (MTF), L (LTF) lists.
     - Parameter guesses (inside module config constraints).
   - Stored in a `systems` collection with:
     - `status: "candidate"`
     - `system_id`
     - Description + reasoning notes (human-readable).

3. **Sanity Checks**
   - Lightweight validation pipeline:
     - Ensure all module references exist.
     - Check parameter ranges.
     - Verify timeframes are consistent.

### Output

- A growing library of **candidate systems**:
  - All defined in a uniform JSON schema.
  - All traceable back to conceptual sources (books, modules, concepts).

---

## 5. Track 3 – Simulation & Demo: Backtesting + Daily Demo Trading

Two layers of real-world evaluation before any real capital.

### 5.1 Offline Backtesting

For each `system` with `status: "candidate"`:

1. **Historical Data Pull**
   - Fetch necessary OHLCV/volume/other features from the historical data store.
   - Strictly enforce no lookahead in feature construction.

2. **Simulation Engine**
   - Run backtests over multiple regimes/time windows.
   - Produce metrics:
     - Win rate, expectancy, Sharpe
     - Max drawdown, worst stagnation period
     - Trade count, average holding time

3. **Result Storage**
   - Save results in `backtests` collection linked to `system_id`.
   - Possibly store per-trade logs for deeper diagnostics.

4. **Promotion Rules to Demo**
   - Example thresholds:
     - Minimum number of trades.
     - Max DD below a limit.
     - Positive expectancy + robust behavior across multiple periods.
   - If passed → system moves to `status: "demo"`.

### 5.2 Demo Trading (Bybit DEMO)

For systems in `status: "demo"`:

1. **Live Demo Runner**
   - Connects to DEMO trading environment.
   - Executes trades according to the system logic and parameters.
   - Logs every decision:
     - Features at decision time
     - Forecast (expected outcome)
     - Actual trade details.

2. **Daily/Periodic Evaluation**
   - Compute forward metrics:
     - Live demo PnL
     - Hit rate vs backtest expectations
     - Slippage and execution issues
   - Compare to config and backtest results.

3. **Automatic Demotion / Disable**
   - If demo performance is bad or unstable:
     - `status: "disabled"` or `status: "rework_required"`.

4. **Promotion to Live Test**
   - If demo performance is consistent and robust:
     - Promote to `status: "live_test"` (small real capital).

### Output

- A filter that ensures **only systems with both backtest and demo evidence** move toward real capital.

---

## 6. Track 4 – Live: Staged Capital Deployment

Two “tiers” of live capital exposure.

### 6.1 Live Test (Tiny Real Capital)

Systems with `status: "live_test"`:

- Same logic as demo, but:
  - Run on real exchange accounts.
  - Tight capital and risk limits:
    - Low notional per trade.
    - Strict max daily loss.
    - Global kill switch for the group.

Daily/weekly logic:

- Evaluate:
  - Live results vs demo vs backtest.
  - Stability under real-world slippage, latency, and liquidation risks.
- Outcomes:
  - If underperforming: demote back to demo or disable.
  - If consistent: consider promotion.

### 6.2 Production (Scaled Capital)

Systems that pass live_test:

- `status: "production"`.
- Risk engine:
  - Allocates capital among production systems based on:
    - Rolling Sharpe
    - Max DD
    - Correlation between systems (avoid stacking similar risk)
- Risk controls:
  - Per-system risk caps.
  - Global portfolio risk caps.
  - Hard rule: **no agent can bypass or modify risk caps**.

---

## 7. Learning & Feedback Loops

The system improves over time by turning **experience** into **data**.

### 7.1 Forecast-Level Logging

At each decision time:

- Log a `forecast` document:
  - Snapshot of features and regime classification.
  - System + modules used.
  - Probabilistic expectations (if used).
  - Actual action (enter/hold/exit/skip).

Later, after the outcome horizon:

- Compute realized outcomes:
  - PnL, max adverse excursion, realized volatility.
- Attach metrics:
  - Forecast error
  - Brier scores (if probabilities)
  - Risk-adjusted returns

### 7.2 Model & System Evolution

Using these logs:

- Train/update statistical or ML models to:
  - Improve entry/exit filters.
  - Adjust parameters to match regime.
- Evaluate modules:
  - Some entries/exits may systematically underperform.
  - Some risk modules may be too aggressive or too conservative.

Agents can:

- Suggest:
  - Parameter shifts.
  - Swapping or disabling weak modules.
  - New systems built from better components.
- But **promotion/demotion rules remain deterministic**, based on numeric metrics.

---

## 8. Role of RAG and Agents

RAG and agents are primarily used for:

- **Knowledge extraction** from books and resources.
- **Module and system design** using structured knowledge and concept tags.
- **Narrative analysis** of results:
  - Writing post-mortems and explanations.
  - Suggesting new experiments or variants.

They are **not** trusted to:

- Bypass risk rules.
- Directly grant capital to untested systems.
- Change core engine or risk caps without human-in-the-loop decisions.

RAG is always anchored on:

- The KB (concepts, rules, scenarios).
- The historical performance logs and metrics.
- Clear schemas that enforce what a valid module/system looks like.

---

## 9. Implementation Roadmap (High-Level)

1. **Schema design**
   - Define JSON structures for:
     - `kb_segments`, `kb_concepts`
     - `modules`
     - `systems` (with status field)
     - `backtests`
     - `forecasts`
   - Keep them small and consistent.

2. **Knowledge ingestion**
   - Set up pipeline to chunk and embed books.
   - Build first concept cards and basic modules manually + with LLM help.

3. **Simple backtester + one data source**
   - Implement minimal backtest engine (no fancy stuff) for 1–2 symbols and TFs.
   - Integrate with `systems` configs.

4. **Demo trading**
   - Connect DEMO trading.
   - Run 1–2 candidate systems with tiny demo capital.

5. **Live test + production**
   - Introduce `live_test` with strict risk.
   - Promote only after backtest + demo evidence.
   - Build a capital allocator for production systems.

6. **Iterative improvement**
   - Add more systems, symbols, and modules.
   - Add better regime detection and learning loops.
   - Expand KB and concept coverage over time.

---

## 10. Key Design Principles

- **No lookahead**: all decisions must be based only on past and current data at that timestamp.
- **Guardrails first**: risk limits and promotion rules are code, not LLM opinions.
- **Separation of concerns**:
  - KB + RAG for **ideas and explanations**.
  - Deterministic engines for **execution and risk**.
- **Staged exposure**:
  - Candidate → Backtest → Demo → Live test → Production.
- **Continuous learning**:
  - Every forecast and trade is data.
  - Systems are promoted or demoted based on measured performance, not vibes.

This document is a brainstorming foundation, not a locked specification. The next step is to define the **actual field lists** for `systems`, `modules`, and `backtests` in a way that works with the data and tools you already have.
