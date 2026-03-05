"""CLI entry point for mcp-billing.

Provides ``mcp-billing init`` and ``mcp-billing status`` commands.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_init(args: argparse.Namespace) -> None:
    """Create a default billing configuration file."""
    from .pricing import save_default_pricing

    output = Path(args.output)
    if output.exists() and not args.force:
        print(f"Error: {output} already exists. Use --force to overwrite.")
        sys.exit(1)

    save_default_pricing(output)
    print(f"Created billing config: {output}")
    print("Edit the file to customize tiers, rate limits, and pricing.")


def cmd_status(args: argparse.Namespace) -> None:
    """Show current usage statistics."""
    from .meter import UsageMeter

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"No billing database found at {db_path}")
        print("Run your MCP server with billing enabled to generate data.")
        sys.exit(1)

    meter = UsageMeter(db_path)
    keys = meter.get_all_keys()

    if not keys:
        print("No usage data recorded yet.")
        meter.close()
        return

    print(f"Billing database: {db_path}")
    print(f"API keys with usage: {len(keys)}")
    print("-" * 50)

    for key in keys:
        report = meter.get_usage(key, period=args.period)
        masked_key = key[:8] + "..." + key[-4:] if len(key) > 12 else key
        print(f"\n  Key: {masked_key}")
        print(f"  Period: {report.period}")
        print(f"  Total calls: {report.total_calls}")
        print(f"  Total cost: ${report.total_cost:.4f}")
        if report.by_tool:
            print("  By tool:")
            for tool, count in sorted(report.by_tool.items()):
                print(f"    {tool}: {count}")

    meter.close()


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="mcp-billing",
        description="Billing and monetization SDK for MCP servers.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # init
    init_parser = subparsers.add_parser(
        "init", help="Create a default billing configuration file"
    )
    init_parser.add_argument(
        "-o",
        "--output",
        default="billing.json",
        help="Output file path (default: billing.json)",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing config file",
    )

    # status
    status_parser = subparsers.add_parser(
        "status", help="Show current usage statistics"
    )
    status_parser.add_argument(
        "--db",
        default="billing.db",
        help="Path to billing database (default: billing.db)",
    )
    status_parser.add_argument(
        "--period",
        default="month",
        choices=["day", "month", "all"],
        help="Usage period to display (default: month)",
    )

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
