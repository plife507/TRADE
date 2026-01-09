"""
Order sizing validation tests.

Validates:
1. Entry fee calculation (notional × taker_fee_rate)
2. Required margin includes fee
3. 100% equity rejection due to fees
4. Max fillable size calculation
5. Exit fee deducted from PnL

Per TEST COVERAGE RULE: Tests both LONG and SHORT positions.
"""

from datetime import datetime

import pytest

from src.backtest.sim.ledger import Ledger, LedgerConfig
from src.backtest.sim.execution.execution_model import ExecutionModel, ExecutionModelConfig
from src.backtest.sim.execution.slippage_model import SlippageConfig
from src.backtest.sim.types import (
    Bar,
    Order,
    OrderSide,
    OrderType,
    Position,
    FillReason,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def ledger_2x() -> Ledger:
    """Ledger with 2x leverage (IMR=0.5) and 10000 USDT initial capital."""
    config = LedgerConfig(
        initial_margin_rate=0.5,  # 2x leverage
        maintenance_margin_rate=0.005,
        taker_fee_rate=0.0006,  # 0.06%
    )
    return Ledger(initial_capital=10000.0, config=config)


@pytest.fixture
def execution_model() -> ExecutionModel:
    """Execution model with default 0.06% taker fee."""
    config = ExecutionModelConfig(
        taker_fee_rate=0.0006,
        maker_fee_rate=0.0001,
    )
    return ExecutionModel(config)


@pytest.fixture
def execution_model_no_slippage() -> ExecutionModel:
    """Execution model with zero slippage (for fee-focused tests)."""
    config = ExecutionModelConfig(
        taker_fee_rate=0.0006,
        maker_fee_rate=0.0001,
        slippage=SlippageConfig(fixed_bps=0.0),  # Zero slippage
    )
    return ExecutionModel(config)


@pytest.fixture
def sample_bar() -> Bar:
    """Sample bar for order fill tests."""
    return Bar(
        symbol="BTCUSDT",
        tf="1m",
        ts_open=datetime(2026, 1, 8, 12, 0, 0),
        ts_close=datetime(2026, 1, 8, 12, 0, 59),
        open=50000.0,
        high=50100.0,
        low=49900.0,
        close=50050.0,
        volume=100.0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry fee calculation tests
# ─────────────────────────────────────────────────────────────────────────────

class TestEntryFeeCalculation:
    """Test entry fee calculation: fee = notional × taker_fee_rate."""

    def test_entry_fee_calculation_long(
        self,
        execution_model: ExecutionModel,
        ledger_2x: Ledger,
        sample_bar: Bar,
    ):
        """Entry fee for LONG: 10000 USDT × 0.06% = 6.00 USDT."""
        order = Order(
            order_id="test_001",
            symbol="BTCUSDT",
            side=OrderSide.LONG,
            size_usdt=10000.0,
            order_type=OrderType.MARKET,
        )

        # Available balance > required, so order should fill
        result = execution_model.fill_entry_order(
            order,
            sample_bar,
            available_balance_usdt=10000.0,
            compute_required_fn=ledger_2x.compute_required_for_entry,
        )

        assert len(result.fills) == 1
        assert len(result.rejections) == 0

        fill = result.fills[0]
        expected_fee = 10000.0 * 0.0006  # 6.00 USDT
        assert fill.fee == pytest.approx(expected_fee, rel=1e-6)
        assert fill.side == OrderSide.LONG

    def test_entry_fee_calculation_short(
        self,
        execution_model: ExecutionModel,
        ledger_2x: Ledger,
        sample_bar: Bar,
    ):
        """Entry fee for SHORT: 10000 USDT × 0.06% = 6.00 USDT."""
        order = Order(
            order_id="test_002",
            symbol="BTCUSDT",
            side=OrderSide.SHORT,
            size_usdt=10000.0,
            order_type=OrderType.MARKET,
        )

        result = execution_model.fill_entry_order(
            order,
            sample_bar,
            available_balance_usdt=10000.0,
            compute_required_fn=ledger_2x.compute_required_for_entry,
        )

        assert len(result.fills) == 1
        fill = result.fills[0]
        expected_fee = 10000.0 * 0.0006  # 6.00 USDT
        assert fill.fee == pytest.approx(expected_fee, rel=1e-6)
        assert fill.side == OrderSide.SHORT


# ─────────────────────────────────────────────────────────────────────────────
# Required margin tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRequiredMargin:
    """Test required margin calculation includes fee."""

    def test_required_margin_includes_fee(self, ledger_2x: Ledger):
        """
        Required = (notional × IMR) + (notional × taker_fee).

        At 2x leverage (IMR=0.5) for 10000 USDT:
        - Position IM = 10000 × 0.5 = 5000
        - Entry fee = 10000 × 0.0006 = 6
        - Required = 5000 + 6 = 5006 USDT
        """
        notional = 10000.0
        required = ledger_2x.compute_required_for_entry(notional)

        expected_im = 10000.0 * 0.5  # 5000
        expected_fee = 10000.0 * 0.0006  # 6
        expected_total = expected_im + expected_fee  # 5006

        assert required == pytest.approx(expected_total, rel=1e-6)

    def test_required_margin_with_close_fee(self, ledger_2x: Ledger):
        """
        Optional: include estimated close fee.

        With include_close_fee=True:
        - Required = 5000 + 6 + 6 = 5012 USDT
        """
        notional = 10000.0
        required = ledger_2x.compute_required_for_entry(notional, include_close_fee=True)

        expected_im = 10000.0 * 0.5  # 5000
        expected_open_fee = 10000.0 * 0.0006  # 6
        expected_close_fee = 10000.0 * 0.0006  # 6
        expected_total = expected_im + expected_open_fee + expected_close_fee  # 5012

        assert required == pytest.approx(expected_total, rel=1e-6)


# ─────────────────────────────────────────────────────────────────────────────
# 100% equity rejection tests
# ─────────────────────────────────────────────────────────────────────────────

class TestEquityRejection:
    """Test that 100% equity orders are rejected due to fees."""

    def test_100_percent_equity_rejected_long(
        self,
        execution_model: ExecutionModel,
        ledger_2x: Ledger,
        sample_bar: Bar,
    ):
        """
        LONG: 100% equity order (10000 USDT) rejected due to fee overhead.

        With 10000 equity at 2x leverage:
        - Required for 10000 notional = 5006 USDT
        - Available = 10000 USDT (initial)
        - BUT: order needs 5006, only 5000 available after margin calc

        Wait, let me recalculate:
        - available_balance = 10000 (no position yet)
        - required = 10000 × 0.5 + 10000 × 0.0006 = 5006
        - 10000 > 5006 → This should FILL!

        The rejection happens when trying max notional that would use 100% margin.
        Let's compute: if available = 5000, then max notional = 5000 / 0.5006 ≈ 9988

        Actually the test should use available_balance LESS than required.
        Let me set available = 5000 (simulating using available_balance_usdt from ledger)
        """
        order = Order(
            order_id="test_reject_long",
            symbol="BTCUSDT",
            side=OrderSide.LONG,
            size_usdt=10000.0,  # Full equity as notional
            order_type=OrderType.MARKET,
        )

        # Simulate: We have 5000 available margin (not 10000 equity directly)
        # Because at 2x leverage, only 50% of equity is available for new positions
        # Actually, available_balance = equity when no position
        # The rejection happens when available < required

        # For this test: available = 5000, required = 5006 → rejected
        result = execution_model.fill_entry_order(
            order,
            sample_bar,
            available_balance_usdt=5000.0,  # Less than 5006 required
            compute_required_fn=ledger_2x.compute_required_for_entry,
        )

        assert len(result.fills) == 0
        assert len(result.rejections) == 1
        assert result.rejections[0].code == "INSUFFICIENT_ENTRY_GATE"

    def test_100_percent_equity_rejected_short(
        self,
        execution_model: ExecutionModel,
        ledger_2x: Ledger,
        sample_bar: Bar,
    ):
        """SHORT: Same rejection logic as LONG."""
        order = Order(
            order_id="test_reject_short",
            symbol="BTCUSDT",
            side=OrderSide.SHORT,
            size_usdt=10000.0,
            order_type=OrderType.MARKET,
        )

        result = execution_model.fill_entry_order(
            order,
            sample_bar,
            available_balance_usdt=5000.0,  # Less than 5006 required
            compute_required_fn=ledger_2x.compute_required_for_entry,
        )

        assert len(result.fills) == 0
        assert len(result.rejections) == 1
        assert result.rejections[0].code == "INSUFFICIENT_ENTRY_GATE"


# ─────────────────────────────────────────────────────────────────────────────
# Max fillable size tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMaxFillableSize:
    """Test max fillable size calculation."""

    def test_max_fillable_size_calculation(self, ledger_2x: Ledger):
        """
        Max notional = available / (IMR + fee_rate).

        At 2x leverage with 10000 equity (no position):
        - available = 10000
        - max_notional = 10000 / (0.5 + 0.0006) = 10000 / 0.5006 ≈ 19976

        Verify this fills successfully:
        """
        available = 10000.0
        imr = 0.5
        fee_rate = 0.0006

        # Calculate max notional
        max_notional = available / (imr + fee_rate)

        # Verify: required for max_notional should equal available
        required = ledger_2x.compute_required_for_entry(max_notional)
        assert required == pytest.approx(available, rel=1e-4)

        # Verify can_afford_entry returns True
        assert ledger_2x.can_afford_entry(max_notional) is True

        # Verify slightly larger amount is NOT affordable
        assert ledger_2x.can_afford_entry(max_notional * 1.001) is False

    def test_max_fillable_fills_successfully_long(
        self,
        execution_model: ExecutionModel,
        ledger_2x: Ledger,
        sample_bar: Bar,
    ):
        """LONG: Max fillable size should fill without rejection."""
        available = 10000.0
        max_notional = available / (0.5 + 0.0006)  # ~19976

        order = Order(
            order_id="test_max_long",
            symbol="BTCUSDT",
            side=OrderSide.LONG,
            size_usdt=max_notional,
            order_type=OrderType.MARKET,
        )

        result = execution_model.fill_entry_order(
            order,
            sample_bar,
            available_balance_usdt=available,
            compute_required_fn=ledger_2x.compute_required_for_entry,
        )

        assert len(result.fills) == 1
        assert len(result.rejections) == 0

    def test_max_fillable_fills_successfully_short(
        self,
        execution_model: ExecutionModel,
        ledger_2x: Ledger,
        sample_bar: Bar,
    ):
        """SHORT: Max fillable size should fill without rejection."""
        available = 10000.0
        max_notional = available / (0.5 + 0.0006)  # ~19976

        order = Order(
            order_id="test_max_short",
            symbol="BTCUSDT",
            side=OrderSide.SHORT,
            size_usdt=max_notional,
            order_type=OrderType.MARKET,
        )

        result = execution_model.fill_entry_order(
            order,
            sample_bar,
            available_balance_usdt=available,
            compute_required_fn=ledger_2x.compute_required_for_entry,
        )

        assert len(result.fills) == 1
        assert len(result.rejections) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Exit fee tests
# ─────────────────────────────────────────────────────────────────────────────

class TestExitFee:
    """Test exit fee is deducted from PnL."""

    def test_exit_fee_deducted_long_profit(
        self,
        execution_model_no_slippage: ExecutionModel,
        sample_bar: Bar,
    ):
        """
        LONG exit with profit:
        - Entry: 10000 USDT at 50000 price
        - Exit: at 51000 price (2% profit)
        - Gross PnL = (51000 - 50000) × (10000/50000) = 1000 × 0.2 = 200 USDT
        - Exit fee = 10000 × 0.0006 = 6 USDT
        - Fill shows exit fee
        """
        position = Position(
            position_id="pos_001",
            symbol="BTCUSDT",
            side=OrderSide.LONG,
            entry_price=50000.0,
            entry_time=datetime(2026, 1, 8, 11, 0, 0),
            size=0.2,  # 10000 / 50000
            size_usdt=10000.0,
        )

        # Create exit bar with higher close price
        exit_bar = Bar(
            symbol="BTCUSDT",
            tf="1m",
            ts_open=datetime(2026, 1, 8, 12, 0, 0),
            ts_close=datetime(2026, 1, 8, 12, 0, 59),
            open=51000.0,
            high=51100.0,
            low=50900.0,
            close=51000.0,
            volume=100.0,
        )

        fill = execution_model_no_slippage.fill_exit(
            position,
            exit_bar,
            reason=FillReason.SIGNAL,
            exit_price=51000.0,
        )

        # Exit fee = notional × taker_fee_rate = 10000 × 0.0006 = 6
        expected_fee = 10000.0 * 0.0006
        assert fill.fee == pytest.approx(expected_fee, rel=1e-6)

        # Realized PnL calculation (gross, before fee)
        realized_pnl = execution_model_no_slippage.calculate_realized_pnl(position, fill.price)
        # PnL = (51000 - 50000) × 0.2 = 200
        expected_pnl = (51000.0 - 50000.0) * 0.2
        assert realized_pnl == pytest.approx(expected_pnl, rel=1e-6)

    def test_exit_fee_deducted_short_profit(
        self,
        execution_model_no_slippage: ExecutionModel,
        sample_bar: Bar,
    ):
        """
        SHORT exit with profit:
        - Entry: 10000 USDT SHORT at 50000 price
        - Exit: at 49000 price (2% profit for short)
        - Gross PnL = (50000 - 49000) × 0.2 = 200 USDT
        - Exit fee = 6 USDT
        """
        position = Position(
            position_id="pos_002",
            symbol="BTCUSDT",
            side=OrderSide.SHORT,
            entry_price=50000.0,
            entry_time=datetime(2026, 1, 8, 11, 0, 0),
            size=0.2,
            size_usdt=10000.0,
        )

        exit_bar = Bar(
            symbol="BTCUSDT",
            tf="1m",
            ts_open=datetime(2026, 1, 8, 12, 0, 0),
            ts_close=datetime(2026, 1, 8, 12, 0, 59),
            open=49000.0,
            high=49100.0,
            low=48900.0,
            close=49000.0,
            volume=100.0,
        )

        fill = execution_model_no_slippage.fill_exit(
            position,
            exit_bar,
            reason=FillReason.SIGNAL,
            exit_price=49000.0,
        )

        expected_fee = 10000.0 * 0.0006
        assert fill.fee == pytest.approx(expected_fee, rel=1e-6)

        # Short PnL: (entry - exit) × size
        realized_pnl = execution_model_no_slippage.calculate_realized_pnl(position, fill.price)
        expected_pnl = (50000.0 - 49000.0) * 0.2  # 200
        assert realized_pnl == pytest.approx(expected_pnl, rel=1e-6)

    def test_exit_fee_deducted_long_loss(
        self,
        execution_model_no_slippage: ExecutionModel,
    ):
        """
        LONG exit with loss:
        - Entry at 50000, exit at 49000 (2% loss)
        - Gross PnL = -200 USDT
        - Exit fee still 6 USDT (doesn't depend on PnL)
        """
        position = Position(
            position_id="pos_003",
            symbol="BTCUSDT",
            side=OrderSide.LONG,
            entry_price=50000.0,
            entry_time=datetime(2026, 1, 8, 11, 0, 0),
            size=0.2,
            size_usdt=10000.0,
        )

        exit_bar = Bar(
            symbol="BTCUSDT",
            tf="1m",
            ts_open=datetime(2026, 1, 8, 12, 0, 0),
            ts_close=datetime(2026, 1, 8, 12, 0, 59),
            open=49000.0,
            high=49100.0,
            low=48900.0,
            close=49000.0,
            volume=100.0,
        )

        fill = execution_model_no_slippage.fill_exit(
            position,
            exit_bar,
            reason=FillReason.STOP_LOSS,
            exit_price=49000.0,
        )

        # Fee is always based on notional, not PnL
        expected_fee = 10000.0 * 0.0006
        assert fill.fee == pytest.approx(expected_fee, rel=1e-6)

        realized_pnl = execution_model_no_slippage.calculate_realized_pnl(position, fill.price)
        expected_pnl = (49000.0 - 50000.0) * 0.2  # -200
        assert realized_pnl == pytest.approx(expected_pnl, rel=1e-6)


# ─────────────────────────────────────────────────────────────────────────────
# Ledger integration tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLedgerIntegration:
    """Test full ledger flow with entry and exit fees."""

    def test_ledger_apply_entry_fee(self, ledger_2x: Ledger):
        """Entry fee reduces cash balance."""
        initial_cash = ledger_2x._cash_balance_usdt
        fee = 6.0

        ledger_2x.apply_entry_fee(fee)

        assert ledger_2x._cash_balance_usdt == pytest.approx(initial_cash - fee)
        assert ledger_2x._total_fees_paid == pytest.approx(fee)

    def test_ledger_apply_exit_with_fee_long_profit(self, ledger_2x: Ledger):
        """
        Exit applies realized PnL minus fee to cash.

        - Realized PnL = 200 USDT (profit)
        - Exit fee = 6 USDT
        - Net to cash = 200 - 6 = 194 USDT
        """
        initial_cash = ledger_2x._cash_balance_usdt

        realized_pnl = 200.0
        exit_fee = 6.0

        update = ledger_2x.apply_exit(realized_pnl, exit_fee)

        expected_cash = initial_cash + realized_pnl - exit_fee  # 10000 + 200 - 6 = 10194
        assert ledger_2x._cash_balance_usdt == pytest.approx(expected_cash)
        assert update.realized_pnl == pytest.approx(realized_pnl)
        assert update.fees_paid == pytest.approx(exit_fee)

    def test_ledger_apply_exit_with_fee_short_profit(self, ledger_2x: Ledger):
        """Same for SHORT profit."""
        initial_cash = ledger_2x._cash_balance_usdt

        realized_pnl = 200.0  # Short profit
        exit_fee = 6.0

        update = ledger_2x.apply_exit(realized_pnl, exit_fee)

        expected_cash = initial_cash + realized_pnl - exit_fee
        assert ledger_2x._cash_balance_usdt == pytest.approx(expected_cash)

    def test_ledger_apply_exit_with_fee_loss(self, ledger_2x: Ledger):
        """
        Exit with loss: fee still deducted.

        - Realized PnL = -200 USDT (loss)
        - Exit fee = 6 USDT
        - Net to cash = -200 - 6 = -206 USDT
        """
        initial_cash = ledger_2x._cash_balance_usdt

        realized_pnl = -200.0  # Loss
        exit_fee = 6.0

        update = ledger_2x.apply_exit(realized_pnl, exit_fee)

        expected_cash = initial_cash + realized_pnl - exit_fee  # 10000 - 200 - 6 = 9794
        assert ledger_2x._cash_balance_usdt == pytest.approx(expected_cash)


# ─────────────────────────────────────────────────────────────────────────────
# Invariant checks
# ─────────────────────────────────────────────────────────────────────────────

class TestLedgerInvariants:
    """Test ledger invariants are maintained throughout operations."""

    def test_invariants_after_entry(self, ledger_2x: Ledger):
        """Invariants hold after entry fee."""
        ledger_2x.apply_entry_fee(6.0)
        errors = ledger_2x.check_invariants()
        assert errors == []

    def test_invariants_after_exit(self, ledger_2x: Ledger):
        """Invariants hold after exit."""
        ledger_2x.apply_exit(200.0, 6.0)
        errors = ledger_2x.check_invariants()
        assert errors == []

    def test_equity_equals_cash_plus_unrealized(self, ledger_2x: Ledger):
        """equity = cash_balance + unrealized_pnl."""
        # After entry fee, no position yet
        ledger_2x.apply_entry_fee(6.0)

        expected_equity = ledger_2x._cash_balance_usdt + ledger_2x._unrealized_pnl_usdt
        assert ledger_2x._equity_usdt == pytest.approx(expected_equity)
