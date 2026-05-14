"""
dashboard/app.py — Streamlit Job Intel Dashboard
Run: streamlit run src/dashboard/app.py
"""
import json
import sys
from pathlib import Path

import streamlit as st
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.db.database import (
    init_db, get_dashboard_jobs, set_user_state, get_conn,
)
from src.pipeline.scorer import get_score_tier

# ─── Page config ─────────────────────────────────────────────
st.set_page_config(
    page_title="Job Intel Dashboard",
    page_icon="🎯",
    layout="wide",
)
init_db()

# ─── CSS ─────────────────────────────────────────────────────
st.markdown("""
<style>
  .job-card { border:1px solid #e0e0e0; border-radius:8px; padding:12px; margin:8px 0; }
  .score-hot  { color:#d4380d; font-weight:bold; }
  .score-good { color:#389e0d; font-weight:bold; }
  .score-maybe{ color:#d48806; }
  .score-skip { color:#8c8c8c; }
  .tag { background:#f0f0f0; border-radius:4px; padding:2px 6px; margin:2px; font-size:0.8em; }
  .badge-new     { background:#1890ff; color:white; border-radius:4px; padding:2px 8px; font-size:0.8em; }
  .badge-changed { background:#fa8c16; color:white; border-radius:4px; padding:2px 8px; font-size:0.8em; }
  .badge-closed  { background:#8c8c8c; color:white; border-radius:4px; padding:2px 8px; font-size:0.8em; }
</style>
""", unsafe_allow_html=True)

# ─── Sidebar filters ─────────────────────────────────────────
with st.sidebar:
    st.title("🎯 Job Intel")
    st.divider()

    view_mode = st.radio("View", ["📋 All Jobs", "⭐ Watchlist", "📊 Stats"])
    st.divider()

    st.subheader("Filters")

    min_score = st.slider("Min Score", 0, 120, 20, step=5)

    change_options = st.multiselect(
        "Change Status",
        ["new", "changed", "unchanged"],
        default=["new", "changed"],
    )

    user_status_options = st.multiselect(
        "My Status",
        ["new", "reviewing", "saved", "excluded", "applied"],
        default=["new", "reviewing", "saved"],
    )

    company_search = st.text_input("Company search", "")

    show_closed = st.checkbox("Show closed jobs", False)

    st.divider()
    if st.button("▶️ Run Pipeline Now", use_container_width=True):
        with st.spinner("Running pipeline..."):
            try:
                from scripts.run_pipeline import run_pipeline
                result = run_pipeline(run_llm=False)
                st.success(
                    f"Done! New:{result['jobs_new']} "
                    f"Changed:{result['jobs_changed']} "
                    f"Closed:{result['jobs_closed']}"
                )
                st.rerun()
            except Exception as e:
                st.error(f"Pipeline error: {e}")

# ─── Main content ─────────────────────────────────────────────
if view_mode == "📋 All Jobs":
    _render_job_list(min_score, change_options, user_status_options, company_search, show_closed)
elif view_mode == "⭐ Watchlist":
    _render_watchlist(min_score)
elif view_mode == "📊 Stats":
    _render_stats()


# ─── Render functions ─────────────────────────────────────────

def _render_job_list(min_score, change_filter, status_filter, company_search, show_closed):
    jobs = get_dashboard_jobs(
        status_filter=status_filter or None,
        company_filter=company_search or None,
        change_filter=change_filter or None,
        min_score=min_score,
        watchlist_only=False,
    )

    if show_closed:
        closed_jobs = _get_closed_jobs(min_score)
        jobs = jobs + closed_jobs

    st.header(f"📋 Jobs ({len(jobs)})")

    if not jobs:
        st.info("No jobs match your filters.")
        return

    for job in jobs:
        _render_job_card(job)


def _render_watchlist(min_score):
    jobs = get_dashboard_jobs(min_score=min_score, watchlist_only=True)
    st.header(f"⭐ Watchlist Companies ({len(jobs)} jobs)")

    # Show watchlist management
    with st.expander("Manage Watchlist Companies"):
        col1, col2 = st.columns([3, 1])
        with col1:
            new_company = st.text_input("Add company", key="wl_add")
        with col2:
            if st.button("Add", key="wl_btn") and new_company:
                _add_to_watchlist(new_company)
                st.rerun()

        current_wl = _get_watchlist()
        for company in current_wl:
            c1, c2 = st.columns([4, 1])
            c1.write(company["company_name"])
            if c2.button("Remove", key=f"wl_rm_{company['id']}"):
                _remove_from_watchlist(company["id"])
                st.rerun()

    if not jobs:
        st.info("No jobs from watchlist companies.")
        return

    for job in jobs:
        _render_job_card(job)


def _render_stats():
    st.header("📊 Stats")

    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM canonical_jobs WHERE status='active'").fetchone()[0]
        new_today = conn.execute(
            "SELECT COUNT(*) FROM canonical_jobs WHERE change_status='new' AND date(first_seen_at) = date('now')"
        ).fetchone()[0]
        changed = conn.execute(
            "SELECT COUNT(*) FROM canonical_jobs WHERE change_status='changed'"
        ).fetchone()[0]
        closed = conn.execute(
            "SELECT COUNT(*) FROM canonical_jobs WHERE status='closed'"
        ).fetchone()[0]

        company_dist = conn.execute(
            """SELECT company_name, COUNT(*) as cnt
               FROM canonical_jobs WHERE status='active'
               GROUP BY company_name ORDER BY cnt DESC LIMIT 15"""
        ).fetchall()

        score_dist = conn.execute(
            """SELECT
                 CASE WHEN total_score >= 70 THEN '💎 HOT (70+)'
                      WHEN total_score >= 45 THEN '✅ GOOD (45-69)'
                      WHEN total_score >= 20 THEN '🔍 MAYBE (20-44)'
                      ELSE '⬇️ SKIP (<20)' END as tier,
                 COUNT(*) as cnt
               FROM job_scores
               GROUP BY tier ORDER BY cnt DESC"""
        ).fetchall()

        last_runs = conn.execute(
            "SELECT run_at, jobs_new, jobs_changed, jobs_closed, status FROM pipeline_runs ORDER BY run_at DESC LIMIT 7"
        ).fetchall()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Active Jobs", total)
    col2.metric("New Today", new_today)
    col3.metric("Changed", changed)
    col4.metric("Closed Total", closed)

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("By Company")
        df_co = pd.DataFrame(company_dist, columns=["Company", "Count"])
        st.bar_chart(df_co.set_index("Company"))

    with col_b:
        st.subheader("Score Distribution")
        df_sc = pd.DataFrame(score_dist, columns=["Tier", "Count"])
        st.dataframe(df_sc, hide_index=True)

    st.subheader("Pipeline Runs (last 7)")
    if last_runs:
        df_runs = pd.DataFrame(last_runs, columns=["Run At", "New", "Changed", "Closed", "Status"])
        st.dataframe(df_runs, hide_index=True)
    else:
        st.info("No runs yet.")


def _render_job_card(job: dict):
    score = job.get("total_score", 0)
    tier = get_score_tier(score)
    change = job.get("change_status", "unchanged")
    user_status = job.get("user_status", "new")

    domain_tags = _parse_tags(job.get("domain_tags"))
    role_tags = _parse_tags(job.get("role_tags"))

    # Change badge
    badge_map = {"new": "badge-new", "changed": "badge-changed", "closed": "badge-closed"}
    badge_class = badge_map.get(change, "")
    badge_html = f'<span class="{badge_class}">{change.upper()}</span>' if badge_class else ""

    with st.container():
        st.markdown(f"""
        <div class="job-card">
          <strong>{job.get('company_name','?')}</strong> &nbsp;
          {badge_html} &nbsp;
          <code>{score:.0f}pt</code> — <small>{tier}</small>
          <br><b>{job.get('job_title','?')}</b>
          <br><small>📍 {job.get('location','?')} &nbsp; 🗂 {job.get('employment_type','?')}
          &nbsp; 🕐 {(job.get('last_seen_at','') or '')[:10]}</small>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("Details / Actions"):
            col1, col2 = st.columns([2, 1])

            with col1:
                if domain_tags:
                    st.write("**Domain:**", " ".join(f"`{t}`" for t in domain_tags))
                if role_tags:
                    st.write("**Role:**", " ".join(f"`{t}`" for t in role_tags))

                if job.get("fit_reason"):
                    st.markdown(f"**Fit:** {job['fit_reason']}")
                if job.get("risk_summary"):
                    st.markdown(f"**Risk:** {job['risk_summary']}")
                if job.get("role_interpretation"):
                    st.markdown(f"**Role:** {job['role_interpretation']}")

                # Score breakdown
                breakdown = _parse_breakdown(job.get("score_breakdown"))
                if breakdown:
                    with st.expander("Score breakdown"):
                        for item in breakdown:
                            sign = "+" if item["score"] >= 0 else ""
                            st.write(f"{sign}{item['score']}  {item['label']}  (`{item['matched']}`)")

                if job.get("source_url"):
                    st.markdown(f"[🔗 원문 공고 열기]({job['source_url']})")

            with col2:
                st.write("**My Status**")
                new_status = st.selectbox(
                    "Status",
                    ["new", "reviewing", "saved", "excluded", "applied"],
                    index=["new", "reviewing", "saved", "excluded", "applied"].index(user_status),
                    key=f"status_{job['canonical_id']}",
                    label_visibility="collapsed",
                )
                memo = st.text_area(
                    "Memo",
                    value=job.get("memo") or "",
                    key=f"memo_{job['canonical_id']}",
                    height=80,
                )
                if st.button("Save", key=f"save_{job['canonical_id']}"):
                    set_user_state(job["canonical_id"], new_status, memo)
                    st.success("Saved!")


# ─── Helpers ─────────────────────────────────────────────────

def _parse_tags(tags_json: str) -> list:
    try:
        return json.loads(tags_json or "[]")
    except Exception:
        return []


def _parse_breakdown(bd_json: str) -> list:
    try:
        return json.loads(bd_json or "[]")
    except Exception:
        return []


def _get_closed_jobs(min_score: float) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.*, COALESCE(s.total_score,0) as total_score, s.score_breakdown,
                      COALESCE(u.status,'new') as user_status, u.memo,
                      l.fit_reason, l.risk_summary, l.role_interpretation
               FROM canonical_jobs c
               LEFT JOIN job_scores s      ON c.canonical_id = s.canonical_id
               LEFT JOIN user_job_states u ON c.canonical_id = u.canonical_id
               LEFT JOIN llm_analyses l    ON c.canonical_id = l.canonical_id
               WHERE c.status='closed' AND COALESCE(s.total_score,0) >= ?
               ORDER BY c.last_seen_at DESC LIMIT 50""",
            (min_score,),
        ).fetchall()
    return [dict(r) for r in rows]


def _get_watchlist():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM watchlist_companies ORDER BY company_name"
        ).fetchall()]


def _add_to_watchlist(company_name: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO watchlist_companies (company_name) VALUES (?)",
            (company_name,),
        )


def _remove_from_watchlist(company_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM watchlist_companies WHERE id = ?", (company_id,))
