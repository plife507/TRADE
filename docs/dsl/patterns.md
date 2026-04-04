# Synthetic Patterns & Validation

Every play MUST have a `validation:` block. Required for `--synthetic` backtest.

## Declaration

```yaml
validation:
  pattern: "trend_up_clean"
```

The parser reads `validation:` with a `pattern` field. Bars are auto-computed from warmup.
CLI overrides: `--synthetic-bars`, `--synthetic-seed`, `--synthetic-pattern`.

## Pattern catalog (38 patterns)

| Category | Patterns |
|----------|----------|
| Trend (6) | `trend_up_clean`, `trend_down_clean`, `trend_grinding`, `trend_parabolic`, `trend_exhaustion`, `trend_stairs` |
| Range (4) | `range_tight`, `range_wide`, `range_ascending`, `range_descending` |
| Reversal (4) | `reversal_v_bottom`, `reversal_v_top`, `reversal_double_bottom`, `reversal_double_top` |
| Breakout (3) | `breakout_clean`, `breakout_false`, `breakout_retest` |
| Volatility (4) | `vol_squeeze_expand`, `vol_spike_recover`, `vol_spike_continue`, `vol_decay` |
| Liquidity (5) | `liquidity_hunt_lows`, `liquidity_hunt_highs`, `choppy_whipsaw`, `accumulation`, `distribution` |
| Multi-TF (4) | `mtf_aligned_bull`, `mtf_aligned_bear`, `mtf_pullback_bull`, `mtf_pullback_bear` |
| ICT (4) | `displacement_impulse`, `trending_with_gaps`, `equal_highs_lows`, `ob_retest` |
| Legacy (4) | `trending`, `ranging`, `volatile`, `multi_tf_aligned` |

## Strategy-to-pattern mapping

| Strategy concept | Long patterns | Short patterns |
|-----------------|---------------|----------------|
| Trend following | `trend_up_clean`, `trend_stairs` | `trend_down_clean` |
| Mean reversion | `range_wide`, `range_tight`, `vol_squeeze_expand` | same |
| Breakout | `breakout_clean`, `breakout_retest` | same |
| Scalping | `range_tight`, `range_wide`, `choppy_whipsaw` | same |
| Range trading | `range_tight`, `range_wide`, `range_ascending` | same |
| ICT/structure | `liquidity_hunt_lows`, `accumulation`, `mtf_aligned_bull` | `liquidity_hunt_highs`, `distribution`, `mtf_aligned_bear` |

## Validation commands

```bash
python trade_cli.py backtest run --play X --synthetic    # Smoke test
python trade_cli.py validate quick                       # 5 core plays
python trade_cli.py validate standard                    # Core + audits
python trade_cli.py validate full                        # 229-play suite
```

## Multi-TF bar dilation warning

3 TFs with `bars_per_tf=500` generates ~48000 bars on lowest TF. Patterns get diluted ~96x.
Use `near_pct` instead of strict `<`/`>` for structure levels on synthetic data.
