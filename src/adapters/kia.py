"""
adapters/kia.py — 기아 careers.kia.com adapter.
robots.txt: 없음. SPA — Playwright 필요.
"""
from typing import List, Optional
from .base import BaseAdapter, RawJobRecord, _now

BASE_URL = "https://careers.kia.com"
SEARCH_KEYWORDS = ["BIM", "VDC", "facility", "설비", "디지털", "스마트팩토리"]


class KiaAdapter(BaseAdapter):
    site_name = "kia_careers"
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
                # 기아 채용 한국어 페이지
                page.goto(f"{BASE_URL}/ko/jobs", wait_until="networkidle", timeout=25000)
                page.wait_for_timeout(2000)

                for kw in SEARCH_KEYWORDS:
                    try:
                        search = page.query_selector("input[type='search'], input[placeholder*='검색'], .search-input")
                        if search:
                            search.fill("")
                            search.fill(kw)
                            page.keyboard.press("Enter")
                            page.wait_for_timeout(2000)

                        links = page.eval_on_selector_all(
                            "a[href*='/jobs/'], a[href*='jobId'], a[href*='position']",
                            "els => els.map(e => e.href).filter(h => h.includes('kia.com'))"
                        )
                        for link in links:
                            if link not in urls:
                                urls.append(link)
                    except Exception as e:
                        print(f"[kia] search kw={kw}: {e}")

            except Exception as e:
                print(f"[kia] list error: {e}")
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

                title = _get_text(page, ["h1", ".job-title", ".position-name", "[class*='title']"]) or page.title()
                body  = _get_text(page, [".job-description", ".detail-content", "[class*='description']"]) or page.inner_text("body")[:8000]
                location = _get_text(page, [".location", "[class*='location']", "[class*='workplace']"])
                emp_type = _get_text(page, [".employment-type", "[class*='type']"])

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
                print(f"[kia] detail error {url}: {e}")
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
