"""Scraper for Zscaler Release Upgrade Summary via RSS feed.

Uses the RSS endpoint at:
  https://help.zscaler.com/rss-feed/zia/release-upgrade-summary-{year}/{cloud}

This is far more efficient than browser-based scraping since it returns
structured XML without needing JavaScript rendering.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

from models import ScrapeExecution, ScrapeResult
from scrapers.base import BaseScraper

# Valid Zscaler clouds for the release page.
VALID_CLOUDS = {
    "zscaler.net", "zscalerone.net", "zscalertwo.net",
    "zscalerthree.net", "zscloud.net", "zscalerbeta.net",
}

MONTH_NUMBERS: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

RSS_BASE_URL = "https://help.zscaler.com/rss-feed/zia/release-upgrade-summary"


def build_rss_url(source_url: str, cloud: str) -> str:
    """Build the RSS feed URL from the original page URL and cloud name.

    Extracts the year from the source URL path (e.g. '.../2026')
    and constructs: /rss-feed/zia/release-upgrade-summary-{year}/{cloud}
    """
    m = re.search(r"(\d{4})", source_url)
    year = m.group(1) if m else "2026"
    return f"{RSS_BASE_URL}-{year}/{cloud}"


def parse_month_filter(date_filter: str) -> int | None:
    """Return month number from filter like 'March', '2026-03', '03', or None for 'all'."""
    if date_filter.lower() == "all":
        return None
    m = re.match(r"(?:\d{4}-)?(\d{2})", date_filter)
    if m:
        return int(m.group(1))
    return MONTH_NUMBERS.get(date_filter.strip().lower())


def parse_rss_date(date_str: str) -> str:
    """Parse RSS pubDate like 'Fri, 20 Mar 2026 07:00:00 GMT' → '2026-03-20'."""
    try:
        dt = datetime.strptime(date_str.strip(), "%a, %d %b %Y %H:%M:%S %Z")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return ""


class _HtmlStripper(HTMLParser):
    """Strip HTML tags, keeping only text content."""

    def __init__(self) -> None:
        """Initialise with an empty parts accumulator."""
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        """Collect each text segment encountered between tags."""
        self._parts.append(data)

    def get_text(self) -> str:
        """Join accumulated text segments into a single space-separated string."""
        return " ".join(self._parts).strip()


def strip_html(html: str) -> str:
    """Remove HTML tags and return plain text."""
    decoded = unescape(html)
    stripper = _HtmlStripper()
    stripper.feed(decoded)
    text = stripper.get_text()
    # Collapse whitespace
    return re.sub(r"\s+", " ", text).strip()


def extract_id_from_link(link: str) -> str:
    """Extract the feature/item ID from the RSS item link URL."""
    parsed = urlparse(link)
    qs = parse_qs(parsed.query)
    return qs.get("id", [""])[0]


def extract_deployment_date_from_link(link: str) -> str:
    """Extract deployment_date param from link URL."""
    parsed = urlparse(link)
    qs = parse_qs(parsed.query)
    return qs.get("deployment_date", [""])[0]


def parse_rss_xml(xml_text: str) -> list[dict[str, str]]:
    """Parse RSS XML into a list of item dicts."""
    root = ET.fromstring(xml_text)
    items: list[dict[str, str]] = []

    channel = root.find("channel")
    if channel is None:
        return items

    for item_el in channel.findall("item"):
        title = (item_el.findtext("title") or "").strip()
        link = (item_el.findtext("link") or "").strip()
        description_raw = (item_el.findtext("description") or "").strip()
        category = (item_el.findtext("category") or "").strip()
        pub_date = (item_el.findtext("pubDate") or "").strip()
        guid = (item_el.findtext("guid") or "").strip()

        items.append({
            "title": title,
            "link": link,
            "description_html": description_raw,
            "description_text": strip_html(description_raw),
            "category": category,
            "pub_date": pub_date,
            "iso_date": parse_rss_date(pub_date),
            "deployment_date": extract_deployment_date_from_link(link),
            "guid": guid,
            "item_id": extract_id_from_link(link),
        })

    return items


class ZscalerReleaseScraper(BaseScraper):
    """Scrape Zscaler Release Upgrade Summary via RSS feed."""

    platform = "Zscaler"
    scrape_type = "release_upgrade_summary"

    async def scrape(self, xml_text: str | None = None) -> ScrapeExecution:
        """Fetch the RSS feed for the configured cloud and return filtered release items.

        Args:
            xml_text: Pre-fetched RSS XML string.  When provided the scraper
                skips the HTTP fetch — useful in Lambda or test contexts where
                the content has already been retrieved via ``urllib`` or similar.
        """
        execution = self._new_execution()

        if self.cloud not in VALID_CLOUDS:
            raise ValueError(
                f"Unknown cloud '{self.cloud}'. Valid: {', '.join(sorted(VALID_CLOUDS))}"
            )

        rss_url = build_rss_url(self.source_url, self.cloud)
        target_month = parse_month_filter(self.date_filter)

        # Fetch the RSS feed if raw content was not pre-supplied
        if xml_text is None:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                resp = await page.goto(rss_url, wait_until="networkidle", timeout=30000)
                xml_text = await resp.text()
                await browser.close()

        items = parse_rss_xml(xml_text)

        for item in items:
            # Prefer the explicit deployment_date query param; fall back to pubDate
            iso_date = item["deployment_date"] or item["iso_date"]

            # Filter by month if specified
            if target_month is not None:
                try:
                    month = int(iso_date.split("-")[1]) if iso_date else 0
                except (IndexError, ValueError):
                    month = 0
                if month != target_month:
                    continue

            result = ScrapeResult(
                title=item["title"],
                description=item["description_text"],
                date=iso_date,
                source_url=item["link"],
                category="release_upgrade",
                status=item["category"],  # "Feature Available", "Feature in Limited Availability", etc.
                metadata={
                    "item_id": item["item_id"],
                    "guid": item["guid"],
                    "deployment_date": item["deployment_date"],
                },
            )
            execution.results.append(result)

        execution.notes = f"Scraped from RSS feed: {rss_url}"

        return execution
