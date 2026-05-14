"""
adapters/saramin.py — 사람인 adapter.
robots.txt: only /error path restricted. Job listings are public.
Technique: requests + BeautifulSoup (no JS required).
"""
import time
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .base import BaseAdapter, RawJobRecord, _now

# Keywords that map to the user's target domain
SEARCH_KEYWORDS = [
    "BIM",
    "VDC",
    "Digital Delivery",
    "설계 BIM",
    "BIM 코디네이터",
    "BIM coordinator",
    "facility management BIM",
    "반도체 BIM",
    "데이터센터 BIM",
]

BASE_URL = "https://www.saramin.co.kr"
SEARCH_URL = f"{BASE_URL}/zf_user/search/recruit"


class SaraminAdapter(BaseAdapter):
    site_name = "saramin"
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
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": BASE_URL,
        })

    def fetch_job_list(self, keywords=None, max_pages=3) -> List[str]:
        keywords = keywords or SEARCH_KEYWORDS
        urls: list = []
        seen: set = set()

        for keyword in keywords:
            for page in range(1, max_pages + 1):
                params = {
                    "searchType": "search",
                    "searchword": keyword,
                    "recruitPage": page,
                    "recruitSort": "reg_dt",
                    "recruitPageCount": 40,
                }
                try:
                    resp = self._session.get(SEARCH_URL, params=params, timeout=12)
                    soup = BeautifulSoup(resp.text, "html.parser")

                    # Saramin job listing links
                    anchors = soup.select(
                        "h2.job_tit a, .job_tit a, a.job_tit_link, .list_item .tit_area a"
                    )
                    for a in anchors:
                        href = a.get("href", "")
                        if not href or href in seen:
                            continue
                        full = urljoin(BASE_URL, href)
                        urls.append(full)
                        seen.add(href)

                    # If no results, stop paging this keyword
                    if not anchors:
                        break

                except Exception as e:
                    print(f"[saramin] list error kw={keyword!r} p={page}: {e}")

                time.sleep(self.request_delay)

        print(f"[saramin] {len(urls)} job URLs across {len(keywords)} keywords")
        return urls

    def fetch_job_detail(self, url: str) -> Optional[RawJobRecord]:
        try:
            resp = self._session.get(url, timeout=12)
            soup = BeautifulSoup(resp.text, "html.parser")

            # Title — multiple possible selectors across Saramin page variants
            title = _select_text(soup, [
                "h1.tit_job", ".job_tit h1", "h3.tit", ".recruit_title",
                "h2.title", ".wrap_jd_top h1",
            ])

            # Body / JD
            body = _select_text(soup, [
                ".jd_contents", ".wrap_jd_content", "#job_detail_description",
                ".cont_jd", ".job_detail_cont",
            ], fallback=soup.get_text(separator="\n")[:8000])

            # Location
            location = _select_text(soup, [
                ".work_place", ".loc_name", ".job_info .work",
                ".jv_cont .jv_workPlace",
            ])

            # Employment type
            emp_type = _select_text(soup, [
                ".career_form", ".work_type", ".jv_cont .jv_emptype",
                ".job_info .type",
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
            print(f"[saramin] detail error {url}: {e}")
            return None


def _select_text(soup: BeautifulSoup, selectors: list, fallback: str = "") -> str:
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            return el.get_text(separator="\n", strip=True)
    return fallback
