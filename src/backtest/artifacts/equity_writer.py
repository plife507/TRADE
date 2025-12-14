"""
Equity curve writer (optional convenience export).

Writes equity_curve.csv with:
- timestamp
- equity
- drawdown_abs
- drawdown_pct
- (optional) additional columns

This is an explicitly derived artifact, separate from the
lossless events.jsonl stream.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any


class EquityWriter:
    """
    Writes equity_curve.csv for a backtest run.
    
    Optional convenience export - the lossless record is in events.jsonl.
    """
    
    def __init__(
        self,
        run_dir: Path,
        filename: str = "equity_curve.csv",
    ):
        """
        Initialize equity writer.
        
        Args:
            run_dir: Directory for run artifacts
            filename: Name of the equity curve file
        """
        self.run_dir = Path(run_dir)
        self.filename = filename
        self._rows: List[Dict[str, Any]] = []
    
    def add_point(
        self,
        timestamp: datetime,
        equity: float,
        drawdown_abs: float = 0.0,
        drawdown_pct: float = 0.0,
        **extra_columns,
    ) -> None:
        """
        Add an equity curve point.
        
        Args:
            timestamp: Point timestamp
            equity: Equity value
            drawdown_abs: Absolute drawdown
            drawdown_pct: Percentage drawdown
            **extra_columns: Additional columns to include
        """
        row = {
            "timestamp": timestamp.isoformat(),
            "equity": equity,
            "drawdown_abs": drawdown_abs,
            "drawdown_pct": drawdown_pct,
            **extra_columns,
        }
        self._rows.append(row)
    
    def add_points(
        self,
        equity_curve: List[Dict[str, Any]],
    ) -> None:
        """
        Add multiple equity curve points.
        
        Args:
            equity_curve: List of dicts with timestamp, equity, etc.
        """
        for point in equity_curve:
            ts = point.get("timestamp")
            if isinstance(ts, datetime):
                ts = ts.isoformat()
            
            self._rows.append({
                "timestamp": ts,
                "equity": point.get("equity", 0),
                "drawdown_abs": point.get("drawdown", point.get("drawdown_abs", 0)),
                "drawdown_pct": point.get("drawdown_pct", 0),
            })
    
    def write(self) -> Optional[Path]:
        """
        Write equity curve to CSV.
        
        Returns:
            Path to written file, or None if no data
        """
        if not self._rows:
            return None
        
        self.run_dir.mkdir(parents=True, exist_ok=True)
        csv_path = self.run_dir / self.filename
        
        # Get all columns from first row
        fieldnames = list(self._rows[0].keys())
        
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self._rows)
        
        return csv_path
    
    def get_rows(self) -> List[Dict[str, Any]]:
        """Get accumulated rows (for testing)."""
        return list(self._rows)
    
    def clear(self) -> None:
        """Clear accumulated rows."""
        self._rows = []

