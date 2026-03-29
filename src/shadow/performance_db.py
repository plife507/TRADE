"""
ShadowPerformanceDB — DuckDB for long-term shadow performance tracking.

Separate database file (data/shadow/shadow_performance.duckdb) to avoid
DuckDB lock conflicts with backtest/live/demo databases.

Design:
- Single writer pattern: only the orchestrator flush loop writes
- Batch inserts: accumulate rows, INSERT in one transaction
- Read queries: for CLI stats/leaderboard/equity commands
- Schema auto-migration: CREATE TABLE IF NOT EXISTS on init
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from ..config.constants import PROJECT_ROOT
from ..utils.logger import get_module_logger

from .types import ShadowSnapshot, ShadowTrade

logger = get_module_logger(__name__)

SHADOW_DB_PATH = PROJECT_ROOT / "data" / "shadow" / "shadow_performance.duckdb"


class ShadowPerformanceDB:
    """DuckDB interface for shadow performance data.

    Thread safety: designed for single-writer (orchestrator flush loop).
    Read queries (CLI) should use a separate connection or run between
    flush cycles.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or SHADOW_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: duckdb.DuckDBPyConnection | None = None

    def open(self) -> None:
        """Open database connection and ensure schema exists."""
        self._conn = duckdb.connect(str(self._db_path))
        self._ensure_schema()
        logger.info("ShadowPerformanceDB opened: %s", self._db_path)

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    # ── Schema ──────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        """Create tables if they don't exist."""
        assert self._conn is not None

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS shadow_instances (
                instance_id VARCHAR PRIMARY KEY,
                play_id VARCHAR NOT NULL,
                symbol VARCHAR NOT NULL,
                exec_tf VARCHAR NOT NULL,
                initial_equity_usdt DOUBLE NOT NULL,
                started_at TIMESTAMP NOT NULL,
                stopped_at TIMESTAMP,
                stop_reason VARCHAR
            )
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS shadow_snapshots (
                instance_id VARCHAR NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                equity_usdt DOUBLE,
                cash_balance_usdt DOUBLE,
                unrealized_pnl_usdt DOUBLE,
                position_side VARCHAR,
                position_size_usdt DOUBLE,
                mark_price DOUBLE,
                cumulative_pnl_usdt DOUBLE,
                total_trades INTEGER,
                winning_trades INTEGER,
                max_drawdown_pct DOUBLE,
                funding_rate DOUBLE,
                atr_pct DOUBLE,
                PRIMARY KEY (instance_id, timestamp)
            )
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS shadow_trades (
                trade_id VARCHAR PRIMARY KEY,
                instance_id VARCHAR NOT NULL,
                play_id VARCHAR NOT NULL,
                symbol VARCHAR NOT NULL,
                direction VARCHAR NOT NULL,
                entry_time TIMESTAMP NOT NULL,
                exit_time TIMESTAMP NOT NULL,
                entry_price DOUBLE NOT NULL,
                exit_price DOUBLE NOT NULL,
                size_usdt DOUBLE NOT NULL,
                pnl_usdt DOUBLE,
                fees_usdt DOUBLE,
                exit_reason VARCHAR,
                mae_pct DOUBLE,
                mfe_pct DOUBLE,
                duration_minutes DOUBLE,
                entry_funding_rate DOUBLE,
                entry_atr_pct DOUBLE
            )
        """)

    # ── Write (batch) ───────────────────────────────────────────

    def register_instance(
        self,
        instance_id: str,
        play_id: str,
        symbol: str,
        exec_tf: str,
        initial_equity: float,
        started_at_iso: str,
    ) -> None:
        """Register a new shadow instance."""
        assert self._conn is not None
        self._conn.execute(
            """INSERT OR REPLACE INTO shadow_instances
               (instance_id, play_id, symbol, exec_tf, initial_equity_usdt, started_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [instance_id, play_id, symbol, exec_tf, initial_equity, started_at_iso],
        )

    def mark_instance_stopped(self, instance_id: str, stop_reason: str) -> None:
        """Mark an instance as stopped."""
        assert self._conn is not None
        from ..utils.datetime_utils import utc_now
        self._conn.execute(
            "UPDATE shadow_instances SET stopped_at = ?, stop_reason = ? WHERE instance_id = ?",
            [utc_now().isoformat(), stop_reason, instance_id],
        )

    def batch_write_snapshots(self, snapshots: list[ShadowSnapshot]) -> None:
        """Batch insert snapshots. Called by orchestrator flush loop."""
        if not snapshots or self._conn is None:
            return

        rows = [
            (
                s.instance_id, s.timestamp.isoformat(), s.equity_usdt,
                s.cash_balance_usdt, s.unrealized_pnl_usdt, s.position_side,
                s.position_size_usdt, s.mark_price, s.cumulative_pnl_usdt,
                s.total_trades, s.winning_trades, s.max_drawdown_pct,
                s.funding_rate, s.atr_pct,
            )
            for s in snapshots
        ]

        self._conn.executemany(
            """INSERT INTO shadow_snapshots
               (instance_id, timestamp, equity_usdt, cash_balance_usdt,
                unrealized_pnl_usdt, position_side, position_size_usdt,
                mark_price, cumulative_pnl_usdt, total_trades, winning_trades,
                max_drawdown_pct, funding_rate, atr_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )

    def batch_write_trades(self, trades: list[ShadowTrade]) -> None:
        """Batch insert trades. Called by orchestrator flush loop."""
        if not trades or self._conn is None:
            return

        rows = [
            (
                t.trade_id, t.instance_id, t.play_id, t.symbol, t.direction,
                t.entry_time.isoformat(), t.exit_time.isoformat(),
                t.entry_price, t.exit_price, t.size_usdt, t.pnl_usdt,
                t.fees_usdt, t.exit_reason, t.mae_pct, t.mfe_pct,
                t.duration_minutes, t.entry_funding_rate, t.entry_atr_pct,
            )
            for t in trades
        ]

        self._conn.executemany(
            """INSERT INTO shadow_trades
               (trade_id, instance_id, play_id, symbol, direction,
                entry_time, exit_time, entry_price, exit_price, size_usdt,
                pnl_usdt, fees_usdt, exit_reason, mae_pct, mfe_pct,
                duration_minutes, entry_funding_rate, entry_atr_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )

    # ── Read (CLI queries) ──────────────────────────────────────

    def get_instance_ids(self) -> list[str]:
        """Get all instance IDs (active and stopped)."""
        assert self._conn is not None
        result = self._conn.execute(
            "SELECT instance_id FROM shadow_instances ORDER BY started_at DESC"
        ).fetchall()
        return [r[0] for r in result]

    def get_instance_info(self, instance_id: str) -> dict | None:
        """Get instance info as dict."""
        assert self._conn is not None
        result = self._conn.execute(
            "SELECT * FROM shadow_instances WHERE instance_id = ?",
            [instance_id],
        ).fetchone()
        if result is None:
            return None
        cols = [d[0] for d in self._conn.description]  # type: ignore[union-attr]
        return dict(zip(cols, result))

    def get_equity_curve(self, instance_id: str, limit: int = 500) -> list[dict]:
        """Get equity curve snapshots for an instance."""
        assert self._conn is not None
        result = self._conn.execute(
            """SELECT timestamp, equity_usdt, cumulative_pnl_usdt, max_drawdown_pct
               FROM shadow_snapshots
               WHERE instance_id = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            [instance_id, limit],
        ).fetchall()
        return [
            {"timestamp": r[0], "equity": r[1], "pnl": r[2], "dd": r[3]}
            for r in reversed(result)
        ]

    def get_trades(self, instance_id: str, limit: int = 100) -> list[dict]:
        """Get recent trades for an instance."""
        assert self._conn is not None
        result = self._conn.execute(
            """SELECT trade_id, direction, entry_time, exit_time,
                      entry_price, exit_price, size_usdt, pnl_usdt,
                      fees_usdt, exit_reason
               FROM shadow_trades
               WHERE instance_id = ?
               ORDER BY exit_time DESC
               LIMIT ?""",
            [instance_id, limit],
        ).fetchall()
        cols = ["trade_id", "direction", "entry_time", "exit_time",
                "entry_price", "exit_price", "size_usdt", "pnl_usdt",
                "fees_usdt", "exit_reason"]
        return [dict(zip(cols, r)) for r in reversed(result)]

    def get_leaderboard(self, metric: str = "pnl", limit: int = 20) -> list[dict]:
        """Get ranked instances by metric.

        Metrics: pnl, equity, trades, drawdown
        """
        assert self._conn is not None

        order_col = {
            "pnl": "cumulative_pnl_usdt DESC",
            "equity": "equity_usdt DESC",
            "trades": "total_trades DESC",
            "drawdown": "max_drawdown_pct ASC",
        }.get(metric, "cumulative_pnl_usdt DESC")

        result = self._conn.execute(
            f"""SELECT s.instance_id, i.play_id, i.symbol,
                       s.equity_usdt, s.cumulative_pnl_usdt,
                       s.total_trades, s.winning_trades, s.max_drawdown_pct
                FROM shadow_snapshots s
                JOIN shadow_instances i ON s.instance_id = i.instance_id
                WHERE s.timestamp = (
                    SELECT MAX(timestamp) FROM shadow_snapshots
                    WHERE instance_id = s.instance_id
                )
                ORDER BY {order_col}
                LIMIT ?""",
            [limit],
        ).fetchall()

        cols = ["instance_id", "play_id", "symbol", "equity", "pnl",
                "trades", "wins", "max_dd"]
        return [dict(zip(cols, r)) for r in result]
