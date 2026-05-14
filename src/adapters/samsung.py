"""
adapters/samsung.py — 삼성전자 recruit.samsung.com adapter.
robots.txt: empty (no restrictions).
Technique: Playwright (SPA — JS-rendered).
"""
import json
import time
from typing import List, Optional

from .base import BaseAdapter, RawJobRecord, _now

BASE_URL = "https://recruit.samsung.com"
LIST_URL = f"{BASE_URL}/global/jobSearch/list.do"

# Samsung uses an internal API — try to intercept it; fall back to DOM scraping
SEARCH_KEYWORDS = ["BIM", "facility", "VDC", "digital", "설계관리"]


class SamsungAdapter(BaseAdapter):
    site_name = "samsung_careers"
    requires_playwright = True
    request_delay = 3.0

    def fetch_job_list(self, **kwargs) -> List[str]:
        from playwright.sync_api import sync_playwright

        urls: list = []
        api_responses: list = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = ctx.new_page()

            # Intercept XHR/fetch to capture job list API responses
            def handle_response(response):
                if "jobSearch" in response.url and response.status == 200:
                    try:
                        api_responses.append(response.json())
                    except Exception:
                        pass

            page.on("response", handle_response)

            for keyword in SEARCH_KEYWORDS:
                try:
                    page.goto(
                        f"{LIST_URL}?searchKeyword={keyword}",
                        wait_until="networkidle",
                        timeout=25000,
                    )
                    page.wait_for_timeout(2000)

                    # Try extracting from intercepted API first
                    for data in api_responses:
                        _extract_samsung_api_urls(data, urls)
                    api_responses.clear()

                    # Fallback: scrape DOM links
                    links = page.eval_on_selector_all(
                        "a[href*='jobSearch'], a[href*='recruitNo'], .list_item a",
                        "els => els.map(e => e.href).filter(h => h.includes('samsung.com'))"
                    )
                    for link in links:
                        if link not in urls:
                            urls.append(link)

                except Exception as e:
                    print(f"[samsung] list error keyword={keyword!r}: {e}")
                time.sleep(self.request_delay)

            browser.close()

        return list(dict.fromkeys(urls))  # dedupe, preserve order

    def fetch_job_detail(self, url: str) -> Optional[RawJobRecord]:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context()
            page = ctx.new_page()
            try:
                page.goto(url, wait_until="networkidle", timeout=25000)
                page.wait_for_timeout(1500)

                title = _get_text(page, [
                    "h1.job_tit", ".recruit_tit h1", ".detail_tit",
                    "h2.tit", ".job_title",
                ]) or page.title()

                body = _get_text(page, [
                    ".jd_wrap", ".job_description", ".contents_area",
                    ".recruit_detail", ".detail_content",
                ]) or _page_body(page)

                location = _get_text(page, [
                    ".work_area", ".location_info", ".jv_location",
                ])

                emp_type = _get_text(page, [
                    ".emp_type", ".employ_type", ".contract_type",
                ])

                return RawJobRecord(
                    source_site=self.site_name,
                    job_url=url,
                    raw_title=title,
                    raw_body=body[:8000],
                    raw_location=location,
                    raw_employment_type=emp_type,
                    fetched_html=page.content()[:50000],
                    fetched_at=_now(),
                )
            except Exception as e:
                print(f"[samsung] detail error {url}: {e}")
                return None
            finally:
                browser.close()


def _extract_samsung_api_urls(data: dict, urls: list) -> None:
    """Try to pull job URLs from common Samsung API response shapes."""
    items = (
        data.get("recruitList")
        or data.get("list")
        or data.get("data", {}).get("list", [])
        or []
    )
    for item in items:
        job_id = item.get("recruitNo") or item.get("jobId") or item.get("id")
        if job_id:
            url = f"{BASE_URL}/global/jobSearch/view.do?recruitNo={job_id}"
            if url not in urls:
                urls.append(url)


def _get_text(page, selectors: list) -> str:
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                return el.inner_text().strip()
        except Exception:
            pass
    return ""


def _page_body(page) -> str:
    try:
        return page.inner_text("body")[:8000]
    except Exception:
        return ""
