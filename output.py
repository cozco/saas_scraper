"""Output writers for scrape results — JSON and TXT formats."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from models import ScrapeExecution


def _output_dir() -> str:
    """Return the absolute path to the ``output/`` directory next to this file."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def _ensure_output_dir() -> str:
    """Create the output directory if it doesn't exist and return its path."""
    path = _output_dir()
    os.makedirs(path, exist_ok=True)
    return path


def build_filename(execution: ScrapeExecution, ext: str) -> str:
    """Build a descriptive filename: {platform}_{scrape_type}_{cloud}_{execution_id}.{ext}"""
    safe_cloud = execution.cloud.replace(".", "_")
    return f"{execution.platform}_{execution.scrape_type}_{safe_cloud}_{execution.execution_id}.{ext}"


def write_json(execution: ScrapeExecution) -> str:
    """Write the execution to a JSON file. Returns the file path."""
    out_dir = _ensure_output_dir()
    filename = build_filename(execution, "json")
    path = os.path.join(out_dir, filename)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(execution.to_dict(), f, indent=2, ensure_ascii=False)

    return path


def write_txt(execution: ScrapeExecution) -> str:
    """Write a human-readable TXT summary. Returns the file path."""
    out_dir = _ensure_output_dir()
    filename = build_filename(execution, "txt")
    path = os.path.join(out_dir, filename)

    lines: list[str] = []
    lines.append("=" * 80)
    lines.append(f"SaaS Scraper Report")
    lines.append("=" * 80)
    lines.append(f"Execution ID : {execution.execution_id}")
    lines.append(f"Platform     : {execution.platform}")
    lines.append(f"Cloud        : {execution.cloud}")
    lines.append(f"Scrape Type  : {execution.scrape_type}")
    lines.append(f"Source URL   : {execution.source_url}")
    lines.append(f"Date Filter  : {execution.date_filter}")
    lines.append(f"Scraped At   : {execution.scrape_timestamp}")
    lines.append(f"Total Results: {len(execution.results)}")
    if execution.notes:
        lines.append(f"Notes        : {execution.notes}")
    lines.append("=" * 80)
    lines.append("")

    for i, result in enumerate(execution.results, 1):
        lines.append(f"--- Result {i} ---")
        lines.append(f"  Title      : {result.title}")
        lines.append(f"  Date       : {result.date}")
        lines.append(f"  Status     : {result.status}")
        if result.severity:
            lines.append(f"  Severity   : {result.severity}")
        lines.append(f"  Category   : {result.category}")
        lines.append(f"  Source URL  : {result.source_url}")

        # Truncate long descriptions for readability
        desc = result.description
        if len(desc) > 300:
            desc = desc[:297] + "..."
        lines.append(f"  Description: {desc}")

        # Show metadata summary — special-case domain_changes (list of dicts)
        # vs generic string metadata (item_id, guid, etc.)
        if result.metadata:
            if "domain_changes" in result.metadata:
                n = len(result.metadata["domain_changes"])
                lines.append(f"  Domain Changes: {n} entries")
                # Preview the first 5 domain changes for quick scanning
                for entry in result.metadata["domain_changes"][:5]:
                    domain = entry.get("Domain/Sub-Domain", "")
                    current = entry.get("Current Category", "")
                    # The "updated" column name varies (e.g. "Updated Category (From 03/01)")
                    # so we grab the last value in the dict as the new category.
                    updated = list(entry.values())[-1] if len(entry) > 2 else ""
                    lines.append(f"    {domain}: {current} → {updated}")
                if n > 5:
                    lines.append(f"    ... and {n - 5} more")
            else:
                # Generic metadata: print non-empty string values
                for k, v in result.metadata.items():
                    if isinstance(v, str) and v:
                        lines.append(f"  {k}: {v}")

        lines.append("")

    lines.append("=" * 80)
    lines.append(f"End of report. Generated {datetime.now(timezone.utc).isoformat()}")
    lines.append("=" * 80)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return path
