**분석 입력 명세 (초안)**

작성일: 2026-11-17 · 관련 기능: F01 분석 입력 저장·정규화

이 문서는 한 번의 CI 테스트 작업 실패를 분석하기 위해 보관하는 입력 묶음(input bundle)을 정의한다. 기능 범위와 완료 기준은 [프로젝트 계획서](../ci_failure_analysis_project_plan.md)를 따른다.

**입력 묶음은 GitHub Actions 작업 하나의 시도 하나에 대응한다.**

| 항목 | 값 | 비고 |
|---|---|---|
| 입력 ID | `gha-<run_id>-a<run_attempt>-j<job_id>` | 같은 실행의 재실행은 `run_attempt`로, 같은 실행의 다른 작업은 `job_id`로 구분한다 |
| 보관 위치 | `work/inputs/<입력 ID>/` | Git에서 제외한다. 평가 사례로 쓰는 일부 파일만 검토 후 `evals/cases/`로 복사한다 |
| 불변성 | 저장 후 파일을 수정하지 않는다 | 다시 수집해야 하면 기존 묶음을 지우지 않고 수집 이유를 기록한다 |

**묶음에는 다음 파일을 담는다.**

| 파일 | 내용 | 수집 방법 |
|---|---|---|
| `run.json` | 실행 ID, 시도 번호, 이벤트, 브랜치, `head_sha`, 작업 목록과 단계별 결과 | `gh run view <run_id> --json ...` |
| `job.log` | 작업 전체 로그(단계별 출력, pytest traceback 포함) | `gh run view <run_id> --log` |
| `reports/junit.xml` | pytest JUnit XML | 워크플로가 `pytest --junitxml`로 생성해 `pytest-reports` artifact로 업로드 |
| `reports/checkout_sha.txt` | 작업이 실제로 체크아웃한 커밋 | 워크플로에서 `git rev-parse HEAD` |
| `reports/python_version.txt` | 실행 환경의 Python 버전 | 워크플로에서 `python --version` |
| `code.tar` | 체크아웃 커밋 시점의 저장소 전체 코드 | `git archive <checkout_sha>` |
| `manifest.json` | 위 항목의 요약과 파일별 SHA-256, 묶음 해시 | 수집 후 생성 |

- 코드 버전은 `head_sha`가 아니라 `checkout_sha`를 기준으로 한다. PR 이벤트에서는 병합 결과 커밋을 체크아웃할 수 있기 때문이다.
- 브랜치가 이후에 바뀌어도 같은 입력으로 재분석할 수 있도록 코드를 브랜치 이름이 아닌 커밋으로 고정해 보관한다.
- 수정 커밋, 이후 이력, 정답 파일은 묶음에 넣지 않는다.

**묶음 해시로 입력의 동일성을 판단한다.**

`manifest.json`의 `files`는 `manifest.json`을 제외한 모든 파일의 상대 경로와 SHA-256이다. `bundle_sha256`은 이 목록을 경로순으로 정렬해 `<경로> <해시>\n` 형식으로 이어 붙인 문자열의 SHA-256이다. 분석 실행 기록과 평가 결과는 입력 ID와 묶음 해시를 함께 남긴다.

**다음 경우는 분석하지 않고 사유를 기록한다.**

| 사유 코드 | 조건 |
|---|---|
| `no_junit` | `reports/junit.xml`이 없거나 파싱할 수 없다. 예: 의존성 설치 단계에서 실패해 pytest가 실행되지 않음 |
| `not_test_failure` | 작업은 실패했지만 JUnit XML에 실패·오류 테스트가 없다 |
| `unsupported_runner` | GitHub Actions 외의 CI, 또는 pytest 외의 테스트 도구 |
| `missing_checkout_sha` | 체크아웃 커밋을 확인할 수 없다 |

**현재 수집 방식과 남은 작업**

- 수집기는 `src/ci_failure_analyzer/inputs/collector.py`, 진입 스크립트는 `scripts/collect_run.py`다. D1에 수동으로 수집한 4개 묶음을 수집기로 다시 수집해 묶음 해시가 같음을 확인했다.
- 수집기는 실행당 작업이 하나인 경우만 지원하고, 코드 스냅샷을 만들려면 분석 대상 저장소의 로컬 클론이 필요하다.
- 이미 저장한 묶음은 덮어쓰지 않는다. CI 재실행은 `run_attempt`가 달라 별도 묶음이 된다.
- 분석 대상 저장소의 워크플로는 [`ci-failure-target`](https://github.com/ksm031116-creator/ci-failure-target)의 `.github/workflows/tests.yml`이다. 이 저장소는 비공개다.
- 로그 길이 제한, 여러 작업이 실패한 실행의 처리, 로그 내 민감정보 마스킹 규칙은 F01 구현 때 확정한다.
