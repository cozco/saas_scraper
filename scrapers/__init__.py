"""Scrapers package."""
from scrapers.zscaler_release import ZscalerReleaseScraper
from scrapers.zscaler_url_changes import ZscalerUrlChangesScraper

__all__ = ["ZscalerReleaseScraper", "ZscalerUrlChangesScraper"]
