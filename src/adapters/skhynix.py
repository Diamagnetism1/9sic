"""
adapters/skhynix.py — SK하이닉스 careers.skhynix.com adapter.
robots.txt: 없음. SPA — Playwright 필요.
"""
import time
from typing import List, Optional
from .base import BaseAdapter, RawJobRecord, _now

BASE_URL = "https://careers.skhynix.com"
SEARCH_KEYWORDS = ["BIM", "VDC", "facility", "설비", "반도체", "cleanroom"]


class SKHynixAdapter(BaseAdapter):
    site_name = "skhynix_careers"
    requires_playwright = True
    request_delay = 3.0

    def fetch_job_list(self, **kwargs) -> List[str]:
        from playwright.sync_api import sync_playwright
        urls = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_context(user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )).new_page()

            try:
                page.goto(f"{BASE_URL}/jobs", wait_until="networkidle", timeout=25000)
                page.wait_for_timeout(2000)

                # 검색어 순회
                for kw in SEARCH_KEYWORDS:
                    try:
                        # 검색창 찾아서 입력
                        search = page.query_selector("input[type='search'], input[placeholder*='검색'], input[placeholder*='Search']")
                        if search:
                            search.fill(kw)
                            page.keyboard.press("Enter")
                            page.wait_for_timeout(2000)

                        links = page.eval_on_selector_all(
                            "a[href*='/jobs/'], a[href*='jobId'], a[href*='job-detail']",
                            "els => els.map(e => e.href).filter(h => h.includes('skhynix'))"
                        )
                        for link in links:
                            if link not in urls:
                                urls.append(link)
                    except Exception as e:
                        print(f"[skhynix] search error kw={kw}: {e}")

                # 검색 없이 전체 목록도 시도
                if not urls:
                    links = page.eval_on_selector_all(
                        "a[href*='/jobs/']",
                        "els => els.map(e => e.href).filter(h => h.includes('skhynix'))"
                    )
                    urls.extend([l for l in links if l not in urls])

            except Exception as e:
                print(f"[skhynix] list error: {e}")
            finally:
                browser.close()

        return list(dict.fromkeys(urls))

    def fetch_job_detail(self, url: str) -> Optional[RawJobRecord]:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_context().new_page()
            try:
                page.goto(url, wait_until="networkidle", timeout=25000)
                page.wait_for_timeout(1500)

                title = _get_text(page, [
                    "h1", ".job-title", ".position-title",
                    ".recruit-title", "[class*='title']"
                ]) or page.title()

                body = _get_text(page, [
                    ".job-description", ".jd-content", ".position-description",
                    ".recruit-detail", "[class*='description']", "[class*='content']"
                ]) or page.inner_text("body")[:8000]

                location = _get_text(page, [".location", ".work-place", "[class*='location']"])
                emp_type = _get_text(page, [".employment-type", "[class*='type']", ".contract"])

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
                print(f"[skhynix] detail error {url}: {e}")
                return None
            finally:
                browser.close()


def _get_text(page, selectors: list) -> str:
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if text:
                    return text
        except Exception:
            pass
    return ""
