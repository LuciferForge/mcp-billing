# mcp-billing

Billing and monetization SDK for MCP servers. Add usage-based pricing in minutes.

16,000+ MCP servers exist. Zero have turnkey billing. This fixes that.

## Install

```bash
pip install mcp-billing
```

## Quick Start — 5 Lines to Monetize

```python
from mcp.server.fastmcp import FastMCP
from mcp_billing import BillingGuard
from mcp_billing.middleware import billing_middleware

mcp = FastMCP("my-server")
guard = BillingGuard()  # SQLite-backed, zero config

@mcp.tool()
@billing_middleware(guard)
def analyze(query: str, api_key: str = "") -> str:
    return f"Analysis of: {query}"
```

That's it. Every call is now gated by API key, tracked with usage counts, and enforced with rate limits.

## What You Get

- **API key gating** — register keys, assign tiers, deny unknown callers
- **Rate limiting** — per-minute and per-month caps per tier
- **Usage metering** — every call logged to SQLite with cost tracking
- **Tier-based pricing** — free/pro/enterprise out of the box, fully customizable
- **Stripe sync** — optional, push usage events to Stripe Billing Meters
- **CLI tools** — `mcp-billing init` and `mcp-billing status`

## Register API Keys

```python
guard = BillingGuard()

# Free tier: 10 req/min, 1000/month
guard.register_key("key-free-abc123", tier_name="free")

# Pro tier: 60 req/min, 50k/month, $0.001/call
guard.register_key("key-pro-xyz789", tier_name="pro")

# Enterprise: unlimited
guard.register_key("key-ent-456def", tier_name="enterprise")
```

## Custom Pricing Tiers

```python
from mcp_billing import PricingTier, BillingGuard

tiers = [
    PricingTier(name="starter", rate_limit=5, monthly_cap=500, cost_per_call=0.0),
    PricingTier(name="growth", rate_limit=100, monthly_cap=100_000, cost_per_call=0.002),
    PricingTier(
        name="scale",
        tools=["analyze", "generate"],  # restrict tool access by tier
        rate_limit=0,
        monthly_cap=0,
        cost_per_call=0.001,
    ),
]

guard = BillingGuard(tiers=tiers)
```

Or load from a JSON file:

```bash
mcp-billing init  # creates billing.json with default tiers
```

```python
from mcp_billing.pricing import load_pricing

tiers = load_pricing("billing.json")
guard = BillingGuard(tiers=tiers)
```

## Check Usage

```bash
mcp-billing status
```

```
Billing database: billing.db
API keys with usage: 3
--------------------------------------------------

  Key: key-free...c123
  Period: 2026-03
  Total calls: 847
  Total cost: $0.0000
  By tool:
    analyze: 847
```

Or programmatically:

```python
from mcp_billing import UsageMeter

meter = UsageMeter("billing.db")
report = meter.get_usage("key-pro-xyz789", period="month")
print(f"Calls: {report.total_calls}, Cost: ${report.total_cost:.4f}")
```

## Stripe Integration

```python
guard = BillingGuard(stripe_api_key="sk_live_...")

# Register key with Stripe customer ID
guard.register_key("key-pro-xyz789", tier_name="pro", stripe_customer_id="cus_abc123")

# Usage events auto-sync to Stripe Billing Meters on each call
```

Or batch sync unsynced events:

```python
from mcp_billing import UsageMeter

meter = UsageMeter("billing.db")
synced = meter.sync_unsynced("sk_live_...")
print(f"Synced {synced} events to Stripe")
```

## How It Works

```
Client → MCP Tool Call
           ↓
    BillingGuard.check_access()
           ↓
    ┌──────────────────┐
    │ Key exists?       │ → 401
    │ Key active?       │ → 402
    │ Tool in tier?     │ → 402
    │ Under rate limit? │ → 429
    │ Under monthly cap?│ → 402
    └──────────────────┘
           ↓ PASS
    Execute tool
           ↓
    Record usage → SQLite
                 → Stripe (optional)
```

## Architecture

| Component | Purpose |
|-----------|---------|
| `BillingGuard` | Access control + usage recording |
| `UsageMeter` | Usage aggregation + Stripe sync |
| `PricingTier` | Tier definitions (limits, costs, tool access) |
| `billing_middleware` | Decorator to wrap any MCP tool |
| `CLI` | `init` config + `status` dashboard |

All data stored in a single `billing.db` SQLite file. No external services required. Stripe is optional.

## Part of the LuciferForge Ecosystem

| Package | Purpose |
|---------|---------|
| [kya-agent](https://pypi.org/project/kya-agent/) | Agent identity standard + cryptographic signing |
| [mcp-security-audit](https://pypi.org/project/mcp-security-audit/) | Security auditor for MCP servers |
| [ai-injection-guard](https://pypi.org/project/ai-injection-guard/) | Prompt injection detection |
| [ai-cost-guard](https://pypi.org/project/ai-cost-guard/) | LLM budget enforcement |
| [ai-decision-tracer](https://pypi.org/project/ai-decision-tracer/) | Agent decision audit trails |
| **mcp-billing** | Billing SDK for MCP servers |

## License

MIT
