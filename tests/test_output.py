"""Tests for output writers."""
import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import ScrapeExecution, ScrapeResult
from output import write_json, write_txt, build_filename


def _sample_execution() -> ScrapeExecution:
    return ScrapeExecution(
        execution_id="20260329-120000-abcd1234",
        platform="Zscaler",
        cloud="zscalertwo.net",
        scrape_type="release_upgrade_summary",
        source_url="https://example.com",
        scrape_timestamp="2026-03-29T12:00:00+00:00",
        date_filter="March",
        results=[
            ScrapeResult(
                title="Test Feature",
                description="A test feature description",
                date="2026-03-20",
                source_url="https://example.com/1",
                category="release_upgrade",
                status="Feature Available",
                metadata={"item_id": "123"},
            ),
        ],
        notes="Test note",
    )


class TestBuildFilename:
    def test_standard(self):
        e = _sample_execution()
        name = build_filename(e, "json")
        assert name == "Zscaler_release_upgrade_summary_zscalertwo_net_20260329-120000-abcd1234.json"

    def test_txt(self):
        e = _sample_execution()
        name = build_filename(e, "txt")
        assert name.endswith(".txt")


class TestWriteJson:
    def test_creates_valid_json(self):
        e = _sample_execution()
        path = write_json(e)
        assert os.path.exists(path)
        with open(path) as f:
            data = json.load(f)
        assert data["execution_id"] == "20260329-120000-abcd1234"
        assert data["total_results"] == 1
        assert data["results"][0]["title"] == "Test Feature"
        # Cleanup
        os.remove(path)

    def test_empty_results(self):
        e = _sample_execution()
        e.results = []
        path = write_json(e)
        with open(path) as f:
            data = json.load(f)
        assert data["total_results"] == 0
        os.remove(path)


class TestWriteTxt:
    def test_creates_readable_file(self):
        e = _sample_execution()
        path = write_txt(e)
        assert os.path.exists(path)
        content = open(path).read()
        assert "Execution ID : 20260329-120000-abcd1234" in content
        assert "Platform     : Zscaler" in content
        assert "Test Feature" in content
        assert "Total Results: 1" in content
        os.remove(path)

    def test_includes_notes(self):
        e = _sample_execution()
        path = write_txt(e)
        content = open(path).read()
        assert "Test note" in content
        os.remove(path)

    def test_domain_changes_display(self):
        e = _sample_execution()
        e.results = [
            ScrapeResult(
                title="URL Changes",
                description="3 changes",
                date="2026-03-01",
                source_url="https://example.com",
                category="url_category_change",
                metadata={
                    "domain_changes": [
                        {"Domain/Sub-Domain": ".example.com", "Current Category": "A", "Updated Category": "B"},
                        {"Domain/Sub-Domain": ".test.com", "Current Category": "C", "Updated Category": "D"},
                    ]
                },
            ),
        ]
        path = write_txt(e)
        content = open(path).read()
        assert "Domain Changes: 2 entries" in content
        assert ".example.com" in content
        os.remove(path)
