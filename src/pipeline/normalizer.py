"""
pipeline/normalizer.py — raw RawJobRecord → normalized_jobs schema.
No ML required. Rule-based field extraction + tag inference.
"""
import json
import re
from datetime import datetime, timezone
from typing import Optional


# ─── Domain / Role keyword taxonomy ─────────────────────────

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "semiconductor":   ["semiconductor", "반도체", "fab", "wafer", "cleanroom", "clean room", "클린룸"],
    "data_center":     ["data center", "datacenter", "데이터센터", "hyperscale"],
    "high_tech":       ["high-tech", "hi-tech", "하이테크", "advanced manufacturing"],
    "manufacturing":   ["production facility", "생산시설", "공장", "manufacturing plant", "factory"],
    "mission_critical":["mission critical", "life science", "pharma", "바이오"],
    "infrastructure":  ["airport", "logistics", "industrial complex", "산업단지"],
    "general_construction": ["construction", "건설", "building", "인프라", "infrastructure"],
}

ROLE_KEYWORDS: dict[str, list[str]] = {
    "BIM_governance":   ["BIM governance", "BIM manager", "BIM management"],
    "VDC":              ["VDC", "virtual design", "virtual construction"],
    "design_coord":     ["design coordination", "design coordinator", "설계 조율", "설계조율"],
    "digital_delivery": ["digital delivery", "digital twin", "디지털 딜리버리"],
    "BIM_QC":           ["BIM QC", "BIM quality", "data quality", "데이터 품질"],
    "handover":         ["handover", "data handover", "준공", "as-built", "핸드오버"],
    "pre_con":          ["pre-construction", "preconstruction", "pre-con", "constructability"],
    "PIM":              ["project information management", "PIM", "CDE"],
    "MEP_BIM":          ["MEP BIM", "MEP coordination", "MEP coordinator"],
    "BIM_coord":        ["BIM coordinator", "BIM lead", "lead BIM", "senior BIM"],
    "BIM_specialist":   ["BIM specialist", "BIM engineer", "BIM consultant"],
    "BIM_modeler":      ["BIM modeler", "BIM 모델러", "모델 작성"],
}

EMPLOYMENT_MAP: dict[str, list[str]] = {
    "fulltime":  ["정규직", "full-time", "fulltime", "permanent", "상용직"],
    "contract":  ["계약직", "contract", "기간제", "fixed-term"],
    "dispatch":  ["파견", "도급", "dispatch", "staffing agency", "용역"],
    "internship":["인턴", "intern", "아르바이트"],
}

SENIORITY_MAP: dict[str, list[str]] = {
    "lead":   ["lead", "manager", "head", "principal", "director", "책임", "팀장", "리드"],
    "senior": ["senior", "시니어", "선임", "수석"],
    "mid":    ["mid", "중급", "경력 3", "경력 5"],
    "junior": ["junior", "주니어", "신입", "초급"],
}


def normalize(raw: dict) -> dict:
    """
    Convert a raw_job_records row → normalized_jobs dict.
    raw must have: id, source_site, job_url, raw_title, raw_body, raw_location, raw_employment_type
    """
    text = (
        (raw.get("raw_title") or "")
        + " "
        + (raw.get("raw_body") or "")
        + " "
        + (raw.get("raw_employment_type") or "")
    ).lower()

    company_name   = _extract_company(raw)
    job_title      = _clean_title(raw.get("raw_title") or "")
    domain_tags    = _match_tags(text, DOMAIN_KEYWORDS)
    role_tags      = _match_tags(text, ROLE_KEYWORDS)
    emp_type       = _match_first(text, EMPLOYMENT_MAP) or "unknown"
    seniority      = _match_first(text, SENIORITY_MAP) or "unknown"
    posting_date   = _extract_date(raw.get("raw_body") or "")
    closing_date   = _extract_closing_date(raw.get("raw_body") or "")

    return {
        "raw_id":             raw["id"],
        "source_site":        raw["source_site"],
        "source_url":         raw["job_url"],
        "company_name":       company_name,
        "job_title":          job_title,
        "team_or_department": "",          # hard to extract reliably; left blank
        "location":           (raw.get("raw_location") or "").strip(),
        "employment_type":    emp_type,
        "seniority":          seniority,
        "domain_tags":        json.dumps(domain_tags, ensure_ascii=False),
        "role_tags":          json.dumps(role_tags, ensure_ascii=False),
        "posting_date":       posting_date,
        "closing_date":       closing_date,
        "description_text":   (raw.get("raw_body") or "")[:10000],
    }


# ─── Field extractors ────────────────────────────────────────

def _extract_company(raw: dict) -> str:
    """
    Try to extract company name from raw_title or source_site name.
    Many job boards include company name in the title: "BIM Manager - 삼성물산"
    """
    title = raw.get("raw_title") or ""
    # Heuristic: "Role - Company" or "Role | Company" or "Company : Role"
    for sep in [" - ", " | ", " : ", " / "]:
        if sep in title:
            parts = title.split(sep, 1)
            # Guess: longer part is the role, shorter is company (or vice versa)
            return parts[-1].strip()

    # Fallback: use source_site label
    site_company_map = {
        "samsung_careers": "삼성전자",
        "skhynix_careers": "SK하이닉스",
        "kia_careers":     "기아",
        "lg_careers":      "LG",
    }
    return site_company_map.get(raw.get("source_site", ""), "")


def _clean_title(title: str) -> str:
    # Strip trailing metadata like "[D+20]", "(채용공고)", etc.
    title = re.sub(r"\[.*?\]", "", title)
    title = re.sub(r"\(.*?\)", "", title)
    return title.strip()


def _match_tags(text: str, taxonomy: dict) -> list:
    matched = []
    for tag, keywords in taxonomy.items():
        for kw in keywords:
            if kw.lower() in text:
                matched.append(tag)
                break
    return matched


def _match_first(text: str, mapping: dict) -> Optional[str]:
    for category, keywords in mapping.items():
        for kw in keywords:
            if kw.lower() in text:
                return category
    return None


def _extract_date(text: str) -> str:
    # Match YYYY.MM.DD, YYYY-MM-DD, YYYY/MM/DD
    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
    if m:
        try:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        except Exception:
            pass
    return ""


def _extract_closing_date(text: str) -> str:
    # Look for "마감" or "closing" or "deadline" near a date
    lower = text.lower()
    patterns = ["마감", "closing date", "deadline", "접수 기간", "모집 기간"]
    for pat in patterns:
        idx = lower.find(pat)
        if idx != -1:
            snippet = text[idx:idx + 60]
            m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", snippet)
            if m:
                try:
                    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                except Exception:
                    pass
    return ""
