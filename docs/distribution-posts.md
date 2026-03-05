# mcp-billing Distribution Posts — Copy-Paste Ready

Post order: HN → MCP Discord (same day) → Reddit r/MCP (day 2) → Reddit r/Python (day 3) → Twitter → GitHub outreach (after first external signal)

---

## 1. HN Show HN

**Title:**
```
Show HN: mcp-billing – Add API-key billing to any MCP server in 5 lines of Python
```

**Body:**

I've been building MCP servers and kept running into the same wall: there's no standard way to gate tool access by API key, enforce rate limits, or meter usage for billing. You either bolt on a custom auth layer every time or leave the server wide open.

mcp-billing is a Python middleware that wraps any MCP tool with:
- API key gating (register keys, assign tiers, deny unknown callers)
- Rate limiting (per-minute + per-month caps per tier)
- Usage metering (every call logged to SQLite with cost tracking)
- Optional Stripe sync (push usage events to Stripe Billing Meters)

Zero external services required. SQLite by default. Stripe is opt-in.

The implementation:

    from mcp.server.fastmcp import FastMCP
    from mcp_billing import BillingGuard
    from mcp_billing.middleware import billing_middleware

    mcp = FastMCP("my-server")
    guard = BillingGuard()  # zero config, SQLite-backed

    @mcp.tool()
    @billing_middleware(guard)
    def analyze(query: str, api_key: str = "") -> str:
        return f"Analysis: {query}"

That's the entire integration. The decorator handles access control, rate limiting, and usage recording. Keys are tiered (free/pro/enterprise by default, fully customizable). Monthly caps, per-minute limits, and tool-level access restrictions all configurable per tier.

There are 16,000+ MCP servers in the wild. To my knowledge none have a standardized billing layer. This is v0.1.0, MIT, works, and I'm actively using it.

PyPI: https://pypi.org/project/mcp-billing/
GitHub: https://github.com/LuciferForge/mcp-billing

Part of a broader MCP infrastructure effort — also shipping mcp-security-audit (scores your server against the MCP spec) and kya-agent (agent identity + cryptographic signing standard). Happy to discuss the architecture or what I got wrong.

---

## 2. Reddit r/MCP or r/ClaudeAI

**Title:**
```
I built a billing SDK for MCP servers because copy-pasting auth middleware got old fast
```

**Body:**

Every MCP server I built had the same problem: zero way to gate tool access without writing a custom auth layer from scratch each time. You either leave the server open or you reinvent the wheel.

So I built mcp-billing — a Python decorator that adds API key gating, rate limiting, and usage metering to any MCP tool.

The full integration looks like this:

```python
from mcp.server.fastmcp import FastMCP
from mcp_billing import BillingGuard
from mcp_billing.middleware import billing_middleware

mcp = FastMCP("my-server")
guard = BillingGuard()  # SQLite, no config needed

@mcp.tool()
@billing_middleware(guard)
def my_tool(query: str, api_key: str = "") -> str:
    return do_the_thing(query)
```

From that point:
- Unknown API keys get a 401
- Rate limit exceeded gets a 429
- Monthly cap hit gets a 402
- Every call is logged with timestamp, tool name, and cost

You can assign keys to tiers (free/pro/enterprise out of box, or define your own with custom limits). If you want Stripe: pass your API key and usage events auto-sync to Stripe Billing Meters. If you don't want Stripe: ignore it, everything stays in a local SQLite file.

It's v0.1.0, MIT licensed, works today. Actively using it on my own servers.

`pip install mcp-billing`

PyPI: https://pypi.org/project/mcp-billing/
GitHub: https://github.com/LuciferForge/mcp-billing

Also building out the surrounding infrastructure — mcp-security-audit audits your server against the MCP spec, kya-agent handles agent identity. If you're building MCP servers commercially, these three together cover the basics.

Feedback welcome — especially if something breaks or the API is awkward.

---

## 3. Reddit r/Python

**Title:**
```
mcp-billing: SQLite-backed billing middleware for MCP servers — zero-config decorator pattern, optional Stripe
```

**Body:**

I've been building MCP (Model Context Protocol) servers and needed a clean, reusable billing layer. Built one, packaged it, sharing it.

The design goal was: zero mandatory dependencies beyond the MCP SDK, no external services required to get started, Stripe as a pure opt-in.

The core is a decorator:

```python
from mcp_billing import BillingGuard
from mcp_billing.middleware import billing_middleware

guard = BillingGuard()  # defaults to billing.db SQLite, no config

@billing_middleware(guard)
def your_tool(query: str, api_key: str = "") -> str:
    return process(query)
```

What happens under the hood on each call:
1. Key lookup (exists? active?)
2. Tier check (is this tool allowed on the caller's tier?)
3. Rate limit check (per-minute sliding window)
4. Monthly cap check
5. If all pass: execute tool, record usage to SQLite
6. If Stripe key configured: queue usage event for sync

Custom tiers are dataclasses:

```python
from mcp_billing import PricingTier, BillingGuard

tiers = [
    PricingTier(name="free", rate_limit=10, monthly_cap=1000, cost_per_call=0.0),
    PricingTier(name="pro", rate_limit=60, monthly_cap=50_000, cost_per_call=0.001),
]
guard = BillingGuard(tiers=tiers)
```

Or load from JSON via CLI: `mcp-billing init` creates the config file, `mcp-billing status` shows live key stats.

Stripe integration is one argument: `BillingGuard(stripe_api_key="sk_live_...")` — usage events sync on each call or in batch via `meter.sync_unsynced()`.

Everything else is standard Python 3.10+, MIT, no magic.

`pip install mcp-billing`
`pip install mcp-billing[stripe]`  # if you want Stripe

PyPI: https://pypi.org/project/mcp-billing/
GitHub: https://github.com/LuciferForge/mcp-billing

v0.1.0. Happy to hear if the API design is wrong or if there's a better pattern I should be using.

---

## 4. MCP Discord

```
Hey — built a billing middleware for MCP servers if anyone needs it.

Problem: you build an MCP server, want to gate access by API key and track usage, end up writing the same auth/metering boilerplate every time.

mcp-billing solves it with a single decorator:

@mcp.tool()
@billing_middleware(guard)
def your_tool(query: str, api_key: str = "") -> str:
    ...

API key gating, rate limits, monthly caps, usage logging to SQLite. Stripe is optional if you want to push usage events to Stripe Billing Meters. Zero external services required to start.

pip install mcp-billing
https://github.com/LuciferForge/mcp-billing

v0.1.0, MIT. If you're building a server you plan to expose externally or charge for, might be useful. Feedback welcome.
```

---

## 5. Twitter/X

**Option A (before/after code):**
```
MCP server billing, before vs after:

BEFORE:
def my_tool(query, api_key):
    if not validate_key(api_key): raise ...
    if rate_limited(api_key): raise ...
    result = do_thing(query)
    log_usage(api_key, "my_tool")
    sync_stripe(api_key, cost)
    return result

AFTER:
@billing_middleware(guard)
def my_tool(query, api_key=""):
    return do_thing(query)

pip install mcp-billing
github.com/LuciferForge/mcp-billing
```

**Option B (hook-first):**
```
16,000+ MCP servers exist. None have a standard billing layer.

mcp-billing: API key gating + rate limits + usage metering in one decorator. SQLite by default, Stripe optional.

pip install mcp-billing

github.com/LuciferForge/mcp-billing
```

---

## 6. GitHub Outreach Template

**For Discussions tab on MCP server repos (NOT cold issues):**

**Subject:**
```
Billing/monetization layer for MCP servers — in case it's useful
```

**Body:**

Hey — noticed you're building an MCP server here. Not sure if monetization is on your roadmap, but I built a billing SDK for exactly this use case and wanted to flag it in case it saves you time.

mcp-billing adds API key gating, rate limiting, and usage metering via a single decorator:

    @mcp.tool()
    @billing_middleware(guard)
    def your_tool(query: str, api_key: str = "") -> str:
        return do_thing(query)

SQLite-backed by default, no external services required. Stripe sync is optional if you want to push usage events to Stripe Billing Meters.

pip install mcp-billing
https://github.com/LuciferForge/mcp-billing

It's v0.1.0 and MIT. Happy to hear if the API doesn't fit your setup — different MCP server patterns might need different integration points and I'd rather know about it than not.

**Targeting notes:**
- Only post where there's an existing discussion about auth/access/billing
- If no Discussions tab, skip — cold issues look like spam
- Personalize first line with something specific about their server
- Only start outreach AFTER you have at least one non-zero download or star

---

## Tracking

Baseline PyPI downloads before posting: check with `pip download` stats or pypistats.org.
Metric that matters: **downloads from strangers within 72h of each post.**
Stars are vanity. Issues from unknowns are gold.
