"""Tests for data models."""
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import generate_execution_id, ScrapeResult, ScrapeExecution


class TestGenerateExecutionId:
    def test_format(self):
        eid = generate_execution_id()
        # Expected: YYYYMMDD-HHMMSS-<8 hex chars>
        assert re.match(r"\d{8}-\d{6}-[0-9a-f]{8}", eid)

    def test_uniqueness(self):
        ids = {generate_execution_id() for _ in range(100)}
        assert len(ids) == 100


class TestScrapeResult:
    def test_to_dict(self):
        r = ScrapeResult(
            title="Test Feature",
            description="A test",
            date="2026-03-20",
            source_url="https://example.com",
            category="release_upgrade",
            status="Feature Available",
        )
        d = r.to_dict()
        assert d["title"] == "Test Feature"
        assert d["date"] == "2026-03-20"
        assert d["status"] == "Feature Available"
        assert d["metadata"] == {}

    def test_defaults(self):
        r = ScrapeResult(
            title="T", description="D", date="2026-01-01",
            source_url="", category="test",
        )
        assert r.status == ""
        assert r.severity == ""
        assert r.metadata == {}


class TestScrapeExecution:
    def test_to_dict_includes_total_results(self):
        e = ScrapeExecution(
            execution_id="20260329-120000-abcd1234",
            platform="Zscaler",
            cloud="zscalertwo.net",
            scrape_type="release_upgrade_summary",
            source_url="https://example.com",
            scrape_timestamp="2026-03-29T12:00:00+00:00",
            date_filter="March",
            results=[
                ScrapeResult(
                    title="F1", description="D1", date="2026-03-20",
                    source_url="", category="release_upgrade",
                ),
                ScrapeResult(
                    title="F2", description="D2", date="2026-03-18",
                    source_url="", category="release_upgrade",
                ),
            ],
        )
        d = e.to_dict()
        assert d["total_results"] == 2
        assert d["platform"] == "Zscaler"
        assert d["cloud"] == "zscalertwo.net"
        assert len(d["results"]) == 2

    def test_empty_results(self):
        e = ScrapeExecution(
            execution_id="test",
            platform="Zscaler",
            cloud="zscalertwo.net",
            scrape_type="test",
            source_url="",
            scrape_timestamp="",
            date_filter="all",
        )
        assert e.to_dict()["total_results"] == 0
