**CI 테스트 실패 분석 서비스 — Git 관리 계획**

작성일: 2026-11-16

이 문서는 서비스 저장소의 버전 관리 규칙을 정한다. 파일 위치는 [폴더 관리 계획](./folder_management.md), 구현 범위와 단계는 [프로젝트 계획서](./ci_failure_analysis_project_plan.md)를 따른다.

**저장소는 이 프로젝트 폴더 하나로 시작한다.**

- 저장소 루트는 이 프로젝트 폴더다. 상위 폴더 `personal proj`에는 다른 프로젝트 문서가 있으므로 그곳에서 초기화하지 않는다.
- 분석 대상 저장소는 별도 Git 저장소로 만들고, 이 저장소의 하위 모듈이나 하위 폴더로 넣지 않는다.
- 기본 브랜치는 `main`이다. 폴더 이름은 유지하고 GitHub 저장소 이름은 영문으로 정한다. 예: `ci-failure-analyzer`.
- GitHub 원격 저장소는 비공개로 시작한다. 한 번 푸시한 비밀정보는 이력에서 지우기 어려우므로, 공개 전환은 아래 점검을 마친 뒤에 한다.

처음 설정할 때 실행하는 명령은 다음과 같다.

```bash
git init -b main
git config core.quotepath false
git config core.autocrlf false
```

`core.quotepath false`는 한글 파일명이 이스케이프 문자로 표시되지 않게 하고, 줄바꿈은 `.gitattributes`로 통일한다.

**추적 범위는 `.gitignore`와 `.gitattributes`로 고정한다.**

기본 추적 대상은 루트 문서·설정, `.github/`, `docs/`, `src/`, `configs/`, `migrations/`, `tests/`, `scripts/`, 공유 가능한 `evals/` 자료, 검토한 작은 `outputs/` 보고서다.

`.gitignore` 초안:

```gitignore
# 원본 입력·실행 기록·로컬 서비스 데이터·임시 작업
work/

# 비밀정보: 값 없는 예시 파일만 추적
.env
.env.*
!.env.example

# Python 환경·캐시·빌드 결과
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
dist/
build/
*.egg-info/

# 로컬 DB·대용량 파일
*.db
*.sqlite3
*.mp4
*.zip

# 편집기·OS
.vscode/
.idea/
.DS_Store
Thumbs.db
```

`.gitattributes` 초안:

```gitattributes
* text=auto eol=lf
*.bat text eol=crlf
*.ps1 text eol=crlf
*.png binary
*.jpg binary
```

- 실제 사용하는 경로가 생기면 `.gitignore`를 갱신하고 `git status --ignored`로 제외 목록을 확인한다.
- 예외로 추적할 파일은 공유 가능한지 먼저 검토하고 `!` 규칙으로 명시한다.
- 1MB를 넘는 파일은 커밋 전에 필요성을 확인한다. 처음에는 Git LFS를 사용하지 않는다.

**브랜치는 짧게 유지하고 PR로 병합한다.**

| 접두어 | 용도 | 예시 |
|---|---|---|
| `feat/` | 기능 구현. 계획서의 기능 ID 포함 | `feat/F01-input-bundle` |
| `fix/` | 버그 수정 | `fix/report-citation-line` |
| `exp/` | 프롬프트·탐색 정책·자원 상한 실험 | `exp/agent-budget-tuning` |
| `docs/` | 문서만 변경 | `docs/input-spec` |
| `chore/` | 설정·의존성·도구 변경 | `chore/pre-commit-setup` |

- `main`은 항상 테스트가 통과하는 상태로 유지한다. `main`에 직접 커밋하지 않는다. 단, 0단계 초기 설정 커밋은 예외로 한다.
- 혼자 개발해도 PR로 병합한다. 이 서비스의 CI가 생긴 뒤에는 CI 통과를 병합 조건으로 설정한다.
- 병합은 squash merge를 기본으로 하고, PR 제목을 커밋 규칙에 맞춘다. 병합한 브랜치는 삭제한다.
- `exp/` 브랜치는 결과를 채택하지 않더라도 결론을 `docs/decisions/`에 기록한 뒤 정리한다. 결과 수치의 근거가 된 커밋은 태그로 남긴다.

**커밋은 하나의 목적만 담는다.**

형식은 `type(scope): 요약`이다. type은 영문, 요약은 한국어로 쓴다. scope에는 계획서의 기능 ID나 영역 이름을 쓴다.

| type | 용도 |
|---|---|
| `feat` | 기능 추가 |
| `fix` | 버그 수정 |
| `test` | 테스트 추가·수정 |
| `eval` | 평가 사례·정답·분할·평가 결과 변경 |
| `exp` | 실험 설정·프롬프트 변경 |
| `docs` | 문서 변경 |
| `refactor` | 동작 변화 없는 구조 변경 |
| `chore` | 설정·의존성·도구 |

예:

```text
feat(F01): JUnit XML 파싱과 입력 해시 기록
test(F06): 워커 중단 후 작업 복구 테스트 추가
eval(splits): case-014를 holdout에서 dev로 이동
```

- 코드 변경과 평가 결과 파일은 별도 커밋으로 나눈다.
- `evals/splits/`를 바꾸는 커밋은 본문에 변경 이유를 적는다. 최종 평가 사례를 개발에 사용한 경우도 여기에 기록한다.
- 이미 푸시한 `main`의 이력은 다시 쓰지 않는다. 작업 브랜치에서만 정리한다.

**태그로 단계와 평가 버전을 고정한다.**

| 태그 | 붙이는 시점 | 예시 |
|---|---|---|
| `v0.<단계>` | 계획서의 단계 완료 기준을 통과한 커밋 | `v0.3` |
| `eval-YYYYMMDD-<name>` | 결과표에 사용할 평가를 실행한 커밋 | `eval-20261201-final` |

- 평가 태그는 작업 트리에 변경이 없는 상태에서 실행한 커밋에만 붙인다. 각 실행의 `manifest.json`에 기록된 커밋 SHA와 일치해야 한다.
- `outputs/`의 결과표에는 사용한 평가 태그를 적는다.
- 태그는 주석 태그(`git tag -a`)로 만들고, 메시지에 사용한 설정 파일과 사례 분할을 적는다. 푸시한 태그는 옮기지 않는다.

**비밀정보는 커밋 전에 차단한다.**

- 인증키·토큰은 `.env`에만 두고, 설정 이름은 값이 없는 `.env.example`로 안내한다.
- pre-commit 훅에서 비밀정보 검사 도구(예: gitleaks)를 실행한다. GitHub 저장소에서는 secret scanning과 push protection을 켠다.
- CI 로그·실행 환경에서 가져온 자료를 추적 위치로 옮길 때는 [폴더 관리 계획](./folder_management.md)의 민감정보 확인 절차를 먼저 거친다.
- 비밀정보를 커밋했다면 이력 삭제보다 먼저 해당 키를 폐기·재발급한다.

**평가 정답이 분석 입력으로 새지 않게 한다.**

- 에이전트의 조회 도구는 분석 대상 저장소의 지정 커밋으로 범위를 고정한다. 수정 커밋과 이후 이력은 조회할 수 없어야 하며, 이 제한은 테스트로 검증한다.
- 서비스 저장소의 `evals/labels/`는 분석 실행 중 조회 도구의 허용 경로에 포함하지 않는다.
- 저장소를 공개하면 `evals/labels/`의 최종 평가 정답도 공개된다. 공개 전에 최종 평가 정답을 포함할지 결정하고, 제외한다면 결과 재현 방법과 함께 그 이유를 문서에 적는다.

**공개 전환 전에는 이력 전체를 점검한다.**

- [ ] 전체 이력에 대해 비밀정보 검사를 실행했다.
- [ ] 원본 로그, 개인 정보, 사용자 피드백의 실명이 이력에 없다.
- [ ] 대용량 파일이 이력에 남아 있지 않다.
- [ ] README에 실행 방법, 기준 문서 링크, 알려진 한계가 있다.
- [ ] `evals/labels/` 공개 범위를 결정했다.

**커밋 전에는 다음을 확인한다.**

- [ ] `git status`에서 `work/`, `.env`, 캐시, 대용량 파일이 보이지 않는다.
- [ ] 변경 내용이 하나의 목적이고 커밋 메시지가 형식을 따른다.
- [ ] 관련 테스트를 실행했고, 실패한 상태로 `main`에 병합하지 않는다.
- [ ] 평가 결과를 커밋한다면 결과표가 평가 태그와 실행 ID를 가리킨다.
- [ ] 폴더 구조나 추적 범위가 바뀌었다면 두 관리 문서를 함께 확인했다.
