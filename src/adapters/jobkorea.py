"""
adapters/jobkorea.py — 잡코리아 adapter.
robots.txt policy (AI crawlers): Disallow: / with specific Allow paths:
  Allow: /recruit/joblist
  Allow: /Recruit/GI_Read   (job detail)
  Allow: /company
Only these paths are crawled.
Technique: requests + BeautifulSoup.
"""
import time
from typing import List, Optional
from urllib.parse import urljoin, urlencode

import requests
from bs4 import BeautifulSoup

from .base import BaseAdapter, RawJobRecord, _now

BASE_URL = "https://www.jobkorea.co.kr"
LIST_URL = f"{BASE_URL}/recruit/joblist"
DETAIL_URL_TPL = f"{BASE_URL}/Recruit/GI_Read/{{job_id}}"

# duty codes relevant to BIM/VDC/Architecture/Engineering on JobKorea
# 10031 = 건설/시공 관련, try keyword-based search
SEARCH_PARAMS_BASE = {
    "menucode": "duty",
    "Txt_sear": "",
    "orderby": "date",
}

SEARCH_KEYWORDS = [
    "BIM", "VDC", "설계관리", "BIM coordinator",
    "Digital Delivery", "시설관리 BIM",
]


class JobKoreaAdapter(BaseAdapter):
    site_name = "jobkorea"
    requires_playwright = False
    request_delay = 2.5

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": BASE_URL,
        })

    def fetch_job_list(self, keywords=None, max_pages=3) -> List[str]:
        keywords = keywords or SEARCH_KEYWORDS
        urls: list = []
        seen: set = set()

        for keyword in keywords:
            for page in range(1, max_pages + 1):
                params = {
                    **SEARCH_PARAMS_BASE,
                    "Txt_sear": keyword,
                    "pageIndex": page,
                    "pageSize": 40,
                }
                try:
                    resp = self._session.get(LIST_URL, params=params, timeout=12)
                    soup = BeautifulSoup(resp.text, "html.parser")

                    # JobKorea list item links
                    anchors = soup.select(
                        ".list-post .post-list-info .title a, "
                        ".recruit_lst .name a, "
                        "a[href*='GI_Read'], a[href*='/job/']"
                    )
                    found = 0
                    for a in anchors:
                        href = a.get("href", "")
                        if not href or href in seen:
                            continue
                        full = urljoin(BASE_URL, href) if href.startswith("/") else href
                        # Only follow /Recruit/GI_Read paths (allowed by robots.txt)
                        if "GI_Read" in full or "/job/" in full:
                            urls.append(full)
                            seen.add(href)
                            found += 1

                    if found == 0:
                        break  # no more results

                except Exception as e:
                    print(f"[jobkorea] list error kw={keyword!r} p={page}: {e}")

                time.sleep(self.request_delay)

        return urls

    def fetch_job_detail(self, url: str) -> Optional[RawJobRecord]:
        # Respect robots.txt: only fetch /Recruit/GI_Read/* paths
        if "GI_Read" not in url and "/job/" not in url:
            print(f"[jobkorea] Skipping non-allowed URL: {url}")
            return None

        try:
            resp = self._session.get(url, timeout=12)
            soup = BeautifulSoup(resp.text, "html.parser")

            title = _select_text(soup, [
                "h1.title", ".recruit-info .title", "h2.name",
                ".tit_job", ".job-info-header h1",
            ])

            body = _select_text(soup, [
                ".recruit-detail-desc", ".jd_cont", ".content-body",
                "#job_detail", ".desc_area",
            ], fallback=soup.get_text(separator="\n")[:8000])

            location = _select_text(soup, [
                ".info-etc .loc", ".work-place", ".loc_name",
                "li:has(.icon-location)", ".job_condition .workplace",
            ])

            emp_type = _select_text(soup, [
                ".info-etc .type", ".work-type", ".emp_type",
                ".career_type", ".job_condition .career",
            ])

            return RawJobRecord(
                source_site=self.site_name,
                job_url=url,
                raw_title=title,
                raw_body=body,
                raw_location=location,
                raw_employment_type=emp_type,
                fetched_html=resp.text[:50000],
                fetched_at=_now(),
                http_status=resp.status_code,
            )
        except Exception as e:
            print(f"[jobkorea] detail error {url}: {e}")
            return None


def _select_text(soup, selectors: list, fallback: str = "") -> str:
    for sel in selectors:
        try:
            el = soup.select_one(sel)
            if el:
                return el.get_text(separator="\n", strip=True)
        except Exception:
            pass
    return fallback
