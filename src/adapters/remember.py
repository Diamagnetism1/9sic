"""
adapters/remember.py — 리멤버 career.rememberapp.co.kr adapter.
robots.txt: Allow: /job/ (명시적 허용)
Sitemap: sitemap-jobs.xml 제공
Technique: Playwright (Next.js SPA) + API 인터셉트
"""
import json
import time
from typing import List, Optional
from urllib.parse import quote

from .base import BaseAdapter, RawJobRecord, _now

BASE_URL = "https://career.rememberapp.co.kr"

# robots.txt에서 허용된 검색 경로: /job/postings
SEARCH_KEYWORDS = [
    "BIM", "VDC", "반도체 시설", "데이터센터 설계",
    "클린룸", "MEP", "설계관리", "Digital Delivery",
]


class RememberAdapter(BaseAdapter):
    site_name = "remember"
    requires_playwright = True
    request_delay = 2.5

    def fetch_job_list(self, **kwargs) -> List[str]:
        from playwright.sync_api import sync_playwright

        urls: list = []
        api_jobs: list = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                extra_http_headers={
                    "Accept-Language": "ko-KR,ko;q=0.9",
                    "Referer": BASE_URL,
                },
            )
            page = ctx.new_page()

            # API 응답 인터셉트
            def on_response(resp):
                url = resp.url
                if resp.status == 200 and (
                    "job/postings" in url or
                    "jobs" in url and "career.rememberapp" in url
                ):
                    try:
                        data = resp.json()
                        _extract_jobs(data, api_jobs)
                    except Exception:
                        pass

            page.on("response", on_response)

            for keyword in SEARCH_KEYWORDS:
                try:
                    search_param = quote(json.dumps({"keyword": keyword}))
                    target_url = f"{BASE_URL}/job/postings?search={search_param}"

                    page.goto(target_url, wait_until="networkidle", timeout=25000)
                    page.wait_for_timeout(2500)

                    # API 인터셉트로 수집된 job ID → URL 변환
                    for job in api_jobs:
                        job_id = job.get("id") or job.get("jobId") or job.get("postingId")
                        if job_id:
                            url = f"{BASE_URL}/job/postings/{job_id}"
                            if url not in urls:
                                urls.append(url)

                    # DOM fallback: 직접 링크 추출
                    dom_links = page.eval_on_selector_all(
                        "a[href*='/job/postings/']",
                        "els => els.map(e => e.href)"
                        ".filter(h => h.includes('career.rememberapp.co.kr/job/postings/'))"
                        ".filter(h => !h.includes('search='))"
                    )
                    for link in dom_links:
                        if link not in urls:
                            urls.append(link)

                    api_jobs.clear()

                except Exception as e:
                    print(f"[remember] list error kw={keyword!r}: {e}")

                time.sleep(self.request_delay)

            browser.close()

        print(f"[remember] {len(urls)} job URLs collected")
        return list(dict.fromkeys(urls))

    def fetch_job_detail(self, url: str) -> Optional[RawJobRecord]:
        from playwright.sync_api import sync_playwright

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

            api_detail: dict = {}

            def on_response(resp):
                if resp.status == 200 and "job/postings/" in resp.url and "career.rememberapp" in resp.url:
                    try:
                        data = resp.json()
                        if isinstance(data, dict) and ("title" in data or "jobTitle" in data):
                            api_detail.update(data)
                    except Exception:
                        pass

            page.on("response", on_response)

            try:
                page.goto(url, wait_until="networkidle", timeout=25000)
                page.wait_for_timeout(2000)

                # API 응답에서 파싱 시도
                if api_detail:
                    title    = api_detail.get("title") or api_detail.get("jobTitle") or ""
                    body     = api_detail.get("description") or api_detail.get("content") or ""
                    location = api_detail.get("location") or api_detail.get("workLocation") or ""
                    emp_type = api_detail.get("employmentType") or api_detail.get("jobType") or ""
                else:
                    # DOM fallback
                    title = _get_text(page, [
                        "h1", ".job-title", "[class*='title']",
                        "[class*='Title']", "h2",
                    ]) or page.title()

                    body = _get_text(page, [
                        "[class*='description']", "[class*='Description']",
                        "[class*='content']", "[class*='Content']",
                        "[class*='detail']", "[class*='jd']",
                    ]) or page.inner_text("body")[:8000]

                    location = _get_text(page, [
                        "[class*='location']", "[class*='Location']",
                        "[class*='workplace']",
                    ])
                    emp_type = _get_text(page, [
                        "[class*='employment']", "[class*='type']",
                        "[class*='contract']",
                    ])

                return RawJobRecord(
                    source_site=self.site_name,
                    job_url=url,
                    raw_title=title,
                    raw_body=str(body)[:8000],
                    raw_location=location,
                    raw_employment_type=emp_type,
                    fetched_html=page.content()[:50000],
                    fetched_at=_now(),
                )

            except Exception as e:
                print(f"[remember] detail error {url}: {e}")
                return None
            finally:
                browser.close()


def _extract_jobs(data, job_list: list) -> None:
    """API 응답에서 공고 목록 추출 (다양한 응답 구조 대응)"""
    items = (
        data.get("postings") or
        data.get("jobs") or
        data.get("list") or
        data.get("data", {}).get("postings") or
        data.get("data", {}).get("jobs") or
        (data.get("data") if isinstance(data.get("data"), list) else None) or
        []
    )
    for item in items:
        if isinstance(item, dict):
            job_list.append(item)


def _get_text(page, selectors: list) -> str:
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if len(text) > 5:
                    return text
        except Exception:
            pass
    return ""
