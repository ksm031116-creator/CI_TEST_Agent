**기준 분석 방식 A/B의 입력 구성**

작성일: 2026-11-19 · 관련 기능: F02 기준 분석 두 가지

이 문서는 방식 A와 B가 모델에 무엇을 제공하는지, 그리고 그 상한을 고정한다. 구현은 `src/ci_failure_analyzer/analysis/context.py`다. 보고서 형식은 [보고서 형식](./report_spec.md), 입력은 [입력 명세](./input_spec.md)를 따른다.

**두 방식은 제공하는 자료만 다르고 나머지는 같다.**

| 항목 | 방식 A | 방식 B |
|---|---|---|
| 실행 정보 | 워크플로, 이벤트, 브랜치, 작업과 단계별 결과, Python 버전 | A와 같음 |
| 실패 테스트 | JUnit XML의 실패·오류 테스트 ID와 메시지, 결과별 개수 | A와 같음 |
| 작업 로그 | 줄 번호를 붙인 로그 | A와 같음 |
| 코드 | 없음 | 아래 규칙으로 고른 파일. 줄 번호를 붙임 |
| 모델, 보고서 형식, 출력 상한 | `configs/analysis.toml` | A와 같음 |

- B의 입력은 A의 입력 뒤에 코드 부분을 덧붙인 것이다. 두 방식의 차이가 코드 제공 여부 하나가 되게 하기 위해서다.
- 커밋 메시지, 수정 커밋, 이후 이력, 정답 파일은 어느 방식에도 제공하지 않는다.

**방식 B의 파일 선택 규칙은 입력 묶음만 보고 결정한다.**

| 순서 | 고르는 파일 | 근거 |
|---|---|---|
| 1 | 실패·오류 테스트가 있는 테스트 파일 | JUnit XML의 테스트 ID |
| 2 | 그 테스트들의 traceback에 나온 저장소 안의 파일. 처음 나온 순서대로 | JUnit XML의 실패 상세 |
| 3 | 1번 파일과 같은 디렉터리의 `conftest.py` | 코드 스냅샷 |

- traceback의 경로는 코드 스냅샷에 있는 파일과 일치할 때만 고른다. 상대 경로는 스냅샷 경로와 같아야 한다. 절대 경로는 스냅샷 경로로 끝나야 하고, 설치된 라이브러리 경로(`site-packages` 등)는 제외한다.
- 규칙은 정답을 보지 않는다. 선택 함수의 입력은 묶음과 JUnit 결과뿐이고, 이 점을 테스트로 확인한다.
- 규칙이 원인 파일을 놓치는 사례가 있다(아래 표). 이것은 방식 B의 한계이며 방식 C(탐색 에이전트)와 비교할 대상이다. 결과를 보고 규칙을 고치지 않는다. 고친다면 이 문서에 사유와 날짜를 남긴다.

**자원 상한은 평가 전에 고정한다.**

| 항목 | 상한 | 넘으면 |
|---|---|---|
| 로그 | 1,500줄 | 실패한 단계의 줄만 남기고, 그중 마지막 1,500줄을 제공. 생략한 줄 수를 표시 |
| 코드 파일 수 | 10개 | 선택 순서대로 10개만 제공. 빠진 파일 이름을 표시 |
| 파일당 줄 수 | 400줄 | 앞 400줄만 제공. 생략한 줄 수를 표시 |
| 출력 토큰 | 8,000 | `configs/analysis.toml`의 `max_output_tokens` |

- 로그는 줄마다 작업·단계 이름, 타임스탬프, 색상 코드를 떼고 내용만 제공한다. 줄 수는 원본과 같아서 줄 번호가 원본 `job.log`의 줄 번호와 일치한다. 단계 이름은 단계가 바뀔 때 구분선으로 표시한다.
- 줄 번호는 인용 검사와 같은 기준으로 붙인다. 모델이 본 번호를 그대로 인용하면 검사를 통과한다.

**dev 사례에 규칙을 적용한 결과 (2026-11-19, 모델 호출 없음)**

| 사례 | 유형 | 고른 파일 | 원인 파일 | 포함 | 입력 크기 A / B (글자) |
|---|---|---|---|---|---|
| case-001 | `log_clear` | `test_catalog.py`, `catalog.py`, `conftest.py` | `catalog.py` | 예 | 22,545 / 25,778 |
| case-005 | `log_clear` | `test_catalog_data.py`, `test_loader.py`, `loader.py`, `conftest.py` | `loader.py` | 예 | 26,303 / 30,002 |
| case-006 | `log_clear` | `test_inventory.py`, `inventory.py`, `conftest.py` | `inventory.py` | 예 | 22,872 / 26,340 |
| case-002 | `needs_related_code` | `test_pricing.py`, `conftest.py` | `config.py` | 아니오 | 23,555 / 25,627 |
| case-007 | `needs_related_code` | `test_pricing.py`, `conftest.py` | `conftest.py` | 예 | 23,861 / 25,918 |
| case-008 | `needs_related_code` | `test_pricing.py`, `conftest.py` | `pricing.py` | 아니오 | 23,785 / 25,857 |
| case-003 | `distant_cause` | `test_orders.py`, `conftest.py` | `inventory.py` | 아니오 | 22,574 / 24,839 |
| case-009 | `distant_cause` | `test_orders.py`, `orders.py`, `inventory.py`, `conftest.py` | `orders.py` | 예 | 23,155 / 29,577 |
| case-010 | `distant_cause` | `test_orders.py`, `test_pricing.py`, `conftest.py` | `catalog.py` | 아니오 | 25,740 / 29,188 |
| case-004 | `insufficient_evidence` | `test_catalog_data.py`, `conftest.py` | 없음(외부 데이터) | 해당 없음 | 23,100 / 25,039 |
| case-011 | `insufficient_evidence` | `test_catalog_data.py`, `orders.py`, `catalog.py`, `conftest.py` | 없음(외부 데이터) | 해당 없음 | 23,022 / 28,581 |
| case-012 | `out_of_scope` | 분석하지 않음(`no_junit`) | `pyproject.toml` | - | - |

- 원인 파일이 코드에 있는 9건 중 규칙이 원인 파일을 포함한 것은 5건, 놓친 것은 4건이다. 놓친 4건은 모두 실패가 단언문에서 드러나 traceback에 테스트 파일만 나오는 사례다.
- 입력 크기의 대부분은 로그다(약 2만 2천~2만 6천 글자). 코드가 더하는 양은 2천~6천 글자다. 토큰 수는 첫 실제 호출에서 측정한다.
- 이 표는 `scripts/selection_coverage.py`로 만든다. 이 스크립트는 정답을 읽는 평가용 도구이고, 최종 평가 전에는 dev 분할에만 실행한다.

**API 비용 상한**

- 프로젝트 전체 API 비용 상한은 100달러다(2026-11-19 결정, `configs/analysis.toml`). 모든 모델 호출은 `analysis/budget.py`의 사용량 장부를 거친다.
- 호출 전에 최악의 경우 비용(입력 추정 상한 + 출력 상한)을 더해 상한을 넘으면 호출하지 않는다. 호출 후 실제 사용량을 `work/service_data/api_usage.jsonl`에 기록한다.
- 요금표에 없는 모델은 호출하지 않는다. 요금 기준일은 설정 파일에 적는다.
- 장부 파일은 Git에서 제외된 로컬 파일이다. 파일을 지우면 누적액이 0으로 돌아가므로 지우지 않는다. 계정 차원의 한도는 Anthropic Console의 사용 한도 설정으로 따로 걸어야 한다.

**아직 정하지 않은 것**

- 시스템 프롬프트와 지시문은 dev 사례로 조정하며 D4 이후에 고정한다.
- 형식·인용 검사에 실패한 응답의 재요청 횟수.
