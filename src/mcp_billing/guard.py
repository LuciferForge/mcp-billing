"""BillingGuard: gate MCP tool calls behind billing checks.

Provides access control and usage recording backed by a local SQLite
database.  When a Stripe API key is configured, usage events are also
forwarded to Stripe for invoicing.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .pricing import DEFAULT_TIERS, PricingTier


# -- Data structures ----------------------------------------------------------

@dataclass
class BillingDecision:
    """Result of an access check.

    Attributes:
        allowed: Whether the call should proceed.
        reason: Human-readable explanation when access is denied.
        tier: The PricingTier that matched the API key.
        remaining_quota: Approximate remaining calls in the current period.
    """

    allowed: bool
    reason: str = ""
    tier: PricingTier | None = None
    remaining_quota: int = -1


@dataclass
class KeyRecord:
    """Internal representation of a registered API key."""

    api_key: str
    tier_name: str
    active: bool = True
    stripe_customer_id: str = ""


# -- BillingGuard -------------------------------------------------------------

class BillingGuard:
    """Wraps MCP tool calls with billing checks and usage recording.

    Works entirely offline with SQLite.  Optionally syncs to Stripe when
    ``stripe_api_key`` is provided.

    Args:
        db_path: Path to the SQLite database file.
            Defaults to ``billing.db`` in the current directory.
        tiers: Pricing tiers to enforce.  Defaults to the built-in tiers.
        stripe_api_key: Optional Stripe secret key for syncing.
    """

    def __init__(
        self,
        db_path: str | Path = "billing.db",
        tiers: list[PricingTier] | None = None,
        stripe_api_key: str | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._tiers = {t.name: t for t in (tiers or DEFAULT_TIERS)}
        self._stripe_api_key = stripe_api_key
        self._conn = self._init_db()

    # -- Database setup -------------------------------------------------------

    def _init_db(self) -> sqlite3.Connection:
        """Create tables if they do not exist."""
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS keys (
                api_key     TEXT PRIMARY KEY,
                tier_name   TEXT NOT NULL DEFAULT 'free',
                active      INTEGER NOT NULL DEFAULT 1,
                stripe_customer_id TEXT DEFAULT '',
                created_at  REAL NOT NULL
            );

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

    # -- Key management -------------------------------------------------------

    def register_key(
        self,
        api_key: str,
        tier_name: str = "free",
        stripe_customer_id: str = "",
    ) -> None:
        """Register a new API key with the given tier.

        Raises:
            ValueError: If the tier name is unknown.
        """
        if tier_name not in self._tiers:
            raise ValueError(
                f"Unknown tier '{tier_name}'. "
                f"Available: {list(self._tiers.keys())}"
            )
        self._conn.execute(
            "INSERT OR REPLACE INTO keys "
            "(api_key, tier_name, active, stripe_customer_id, created_at) "
            "VALUES (?, ?, 1, ?, ?)",
            (api_key, tier_name, stripe_customer_id, time.time()),
        )
        self._conn.commit()

    def _get_key_record(self, api_key: str) -> KeyRecord | None:
        row = self._conn.execute(
            "SELECT api_key, tier_name, active, stripe_customer_id "
            "FROM keys WHERE api_key = ?",
            (api_key,),
        ).fetchone()
        if row is None:
            return None
        return KeyRecord(
            api_key=row[0],
            tier_name=row[1],
            active=bool(row[2]),
            stripe_customer_id=row[3],
        )

    # -- Usage counting -------------------------------------------------------

    def _usage_count_this_month(self, api_key: str) -> int:
        """Count usage events for the current calendar month."""
        import datetime

        now = datetime.datetime.now(datetime.timezone.utc)
        month_start = datetime.datetime(
            now.year, now.month, 1, tzinfo=datetime.timezone.utc
        )
        row = self._conn.execute(
            "SELECT COUNT(*) FROM usage_log "
            "WHERE api_key = ? AND timestamp >= ?",
            (api_key, month_start.timestamp()),
        ).fetchone()
        return row[0] if row else 0

    def _usage_count_last_minute(self, api_key: str) -> int:
        """Count usage events in the last 60 seconds."""
        cutoff = time.time() - 60
        row = self._conn.execute(
            "SELECT COUNT(*) FROM usage_log "
            "WHERE api_key = ? AND timestamp >= ?",
            (api_key, cutoff),
        ).fetchone()
        return row[0] if row else 0

    # -- Core API -------------------------------------------------------------

    def check_access(self, api_key: str, tool_name: str) -> BillingDecision:
        """Check whether the given API key may invoke the tool.

        Validates key existence, active status, tier tool access,
        rate limits, and monthly caps.

        Args:
            api_key: The caller's API key.
            tool_name: The MCP tool being invoked.

        Returns:
            A BillingDecision indicating whether the call is allowed.
        """
        record = self._get_key_record(api_key)
        if record is None:
            return BillingDecision(allowed=False, reason="Unknown API key")

        if not record.active:
            return BillingDecision(allowed=False, reason="API key is deactivated")

        tier = self._tiers.get(record.tier_name)
        if tier is None:
            return BillingDecision(
                allowed=False, reason=f"Tier '{record.tier_name}' not configured"
            )

        if not tier.has_tool_access(tool_name):
            return BillingDecision(
                allowed=False,
                reason=f"Tool '{tool_name}' not available on '{tier.name}' tier",
                tier=tier,
            )

        # Rate limit check
        if tier.rate_limit > 0:
            rpm = self._usage_count_last_minute(api_key)
            if rpm >= tier.rate_limit:
                return BillingDecision(
                    allowed=False,
                    reason=f"Rate limit exceeded ({tier.rate_limit}/min)",
                    tier=tier,
                    remaining_quota=0,
                )

        # Monthly cap check
        remaining = -1
        if tier.monthly_cap > 0:
            monthly = self._usage_count_this_month(api_key)
            remaining = tier.monthly_cap - monthly
            if remaining <= 0:
                return BillingDecision(
                    allowed=False,
                    reason=f"Monthly cap reached ({tier.monthly_cap} calls)",
                    tier=tier,
                    remaining_quota=0,
                )

        return BillingDecision(
            allowed=True,
            tier=tier,
            remaining_quota=remaining,
        )

    def record_usage(
        self,
        api_key: str,
        tool_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a usage event for the given API key.

        Args:
            api_key: The caller's API key.
            tool_name: The MCP tool that was invoked.
            metadata: Optional metadata dict stored as JSON.
        """
        import json

        record = self._get_key_record(api_key)
        cost = 0.0
        if record:
            tier = self._tiers.get(record.tier_name)
            if tier:
                cost = tier.cost_per_call

        self._conn.execute(
            "INSERT INTO usage_log (api_key, tool_name, cost, metadata, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                api_key,
                tool_name,
                cost,
                json.dumps(metadata or {}),
                time.time(),
            ),
        )
        self._conn.commit()

        # Best-effort Stripe sync
        if self._stripe_api_key and record and record.stripe_customer_id:
            self._sync_to_stripe(record.stripe_customer_id, tool_name, cost)

    def _sync_to_stripe(
        self, customer_id: str, tool_name: str, cost: float
    ) -> None:
        """Attempt to report a usage event to Stripe. Fails silently."""
        try:
            import stripe

            stripe.api_key = self._stripe_api_key
            stripe.billing.MeterEvent.create(
                event_name="mcp_tool_call",
                payload={
                    "stripe_customer_id": customer_id,
                    "tool_name": tool_name,
                    "cost": str(cost),
                },
            )
        except Exception:
            # Non-critical -- local record is the source of truth
            pass

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()
