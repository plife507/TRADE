"""
Play Generator for Functional Tests.

Generates test plays from the coverage matrix.
Each indicator/structure/operator gets its own test play.

Usage:
    python -m tests.functional.generator --indicators
    python -m tests.functional.generator --structures
    python -m tests.functional.generator --operators
    python -m tests.functional.generator --all
"""

from pathlib import Path
from typing import Any
import yaml

from .coverage import (
    INDICATOR_COVERAGE,
    STRUCTURE_COVERAGE,
    OPERATOR_COVERAGE,
    IndicatorRole,
    IndicatorCoverage,
)


# Base template for all plays
PLAY_TEMPLATE = """version: "3.0.0"
name: "{name}"
description: "{description}"

symbol: "BTCUSDT"
tf: "15m"

account:
  starting_equity_usdt: 10000.0
  max_leverage: 1.0
  margin_mode: isolated_usdt
  min_trade_notional_usdt: 10.0
  fee_model:
    taker_bps: 5.5
    maker_bps: 2.0
  slippage_bps: 2.0

features:
{features}

actions:
  entry_long:
    all:
{conditions}

position_policy:
  mode: long_only
  exit_mode: sl_tp_only

risk:
  stop_loss_pct: 2.0
  take_profit_pct: 4.0
  max_position_pct: 10.0
"""


class PlayGenerator:
    """Generates test plays from coverage matrix."""

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir or Path("tests/functional/strategies/plays")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_indicator_plays(self) -> list[str]:
        """Generate plays for all indicators."""
        generated = []

        for idx, (name, coverage) in enumerate(INDICATOR_COVERAGE.items(), start=1):
            play_id = f"F_IND_{idx:03d}_{name}"
            filename = f"{play_id}.yml"
            filepath = self.output_dir / filename

            content = self._generate_indicator_play(play_id, name, coverage)

            # Write with LF line endings
            with open(filepath, "w", newline="\n") as f:
                f.write(content)

            generated.append(play_id)
            print(f"  Generated: {filename}")

        return generated

    def _generate_indicator_play(
        self,
        play_id: str,
        indicator_name: str,
        coverage: IndicatorCoverage,
    ) -> str:
        """Generate a single indicator test play."""

        # Build features section
        features_lines = self._build_features(indicator_name, coverage)

        # Build conditions section
        conditions_lines = self._build_conditions(indicator_name, coverage)

        # Build description
        role_str = coverage.role.value
        description = f"Functional test: {indicator_name} ({role_str}). {coverage.notes}"

        return PLAY_TEMPLATE.format(
            name=play_id,
            description=description,
            features=features_lines,
            conditions=conditions_lines,
        )

    def _build_features(self, indicator_name: str, coverage: IndicatorCoverage) -> str:
        """Build the features YAML section."""
        lines = []
        params = coverage.typical_params or {}
        declared_features = set()

        # Get indicator info for multi-output detection
        from src.indicators import get_registry
        registry = get_registry()
        info = registry.get_indicator_info(indicator_name)

        # For HYBRID indicators with crossover test, parse the condition to find referenced features
        # e.g., '["ema_9", "cross_above", "ema_21"]' needs both ema_9 and ema_21 declared
        if coverage.role == IndicatorRole.HYBRID and coverage.test_condition:
            crossover_features = self._extract_crossover_features(
                indicator_name, coverage.test_condition
            )
            for feat_id, feat_length in crossover_features:
                if feat_id not in declared_features:
                    lines.append(f"  {feat_id}:")
                    lines.append(f"    indicator: {indicator_name}")
                    lines.append("    params:")
                    lines.append(f"      length: {feat_length}")
                    declared_features.add(feat_id)

        # If no features declared yet (non-crossover hybrid or trigger), use typical_params
        if not declared_features:
            feature_id = self._build_feature_id(indicator_name, params)
            lines.append(f"  {feature_id}:")
            lines.append(f"    indicator: {indicator_name}")

            if params:
                lines.append("    params:")
                for k, v in params.items():
                    lines.append(f"      {k}: {v}")
            declared_features.add(feature_id)

        # For CONTEXT indicators, add a simple trigger (EMA crossover)
        if coverage.role == IndicatorRole.CONTEXT:
            lines.append("  ema_9:")
            lines.append("    indicator: ema")
            lines.append("    params:")
            lines.append("      length: 9")
            lines.append("  ema_21:")
            lines.append("    indicator: ema")
            lines.append("    params:")
            lines.append("      length: 21")

        return "\n".join(lines)

    def _extract_crossover_features(
        self, indicator_name: str, test_condition: str
    ) -> list[tuple[str, int]]:
        """Extract feature IDs and lengths from crossover test conditions.

        For conditions like '["ema_9", "cross_above", "ema_21"]', returns:
        [("ema_9", 9), ("ema_21", 21)]
        """
        import re

        # Pattern to match feature references like "ema_9", "sma_10", etc.
        pattern = rf'"{indicator_name}_(\d+)"'
        matches = re.findall(pattern, test_condition)

        features = []
        for length_str in matches:
            length = int(length_str)
            feat_id = f"{indicator_name}_{length}"
            features.append((feat_id, length))

        return features

    def _build_conditions(self, indicator_name: str, coverage: IndicatorCoverage) -> str:
        """Build the conditions YAML section."""
        lines = []
        params = coverage.typical_params or {}
        feature_id = self._build_feature_id(indicator_name, params)

        if coverage.role == IndicatorRole.CONTEXT:
            # Context indicators: use EMA cross as trigger + indicator as filter
            lines.append('      - ["ema_9", "cross_above", "ema_21"]')
            # Use the test_condition if it's more than a simple check
            # (e.g., multi-output indicators like ADX need field accessors)
            condition = coverage.test_condition
            if condition and "{" in condition:  # Has field accessor syntax
                lines.append(f"      - {condition}")
            else:
                # Simple validity check
                lines.append(f'      - ["{feature_id}", ">", 0]')
        else:
            # Trigger or Hybrid: use the test_condition directly
            # Parse the test_condition and format it
            condition = coverage.test_condition
            if condition:
                # The condition is already a string representation
                lines.append(f"      - {condition}")
            else:
                # Fallback: simple > 0 check
                lines.append(f'      - ["{feature_id}", ">", 0]')

        return "\n".join(lines)

    def _format_param(self, value: Any) -> str:
        """Format a parameter value for feature ID (remove .0 from whole numbers)."""
        if isinstance(value, float) and value == int(value):
            return str(int(value))
        return str(value)

    def _build_feature_id(self, indicator_name: str, params: dict[str, Any]) -> str:
        """Build parameterized feature ID."""
        if not params:
            return indicator_name

        # Build ID based on indicator type
        if indicator_name in ("ema", "sma", "wma", "dema", "tema", "trima", "zlma", "kama", "rsi", "atr", "natr", "cci", "willr", "roc", "mom", "mfi", "cmf", "cmo", "linreg", "midprice", "trix"):
            # Single length param
            length = params.get("length", 14)
            return f"{indicator_name}_{length}"

        elif indicator_name == "alma":
            length = params.get("length", 20)
            return f"{indicator_name}_{length}"

        elif indicator_name == "macd":
            fast = params.get("fast", 12)
            slow = params.get("slow", 26)
            signal = params.get("signal", 9)
            return f"macd_{fast}_{slow}_{signal}"

        elif indicator_name == "bbands":
            length = params.get("length", 20)
            std = params.get("std", 2)
            return f"bbands_{length}_{self._format_param(std)}"

        elif indicator_name == "stoch":
            k = params.get("k", 14)
            d = params.get("d", 3)
            smooth_k = params.get("smooth_k", 3)
            return f"stoch_{k}_{d}_{smooth_k}"

        elif indicator_name == "stochrsi":
            length = params.get("length", 14)
            rsi_length = params.get("rsi_length", 14)
            k = params.get("k", 3)
            d = params.get("d", 3)
            return f"stochrsi_{length}_{rsi_length}_{k}_{d}"

        elif indicator_name == "adx":
            length = params.get("length", 14)
            return f"adx_{length}"

        elif indicator_name == "aroon":
            length = params.get("length", 25)
            return f"aroon_{length}"

        elif indicator_name == "kc":
            length = params.get("length", 20)
            scalar = params.get("scalar", 1.5)
            return f"kc_{length}_{self._format_param(scalar)}"

        elif indicator_name == "donchian":
            lower = params.get("lower_length", 20)
            upper = params.get("upper_length", 20)
            return f"donchian_{lower}_{upper}"

        elif indicator_name == "supertrend":
            length = params.get("length", 10)
            mult = params.get("multiplier", 3.0)
            # Format multiplier without decimal if whole number
            mult_str = str(int(mult)) if mult == int(mult) else str(mult)
            return f"supertrend_{length}_{mult_str}"

        elif indicator_name == "psar":
            af0 = params.get("af0", 0.02)
            af = params.get("af", 0.02)
            max_af = params.get("max_af", 0.2)
            return f"psar_{self._format_param(af0)}_{self._format_param(af)}_{self._format_param(max_af)}"

        elif indicator_name == "squeeze":
            bb_length = params.get("bb_length", 20)
            bb_std = params.get("bb_std", 2.0)
            kc_length = params.get("kc_length", 20)
            kc_scalar = params.get("kc_scalar", 1.5)
            return f"squeeze_{bb_length}_{self._format_param(bb_std)}_{kc_length}_{self._format_param(kc_scalar)}"

        elif indicator_name == "vortex":
            length = params.get("length", 14)
            return f"vortex_{length}"

        elif indicator_name == "dm":
            length = params.get("length", 14)
            return f"dm_{length}"

        elif indicator_name == "fisher":
            length = params.get("length", 9)
            return f"fisher_{length}"

        elif indicator_name in ("tsi", "kvo"):
            fast = params.get("fast", 13)
            slow = params.get("slow", 25)
            signal = params.get("signal", 13)
            return f"{indicator_name}_{fast}_{slow}_{signal}"

        elif indicator_name == "uo":
            fast = params.get("fast", 7)
            medium = params.get("medium", 14)
            slow = params.get("slow", 28)
            return f"uo_{fast}_{medium}_{slow}"

        elif indicator_name == "ppo":
            fast = params.get("fast", 12)
            slow = params.get("slow", 26)
            signal = params.get("signal", 9)
            return f"ppo_{fast}_{slow}_{signal}"

        elif indicator_name == "vwap":
            anchor = params.get("anchor", "D")
            return f"vwap_{anchor}"

        elif indicator_name in ("obv", "ohlc4"):
            return indicator_name

        else:
            # Default: just use indicator name
            return indicator_name

    def generate_all(self) -> dict[str, list[str]]:
        """Generate all test plays."""
        results = {}

        print("\n[GENERATOR] Generating Indicator Plays...")
        results["indicators"] = self.generate_indicator_plays()

        # TODO: Add structure and operator plays
        # print("\n[GENERATOR] Generating Structure Plays...")
        # results["structures"] = self.generate_structure_plays()

        # print("\n[GENERATOR] Generating Operator Plays...")
        # results["operators"] = self.generate_operator_plays()

        return results


def generate_indicator_plays(output_dir: Path | None = None) -> list[str]:
    """Convenience function to generate indicator plays."""
    generator = PlayGenerator(output_dir=output_dir)
    return generator.generate_indicator_plays()


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    """CLI entry point for play generator."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate functional test plays from coverage matrix",
    )

    parser.add_argument(
        "--indicators",
        action="store_true",
        help="Generate indicator test plays",
    )
    parser.add_argument(
        "--structures",
        action="store_true",
        help="Generate structure test plays",
    )
    parser.add_argument(
        "--operators",
        action="store_true",
        help="Generate operator test plays",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate all test plays",
    )
    parser.add_argument(
        "--output-dir",
        default="tests/functional/strategies/plays",
        help="Output directory for plays",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be generated without writing",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    generator = PlayGenerator(output_dir=output_dir)

    if args.all or (not args.indicators and not args.structures and not args.operators):
        # Default: generate all
        results = generator.generate_all()
        total = sum(len(v) for v in results.values())
        print(f"\n[DONE] Generated {total} plays")

    elif args.indicators:
        plays = generator.generate_indicator_plays()
        print(f"\n[DONE] Generated {len(plays)} indicator plays")

    # TODO: Add --structures and --operators handling


if __name__ == "__main__":
    main()
