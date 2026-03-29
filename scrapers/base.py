"""Base scraper class."""
from __future__ import annotations

import abc
from datetime import datetime, timezone

from models import ScrapeExecution, generate_execution_id


class BaseScraper(abc.ABC):
    """Abstract base for all SaaS scrapers."""

    platform: str = ""
    scrape_type: str = ""

    def __init__(self, source_url: str, cloud: str, date_filter: str) -> None:
        """Initialise the scraper with target URL, cloud name, and date filter.

        Args:
            source_url: The page URL that identifies the data source.
            cloud: Vendor cloud instance to target (e.g. ``zscalertwo.net``).
            date_filter: A date/month/year string used to narrow results.
        """
        self.source_url = source_url
        self.cloud = cloud
        self.date_filter = date_filter

    @abc.abstractmethod
    async def scrape(self) -> ScrapeExecution:
        """Execute the scrape and return a ScrapeExecution."""
        ...

    def _new_execution(self) -> ScrapeExecution:
        """Create a ScrapeExecution shell pre-filled with common fields."""
        return ScrapeExecution(
            execution_id=generate_execution_id(),
            platform=self.platform,
            cloud=self.cloud,
            scrape_type=self.scrape_type,
            source_url=self.source_url,
            scrape_timestamp=datetime.now(timezone.utc).isoformat(),
            date_filter=self.date_filter,
        )
