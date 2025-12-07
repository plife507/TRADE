"""
Bybit account and position methods.

Contains: get_balance, get_positions, get_account_info, get_fee_rates,
and UTA extended methods (transaction_log, collateral, borrow, etc.)
"""

from typing import Dict, List, Any, Optional, TYPE_CHECKING

from ..utils.time_range import TimeRange

if TYPE_CHECKING:
    from .bybit_client import BybitClient


def get_balance(client: "BybitClient", account_type: str = "UNIFIED") -> Dict:
    """Get account balance."""
    client._private_limiter.acquire()
    
    response = client._session.get_wallet_balance(accountType=account_type)
    result = client._extract_result(response)
    
    balances = result.get("list", [])
    if balances:
        return balances[0]
    return {}


def get_positions(
    client: "BybitClient", symbol: str = None, settle_coin: str = "USDT", category: str = "linear"
) -> List[Dict]:
    """Get open positions."""
    client._private_limiter.acquire()
    
    kwargs = {"category": category}
    if symbol:
        kwargs["symbol"] = symbol
    else:
        kwargs["settleCoin"] = settle_coin
    
    response = client._session.get_positions(**kwargs)
    
    result = client._extract_result(response)
    return result.get("list", [])


def get_account_info(client: "BybitClient") -> Dict:
    """Get account info (margin mode, etc)."""
    client._private_limiter.acquire()
    
    response = client._session.get_account_info()
    return client._extract_result(response)


def get_fee_rates(client: "BybitClient", symbol: str = None, category: str = "linear") -> Dict:
    """Get fee rates for the account."""
    client._private_limiter.acquire()
    
    kwargs = {"category": category}
    if symbol:
        kwargs["symbol"] = symbol
    
    response = client._session.get_fee_rates(**kwargs)
    result = client._extract_result(response)
    return result.get("list", [])


# ==================== UTA Extended Methods ====================

def get_transaction_log(
    client: "BybitClient",
    time_range: TimeRange,
    account_type: str = "UNIFIED",
    category: str = None,
    currency: str = None,
    base_coin: str = None,
    log_type: str = None,
    limit: int = 50,
    cursor: str = None,
) -> Dict:
    """Get transaction logs in Unified account."""
    client._private_limiter.acquire()
    
    time_params = time_range.to_bybit_params()
    client.logger.debug(f"get_transaction_log: {time_range.label} ({time_range.format_range()})")
    
    kwargs = {
        "accountType": account_type,
        "limit": min(limit, 50),
        "startTime": time_params["startTime"],
        "endTime": time_params["endTime"],
    }
    if category:
        kwargs["category"] = category
    if currency:
        kwargs["currency"] = currency
    if base_coin:
        kwargs["baseCoin"] = base_coin
    if log_type:
        kwargs["type"] = log_type
    if cursor:
        kwargs["cursor"] = cursor
    
    response = client._session.get_transaction_log(**kwargs)
    return client._extract_result(response)


def get_collateral_info(client: "BybitClient", currency: str = None) -> List[Dict]:
    """Get collateral info for coins."""
    client._private_limiter.acquire()
    
    kwargs = {}
    if currency:
        kwargs["currency"] = currency
    
    response = client._session.get_collateral_info(**kwargs)
    result = client._extract_result(response)
    return result.get("list", [])


def set_collateral_coin(client: "BybitClient", coin: str, switch: str) -> Dict:
    """Enable/disable a coin as collateral."""
    client._private_limiter.acquire()
    
    response = client._session.set_collateral_switch(
        coin=coin,
        collateralSwitch=switch,
    )
    return client._extract_result(response)


def batch_set_collateral_coin(client: "BybitClient", coins: List[Dict[str, str]]) -> Dict:
    """Batch set collateral coins."""
    client._private_limiter.acquire()
    
    response = client._session.batch_set_collateral_coin(request=coins)
    return client._extract_result(response)


def get_borrow_history(
    client: "BybitClient",
    time_range: TimeRange,
    currency: str = None,
    limit: int = 50,
    cursor: str = None,
) -> Dict:
    """Get borrow history for Unified account."""
    client._private_limiter.acquire()
    
    time_params = time_range.to_bybit_params()
    client.logger.debug(f"get_borrow_history: {time_range.label} ({time_range.format_range()})")
    
    kwargs = {
        "limit": min(limit, 50),
        "startTime": time_params["startTime"],
        "endTime": time_params["endTime"],
    }
    if currency:
        kwargs["currency"] = currency
    if cursor:
        kwargs["cursor"] = cursor
    
    response = client._session.get_borrow_history(**kwargs)
    return client._extract_result(response)


def repay_liability(client: "BybitClient", coin: str = None) -> Dict:
    """Repay liabilities in Unified account."""
    client._private_limiter.acquire()
    
    kwargs = {}
    if coin:
        kwargs["coin"] = coin
    
    response = client._session.repay_liability(**kwargs)
    return client._extract_result(response)


def get_coin_greeks(client: "BybitClient", base_coin: str = None) -> List[Dict]:
    """Get options Greeks for coins."""
    client._private_limiter.acquire()
    
    kwargs = {}
    if base_coin:
        kwargs["baseCoin"] = base_coin
    
    response = client._session.get_coin_greeks(**kwargs)
    result = client._extract_result(response)
    return result.get("list", [])


def set_account_margin_mode(client: "BybitClient", margin_mode: str) -> Dict:
    """Set account margin mode (REGULAR_MARGIN or PORTFOLIO_MARGIN)."""
    client._private_limiter.acquire()
    
    response = client._session.set_margin_mode(setMarginMode=margin_mode)
    return client._extract_result(response)


def upgrade_to_unified_account(client: "BybitClient") -> Dict:
    """Upgrade to Unified Trading Account."""
    client._private_limiter.acquire()
    
    response = client._session.upgrade_to_unified_trading_account()
    return client._extract_result(response)


def get_transferable_amount(client: "BybitClient", coin: str) -> Dict:
    """Get amount available to transfer out."""
    client._private_limiter.acquire()
    
    response = client._session.get_spot_margin_trade_borrow_amount(coin=coin)
    result = client._extract_result(response)
    return result


def get_mmp_state(client: "BybitClient", base_coin: str) -> Dict:
    """Get Market Maker Protection state."""
    client._private_limiter.acquire()
    
    response = client._session.get_mmp_state(baseCoin=base_coin)
    return client._extract_result(response)


def set_mmp(
    client: "BybitClient",
    base_coin: str,
    window: int,
    frozen_period: int,
    qty_limit: str,
    delta_limit: str,
) -> Dict:
    """Configure Market Maker Protection."""
    client._private_limiter.acquire()
    
    response = client._session.set_mmp(
        baseCoin=base_coin,
        window=str(window),
        frozenPeriod=str(frozen_period),
        qtyLimit=qty_limit,
        deltaLimit=delta_limit,
    )
    return client._extract_result(response)


def reset_mmp(client: "BybitClient", base_coin: str) -> Dict:
    """Reset MMP status."""
    client._private_limiter.acquire()
    
    response = client._session.reset_mmp(baseCoin=base_coin)
    return client._extract_result(response)


def get_borrow_quota(
    client: "BybitClient",
    category: str,
    symbol: str,
    side: str,
) -> Dict:
    """Get borrow quota for spot margin trading."""
    client._private_limiter.acquire()
    
    response = client._session.get_spot_margin_trade_borrow_quota(
        category=category,
        symbol=symbol,
        side=side,
    )
    return client._extract_result(response)

