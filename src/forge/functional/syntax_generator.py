"""
Syntax Test Generator.

Generates test plays for DSL syntax coverage and position mode testing.

Usage:
    python -m tests.functional.syntax_generator --typical
    python -m tests.functional.syntax_generator --edge-cases
    python -m tests.functional.syntax_generator --positions
    python -m tests.functional.syntax_generator --all
"""

from pathlib import Path
import json

from .syntax_coverage import (
    ALL_SYNTAX_TESTS,
    TYPICAL_SYNTAX,
    EDGE_CASE_SYNTAX,
    POSITION_MODE_TESTS,
    SyntaxTest,
    SyntaxCategory,
)


# =============================================================================
# TEMPLATES
# =============================================================================

LONG_ONLY_TEMPLATE = '''version: "3.0.0"
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
'''

SHORT_ONLY_TEMPLATE = '''version: "3.0.0"
name: "{name}"
description: "{description}"

# Using SOL for short tests - had significant downtrends in 2025:
# - October 2025: $16B liquidation crash (20-40% drops)
# - Dec 1, 2025: Sharp sell-off (-9%)
# Suggested test windows: 2025-10-01 to 2025-10-20, 2025-11-25 to 2025-12-15
symbol: "SOLUSDT"
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
  entry_short:
    all:
{conditions}

position_policy:
  mode: short_only
  exit_mode: sl_tp_only

risk:
  stop_loss_pct: 2.0
  take_profit_pct: 4.0
  max_position_pct: 10.0
'''

class SyntaxTestGenerator:
    """Generates syntax test plays."""

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir or Path("tests/functional/strategies/plays")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_typical_tests(self) -> list[str]:
        """Generate typical syntax test plays."""
        return self._generate_tests(TYPICAL_SYNTAX, "F_SYN")

    def generate_edge_case_tests(self) -> list[str]:
        """Generate edge case syntax test plays."""
        return self._generate_tests(EDGE_CASE_SYNTAX, "F_EDGE")

    def generate_position_mode_tests(self) -> list[str]:
        """Generate position mode test plays.

        Currently only generates short_only tests.
        long_short mode requires engine enhancement (position flip logic).
        """
        generated = []

        for name, test in POSITION_MODE_TESTS.items():
            play_id = name
            filename = f"{play_id}.yml"
            filepath = self.output_dir / filename

            # All position mode tests are currently short_only
            # (long_short requires engine enhancement - see syntax_coverage.py)
            content = self._generate_short_only_play(play_id, test)

            with open(filepath, "w", newline="\n") as f:
                f.write(content)

            generated.append(play_id)
            print(f"  Generated: {filename}")

        return generated

    def _generate_tests(self, tests: dict[str, SyntaxTest], prefix: str) -> list[str]:
        """Generate test plays from a dict of syntax tests."""
        generated = []

        for name, test in tests.items():
            play_id = name
            filename = f"{play_id}.yml"
            filepath = self.output_dir / filename

            content = self._generate_long_only_play(play_id, test)

            with open(filepath, "w", newline="\n") as f:
                f.write(content)

            generated.append(play_id)
            print(f"  Generated: {filename}")

        return generated

    def _generate_long_only_play(self, play_id: str, test: SyntaxTest) -> str:
        """Generate a long-only test play."""
        features = self._build_features(test.features)
        conditions = self._build_conditions(test.condition)

        return LONG_ONLY_TEMPLATE.format(
            name=play_id,
            description=test.description,
            features=features,
            conditions=conditions,
        )

    def _generate_short_only_play(self, play_id: str, test: SyntaxTest) -> str:
        """Generate a short-only test play."""
        features = self._build_features(test.features)
        conditions = self._build_conditions(test.condition)

        return SHORT_ONLY_TEMPLATE.format(
            name=play_id,
            description=test.description,
            features=features,
            conditions=conditions,
        )

    def _generate_long_short_play(self, play_id: str, test: SyntaxTest) -> str:
        """Generate a long/short test play."""
        features = self._build_features(test.features)
        long_conditions = self._build_conditions(test.condition)

        # Generate inverse condition for short
        short_condition = self._invert_condition(test)
        short_conditions = self._build_conditions(short_condition)

        return LONG_SHORT_TEMPLATE.format(
            name=play_id,
            description=test.description,
            features=features,
            long_conditions=long_conditions,
            short_conditions=short_conditions,
        )

    def _invert_condition(self, test: SyntaxTest) -> str:
        """Create inverse condition for short entry.

        Note: This method is for future long_short mode (not yet implemented).
        Currently only short_only mode is tested.
        """
        cond = test.condition

        # Handle specific known patterns
        if isinstance(cond, str):
            # RSI: oversold -> overbought
            if '"lt", 30' in cond:
                return cond.replace("lt", "gt").replace("30", "70")

            # EMA cross: cross_above -> cross_below
            if "cross_above" in cond:
                return cond.replace("cross_above", "cross_below")

            # SuperTrend direction: 1 -> -1
            if '"eq", 1' in cond:
                return cond.replace("1]", "-1]")

        return cond  # Fallback: same condition

    def _build_features(self, features: dict[str, dict]) -> str:
        """Build features YAML section."""
        lines = []

        for feat_id, config in features.items():
            if not config:  # Built-in like "close"
                continue

            lines.append(f"  {feat_id}:")
            if "indicator" in config:
                lines.append(f"    indicator: {config['indicator']}")
            if "params" in config and config["params"]:
                lines.append("    params:")
                for k, v in config["params"].items():
                    lines.append(f"      {k}: {v}")

        return "\n".join(lines) if lines else "  # No features (uses built-ins)"

    def _build_conditions(self, condition: str | dict) -> str:
        """Build conditions YAML section."""
        lines = []

        if isinstance(condition, str):
            # Simple string condition
            lines.append(f"      - {condition}")
        elif isinstance(condition, dict):
            # Nested condition (all/any/not)
            yaml_str = self._dict_to_yaml(condition, indent=6)
            lines.append(yaml_str)

        return "\n".join(lines)

    def _dict_to_yaml(self, d: dict, indent: int = 0) -> str:
        """Convert nested condition dict to YAML string."""
        lines = []
        prefix = " " * indent

        for key, value in d.items():
            if key in ("all", "any"):
                lines.append(f"{prefix}- {key}:")
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            lines.append(f"{prefix}    - {item}")
                        elif isinstance(item, dict):
                            nested = self._dict_to_yaml(item, indent + 4)
                            lines.append(nested)
            elif key == "not":
                lines.append(f"{prefix}- not: {value}")

        return "\n".join(lines)

    def generate_all(self) -> dict[str, list[str]]:
        """Generate all syntax tests."""
        results = {}

        print("\n[GENERATOR] Generating Typical Syntax Tests...")
        results["typical"] = self.generate_typical_tests()

        print("\n[GENERATOR] Generating Edge Case Tests...")
        results["edge_cases"] = self.generate_edge_case_tests()

        print("\n[GENERATOR] Generating Position Mode Tests...")
        results["positions"] = self.generate_position_mode_tests()

        return results


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate syntax and position mode test plays",
    )

    parser.add_argument("--typical", action="store_true", help="Generate typical syntax tests")
    parser.add_argument("--edge-cases", action="store_true", help="Generate edge case tests")
    parser.add_argument("--positions", action="store_true", help="Generate position mode tests")
    parser.add_argument("--all", action="store_true", help="Generate all tests")
    parser.add_argument("--output-dir", default="tests/functional/strategies/plays")

    args = parser.parse_args()

    generator = SyntaxTestGenerator(output_dir=Path(args.output_dir))

    if args.all or (not args.typical and not args.edge_cases and not args.positions):
        results = generator.generate_all()
        total = sum(len(v) for v in results.values())
        print(f"\n[DONE] Generated {total} syntax test plays")

    else:
        if args.typical:
            plays = generator.generate_typical_tests()
            print(f"\n[DONE] Generated {len(plays)} typical syntax tests")

        if args.edge_cases:
            plays = generator.generate_edge_case_tests()
            print(f"\n[DONE] Generated {len(plays)} edge case tests")

        if args.positions:
            plays = generator.generate_position_mode_tests()
            print(f"\n[DONE] Generated {len(plays)} position mode tests")


if __name__ == "__main__":
    main()
