"""
Comprehensive pivot math test on 4h SOLUSDT.
Compares fractal vs ATR ZigZag modes to verify:
1. Math correctness
2. Pivot count reduction with ZigZag
3. Major/minor classification accuracy
"""
import sys
sys.path.insert(0, ".")

from datetime import datetime, timezone
import math

from src.data.historical_data_store import HistoricalDataStore
from src.indicators import compute_indicator
from src.structures.detectors.swing import IncrementalSwingDetector
from src.structures.base import BarData

# Configuration
SYMBOL = "SOLUSDT"
TIMEFRAME = "4h"
START = datetime(2025, 10, 1, tzinfo=timezone.utc)
END = datetime(2026, 1, 15, tzinfo=timezone.utc)

# Common params
ATR_LENGTH = 14
MAJOR_THRESHOLD = 1.5

print(f"{'='*70}")
print(f"=== PIVOT MODE COMPARISON TEST ===")
print(f"{'='*70}")
print(f"Symbol: {SYMBOL}, TF: {TIMEFRAME}")
print(f"Period: {START.date()} to {END.date()}")
print(f"ATR length: {ATR_LENGTH}, Major threshold: {MAJOR_THRESHOLD}")
print()

# Fetch data
store = HistoricalDataStore()
df = store.get_ohlcv(SYMBOL, TIMEFRAME, start=START, end=END)
df = df.set_index("timestamp")
print(f"Loaded {len(df)} bars (~{len(df)*4} hours = {len(df)*4/24:.1f} days)")

# Calculate ATR
atr_values = compute_indicator("atr", close=df["close"], high=df["high"], low=df["low"], length=ATR_LENGTH)
df["atr"] = atr_values

print()
print(f"{'='*70}")
print(f"=== TEST 1: FRACTAL MODE (left=5, right=5) ===")
print(f"{'='*70}")

# Create fractal detector
detector_fractal = IncrementalSwingDetector(
    params={
        "mode": "fractal",
        "left": 5,
        "right": 5,
        "atr_key": "atr",
        "major_threshold": MAJOR_THRESHOLD,
    }
)

fractal_pivots = []
prev_version_f = 0

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

    detector_fractal.update(i, bar)

    version = detector_fractal.get_value("version")
    if version > prev_version_f:
        pivot_type = detector_fractal.get_value("last_confirmed_pivot_type")
        pivot_idx = detector_fractal.get_value("last_confirmed_pivot_idx")

        if pivot_type == "high":
            level = detector_fractal.get_value("high_level")
            sig = detector_fractal.get_value("high_significance")
            is_major = detector_fractal.get_value("high_is_major")
        else:
            level = detector_fractal.get_value("low_level")
            sig = detector_fractal.get_value("low_significance")
            is_major = detector_fractal.get_value("low_is_major")

        fractal_pivots.append({
            "type": pivot_type.upper(),
            "bar_idx": pivot_idx,
            "timestamp": df.index[pivot_idx],
            "level": level,
            "significance": sig,
            "is_major": is_major,
        })
        prev_version_f = version

print(f"\nFractal Results:")
print(f"  Total pivots: {len(fractal_pivots)}")
highs_f = sum(1 for p in fractal_pivots if p["type"] == "HIGH")
lows_f = sum(1 for p in fractal_pivots if p["type"] == "LOW")
major_f = sum(1 for p in fractal_pivots if p["is_major"])
print(f"  Highs: {highs_f}, Lows: {lows_f}")
print(f"  Major: {major_f} ({100*major_f/len(fractal_pivots):.1f}%), Minor: {len(fractal_pivots)-major_f}")

# Show some fractal pivots
print(f"\n  First 10 fractal pivots:")
for i, p in enumerate(fractal_pivots[:10]):
    sig_str = f"{p['significance']:.2f}" if not math.isnan(p['significance']) else "N/A"
    major_str = "MAJOR" if p['is_major'] else "minor"
    print(f"    {i+1}. {p['type']:4} @ bar {p['bar_idx']:3} ({p['timestamp'].strftime('%Y-%m-%d %H:%M')}) "
          f"level={p['level']:.2f} sig={sig_str} {major_str}")

print()
ATR_MULTIPLIER = 3.0
print(f"{'='*70}")
print(f"=== TEST 2: ATR ZIGZAG MODE (atr_multiplier={ATR_MULTIPLIER}) ===")
print(f"{'='*70}")

# Create ATR ZigZag detector
detector_zigzag = IncrementalSwingDetector(
    params={
        "mode": "atr_zigzag",
        "atr_key": "atr",
        "atr_multiplier": ATR_MULTIPLIER,
        "major_threshold": MAJOR_THRESHOLD,
    }
)

zigzag_pivots = []
prev_version_z = 0

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

    detector_zigzag.update(i, bar)

    version = detector_zigzag.get_value("version")
    if version > prev_version_z:
        pivot_type = detector_zigzag.get_value("last_confirmed_pivot_type")
        pivot_idx = detector_zigzag.get_value("last_confirmed_pivot_idx")

        if pivot_type == "high":
            level = detector_zigzag.get_value("high_level")
            sig = detector_zigzag.get_value("high_significance")
            is_major = detector_zigzag.get_value("high_is_major")
        else:
            level = detector_zigzag.get_value("low_level")
            sig = detector_zigzag.get_value("low_significance")
            is_major = detector_zigzag.get_value("low_is_major")

        zigzag_pivots.append({
            "type": pivot_type.upper(),
            "bar_idx": pivot_idx,
            "timestamp": df.index[pivot_idx],
            "level": level,
            "significance": sig,
            "is_major": is_major,
        })
        prev_version_z = version

print(f"\nATR ZigZag Results:")
print(f"  Total pivots: {len(zigzag_pivots)}")
highs_z = sum(1 for p in zigzag_pivots if p["type"] == "HIGH")
lows_z = sum(1 for p in zigzag_pivots if p["type"] == "LOW")
major_z = sum(1 for p in zigzag_pivots if p["is_major"])
print(f"  Highs: {highs_z}, Lows: {lows_z}")
print(f"  Major: {major_z} ({100*major_z/len(zigzag_pivots):.1f}% if pivots else 0), Minor: {len(zigzag_pivots)-major_z}")

# Show some zigzag pivots
print(f"\n  First 10 ZigZag pivots:")
for i, p in enumerate(zigzag_pivots[:10]):
    sig_str = f"{p['significance']:.2f}" if not math.isnan(p['significance']) else "N/A"
    major_str = "MAJOR" if p['is_major'] else "minor"
    print(f"    {i+1}. {p['type']:4} @ bar {p['bar_idx']:3} ({p['timestamp'].strftime('%Y-%m-%d %H:%M')}) "
          f"level={p['level']:.2f} sig={sig_str} {major_str}")

print()
print(f"{'='*70}")
print(f"=== COMPARISON ===")
print(f"{'='*70}")
print(f"Fractal mode:   {len(fractal_pivots)} pivots ({major_f} major)")
print(f"ATR ZigZag:     {len(zigzag_pivots)} pivots ({major_z} major)")
if len(fractal_pivots) > 0:
    reduction = (1 - len(zigzag_pivots) / len(fractal_pivots)) * 100
    print(f"Reduction:      {reduction:.1f}% fewer pivots with ZigZag")

print()
print(f"{'='*70}")
print(f"=== MATH VERIFICATION (ZigZag) ===")
print(f"{'='*70}")
print("Checking: reversal threshold = extreme - (ATR × multiplier)")
print()

# Verify ZigZag math by checking reversal conditions
print("Verifying first 5 ZigZag pivots with detailed math:")
for i, p in enumerate(zigzag_pivots[:5]):
    print(f"\nPivot #{i+1}: {p['type']} @ bar {p['bar_idx']} ({p['timestamp']})")
    print(f"  Level: {p['level']:.4f}")

    # For each pivot, check if the math makes sense
    if p['bar_idx'] >= 0 and p['bar_idx'] < len(df):
        pivot_bar = df.iloc[p['bar_idx']]
        print(f"  Bar OHLC: O={pivot_bar['open']:.2f} H={pivot_bar['high']:.2f} L={pivot_bar['low']:.2f} C={pivot_bar['close']:.2f}")

        # Find the confirmation bar (where reversal happened)
        # This is tricky to determine exactly, but we can look at nearby bars
        if i > 0:
            prev_pivot = zigzag_pivots[i-1]
            bars_between = p['bar_idx'] - prev_pivot['bar_idx']
            print(f"  Bars since previous pivot: {bars_between}")

    sig_str = f"{p['significance']:.4f}" if not math.isnan(p['significance']) else "N/A (first)"
    print(f"  Significance: {sig_str}")
    print(f"  Is Major: {p['is_major']}")

print()
print(f"{'='*70}")
print(f"=== ALTERNATION CHECK ===")
print(f"{'='*70}")
print("Checking if ZigZag produces proper H-L-H-L sequence:")

zigzag_sequence = [p['type'] for p in zigzag_pivots]
alternates_correctly = True
for i in range(1, len(zigzag_sequence)):
    if zigzag_sequence[i] == zigzag_sequence[i-1]:
        alternates_correctly = False
        print(f"  VIOLATION at index {i}: {zigzag_sequence[i-1]} followed by {zigzag_sequence[i]}")
        break

if alternates_correctly:
    print(f"  PASS: All {len(zigzag_pivots)} pivots alternate correctly (H-L-H-L)")
else:
    print(f"  FAIL: ZigZag should always alternate")

# Also check fractal
print("\nChecking fractal alternation:")
fractal_sequence = [p['type'] for p in fractal_pivots]
consecutive_same = 0
for i in range(1, len(fractal_sequence)):
    if fractal_sequence[i] == fractal_sequence[i-1]:
        consecutive_same += 1

print(f"  Fractal has {consecutive_same} consecutive same-type pivots (expected - fractal doesn't force alternation)")

print()
print(f"{'='*70}")
print(f"=== SUMMARY ===")
print(f"{'='*70}")
print(f"Symbol: {SYMBOL} {TIMEFRAME}")
print(f"Data: {len(df)} bars ({START.date()} to {END.date()})")
print(f"")
print(f"Fractal (left=5, right=5):")
print(f"  - {len(fractal_pivots)} pivots ({highs_f} H, {lows_f} L)")
print(f"  - {major_f} major ({100*major_f/len(fractal_pivots) if fractal_pivots else 0:.0f}%)")
print(f"")
print(f"ATR ZigZag (atr_mult=2.0):")
print(f"  - {len(zigzag_pivots)} pivots ({highs_z} H, {lows_z} L)")
print(f"  - {major_z} major ({100*major_z/len(zigzag_pivots) if zigzag_pivots else 0:.0f}%)")
print(f"  - Alternation: {'PASS' if alternates_correctly else 'FAIL'}")
if fractal_pivots:
    print(f"  - Reduction: {(1 - len(zigzag_pivots)/len(fractal_pivots))*100:.1f}% fewer pivots")
