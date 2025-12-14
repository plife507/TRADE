"""
Deterministic hashing utilities for backtest artifacts.

Provides hash functions for:
- Trades list (for replay determinism)
- Equity curve (for replay determinism)
- IdeaCard (for config identity)

All hash functions produce deterministic, reproducible hashes
from the same input data across runs.
"""

import hashlib
import json
from typing import List, Dict, Any, Optional

from ..types import Trade, EquityPoint


def compute_trades_hash(trades: List[Trade]) -> str:
    """
    Compute deterministic hash of trades list.
    
    Args:
        trades: List of Trade objects
        
    Returns:
        SHA256 hash (first 16 chars) of serialized trades
    """
    # Serialize trades to dicts
    trades_data = []
    for t in trades:
        if hasattr(t, 'to_dict'):
            trades_data.append(t.to_dict())
        elif isinstance(t, dict):
            trades_data.append(t)
        else:
            # Fallback: extract key fields
            trades_data.append({
                "entry_time": str(getattr(t, 'entry_time', '')),
                "exit_time": str(getattr(t, 'exit_time', '')),
                "side": getattr(t, 'side', ''),
                "entry_price": getattr(t, 'entry_price', 0),
                "exit_price": getattr(t, 'exit_price', 0),
                "net_pnl": getattr(t, 'net_pnl', 0),
            })
    
    # Sort keys for determinism
    serialized = json.dumps(trades_data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:16]


def compute_equity_hash(equity_curve: List[EquityPoint]) -> str:
    """
    Compute deterministic hash of equity curve.
    
    Args:
        equity_curve: List of EquityPoint objects
        
    Returns:
        SHA256 hash (first 16 chars) of serialized equity curve
    """
    # Serialize equity points
    equity_data = []
    for e in equity_curve:
        if hasattr(e, 'to_dict'):
            equity_data.append(e.to_dict())
        elif isinstance(e, dict):
            equity_data.append(e)
        else:
            # Fallback: extract key fields
            equity_data.append({
                "timestamp": str(getattr(e, 'timestamp', '')),
                "equity": getattr(e, 'equity', 0),
            })
    
    serialized = json.dumps(equity_data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:16]


def compute_run_hash(
    trades_hash: str,
    equity_hash: str,
    idea_card_hash: Optional[str] = None,
) -> str:
    """
    Compute combined run hash from component hashes.
    
    Args:
        trades_hash: Hash of trades list
        equity_hash: Hash of equity curve
        idea_card_hash: Optional hash of IdeaCard config
        
    Returns:
        Combined SHA256 hash (first 16 chars)
    """
    components = {
        "trades": trades_hash,
        "equity": equity_hash,
    }
    if idea_card_hash:
        components["idea_card"] = idea_card_hash
    
    serialized = json.dumps(components, sort_keys=True)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:16]


def compute_artifact_file_hash(file_path: str) -> str:
    """
    Compute SHA256 hash of a file's contents.
    
    Args:
        file_path: Path to file
        
    Returns:
        Full SHA256 hash of file contents
    """
    with open(file_path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

