# IdeaCard Risk Configuration Integration

**Date**: December 17, 2025  
**Type**: Architectural Guidance  
**Scope**: Simulation configuration, Risk/Account data flow, IdeaCard-native transition  
**Status**: Planning / Implementation Guidance

---

## Executive Summary

This document outlines the configuration and architectural changes required to make the **IdeaCard** the single source of truth for all simulation variables, specifically focusing on risk and account parameters (capital, leverage, fees, and sizing).

The goal is to eliminate hard-coded defaults in the backtest engine and ensure that every simulation run is strictly driven by the declarations in the strategy's IdeaCard YAML.

---

## Key Configuration Principles

### 1. IdeaCard as the "System Manifest"
The IdeaCard is not just a strategy script; it is a complete environment specification. Every variable that affects the ledger (starting equity, leverage limits, fees) or execution (minimum trade size, slippage) must be explicitly declared in the `account` and `risk_model` sections.

### 2. No Implicit Defaults (Fail Loud)
The system is designed to "Fail Loud" if required configuration is missing. This prevents simulations from running with hidden assumptions that could skew results.

---

## Implementation Guidance

### A. IdeaCard YAML Configuration
Ensure your `configs/idea_cards/*.yml` file contains the following required sections:

```yaml
# -----------------------------------------------------------------------------
# ACCOUNT CONFIG (Required)
# -----------------------------------------------------------------------------
account:
  starting_equity_usdt: 10000.0           # Starting capital in USDT
  max_leverage: 3.0                       # Maximum allowed leverage
  margin_mode: "isolated_usdt"            # Only "isolated_usdt" supported
  min_trade_notional_usdt: 10.0           # Minimum trade size in USDT
  fee_model:
    taker_bps: 6.0                        # Taker fee in basis points (0.06%)
    maker_bps: 2.0                        # Maker fee in basis points (0.02%)
  slippage_bps: 2.0                       # Expected slippage in basis points

# -----------------------------------------------------------------------------
# RISK MODEL (Required)
# -----------------------------------------------------------------------------
risk_model:
  stop_loss:
    type: "percent"
    value: 2.0
  sizing:
    model: "percent_equity"
    value: 1.0                            # 1% of equity per trade
```

### B. Current Adapter Layer
Currently, the integration is handled by the `IdeaCardEngineWrapper` in `src/backtest/runner.py`. This bridge extracts values from the IdeaCard and maps them to the `SystemConfig` required by the `BacktestEngine`:

```python
# From src/backtest/runner.py:156+
initial_equity = idea_card.account.starting_equity_usdt
max_leverage = idea_card.account.max_leverage

# Mapping to RiskProfileConfig
risk_profile = RiskProfileConfig(
    initial_equity=initial_equity,
    max_leverage=max_leverage,
    # ... other fields mapped from idea_card.account and idea_card.risk_model
)
```

### C. Final Architectural Goal
To fully achieve the "no hard-coded" goal, the `BacktestEngine` must be refactored to natively accept an `IdeaCard` instead of the legacy `SystemConfig`.

**Target State in `src/backtest/engine.py`**:
```python
class BacktestEngine:
    def __init__(self, idea_card: IdeaCard, ...):
        # Initialize components directly from IdeaCard
        self._exchange = SimulatedExchange(
            symbol=idea_card.symbol_universe[0],
            initial_capital=idea_card.account.starting_equity_usdt,
            risk_profile=idea_card.account,
            # ...
        )
        self.risk_manager = SimulatedRiskManager(idea_card.risk_model)
```

---

## Key Code Locations

| Component | File | Responsibility |
|-----------|------|----------------|
| **Data Structure** | `src/backtest/idea_card.py` | Defines `AccountConfig` and `RiskModel` classes. |
| **Bridge/Runner** | `src/backtest/runner.py` | Extracts IdeaCard values for the current engine implementation. |
| **Simulated Exchange** | `src/backtest/sim/exchange.py` | Applies `initial_capital`, `leverage`, and `fee_rate` to the ledger. |
| **Risk Manager** | `src/backtest/simulated_risk_manager.py` | Computes `size_usdt` based on IdeaCard sizing rules. |

---

## Recommendations

1. **Explicit Sizing**: Always define a `risk_model.sizing` section in your IdeaCard to avoid the engine falling back to a "fixed_notional" model.
2. **Min Notional**: Use `account.min_trade_notional_usdt` to ensure the simulation rejects trades that would be too small to execute on a real exchange.
3. **Deprecate SystemConfig**: New development should prioritize making the engine accept `IdeaCard` natively, eventually removing the `IdeaCardSystemConfig` adapter.

---

**Document Version**: 1.0  
**Last Updated**: December 17, 2025  
**Status**: Guidance Only

