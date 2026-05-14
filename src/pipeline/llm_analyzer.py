"""
pipeline/llm_analyzer.py — Optional LLM-based job analysis.
Uses Anthropic Claude API. Gracefully skips if API key not set.
Only runs on new/changed jobs with score >= threshold.
"""
import json
import os
from typing import Optional

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
LLM_SCORE_THRESHOLD = float(os.environ.get("LLM_SCORE_THRESHOLD", "30"))
PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """\
You are a career advisor specializing in BIM, VDC, and high-tech facility construction.
You analyze job postings for a senior BIM/VDC professional targeting:
- High-tech facilities: semiconductor fabs, data centers, cleanrooms
- Roles: MEP BIM, VDC, BIM Governance, Design Coordination, Digital Delivery, BIM QC, Handover Data
- Owner-side or owner-adjacent positions
- Full-time permanent roles with genuine role ownership

Respond ONLY with valid JSON matching this schema. No markdown, no preamble.
"""

RESPONSE_SCHEMA = {
    "fit_reason": "string — 2-3 sentences on why this role fits the profile",
    "risk_summary": "string — 1-2 sentences on risks or red flags (empty string if none)",
    "role_interpretation": "string — concise interpretation of actual day-to-day responsibilities",
    "match_keywords": ["list", "of", "matched", "career-relevant", "keywords"],
}

USER_PROMPT_TPL = """\
Analyze this job posting for career fit:

Company: {company_name}
Title: {job_title}
Location: {location}
Employment Type: {employment_type}
Domain Tags: {domain_tags}
Role Tags: {role_tags}

Job Description (truncated to 3000 chars):
{description_text}

Respond with JSON only, matching this schema:
{schema}
"""


def analyze_job(normalized: dict) -> Optional[dict]:
    """
    Run LLM analysis on a normalized job dict.
    Returns dict matching llm_analyses table, or None if skipped/failed.
    """
    if not ANTHROPIC_API_KEY:
        return None

    prompt = USER_PROMPT_TPL.format(
        company_name=normalized.get("company_name", ""),
        job_title=normalized.get("job_title", ""),
        location=normalized.get("location", ""),
        employment_type=normalized.get("employment_type", ""),
        domain_tags=normalized.get("domain_tags", "[]"),
        role_tags=normalized.get("role_tags", "[]"),
        description_text=(normalized.get("description_text") or "")[:3000],
        schema=json.dumps(RESPONSE_SCHEMA, indent=2, ensure_ascii=False),
    )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",   # cheapest for batch jobs
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = msg.content[0].text.strip()

        # Strip markdown fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]

        parsed = json.loads(raw_text)

        return {
            "canonical_id":       normalized["canonical_id"],
            "fit_reason":         parsed.get("fit_reason", ""),
            "risk_summary":       parsed.get("risk_summary", ""),
            "role_interpretation":parsed.get("role_interpretation", ""),
            "match_keywords":     json.dumps(parsed.get("match_keywords", []), ensure_ascii=False),
            "model_used":         "claude-haiku-4-5-20251001",
            "prompt_version":     PROMPT_VERSION,
        }

    except Exception as e:
        print(f"[llm] analysis failed for {normalized.get('canonical_id')}: {e}")
        return None


def should_analyze(job: dict, score: float) -> bool:
    """Only analyze jobs above threshold and that are new or changed."""
    if score < LLM_SCORE_THRESHOLD:
        return False
    if job.get("change_status") in ("new", "changed"):
        return True
    return False
