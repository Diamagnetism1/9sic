"""
db/database.py — SQLite access helpers.
All SQL lives here; other modules call these functions.
"""
import sqlite3
import json
import os
from pathlib import Path
from typing import Optional

DB_PATH = os.environ.get("JOB_INTEL_DB", "data/job_intel.db")
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding='utf-8'))
    _seed_sources()


def _seed_sources() -> None:
    rows = [
        ("saramin",          "https://www.saramin.co.kr",   "SaraminAdapter",  0, 1, "allowed",  "Server-rendered. requests/BS4 OK."),
        ("jobkorea",         "https://www.jobkorea.co.kr",  "JobKoreaAdapter", 0, 1, "partial",  "AI crawlers: only /recruit/joblist and /Recruit/GI_Read allowed per robots.txt."),
        ("samsung_careers",  "https://recruit.samsung.com", "SamsungAdapter",  1, 1, "allowed",  "Empty robots.txt. SPA — Playwright required."),
        ("skhynix_careers",  "https://careers.skhynix.com", "SKHynixAdapter",  1, 1, "allowed",  "Empty robots.txt. SPA — Playwright required."),
        ("kia_careers",      "https://careers.kia.com",     "KiaAdapter",      1, 1, "allowed",  "Empty robots.txt. SPA — Playwright required."),
        ("lg_careers",       "https://careers.lg.com",      "LGAdapter",       1, 1, "allowed",  "React SPA. No robots.txt. Playwright required."),
        ("linkedin",         "https://www.linkedin.com",    "ManualOnly",      0, 0, "prohibited","Explicitly prohibits automated access. Manual add only."),
        ("wanted",           "https://www.wanted.co.kr",    "ManualOnly",      0, 0, "prohibited","CloudFront blocks automated requests."),
        ("jobplanet",        "https://www.jobplanet.co.kr", "ManualOnly",      0, 0, "prohibited","Cloudflare challenge. Automated access blocked."),
        ("remember",         "https://www.rememberapp.co.kr","ManualOnly",     0, 0, "partial",  "Robots limited. Career page structure unclear; manual preferred."),
    ]
    with get_conn() as conn:
        conn.executemany(
            """INSERT OR IGNORE INTO source_sites
               (name, base_url, adapter_class, requires_playwright, enabled, robots_policy, notes)
               VALUES (?,?,?,?,?,?,?)""",
            rows,
        )


# ─── Raw ────────────────────────────────────────────────────

def insert_raw(record: dict) -> Optional[int]:
    """Insert raw record; skip if same URL+hash already exists. Returns rowid or None."""
    with get_conn() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO raw_job_records
                   (source_site, job_url, raw_title, raw_body, raw_location,
                    raw_employment_type, fetched_html, fetched_at, content_hash, http_status)
                   VALUES (:source_site,:job_url,:raw_title,:raw_body,:raw_location,
                           :raw_employment_type,:fetched_html,:fetched_at,:content_hash,:http_status)""",
                record,
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None  # duplicate


# ─── Normalized ─────────────────────────────────────────────

def upsert_normalized(record: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO normalized_jobs
               (raw_id, source_site, source_url, company_name, job_title, team_or_department,
                location, employment_type, seniority, domain_tags, role_tags,
                posting_date, closing_date, description_text)
               VALUES (:raw_id,:source_site,:source_url,:company_name,:job_title,:team_or_department,
                       :location,:employment_type,:seniority,:domain_tags,:role_tags,
                       :posting_date,:closing_date,:description_text)""",
            record,
        )
        return cur.lastrowid


# ─── Canonical ──────────────────────────────────────────────

def get_canonical(canonical_id: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM canonical_jobs WHERE canonical_id = ?", (canonical_id,)
        ).fetchone()
        return dict(row) if row else None


def upsert_canonical(record: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO canonical_jobs
               (canonical_id, company_name, job_title, location, employment_type,
                domain_tags, role_tags, description_text, source_url, source_site,
                first_seen_at, last_seen_at, status, change_status, last_changed_at)
               VALUES (:canonical_id,:company_name,:job_title,:location,:employment_type,
                       :domain_tags,:role_tags,:description_text,:source_url,:source_site,
                       :first_seen_at,:last_seen_at,:status,:change_status,:last_changed_at)
               ON CONFLICT(canonical_id) DO UPDATE SET
                 last_seen_at    = excluded.last_seen_at,
                 status          = excluded.status,
                 change_status   = excluded.change_status,
                 last_changed_at = excluded.last_changed_at,
                 description_text = excluded.description_text,
                 domain_tags     = excluded.domain_tags,
                 role_tags       = excluded.role_tags""",
            record,
        )


def mark_closed_unseen(active_canonical_ids: list, cutoff_days: int = 3) -> list:
    """Mark jobs not seen in last cutoff_days as closed."""
    from datetime import datetime, timedelta, timezone
    threshold = (datetime.now(timezone.utc) - timedelta(days=cutoff_days)).isoformat()
    with get_conn() as conn:
        if active_canonical_ids:
            placeholders = ",".join("?" * len(active_canonical_ids))
            conn.execute(
                f"""UPDATE canonical_jobs SET status='closed', change_status='closed'
                    WHERE canonical_id NOT IN ({placeholders})
                    AND status='active'
                    AND last_seen_at < ?""",
                active_canonical_ids + [threshold],
            )
        rows = conn.execute(
            "SELECT canonical_id FROM canonical_jobs WHERE status='closed'"
        ).fetchall()
    return [r["canonical_id"] for r in rows]


# ─── Scores ─────────────────────────────────────────────────

def upsert_score(record: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO job_scores
               (canonical_id, total_score, domain_score, role_level_score, ownership_score,
                employment_type_score, company_tier_score, penalty_score, score_breakdown)
               VALUES (:canonical_id,:total_score,:domain_score,:role_level_score,:ownership_score,
                       :employment_type_score,:company_tier_score,:penalty_score,:score_breakdown)
               ON CONFLICT(canonical_id) DO UPDATE SET
                 total_score           = excluded.total_score,
                 domain_score          = excluded.domain_score,
                 role_level_score      = excluded.role_level_score,
                 ownership_score       = excluded.ownership_score,
                 employment_type_score = excluded.employment_type_score,
                 company_tier_score    = excluded.company_tier_score,
                 penalty_score         = excluded.penalty_score,
                 score_breakdown       = excluded.score_breakdown,
                 scored_at             = datetime('now')""",
            record,
        )


# ─── LLM ────────────────────────────────────────────────────

def upsert_llm_analysis(record: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO llm_analyses
               (canonical_id, fit_reason, risk_summary, role_interpretation, match_keywords, model_used)
               VALUES (:canonical_id,:fit_reason,:risk_summary,:role_interpretation,:match_keywords,:model_used)
               ON CONFLICT(canonical_id) DO UPDATE SET
                 fit_reason          = excluded.fit_reason,
                 risk_summary        = excluded.risk_summary,
                 role_interpretation = excluded.role_interpretation,
                 match_keywords      = excluded.match_keywords,
                 analyzed_at         = datetime('now')""",
            record,
        )


# ─── User state ─────────────────────────────────────────────

def set_user_state(canonical_id: str, status: str, memo: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO user_job_states (canonical_id, status, memo)
               VALUES (?, ?, ?)
               ON CONFLICT(canonical_id) DO UPDATE SET
                 status     = excluded.status,
                 memo       = excluded.memo,
                 updated_at = datetime('now')""",
            (canonical_id, status, memo),
        )


# ─── Dashboard queries ───────────────────────────────────────

def get_dashboard_jobs(
    status_filter: list = None,
    company_filter: str = None,
    change_filter: list = None,
    min_score: float = 0,
    watchlist_only: bool = False,
) -> list:
    query = """
        SELECT
            c.canonical_id, c.company_name, c.job_title, c.location,
            c.employment_type, c.domain_tags, c.role_tags,
            c.status, c.change_status, c.first_seen_at, c.last_seen_at,
            c.source_url,
            COALESCE(s.total_score, 0) as total_score,
            s.score_breakdown,
            COALESCE(u.status, 'new') as user_status,
            u.memo,
            l.fit_reason, l.risk_summary, l.role_interpretation
        FROM canonical_jobs c
        LEFT JOIN job_scores s       ON c.canonical_id = s.canonical_id
        LEFT JOIN user_job_states u  ON c.canonical_id = u.canonical_id
        LEFT JOIN llm_analyses l     ON c.canonical_id = l.canonical_id
        WHERE c.status != 'closed'
          AND COALESCE(s.total_score, 0) >= ?
    """
    params = [min_score]

    if status_filter:
        placeholders = ",".join("?" * len(status_filter))
        query += f" AND COALESCE(u.status, 'new') IN ({placeholders})"
        params.extend(status_filter)

    if company_filter:
        query += " AND c.company_name LIKE ?"
        params.append(f"%{company_filter}%")

    if change_filter:
        placeholders = ",".join("?" * len(change_filter))
        query += f" AND c.change_status IN ({placeholders})"
        params.extend(change_filter)

    if watchlist_only:
        query += " AND c.company_name IN (SELECT company_name FROM watchlist_companies)"

    query += " ORDER BY total_score DESC, c.last_seen_at DESC"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def log_pipeline_run(record: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO pipeline_runs
               (run_at, sites_attempted, jobs_fetched, jobs_new, jobs_changed,
                jobs_closed, errors, duration_seconds, status)
               VALUES (:run_at,:sites_attempted,:jobs_fetched,:jobs_new,:jobs_changed,
                       :jobs_closed,:errors,:duration_seconds,:status)""",
            record,
        )
