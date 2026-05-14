-- ============================================================
-- Job Intel Dashboard — SQLite Schema
-- Layers: raw → normalized → canonical → scored → user_state
-- ============================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ─── 1. Source sites registry ───────────────────────────────
CREATE TABLE IF NOT EXISTS source_sites (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL UNIQUE,
    base_url        TEXT    NOT NULL,
    adapter_class   TEXT    NOT NULL,
    requires_playwright INTEGER DEFAULT 0,
    enabled         INTEGER DEFAULT 1,
    robots_policy   TEXT,      -- 'allowed' | 'partial' | 'prohibited'
    notes           TEXT,
    created_at      TEXT    DEFAULT (datetime('now'))
);

-- ─── 2. Raw job records (original scraped data) ─────────────
CREATE TABLE IF NOT EXISTS raw_job_records (
    id                  INTEGER PRIMARY KEY,
    source_site         TEXT    NOT NULL,
    job_url             TEXT    NOT NULL,
    raw_title           TEXT,
    raw_body            TEXT,
    raw_location        TEXT,
    raw_employment_type TEXT,
    fetched_html        TEXT,   -- truncated snapshot for debug
    fetched_at          TEXT    NOT NULL,
    content_hash        TEXT,   -- md5(raw_title + raw_body)
    http_status         INTEGER DEFAULT 200,
    UNIQUE(job_url, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_raw_site      ON raw_job_records(source_site);
CREATE INDEX IF NOT EXISTS idx_raw_url       ON raw_job_records(job_url);
CREATE INDEX IF NOT EXISTS idx_raw_fetched   ON raw_job_records(fetched_at);

-- ─── 3. Normalized jobs (common schema) ─────────────────────
CREATE TABLE IF NOT EXISTS normalized_jobs (
    id                  INTEGER PRIMARY KEY,
    raw_id              INTEGER REFERENCES raw_job_records(id),
    source_site         TEXT    NOT NULL,
    source_url          TEXT    NOT NULL,
    company_name        TEXT,
    job_title           TEXT,
    team_or_department  TEXT,
    location            TEXT,
    employment_type     TEXT,   -- 'fulltime' | 'contract' | 'unknown'
    seniority           TEXT,   -- 'junior' | 'mid' | 'senior' | 'lead' | 'unknown'
    domain_tags         TEXT,   -- JSON array: ["semiconductor","cleanroom"]
    role_tags           TEXT,   -- JSON array: ["MEP BIM","VDC","Design Coordination"]
    posting_date        TEXT,
    closing_date        TEXT,
    description_text    TEXT,
    normalized_at       TEXT    DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_norm_company ON normalized_jobs(company_name);
CREATE INDEX IF NOT EXISTS idx_norm_url     ON normalized_jobs(source_url);

-- ─── 4. Canonical jobs (deduped, version-tracked) ───────────
CREATE TABLE IF NOT EXISTS canonical_jobs (
    id              INTEGER PRIMARY KEY,
    canonical_id    TEXT    NOT NULL UNIQUE,  -- sha256(company+title+location) prefix
    company_name    TEXT,
    job_title       TEXT,
    location        TEXT,
    employment_type TEXT,
    domain_tags     TEXT,   -- JSON array
    role_tags       TEXT,   -- JSON array
    description_text TEXT,
    source_url      TEXT,
    source_site     TEXT,
    first_seen_at   TEXT,
    last_seen_at    TEXT,
    status          TEXT    DEFAULT 'active',    -- 'active' | 'closed'
    change_status   TEXT    DEFAULT 'new',       -- 'new' | 'changed' | 'closed' | 'unchanged'
    last_changed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_canon_company ON canonical_jobs(company_name);
CREATE INDEX IF NOT EXISTS idx_canon_status  ON canonical_jobs(status);
CREATE INDEX IF NOT EXISTS idx_canon_change  ON canonical_jobs(change_status);

-- ─── 5. Job versions (change history) ───────────────────────
CREATE TABLE IF NOT EXISTS job_versions (
    id              INTEGER PRIMARY KEY,
    canonical_id    TEXT    NOT NULL REFERENCES canonical_jobs(canonical_id),
    version_num     INTEGER NOT NULL,
    snapshot_json   TEXT,   -- full normalized_job as JSON
    changed_fields  TEXT,   -- JSON list of changed field names
    recorded_at     TEXT    DEFAULT (datetime('now')),
    UNIQUE(canonical_id, version_num)
);

-- ─── 6. Job scores ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS job_scores (
    id                    INTEGER PRIMARY KEY,
    canonical_id          TEXT    NOT NULL REFERENCES canonical_jobs(canonical_id),
    total_score           REAL,
    domain_score          REAL,   -- semiconductor/DC/cleanroom match
    role_level_score      REAL,   -- BIM coord/VDC/governance vs. modeler
    ownership_score       REAL,   -- owner-side / role ownership signals
    employment_type_score REAL,   -- fulltime > contract
    company_tier_score    REAL,   -- Samsung/SK hynix tier bonus
    penalty_score         REAL,   -- deductions for red-flag keywords
    score_breakdown       TEXT,   -- JSON: {rule: points, reason: str}
    scored_at             TEXT    DEFAULT (datetime('now')),
    UNIQUE(canonical_id)
);

-- ─── 7. LLM analyses (optional, async) ─────────────────────
CREATE TABLE IF NOT EXISTS llm_analyses (
    id                  INTEGER PRIMARY KEY,
    canonical_id        TEXT    NOT NULL REFERENCES canonical_jobs(canonical_id),
    fit_reason          TEXT,
    risk_summary        TEXT,
    role_interpretation TEXT,
    match_keywords      TEXT,   -- JSON array of matched keywords
    model_used          TEXT,
    prompt_version      TEXT    DEFAULT 'v1',
    analyzed_at         TEXT    DEFAULT (datetime('now')),
    UNIQUE(canonical_id)
);

-- ─── 8. User job states ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_job_states (
    id           INTEGER PRIMARY KEY,
    canonical_id TEXT    NOT NULL UNIQUE REFERENCES canonical_jobs(canonical_id),
    status       TEXT    DEFAULT 'new',  -- 'new'|'reviewing'|'saved'|'excluded'|'applied'
    memo         TEXT,
    updated_at   TEXT    DEFAULT (datetime('now'))
);

-- ─── 9. Watchlist companies ─────────────────────────────────
CREATE TABLE IF NOT EXISTS watchlist_companies (
    id           INTEGER PRIMARY KEY,
    company_name TEXT    NOT NULL UNIQUE,
    notes        TEXT,
    added_at     TEXT    DEFAULT (datetime('now'))
);

-- ─── 10. Pipeline run logs ──────────────────────────────────
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id               INTEGER PRIMARY KEY,
    run_at           TEXT    NOT NULL,
    sites_attempted  TEXT,   -- JSON list of site names
    jobs_fetched     INTEGER DEFAULT 0,
    jobs_new         INTEGER DEFAULT 0,
    jobs_changed     INTEGER DEFAULT 0,
    jobs_closed      INTEGER DEFAULT 0,
    errors           TEXT,   -- JSON list of error messages
    duration_seconds REAL,
    status           TEXT    DEFAULT 'success'  -- 'success'|'partial'|'failed'
);
