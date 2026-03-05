"""Pricing tier definitions and configuration loader.

Defines the PricingTier dataclass and utilities for loading pricing
configurations from JSON or YAML files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PricingTier:
    """A pricing tier that defines access, limits, and costs.

    Attributes:
        name: Tier identifier (e.g. "free", "pro", "enterprise").
        tools: List of tool names accessible in this tier.
            An empty list means all tools are accessible.
        rate_limit: Maximum calls per minute. 0 means unlimited.
        monthly_cap: Maximum calls per month. 0 means unlimited.
        cost_per_call: Cost in USD per tool invocation.
        monthly_price: Fixed monthly subscription price in USD.
    """

    name: str
    tools: list[str] = field(default_factory=list)
    rate_limit: int = 0
    monthly_cap: int = 0
    cost_per_call: float = 0.0
    monthly_price: float = 0.0

    def has_tool_access(self, tool_name: str) -> bool:
        """Check if this tier grants access to the given tool.

        An empty tools list means unrestricted access to all tools.
        """
        if not self.tools:
            return True
        return tool_name in self.tools


# -- Default tiers -----------------------------------------------------------

DEFAULT_TIERS: list[PricingTier] = [
    PricingTier(
        name="free",
        tools=[],
        rate_limit=10,
        monthly_cap=1000,
        cost_per_call=0.0,
        monthly_price=0.0,
    ),
    PricingTier(
        name="pro",
        tools=[],
        rate_limit=60,
        monthly_cap=50_000,
        cost_per_call=0.001,
        monthly_price=29.0,
    ),
    PricingTier(
        name="enterprise",
        tools=[],
        rate_limit=0,
        monthly_cap=0,
        cost_per_call=0.0005,
        monthly_price=199.0,
    ),
]


def _tier_from_dict(data: dict[str, Any]) -> PricingTier:
    """Create a PricingTier from a dict, ignoring unknown keys."""
    known_fields = {f.name for f in PricingTier.__dataclass_fields__.values()}
    filtered = {k: v for k, v in data.items() if k in known_fields}
    return PricingTier(**filtered)


def load_pricing(path: str | Path) -> list[PricingTier]:
    """Load pricing tiers from a JSON file.

    The file should contain a JSON object with a top-level ``tiers`` key
    holding a list of tier objects.  If the file has a ``.yaml`` or ``.yml``
    extension, PyYAML is used instead (must be installed separately).

    Args:
        path: Path to the pricing configuration file.

    Returns:
        A list of PricingTier instances.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If the file format is unsupported or malformed.
    """
    filepath = Path(path)
    if not filepath.exists():
        raise FileNotFoundError(f"Pricing config not found: {filepath}")

    suffix = filepath.suffix.lower()
    raw_text = filepath.read_text(encoding="utf-8")

    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "PyYAML is required to load YAML pricing configs. "
                "Install it with: pip install pyyaml"
            ) from exc
        data = yaml.safe_load(raw_text)
    elif suffix == ".json":
        data = json.loads(raw_text)
    else:
        raise ValueError(f"Unsupported config format: {suffix}")

    if not isinstance(data, dict) or "tiers" not in data:
        raise ValueError("Pricing config must contain a top-level 'tiers' key")

    return [_tier_from_dict(t) for t in data["tiers"]]


def save_default_pricing(path: str | Path) -> None:
    """Write the default pricing tiers to a JSON file.

    Useful for bootstrapping a new billing configuration via the CLI.
    """
    filepath = Path(path)
    tiers_data = {
        "tiers": [
            {
                "name": t.name,
                "tools": t.tools,
                "rate_limit": t.rate_limit,
                "monthly_cap": t.monthly_cap,
                "cost_per_call": t.cost_per_call,
                "monthly_price": t.monthly_price,
            }
            for t in DEFAULT_TIERS
        ]
    }
    filepath.write_text(json.dumps(tiers_data, indent=2) + "\n", encoding="utf-8")
