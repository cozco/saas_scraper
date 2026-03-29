# SaaS Security Scraper

A Python tool that scrapes changes, advisories, and updates from SaaS security vendors and outputs structured JSON and human-readable TXT reports. Can run locally via the CLI or in AWS Lambda with S3 output.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

> **Note:** Playwright and Chromium are only required for the local CLI (`main.py`). The Lambda handler (`lambda_function.py`) uses `urllib` from the standard library and does not need Playwright.

## CLI Usage

```
python main.py <scraper> [options]
```

### Positional Argument

| Argument | Required | Description |
|----------|----------|-------------|
| `scraper` | Yes | Which scraper to run. See [Available Scrapers](#available-scrapers) below. |

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--url <URL>` | *(none)* | Source URL to scrape. **Required** when running a specific scraper. Ignored when using `all`. |
| `--cloud <CLOUD>` | `zscalertwo.net` | Zscaler cloud name to target. |
| `--date-filter <FILTER>` | `all` | Date filter to narrow results. Accepts a month name (`March`), `YYYY-MM` (`2026-03`), a year (`2026`), or `all`. |
| `-h`, `--help` | | Show help message and exit. |

### Available Scrapers

| Scraper Name | Description | Expected `--url` | `--date-filter` format |
|--------------|-------------|-------------------|------------------------|
| `zscaler_release` | Zscaler ZIA Release Upgrade Summary (via RSS feed) | `https://help.zscaler.com/zia/release-upgrade-summary-2026` | Month name or `YYYY-MM` (e.g. `March`, `2026-03`) |
| `zscaler_url_changes` | Zscaler Trust URL Category Change Notifications (via JSON feed) | `https://trust.zscaler.com/notifications/url-change-notification` | Year (e.g. `2026`) |
| `all` | Runs all Zscaler scrapers with default URLs and date filters | *(ignored)* | *(ignored -- uses `March` for releases, `2026` for URL changes)* |

### Supported Clouds

When using `--cloud`, the following Zscaler clouds are valid:

- `zscaler.net`
- `zscalerone.net`
- `zscalertwo.net`
- `zscalerthree.net`
- `zscloud.net`
- `zscalerbeta.net`

### CLI Examples

```bash
# Run all Zscaler scrapers with defaults (zscalertwo.net, March releases, 2026 URL changes)
python main.py all

# Run all scrapers against a different cloud
python main.py all --cloud zscalerone.net

# Scrape release upgrades for March only
python main.py zscaler_release \
  --url https://help.zscaler.com/zia/release-upgrade-summary-2026 \
  --cloud zscalertwo.net \
  --date-filter March

# Scrape release upgrades for all dates
python main.py zscaler_release \
  --url https://help.zscaler.com/zia/release-upgrade-summary-2026 \
  --cloud zscalertwo.net \
  --date-filter all

# Scrape URL category changes for 2026
python main.py zscaler_url_changes \
  --url https://trust.zscaler.com/notifications/url-change-notification \
  --cloud zscalertwo.net \
  --date-filter 2026
```

## AWS Lambda Usage

The `lambda_function.py` module provides a Lambda-compatible entry point that runs the scrapers and uploads JSON + TXT output files to an S3 bucket. It does **not** require Playwright -- it uses Python's built-in `urllib` to fetch the RSS/JSON feeds directly.

### Lambda Handler

- **Handler**: `lambda_function.lambda_handler`
- **Runtime**: Python 3.12+
- **Required IAM permissions**: `s3:PutObject` on the target bucket

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `S3_BUCKET` | Yes (unless provided in event) | *(none)* | Target S3 bucket name. |
| `S3_PREFIX` | No | `scraper-output` | Key prefix / folder inside the bucket. |
| `CLOUD` | No | `zscalertwo.net` | Zscaler cloud to scrape. |

### Event Payload Schema

All fields are optional -- sensible defaults are used when omitted.

```json
{
  "scrapers": ["zscaler_release", "zscaler_url_changes"],
  "cloud": "zscalertwo.net",
  "date_filters": {
    "zscaler_release": "March",
    "zscaler_url_changes": "2026"
  },
  "s3_bucket": "my-bucket",
  "s3_prefix": "scraper-output"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `scrapers` | `string[]` | `["all"]` | List of scraper names to run, or `["all"]` for all. |
| `cloud` | `string` | `zscalertwo.net` | Zscaler cloud to target. |
| `date_filters` | `object` | `{"zscaler_release": "March", "zscaler_url_changes": "2026"}` | Per-scraper date filter overrides. |
| `s3_bucket` | `string` | Value of `S3_BUCKET` env var | Target S3 bucket (overrides env var). |
| `s3_prefix` | `string` | Value of `S3_PREFIX` env var or `scraper-output` | S3 key prefix (overrides env var). |

### Lambda Response

```json
{
  "statusCode": 200,
  "body": {
    "message": "Completed 2 scraper(s)",
    "uploads": [
      {
        "scraper": "zscaler_release",
        "execution_id": "20260329-120000-abcd1234",
        "results_count": 25,
        "json_key": "s3://my-bucket/scraper-output/Zscaler_release_upgrade_summary_zscalertwo_net_20260329-120000-abcd1234.json",
        "txt_key": "s3://my-bucket/scraper-output/Zscaler_release_upgrade_summary_zscalertwo_net_20260329-120000-abcd1234.txt"
      },
      {
        "scraper": "zscaler_url_changes",
        "execution_id": "20260329-120001-efgh5678",
        "results_count": 4,
        "json_key": "s3://my-bucket/scraper-output/Zscaler_url_category_changes_zscalertwo_net_20260329-120001-efgh5678.json",
        "txt_key": "s3://my-bucket/scraper-output/Zscaler_url_category_changes_zscalertwo_net_20260329-120001-efgh5678.txt"
      }
    ]
  }
}
```

### Lambda Deployment

Package the following files into a deployment zip (no Playwright or Chromium needed):

```
lambda_function.py    # Lambda entry point
models.py
output.py
scrapers/
  __init__.py
  base.py
  zscaler_release.py
  zscaler_url_changes.py
```

`boto3` is pre-installed in the Lambda runtime. No additional dependencies are required.

### Lambda Event Examples

```json
// Run all scrapers with defaults
{}

// Run only the release scraper for January
{
  "scrapers": ["zscaler_release"],
  "date_filters": {"zscaler_release": "January"},
  "s3_bucket": "my-security-data"
}

// Target a different cloud
{
  "cloud": "zscalerone.net",
  "s3_bucket": "my-security-data",
  "s3_prefix": "zscaler/2026"
}
```

## Output

Each scraper run produces two files:

- **JSON** (`<platform>_<type>_<cloud>_<execution_id>.json`) -- structured data suitable for database storage
- **TXT** (`<platform>_<type>_<cloud>_<execution_id>.txt`) -- human-readable summary report

When run via CLI, files are written to the local `output/` directory. When run via Lambda, files are uploaded to the configured S3 bucket.

### JSON Schema

| Field | Type | Description |
|-------|------|-------------|
| `execution_id` | `string` | Unique ID for the run (`YYYYMMDD-HHMMSS-<uuid>`) |
| `platform` | `string` | Vendor name (e.g. `Zscaler`) |
| `cloud` | `string` | Target cloud (e.g. `zscalertwo.net`) |
| `scrape_type` | `string` | `release_upgrade_summary` or `url_category_changes` |
| `source_url` | `string` | Original URL provided |
| `scrape_timestamp` | `string` | ISO-8601 timestamp of when the scrape ran |
| `date_filter` | `string` | The date filter that was applied |
| `total_results` | `integer` | Number of results returned |
| `notes` | `string` | Additional context (e.g. actual feed URL used) |
| `results` | `array` | List of result objects (see below) |

### Result Object

| Field | Type | Description |
|-------|------|-------------|
| `title` | `string` | Title of the change/feature/notification |
| `description` | `string` | Plain-text description |
| `date` | `string` | ISO date the change applies (`YYYY-MM-DD`) |
| `source_url` | `string` | Direct link to the specific item |
| `category` | `string` | `release_upgrade` or `url_category_change` |
| `status` | `string` | e.g. `Feature Available`, `Feature in Limited Availability` |
| `severity` | `string` | Severity level (when available) |
| `metadata` | `object` | Scraper-specific extra data (item IDs, domain change lists, etc.) |

## Running Tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

## Project Structure

```
saas_scaper/
├── main.py                          # CLI entry point
├── lambda_function.py               # AWS Lambda entry point (S3 output)
├── models.py                        # ScrapeResult + ScrapeExecution dataclasses
├── output.py                        # JSON + TXT file writers (local)
├── requirements.txt                 # Python dependencies
├── scrapers/
│   ├── __init__.py
│   ├── base.py                      # Abstract BaseScraper
│   ├── zscaler_release.py           # RSS feed scraper for release upgrades
│   └── zscaler_url_changes.py       # JSON feed scraper for URL category changes
├── tests/
│   ├── test_models.py
│   ├── test_output.py
│   ├── test_zscaler_release.py
│   ├── test_zscaler_url_changes.py
│   └── test_lambda_function.py
└── output/                          # Local CLI output directory
```
