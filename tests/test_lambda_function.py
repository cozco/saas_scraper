"""Tests for the Lambda handler and its helper functions."""
import sys
import os
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from models import ScrapeExecution, ScrapeResult
from lambda_function import (
    _fetch_url,
    _generate_json_content,
    _generate_txt_content,
    _upload_to_s3,
    _async_handler,
    lambda_handler,
)


def _sample_execution() -> ScrapeExecution:
    """Create a minimal ScrapeExecution for testing."""
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
                description="A test feature",
                date="2026-03-20",
                source_url="https://example.com/1",
                category="release_upgrade",
                status="Feature Available",
            ),
        ],
        notes="Test note",
    )


class TestGenerateJsonContent:
    def test_produces_valid_json(self):
        execution = _sample_execution()
        content = _generate_json_content(execution)
        data = json.loads(content)
        assert data["execution_id"] == "20260329-120000-abcd1234"
        assert data["total_results"] == 1
        assert data["results"][0]["title"] == "Test Feature"

    def test_empty_results(self):
        execution = _sample_execution()
        execution.results = []
        data = json.loads(_generate_json_content(execution))
        assert data["total_results"] == 0


class TestGenerateTxtContent:
    def test_contains_header(self):
        txt = _generate_txt_content(_sample_execution())
        assert "SaaS Scraper Report" in txt
        assert "Execution ID : 20260329-120000-abcd1234" in txt

    def test_contains_results(self):
        txt = _generate_txt_content(_sample_execution())
        assert "Test Feature" in txt
        assert "2026-03-20" in txt

    def test_contains_notes(self):
        txt = _generate_txt_content(_sample_execution())
        assert "Test note" in txt

    def test_domain_changes_in_txt(self):
        execution = _sample_execution()
        execution.results = [
            ScrapeResult(
                title="URL Changes",
                description="2 changes",
                date="2026-03-01",
                source_url="https://example.com",
                category="url_category_change",
                metadata={
                    "domain_changes": [
                        {"Domain/Sub-Domain": ".example.com", "Current Category": "A", "Updated Category": "B"},
                    ],
                },
            ),
        ]
        txt = _generate_txt_content(execution)
        assert "Domain Changes: 1 entries" in txt
        assert ".example.com" in txt


class TestUploadToS3:
    def test_calls_put_object(self):
        # boto3 is imported locally inside _upload_to_s3, so we mock it at module level
        mock_s3_client = MagicMock()
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            _upload_to_s3("my-bucket", "prefix/file.json", '{"test": 1}', "application/json")

        mock_boto3.client.assert_called_once_with("s3")
        mock_s3_client.put_object.assert_called_once_with(
            Bucket="my-bucket",
            Key="prefix/file.json",
            Body=b'{"test": 1}',
            ContentType="application/json",
        )


class TestFetchUrl:
    @patch("lambda_function.urllib.request.urlopen")
    def test_returns_decoded_response(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<rss>test</rss>"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = _fetch_url("https://example.com/feed.xml")
        assert result == "<rss>test</rss>"


class TestAsyncHandler:
    @pytest.mark.asyncio
    @patch("lambda_function._upload_to_s3")
    @patch("lambda_function._run_url_changes_scraper")
    @patch("lambda_function._run_release_scraper")
    async def test_runs_all_scrapers(self, mock_release, mock_url_changes, mock_upload):
        mock_release.return_value = _sample_execution()
        url_exec = _sample_execution()
        url_exec.scrape_type = "url_category_changes"
        mock_url_changes.return_value = url_exec

        result = await _async_handler({
            "s3_bucket": "test-bucket",
            "s3_prefix": "output",
            "scrapers": ["all"],
        })

        assert result["statusCode"] == 200
        assert len(result["body"]["uploads"]) == 2
        # 2 scrapers x 2 files each = 4 uploads
        assert mock_upload.call_count == 4

    @pytest.mark.asyncio
    @patch("lambda_function._upload_to_s3")
    @patch("lambda_function._run_release_scraper")
    async def test_single_scraper(self, mock_release, mock_upload):
        mock_release.return_value = _sample_execution()

        result = await _async_handler({
            "s3_bucket": "test-bucket",
            "scrapers": ["zscaler_release"],
        })

        assert result["statusCode"] == 200
        assert len(result["body"]["uploads"]) == 1
        assert result["body"]["uploads"][0]["scraper"] == "zscaler_release"

    @pytest.mark.asyncio
    async def test_missing_bucket_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="S3_BUCKET"):
                await _async_handler({"scrapers": ["zscaler_release"]})

    @pytest.mark.asyncio
    @patch("lambda_function._upload_to_s3")
    @patch("lambda_function._run_release_scraper")
    async def test_uses_env_vars(self, mock_release, mock_upload):
        mock_release.return_value = _sample_execution()

        with patch.dict(os.environ, {"S3_BUCKET": "env-bucket", "S3_PREFIX": "env-prefix", "CLOUD": "zscaler.net"}):
            result = await _async_handler({"scrapers": ["zscaler_release"]})

        assert result["statusCode"] == 200
        # Check that the upload used the env prefix
        first_upload_key = mock_upload.call_args_list[0][0][1]
        assert first_upload_key.startswith("env-prefix/")

    @pytest.mark.asyncio
    @patch("lambda_function._upload_to_s3")
    @patch("lambda_function._run_release_scraper")
    async def test_event_overrides_env(self, mock_release, mock_upload):
        mock_release.return_value = _sample_execution()

        with patch.dict(os.environ, {"S3_BUCKET": "env-bucket", "S3_PREFIX": "env-prefix"}):
            result = await _async_handler({
                "s3_bucket": "event-bucket",
                "s3_prefix": "event-prefix",
                "scrapers": ["zscaler_release"],
            })

        # Event values should take precedence
        first_call_bucket = mock_upload.call_args_list[0][0][0]
        assert first_call_bucket == "event-bucket"

    @pytest.mark.asyncio
    @patch("lambda_function._upload_to_s3")
    async def test_custom_date_filter(self, mock_upload):
        from unittest.mock import AsyncMock
        mock_runner = AsyncMock(return_value=_sample_execution())

        with patch.dict("lambda_function.SCRAPER_RUNNERS", {"zscaler_release": mock_runner}):
            await _async_handler({
                "s3_bucket": "test-bucket",
                "scrapers": ["zscaler_release"],
                "date_filters": {"zscaler_release": "February"},
            })

        # Verify the scraper runner was called with the custom date filter
        mock_runner.assert_called_once_with("zscalertwo.net", "February")

    @pytest.mark.asyncio
    @patch("lambda_function._upload_to_s3")
    @patch("lambda_function._run_release_scraper")
    async def test_upload_keys_structure(self, mock_release, mock_upload):
        mock_release.return_value = _sample_execution()

        await _async_handler({
            "s3_bucket": "test-bucket",
            "s3_prefix": "my-output",
            "scrapers": ["zscaler_release"],
        })

        json_key = mock_upload.call_args_list[0][0][1]
        txt_key = mock_upload.call_args_list[1][0][1]
        assert json_key.startswith("my-output/")
        assert json_key.endswith(".json")
        assert txt_key.startswith("my-output/")
        assert txt_key.endswith(".txt")


class TestLambdaHandler:
    @patch("lambda_function._async_handler")
    def test_delegates_to_async(self, mock_async):
        """Verify the sync entry point runs the async handler."""
        import asyncio

        mock_async.return_value = {"statusCode": 200, "body": {}}

        result = lambda_handler({"s3_bucket": "b"}, None)
        assert result["statusCode"] == 200

    @patch("lambda_function._async_handler")
    def test_none_event_becomes_empty_dict(self, mock_async):
        mock_async.return_value = {"statusCode": 200, "body": {}}
        lambda_handler(None, None)
        # The async handler should have received {}
        mock_async.assert_called_once()
