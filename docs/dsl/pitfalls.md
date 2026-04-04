# Pitfalls

Critical mistakes that cause silent failures (zero trades, wrong behavior).

## near_pct is a PERCENTAGE

```yaml
# WRONG: 0.03 = 0.03% = almost never matches
- ["close", "near_pct", "fib.level[0.618]", 0.03]
# CORRECT: 3 = 3%
- ["close", "near_pct", "fib.level[0.618]", 3]
```

## Never == on floats

```yaml
# WRONG: exact float equality almost never true
- ["close", "==", "fib.level[0.618]"]
# CORRECT: use proximity
- ["close", "near_pct", "fib.level[0.618]", 0.5]
```

## PSAR parameter names

```yaml
# WRONG: silently ignored, falls back to defaults
params: { af_start: 0.02, af_max: 0.2 }
# CORRECT:
params: { af0: 0.02, af: 0.02, max_af: 0.2 }
```

## Impossible conditions (zero trades)

```yaml
# Donchian upper >= close by definition — always false
- ["close", ">", "donchian_20.upper"]

# RSI bounds are [0,100]
- ["rsi_14", ">", 120]

# Strict comparison against structure levels — use near_pct instead
- ["close", "==", "swing.high_level"]
```

## Structure dependencies must be ordered

```yaml
# WRONG: trend before swing
structures:
  exec:
    - type: trend          # ERROR: swing not yet defined
      key: trend
      uses: swing
    - type: swing
      key: swing
      params: { left: 5, right: 5 }

# CORRECT: swing first, then trend
structures:
  exec:
    - type: swing
      key: swing
      params: { left: 5, right: 5 }
    - type: trend
      key: trend
      uses: swing
```

## Trend-wave vs paired anchors

`use_trend_anchor: true` requires `use_paired_anchor: false`. They are mutually exclusive.
`use_trend_anchor: true` also requires `uses: [swing, trend]`.

## Fib level key format

`:g` strips trailing zeros: ratio `1.0` → key `level_1` (not `level_1.0`).
Use bracket syntax to avoid confusion: `fib.level[1]`.

## exec is a pointer

```yaml
# WRONG:
exec: "15m"
# CORRECT:
exec: "low_tf"
```

## Feature naming

```yaml
# WRONG: hides parameters
ema_fast: { indicator: ema, params: { length: 9 } }
# CORRECT: encode parameters
ema_9: { indicator: ema, params: { length: 9 } }
```

## Missing validation block

Every play MUST have `validation:` with `pattern`. Without it, `--synthetic` fails.

## Exit mode matters

- `sl_tp_only`: signal exit conditions are **completely ignored**
- `signal`: SL/TP only fire as emergency backstops
- `first_hit`: whichever fires first wins
- If you define `exit_long` conditions, use `signal` or `first_hit` — not `sl_tp_only`

## Boolean 1/0 vs true/false

Structure BOOL outputs use `1`/`0` integers, not YAML true/false:
```yaml
# CORRECT:
- ["ms.bos_this_bar", "==", 1]
# WRONG:
- ["ms.bos_this_bar", "==", true]
```
