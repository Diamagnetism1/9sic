"""
adapters/lg.py — LG careers.lg.com adapter.
robots.txt: 없음. React SPA — Playwright 필요.
"""
from typing import List, Optional
from .base import BaseAdapter, RawJobRecord, _now

BASE_URL = "https://careers.lg.com"
SEARCH_KEYWORDS = ["BIM", "VDC", "facility", "설비관리", "스마트팩토리", "디지털"]


class LGAdapter(BaseAdapter):
    site_name = "lg_careers"
    requires_playwright = True
    request_delay = 3.0

    def fetch_job_list(self, **kwargs) -> List[str]:
        from playwright.sync_api import sync_playwright
        urls = []
        api_jobs = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ))
            page = ctx.new_page()

            # API 응답 인터셉트
            def on_response(resp):
                if "job" in resp.url.lower() and resp.status == 200:
                    try:
                        data = resp.json()
                        _extract_lg_jobs(data, api_jobs)
                    except Exception:
                        pass
            page.on("response", on_response)

            try:
                page.goto(BASE_URL, wait_until="networkidle", timeout=25000)
                page.wait_for_timeout(2000)

                # API에서 수집된 job id로 URL 구성
                for job_id in api_jobs:
                    url = f"{BASE_URL}/jobs/{job_id}"
                    if url not in urls:
                        urls.append(url)

                # DOM fallback
                if not urls:
                    links = page.eval_on_selector_all(
                        "a[href*='/jobs/']",
                        "els => els.map(e => e.href).filter(h => h.includes('careers.lg.com'))"
                    )
                    urls.extend([l for l in links if l not in urls])

                # 검색어 시도
                for kw in SEARCH_KEYWORDS:
                    try:
                        page.goto(f"{BASE_URL}?keyword={kw}", wait_until="networkidle", timeout=20000)
                        page.wait_for_timeout(1500)
                        links = page.eval_on_selector_all(
                            "a[href*='/jobs/']",
                            "els => els.map(e => e.href).filter(h => h.includes('careers.lg.com'))"
                        )
                        for link in links:
                            if link not in urls:
                                urls.append(link)
                    except Exception as e:
                        print(f"[lg] search kw={kw}: {e}")

            except Exception as e:
                print(f"[lg] list error: {e}")
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

                title    = _get_text(page, ["h1", ".job-title", "[class*='title']"]) or page.title()
                body     = _get_text(page, [".job-description", "[class*='description']", "[class*='content']"]) or page.inner_text("body")[:8000]
                location = _get_text(page, [".location", "[class*='location']"])
                emp_type = _get_text(page, ["[class*='type']", "[class*='employment']"])

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
                print(f"[lg] detail error {url}: {e}")
                return None
            finally:
                browser.close()


def _extract_lg_jobs(data: dict, job_ids: list) -> None:
    items = (data.get("jobs") or data.get("list") or
             data.get("data", {}).get("jobs", []) or [])
    for item in items:
        jid = item.get("id") or item.get("jobId") or item.get("requisitionId")
        if jid and jid not in job_ids:
            job_ids.append(str(jid))


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
