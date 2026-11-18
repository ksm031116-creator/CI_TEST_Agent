**분석 보고서 형식**

작성일: 2026-11-19 · 관련 기능: F04 보고서 생성·검증

분석 방식 A/B/C는 모두 이 형식으로 보고서를 낸다. 데이터 모델은 `src/ci_failure_analyzer/report/schema.py`, 인용 검사는 `src/ci_failure_analyzer/report/citations.py`다. 분석 입력은 [입력 명세](./input_spec.md)를 따른다.

**보고서는 JSON 객체 하나다.**

| 필드 | 내용 | 조건 |
|---|---|---|
| `schema_version` | 형식 버전. 현재 `"1"` | |
| `conclusion` | `cause_candidate`, `insufficient_evidence`, `out_of_scope` 중 하나 | 필수 |
| `reason_code` | 분석하지 않은 사유 코드. 예: `no_junit` | `out_of_scope`에서만, 필수 |
| `observed_facts` | 입력에서 직접 확인한 사실. 각각 `statement`와 `evidence_ids`(1개 이상) | `out_of_scope` 외에는 1개 이상 |
| `cause_candidates` | 원인 후보. `summary`, `reasoning`, `confidence`(`low`/`medium`/`high`), `location`(파일·줄, 선택), `evidence_ids`(1개 이상) | `cause_candidate`에서는 1개 이상 |
| `evidence` | 근거 목록. 아래 표 참고 | |
| `verification_steps` | 사람이 원인을 확인할 방법. `description`, `command`(선택) | `out_of_scope` 외에는 1개 이상 |
| `limitations` | 입력만으로 알 수 없었던 것 | `insufficient_evidence`에서는 1개 이상 |

- 정의하지 않은 필드는 거부한다. 수정 패치 같은 범위 밖 내용을 넣지 못하게 하기 위해서다.
- `insufficient_evidence`에는 확신도 `high`인 후보를 둘 수 없다. 낮은 확신의 후보는 둘 수 있다.
- `out_of_scope`에는 원인 후보를 둘 수 없다.
- 사실과 후보가 가리키는 `evidence_ids`는 모두 `evidence`에 있어야 하고, 근거 ID는 중복될 수 없다.

**근거는 입력의 줄 범위와 그 원문을 함께 적는다.**

| 필드 | 내용 |
|---|---|
| `id` | 보고서 안에서 유일한 ID. 예: `E1` |
| `source` | `log`, `junit`, `code` |
| `path` | `log`는 `job.log`, `junit`은 `reports/junit.xml`, `code`는 코드 스냅샷 안의 경로 |
| `start_line`, `end_line` | 1부터 시작하는 줄 번호. 끝 줄 포함 |
| `quote` | 해당 줄 범위에서 그대로 옮긴 원문 |

- 로그의 원문은 작업·단계 이름, 타임스탬프, 색상 코드를 뗀 내용을 기준으로 한다. 줄 수는 원본과 같다([분석 방식](./analysis_methods.md)).
- 줄 번호는 줄바꿈 문자(`\n`)만으로 센다. 분석에 제공하는 본문과 인용 검사가 같은 함수로 줄을 나누므로 번호가 어긋나지 않는다.

**형식 검사와 인용 검사는 코드로 한다.**

| 검사 | 검출하는 것 |
|---|---|
| 형식 (`parse_report`) | JSON 오류, 필수 항목 누락, 빈 문자열, 정의되지 않은 필드·값, 결론 유형과 맞지 않는 구성. 위반을 한 번에 모두 알려 준다 |
| 인용 (`check_citations`) | `file_not_found` 묶음에 없는 파일 · `line_out_of_range` 파일 길이를 넘는 줄 · `quote_mismatch` 줄 범위에 없는 원문 · `not_in_context` 분석에 제공하지 않은 코드 파일 |

- 원문 비교는 공백을 정규화해서 한다. 들여쓰기와 줄바꿈 차이는 불일치로 보지 않고, 글자가 다르면 불일치다.
- `not_in_context`는 파일이 스냅샷에 실제로 있어도 검출한다. 방식 A(로그만)가 코드 줄을 인용하면 읽지 않은 내용을 지어낸 것이기 때문이다.
- 근거가 주장을 실제로 뒷받침하는지는 코드로 검사하지 않는다. 평가에서 사람이 확인한다.
- 검사에 실패한 보고서는 문제 목록을 알려 1회만 다시 요청하고, 또 실패하면 실패로 기록한다([분석 방식](./analysis_methods.md)).

**아직 정하지 않은 것**

- 보고서를 사람이 읽는 형태(Markdown, 웹 화면)로 바꾸는 방법은 F09에서 정한다.
