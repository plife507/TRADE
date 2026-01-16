"""
Debug script to verify significance calculation math on SOLUSDT.
Verifies: significance = |current_level - previous_level| / ATR
"""
import sys
sys.path.insert(0, ".")

from datetime import datetime, timezone
import random
import math

from src.data.historical_data_store import HistoricalDataStore
from src.indicators import compute_indicator

# Configuration
SYMBOL = "SOLUSDT"
TIMEFRAME = "1h"
START = datetime(2025, 11, 15, tzinfo=timezone.utc)
END = datetime(2026, 1, 15, tzinfo=timezone.utc)

# Swing detector params
LEFT = 5
RIGHT = 5
ATR_LENGTH = 14
MAJOR_THRESHOLD = 1.5

print(f"=== Significance Math Verification ===")
print(f"Symbol: {SYMBOL}, TF: {TIMEFRAME}")
print(f"Period: {START.date()} to {END.date()}")
print(f"Swing params: left={LEFT}, right={RIGHT}")
print(f"ATR length: {ATR_LENGTH}, Major threshold: {MAJOR_THRESHOLD}")
print()

# Fetch data
store = HistoricalDataStore()
df = store.get_ohlcv(SYMBOL, TIMEFRAME, start=START, end=END)
df = df.set_index("timestamp")
print(f"Loaded {len(df)} bars")

# Calculate ATR (pass individual series)
atr_values = compute_indicator("atr", close=df["close"], high=df["high"], low=df["low"], length=ATR_LENGTH)
df["atr"] = atr_values

# Import swing detector and BarData
from src.structures.detectors.swing import IncrementalSwingDetector
from src.structures.base import BarData

# Create detector with ATR significance
detector = IncrementalSwingDetector(
    params={
        "left": LEFT,
        "right": RIGHT,
        "atr_key": "atr",
        "major_threshold": MAJOR_THRESHOLD,
    }
)

# Track pivots for verification
all_pivots = []
prev_version = 0
prev_high_level = float("nan")
prev_low_level = float("nan")

# Run incremental detection
for i in range(len(df)):
    row = df.iloc[i]
    bar_idx = i

    # Build bar data using BarData dataclass
    bar = BarData(
        idx=bar_idx,
        open=row["open"],
        high=row["high"],
        low=row["low"],
        close=row["close"],
        volume=row.get("volume", 0),
        indicators={"atr": row["atr"]},
    )

    # Update detector
    detector.update(bar_idx, bar)

    # Check for new pivot (version changed)
    version = detector.get_value("version")
    if version > prev_version:
        # Get current values
        high_level = detector.get_value("high_level")
        low_level = detector.get_value("low_level")
        high_sig = detector.get_value("high_significance")
        low_sig = detector.get_value("low_significance")
        high_major = detector.get_value("high_is_major")
        low_major = detector.get_value("low_is_major")
        pivot_type = detector.get_value("last_confirmed_pivot_type")
        pivot_idx = detector.get_value("last_confirmed_pivot_idx")

        # Get ATR at the CONFIRMATION bar (not pivot bar!)
        # Pivot is confirmed at bar_idx, which is pivot_idx + RIGHT bars
        confirm_idx = pivot_idx + RIGHT  # This equals bar_idx
        atr_at_confirm = df.iloc[confirm_idx]["atr"] if confirm_idx >= 0 and confirm_idx < len(df) else float("nan")
        pivot_timestamp = df.index[pivot_idx] if pivot_idx >= 0 and pivot_idx < len(df) else None

        if pivot_type == "high":
            # Calculate expected significance using ATR at confirmation bar
            if math.isnan(prev_high_level):
                expected_sig = 0.0
            else:
                expected_sig = abs(high_level - prev_high_level) / atr_at_confirm if atr_at_confirm > 0 else 0.0

            all_pivots.append({
                "type": "HIGH",
                "bar_idx": pivot_idx,
                "confirm_idx": confirm_idx,
                "level": high_level,
                "prev_level": prev_high_level,
                "atr": atr_at_confirm,
                "reported_sig": high_sig,
                "expected_sig": expected_sig,
                "is_major": high_major,
                "timestamp": pivot_timestamp,
            })
            prev_high_level = high_level

        elif pivot_type == "low":
            # Calculate expected significance using ATR at confirmation bar
            if math.isnan(prev_low_level):
                expected_sig = 0.0
            else:
                expected_sig = abs(low_level - prev_low_level) / atr_at_confirm if atr_at_confirm > 0 else 0.0

            all_pivots.append({
                "type": "LOW",
                "bar_idx": pivot_idx,
                "confirm_idx": confirm_idx,
                "level": low_level,
                "prev_level": prev_low_level,
                "atr": atr_at_confirm,
                "reported_sig": low_sig,
                "expected_sig": expected_sig,
                "is_major": low_major,
                "timestamp": pivot_timestamp,
            })
            prev_low_level = low_level

        prev_version = version

print(f"\n=== Results ===")
print(f"Total pivots detected: {len(all_pivots)}")

highs = [p for p in all_pivots if p["type"] == "HIGH"]
lows = [p for p in all_pivots if p["type"] == "LOW"]
major_count = sum(1 for p in all_pivots if p["is_major"])
minor_count = len(all_pivots) - major_count

print(f"Highs: {len(highs)}, Lows: {len(lows)}")
print(f"Major: {major_count}, Minor: {minor_count}")

# Verify math on random sample (skip first pivot of each type - no prev)
pivots_with_prev = [p for p in all_pivots if not math.isnan(p["prev_level"])]
print(f"\n=== Random Sample Verification (10 pivots with previous) ===")
sample = random.sample(pivots_with_prev, min(10, len(pivots_with_prev)))
sample.sort(key=lambda x: x["bar_idx"])

all_match = True
for p in sample:
    reported = p["reported_sig"]
    expected = p["expected_sig"]

    # Handle NaN comparison
    if math.isnan(reported) and math.isnan(expected):
        match = True  # Both NaN
    elif math.isnan(reported) or math.isnan(expected):
        match = False  # One NaN
    else:
        match = abs(reported - expected) < 0.0001

    status = "OK" if match else "MISMATCH"
    if not match:
        all_match = False

    major_str = "MAJOR" if p["is_major"] else "minor"
    prev_str = f"{p['prev_level']:.4f}" if not math.isnan(p["prev_level"]) else "N/A (first)"

    print(f"[{status}] {p['type']:4} @ bar {p['bar_idx']:4} | "
          f"level={p['level']:.4f} prev={prev_str} ATR={p['atr']:.4f} | "
          f"reported={reported:.4f} expected={expected:.4f} | {major_str}")

print(f"\n=== Math Verification: {'ALL PASSED' if all_match else 'SOME MISMATCHES'} ===")

# Show detailed breakdown of first few pivots
print(f"\n=== First 5 Pivots Detail ===")
for i, p in enumerate(all_pivots[:5]):
    print(f"\nPivot #{i+1}: {p['type']} @ bar {p['bar_idx']}")
    print(f"  Timestamp: {p['timestamp']}")
    print(f"  Level: {p['level']:.4f}")
    if not math.isnan(p["prev_level"]):
        print(f"  Previous {p['type']}: {p['prev_level']:.4f}")
        print(f"  Move: |{p['level']:.4f} - {p['prev_level']:.4f}| = {abs(p['level'] - p['prev_level']):.4f}")
        print(f"  ATR at pivot: {p['atr']:.4f}")
        print(f"  Significance: {abs(p['level'] - p['prev_level']):.4f} / {p['atr']:.4f} = {p['expected_sig']:.4f}")
    else:
        print(f"  First pivot of this type - no previous to compare")
    print(f"  Reported significance: {p['reported_sig']:.4f}")
    print(f"  Is Major (>= {MAJOR_THRESHOLD} ATR): {p['is_major']}")

# Also test 4h timeframe
print(f"\n\n{'='*60}")
print(f"=== Now testing 4h timeframe ===")
print(f"{'='*60}")

# Fetch 4h data
df_4h = store.get_ohlcv(SYMBOL, "4h", start=START, end=END)
df_4h = df_4h.set_index("timestamp")
print(f"Loaded {len(df_4h)} bars (4h)")

# Calculate ATR for 4h
atr_values_4h = compute_indicator("atr", close=df_4h["close"], high=df_4h["high"], low=df_4h["low"], length=ATR_LENGTH)
df_4h["atr"] = atr_values_4h

# Create new detector for 4h
detector_4h = IncrementalSwingDetector(
    params={
        "left": LEFT,
        "right": RIGHT,
        "atr_key": "atr",
        "major_threshold": MAJOR_THRESHOLD,
    }
)

# Track pivots
pivots_4h = []
prev_version_4h = 0
prev_high_level_4h = float("nan")
prev_low_level_4h = float("nan")

for i in range(len(df_4h)):
    row = df_4h.iloc[i]
    bar_idx = i

    bar = BarData(
        idx=bar_idx,
        open=row["open"],
        high=row["high"],
        low=row["low"],
        close=row["close"],
        volume=row.get("volume", 0),
        indicators={"atr": row["atr"]},
    )

    detector_4h.update(bar_idx, bar)

    version = detector_4h.get_value("version")
    if version > prev_version_4h:
        high_level = detector_4h.get_value("high_level")
        low_level = detector_4h.get_value("low_level")
        high_sig = detector_4h.get_value("high_significance")
        low_sig = detector_4h.get_value("low_significance")
        high_major = detector_4h.get_value("high_is_major")
        low_major = detector_4h.get_value("low_is_major")
        pivot_type = detector_4h.get_value("last_confirmed_pivot_type")
        pivot_idx = detector_4h.get_value("last_confirmed_pivot_idx")

        confirm_idx_4h = pivot_idx + RIGHT
        atr_at_confirm_4h = df_4h.iloc[confirm_idx_4h]["atr"] if confirm_idx_4h >= 0 and confirm_idx_4h < len(df_4h) else float("nan")
        pivot_timestamp = df_4h.index[pivot_idx] if pivot_idx >= 0 and pivot_idx < len(df_4h) else None

        if pivot_type == "high":
            if math.isnan(prev_high_level_4h):
                expected_sig = 0.0
            else:
                expected_sig = abs(high_level - prev_high_level_4h) / atr_at_confirm_4h if atr_at_confirm_4h > 0 else 0.0

            pivots_4h.append({
                "type": "HIGH",
                "bar_idx": pivot_idx,
                "confirm_idx": confirm_idx_4h,
                "level": high_level,
                "prev_level": prev_high_level_4h,
                "atr": atr_at_confirm_4h,
                "reported_sig": high_sig,
                "expected_sig": expected_sig,
                "is_major": high_major,
                "timestamp": pivot_timestamp,
            })
            prev_high_level_4h = high_level

        elif pivot_type == "low":
            if math.isnan(prev_low_level_4h):
                expected_sig = 0.0
            else:
                expected_sig = abs(low_level - prev_low_level_4h) / atr_at_confirm_4h if atr_at_confirm_4h > 0 else 0.0

            pivots_4h.append({
                "type": "LOW",
                "bar_idx": pivot_idx,
                "confirm_idx": confirm_idx_4h,
                "level": low_level,
                "prev_level": prev_low_level_4h,
                "atr": atr_at_confirm_4h,
                "reported_sig": low_sig,
                "expected_sig": expected_sig,
                "is_major": low_major,
                "timestamp": pivot_timestamp,
            })
            prev_low_level_4h = low_level

        prev_version_4h = version

print(f"\n=== 4h Results ===")
print(f"Total pivots detected: {len(pivots_4h)}")

highs_4h = [p for p in pivots_4h if p["type"] == "HIGH"]
lows_4h = [p for p in pivots_4h if p["type"] == "LOW"]
major_count_4h = sum(1 for p in pivots_4h if p["is_major"])
minor_count_4h = len(pivots_4h) - major_count_4h

print(f"Highs: {len(highs_4h)}, Lows: {len(lows_4h)}")
print(f"Major: {major_count_4h}, Minor: {minor_count_4h}")

# Verify math on 4h sample
pivots_4h_with_prev = [p for p in pivots_4h if not math.isnan(p["prev_level"])]
print(f"\n=== 4h Random Sample Verification (5 pivots) ===")
sample_4h = random.sample(pivots_4h_with_prev, min(5, len(pivots_4h_with_prev)))
sample_4h.sort(key=lambda x: x["bar_idx"])

all_match_4h = True
for p in sample_4h:
    reported = p["reported_sig"]
    expected = p["expected_sig"]

    if math.isnan(reported) and math.isnan(expected):
        match = True
    elif math.isnan(reported) or math.isnan(expected):
        match = False
    else:
        match = abs(reported - expected) < 0.0001

    status = "OK" if match else "MISMATCH"
    if not match:
        all_match_4h = False

    major_str = "MAJOR" if p["is_major"] else "minor"
    prev_str = f"{p['prev_level']:.4f}" if not math.isnan(p["prev_level"]) else "N/A"

    print(f"[{status}] {p['type']:4} @ bar {p['bar_idx']:3} ({p['timestamp']}) | "
          f"level={p['level']:.4f} prev={prev_str} ATR={p['atr']:.4f} | "
          f"sig={reported:.4f} | {major_str}")

print(f"\n=== 4h Math Verification: {'ALL PASSED' if all_match_4h else 'SOME MISMATCHES'} ===")

print(f"\n\n{'='*60}")
print(f"=== SUMMARY ===")
print(f"{'='*60}")
print(f"1h: {len(all_pivots)} pivots ({major_count} major, {minor_count} minor)")
print(f"4h: {len(pivots_4h)} pivots ({major_count_4h} major, {minor_count_4h} minor)")
print(f"Math verification: 1h={'PASS' if all_match else 'FAIL'}, 4h={'PASS' if all_match_4h else 'FAIL'}")
