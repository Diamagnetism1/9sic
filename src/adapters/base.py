"""
adapters/base.py — BaseAdapter contract.
Every site adapter inherits this and implements fetch_job_list + fetch_job_detail.
"""
import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class RawJobRecord:
    source_site: str
    job_url: str
    raw_title: str
    raw_body: str
    raw_location: str = ""
    raw_employment_type: str = ""
    fetched_html: str = ""
    fetched_at: str = ""
    content_hash: str = ""
    http_status: int = 200


class BaseAdapter(ABC):
    site_name: str = ""
    requires_playwright: bool = False
    request_delay: float = 2.0  # seconds between requests — respect the server

    @abstractmethod
    def fetch_job_list(self, **kwargs) -> List[str]:
        """Return list of job detail URLs to crawl."""

    @abstractmethod
    def fetch_job_detail(self, url: str) -> Optional[RawJobRecord]:
        """Fetch one job detail page. Return None on failure."""

    def run(self, **kwargs) -> List[RawJobRecord]:
        """Orchestrate: list → detail fetch for each URL."""
        records = []
        urls = self.fetch_job_list(**kwargs)
        print(f"[{self.site_name}] Found {len(urls)} job URLs")

        for url in urls:
            try:
                record = self.fetch_job_detail(url)
                if record:
                    record.content_hash = _hash(record.raw_title + record.raw_body)
                    if not record.fetched_at:
                        record.fetched_at = _now()
                    records.append(record)
            except Exception as e:
                print(f"[{self.site_name}] Error fetching {url}: {e}")
            time.sleep(self.request_delay)

        print(f"[{self.site_name}] Collected {len(records)} records")
        return records

    def to_db_dict(self, record: RawJobRecord) -> dict:
        return {
            "source_site":         record.source_site,
            "job_url":             record.job_url,
            "raw_title":           record.raw_title,
            "raw_body":            record.raw_body[:20000],
            "raw_location":        record.raw_location,
            "raw_employment_type": record.raw_employment_type,
            "fetched_html":        record.fetched_html[:50000],
            "fetched_at":          record.fetched_at,
            "content_hash":        record.content_hash,
            "http_status":         record.http_status,
        }


def _hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
