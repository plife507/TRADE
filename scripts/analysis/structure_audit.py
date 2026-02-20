"""
Structure Detection Audit Script
=================================
Runs swing, trend, and market structure detectors on real BTC data
across 4h, 12h, and D timeframes. Produces a detailed analysis of
whether the detection is correct and consistent across timeframes.

This is a READ-ONLY analysis - does NOT modify any bot code.
"""
# pyright: reportCallIssue=false, reportArgumentType=false

import sys
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.data.historical_data_store import HistoricalDataStore
from src.structures.detectors.swing import IncrementalSwing
from src.structures.detectors.trend import IncrementalTrend
from src.structures.detectors.market_structure import IncrementalMarketStructure
from src.structures.base import BarData
from src.indicators.incremental.core import IncrementalATR


# ─────────────────────────────────────────────────────────
# Data Loading
# ─────────────────────────────────────────────────────────

def load_btc_data(tf: str, period: str = "6M") -> pd.DataFrame:
    """Load BTC OHLCV data from DuckDB."""
    store = HistoricalDataStore(env="live")
    df = store.get_ohlcv("BTCUSDT", tf, period=period)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


# ─────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────

@dataclass
class SwingPoint:
    idx: int
    timestamp: str
    level: float
    swing_type: str  # "high" or "low"
    significance: float
    is_major: bool


@dataclass
class StructureEvent:
    idx: int
    timestamp: str
    event_type: str  # "bos" or "choch"
    direction: str
    level: float
    bias_after: int


@dataclass
class TrendChange:
    idx: int
    timestamp: str
    direction: int
    strength: int
    wave_count: int


# ─────────────────────────────────────────────────────────
# Harness functions
# ─────────────────────────────────────────────────────────

def compute_atr_series(df: pd.DataFrame, length: int = 14) -> list[float]:
    """Compute ATR incrementally for the data."""
    atr = IncrementalATR(length=length)
    values: list[float] = []
    for idx in range(len(df)):
        row = df.iloc[idx]
        atr.update(float(row["high"]), float(row["low"]), float(row["close"]))
        values.append(atr.value if atr.is_ready else float("nan"))
    return values


def _make_bar(idx: int, row: Any, atr_val: float) -> BarData:
    return BarData(
        idx=idx,
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
        indicators={"atr": atr_val},
    )


def run_swing_detection(
    df: pd.DataFrame,
    atr_values: list[float],
    left: int = 5,
    right: int = 5,
    min_atr_move: float = 0.0,
    strict_alternation: bool = False,
) -> list[SwingPoint]:
    """Run swing detector on data, return list of swing points."""
    params: dict[str, Any] = {
        "left": left,
        "right": right,
        "atr_key": "atr",
        "major_threshold": 1.5,
    }
    if min_atr_move > 0:
        params["min_atr_move"] = min_atr_move
    if strict_alternation:
        params["strict_alternation"] = True

    swing = IncrementalSwing(params=params, deps={})
    swings: list[SwingPoint] = []

    prev_high_version = 0
    prev_low_version = 0

    for i in range(len(df)):
        row = df.iloc[i]
        bar = _make_bar(i, row, atr_values[i])
        swing.update(i, bar)

        high_ver = int(swing.get_value("high_version"))
        low_ver = int(swing.get_value("low_version"))

        if high_ver > prev_high_version:
            h_idx = int(swing.get_value("high_idx"))
            swings.append(SwingPoint(
                idx=h_idx,
                timestamp=str(df.iloc[h_idx]["timestamp"]),
                level=float(swing.get_value("high_level")),
                swing_type="high",
                significance=float(swing.get_value("high_significance")),
                is_major=bool(swing.get_value("high_is_major")),
            ))
            prev_high_version = high_ver

        if low_ver > prev_low_version:
            l_idx = int(swing.get_value("low_idx"))
            swings.append(SwingPoint(
                idx=l_idx,
                timestamp=str(df.iloc[l_idx]["timestamp"]),
                level=float(swing.get_value("low_level")),
                swing_type="low",
                significance=float(swing.get_value("low_significance")),
                is_major=bool(swing.get_value("low_is_major")),
            ))
            prev_low_version = low_ver

    return swings


def run_trend_detection(
    df: pd.DataFrame,
    atr_values: list[float],
    left: int = 5,
    right: int = 5,
) -> list[TrendChange]:
    """Run trend detector, return list of trend changes."""
    swing_params: dict[str, Any] = {
        "left": left, "right": right, "atr_key": "atr", "major_threshold": 1.5,
    }
    swing = IncrementalSwing(params=swing_params, deps={})
    trend = IncrementalTrend(params={}, deps={"swing": swing})
    changes: list[TrendChange] = []

    prev_version = 0

    for i in range(len(df)):
        row = df.iloc[i]
        bar = _make_bar(i, row, atr_values[i])
        swing.update(i, bar)
        trend.update(i, bar)

        ver = int(trend.get_value("version"))
        if ver > prev_version:
            changes.append(TrendChange(
                idx=i,
                timestamp=str(row["timestamp"]),
                direction=int(trend.get_value("direction")),
                strength=int(trend.get_value("strength")),
                wave_count=int(trend.get_value("wave_count")),
            ))
            prev_version = ver

    return changes


def run_market_structure(
    df: pd.DataFrame,
    atr_values: list[float],
    left: int = 5,
    right: int = 5,
    confirmation_close: bool = True,
) -> list[StructureEvent]:
    """Run market structure detector, return BOS/CHoCH events."""
    swing_params: dict[str, Any] = {
        "left": left, "right": right, "atr_key": "atr", "major_threshold": 1.5,
    }
    swing = IncrementalSwing(params=swing_params, deps={})
    ms = IncrementalMarketStructure(
        params={"confirmation_close": confirmation_close},
        deps={"swing": swing},
    )
    events: list[StructureEvent] = []

    for i in range(len(df)):
        row = df.iloc[i]
        bar = _make_bar(i, row, atr_values[i])
        swing.update(i, bar)
        ms.update(i, bar)

        bos = bool(ms.get_value("bos_this_bar"))
        choch = bool(ms.get_value("choch_this_bar"))

        if bos:
            events.append(StructureEvent(
                idx=i,
                timestamp=str(row["timestamp"]),
                event_type="bos",
                direction=str(ms.get_value("bos_direction")),
                level=float(ms.get_value("last_bos_level")),
                bias_after=int(ms.get_value("bias")),
            ))
        if choch:
            events.append(StructureEvent(
                idx=i,
                timestamp=str(row["timestamp"]),
                event_type="choch",
                direction=str(ms.get_value("choch_direction")),
                level=float(ms.get_value("last_choch_level")),
                bias_after=int(ms.get_value("bias")),
            ))

    return events


# ─────────────────────────────────────────────────────────
# Analysis Functions
# ─────────────────────────────────────────────────────────

def analyze_swing_distribution(swings: list[SwingPoint], tf: str, total_bars: int) -> dict[str, Any]:
    """Analyze swing point frequency and distribution."""
    highs = [s for s in swings if s.swing_type == "high"]
    lows = [s for s in swings if s.swing_type == "low"]

    print(f"\n{'='*60}")
    print(f"  SWING ANALYSIS — {tf}")
    print(f"{'='*60}")
    print(f"  Total bars: {total_bars}")
    print(f"  Total swings: {len(swings)} ({len(highs)} highs, {len(lows)} lows)")
    print(f"  Avg bars between swings: {total_bars / max(len(swings), 1):.1f}")
    print(f"  Major swings: {sum(1 for s in swings if s.is_major)} / {len(swings)}")

    # Check alternation
    alternation_violations = 0
    for i in range(1, len(swings)):
        if swings[i].swing_type == swings[i-1].swing_type:
            alternation_violations += 1
    print(f"  Alternation violations: {alternation_violations} (consecutive same-type)")

    # Check for HH/HL/LH/LL sequences
    if len(highs) >= 2:
        hh_count = sum(1 for i in range(1, len(highs)) if highs[i].level > highs[i-1].level)
        lh_count = sum(1 for i in range(1, len(highs)) if highs[i].level < highs[i-1].level)
        eh_count = sum(1 for i in range(1, len(highs)) if highs[i].level == highs[i-1].level)
        print(f"  Highs: {hh_count} HH, {lh_count} LH, {eh_count} EH")

    if len(lows) >= 2:
        hl_count = sum(1 for i in range(1, len(lows)) if lows[i].level > lows[i-1].level)
        ll_count = sum(1 for i in range(1, len(lows)) if lows[i].level < lows[i-1].level)
        el_count = sum(1 for i in range(1, len(lows)) if lows[i].level == lows[i-1].level)
        print(f"  Lows:  {hl_count} HL, {ll_count} LL, {el_count} EL")

    # Significance distribution
    sigs = [s.significance for s in swings if s.significance > 0]
    if sigs:
        print(f"  Significance: min={min(sigs):.2f}, median={np.median(sigs):.2f}, max={max(sigs):.2f} ATR")

    return {
        "tf": tf,
        "total_bars": total_bars,
        "total_swings": len(swings),
        "highs": len(highs),
        "lows": len(lows),
        "bars_per_swing": total_bars / max(len(swings), 1),
        "alternation_violations": alternation_violations,
        "major_count": sum(1 for s in swings if s.is_major),
    }


def analyze_cross_tf_alignment(
    swings_4h: list[SwingPoint],
    swings_12h: list[SwingPoint],
    swings_d: list[SwingPoint],
) -> None:
    """Check if lower TF swings align with higher TF swings."""
    print(f"\n{'='*60}")
    print(f"  CROSS-TIMEFRAME ALIGNMENT ANALYSIS")
    print(f"{'='*60}")

    print(f"\n  Daily swings vs 12h/4h alignment:")
    print(f"  {'-'*55}")

    d_aligned_12h = 0
    d_aligned_4h = 0

    for ds in swings_d:
        ts = pd.Timestamp(ds.timestamp)

        # Find 12h swings within ±1.5 days
        nearby_12h = [
            s for s in swings_12h
            if s.swing_type == ds.swing_type
            and abs((pd.Timestamp(s.timestamp) - ts).total_seconds()) < 86400 * 1.5
        ]
        # Find 4h swings within ±1.5 days
        nearby_4h = [
            s for s in swings_4h
            if s.swing_type == ds.swing_type
            and abs((pd.Timestamp(s.timestamp) - ts).total_seconds()) < 86400 * 1.5
        ]

        has_12h = len(nearby_12h) > 0
        has_4h = len(nearby_4h) > 0

        if has_12h:
            d_aligned_12h += 1
        if has_4h:
            d_aligned_4h += 1

        price_match_12h = ""
        if nearby_12h:
            closest = min(nearby_12h, key=lambda s: abs(s.level - ds.level))
            pct_diff = abs(closest.level - ds.level) / ds.level * 100
            price_match_12h = f" (price diff: {pct_diff:.2f}%)"

        price_match_4h = ""
        if nearby_4h:
            closest = min(nearby_4h, key=lambda s: abs(s.level - ds.level))
            pct_diff = abs(closest.level - ds.level) / ds.level * 100
            price_match_4h = f" (price diff: {pct_diff:.2f}%)"

        status_12h = "ALIGNED" if has_12h else "MISSING"
        status_4h = "ALIGNED" if has_4h else "MISSING"
        ts_str = str(ts)[:10]

        print(f"    D {ds.swing_type:4s} @ {ts_str} ${ds.level:,.0f} | "
              f"12h: {status_12h}{price_match_12h} | "
              f"4h: {status_4h}{price_match_4h}")

    total_d = max(len(swings_d), 1)
    print(f"\n  Summary:")
    print(f"    Daily->12h alignment: {d_aligned_12h}/{len(swings_d)} ({d_aligned_12h/total_d*100:.0f}%)")
    print(f"    Daily->4h  alignment: {d_aligned_4h}/{len(swings_d)} ({d_aligned_4h/total_d*100:.0f}%)")

    # 12h vs 4h
    print(f"\n  12h swings vs 4h alignment:")
    print(f"  {'-'*50}")
    h12_aligned_4h = 0

    for s12 in swings_12h:
        ts = pd.Timestamp(s12.timestamp)
        nearby_4h = [
            s for s in swings_4h
            if s.swing_type == s12.swing_type
            and abs((pd.Timestamp(s.timestamp) - ts).total_seconds()) < 43200 * 1.5
        ]
        if nearby_4h:
            h12_aligned_4h += 1

    total_12h = max(len(swings_12h), 1)
    print(f"    12h->4h alignment: {h12_aligned_4h}/{len(swings_12h)} ({h12_aligned_4h/total_12h*100:.0f}%)")

    # Ratio analysis
    ratio_4h_12h = len(swings_4h) / max(len(swings_12h), 1)
    ratio_4h_d = len(swings_4h) / max(len(swings_d), 1)
    ratio_12h_d = len(swings_12h) / max(len(swings_d), 1)

    print(f"\n  Swing count ratios:")
    print(f"    4h/12h: {ratio_4h_12h:.1f}x (expected: 2-4x)")
    print(f"    4h/D:   {ratio_4h_d:.1f}x (expected: 4-8x)")
    print(f"    12h/D:  {ratio_12h_d:.1f}x (expected: 1.5-3x)")


def analyze_swing_vs_actual_extremes(
    swings: list[SwingPoint],
    df: pd.DataFrame,
    tf: str,
    window: int = 20,
) -> None:
    """Verify detected swings are actual local extremes."""
    print(f"\n{'='*60}")
    print(f"  SWING VS ACTUAL EXTREMES — {tf} (window={window})")
    print(f"{'='*60}")

    highs_arr = np.array(df["high"].values, dtype=float)
    lows_arr = np.array(df["low"].values, dtype=float)
    n = len(df)

    # Find "obvious" local extremes using a rolling window
    obvious_highs: list[tuple[int, float, str]] = []
    obvious_lows: list[tuple[int, float, str]] = []
    half_w = window // 2

    for i in range(half_w, n - half_w):
        local_high = highs_arr[i - half_w:i + half_w + 1]
        local_low = lows_arr[i - half_w:i + half_w + 1]

        if highs_arr[i] == max(local_high) and highs_arr[i] > highs_arr[i-1] and highs_arr[i] > highs_arr[i+1]:
            obvious_highs.append((i, float(highs_arr[i]), str(df.iloc[i]["timestamp"])))
        if lows_arr[i] == min(local_low) and lows_arr[i] < lows_arr[i-1] and lows_arr[i] < lows_arr[i+1]:
            obvious_lows.append((i, float(lows_arr[i]), str(df.iloc[i]["timestamp"])))

    # Check: are detected swings real extremes?
    false_highs = 0
    for s in swings:
        if s.swing_type == "high":
            start = max(0, s.idx - half_w)
            end = min(n, s.idx + half_w + 1)
            local_max = float(max(highs_arr[start:end]))
            if highs_arr[s.idx] < local_max:
                false_highs += 1

    false_lows = 0
    for s in swings:
        if s.swing_type == "low":
            start = max(0, s.idx - half_w)
            end = min(n, s.idx + half_w + 1)
            local_min = float(min(lows_arr[start:end]))
            if lows_arr[s.idx] > local_min:
                false_lows += 1

    # Check: are obvious extremes detected?
    missed_highs: list[tuple[int, float, str]] = []
    for idx, level, ts in obvious_highs:
        nearby = [s for s in swings if s.swing_type == "high" and abs(s.idx - idx) <= half_w]
        if not nearby:
            missed_highs.append((idx, level, ts))

    missed_lows: list[tuple[int, float, str]] = []
    for idx, level, ts in obvious_lows:
        nearby = [s for s in swings if s.swing_type == "low" and abs(s.idx - idx) <= half_w]
        if not nearby:
            missed_lows.append((idx, level, ts))

    total_detected_h = sum(1 for s in swings if s.swing_type == "high")
    total_detected_l = sum(1 for s in swings if s.swing_type == "low")

    print(f"  Reference extremes (window={window}): {len(obvious_highs)} highs, {len(obvious_lows)} lows")
    print(f"  Detected swings: {total_detected_h} highs, {total_detected_l} lows")
    print(f"  False positives: {false_highs} highs, {false_lows} lows "
          f"(not actual local extreme in {window}-bar window)")
    print(f"  Missed extremes: {len(missed_highs)} highs, {len(missed_lows)} lows")

    if missed_highs:
        print(f"\n  Top missed highs (most significant):")
        missed_highs.sort(key=lambda x: x[1], reverse=True)
        for idx, level, ts in missed_highs[:10]:
            print(f"    bar {idx} @ {ts} — ${level:,.0f}")

    if missed_lows:
        print(f"\n  Top missed lows (most significant):")
        missed_lows.sort(key=lambda x: x[1])
        for idx, level, ts in missed_lows[:10]:
            print(f"    bar {idx} @ {ts} — ${level:,.0f}")


def print_swing_timeline(swings: list[SwingPoint], tf: str, limit: int = 60) -> None:
    """Print a chronological timeline of swing points."""
    print(f"\n{'='*60}")
    print(f"  SWING TIMELINE — {tf} (last {limit})")
    print(f"{'='*60}")

    recent = swings[-limit:] if len(swings) > limit else swings

    for s in recent:
        major_flag = " MAJOR" if s.is_major else ""
        print(f"  bar {s.idx:4d} | {s.timestamp} | {s.swing_type:4s} ${s.level:>10,.0f} | "
              f"sig={s.significance:5.2f}{major_flag}")


def print_structure_events(events: list[StructureEvent], tf: str, conf_mode: str) -> None:
    """Print BOS/CHoCH events."""
    print(f"\n{'='*60}")
    print(f"  MARKET STRUCTURE EVENTS — {tf} (confirmation: {conf_mode})")
    print(f"{'='*60}")

    bos_count = sum(1 for e in events if e.event_type == "bos")
    choch_count = sum(1 for e in events if e.event_type == "choch")

    print(f"  Total: {len(events)} events ({bos_count} BOS, {choch_count} CHoCH)")

    for e in events:
        bias_str = {1: "BULL", -1: "BEAR", 0: "RANG"}[e.bias_after]
        icon = "BOS " if e.event_type == "bos" else "CHCH"
        print(f"  bar {e.idx:4d} | {e.timestamp} | {icon} {e.direction:7s} @ ${e.level:>10,.0f} | bias->{bias_str}")


def analyze_structure_consistency(
    events_wick: list[StructureEvent],
    events_close: list[StructureEvent],
    tf: str,
) -> None:
    """Compare wick-based vs close-based structure detection."""
    print(f"\n{'='*60}")
    print(f"  WICK vs CLOSE COMPARISON — {tf}")
    print(f"{'='*60}")

    print(f"  Wick-based:  {len(events_wick)} events "
          f"({sum(1 for e in events_wick if e.event_type == 'bos')} BOS, "
          f"{sum(1 for e in events_wick if e.event_type == 'choch')} CHoCH)")
    print(f"  Close-based: {len(events_close)} events "
          f"({sum(1 for e in events_close if e.event_type == 'bos')} BOS, "
          f"{sum(1 for e in events_close if e.event_type == 'choch')} CHoCH)")

    if len(events_wick) > len(events_close):
        extra = len(events_wick) - len(events_close)
        print(f"  Wick fires {extra} more events ({extra/max(len(events_close),1)*100:.0f}% more)")
        print(f"  -> These extras are likely LIQUIDITY SWEEPS, not real structure breaks")
    elif len(events_wick) < len(events_close):
        print(f"  WARNING: Close-based fires MORE events than wick-based — unexpected!")
    else:
        print(f"  Same event count")


def analyze_trend_vs_structure(
    trend_changes: list[TrendChange],
    structure_events: list[StructureEvent],
    tf: str,
) -> None:
    """Check if trend and structure detectors agree."""
    print(f"\n{'='*60}")
    print(f"  TREND vs STRUCTURE AGREEMENT — {tf}")
    print(f"{'='*60}")

    chochs = [e for e in structure_events if e.event_type == "choch"]

    agreement = 0
    disagreement = 0
    no_trend = 0

    for ch in chochs:
        nearby_trend = [t for t in trend_changes if abs(t.idx - ch.idx) <= 20]
        if nearby_trend:
            t = nearby_trend[0]
            choch_dir = 1 if ch.direction == "bullish" else -1
            if t.direction == choch_dir:
                agreement += 1
            else:
                disagreement += 1
                print(f"  DISAGREE @ bar {ch.idx}: CHoCH {ch.direction} but trend->{t.direction}")
        else:
            no_trend += 1
            print(f"  NO TREND CHANGE near CHoCH @ bar {ch.idx} ({ch.direction})")

    total = agreement + disagreement + no_trend
    if total > 0:
        print(f"\n  Agreement: {agreement}/{total} | Disagreement: {disagreement} | No trend change: {no_trend}")
    else:
        print(f"\n  No CHoCH events to compare")


def param_sensitivity_test(df: pd.DataFrame, atr_values: list[float], tf: str) -> None:
    """Test how different parameters affect swing detection."""
    print(f"\n{'='*60}")
    print(f"  PARAMETER SENSITIVITY — {tf}")
    print(f"{'='*60}")

    configs: list[dict[str, Any]] = [
        {"left": 2, "right": 2, "label": "Williams Fractal (2,2)"},
        {"left": 3, "right": 3, "label": "Short-term (3,3)"},
        {"left": 5, "right": 5, "label": "Standard (5,5)"},
        {"left": 8, "right": 8, "label": "Position (8,8)"},
        {"left": 13, "right": 13, "label": "Major (13,13)"},
        {"left": 5, "right": 5, "min_atr_move": 0.5, "label": "Std + ATR filter 0.5"},
        {"left": 5, "right": 5, "min_atr_move": 1.0, "label": "Std + ATR filter 1.0"},
        {"left": 5, "right": 5, "strict_alternation": True, "label": "Std + strict alt"},
    ]

    hdr = (f"  {'Config':<30s} | {'Swings':>6s} | {'Highs':>5s} | {'Lows':>5s} "
           f"| {'Major':>5s} | {'Bars/Swing':>10s} | {'AltViol':>7s}")
    print(hdr)
    print(f"  {'-'*30}-+-{'-'*6}-+-{'-'*5}-+-{'-'*5}-+-{'-'*5}-+-{'-'*10}-+-{'-'*7}")

    for cfg in configs:
        swings = run_swing_detection(
            df, atr_values,
            left=cfg.get("left", 5),
            right=cfg.get("right", 5),
            min_atr_move=cfg.get("min_atr_move", 0.0),
            strict_alternation=cfg.get("strict_alternation", False),
        )

        n_highs = sum(1 for s in swings if s.swing_type == "high")
        n_lows = sum(1 for s in swings if s.swing_type == "low")
        major = sum(1 for s in swings if s.is_major)
        alt_v = sum(1 for i in range(1, len(swings)) if swings[i].swing_type == swings[i-1].swing_type)
        bps = len(df) / max(len(swings), 1)

        print(f"  {cfg['label']:<30s} | {len(swings):>6d} | {n_highs:>5d} | {n_lows:>5d} "
              f"| {major:>5d} | {bps:>10.1f} | {alt_v:>7d}")


# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 70)
    print("  STRUCTURE DETECTION AUDIT — BTCUSDT (6 months)")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    # Load data
    print("\nLoading data...")
    df_4h = load_btc_data("4h")
    df_12h = load_btc_data("12h")
    df_d = load_btc_data("D")

    print(f"  4h:  {len(df_4h)} bars ({df_4h['timestamp'].min()} to {df_4h['timestamp'].max()})")
    print(f"  12h: {len(df_12h)} bars ({df_12h['timestamp'].min()} to {df_12h['timestamp'].max()})")
    print(f"  D:   {len(df_d)} bars ({df_d['timestamp'].min()} to {df_d['timestamp'].max()})")

    # Compute ATR
    print("\nComputing ATR...")
    atr_4h = compute_atr_series(df_4h)
    atr_12h = compute_atr_series(df_12h)
    atr_d = compute_atr_series(df_d)

    # ─── Swing Detection (left=5, right=5) ───
    print("\nRunning swing detection (left=5, right=5)...")
    swings_4h = run_swing_detection(df_4h, atr_4h, left=5, right=5)
    swings_12h = run_swing_detection(df_12h, atr_12h, left=5, right=5)
    swings_d = run_swing_detection(df_d, atr_d, left=5, right=5)

    for swings, df, tf in [(swings_4h, df_4h, "4h"), (swings_12h, df_12h, "12h"), (swings_d, df_d, "D")]:
        analyze_swing_distribution(swings, tf, len(df))

    for swings, tf in [(swings_4h, "4h"), (swings_12h, "12h"), (swings_d, "D")]:
        print_swing_timeline(swings, tf)

    analyze_cross_tf_alignment(swings_4h, swings_12h, swings_d)

    for swings, df, tf in [(swings_4h, df_4h, "4h"), (swings_12h, df_12h, "12h"), (swings_d, df_d, "D")]:
        analyze_swing_vs_actual_extremes(swings, df, tf, window=20)

    # ─── Market Structure ───
    print("\n\n" + "=" * 70)
    print("  MARKET STRUCTURE ANALYSIS")
    print("=" * 70)

    for df, atr, tf in [(df_4h, atr_4h, "4h"), (df_12h, atr_12h, "12h"), (df_d, atr_d, "D")]:
        events_wick = run_market_structure(df, atr, confirmation_close=False)
        events_close = run_market_structure(df, atr, confirmation_close=True)
        print_structure_events(events_close, tf, "CLOSE")
        analyze_structure_consistency(events_wick, events_close, tf)

    # ─── Trend Detection ───
    print("\n\n" + "=" * 70)
    print("  TREND ANALYSIS")
    print("=" * 70)

    for df, atr, tf in [(df_4h, atr_4h, "4h"), (df_12h, atr_12h, "12h"), (df_d, atr_d, "D")]:
        changes = run_trend_detection(df, atr)

        print(f"\n  TREND CHANGES — {tf}")
        for tc in changes:
            dir_str = {1: "UP  ", -1: "DOWN", 0: "RANG"}[tc.direction]
            print(f"    bar {tc.idx:4d} | {tc.timestamp} | -> {dir_str} | "
                  f"strength={tc.strength} | waves={tc.wave_count}")

        events_close = run_market_structure(df, atr, confirmation_close=True)
        analyze_trend_vs_structure(changes, events_close, tf)

    # ─── Parameter Sensitivity ───
    print("\n\n" + "=" * 70)
    print("  PARAMETER SENSITIVITY TESTS")
    print("=" * 70)

    for df, atr, tf in [(df_4h, atr_4h, "4h"), (df_12h, atr_12h, "12h"), (df_d, atr_d, "D")]:
        param_sensitivity_test(df, atr, tf)

    print("\n\n" + "=" * 70)
    print("  AUDIT COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
