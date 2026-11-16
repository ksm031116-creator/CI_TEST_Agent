**평가 사례·정답 형식 (초안)**

작성일: 2026-11-17 · 관련 기능: F03 평가·재분석 실행기

평가 사례는 [입력 명세](./input_spec.md)의 입력 묶음 하나와 사람이 확인한 정답 하나로 구성한다. 폴더 구조와 누출 방지 원칙은 [폴더 관리 계획](../folder_management.md)을 따른다.

**사례 유형은 프로젝트 계획서의 네 가지 구성을 따른다.**

| 코드 | 의미 | 기대하는 분석 결과 |
|---|---|---|
| `log_clear` | 로그만으로 원인이 명확한 실패 | 방식 A(로그만)로도 원인 후보 제시 |
| `needs_related_code` | 실패 위치 외의 함수·fixture·설정 확인이 필요한 실패 | 관련 코드를 본 경우에만 정확한 원인 |
| `distant_cause` | 오류가 드러난 위치와 원인 위치가 다른 실패 | 호출 관계를 따라가야 원인 도달 |
| `insufficient_evidence` | 입력 자료만으로 결론을 낼 수 없는 실패 | 판단 보류, 또는 확인 방법을 붙인 낮은 확신의 후보 |

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

**현재 사례 (2026-11-17)**

| 사례 | 유형 | 실패 테스트 | 분할 |
|---|---|---|---|
| case-001 | `log_clear` | `test_catalog.py::test_free_product_allowed` | dev |
| case-002 | `needs_related_code` | `test_pricing.py::test_bulk_discount_applies_at_threshold` | dev |
| case-003 | `distant_cause` | `test_orders.py::test_failed_order_releases_reservations` | dev |
| case-004 | `insufficient_evidence` | `test_catalog_data.py::test_reference_order_total` | dev |

네 사례 모두 의도적으로 만든 합성 사례(`synthetic`)이고, 각 사례의 실패 커밋은 하나의 변경만 담는다. 실제 개발 중 발생한 실패는 아직 없다.
