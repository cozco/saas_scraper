"""Data models for SaaS scraper output."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def generate_execution_id() -> str:
    """Generate a unique execution ID: YYYYMMDD-HHMMSS-<short_uuid>."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    short_id = uuid.uuid4().hex[:8]
    return f"{ts}-{short_id}"


@dataclass
class ScrapeResult:
    """A single scraped item (release note, URL change, advisory, etc.)."""
    title: str
    description: str
    date: str  # ISO-8601 date string of when the change applies
    source_url: str
    category: str  # e.g. "release_upgrade", "url_category_change"
    status: str = ""  # e.g. "In Progress", "Resolved", "Feature Available"
    severity: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert this result to a plain dictionary for JSON serialisation."""
        return asdict(self)


@dataclass
class ScrapeExecution:
    """Top-level container for a scrape execution run."""
    execution_id: str
    platform: str  # e.g. "Zscaler"
    cloud: str  # e.g. "zscalertwo.net"
    scrape_type: str  # e.g. "release_upgrade_summary", "url_category_changes"
    source_url: str
    scrape_timestamp: str  # ISO-8601 when the scrape ran
    date_filter: str  # what date range was targeted
    results: list[ScrapeResult] = field(default_factory=list)
    notes: str = ""  # optional notes about the scrape (e.g. actual feed URL used)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dictionary, adding a computed ``total_results`` count."""
        d = asdict(self)
        d["total_results"] = len(self.results)
        return d
