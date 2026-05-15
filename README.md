Job Intelligence Platform

나만을 위한 AI 기반 채용공고 자동 모니터링 시스템

📌 프로젝트 개요

이 프로젝트는 개인 맞춤형 채용공고 자동 수집·분석·추천 시스템입니다.  GitHub Actions를 통해 매일 자동으로 주요 채용 사이트를 크롤링하고, AI가 내 이력서와 적합도를 분석하여 SQLite DB에 저장합니다.

🎯 핵심 기능

✅ 자동 크롤링: 매일 오전 10시 자동 실행 (또는 수동 실행 가능)✅ 멀티 사이트 지원: 사람인, 잡코리아, 원티드, 삼성 등 주요 채용 사이트✅ AI 적합도 분석: Anthropic Claude API를 활용한 이력서 매칭✅ SQLite 데이터베이스: 수집된 공고를 구조화된 DB로 관리✅ GitHub 자동 커밋: 업데이트된 DB를 자동으로 저장소에 반영

🛠️ 기술 스택

구분기술언어Python 3.11크롤링Playwright (Chromium)AIAnthropic Claude API데이터베이스SQLite자동화GitHub Actions의존성 관리pip + requirements.txt

📂 프로젝트 구조
        
                text
                
    



    Copy
            
            .
├── .github/
│   └── workflows/
│       └── daily_pipeline.yml    # GitHub Actions 워크플로우
├── data/
│   └── job_intel.db              # SQLite 데이터베이스 (자동 생성)
├── scripts/
│   └── run_pipeline.py           # 메인 파이프라인 스크립트
├── src/
│   └── adapters/                 # 사이트별 크롤러
│       ├── saramin.py
│       ├── jobkorea.py
│       ├── kia.py
│       ├── lg.py
│       ├── saramin_cnt.py
│       ├── rememberapp.py
│       └── skynyc.py
├── requirements.txt              # Python 의존성
└── README.md                     # 이 파일
        ⚙️ 설정 방법

1️⃣ 저장소 복제
        
                bash
                
    



    Copy
            
            git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
        2️⃣ 환경 변수 설정 (GitHub Secrets)

Repository → Settings → Secrets and variables → Actions → New repository secret

Secret 이름설명예시ANTHROPIC_API_KEYClaude API 키sk-ant-xxxxx
3️⃣ GitHub Actions 권한 설정

Repository → Settings → Actions → General → Workflow permissions

✅ Read and write permissions 선택✅ Save 클릭

4️⃣ 로컬 실행 (선택사항)
        
                bash
                
    



    Copy
            
            # 가상환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
pip install playwright
playwright install chromium --with-deps

# 실행
export ANTHROPIC_API_KEY="your-api-key"
export JOB_INTEL_DB="data/job_intel.db"
export LLM_SCORE_THRESHOLD="45"
python scripts/run_pipeline.py --no-llm
        🚀 자동 실행 방식

📅 스케줄 실행

매일 오전 10시 (한국 시간) 자동 실행GitHub Actions cron: 0 1   * (UTC 01:00 = KST 10:00)

🖱️ 수동 실행

Repository → Actions → Daily Job Intel Pipeline → Run workflow

🔄 워크플로우 동작 방식
        
                mermaid
                
    



    Copy
            
            graph LR
    A[스케줄/수동 트리거] --> B[Python 환경 설정]
    B --> C[의존성 설치]
    C --> D[Playwright 설치]
    D --> E[크롤링 실행]
    E --> F[AI 분석]
    F --> G[SQLite DB 저장]
    G --> H[GitHub 자동 커밋]
        주요 단계

Checkout: 저장소 코드 체크아웃 (전체 히스토리)Python 설정: Python 3.11 + pip 캐시의존성 설치: requirements.txt + playwrightPlaywright 설치: Chromium 브라우저 설치DB 복원: 이전 실행 DB 캐시 복원파이프라인 실행: 크롤링 + AI 분석DB 아티팩트 저장: 30일 보관자동 커밋: 변경사항 자동 push

🗃️ 데이터베이스 스키마
        
                sql
                
    



    Copy
            
            CREATE TABLE jobs (
    id INTEGER PRIMARY KEY,
    site TEXT,              -- 채용 사이트명
    title TEXT,             -- 공고 제목
    company TEXT,           -- 회사명
    location TEXT,          -- 근무지
    experience TEXT,        -- 경력
    deadline TEXT,          -- 마감일
    url TEXT UNIQUE,        -- 공고 URL
    ai_score INTEGER,       -- AI 적합도 점수 (0-100)
    created_at TIMESTAMP    -- 수집 일시
);
        🔧 트러블슈팅

❌ Push 실패: "failed to push some refs"

원인: 동시 실행 또는 원격 변경사항과 충돌

해결:✅ concurrency 설정 확인 (동시 실행 방지)✅ git pull --rebase 순서 확인✅ permissions: contents: write 확인

❌ Playwright 설치 실패

원인: 시스템 의존성 누락

해결:
        
                bash
                
    



    Copy
            
            playwright install chromium --with-deps
        ❌ AI 분석 안 됨

원인: API 키 미설정 또는 잘못된 환경변수

해결:GitHub Secrets에 ANTHROPIC_API_KEY 확인로컬 실행 시 환경변수 export 확인

📊 모니터링

Actions 실행 확인

Repository → Actions → 최근 워크플로우 실행 확인

DB 다운로드

Repository → Actions → 해당 실행 → Artifacts → job-intel-db-xxxxx 다운로드

🔒 보안 고려사항

✅ API 키는 절대 코드에 하드코딩하지 않음✅ GitHub Secrets로 민감 정보 관리✅ .gitignore에 로컬 설정 파일 추가 권장✅ DB에 개인정보 저장 시 암호화 고려

📝 커스터마이징

크롤링 사이트 추가

src/adapters/ 폴더에 새 크롤러 추가 후  scripts/run_pipeline.py에서 import 및 실행 추가

AI 점수 임계값 변경

.github/workflows/daily_pipeline.yml:
        
                yaml
                
    



    Copy
            
            env:
  LLM_SCORE_THRESHOLD: "50"  # 기본 45 → 50으로 변경
        실행 시간 변경
        
                yaml
                
    



    Copy
            
            on:
  schedule:
    - cron: "0 9 * * *"  # 매일 18:00 KST로 변경
        🤝 기여

개선 제안 및 이슈는 Issues 탭에서 환영합니다!

📜 라이선스

이 프로젝트는 개인 용도로 제작되었습니다.

📞 문의

GitHub: @your-usernameEmail: your-email@example.com

💡 Tip: 첫 실행 시 수동으로 한 번 실행해서 정상 동작 확인 후 스케줄에 맡기세요!
