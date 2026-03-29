"""Tests for the Zscaler Release Upgrade scraper (RSS-based)."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.zscaler_release import (
    build_rss_url,
    parse_month_filter,
    parse_rss_date,
    strip_html,
    extract_id_from_link,
    extract_deployment_date_from_link,
    parse_rss_xml,
)


class TestBuildRssUrl:
    def test_standard(self):
        url = build_rss_url(
            "https://help.zscaler.com/zia/release-upgrade-summary-2026",
            "zscalertwo.net",
        )
        assert url == "https://help.zscaler.com/rss-feed/zia/release-upgrade-summary-2026/zscalertwo.net"

    def test_different_year(self):
        url = build_rss_url(
            "https://help.zscaler.com/zia/release-upgrade-summary-2025",
            "zscaler.net",
        )
        assert url == "https://help.zscaler.com/rss-feed/zia/release-upgrade-summary-2025/zscaler.net"

    def test_no_year_defaults_2026(self):
        url = build_rss_url("https://help.zscaler.com/zia/release-upgrade-summary", "zscloud.net")
        assert url == "https://help.zscaler.com/rss-feed/zia/release-upgrade-summary-2026/zscloud.net"


class TestParseMonthFilter:
    def test_month_name(self):
        assert parse_month_filter("March") == 3
        assert parse_month_filter("march") == 3
        assert parse_month_filter("JANUARY") == 1

    def test_iso_format(self):
        assert parse_month_filter("2026-03") == 3
        assert parse_month_filter("2026-12") == 12

    def test_two_digit(self):
        assert parse_month_filter("03") == 3

    def test_all(self):
        assert parse_month_filter("all") is None
        assert parse_month_filter("All") is None

    def test_invalid(self):
        assert parse_month_filter("foobar") is None


class TestParseRssDate:
    def test_standard(self):
        assert parse_rss_date("Fri, 20 Mar 2026 07:00:00 GMT") == "2026-03-20"

    def test_another_date(self):
        assert parse_rss_date("Wed, 18 Mar 2026 07:00:00 GMT") == "2026-03-18"

    def test_invalid(self):
        assert parse_rss_date("not a date") == ""

    def test_empty(self):
        assert parse_rss_date("") == ""


class TestStripHtml:
    def test_basic(self):
        assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_entities(self):
        # After unescape, <tag> becomes an HTML tag and is stripped
        assert strip_html("&lt;tag&gt; &amp; more") == "& more"

    def test_amp_entity(self):
        assert strip_html("foo &amp; bar") == "foo & bar"

    def test_empty(self):
        assert strip_html("") == ""

    def test_nested(self):
        result = strip_html('<div class="sub"><p>Feature text</p></div>')
        assert result == "Feature text"


class TestExtractIdFromLink:
    def test_standard(self):
        link = "https://help.zscaler.com/zia/release-upgrade-summary-2026?applicable_category=zscalertwo.net&deployment_date=2026-03-20&id=1533702"
        assert extract_id_from_link(link) == "1533702"

    def test_no_id(self):
        assert extract_id_from_link("https://example.com") == ""


class TestExtractDeploymentDate:
    def test_standard(self):
        link = "https://help.zscaler.com/zia/release-upgrade-summary-2026?deployment_date=2026-03-20&id=123"
        assert extract_deployment_date_from_link(link) == "2026-03-20"

    def test_no_date(self):
        assert extract_deployment_date_from_link("https://example.com") == ""


class TestParseRssXml:
    SAMPLE_RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Release Upgrade Summary (2026)</title>
    <item>
      <title>Support for Copilot</title>
      <link>https://help.zscaler.com/zia/release-upgrade-summary-2026?applicable_category=zscalertwo.net&amp;deployment_date=2026-03-20&amp;id=1533702</link>
      <description>&lt;div class="sub"&gt;&lt;p&gt;Organizations face risk...&lt;/p&gt;&lt;/div&gt;</description>
      <category>Feature Available</category>
      <pubDate>Fri, 20 Mar 2026 07:00:00 GMT</pubDate>
      <guid isPermaLink="false">feature 1533702 at https://help.zscaler.com</guid>
    </item>
    <item>
      <title>Cloud Custom IPS</title>
      <link>https://help.zscaler.com/zia/release-upgrade-summary-2026?applicable_category=zscalertwo.net&amp;deployment_date=2026-03-18&amp;id=1533635</link>
      <description>&lt;p&gt;Custom IPS on cloud&lt;/p&gt;</description>
      <category>Feature in Limited Availability</category>
      <pubDate>Wed, 18 Mar 2026 07:00:00 GMT</pubDate>
      <guid isPermaLink="false">feature 1533635 at https://help.zscaler.com</guid>
    </item>
    <item>
      <title>January Feature</title>
      <link>https://help.zscaler.com/zia/release-upgrade-summary-2026?applicable_category=zscalertwo.net&amp;deployment_date=2026-01-15&amp;id=100</link>
      <description>&lt;p&gt;Old feature&lt;/p&gt;</description>
      <category>Feature Available</category>
      <pubDate>Wed, 15 Jan 2026 07:00:00 GMT</pubDate>
      <guid isPermaLink="false">feature 100 at https://help.zscaler.com</guid>
    </item>
  </channel>
</rss>"""

    def test_parse_count(self):
        items = parse_rss_xml(self.SAMPLE_RSS)
        assert len(items) == 3

    def test_first_item_fields(self):
        items = parse_rss_xml(self.SAMPLE_RSS)
        first = items[0]
        assert first["title"] == "Support for Copilot"
        assert first["category"] == "Feature Available"
        assert first["iso_date"] == "2026-03-20"
        assert first["deployment_date"] == "2026-03-20"
        assert first["item_id"] == "1533702"

    def test_description_stripped(self):
        items = parse_rss_xml(self.SAMPLE_RSS)
        # Should be plain text, no HTML tags
        assert "<" not in items[0]["description_text"]

    def test_empty_rss(self):
        xml = '<?xml version="1.0"?><rss><channel></channel></rss>'
        assert parse_rss_xml(xml) == []
