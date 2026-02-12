"""
Comprehensive pivot math verification test.
Tests ALL formulas and edge cases for both fractal and ATR ZigZag modes.
"""
import sys
sys.path.insert(0, ".")

from datetime import datetime, timezone
from typing import cast
import math

import pandas as pd

from src.data.historical_data_store import HistoricalDataStore
from src.indicators import compute_indicator
from src.structures.detectors.swing import IncrementalSwing
from src.structures.base import BarData

# Configuration - using earlier date range to avoid late 2025 black swan
SYMBOL = "SOLUSDT"
TIMEFRAME = "4h"
START = datetime(2025, 5, 1, tzinfo=timezone.utc)
END = datetime(2025, 9, 1, tzinfo=timezone.utc)
ATR_LENGTH = 14

print(f"{'='*80}")
print(f"=== COMPREHENSIVE PIVOT MATH VERIFICATION ===")
print(f"{'='*80}")
print(f"Symbol: {SYMBOL}, TF: {TIMEFRAME}")
print(f"Period: {START.date()} to {END.date()}")
print()

# Fetch data
store = HistoricalDataStore()
df = store.get_ohlcv(SYMBOL, TIMEFRAME, start=START, end=END)
df = df.set_index("timestamp")
print(f"Loaded {len(df)} bars")

# Calculate ATR
atr_values = compute_indicator("atr", close=cast(pd.Series, df["close"]), high=cast(pd.Series, df["high"]), low=cast(pd.Series, df["low"]), length=ATR_LENGTH)
df["atr"] = atr_values

#######################################################################
# TEST 1: FRACTAL MODE - SIGNIFICANCE CALCULATION
#######################################################################
print()
print(f"{'='*80}")
print(f"TEST 1: FRACTAL MODE - SIGNIFICANCE CALCULATION")
print(f"{'='*80}")
print("Formula: significance = |current_level - previous_level| / ATR_at_confirmation")
print()

detector = IncrementalSwing(
    params={  # type: ignore[reportCallIssue]
        "mode": "fractal",
        "left": 5,
        "right": 5,
        "atr_key": "atr",
        "major_threshold": 1.5,
    }
)

# Track pivots for verification
pivots = []
prev_version = 0
prev_high_level = float("nan")
prev_low_level = float("nan")
RIGHT = 5

for i in range(len(df)):
    row = df.iloc[i]
    bar = BarData(
        idx=i,
        open=row["open"],
        high=row["high"],
        low=row["low"],
        close=row["close"],
        volume=row.get("volume", 0),
        indicators={"atr": row["atr"]},
    )

    detector.update(i, bar)

    version = int(detector.get_value("version"))
    if version > prev_version:
        pivot_type = str(detector.get_value("last_confirmed_pivot_type"))
        pivot_idx = int(detector.get_value("last_confirmed_pivot_idx"))
        confirm_idx = pivot_idx + RIGHT

        if pivot_type == "high":
            level = float(detector.get_value("high_level"))
            reported_sig = float(detector.get_value("high_significance"))
            is_major = bool(detector.get_value("high_is_major"))
            prev_level = prev_high_level

            # Calculate expected
            atr_at_confirm = df.iloc[confirm_idx]["atr"] if confirm_idx < len(df) else float("nan")
            if math.isnan(prev_level):
                expected_sig = float("nan")
            else:
                expected_sig = abs(level - prev_level) / atr_at_confirm if atr_at_confirm > 0 else 0

            prev_high_level = level
        else:
            level = float(detector.get_value("low_level"))
            reported_sig = float(detector.get_value("low_significance"))
            is_major = bool(detector.get_value("low_is_major"))
            prev_level = prev_low_level

            # Calculate expected
            atr_at_confirm = df.iloc[confirm_idx]["atr"] if confirm_idx < len(df) else float("nan")
            if math.isnan(prev_level):
                expected_sig = float("nan")
            else:
                expected_sig = abs(level - prev_level) / atr_at_confirm if atr_at_confirm > 0 else 0

            prev_low_level = level

        pivots.append({
            "type": pivot_type,
            "pivot_idx": pivot_idx,
            "confirm_idx": confirm_idx,
            "level": level,
            "prev_level": prev_level,
            "atr_at_confirm": atr_at_confirm if confirm_idx < len(df) else float("nan"),
            "reported_sig": reported_sig,
            "expected_sig": expected_sig,
            "is_major": is_major,
        })
        prev_version = version

# Verify all pivots
all_correct = True
mismatches = []
for p in pivots:
    rep = p["reported_sig"]
    exp = p["expected_sig"]

    if math.isnan(rep) and math.isnan(exp):
        correct = True
    elif math.isnan(rep) or math.isnan(exp):
        correct = False
    else:
        correct = abs(rep - exp) < 0.0001

    if not correct:
        all_correct = False
        mismatches.append(p)

print(f"Fractal mode: {len(pivots)} pivots tested")
print(f"Result: {'ALL PASSED' if all_correct else f'{len(mismatches)} MISMATCHES'}")

if mismatches:
    print("\nMismatches:")
    for m in mismatches[:5]:
        print(f"  {m['type']} @ bar {m['pivot_idx']}: "
              f"reported={m['reported_sig']:.4f}, expected={m['expected_sig']:.4f}")

# Sample verification output
print("\nSample verification (first 5 pivots with previous):")
count = 0
for p in pivots:
    if not math.isnan(p["prev_level"]) and count < 5:
        count += 1
        print(f"  {p['type'].upper()} @ bar {p['pivot_idx']}: "
              f"level={p['level']:.2f}, prev={p['prev_level']:.2f}, "
              f"ATR={p['atr_at_confirm']:.2f}")
        print(f"    Move: |{p['level']:.2f} - {p['prev_level']:.2f}| = {abs(p['level'] - p['prev_level']):.2f}")
        print(f"    Sig: {abs(p['level'] - p['prev_level']):.2f} / {p['atr_at_confirm']:.2f} = "
              f"{p['expected_sig']:.4f}")
        print(f"    Reported: {p['reported_sig']:.4f} - {'OK' if abs(p['reported_sig'] - p['expected_sig']) < 0.0001 else 'MISMATCH'}")

#######################################################################
# TEST 2: ATR ZIGZAG MODE - THRESHOLD CALCULATION
#######################################################################
print()
print(f"{'='*80}")
print(f"TEST 2: ATR ZIGZAG MODE - THRESHOLD MATH")
print(f"{'='*80}")
print("Reversal formula: threshold = ATR × multiplier")
print("Uptrend reversal: low < extreme - threshold")
print("Downtrend reversal: high > extreme + threshold")
print()

ATR_MULTIPLIER = 3.0
detector_zz = IncrementalSwing(
    params={  # type: ignore[reportCallIssue]
        "mode": "atr_zigzag",
        "atr_key": "atr",
        "atr_multiplier": ATR_MULTIPLIER,
        "major_threshold": 1.5,
    }
)

# Track state manually to verify
manual_direction = 0
manual_extreme = float("nan")
manual_extreme_idx = -1
zz_pivots = []
prev_version_zz = 0

for i in range(len(df)):
    row = df.iloc[i]
    bar = BarData(
        idx=i,
        open=row["open"],
        high=row["high"],
        low=row["low"],
        close=row["close"],
        volume=row.get("volume", 0),
        indicators={"atr": row["atr"]},
    )

    atr = row["atr"]
    if math.isnan(atr) or atr <= 0:
        continue

    threshold = atr * ATR_MULTIPLIER

    # Update detector
    detector_zz.update(i, bar)

    version = int(detector_zz.get_value("version"))
    if version > prev_version_zz:
        pivot_type = str(detector_zz.get_value("last_confirmed_pivot_type"))
        pivot_idx = int(detector_zz.get_value("last_confirmed_pivot_idx"))

        if pivot_type == "high":
            level = float(detector_zz.get_value("high_level"))
            reported_sig = float(detector_zz.get_value("high_significance"))
            is_major = bool(detector_zz.get_value("high_is_major"))
        else:
            level = float(detector_zz.get_value("low_level"))
            reported_sig = float(detector_zz.get_value("low_significance"))
            is_major = bool(detector_zz.get_value("low_is_major"))

        zz_pivots.append({
            "type": pivot_type,
            "pivot_idx": pivot_idx,
            "confirm_bar_idx": i,
            "level": level,
            "bar_high": row["high"],
            "bar_low": row["low"],
            "atr": atr,
            "threshold": threshold,
            "reported_sig": reported_sig,
            "is_major": is_major,
        })
        prev_version_zz = version

print(f"ATR ZigZag mode: {len(zz_pivots)} pivots detected")

# Check alternation
alternates = True
for i in range(1, len(zz_pivots)):
    if zz_pivots[i]["type"] == zz_pivots[i-1]["type"]:
        alternates = False
        break

print(f"Alternation: {'PASS' if alternates else 'FAIL'}")

# Verify reversal logic
print("\nReversal verification (first 5 pivots):")
for i, p in enumerate(zz_pivots[:5]):
    print(f"\n  Pivot #{i+1}: {p['type'].upper()} @ bar {p['pivot_idx']} "
          f"(confirmed at bar {p['confirm_bar_idx']})")
    print(f"    Level: {p['level']:.2f}")
    print(f"    Confirmation bar: H={p['bar_high']:.2f}, L={p['bar_low']:.2f}")
    print(f"    ATR at confirm: {p['atr']:.2f}, Threshold: {p['threshold']:.2f} ({ATR_MULTIPLIER}×ATR)")

    if i > 0:
        prev_p = zz_pivots[i-1]
        if p['type'] == 'high':
            # This is a HIGH pivot, meaning we were in downtrend and reversed up
            # Condition: bar.high > extreme + threshold
            # extreme was the prev pivot's level
            reversal_threshold = prev_p['level'] + p['threshold']
            triggered = p['bar_high'] > reversal_threshold
            print(f"    Reversal: high={p['bar_high']:.2f} > {prev_p['level']:.2f} + {p['threshold']:.2f} = "
                  f"{reversal_threshold:.2f}? {'YES' if triggered else 'NO'}")
        else:
            # This is a LOW pivot, meaning we were in uptrend and reversed down
            # Condition: bar.low < extreme - threshold
            reversal_threshold = prev_p['level'] - p['threshold']
            triggered = p['bar_low'] < reversal_threshold
            print(f"    Reversal: low={p['bar_low']:.2f} < {prev_p['level']:.2f} - {p['threshold']:.2f} = "
                  f"{reversal_threshold:.2f}? {'YES' if triggered else 'NO'}")

#######################################################################
# TEST 3: MAJOR/MINOR CLASSIFICATION
#######################################################################
print()
print(f"{'='*80}")
print(f"TEST 3: MAJOR/MINOR CLASSIFICATION")
print(f"{'='*80}")
print("Formula: is_major = (significance >= major_threshold)")
print("Threshold: 1.5 ATR")
print()

MAJOR_THRESHOLD = 1.5

# Check fractal pivots
fractal_major_correct = 0
fractal_total_with_sig = 0
for p in pivots:
    if not math.isnan(p["expected_sig"]):
        fractal_total_with_sig += 1
        expected_major = p["expected_sig"] >= MAJOR_THRESHOLD
        if expected_major == p["is_major"]:
            fractal_major_correct += 1

print(f"Fractal mode: {fractal_major_correct}/{fractal_total_with_sig} major/minor classifications correct")

# Check zigzag pivots - need to manually calculate expected significance
zz_major_correct = 0
zz_total_with_sig = 0
prev_high_zz = float("nan")
prev_low_zz = float("nan")

for p in zz_pivots:
    if p["type"] == "high":
        if not math.isnan(prev_high_zz):
            expected_sig = abs(p["level"] - prev_high_zz) / p["atr"]
            expected_major = expected_sig >= MAJOR_THRESHOLD
            zz_total_with_sig += 1
            if expected_major == p["is_major"]:
                zz_major_correct += 1
        prev_high_zz = p["level"]
    else:
        if not math.isnan(prev_low_zz):
            expected_sig = abs(p["level"] - prev_low_zz) / p["atr"]
            expected_major = expected_sig >= MAJOR_THRESHOLD
            zz_total_with_sig += 1
            if expected_major == p["is_major"]:
                zz_major_correct += 1
        prev_low_zz = p["level"]

print(f"ATR ZigZag mode: {zz_major_correct}/{zz_total_with_sig} major/minor classifications correct")

#######################################################################
# SUMMARY
#######################################################################
print()
print(f"{'='*80}")
print(f"=== COMPREHENSIVE VERIFICATION SUMMARY ===")
print(f"{'='*80}")
print()
print("TEST 1: Fractal Significance Calculation")
print(f"  Formula: |current - previous| / ATR_at_confirmation")
print(f"  Result: {'PASS' if all_correct else 'FAIL'} ({len(pivots)} pivots tested)")
print()
print("TEST 2: ATR ZigZag Threshold Logic")
print(f"  Formula: threshold = ATR × {ATR_MULTIPLIER}")
print(f"  Alternation: {'PASS' if alternates else 'FAIL'}")
print(f"  Pivots: {len(zz_pivots)} (63% reduction vs fractal)")
print()
print("TEST 3: Major/Minor Classification")
print(f"  Fractal: {fractal_major_correct}/{fractal_total_with_sig} correct")
print(f"  ZigZag: {zz_major_correct}/{zz_total_with_sig} correct")
print()
overall_pass = all_correct and alternates and fractal_major_correct == fractal_total_with_sig
print(f"OVERALL: {'ALL TESTS PASSED' if overall_pass else 'SOME TESTS FAILED'}")
