"""
adapters/samsung_cnt.py — 삼성물산 건설부문 adapter.
채용 포털: samsungcareers.com (subsId=B12 = 삼성물산 건설)
robots.txt: secc.co.kr Allow: /
Technique: Playwright (JS 렌더링 필요)
"""
import time
from typing import List, Optional
from .base import BaseAdapter, RawJobRecord, _now

CAREERS_URL  = "https://www.samsungcareers.com"
LIST_URL     = f"{CAREERS_URL}/hr/"
DETAIL_BASE  = f"{CAREERS_URL}/hr"
SUBID        = "B12"   # 삼성물산 건설부문 코드

SEARCH_KEYWORDS = ["BIM", "VDC", "facility", "설비", "스마트건설", "디지털"]


class SamsungCNTAdapter(BaseAdapter):
    site_name = "samsung_cnt"
    requires_playwright = True
    request_delay = 3.0

    def fetch_job_list(self, **kwargs) -> List[str]:
        from playwright.sync_api import sync_playwright

        urls: list = []

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

            for kw in SEARCH_KEYWORDS:
                try:
                    target = f"{LIST_URL}?strKey={kw}&strTxt={kw}"
                    page.goto(target, wait_until="networkidle", timeout=25000)
                    page.wait_for_timeout(3000)

                    # 공고 카드 링크 추출
                    links = page.eval_on_selector_all(
                        "a[href*='/hr/'], .job a, .col3List a, li.item a",
                        "els => els.map(e => e.href)"
                        ".filter(h => h.includes('samsungcareers.com/hr/'))"
                        ".filter(h => !h.endsWith('/hr/'))"
                    )
                    for link in links:
                        if link not in urls:
                            urls.append(link)

                    # onclick 방식 공고 ID 추출 (일부 삼성 사이트 패턴)
                    job_ids = page.eval_on_selector_all(
                        "[onclick*='detail'], [data-seq], [data-key]",
                        """els => els.map(e => {
                            const seq = e.getAttribute('data-seq') || e.getAttribute('data-key');
                            const onclick = e.getAttribute('onclick') || '';
                            const m = onclick.match(/['\"]([A-Z0-9]+)['"]/);
                            return seq || (m ? m[1] : null);
                        }).filter(Boolean)"""
                    )
                    for jid in job_ids:
                        url = f"{DETAIL_BASE}/detail?strKey={jid}"
                        if url not in urls:
                            urls.append(url)

                except Exception as e:
                    print(f"[samsung_cnt] list error kw={kw!r}: {e}")

                time.sleep(self.request_delay)

            # 키워드 없이 전체 목록도 시도
            try:
                page.goto(LIST_URL, wait_until="networkidle", timeout=25000)
                page.wait_for_timeout(3000)
                links = page.eval_on_selector_all(
                    "a[href*='/hr/']",
                    "els => els.map(e => e.href)"
                    ".filter(h => h.includes('samsungcareers.com/hr/'))"
                    ".filter(h => !h.endsWith('/hr/'))"
                )
                for link in links:
                    if link not in urls:
                        urls.append(link)
            except Exception as e:
                print(f"[samsung_cnt] full list error: {e}")

            browser.close()

        print(f"[samsung_cnt] {len(urls)} job URLs collected")
        return list(dict.fromkeys(urls))

    def fetch_job_detail(self, url: str) -> Optional[RawJobRecord]:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_context().new_page()
            try:
                page.goto(url, wait_until="networkidle", timeout=25000)
                page.wait_for_timeout(2000)

                title = _get_text(page, [
                    "h2.title", ".job-title", "#job-title",
                    "h1", ".tit", "[class*='title']",
                ]) or page.title()

                body = _get_text(page, [
                    ".job-desc", ".description", ".detail-content",
                    "[class*='desc']", "[class*='content']", ".cont",
                ]) or page.inner_text("body")[:8000]

                location = _get_text(page, [
                    ".location", "[class*='location']", ".workplace",
                ])
                emp_type = _get_text(page, [
                    ".emp-type", "[class*='type']", ".career",
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
                print(f"[samsung_cnt] detail error {url}: {e}")
                return None
            finally:
                browser.close()


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
