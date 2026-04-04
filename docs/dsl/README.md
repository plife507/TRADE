# Play DSL Playbook

Modular reference for writing Play YAML files. Load only what you need.

| Module | When to load | Tokens |
|--------|-------------|--------|
| [skeleton](skeleton.md) | Always — play structure, timeframes, account | ~800 |
| [indicators](indicators.md) | Always — 47 indicators, params, naming | ~600 |
| [structures](structures.md) | Structure-based strategies — all 13 types | ~1200 |
| [conditions](conditions.md) | Always — operators, logic, setups, windows | ~700 |
| [risk](risk.md) | Always — SL/TP, trailing, sizing, entries | ~500 |
| [patterns](patterns.md) | Validation — synthetic patterns, expected | ~300 |
| [pitfalls](pitfalls.md) | Always — critical mistakes to avoid | ~300 |
| [recipes](recipes.md) | Examples — complete plays by concept | ~800 |

**Minimum set for simple plays:** skeleton + indicators + conditions + risk + pitfalls
**Full set for ICT/structure plays:** all modules

DSL semantics frozen 2026-01-08. Validated by 229 synthetic + 61 real-data plays.
