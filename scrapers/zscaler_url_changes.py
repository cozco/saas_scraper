"""Scraper for Zscaler Trust URL Category Change Notifications.

Uses the JSON feed at:
  https://trust.zscaler.com/rss-feed/url-category-notification?_format=json

This returns all URL category change notifications with embedded HTML tables.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from html.parser import HTMLParser

from models import ScrapeExecution, ScrapeResult
from scrapers.base import BaseScraper

JSON_FEED_URL = "https://trust.zscaler.com/rss-feed/url-category-notification?_format=json"


class _TableParser(HTMLParser):
    """Minimal HTML parser that extracts rows from <table> elements in the body HTML."""

    def __init__(self) -> None:
        """Initialise parser state for tracking table cells and rows."""
        super().__init__()
        self._in_td = False
        self._current_row: list[str] = []
        self._rows: list[list[str]] = []
        self._current_data = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """On ``<td>`` start collecting cell text; on ``<tr>`` reset the current row."""
        if tag == "td":
            self._in_td = True
            self._current_data = ""
        elif tag == "tr":
            self._current_row = []

    def handle_endtag(self, tag: str) -> None:
        """On ``</td>`` finish the cell; on ``</tr>`` store the completed row."""
        if tag == "td":
            self._in_td = False
            self._current_row.append(self._current_data.strip())
        elif tag == "tr" and self._current_row:
            self._rows.append(self._current_row)

    def handle_data(self, data: str) -> None:
        """Accumulate text content while inside a ``<td>`` element."""
        if self._in_td:
            self._current_data += data

    @property
    def rows(self) -> list[list[str]]:
        """Return all completed table rows as lists of cell strings."""
        return self._rows


def parse_table_from_html(html_body: str) -> list[dict[str, str]]:
    """Parse the HTML body of a notification into a list of domain change dicts."""
    parser = _TableParser()
    parser.feed(html_body)

    entries: list[dict[str, str]] = []
    header_row = None
    for row in parser.rows:
        if not row:
            continue
        # Detect the header row by looking for a cell containing "domain".
        # This works because every Zscaler URL-change table starts with a
        # "Domain/Sub-Domain" column header.
        if header_row is None and any("domain" in c.lower() for c in row):
            header_row = row
            continue
        # Map each data row's cells to the header column names
        if header_row and len(row) >= len(header_row):
            entry = {}
            for i, col in enumerate(header_row):
                entry[col.strip()] = row[i].strip() if i < len(row) else ""
            entries.append(entry)
    return entries


def parse_change_date_from_title(title: str) -> str:
    """Extract an ISO date from titles like '... Change Date: Apr 19th, 2026'."""
    # Match abbreviated or full month names, day with optional ordinal suffix,
    # and a 4-digit year after the "Change Date:" label.
    m = re.search(
        r"Change Date:\s*"
        r"((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
        r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
        r"Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4})",
        title,
        re.IGNORECASE,
    )
    if not m:
        return ""
    raw = m.group(1)
    # Strip ordinal suffixes (e.g. "19th" → "19") so strptime can parse it
    cleaned = re.sub(r"(\d+)(?:st|nd|rd|th)", r"\1", raw)
    # Try full and abbreviated month formats, with and without comma
    for fmt in ("%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            return datetime.strptime(cleaned.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def matches_year_filter(iso_date: str, year_filter: str) -> bool:
    """Check if an ISO date string falls within the year filter (e.g. '2026')."""
    if not iso_date:
        return False
    return iso_date.startswith(year_filter)


class ZscalerUrlChangesScraper(BaseScraper):
    """Scrape Zscaler Trust URL Category Change notifications via JSON feed."""

    platform = "Zscaler"
    scrape_type = "url_category_changes"

    async def scrape(self, raw_json: str | None = None) -> ScrapeExecution:
        """Fetch the JSON feed, filter notifications by year, and extract domain changes.

        Args:
            raw_json: Pre-fetched JSON string.  When provided the scraper
                skips the HTTP fetch — useful in Lambda or test contexts where
                the content has already been retrieved via ``urllib`` or similar.
        """
        execution = self._new_execution()

        # Fetch the JSON feed if raw content was not pre-supplied
        if raw_json is None:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                resp = await page.goto(JSON_FEED_URL, wait_until="networkidle", timeout=30000)
                raw_json = await resp.text()
                await browser.close()

        feed = json.loads(raw_json)
        items = feed.get("items", [])

        for item in items:
            change_date = parse_change_date_from_title(item.get("title", ""))
            if not matches_year_filter(change_date, self.date_filter):
                continue

            body_html = item.get("body", "")
            domain_entries = parse_table_from_html(body_html)

            result = ScrapeResult(
                title=item.get("title", ""),
                description=(
                    f"{len(domain_entries)} domain categorization changes "
                    f"scheduled for {change_date}"
                ),
                date=change_date,
                source_url=item.get("url", ""),
                category="url_category_change",
                status="",
                severity="",
                metadata={
                    "notification_id": item.get("id", ""),
                    "published": item.get("pubdate", ""),
                    "domain_changes": domain_entries,
                },
            )
            execution.results.append(result)

        execution.notes = f"Scraped from JSON feed: {JSON_FEED_URL}"
        return execution
