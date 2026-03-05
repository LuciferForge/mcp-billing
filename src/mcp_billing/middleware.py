"""MCP middleware integration for billing.

Provides a decorator that intercepts MCP tool calls, checks billing
status via BillingGuard, and records usage on success.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

from .guard import BillingGuard

F = TypeVar("F", bound=Callable[..., Any])


class BillingError(Exception):
    """Raised when a tool call is denied due to billing.

    Attributes:
        reason: Human-readable denial reason.
        status_code: HTTP-style status code (402 by default).
    """

    def __init__(self, reason: str, status_code: int = 402) -> None:
        self.reason = reason
        self.status_code = status_code
        super().__init__(reason)


def billing_middleware(
    guard: BillingGuard,
    api_key_param: str = "api_key",
) -> Callable[[F], F]:
    """Decorator factory that wraps an MCP tool function with billing checks.

    The decorated function must accept a keyword argument named by
    ``api_key_param`` (default ``"api_key"``).  Before the tool runs,
    the middleware calls ``guard.check_access``.  If denied, a
    ``BillingError`` is raised.  On success, usage is recorded.

    Example usage with FastMCP::

        from mcp.server.fastmcp import FastMCP
        from mcp_billing import BillingGuard
        from .middleware import billing_middleware

        mcp = FastMCP("my-server")
        guard = BillingGuard()

        @mcp.tool()
        @billing_middleware(guard)
        def my_tool(query: str, api_key: str = "") -> str:
            return f"result for {query}"

    Args:
        guard: BillingGuard instance to use for checks.
        api_key_param: Name of the keyword argument that carries the
            caller's API key.

    Returns:
        A decorator that wraps tool functions with billing logic.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            api_key = kwargs.get(api_key_param, "")

            if not api_key:
                raise BillingError("Missing API key", status_code=401)

            tool_name = func.__name__

            # Check access
            decision = guard.check_access(api_key, tool_name)
            if not decision.allowed:
                raise BillingError(decision.reason, status_code=402)

            # Execute the tool
            result = func(*args, **kwargs)

            # Record usage after successful execution
            guard.record_usage(api_key, tool_name)

            return result

        return wrapper  # type: ignore[return-value]

    return decorator  # type: ignore[return-value]


def extract_api_key_from_context(
    context: dict[str, Any],
    header: str = "x-api-key",
) -> str:
    """Utility to extract an API key from an MCP request context.

    Looks in common locations: headers, params, and auth fields.

    Args:
        context: The MCP request context or metadata dict.
        header: Header name to look for the API key.

    Returns:
        The API key string, or empty string if not found.
    """
    # Check headers
    headers = context.get("headers", {})
    if header in headers:
        return headers[header]

    # Check params
    params = context.get("params", {})
    if "api_key" in params:
        return params["api_key"]

    # Check auth
    auth = context.get("auth", {})
    if "api_key" in auth:
        return auth["api_key"]

    return ""
