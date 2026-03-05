"""UsageMeter: track per-key usage counts and costs.

Provides aggregated usage reporting from the local SQLite database,
with optional sync to Stripe Billing Meter API.
"""

from __future__ import annotations

import datetime
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class UsageReport:
    """Aggregated usage data for a single API key.

    Attributes:
        api_key: The API key this report belongs to.
        period: The period label (e.g. "2026-03", "2026-03-03").
        total_calls: Total number of tool invocations.
        total_cost: Accumulated cost in USD.
        by_tool: Breakdown of calls per tool name.
    """

    api_key: str
    period: str
    total_calls: int = 0
    total_cost: float = 0.0
    by_tool: dict[str, int] = field(default_factory=dict)


class UsageMeter:
    """Track per-key usage counts and costs in SQLite.

    Uses the same database schema as BillingGuard so they can share
    a single ``billing.db`` file.  Can also operate on its own.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str | Path = "billing.db") -> None:
        self._db_path = Path(db_path)
        self._conn = self._init_db()

    def _init_db(self) -> sqlite3.Connection:
        """Ensure the usage_log table exists."""
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS usage_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key     TEXT NOT NULL,
                tool_name   TEXT NOT NULL,
                cost        REAL NOT NULL DEFAULT 0.0,
                metadata    TEXT DEFAULT '{}',
                timestamp   REAL NOT NULL,
                synced      INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_usage_key_ts
                ON usage_log(api_key, timestamp);
            """
        )
        conn.commit()
        return conn

    # -- Recording ------------------------------------------------------------

    def increment(
        self,
        api_key: str,
        tool_name: str,
        cost: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a single tool invocation.

        Args:
            api_key: The caller's API key.
            tool_name: Name of the tool invoked.
            cost: Cost in USD for this call.
            metadata: Optional metadata dict.
        """
        import json

        self._conn.execute(
            "INSERT INTO usage_log (api_key, tool_name, cost, metadata, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (api_key, tool_name, cost, json.dumps(metadata or {}), time.time()),
        )
        self._conn.commit()

    # -- Reporting ------------------------------------------------------------

    def get_usage(self, api_key: str, period: str = "month") -> UsageReport:
        """Get aggregated usage for a key over a time period.

        Args:
            api_key: The API key to query.
            period: One of ``"month"`` (current calendar month),
                ``"day"`` (today), or ``"all"`` (all time).

        Returns:
            A UsageReport with totals and per-tool breakdown.

        Raises:
            ValueError: If period is not recognized.
        """
        now = datetime.datetime.now(datetime.timezone.utc)

        if period == "month":
            start = datetime.datetime(
                now.year, now.month, 1, tzinfo=datetime.timezone.utc
            )
            label = now.strftime("%Y-%m")
        elif period == "day":
            start = datetime.datetime(
                now.year, now.month, now.day, tzinfo=datetime.timezone.utc
            )
            label = now.strftime("%Y-%m-%d")
        elif period == "all":
            start = datetime.datetime(
                2000, 1, 1, tzinfo=datetime.timezone.utc
            )
            label = "all"
        else:
            raise ValueError(
                f"Unknown period '{period}'. Use 'month', 'day', or 'all'."
            )

        rows = self._conn.execute(
            "SELECT tool_name, COUNT(*), SUM(cost) FROM usage_log "
            "WHERE api_key = ? AND timestamp >= ? "
            "GROUP BY tool_name",
            (api_key, start.timestamp()),
        ).fetchall()

        report = UsageReport(api_key=api_key, period=label)
        for tool_name, count, cost in rows:
            report.total_calls += count
            report.total_cost += cost or 0.0
            report.by_tool[tool_name] = count

        return report

    def get_all_keys(self) -> list[str]:
        """Return all distinct API keys that have usage records."""
        rows = self._conn.execute(
            "SELECT DISTINCT api_key FROM usage_log"
        ).fetchall()
        return [r[0] for r in rows]

    # -- Stripe sync ----------------------------------------------------------

    def sync_unsynced(self, stripe_api_key: str) -> int:
        """Push unsynced usage events to Stripe Billing Meter API.

        Marks events as synced after successful delivery.

        Args:
            stripe_api_key: Stripe secret API key.

        Returns:
            Number of events successfully synced.
        """
        rows = self._conn.execute(
            "SELECT id, api_key, tool_name, cost, timestamp "
            "FROM usage_log WHERE synced = 0 ORDER BY timestamp"
        ).fetchall()

        if not rows:
            return 0

        synced = 0
        try:
            import stripe

            stripe.api_key = stripe_api_key

            for row_id, api_key, tool_name, cost, ts in rows:
                try:
                    stripe.billing.MeterEvent.create(
                        event_name="mcp_tool_call",
                        payload={
                            "value": "1",
                            "tool_name": tool_name,
                            "cost": str(cost),
                        },
                    )
                    self._conn.execute(
                        "UPDATE usage_log SET synced = 1 WHERE id = ?",
                        (row_id,),
                    )
                    synced += 1
                except Exception:
                    # Stop on first failure to preserve ordering
                    break

            self._conn.commit()
        except ImportError:
            pass

        return synced

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()
