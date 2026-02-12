"""
USDT accounting ledger with invariants.

Maintains Bybit-aligned margin model:
- cash_balance_usdt: realized cash (initial + realized PnL - fees)
- unrealized_pnl_usdt: current mark-to-market unrealized PnL
- equity_usdt = cash_balance_usdt + unrealized_pnl_usdt
- used_margin_usdt = position_value × IMR (Position IM)
- free_margin_usdt = equity_usdt - used_margin_usdt (can be negative)
- available_balance_usdt = max(0, free_margin_usdt)

Invariants:
1. equity_usdt = cash_balance_usdt + unrealized_pnl_usdt
2. free_margin_usdt = equity_usdt - used_margin_usdt
3. available_balance_usdt = max(0, free_margin_usdt)
4. cash_balance_usdt changes only on: fills (PnL + fees), funding

References:
- Bybit margin model: reference/exchanges/bybit/docs/v5/account/wallet-balance.mdx
- Position IM/MM: reference/exchanges/bybit/docs/v5/position/position.mdx
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .types import (
    Position,
    LedgerState,
    LedgerUpdate,
)

if TYPE_CHECKING:
    from ..system_config import RiskProfileConfig


@dataclass
class LedgerConfig:
    """Configuration for ledger accounting."""
    initial_margin_rate: float = 0.5  # IMR = 1/leverage
    maintenance_margin_rate: float = 0.005  # MMR (0.5% Bybit default)
    taker_fee_rate: float | None = None  # Loaded from DEFAULTS if None
    debug_check_invariants: bool = False  # Check invariants after every mutation

    def __post_init__(self) -> None:
        if self.taker_fee_rate is None:
            from src.config.constants import DEFAULTS
            object.__setattr__(self, 'taker_fee_rate', DEFAULTS.fees.taker_rate)
    
    @classmethod
    def from_risk_profile(cls, risk_profile: "RiskProfileConfig") -> "LedgerConfig":
        """Create LedgerConfig from RiskProfileConfig."""
        return cls(
            initial_margin_rate=risk_profile.initial_margin_rate,
            maintenance_margin_rate=risk_profile.maintenance_margin_rate,
            taker_fee_rate=risk_profile.taker_fee_rate,
        )


class Ledger:
    """
    USDT accounting ledger with Bybit-aligned margin model.
    
    Tracks all account balances and enforces invariants.
    """
    
    def __init__(
        self,
        initial_capital: float,
        config: LedgerConfig | None = None,
    ):
        """
        Initialize ledger with starting capital.
        
        Args:
            initial_capital: Starting capital in USDT (quote currency).
                All values are in USDT (quote currency).
            config: Optional ledger configuration
        """
        self._config = config or LedgerConfig()
        self._initial_capital = initial_capital
        
        # Core state
        self._cash_balance_usdt = initial_capital
        self._unrealized_pnl_usdt = 0.0
        self._used_margin_usdt = 0.0
        self._maintenance_margin_usdt = 0.0
        self._total_fees_paid = 0.0
        
        # Derived (computed via invariants)
        self._equity_usdt = initial_capital
        self._free_margin_usdt = initial_capital
        self._available_balance_usdt = initial_capital
    
    @property
    def state(self) -> LedgerState:
        """Get current ledger state."""
        return LedgerState(
            cash_balance_usdt=self._cash_balance_usdt,
            unrealized_pnl_usdt=self._unrealized_pnl_usdt,
            equity_usdt=self._equity_usdt,
            used_margin_usdt=self._used_margin_usdt,
            free_margin_usdt=self._free_margin_usdt,
            available_balance_usdt=self._available_balance_usdt,
            maintenance_margin_usdt=self._maintenance_margin_usdt,
            total_fees_paid=self._total_fees_paid,
        )
    
    def check_invariants(self) -> list[str]:
        """
        Check all ledger invariants.
        
        Returns:
            List of error messages (empty if all invariants hold)
        """
        errors = []
        
        # Invariant 1: equity = cash + unrealized
        expected_equity = self._cash_balance_usdt + self._unrealized_pnl_usdt
        if abs(self._equity_usdt - expected_equity) > 1e-8:
            errors.append(
                f"Invariant violated: equity ({self._equity_usdt:.8f}) != "
                f"cash ({self._cash_balance_usdt:.8f}) + unrealized ({self._unrealized_pnl_usdt:.8f})"
            )
        
        # Invariant 2: free_margin = equity - used_margin
        expected_free = self._equity_usdt - self._used_margin_usdt
        if abs(self._free_margin_usdt - expected_free) > 1e-8:
            errors.append(
                f"Invariant violated: free_margin ({self._free_margin_usdt:.8f}) != "
                f"equity ({self._equity_usdt:.8f}) - used ({self._used_margin_usdt:.8f})"
            )
        
        # Invariant 3: available = max(0, free_margin)
        expected_available = max(0.0, self._free_margin_usdt)
        if abs(self._available_balance_usdt - expected_available) > 1e-8:
            errors.append(
                f"Invariant violated: available ({self._available_balance_usdt:.8f}) != "
                f"max(0, free_margin) ({expected_available:.8f})"
            )
        
        return errors
    
    def _recompute_derived(self) -> None:
        """Recompute derived values from core state."""
        self._equity_usdt = self._cash_balance_usdt + self._unrealized_pnl_usdt
        self._free_margin_usdt = self._equity_usdt - self._used_margin_usdt
        self._available_balance_usdt = max(0.0, self._free_margin_usdt)

        # Debug mode: check invariants after every mutation
        if self._config.debug_check_invariants:
            errors = self.check_invariants()
            if errors:
                raise AssertionError(f"Ledger invariant violation: {errors}")
    
    def update_for_mark_price(
        self,
        position: Position | None,
        mark_price: float,
    ) -> LedgerUpdate:
        """
        Update ledger for current mark price (MTM valuation).
        
        Updates unrealized PnL and margins based on position and mark price.
        
        Args:
            position: Current open position (or None)
            mark_price: Current mark price
            
        Returns:
            LedgerUpdate with current state
        """
        if position is None:
            self._unrealized_pnl_usdt = 0.0
            self._used_margin_usdt = 0.0
            self._maintenance_margin_usdt = 0.0
        else:
            # Calculate unrealized PnL
            self._unrealized_pnl_usdt = position.unrealized_pnl(mark_price)
            
            # Calculate position value at mark
            position_value = position.size * mark_price
            
            # Position IM = position_value × IMR
            self._used_margin_usdt = position_value * self._config.initial_margin_rate
            
            # Maintenance margin = position_value × MMR
            self._maintenance_margin_usdt = position_value * self._config.maintenance_margin_rate
        
        self._recompute_derived()
        
        return LedgerUpdate(
            state=self.state,
            realized_pnl=0.0,
            fees_paid=0.0,
            funding_paid=0.0,
        )
    
    def apply_entry_fee(self, fee: float) -> None:
        """
        Apply entry fee (deduct from cash balance).
        
        Args:
            fee: Fee amount in USD
        """
        self._cash_balance_usdt -= fee
        self._total_fees_paid += fee
        self._recompute_derived()
    
    def apply_exit(
        self,
        realized_pnl: float,
        exit_fee: float,
    ) -> LedgerUpdate:
        """
        Apply full position exit (realize PnL and deduct fee).

        Args:
            realized_pnl: Gross realized PnL (before fees)
            exit_fee: Exit fee in USD

        Returns:
            LedgerUpdate with realized PnL and fees
        """
        # Realize PnL into cash
        self._cash_balance_usdt += realized_pnl - exit_fee
        self._total_fees_paid += exit_fee

        # Clear position-related state (full close)
        self._unrealized_pnl_usdt = 0.0
        self._used_margin_usdt = 0.0
        self._maintenance_margin_usdt = 0.0

        self._recompute_derived()

        return LedgerUpdate(
            state=self.state,
            realized_pnl=realized_pnl,
            fees_paid=exit_fee,
            funding_paid=0.0,
        )

    def apply_partial_exit(
        self,
        realized_pnl: float,
        exit_fee: float,
    ) -> LedgerUpdate:
        """
        Apply partial position exit (realize PnL, keep margin state).

        Unlike apply_exit, this does NOT clear margin/unrealized PnL state.
        Those will be recalculated on the next update_for_mark_price call
        based on the reduced position size.

        Args:
            realized_pnl: Gross realized PnL for closed portion (before fees)
            exit_fee: Exit fee in USD

        Returns:
            LedgerUpdate with realized PnL and fees
        """
        # Realize PnL into cash (partial close)
        self._cash_balance_usdt += realized_pnl - exit_fee
        self._total_fees_paid += exit_fee

        # Do NOT clear position-related state - position is still open
        # update_for_mark_price will recalculate based on reduced position

        self._recompute_derived()

        return LedgerUpdate(
            state=self.state,
            realized_pnl=realized_pnl,
            fees_paid=exit_fee,
            funding_paid=0.0,
        )

    def apply_funding(self, funding_pnl: float) -> LedgerUpdate:
        """
        Apply funding payment.
        
        Positive = received funding, negative = paid funding.
        
        Args:
            funding_pnl: Funding amount (positive = profit)
            
        Returns:
            LedgerUpdate with funding applied
        """
        self._cash_balance_usdt += funding_pnl
        self._recompute_derived()
        
        return LedgerUpdate(
            state=self.state,
            realized_pnl=0.0,
            fees_paid=0.0,
            funding_paid=funding_pnl,
        )
    
    def apply_liquidation_fee(self, fee: float) -> None:
        """
        Apply liquidation fee.
        
        Args:
            fee: Liquidation fee in USD
        """
        self._cash_balance_usdt -= fee
        self._total_fees_paid += fee
        self._recompute_derived()
    
    def compute_required_for_entry(
        self,
        notional_usdt: float,
        include_close_fee: bool = False,
    ) -> float:
        """
        Compute required available balance to enter a position.
        
        Entry gate (Active Order IM):
        - Position IM = notional × IMR
        - Est open fee = notional × taker_fee_rate
        - Est close fee = notional × taker_fee_rate (if include_close_fee)
        
        Args:
            notional_usdt: Position notional in USDT
            include_close_fee: Include estimated close fee
            
        Returns:
            Required USD to open position
        """
        position_im = notional_usdt * self._config.initial_margin_rate
        assert self._config.taker_fee_rate is not None
        est_open_fee = notional_usdt * self._config.taker_fee_rate
        est_close_fee = 0.0
        if include_close_fee:
            est_close_fee = notional_usdt * self._config.taker_fee_rate
        
        return position_im + est_open_fee + est_close_fee
    
    def can_afford_entry(
        self,
        notional_usdt: float,
        include_close_fee: bool = False,
    ) -> bool:
        """
        Check if available balance can afford entry.
        
        Args:
            notional_usdt: Position notional in USDT
            include_close_fee: Include estimated close fee
            
        Returns:
            True if entry is affordable
        """
        required = self.compute_required_for_entry(notional_usdt, include_close_fee)
        return self._available_balance_usdt >= required
    
    @property
    def is_liquidatable(self) -> bool:
        """
        Check if account should be liquidated.
        
        Liquidation occurs when equity <= maintenance margin.
        Only applicable when position is open (maintenance_margin > 0).
        """
        if self._maintenance_margin_usdt <= 0:
            return False
        return self._equity_usdt <= self._maintenance_margin_usdt

