# Structure Detection Audit — BTCUSDT (6 months)

**Date**: 2026-02-20
**Data**: BTCUSDT 4h/12h/D, Aug 2025 — Feb 2026 (1081/361/181 bars)
**Script**: `scripts/analysis/structure_audit.py`

## Executive Summary

The swing detection algorithm (fractal mode) is **correctly implemented** per standard definitions. Cross-TF alignment is perfect (100%). However, there are **serious downstream issues** in how trend and market structure detectors consume swing data, producing contradictory signals.

| # | Finding | Severity | Type |
|---|---------|----------|------|
| 1 | Swing fractal algorithm correct | OK | Verified |
| 2 | Cross-TF alignment: 100% | OK | Verified |
| 3 | Swing count ratios healthy | OK | Verified |
| 4 | Too many noise swings (no filters by default) | Medium | Config |
| 5 | **Trend vs Market Structure: 0% agreement** | **Critical** | Architecture |
| 6 | Default `confirmation_close=False` wrong for ICT/SMC | Medium | Config default |
| 7 | Trend never reaches strength=2 on real data | Medium | Algorithm |
| 8 | 25-30% alternation violations without filter | Low | Config |

---

## 1. Swing Detection: Correct

The fractal algorithm (`left=5, right=5`) matches the standard N-bar pivot definition:

- Uses strict inequality (`>=` rejection) — standard
- Confirmation delayed by `right` bars — correct
- Wicks used for pivot detection (high/low not close) — correct per TA canon
- ATR zigzag mode also correctly implemented

### Cross-TF Alignment: Perfect

Every Daily swing has a matching 12h and 4h swing at 0.00% price difference:

```
Daily->12h alignment: 20/20 (100%)
Daily->4h  alignment: 20/20 (100%)
12h->4h alignment:    42/42 (100%)
```

### Swing Count Ratios: Healthy

```
4h/12h: 3.2x (expected: 2-4x)  -- GOOD
4h/D:   6.8x (expected: 4-8x)  -- GOOD
12h/D:  2.1x (expected: 1.5-3x) -- GOOD
```

---

## 2. Problem: Too Many Noise Swings

With default `left=5, right=5` and no filters:

| TF | Total Swings | Bars/Swing | Alt. Violations | False Positives (20-bar window) |
|----|-------------|-----------|----------------|-------------------------------|
| 4h | 136 | 7.9 | **34 (25%)** | **40 highs (59%), 34 lows (50%)** |
| 12h | 42 | 8.6 | 3 (7%) | 11 highs (52%), 9 lows (43%) |
| D | 20 | 9.1 | **6 (30%)** | 5 highs (50%), 4 lows (40%) |

"False positive" = detected as 5-bar pivot but NOT the actual highest/lowest in a 20-bar window. These are real fractals, but not meaningful swing points — they're noise that pollutes downstream detectors.

### Parameter Sensitivity (4h)

```
Config                         | Swings | Bars/Swing | AltViol
Williams Fractal (2,2)         |    323 |        3.3 |      66
Short-term (3,3)               |    229 |        4.7 |      52
Standard (5,5)                 |    136 |        7.9 |      34
Position (8,8)                 |     76 |       14.2 |      22
Major (13,13)                  |     47 |       23.0 |       8
Std + ATR filter 0.5           |    105 |       10.3 |      33
Std + ATR filter 1.0           |     80 |       13.5 |      30
Std + strict alt               |    122 |        8.9 |      20
```

**Recommendation**: For structure detection feeding BOS/CHoCH, use `min_atr_move: 0.5` or `strict_alternation: true` (or both) to reduce noise. Without filters, the swing detector produces ~2x more pivots than are structurally meaningful.

---

## 3. CRITICAL: Trend vs Market Structure — 0% Agreement

This is the most important finding. The trend detector and market structure detector **produce contradictory signals** on real data:

| TF | CHoCH Events | Agreed with Trend | Disagreed | No Trend Change |
|----|-------------|-------------------|-----------|----------------|
| 4h | 22 | **0 (0%)** | 21 | 1 |
| 12h | 7 | **0 (0%)** | 7 | 0 |
| D | 3 | **1 (33%)** | 2 | 0 |

### Root Cause: Timing Mismatch

The two detectors operate on fundamentally different timescales:

**Market Structure** (fast, reactive):
- Fires BOS/CHoCH immediately when price breaks a swing level
- No confirmation delay beyond the bar itself
- Acts like a real-time event detector

**Trend** (slow, confirmatory):
- Waits for complete wave pairs (swing-to-swing segments) to form
- Needs 2+ waves to classify direction
- Needs 4+ waves for strength=2
- Acts like a lagging trend filter

**Result**: When a CHoCH fires saying "bearish reversal", the trend detector either:
- Still says "bullish" (hasn't seen enough waves yet) — **contradiction**
- Has moved to "ranging" (saw conflicting waves but can't confirm direction) — **weak agreement at best**
- Eventually confirms "bearish" 10-20 bars later — **too late, CHoCH already happened**

### Example (4h timeline)

```
bar 887: CHoCH bearish fires — bias flips to BEAR
bar 884: Trend was at RANGING (strength=0)
bar 893: Trend finally goes DOWN (strength=1) — 6 bars AFTER the CHoCH
```

### Why This Matters

If a play uses BOTH `trend.direction == -1` AND `market_structure.choch_this_bar` in its entry conditions, they will **almost never fire on the same bar**. The CHoCH is a leading signal; the trend is a lagging confirmation. They measure different things at different speeds.

### Possible Solutions

1. **Accept the mismatch as intentional** — treat them as complementary (CHoCH = early warning, trend = confirmation). Plays should use one OR the other, not both simultaneously.

2. **Make market structure depend on trend** — only fire CHoCH when trend direction agrees. This would make MS more conservative but avoid contradictions. (Downside: CHoCH would lose its leading-indicator quality.)

3. **Add a "pending" CHoCH** — fire CHoCH as a preliminary signal, but don't flip bias until trend confirms. This splits CHoCH into "tentative" and "confirmed" events.

4. **Speed up trend detection** — reduce the wave requirement from 2 complete waves to 1, or use a shorter swing lookback for the trend's source swing. (Downside: more noise in trend signals.)

5. **Slow down market structure** — require N consecutive bars above/below the break level before confirming BOS/CHoCH. (Downside: defeats the purpose of real-time detection.)

---

## 4. Default `confirmation_close=False` Is Wrong for ICT/SMC

Per ICT/SMC canon, a structure break requires a **candle body close** beyond the level. A wick-only breach is a **liquidity sweep**, not a structural break.

Our default `confirmation_close=False` uses wicks, producing:

| TF | Wick Events | Close Events | Extra (likely false) |
|----|------------|-------------|---------------------|
| 4h | 64 | 45 | 19 (42% more) |
| 12h | 19 | 13 | 6 (46% more) |
| D | 8 | 6 | 2 (33% more) |

**Recommendation**: Change default to `confirmation_close=True` for ICT/SMC strategies. Keep `False` available as an option for strategies that intentionally use wick breaks.

---

## 5. Trend Never Reaches strength=2

On 4h: 53 trend changes over 6 months. Every single one is `strength=0` (ranging) or `strength=1` (normal). **Zero** instances of `strength=2` (strong trend).

This means the wave-pair comparison in `_classify_trend()` never finds 2+ consecutive pairs confirming the same direction. The trend oscillates rapidly: UP -> RANGING -> DOWN -> RANGING -> UP...

On 12h and D: same pattern. No strength=2 ever achieved.

**Root cause**: The 4-wave deque is too short, and BTC's volatility means wave pairs frequently alternate direction before 2 consecutive same-direction pairs can form.

**Impact**: Any play condition checking `trend.strength >= 2` will NEVER fire on real BTC data with default params.

---

## 6. Wick vs Close: Swing Detection vs Structure Breaks

Research confirms the industry standard:

| Component | Should Use | Our Code |
|-----------|-----------|----------|
| Swing detection (pivot identification) | **Wicks** (high/low) | Correct |
| BOS/CHoCH (structure breaks) | **Body close** | Default wrong (`False`) |
| Stop loss placement | Beyond wick extreme | N/A (sim handles) |

---

## 7. Reference: What Correct Detection Looks Like

### Swing Detection Algorithm (Verified Correct)

Our fractal mode matches the standard definition exactly:
- Window = `left + right + 1` bars
- Pivot must be strictly greater/less than ALL neighbors
- Confirmation delayed by `right` bars
- Equal values disqualify (strict inequality)

### BOS/CHoCH State Machine (Verified Correct)

```
RANGING + break above swing high  -> BULLISH (BOS)
RANGING + break below swing low   -> BEARISH (BOS)
BULLISH + break above swing high  -> BULLISH (BOS continuation)
BULLISH + break below swing low   -> BEARISH (CHoCH reversal)
BEARISH + break below swing low   -> BEARISH (BOS continuation)
BEARISH + break above swing high  -> BULLISH (CHoCH reversal)
```

Our implementation matches. CHoCH correctly supersedes BOS on same bar.

### One Subtle Gap: CHoCH Should Break the BOS-Producing Swing

Strict ICT rule: CHoCH is only valid when price breaks "the swing that produced the last BOS." Our code uses `_prev_swing_high/low` (most recent swing), which is usually the same but can diverge in complex multi-swing structures. This is a minor correctness issue, not a critical bug.

---

## 8. Recommendations (Prioritized)

### Must Address Before Live Trading

1. **Document the trend/MS timing mismatch** — plays must not expect both to agree on the same bar. Add guidance to PLAY_DSL_REFERENCE.md.
2. **Change `confirmation_close` default to `True`** — or at minimum, ensure all ICT/SMC plays explicitly set it.

### Should Address

3. **Recommend `min_atr_move: 0.5` or `strict_alternation: true`** in play templates that use structure detection.
4. **Investigate why strength=2 never fires** — consider reducing the requirement or increasing wave history.

### Nice to Have

5. **Add CHoCH "which swing was broken" tracking** — store the swing that produced the last BOS, compare against it for CHoCH validation.
6. **Consider a unified "structure bias" output** that combines trend + MS into a single coherent signal.

---

## Appendix: Key Data Points

### BTC Price Context (Aug 2025 — Feb 2026)

- Aug 2025: ~$108k-113k (ranging)
- Sep 2025: ~$108k-118k (range with brief breakout)
- Oct 2025: $101k-126k (volatile, peaked at $126k on Oct 6)
- Nov 2025: $80k-116k (crash to $80k on Nov 21)
- Dec 2025: $84k-94k (range-bound recovery)
- Jan 2026: $86k-98k (range, then breakdown)
- Feb 2026: $59k-72k (major crash to $59k on Feb 6)

### Market Structure Timeline (Daily, close-based)

```
Oct 1:  BOS bullish  @ $117,884 -> BULL
Nov 4:  CHoCH bearish @ $103,437 -> BEAR
Nov 14: BOS bearish  @ $98,888  -> BEAR
Jan 3:  CHoCH bullish @ $90,589  -> BULL
Jan 13: BOS bullish  @ $94,750  -> BULL
Jan 30: CHoCH bearish @ $84,408  -> BEAR (current)
```

This daily structure timeline looks reasonable for the price action described above.

---

## Files

- Audit script: `scripts/analysis/structure_audit.py`
- This document: `docs/STRUCTURE_DETECTION_AUDIT.md`
- Structure detectors: `src/structures/detectors/`
- Base class: `src/structures/base.py`
