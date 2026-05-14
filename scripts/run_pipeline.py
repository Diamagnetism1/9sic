"""
scripts/run_pipeline.py — Daily pipeline entry point.
Usage:
    python scripts/run_pipeline.py                  # run all enabled adapters
    python scripts/run_pipeline.py --sites saramin  # run specific site only
    python scripts/run_pipeline.py --no-llm         # skip LLM analysis
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Make src importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import (
    init_db, insert_raw, upsert_normalized, upsert_canonical,
    get_canonical, upsert_score, upsert_llm_analysis,
    mark_closed_unseen, log_pipeline_run, get_conn,
)
from src.pipeline.normalizer import normalize
from src.pipeline.change_detector import (
    make_canonical_id, build_canonical_record,
    detect_change, build_version_snapshot,
)
from src.pipeline.scorer import score_job
from src.pipeline.llm_analyzer import analyze_job, should_analyze


def get_enabled_adapters() -> dict:
    """Return {site_name: AdapterClass} for all enabled sites."""
    from src.adapters.saramin import SaraminAdapter
    from src.adapters.jobkorea import JobKoreaAdapter

    # requests 기반 (항상 활성)
    adapters = {
        "saramin":  SaraminAdapter,
        "jobkorea": JobKoreaAdapter,
    }

    # Playwright 기반 — playwright 설치된 경우에만 활성
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        from src.adapters.samsung import SamsungAdapter
        from src.adapters.skhynix import SKHynixAdapter
        from src.adapters.kia import KiaAdapter
        from src.adapters.lg import LGAdapter
        adapters["samsung_careers"] = SamsungAdapter
        adapters["skhynix_careers"] = SKHynixAdapter
        adapters["kia_careers"]     = KiaAdapter
        adapters["lg_careers"]      = LGAdapter
        from src.adapters.remember import RememberAdapter
        adapters["remember"]        = RememberAdapter
        from src.adapters.samsung_cnt import SamsungCNTAdapter
        adapters["samsung_cnt"]    = SamsungCNTAdapter
        print("[pipeline] Playwright adapters loaded: samsung, samsung_cnt, skhynix, kia, lg, remember")
    except ImportError:
        print("[pipeline] Playwright not installed — skipping corporate site adapters")
        print("           설치: pip install playwright && playwright install chromium")

    return adapters


def run_pipeline(sites: list = None, run_llm: bool = True) -> dict:
    start_time = time.time()
    now = datetime.now(timezone.utc).isoformat()
    init_db()

    all_adapters = get_enabled_adapters()
    target_adapters = {k: v for k, v in all_adapters.items()
                       if sites is None or k in sites}

    stats = {
        "run_at": now,
        "sites_attempted": json.dumps(list(target_adapters.keys())),
        "jobs_fetched": 0,
        "jobs_new": 0,
        "jobs_changed": 0,
        "jobs_closed": 0,
        "errors": [],
        "status": "success",
    }

    active_canonical_ids = []

    for site_name, AdapterClass in target_adapters.items():
        print(f"\n{'='*50}")
        print(f"Running adapter: {site_name}")
        print(f"{'='*50}")

        try:
            adapter = AdapterClass()
            raw_records = adapter.run()

            for raw in raw_records:
                stats["jobs_fetched"] += 1

                # 1. Store raw
                raw_id = insert_raw(adapter.to_db_dict(raw))
                if raw_id is None:
                    continue  # exact duplicate — skip

                # 2. Normalize
                raw_dict = {
                    "id": raw_id,
                    "source_site": raw.source_site,
                    "job_url": raw.job_url,
                    "raw_title": raw.raw_title,
                    "raw_body": raw.raw_body,
                    "raw_location": raw.raw_location,
                    "raw_employment_type": raw.raw_employment_type,
                }
                norm = normalize(raw_dict)
                norm_id = upsert_normalized(norm)
                norm["id"] = norm_id

                # 3. Canonicalize + change detection
                cid = make_canonical_id(
                    norm.get("company_name", ""), norm.get("job_title", "")
                )
                norm["canonical_id"] = cid
                existing = get_canonical(cid)
                change_status, changed_fields = detect_change(existing, norm)

                canonical = build_canonical_record(norm, now)
                canonical["change_status"] = change_status
                if existing:
                    canonical["first_seen_at"] = existing["first_seen_at"]

                upsert_canonical(canonical)
                active_canonical_ids.append(cid)

                # 4. Version snapshot on change
                if change_status in ("new", "changed"):
                    version_num = 1 if change_status == "new" else _next_version(cid)
                    snapshot = build_version_snapshot(norm, version_num, changed_fields)
                    _insert_version(snapshot)

                if change_status == "new":
                    stats["jobs_new"] += 1
                elif change_status == "changed":
                    stats["jobs_changed"] += 1

                # 5. Score
                score_record = score_job(norm)
                upsert_score(score_record)

                # 6. LLM analysis (optional, only for qualifying jobs)
                if run_llm and should_analyze(canonical, score_record["total_score"]):
                    llm_result = analyze_job(norm)
                    if llm_result:
                        upsert_llm_analysis(llm_result)

        except Exception as e:
            err_msg = f"{site_name}: {e}"
            print(f"[pipeline] ADAPTER ERROR — {err_msg}")
            stats["errors"].append(err_msg)
            stats["status"] = "partial"

    # 7. Mark stale jobs as closed
    closed = mark_closed_unseen(active_canonical_ids, cutoff_days=3)
    stats["jobs_closed"] = len(closed)

    stats["duration_seconds"] = round(time.time() - start_time, 2)
    stats["errors"] = json.dumps(stats["errors"])

    if stats["errors"] != "[]" and stats["jobs_fetched"] == 0:
        stats["status"] = "failed"

    log_pipeline_run(stats)

    print(f"\n{'='*50}")
    print(f"Pipeline complete in {stats['duration_seconds']}s")
    print(f"  Fetched: {stats['jobs_fetched']}")
    print(f"  New:     {stats['jobs_new']}")
    print(f"  Changed: {stats['jobs_changed']}")
    print(f"  Closed:  {stats['jobs_closed']}")
    print(f"  Status:  {stats['status']}")

    return stats


def _next_version(canonical_id: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(version_num) as v FROM job_versions WHERE canonical_id = ?",
            (canonical_id,),
        ).fetchone()
        return (row["v"] or 0) + 1


def _insert_version(snapshot: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO job_versions
               (canonical_id, version_num, snapshot_json, changed_fields)
               VALUES (:canonical_id, :version_num, :snapshot_json, :changed_fields)""",
            snapshot,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run job intel pipeline")
    parser.add_argument("--sites", nargs="+", help="Specific site names to run")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM analysis")
    args = parser.parse_args()

    run_pipeline(sites=args.sites, run_llm=not args.no_llm)
