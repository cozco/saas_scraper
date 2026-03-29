"""Main CLI entry point for the SaaS Security Scraper."""
from __future__ import annotations

import argparse
import asyncio
import sys

from scrapers.zscaler_release import ZscalerReleaseScraper
from scrapers.zscaler_url_changes import ZscalerUrlChangesScraper
from output import write_json, write_txt


SCRAPER_REGISTRY = {
    "zscaler_release": ZscalerReleaseScraper,
    "zscaler_url_changes": ZscalerUrlChangesScraper,
}


async def run_scraper(scraper_name: str, url: str, cloud: str, date_filter: str) -> None:
    """Run a single scraper and write output files."""
    cls = SCRAPER_REGISTRY.get(scraper_name)
    if cls is None:
        print(f"Error: Unknown scraper '{scraper_name}'. Available: {', '.join(SCRAPER_REGISTRY)}")
        sys.exit(1)

    scraper = cls(source_url=url, cloud=cloud, date_filter=date_filter)
    print(f"Running {scraper_name} scraper...")
    print(f"  URL: {url}")
    print(f"  Cloud: {cloud}")
    print(f"  Date filter: {date_filter}")

    execution = await scraper.scrape()

    print(f"  Found {len(execution.results)} results")

    json_path = write_json(execution)
    txt_path = write_txt(execution)

    print(f"  JSON output: {json_path}")
    print(f"  TXT output:  {txt_path}")
    return execution


async def main() -> None:
    """Parse CLI arguments and dispatch to the appropriate scraper(s)."""
    parser = argparse.ArgumentParser(
        description="SaaS Security Vendor Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape Zscaler release upgrades for zscalertwo.net, March only
  python main.py zscaler_release \\
    --url https://help.zscaler.com/zia/release-upgrade-summary-2026 \\
    --cloud zscalertwo.net \\
    --date-filter March

  # Scrape Zscaler URL category changes for 2026
  python main.py zscaler_url_changes \\
    --url https://trust.zscaler.com/notifications/url-change-notification \\
    --cloud zscalertwo.net \\
    --date-filter 2026

  # Run all Zscaler scrapers
  python main.py all --cloud zscalertwo.net
        """,
    )
    parser.add_argument(
        "scraper",
        choices=list(SCRAPER_REGISTRY.keys()) + ["all"],
        help="Which scraper to run (or 'all' for all Zscaler scrapers)",
    )
    parser.add_argument("--url", help="Source URL to scrape")
    parser.add_argument("--cloud", default="zscalertwo.net", help="Cloud name (default: zscalertwo.net)")
    parser.add_argument("--date-filter", default="all", help="Date filter: month name, YYYY-MM, or year (default: all)")

    args = parser.parse_args()

    if args.scraper == "all":
        # Run both Zscaler scrapers with sensible defaults
        await run_scraper(
            "zscaler_release",
            url="https://help.zscaler.com/zia/release-upgrade-summary-2026",
            cloud=args.cloud,
            date_filter="March",
        )
        print()
        await run_scraper(
            "zscaler_url_changes",
            url="https://trust.zscaler.com/notifications/url-change-notification",
            cloud=args.cloud,
            date_filter="2026",
        )
    else:
        if not args.url:
            parser.error(f"--url is required when running a specific scraper")
        await run_scraper(args.scraper, args.url, args.cloud, args.date_filter)


if __name__ == "__main__":
    asyncio.run(main())
