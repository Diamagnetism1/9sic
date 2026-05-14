"""
pipeline/scorer.py — Rule-based scoring engine.
Reads config/scoring_rules.yaml and scores normalized job records.
LLM is not required for this module to work.
"""
import json
import re
from pathlib import Path
from typing import Any

import yaml

RULES_PATH = Path(__file__).parent.parent.parent / "config" / "scoring_rules.yaml"

_rules: dict = {}


def _load_rules() -> dict:
    global _rules
    if not _rules:
        _rules = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))
    return _rules


def score_job(normalized: dict) -> dict:
    """
    Score a normalized job record.
    Returns a dict matching the job_scores table schema.
    """
    rules = _load_rules()
    text = _build_search_text(normalized)

    domain_score        = _apply_keyword_rules(text, rules.get("domain_rules", []))
    role_level_score    = _apply_keyword_rules(text, rules.get("role_rules", []))
    ownership_score     = _apply_keyword_rules(text, rules.get("ownership_rules", []))
    employment_score    = _apply_keyword_rules(text, rules.get("employment_type_rules", []))
    company_score       = _apply_company_rules(normalized.get("company_name", ""), rules.get("company_rules", []))
    penalty_score       = _apply_keyword_rules(text, rules.get("penalty_rules", []))

    total = (
        domain_score
        + role_level_score
        + ownership_score
        + employment_score
        + company_score
        + penalty_score   # already negative
    )

    breakdown = _build_breakdown(
        text, normalized.get("company_name", ""), rules
    )

    return {
        "canonical_id":          normalized["canonical_id"],
        "total_score":           round(total, 2),
        "domain_score":          round(domain_score, 2),
        "role_level_score":      round(role_level_score, 2),
        "ownership_score":       round(ownership_score, 2),
        "employment_type_score": round(employment_score, 2),
        "company_tier_score":    round(company_score, 2),
        "penalty_score":         round(penalty_score, 2),
        "score_breakdown":       json.dumps(breakdown, ensure_ascii=False),
    }


def get_score_tier(total_score: float) -> str:
    rules = _load_rules()
    thresholds = rules.get("thresholds", {})
    if total_score >= thresholds.get("hot", 70):
        return "💎 HOT"
    if total_score >= thresholds.get("good", 45):
        return "✅ GOOD"
    if total_score >= thresholds.get("maybe", 20):
        return "🔍 MAYBE"
    return "⬇️ SKIP"


# ─── Internal helpers ────────────────────────────────────────

def _build_search_text(normalized: dict) -> str:
    """Combine all text fields into one searchable string (lowercased)."""
    parts = [
        normalized.get("job_title", ""),
        normalized.get("team_or_department", ""),
        normalized.get("description_text", ""),
        normalized.get("company_name", ""),
        " ".join(json.loads(normalized.get("domain_tags", "[]"))),
        " ".join(json.loads(normalized.get("role_tags", "[]"))),
        normalized.get("employment_type", ""),
        normalized.get("location", ""),
    ]
    return " ".join(str(p) for p in parts if p).lower()


def _apply_keyword_rules(text: str, rule_list: list) -> float:
    total = 0.0
    for rule in rule_list:
        for kw in rule.get("keywords", []):
            if kw.lower() in text:
                total += rule["score"]
                break  # one match per rule is enough
    return total


def _apply_company_rules(company_name: str, rule_list: list) -> float:
    company_lower = company_name.lower()
    for rule in rule_list:
        for name in rule.get("companies", []):
            if name.lower() in company_lower or company_lower in name.lower():
                return float(rule["score"])
    return 0.0


def _build_breakdown(text: str, company_name: str, rules: dict) -> list:
    """Return list of {label, score, matched_keyword} for matched rules."""
    result = []

    for group_key in ["domain_rules", "role_rules", "ownership_rules",
                       "employment_type_rules", "penalty_rules"]:
        for rule in rules.get(group_key, []):
            for kw in rule.get("keywords", []):
                if kw.lower() in text:
                    result.append({
                        "label":   rule["label"],
                        "score":   rule["score"],
                        "matched": kw,
                    })
                    break

    for rule in rules.get("company_rules", []):
        for name in rule.get("companies", []):
            if name.lower() in company_name.lower():
                result.append({
                    "label":   rule["label"],
                    "score":   rule["score"],
                    "matched": name,
                })
                break

    return result
