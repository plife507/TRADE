"""
Market data tools for TRADE trading bot.

These tools provide access to prices, OHLCV, funding rates, orderbooks, and more.
"""

from typing import Optional, Dict, Any, List
from .shared import ToolResult, _get_exchange_manager


def get_price_tool(symbol: str) -> ToolResult:
    """
    Get current price for a symbol.
    
    Args:
        symbol: Trading symbol
    
    Returns:
        ToolResult with current price
    """
    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")
    
    try:
        exchange = _get_exchange_manager()
        price = exchange.get_price(symbol)
        
        if price and price > 0:
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"{symbol}: ${price:,.2f}",
                data={"symbol": symbol, "price": price},
                source="rest_api",
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error=f"Could not get price for {symbol}",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to get price: {str(e)}",
        )


def get_ohlcv_tool(
    symbol: str,
    interval: str = "15",
    limit: int = 100,
) -> ToolResult:
    """
    Get OHLCV (candlestick) data for a symbol.
    
    Args:
        symbol: Trading symbol
        interval: Timeframe (e.g., "1", "5", "15", "60", "240", "D")
        limit: Number of candles to retrieve
    
    Returns:
        ToolResult with OHLCV data
    """
    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")
    
    try:
        exchange = _get_exchange_manager()
        data = exchange.bybit.get_klines(symbol, interval=interval, limit=limit)
        
        # Handle DataFrame or list response
        import pandas as pd
        if isinstance(data, pd.DataFrame):
            candle_count = len(data) if not data.empty else 0
            candles = data.to_dict('records') if candle_count > 0 else []
        elif data is not None:
            candle_count = len(data)
            candles = data
        else:
            candle_count = 0
            candles = []
        
        return ToolResult(
            success=candle_count > 0,
            symbol=symbol,
            message=f"Retrieved {candle_count} candles ({interval}m)",
            data={
                "symbol": symbol,
                "interval": interval,
                "candle_count": candle_count,
                "candles": candles,
            },
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to get OHLCV: {str(e)}",
        )


def get_funding_rate_tool(symbol: str, limit: int = 1) -> ToolResult:
    """
    Get funding rate data for a symbol.
    
    Args:
        symbol: Trading symbol
        limit: Number of funding records to retrieve
    
    Returns:
        ToolResult with funding rate data
    """
    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")
    
    try:
        exchange = _get_exchange_manager()
        funding = exchange.bybit.get_funding_rate(symbol, limit=limit)
        
        if funding and len(funding) > 0:
            rate = float(funding[0].get("fundingRate", 0)) * 100
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"{symbol} funding: {rate:.4f}%",
                data={
                    "symbol": symbol,
                    "funding_rate_pct": rate,
                    "records": funding,
                },
                source="rest_api",
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error="No funding data returned",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to get funding rate: {str(e)}",
        )


def get_open_interest_tool(
    symbol: str,
    interval: str = "5min",
    limit: int = 1,
) -> ToolResult:
    """
    Get open interest data for a symbol.
    
    Args:
        symbol: Trading symbol
        interval: Time interval (e.g., "5min", "15min", "30min", "1h", "4h", "1d")
        limit: Number of records to retrieve
    
    Returns:
        ToolResult with open interest data
    """
    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")
    
    try:
        exchange = _get_exchange_manager()
        oi = exchange.bybit.get_open_interest(symbol, interval=interval, limit=limit)
        
        if oi and len(oi) > 0:
            oi_value = float(oi[0].get("openInterest", 0))
            return ToolResult(
                success=True,
                symbol=symbol,
                message=f"{symbol} OI: {oi_value:,.0f}",
                data={
                    "symbol": symbol,
                    "open_interest": oi_value,
                    "interval": interval,
                    "records": oi,
                },
                source="rest_api",
            )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error="No open interest data returned",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to get open interest: {str(e)}",
        )


def get_orderbook_tool(symbol: str, limit: int = 25) -> ToolResult:
    """
    Get orderbook data for a symbol.
    
    Args:
        symbol: Trading symbol
        limit: Depth of orderbook (levels per side)
    
    Returns:
        ToolResult with orderbook data
    """
    if not symbol or not isinstance(symbol, str):
        return ToolResult(success=False, error="Invalid symbol parameter")
    
    try:
        exchange = _get_exchange_manager()
        orderbook = exchange.bybit.get_orderbook(symbol, limit=limit)
        
        bids = orderbook.get("b", [])
        asks = orderbook.get("a", [])
        
        bid_count = len(bids)
        ask_count = len(asks)
        
        # Get best bid/ask
        best_bid = float(bids[0][0]) if bids else None
        best_ask = float(asks[0][0]) if asks else None
        spread = best_ask - best_bid if best_bid and best_ask else None
        
        return ToolResult(
            success=bid_count > 0 and ask_count > 0,
            symbol=symbol,
            message=f"Orderbook: {bid_count} bids, {ask_count} asks",
            data={
                "symbol": symbol,
                "bid_count": bid_count,
                "ask_count": ask_count,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread": spread,
                "bids": bids,
                "asks": asks,
            },
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to get orderbook: {str(e)}",
        )


def get_instruments_tool(symbol: Optional[str] = None) -> ToolResult:
    """
    Get instrument information for a symbol or all symbols.
    
    Args:
        symbol: Trading symbol (None for all instruments)
    
    Returns:
        ToolResult with instrument details
    """
    try:
        exchange = _get_exchange_manager()
        instruments = exchange.bybit.get_instruments(symbol)
        
        if instruments and len(instruments) > 0:
            if symbol:
                info = instruments[0]
                tick_size = info.get("priceFilter", {}).get("tickSize", "N/A")
                min_qty = info.get("lotSizeFilter", {}).get("minOrderQty", "N/A")
                return ToolResult(
                    success=True,
                    symbol=symbol,
                    message=f"{symbol}: tick={tick_size}, minQty={min_qty}",
                    data={
                        "symbol": symbol,
                        "tick_size": tick_size,
                        "min_order_qty": min_qty,
                        "instrument": info,
                    },
                    source="rest_api",
                )
            else:
                return ToolResult(
                    success=True,
                    message=f"Retrieved {len(instruments)} instruments",
                    data={
                        "count": len(instruments),
                        "instruments": instruments,
                    },
                    source="rest_api",
                )
        else:
            return ToolResult(
                success=False,
                symbol=symbol,
                error="No instrument info returned",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            symbol=symbol,
            error=f"Failed to get instruments: {str(e)}",
        )


def run_market_data_tests_tool(symbol: str) -> ToolResult:
    """
    Run comprehensive market data tests on a symbol.
    
    Tests: price fetch, OHLCV (multiple timeframes), funding rate,
    open interest, orderbook, instrument info.
    
    Args:
        symbol: Symbol to test
    
    Returns:
        ToolResult with all test results
    """
    tests = {}
    
    # Test 1: Price fetch
    price_result = get_price_tool(symbol)
    tests["price_fetch"] = {
        "passed": price_result.success,
        "message": price_result.message if price_result.success else price_result.error,
    }
    
    # Test 2: OHLCV (multiple timeframes)
    try:
        exchange = _get_exchange_manager()
        timeframes = ["1", "15", "60"]
        ohlcv_results = {}
        for tf in timeframes:
            data = exchange.bybit.get_klines(symbol, interval=tf, limit=10)
            ohlcv_results[tf] = len(data) if data else 0
        
        tests["ohlcv_fetch"] = {
            "passed": all(c > 0 for c in ohlcv_results.values()),
            "message": f"1m: {ohlcv_results['1']}, 15m: {ohlcv_results['15']}, 1h: {ohlcv_results['60']}",
            "data": ohlcv_results,
        }
    except Exception as e:
        tests["ohlcv_fetch"] = {"passed": False, "message": str(e)}
    
    # Test 3: Funding rate
    funding_result = get_funding_rate_tool(symbol)
    tests["funding_rate"] = {
        "passed": funding_result.success,
        "message": funding_result.message if funding_result.success else funding_result.error,
    }
    
    # Test 4: Open interest
    oi_result = get_open_interest_tool(symbol)
    tests["open_interest"] = {
        "passed": oi_result.success,
        "message": oi_result.message if oi_result.success else oi_result.error,
    }
    
    # Test 5: Orderbook
    ob_result = get_orderbook_tool(symbol)
    tests["orderbook"] = {
        "passed": ob_result.success,
        "message": ob_result.message if ob_result.success else ob_result.error,
    }
    
    # Test 6: Instrument info
    inst_result = get_instruments_tool(symbol)
    tests["instrument_info"] = {
        "passed": inst_result.success,
        "message": inst_result.message if inst_result.success else inst_result.error,
    }
    
    # Summary
    passed_count = sum(1 for t in tests.values() if t["passed"])
    total_count = len(tests)
    all_passed = passed_count == total_count
    
    return ToolResult(
        success=all_passed,
        symbol=symbol,
        message=f"Market data tests: {passed_count}/{total_count} passed",
        data={
            "tests": tests,
            "passed_count": passed_count,
            "total_count": total_count,
            "all_passed": all_passed,
        },
        source="rest_api",
    )

