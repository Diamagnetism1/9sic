"""
dashboard/app.py — Job Intel Dashboard
"""
import json
import sys
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.db.database import init_db, get_dashboard_jobs, set_user_state, get_conn
from src.pipeline.scorer import get_score_tier

st.set_page_config(page_title="Job Intel", page_icon="🎯", layout="wide")
init_db()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }

/* ── Card ── */
.job-card {
  background: #ffffff;
  border: 1px solid #ebebeb;
  border-radius: 12px;
  padding: 18px 20px 14px 20px;
  margin: 8px 0;
  position: relative;
  transition: box-shadow 0.15s, border-color 0.15s;
}
.job-card:hover {
  box-shadow: 0 4px 16px rgba(0,0,0,0.07);
  border-color: #d0d0d0;
}

/* ── Source badges (top-right) ── */
.source-badges {
  position: absolute;
  top: 14px;
  right: 16px;
  display: flex;
  gap: 4px;
}
.src-badge {
  font-size: 11px;
  font-weight: 700;
  border-radius: 6px;
  padding: 3px 9px;
  letter-spacing: 0.2px;
}
/* 일반 구인공고 사이트 — 파란색 */
.src-blue   { background: #e6f4ff; color: #0958d9; border: 1px solid #91caff; }
/* 대기업 자체 채용 — 주황색 */
.src-orange { background: #fff7e6; color: #d46b08; border: 1px solid #ffd591; }
/* 리멤버 — 노란색 */
.src-yellow { background: #feffe6; color: #7c6100; border: 1px solid #ffe58f; }

/* ── Score + Fit bar ── */
.score-block {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 10px 0 6px 0;
}
.fit-label {
  font-size: 11px;
  color: #8c8c8c;
  white-space: nowrap;
}
.fit-bar-wrap {
  flex: 1;
  max-width: 160px;
  background: #f0f0f0;
  border-radius: 99px;
  height: 7px;
  overflow: hidden;
}
.fit-bar-fill {
  height: 100%;
  border-radius: 99px;
  transition: width 0.4s;
}
.fit-pct {
  font-size: 13px;
  font-weight: 700;
  white-space: nowrap;
}
.score-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 99px;
  white-space: nowrap;
}

/* ── Employment type badge ── */
.emp-badge {
  font-size: 11px;
  font-weight: 600;
  border-radius: 4px;
  padding: 2px 8px;
  display: inline-block;
  margin-right: 6px;
}
.emp-full     { background: #f6ffed; color: #389e0d; border: 1px solid #b7eb8f; }
.emp-contract { background: #fff2e8; color: #d4380d; border: 1px solid #ffbb96; }
.emp-dispatch { background: #fff1f0; color: #cf1322; border: 1px solid #ffa39e; }
.emp-unknown  { background: #fafafa; color: #8c8c8c; border: 1px solid #d9d9d9; }

/* ── Change badge ── */
.change-new     { font-size:11px; font-weight:700; background:#e6f4ff; color:#0958d9; border-radius:4px; padding:2px 7px; margin-right:4px; }
.change-changed { font-size:11px; font-weight:700; background:#fff7e6; color:#d46b08; border-radius:4px; padding:2px 7px; margin-right:4px; }

/* ── Title & meta ── */
.job-title {
  font-size: 15px; font-weight: 700; color: #111827;
  margin: 4px 0 2px 0; line-height: 1.45;
  padding-right: 120px; /* avoid overlap with badges */
}
.job-company { font-size: 13px; color: #374151; font-weight: 500; margin-bottom: 2px; }
.job-meta    { font-size: 12px; color: #9ca3af; }
.job-meta span { margin-right: 10px; }

.dday-hot    { color: #cf1322; font-weight: 700; font-size: 12px; }
.dday-ok     { color: #389e0d; font-weight: 700; font-size: 12px; }
.dday-always { color: #9ca3af; font-size: 12px; }

.section-title { font-size: 20px; font-weight: 700; color: #111827; margin: 20px 0 2px 0; }
.section-sub   { font-size: 12px; color: #9ca3af; margin-bottom: 14px; }
</style>
""", unsafe_allow_html=True)


# ─── Constants ───────────────────────────────────────────────

# 최대 이론 점수 (domain 30 + role 35 + ownership 20 + company 20 + emp 10 = 115)
MAX_SCORE = 115.0

# Source → category
SOURCE_CATEGORY = {
    "saramin":         "general",
    "jobkorea":        "general",
    "remember":        "remember",
    "samsung_careers": "corporate",
    "skhynix_careers": "corporate",
    "kia_careers":     "corporate",
    "lg_careers":      "corporate",
}

SOURCE_LABEL = {
    "saramin":         "사람인",
    "jobkorea":        "잡코리아",
    "remember":        "리멤버",
    "samsung_careers": "삼성전자",
    "skhynix_careers": "SK하이닉스",
    "kia_careers":     "기아",
    "lg_careers":      "LG",
}


# ─── Helpers ─────────────────────────────────────────────────

def _fit_pct(score):
    return min(100, max(0, round(score * 100 / MAX_SCORE)))

def _fit_color(pct):
    if pct >= 70: return "#cf1322"
    if pct >= 50: return "#389e0d"
    if pct >= 30: return "#d4b106"
    return "#d9d9d9"

def _fit_label(pct):
    if pct >= 70: return ("score-hot",   "🔥 강력추천")
    if pct >= 50: return ("score-good",  "✅ 추천")
    if pct >= 30: return ("score-maybe", "🔍 검토")
    return ("score-skip", "—")

def _source_badge_html(source_site: str) -> str:
    label = SOURCE_LABEL.get(source_site, source_site or "기타")
    cat   = SOURCE_CATEGORY.get(source_site, "general")
    cls   = {"general": "src-blue", "corporate": "src-orange", "remember": "src-yellow"}.get(cat, "src-blue")
    return f'<span class="src-badge {cls}">{label}</span>'

def _all_sources_for(canonical_id: str) -> list:
    """모든 소스 사이트 조회 (same canonical = multiple sources)"""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT DISTINCT n.source_site
               FROM normalized_jobs n
               JOIN canonical_jobs c ON n.source_url = c.source_url
               WHERE c.canonical_id = ?""",
            (canonical_id,)
        ).fetchall()
        if not rows:
            # fallback: get from canonical_jobs directly
            row = conn.execute(
                "SELECT source_site FROM canonical_jobs WHERE canonical_id=?",
                (canonical_id,)
            ).fetchone()
            return [row[0]] if row and row[0] else []
    return [r[0] for r in rows]

def _dday_html(closing_date):
    if not closing_date:
        return '<span class="dday-always">상시채용</span>'
    try:
        diff = (datetime.strptime(closing_date[:10], "%Y-%m-%d") - datetime.now()).days
        if diff < 0:   return '<span class="dday-always">마감</span>'
        if diff <= 7:  return f'<span class="dday-hot">D-{diff}</span>'
        return f'<span class="dday-ok">D-{diff}</span>'
    except Exception:
        return '<span class="dday-always">상시채용</span>'

def _emp_badge_html(emp_type):
    m = {"fulltime":  ("정규직", "emp-full"),
         "contract":  ("계약직", "emp-contract"),
         "dispatch":  ("파견직", "emp-dispatch"),
         "internship":("인턴",   "emp-contract")}
    label, cls = m.get(emp_type, ("고용형태미상", "emp-unknown"))
    return f'<span class="emp-badge {cls}">{label}</span>'

def _change_badge_html(change):
    if change == "new":     return '<span class="change-new">NEW</span>'
    if change == "changed": return '<span class="change-changed">변경</span>'
    return ""

def _parse_tags(j): 
    try: return json.loads(j or "[]")
    except: return []

def _parse_breakdown(j):
    try: return json.loads(j or "[]")
    except: return []

def _get_watchlist():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM watchlist_companies ORDER BY company_name").fetchall()]

def _add_to_watchlist(name):
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO watchlist_companies (company_name) VALUES (?)", (name,))

def _remove_from_watchlist(wid):
    with get_conn() as conn:
        conn.execute("DELETE FROM watchlist_companies WHERE id=?", (wid,))

def _get_closed_jobs(min_score):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.*, COALESCE(s.total_score,0) as total_score, s.score_breakdown,
                      COALESCE(u.status,'new') as user_status, u.memo,
                      l.fit_reason, l.risk_summary, l.role_interpretation
               FROM canonical_jobs c
               LEFT JOIN job_scores s ON c.canonical_id=s.canonical_id
               LEFT JOIN user_job_states u ON c.canonical_id=u.canonical_id
               LEFT JOIN llm_analyses l ON c.canonical_id=l.canonical_id
               WHERE c.status='closed' AND COALESCE(s.total_score,0)>=?
               ORDER BY c.last_seen_at DESC LIMIT 50""",
            (min_score,)).fetchall()
    return [dict(r) for r in rows]


# ─── Job Card ─────────────────────────────────────────────────

def _render_job_card(job):
    score    = job.get("total_score", 0)
    fit      = _fit_pct(score)
    bar_color= _fit_color(fit)
    _, flabel= _fit_label(fit)
    change   = job.get("change_status", "unchanged")
    emp_type = job.get("employment_type", "unknown")
    closing  = job.get("closing_date", "")
    cid      = job.get("canonical_id", "")
    user_st  = job.get("user_status", "new")

    # 멀티소스 배지
    sources = _all_sources_for(cid) or [job.get("source_site", "")]
    sources_html = "".join(_source_badge_html(s) for s in sources)

    st.markdown(f"""
    <div class="job-card">
      <!-- 소스 배지 우상단 -->
      <div class="source-badges">{sources_html}</div>

      <!-- 고용형태 + 변경상태 + D-day -->
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
        {_emp_badge_html(emp_type)}
        {_change_badge_html(change)}
        {_dday_html(closing)}
      </div>

      <!-- 제목 -->
      <div class="job-title">{job.get('job_title') or '(제목 없음)'}</div>
      <div class="job-company">🏢 {job.get('company_name') or '?'}</div>

      <!-- 점수 + 적합도 바 -->
      <div class="score-block">
        <span class="fit-label">직무적합도</span>
        <div class="fit-bar-wrap">
          <div class="fit-bar-fill" style="width:{fit}%;background:{bar_color};"></div>
        </div>
        <span class="fit-pct" style="color:{bar_color};">{fit}%</span>
        <span class="fit-label" style="margin-left:4px;">{flabel} &nbsp; ({score:.0f}pt)</span>
      </div>

      <!-- 메타 -->
      <div class="job-meta">
        <span>📍 {job.get('location') or '?'}</span>
        <span>🕐 {(job.get('last_seen_at') or '')[:10]}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("상세 / 상태 변경"):
        col1, col2 = st.columns([2, 1])
        with col1:
            dtags = _parse_tags(job.get("domain_tags"))
            rtags = _parse_tags(job.get("role_tags"))
            if dtags or rtags:
                tags_html = "".join(f'<span style="background:#f0f0f0;border-radius:4px;padding:2px 8px;margin:2px;font-size:12px;display:inline-block;">{t}</span>' for t in dtags + rtags)
                st.markdown(tags_html, unsafe_allow_html=True)
                st.markdown("")

            if job.get("fit_reason"):
                st.success(f"✅ {job['fit_reason']}")
            if job.get("risk_summary"):
                st.warning(f"⚠️ {job['risk_summary']}")
            if job.get("role_interpretation"):
                st.markdown(f"**역할 해석:** {job['role_interpretation']}")

            bd = _parse_breakdown(job.get("score_breakdown"))
            if bd:
                with st.expander("점수 상세 보기"):
                    for item in bd:
                        sign = "+" if item["score"] >= 0 else ""
                        c = "green" if item["score"] > 0 else "red"
                        st.markdown(f":{c}[{sign}{item['score']}pt] &nbsp; {item['label']} &nbsp; `{item['matched']}`")

            if job.get("source_url"):
                st.markdown(f"[🔗 원문 공고 열기]({job['source_url']})")

        with col2:
            sl = ["new","reviewing","saved","excluded","applied"]
            lm = {"new":"신규","reviewing":"검토중","saved":"찜","excluded":"제외","applied":"지원완료"}
            idx = sl.index(user_st) if user_st in sl else 0
            ns = st.selectbox("내 상태", [lm[s] for s in sl], index=idx, key=f"st_{cid}")
            memo = st.text_area("메모", value=job.get("memo") or "", key=f"mo_{cid}", height=80)
            if st.button("저장", key=f"sv_{cid}"):
                real = sl[[lm[s] for s in sl].index(ns)]
                set_user_state(cid, real, memo)
                st.success("저장됨!")


# ─── Views ───────────────────────────────────────────────────

def _render_job_list(min_score, change_filter, status_filter, company_search, show_closed):
    jobs = get_dashboard_jobs(
        status_filter=status_filter or None,
        company_filter=company_search or None,
        change_filter=change_filter or None,
        min_score=min_score,
    )
    if show_closed:
        jobs = jobs + _get_closed_jobs(min_score)

    st.markdown(f'<div class="section-title">📋 공고 목록 <span style="font-size:16px;color:#9ca3af;font-weight:500;">({len(jobs)})</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">커리어 전략 기반 자동 필터링 · 점수순 정렬</div>', unsafe_allow_html=True)

    if not jobs:
        st.info("공고가 없습니다. 왼쪽 '지금 수집 실행'을 눌러 시작하세요.")
        return
    for job in jobs:
        _render_job_card(job)


def _render_watchlist(min_score):
    jobs = get_dashboard_jobs(min_score=min_score, watchlist_only=True)
    st.markdown(f'<div class="section-title">⭐ 관심 기업 <span style="font-size:16px;color:#9ca3af;font-weight:500;">({len(jobs)})</span></div>', unsafe_allow_html=True)

    with st.expander("관심 기업 관리"):
        c1, c2 = st.columns([3,1])
        with c1: new_co = st.text_input("기업명", key="wl_add")
        with c2:
            if st.button("추가", key="wl_btn") and new_co:
                _add_to_watchlist(new_co); st.rerun()
        for co in _get_watchlist():
            a, b = st.columns([4,1])
            a.write(co["company_name"])
            if b.button("삭제", key=f"wl_rm_{co['id']}"): 
                _remove_from_watchlist(co["id"]); st.rerun()

    if not jobs:
        st.info("관심 기업의 공고가 없습니다.")
        return
    for job in jobs: _render_job_card(job)


def _render_stats():
    st.markdown('<div class="section-title">📊 통계</div>', unsafe_allow_html=True)
    with get_conn() as conn:
        total     = conn.execute("SELECT COUNT(*) FROM canonical_jobs WHERE status='active'").fetchone()[0]
        new_today = conn.execute("SELECT COUNT(*) FROM canonical_jobs WHERE change_status='new' AND date(first_seen_at)=date('now')").fetchone()[0]
        changed   = conn.execute("SELECT COUNT(*) FROM canonical_jobs WHERE change_status='changed'").fetchone()[0]
        closed    = conn.execute("SELECT COUNT(*) FROM canonical_jobs WHERE status='closed'").fetchone()[0]
        company_dist = conn.execute("SELECT company_name, COUNT(*) as cnt FROM canonical_jobs WHERE status='active' GROUP BY company_name ORDER BY cnt DESC LIMIT 15").fetchall()
        score_dist   = conn.execute("""SELECT CASE WHEN total_score>=70 THEN '🔥 강력추천 (70+)' WHEN total_score>=45 THEN '✅ 추천 (45-69)' WHEN total_score>=20 THEN '🔍 검토 (20-44)' ELSE '— 낮음 (<20)' END as tier, COUNT(*) as cnt FROM job_scores GROUP BY tier ORDER BY cnt DESC""").fetchall()
        last_runs    = conn.execute("SELECT run_at, jobs_new, jobs_changed, jobs_closed, status FROM pipeline_runs ORDER BY run_at DESC LIMIT 7").fetchall()

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("활성 공고", total); c2.metric("오늘 신규", new_today)
    c3.metric("변경됨", changed);  c4.metric("마감됨", closed)

    ca, cb = st.columns(2)
    with ca:
        st.subheader("기업별 공고 수")
        if company_dist:
            st.bar_chart(pd.DataFrame(company_dist, columns=["기업","공고수"]).set_index("기업"))
        else: st.info("데이터 없음")
    with cb:
        st.subheader("적합도 분포")
        if score_dist:
            st.dataframe(pd.DataFrame(score_dist, columns=["등급","공고수"]), hide_index=True)
        else: st.info("데이터 없음")

    st.subheader("파이프라인 실행 기록")
    if last_runs:
        st.dataframe(pd.DataFrame(last_runs, columns=["실행시각","신규","변경","마감","상태"]), hide_index=True)
    else: st.info("실행 기록 없음")


# ─── Sidebar ─────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🎯 Job Intel")
    st.caption("커리어 전략 맞춤 공고 대시보드")

    # 배지 범례
    st.markdown("""
    <div style="font-size:11px;color:#6b7280;margin:8px 0 4px 0;">소스 배지 범례</div>
    <span class="src-badge src-blue" style="font-size:11px;font-weight:700;border-radius:6px;padding:3px 9px;background:#e6f4ff;color:#0958d9;border:1px solid #91caff;">구인사이트</span>&nbsp;
    <span class="src-badge src-orange" style="font-size:11px;font-weight:700;border-radius:6px;padding:3px 9px;background:#fff7e6;color:#d46b08;border:1px solid #ffd591;">대기업</span>&nbsp;
    <span class="src-badge src-yellow" style="font-size:11px;font-weight:700;border-radius:6px;padding:3px 9px;background:#feffe6;color:#7c6100;border:1px solid #ffe58f;">리멤버</span>
    """, unsafe_allow_html=True)

    st.divider()
    view_mode = st.radio("", ["📋 공고 목록","⭐ 관심 기업","📊 통계"], label_visibility="collapsed")
    st.divider()

    st.markdown("**필터**")
    min_score = st.slider("최소 적합도 점수", 0, 120, 20, step=5)
    change_options = st.multiselect("변경 상태", ["new","changed","unchanged"], default=["new","changed"],
        format_func=lambda x: {"new":"신규","changed":"변경","unchanged":"변동없음"}[x])
    user_status_options = st.multiselect("내 상태", ["new","reviewing","saved","excluded","applied"],
        default=["new","reviewing","saved"],
        format_func=lambda x: {"new":"신규","reviewing":"검토중","saved":"찜","excluded":"제외","applied":"지원완료"}[x])
    company_search = st.text_input("기업명 검색", "")
    show_closed = st.checkbox("마감 공고 포함", False)

    st.divider()
    if st.button("▶ 지금 수집 실행", use_container_width=True, type="primary"):
        with st.spinner("수집 중..."):
            try:
                from scripts.run_pipeline import run_pipeline
                result = run_pipeline(run_llm=False)
                st.success(f"완료! 신규 {result['jobs_new']}개 / 변경 {result['jobs_changed']}개")
                st.rerun()
            except Exception as e:
                st.error(f"오류: {e}")


# ─── Main ─────────────────────────────────────────────────────

if view_mode == "📋 공고 목록":
    _render_job_list(min_score, change_options, user_status_options, company_search, show_closed)
elif view_mode == "⭐ 관심 기업":
    _render_watchlist(min_score)
elif view_mode == "📊 통계":
    _render_stats()
