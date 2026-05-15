JOB INTELLIGENCE PLATFORM
개인용 채용공고 자동 수집 및 모니터링 시스템

설명
이 프로젝트는 개인 맞춤형 채용공고를 자동으로 수집하고, 필요 시 AI 분석까지 연결할 수 있도록 만든 개인용 파이프라인이다.
GitHub Actions를 이용해 정해진 시간에 자동 실행할 수 있고, 수집 결과는 SQLite 데이터베이스에 저장한다.
주요 목적은 반복적인 채용공고 확인 작업을 줄이고, 관심 있는 기업/직무 공고를 지속적으로 추적하는 것이다.

주요 기능
- 주요 채용 사이트 공고 자동 수집
- GitHub Actions 기반 일일 자동 실행
- SQLite DB 저장
- 아티팩트 업로드 및 필요 시 저장소 커밋
- 향후 AI 적합도 분석 확장 가능
- 수동 실행(workflow_dispatch) 지원

기술 스택
- Python 3.11
- Playwright (Chromium)
- SQLite
- GitHub Actions
- pip / requirements.txt
- Anthropic API (선택적 사용)

예상 프로젝트 구조
.
├── .github/
│   └── workflows/
│       └── daily_pipeline.yml
├── data/
│   └── job_intel.db
├── scripts/
│   └── run_pipeline.py
├── src/
│   └── adapters/
├── requirements.txt
└── README.md

로컬 실행 방법
1. 저장소 클론
git clone https://github.com/Diamagnetism1/9sic.git
cd 9sic

2. 가상환경 생성
python -m venv venv

3. 가상환경 활성화
Windows
venv\Scripts\activate

Mac / Linux
source venv/bin/activate

4. 의존성 설치
pip install -r requirements.txt
pip install playwright
playwright install chromium --with-deps

5. 환경변수 설정
Windows PowerShell
$env:ANTHROPIC_API_KEY="your-api-key"
$env:JOB_INTEL_DB="data/job_intel.db"
$env:LLM_SCORE_THRESHOLD="45"

Mac / Linux
export ANTHROPIC_API_KEY="your-api-key"
export JOB_INTEL_DB="data/job_intel.db"
export LLM_SCORE_THRESHOLD="45"

6. 실행
python scripts/run_pipeline.py --no-llm

주의
- --no-llm 옵션은 AI 분석 없이 크롤링/수집 파이프라인만 점검할 때 사용한다.
- 실제 AI 분석까지 수행하려면 코드에서 해당 옵션 처리 방식과 API 키 사용 경로를 확인해야 한다.

GitHub Actions 자동 실행
- 스케줄 실행: 매일 정해진 시간에 자동 실행
- 수동 실행: GitHub Actions 탭에서 직접 Run workflow 가능

예시 cron
0 1 * * *
위 설정은 UTC 기준 01:00이며, 한국 시간(KST) 기준 오전 10:00이다.

운영에 필요한 GitHub 설정
1. Repository > Settings > Actions > General
2. Workflow permissions 항목에서
   Read and write permissions 선택
3. Save 클릭

이 설정이 필요한 이유
- 워크플로우가 실행 후 DB 파일을 저장소에 다시 push하려면 기본 토큰에 쓰기 권한이 있어야 한다.
- 읽기 전용이면 크롤링은 성공해도 마지막 git push 단계에서 실패할 수 있다.

권장 workflow 핵심 설정
daily_pipeline.yml에는 아래 개념이 들어가는 것이 좋다.

1. permissions
permissions:
  contents: write

이유
- GITHUB_TOKEN으로 저장소 내용을 수정하고 push하려면 contents: write 권한이 필요하다.

2. concurrency
concurrency:
  group: job-intel-main
  cancel-in-progress: false

이유
- 스케줄 실행과 수동 실행이 겹치면 DB 파일 push 충돌이 날 수 있다.
- concurrency를 두면 같은 워크플로우가 동시에 main을 갱신하려는 상황을 줄일 수 있다.

3. checkout depth
- uses: actions/checkout@v4
  with:
    fetch-depth: 0

이유
- git pull --rebase 또는 전체 히스토리 기반 동작이 필요한 경우 shallow clone은 문제를 일으킬 수 있다.

4. DB 커밋 방식
git add -f data/job_intel.db

이유
- .gitignore에 *.db 또는 data/ 규칙이 생겨도 강제로 추가할 수 있다.

5. 변경 없으면 종료
if git diff --staged --quiet; then
  echo "No changes to commit"
  exit 0
fi

이유
- 실제 변경이 없을 때 불필요한 커밋과 push를 막는다.

권장 커밋 단계 예시
set -euo pipefail

git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"

git add -f data/job_intel.db

if git diff --staged --quiet; then
  echo "No changes to commit"
  exit 0
fi

git commit -m "chore: daily pipeline run $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git pull --rebase origin main
git push origin HEAD:main

왜 이 순서가 중요한가
- 먼저 결과물을 하나의 커밋으로 만들고
- 그 뒤 원격 최신 커밋 위로 재배치(rebase)한 후
- 마지막에 push해야 non-fast-forward 문제를 줄일 수 있다

중요한 운영상 주의점
1. SQLite DB를 git에 직접 커밋하는 구조는 간단하지만 장기적으로 충돌에 약하다.
2. .db 파일은 바이너리라 merge/rebase 충돌 시 해결이 어렵다.
3. 프로젝트가 커지면 artifact 저장 또는 외부 저장소 분리를 고려하는 것이 더 안정적이다.

추천 운영 전략
- 초기 단계: SQLite DB를 repo에 커밋
- 중기 단계: artifact 병행 저장
- 장기 단계: JSON/CSV 스냅샷 또는 외부 저장소(S3, R2, Supabase 등) 검토

수동 실행 방법
1. GitHub 저장소 접속
2. Actions 탭 클릭
3. Daily Job Intel Pipeline 선택
4. Run workflow 클릭
5. 브랜치 선택 후 실행

문제 발생 시 확인 순서
1. Actions 로그에서 실패한 step 이름 확인
2. 실패 로그 마지막 20줄 확인
3. 아래 항목 점검

체크리스트
- Workflow permissions가 Read and write로 설정되어 있는가
- daily_pipeline.yml에 permissions: contents: write가 있는가
- concurrency가 있는가
- actions/checkout에 fetch-depth: 0이 있는가
- git add -f data/job_intel.db를 사용하는가
- branch protection 또는 ruleset이 main 직접 push를 막고 있지 않은가
- data/job_intel.db 파일이 실제 생성되는가

자주 발생하는 오류와 원인

1. failed to push some refs
원인
- 원격 저장소에 내 로컬에 없는 커밋이 존재
- 동시에 여러 workflow가 실행됨
- branch protection 또는 rebase 충돌

대응
- concurrency 추가
- git pull --rebase 순서 확인
- branch protection 확인

2. Permission denied
원인
- GITHUB_TOKEN 쓰기 권한 부족
- 저장소 Actions 권한 설정 미완료
- workflow permissions 누락

대응
- Settings > Actions > General > Workflow permissions 확인
- daily_pipeline.yml에 permissions: contents: write 추가

3. pathspec did not match any files
원인
- data/job_intel.db 파일이 생성되지 않음
- 경로가 잘못됨

대응
- 스크립트가 실제로 DB를 생성하는지 확인
- data 폴더 존재 여부 확인

4. No changes to commit
원인
- 변경사항이 없어서 정상 종료
의미
- 오류가 아니라 결과적으로 새 데이터가 없다는 뜻일 수 있음

브랜치 보호 규칙 확인
확인 위치
- Repository > Settings > Branches
또는
- Repository > Settings > Rules / Rulesets

확인 항목
- Require a pull request before merging
- Restrict who can push
- Require status checks
- Require signed commits

왜 확인해야 하나
- workflow 권한이 정상이어도 branch protection이 direct push를 막으면 push는 실패한다.

보안 메모
- API 키는 코드에 직접 넣지 않는다
- GitHub Secrets 사용
- 개인정보가 포함된 파일은 repo에 커밋하지 않는다
- 이력서, 지원서, 동의서 등 민감 문서는 별도 보관한다

향후 개선 아이디어
- 사이트별 수집 결과를 JSON으로 병행 저장
- AI 요약/적합도 스코어링 선택 실행 옵션 추가
- 중복 공고 판별 로직 강화
- 알림 기능(이메일, 디스코드, 슬랙, 텔레그램) 추가
- Streamlit 또는 간단한 웹 대시보드 연결

프로젝트 목적 정리
이 프로젝트의 핵심은 단순 크롤링이 아니라,
반복적인 채용공고 확인 작업을 자동화하고
관심 공고를 누적 관리할 수 있는 개인용 운영 시스템을 만드는 것이다.

실무 메모
- 처음에는 반드시 수동 실행으로 1회 검증
- 그 다음 스케줄 활성화
- push 실패 시 YAML만 보지 말고 branch/ruleset/log를 함께 확인
- 장기적으로는 DB를 git에 계속 커밋하는 구조를 재검토할 것

저장 파일명 예시
README.txt
README.md
운영메모.txt
