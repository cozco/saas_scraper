"""AWS Lambda handler for the SaaS Security Scraper.

Runs the configured scrapers, generates JSON and TXT outputs, and uploads
them to an S3 bucket.  Does **not** require Playwright — uses ``urllib``
from the standard library for HTTP fetches, then passes the raw content
to the scraper parsing logic.

Environment variables
---------------------
S3_BUCKET : str
    Target S3 bucket name (required).
S3_PREFIX : str
    Key prefix / folder inside the bucket (default: ``"scraper-output"``).
CLOUD : str
    Zscaler cloud to scrape (default: ``"zscalertwo.net"``).

Lambda event schema
-------------------
The handler accepts an optional JSON event to override defaults::

    {
        "scrapers": ["zscaler_release", "zscaler_url_changes"],  // or ["all"]
        "cloud": "zscalertwo.net",
        "date_filters": {
            "zscaler_release": "March",
            "zscaler_url_changes": "2026"
        },
        "s3_bucket": "my-bucket",
        "s3_prefix": "scraper-output"
    }

All fields are optional — sensible defaults are used when omitted.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import ssl
import urllib.request
from typing import Any

from models import ScrapeExecution
from output import build_filename
from scrapers.zscaler_release import (
    ZscalerReleaseScraper,
    build_rss_url,
)
from scrapers.zscaler_url_changes import (
    ZscalerUrlChangesScraper,
    JSON_FEED_URL,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Default URLs used when running via ``all``
DEFAULT_RELEASE_URL = "https://help.zscaler.com/zia/release-upgrade-summary-2026"
DEFAULT_URL_CHANGES_URL = "https://trust.zscaler.com/notifications/url-change-notification"

# Default date filters per scraper
DEFAULT_DATE_FILTERS: dict[str, str] = {
    "zscaler_release": "March",
    "zscaler_url_changes": "2026",
}


def _fetch_url(url: str, timeout: int = 30) -> str:
    """Fetch a URL using ``urllib`` and return the response body as a string.

    This avoids the need for Playwright/Chromium in the Lambda environment.
    Both Zscaler data endpoints return plain XML or JSON that does not
    require JavaScript rendering.
    """
    # Create a default SSL context for HTTPS connections
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "SaaSSecurityScraper/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read().decode("utf-8")


def _generate_json_content(execution: ScrapeExecution) -> str:
    """Serialise a ScrapeExecution to a JSON string (same format as ``write_json``)."""
    return json.dumps(execution.to_dict(), indent=2, ensure_ascii=False)


def _generate_txt_content(execution: ScrapeExecution) -> str:
    """Generate the TXT report content in-memory (mirrors ``write_txt`` logic)."""
    from datetime import datetime, timezone

    lines: list[str] = []
    lines.append("=" * 80)
    lines.append("SaaS Scraper Report")
    lines.append("=" * 80)
    lines.append(f"Execution ID : {execution.execution_id}")
    lines.append(f"Platform     : {execution.platform}")
    lines.append(f"Cloud        : {execution.cloud}")
    lines.append(f"Scrape Type  : {execution.scrape_type}")
    lines.append(f"Source URL   : {execution.source_url}")
    lines.append(f"Date Filter  : {execution.date_filter}")
    lines.append(f"Scraped At   : {execution.scrape_timestamp}")
    lines.append(f"Total Results: {len(execution.results)}")
    if execution.notes:
        lines.append(f"Notes        : {execution.notes}")
    lines.append("=" * 80)
    lines.append("")

    for i, result in enumerate(execution.results, 1):
        lines.append(f"--- Result {i} ---")
        lines.append(f"  Title      : {result.title}")
        lines.append(f"  Date       : {result.date}")
        lines.append(f"  Status     : {result.status}")
        if result.severity:
            lines.append(f"  Severity   : {result.severity}")
        lines.append(f"  Category   : {result.category}")
        lines.append(f"  Source URL  : {result.source_url}")

        desc = result.description
        if len(desc) > 300:
            desc = desc[:297] + "..."
        lines.append(f"  Description: {desc}")

        if result.metadata:
            if "domain_changes" in result.metadata:
                n = len(result.metadata["domain_changes"])
                lines.append(f"  Domain Changes: {n} entries")
                for entry in result.metadata["domain_changes"][:5]:
                    domain = entry.get("Domain/Sub-Domain", "")
                    current = entry.get("Current Category", "")
                    updated = list(entry.values())[-1] if len(entry) > 2 else ""
                    lines.append(f"    {domain}: {current} → {updated}")
                if n > 5:
                    lines.append(f"    ... and {n - 5} more")
            else:
                for k, v in result.metadata.items():
                    if isinstance(v, str) and v:
                        lines.append(f"  {k}: {v}")
        lines.append("")

    lines.append("=" * 80)
    lines.append(f"End of report. Generated {datetime.now(timezone.utc).isoformat()}")
    lines.append("=" * 80)
    return "\n".join(lines)


def _upload_to_s3(bucket: str, key: str, body: str, content_type: str) -> None:
    """Upload a string payload to S3.

    Uses ``boto3`` which is pre-installed in the Lambda runtime.
    """
    import boto3

    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=body.encode("utf-8"),
        ContentType=content_type,
    )
    logger.info("Uploaded s3://%s/%s", bucket, key)


async def _run_release_scraper(cloud: str, date_filter: str) -> ScrapeExecution:
    """Fetch the RSS feed with urllib and run the release scraper over it."""
    scraper = ZscalerReleaseScraper(
        source_url=DEFAULT_RELEASE_URL,
        cloud=cloud,
        date_filter=date_filter,
    )
    rss_url = build_rss_url(DEFAULT_RELEASE_URL, cloud)
    xml_text = _fetch_url(rss_url)
    return await scraper.scrape(xml_text=xml_text)


async def _run_url_changes_scraper(cloud: str, date_filter: str) -> ScrapeExecution:
    """Fetch the JSON feed with urllib and run the URL changes scraper over it."""
    scraper = ZscalerUrlChangesScraper(
        source_url=DEFAULT_URL_CHANGES_URL,
        cloud=cloud,
        date_filter=date_filter,
    )
    raw_json = _fetch_url(JSON_FEED_URL)
    return await scraper.scrape(raw_json=raw_json)


SCRAPER_RUNNERS = {
    "zscaler_release": _run_release_scraper,
    "zscaler_url_changes": _run_url_changes_scraper,
}


async def _async_handler(event: dict[str, Any]) -> dict[str, Any]:
    """Core async logic for the Lambda handler."""
    # Resolve configuration from event, falling back to env vars then defaults
    cloud = event.get("cloud") or os.environ.get("CLOUD", "zscalertwo.net")
    s3_bucket = event.get("s3_bucket") or os.environ.get("S3_BUCKET", "")
    s3_prefix = event.get("s3_prefix") or os.environ.get("S3_PREFIX", "scraper-output")
    date_filters = event.get("date_filters", {})

    if not s3_bucket:
        raise ValueError(
            "S3_BUCKET must be set via the event payload or the S3_BUCKET environment variable"
        )

    # Determine which scrapers to run
    scraper_names = event.get("scrapers", ["all"])
    if "all" in scraper_names:
        scraper_names = list(SCRAPER_RUNNERS.keys())

    uploaded: list[dict[str, str]] = []

    for name in scraper_names:
        runner = SCRAPER_RUNNERS.get(name)
        if runner is None:
            logger.warning("Unknown scraper '%s', skipping", name)
            continue

        df = date_filters.get(name, DEFAULT_DATE_FILTERS.get(name, "all"))
        logger.info("Running %s (cloud=%s, date_filter=%s)", name, cloud, df)

        execution = await runner(cloud, df)
        logger.info("  %s returned %d results", name, len(execution.results))

        # Generate output content
        json_content = _generate_json_content(execution)
        txt_content = _generate_txt_content(execution)

        json_key = f"{s3_prefix}/{build_filename(execution, 'json')}"
        txt_key = f"{s3_prefix}/{build_filename(execution, 'txt')}"

        # Upload to S3
        _upload_to_s3(s3_bucket, json_key, json_content, "application/json")
        _upload_to_s3(s3_bucket, txt_key, txt_content, "text/plain")

        uploaded.append({
            "scraper": name,
            "execution_id": execution.execution_id,
            "results_count": len(execution.results),
            "json_key": f"s3://{s3_bucket}/{json_key}",
            "txt_key": f"s3://{s3_bucket}/{txt_key}",
        })

    return {
        "statusCode": 200,
        "body": {
            "message": f"Completed {len(uploaded)} scraper(s)",
            "uploads": uploaded,
        },
    }


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    """AWS Lambda entry point.

    Args:
        event: Lambda event payload (see module docstring for schema).
        context: Lambda runtime context (unused).

    Returns:
        A dict with ``statusCode`` and ``body`` containing upload details.
    """
    event = event or {}
    return asyncio.get_event_loop().run_until_complete(_async_handler(event))
