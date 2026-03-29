"""Tests for the Zscaler URL Category Changes scraper."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.zscaler_url_changes import (
    parse_table_from_html,
    parse_change_date_from_title,
    matches_year_filter,
)


class TestParseTableFromHtml:
    SAMPLE_HTML = """
    <p>Description text</p>
    <table>
        <tr><td><strong>Domain/Sub-Domain</strong></td><td><strong>Current Category</strong></td><td><strong>Updated Category (From 03/01)</strong></td></tr>
        <tr><td>.cdn.office.net</td><td>Corporate Marketing</td><td>CDN</td></tr>
        <tr><td>.example.com</td><td>Internet Services</td><td>Developer Tools</td></tr>
    </table>
    """

    def test_basic_parsing(self):
        entries = parse_table_from_html(self.SAMPLE_HTML)
        assert len(entries) == 2

    def test_first_entry_fields(self):
        entries = parse_table_from_html(self.SAMPLE_HTML)
        first = entries[0]
        assert first["Domain/Sub-Domain"] == ".cdn.office.net"
        assert first["Current Category"] == "Corporate Marketing"

    def test_second_entry(self):
        entries = parse_table_from_html(self.SAMPLE_HTML)
        assert entries[1]["Domain/Sub-Domain"] == ".example.com"
        assert entries[1]["Current Category"] == "Internet Services"

    def test_empty_html(self):
        assert parse_table_from_html("") == []

    def test_no_table(self):
        assert parse_table_from_html("<p>No table here</p>") == []

    def test_table_no_domain_header(self):
        html = "<table><tr><td>A</td><td>B</td></tr><tr><td>1</td><td>2</td></tr></table>"
        # No "domain" in header → no entries parsed
        assert parse_table_from_html(html) == []


class TestParseChangeDateFromTitle:
    def test_standard_format(self):
        title = "URL Recategorization Notification || Change Date: Apr 19th, 2026"
        assert parse_change_date_from_title(title) == "2026-04-19"

    def test_march_format(self):
        title = "URL Recategorization Notification || Change Date: March 01, 2026"
        assert parse_change_date_from_title(title) == "2026-03-01"

    def test_no_ordinal(self):
        title = "URL Recategorization Notification || Change Date: Feb 08, 2026"
        assert parse_change_date_from_title(title) == "2026-02-08"

    def test_with_st_suffix(self):
        title = "Notification || Change Date: Jan 1st, 2026"
        assert parse_change_date_from_title(title) == "2026-01-01"

    def test_with_nd_suffix(self):
        title = "Notification || Change Date: Jan 2nd, 2026"
        assert parse_change_date_from_title(title) == "2026-01-02"

    def test_with_rd_suffix(self):
        title = "Notification || Change Date: Jan 3rd, 2026"
        assert parse_change_date_from_title(title) == "2026-01-03"

    def test_no_match(self):
        assert parse_change_date_from_title("Some random title") == ""

    def test_empty(self):
        assert parse_change_date_from_title("") == ""


class TestMatchesYearFilter:
    def test_match(self):
        assert matches_year_filter("2026-03-01", "2026") is True

    def test_no_match(self):
        assert matches_year_filter("2025-12-01", "2026") is False

    def test_empty_date(self):
        assert matches_year_filter("", "2026") is False

    def test_partial_match(self):
        assert matches_year_filter("2026-01-01", "2026") is True
