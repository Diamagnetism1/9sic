"""
pipeline/change_detector.py — Canonicalization, dedup, and change detection.
Canonical ID = sha256(company_name_normalized + job_title_normalized)[:16]
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Optional


def make_canonical_id(company_name: str, job_title: str, location: str = "") -> str:
    """Stable ID based on normalized company + title. Location optional for multi-location roles."""
    key = _normalize_key(company_name) + "|" + _normalize_key(job_title)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def build_canonical_record(normalized: dict, now: str = None) -> dict:
    """Convert normalized_jobs row → canonical_jobs dict."""
    now = now or _now()
    cid = make_canonical_id(
        normalized.get("company_name", ""),
        normalized.get("job_title", ""),
    )
    return {
        "canonical_id":    cid,
        "company_name":    normalized.get("company_name", ""),
        "job_title":       normalized.get("job_title", ""),
        "location":        normalized.get("location", ""),
        "employment_type": normalized.get("employment_type", ""),
        "domain_tags":     normalized.get("domain_tags", "[]"),
        "role_tags":       normalized.get("role_tags", "[]"),
        "description_text":normalized.get("description_text", ""),
        "source_url":      normalized.get("source_url", ""),
        "source_site":     normalized.get("source_site", ""),
        "first_seen_at":   now,
        "last_seen_at":    now,
        "status":          "active",
        "change_status":   "new",
        "last_changed_at": now,
    }


def detect_change(existing: dict, incoming: dict) -> tuple[str, list]:
    """
    Compare existing canonical record vs incoming data.
    Returns (change_status, changed_fields).
    change_status: 'new' | 'changed' | 'unchanged'
    """
    if existing is None:
        return "new", []

    watch_fields = ["job_title", "description_text", "employment_type", "location", "domain_tags", "role_tags"]
    changed = []

    for field in watch_fields:
        old_val = str(existing.get(field, "")).strip()
        new_val = str(incoming.get(field, "")).strip()
        if field in ("domain_tags", "role_tags"):
            # Normalize JSON arrays before comparing
            try:
                old_val = json.dumps(sorted(json.loads(old_val)))
                new_val = json.dumps(sorted(json.loads(new_val)))
            except Exception:
                pass
        if old_val != new_val:
            changed.append(field)

    return ("changed" if changed else "unchanged"), changed


def build_version_snapshot(normalized: dict, version_num: int, changed_fields: list) -> dict:
    return {
        "canonical_id":  make_canonical_id(
            normalized.get("company_name", ""), normalized.get("job_title", "")
        ),
        "version_num":   version_num,
        "snapshot_json": json.dumps(normalized, ensure_ascii=False),
        "changed_fields":json.dumps(changed_fields, ensure_ascii=False),
    }


# ─── Internal ────────────────────────────────────────────────

def _normalize_key(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s가-힣]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
