# Job Intel Dashboard

개인 커리어 전략에 맞는 채용공고만 자동 선별하는 개인용 Job Intelligence 시스템.

---

## 빠른 시작

```bash
# 1. 설치
pip install -r requirements.txt

# 2. DB 초기화 + 파이프라인 실행 (requests 기반 사이트만)
python scripts/run_pipeline.py --sites saramin jobkorea

# 3. 대시보드 실행
streamlit run src/dashboard/app.py
```

브라우저에서 `http://localhost:8501` 접속.

---

## 환경변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `JOB_INTEL_DB` | SQLite 파일 경로 | `data/job_intel.db` |
| `ANTHROPIC_API_KEY` | LLM 분석용 (optional) | 없으면 LLM 스킵 |
| `LLM_SCORE_THRESHOLD` | LLM 분석 최소 점수 | `30` |

---

## 파이프라인 실행 옵션

```bash
# 전체 실행
python scripts/run_pipeline.py

# 특정 사이트만
python scripts/run_pipeline.py --sites saramin

# LLM 분석 없이
python scripts/run_pipeline.py --no-llm

# Playwright 사이트 포함 (playwright 설치 필요)
# playwright install chromium
python scripts/run_pipeline.py --sites samsung_careers skhynix_careers
```

---

## 사이트별 수집 전략

| 사이트 | 방식 | robots.txt |
|--------|------|-----------|
| 사람인 | requests/BS4 | ✅ 허용 |
| 잡코리아 | requests/BS4 | ⚠️ 일부 허용 (`/recruit/joblist`, `/Recruit/GI_Read`) |
| 삼성전자 | Playwright | ✅ robots.txt 없음 (SPA) |
| SK하이닉스 | Playwright | ✅ robots.txt 없음 (SPA) |
| 기아 | Playwright | ✅ robots.txt 없음 (SPA) |
| LG | Playwright | ✅ robots.txt 없음 (SPA) |
| LinkedIn | ❌ 제외 | 자동 수집 명시적 금지 |
| Wanted | ❌ 제외 | CloudFront 차단 |
| 잡플래닛 | ❌ 제외 | Cloudflare 차단 |
| 리멤버 | 수동 추가 | 구조 불명확 |

---

## 폴더 구조

```
job_intel/
├── config/
│   ├── scoring_rules.yaml     # 점수화 규칙 (편집 가능)
│   └── sources.yaml           # (선택) 사이트 설정 override
├── data/
│   └── job_intel.db           # SQLite DB (gitignore 권장)
├── scripts/
│   └── run_pipeline.py        # 파이프라인 진입점
├── src/
│   ├── adapters/
│   │   ├── base.py            # BaseAdapter
│   │   ├── saramin.py         # 사람인
│   │   ├── jobkorea.py        # 잡코리아
│   │   └── samsung.py         # 삼성전자 (Playwright)
│   ├── db/
│   │   ├── schema.sql         # DDL
│   │   └── database.py        # DB 헬퍼
│   ├── pipeline/
│   │   ├── normalizer.py      # raw → normalized
│   │   ├── change_detector.py # canonical + 변경 감지
│   │   ├── scorer.py          # rule-based 점수화
│   │   └── llm_analyzer.py    # LLM 분석 (optional)
│   └── dashboard/
│       └── app.py             # Streamlit UI
├── .github/workflows/
│   └── daily_pipeline.yml     # GitHub Actions 스케줄
└── requirements.txt
```

---

## 점수 기준

| 구간 | 등급 | 의미 |
|------|------|------|
| 70+ | 💎 HOT | 강력 추천 |
| 45–69 | ✅ GOOD | 검토 권장 |
| 20–44 | 🔍 MAYBE | 참고용 |
| <20 | ⬇️ SKIP | 낮은 적합도 |

규칙 편집: `config/scoring_rules.yaml`

---

## GitHub Actions 자동 스케줄

`.github/workflows/daily_pipeline.yml`
- **실행 시각**: 매일 오전 7시 KST
- **대상**: `saramin`, `jobkorea` (requests 기반)
- **DB 보존**: GitHub Artifacts + 캐시로 실행 간 유지

Secrets 설정 필요: `ANTHROPIC_API_KEY` (LLM 사용 시)

---

## Adapter 추가 방법

```python
# src/adapters/mysite.py
from .base import BaseAdapter, RawJobRecord

class MySiteAdapter(BaseAdapter):
    site_name = "mysite"
    requires_playwright = False

    def fetch_job_list(self, **kwargs) -> list[str]:
        # robots.txt 확인 후 URL 목록 반환
        ...

    def fetch_job_detail(self, url: str) -> RawJobRecord | None:
        # 상세 페이지 파싱 후 RawJobRecord 반환
        ...
```

그 다음 `scripts/run_pipeline.py`의 `get_enabled_adapters()`에 추가.
