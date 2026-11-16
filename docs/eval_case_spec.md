**평가 사례·정답 형식 (초안)**

작성일: 2026-11-17 · 관련 기능: F03 평가·재분석 실행기

평가 사례는 [입력 명세](./input_spec.md)의 입력 묶음 하나와 사람이 확인한 정답 하나로 구성한다. 폴더 구조와 누출 방지 원칙은 [폴더 관리 계획](../folder_management.md)을 따른다.

**사례 유형은 프로젝트 계획서의 네 가지 구성에 지원 범위 밖 유형을 더한다.**

| 코드 | 의미 | 기대하는 분석 결과 |
|---|---|---|
| `log_clear` | 로그만으로 원인이 명확한 실패 | 방식 A(로그만)로도 원인 후보 제시 |
| `needs_related_code` | 실패 위치 외의 함수·fixture·설정 확인이 필요한 실패 | 관련 코드를 본 경우에만 정확한 원인 |
| `distant_cause` | 오류가 드러난 위치와 원인 위치가 다른 실패 | 호출 관계를 따라가야 원인 도달 |
| `insufficient_evidence` | 입력 자료만으로 결론을 낼 수 없는 실패 | 판단 보류, 또는 확인 방법을 붙인 낮은 확신의 후보 |
| `out_of_scope` | 테스트 실행 전 단계의 실패 등 첫 버전이 분석하지 않는 실패 | 분석하지 않고 사유 코드 표시. 시스템 오류로 처리하지 않음 |

**`evals/cases/<case_id>/`에는 분석 입력만 둔다.**

| 파일 | 내용 |
|---|---|
| `metadata.json` | 사례 ID, 유형, 출처(`synthetic`/`real`), 입력 ID와 묶음 해시, 저장소·실행·작업 ID, `checkout_sha`, 실패 테스트, 로그만으로 풀릴지에 대한 예상, 포함 파일, 마스킹 여부 |
| `job.log`, `junit.xml` | 민감정보 검사를 마친 입력 사본 |

코드 스냅샷은 크기 때문에 복사하지 않는다. `checkout_sha`로 분석 대상 저장소에서 다시 만들 수 있다.

**`evals/labels/<case_id>.json`에는 정답과 채점 기준을 둔다.**

| 필드 | 내용 |
|---|---|
| `root_cause` | 원인 파일·줄(코드 밖 원인이면 `null`)과 한 문장 설명 |
| `fault_commit_message` | 실패를 만든 커밋 메시지. 분석 입력의 커밋 메시지가 오해를 유도하는지 확인하는 용도 |
| `acceptable_conclusions` | 허용하는 결론 유형: `cause_candidate`, `insufficient_evidence`, `out_of_scope` |
| `expected_reason_code` | `out_of_scope` 사례에서 기대하는 사유 코드. 예: `no_junit` |
| `accepted_candidates` | 정답으로 인정하는 원인 후보 설명 |
| `required_evidence` | 근거로 제시되어야 할 로그·코드 위치 |
| `incorrect_conclusions` | 오답으로 처리할 대표적인 결론 |
| `fix_summary` | 수정 방법. 분석 입력에는 넣지 않는다 |
| `notes` | 사례 수집 과정의 특이사항(선택) |

- 정답은 사람이 원인을 확인하고 재현한 결과로 작성한다. 모델 출력으로 정답을 만들지 않는다.
- 근거가 원인을 실제로 뒷받침하는지는 채점 시 사람이 확인한다. 파일·줄 존재 여부는 코드로 검사한다.

**`evals/splits/<split>.json`에 사례 ID 목록을 둔다.**

- `dev.json`: 개발·프롬프트 조정에 사용하는 사례
- `holdout.json`: 최종 평가에만 사용하는 사례. 아직 만들지 않았다
- 같은 결함의 변형은 같은 분할에 둔다. 사례 파일은 분할별로 복제하지 않는다.

**최종 평가용(holdout) 사례는 개발용과 결함이 겹치지 않게 만든다.**

- **시점:** 방식 A/B의 프롬프트와 B의 파일 선택 규칙을 dev 사례로 조정하기 전에 만든다. 만든 뒤에는 최종 평가 전까지 분석 결과를 보고 프롬프트를 고치는 데 쓰지 않는다.
- **수량:** 10개 내외. 유형별 2개 이상, `out_of_scope`는 1개.
- **결함 분리:** dev 사례와 같은 줄·같은 조건식·같은 설정값을 다시 쓰지 않는다. 같은 결함의 이름만 바꾼 변형도 만들지 않는다. dev와 같은 계열(예: 외부 데이터 변경)은 holdout에 넣지 않는다.
- **코드 분리:** 분석 대상 저장소에 새 모듈(쿠폰·배송비 등)을 추가하고, holdout 결함의 절반 이상을 dev 사례가 건드리지 않은 모듈에 둔다.
- **작성 순서:** 정답과 허용 결론을 먼저 적고 실패를 만든다. 실패가 예상과 다르게 드러나면 사례를 버리지 않고 메타데이터에 기록한다.
- **공개 범위:** holdout 정답도 이 저장소에 커밋한다. 분석 입력으로의 누출은 조회 도구의 범위 제한으로 막고, 공개 자체는 누출로 보지 않는다([Git 관리 계획](../git_management.md)).
- **사용 기록:** holdout 사례를 개발에 사용했다면 `splits/`와 커밋 메시지에 이유를 남기고 새 사례를 확보한다.

**현재 사례 (2026-11-18)**

| 사례 | 유형 | 실패 테스트 | 원인 위치 | 분할 |
|---|---|---|---|---|
| case-001 | `log_clear` | `test_free_product_allowed` | `catalog.py` 가격 검증 | dev |
| case-005 | `log_clear` | `test_loader.py` 2건, `test_reference_order_total` | `loader.py` 컬럼 이름 | dev |
| case-006 | `log_clear` | `test_commit_removes_from_on_hand` | `inventory.py` 속성 이름 | dev |
| case-002 | `needs_related_code` | `test_bulk_discount_applies_at_threshold` | `config.py` 기준 수량 | dev |
| case-007 | `needs_related_code` | `test_no_tax_for_exempt_product` | `conftest.py` fixture | dev |
| case-008 | `needs_related_code` | `test_bulk_discount_applies_at_threshold` | `pricing.py` 경계 조건 | dev |
| case-003 | `distant_cause` | `test_failed_order_releases_reservations` | `inventory.py` release | dev |
| case-009 | `distant_cause` | `test_too_many_items_rejected` | `orders.py` 상한 검사 | dev |
| case-010 | `distant_cause` | `test_order_totals`, `test_tax_for_taxable_product` | `catalog.py` 기본값 | dev |
| case-004 | `insufficient_evidence` | `test_reference_order_total` | 외부 데이터 가격 변경 | dev |
| case-011 | `insufficient_evidence` | `test_reference_order_total` | 외부 데이터 행 삭제 | dev |
| case-012 | `out_of_scope` | 없음 (JUnit XML 없음) | `pyproject.toml` 의존성 | dev |

- 12개 모두 의도적으로 만든 합성 사례(`synthetic`)이고, 각 실패 커밋은 변경 하나만 담는다. 실제 개발 중 발생한 실패는 아직 없다.
- case-002와 case-008은 로그 증상이 같고 원인이 다르다. case-004와 case-011은 같은 계열이다.
- case-005~010은 첫 실행이 아닌 재실행(`run_attempt` 2)에서 수집했다. 첫 실행에는 사례 011용으로 바꾼 테스트 데이터가 섞여 무관한 실패가 하나 더 있었다. 첫 실행의 입력 묶음은 `work/inputs/`에 남아 있고 사례로는 쓰지 않는다.
- case-001~004는 수동 수집, case-005~012는 수집기(`scripts/collect_run.py`)로 수집했다. 수집기로 001~004를 다시 수집해 묶음 해시가 같음을 확인했다.
