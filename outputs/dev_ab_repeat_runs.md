**dev 사례 A/B 반복 실행 결과 (프롬프트 v0, 사례·방식당 3회)**

실행일: 2026-11-18 · 대상: dev 12건 × 방식 A/B × 3회 · 상태: **원인 일치 채점은 미검토**

[1차 실행](./dev_ab_first_run.md)과 같은 입력·모델·프롬프트로 2회를 더 실행해, 결과가 실행마다 얼마나 달라지는지 쟀다. 채점은 [채점 기준](../docs/grading_spec.md) 버전 1을 따랐고, 1차 실행의 판정도 이 기준으로 다시 매겼다. holdout 사례는 실행하지 않았다.

**1. 집계: 일치는 A 36회 중 20회, B 36회 중 28회다. 판정이 3회 모두 같은 사례는 A 9건, B 11건이다(12건 중).**

아래 표는 `scripts/evaluate.py --split dev`의 출력이다. 채점 기록은 `evals/gradings/`에 실행 ID별로 있다.

모델 `claude-opus-5-5` · effort `medium` · 프롬프트 `v0` (`1d7b7066cb90`) · 분할 `dev` · 실행 72건

**방식별 집계 (실행 단위)**

| 방식 | 실행 | 일치 | 부분 | 불일치 | 미채점 | 맞는 추정+보류 | high 오답 | 결론 유형 허용 | 위치: 줄 / 파일 / 다른 파일 / 없음 | 첫 응답 검사 통과 | 사람 검토 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 36 | 20 | 11 | 5 | 0 | 2 | 0 | 25/36 | 9 / 3 / 2 / 13 (대상 27) | 33/33 | 0/33 |
| B | 36 | 28 | 8 | 0 | 0 | 3 | 0 | 30/36 | 15 / 0 / 0 / 12 (대상 27) | 33/33 | 0/33 |

**방식별 집계 (사례 단위)**

| 방식 | 사례 | 모든 실행이 일치 | 일치가 과반 | 판정이 실행마다 같음 | 결론 유형이 실행마다 같음 | 1순위 후보가 실행마다 같음 |
|---|---|---|---|---|---|---|
| A | 12 | 6 | 6 | 9 | 11 | 9/11 |
| B | 12 | 9 | 9 | 11 | 12 | 10/11 |

**사례별 결과**

| 사례 | 유형 | 방식 | 판정 (실행 순) | 결론 (실행 순) | 1순위 후보 (실행 순) | 판정이 같은가 | 1순위 후보가 같은가 |
|---|---|---|---|---|---|---|---|
| case-001 | log_clear | A | 일치 / 일치 / 일치 | cause_candidate / cause_candidate / cause_candidate | price_check_le_zero / price_check_le_zero / price_check_le_zero | 예 | 예 |
| case-001 | log_clear | B | 일치 / 일치 / 일치 | cause_candidate / cause_candidate / cause_candidate | price_check_le_zero / price_check_le_zero / price_check_le_zero | 예 | 예 |
| case-002 | needs_related_code | A | 부분 / 일치 / 부분 | cause_candidate / cause_candidate / cause_candidate | threshold_20_test_side / threshold_20_neutral / threshold_20_test_side | **아니오** | **아니오** |
| case-002 | needs_related_code | B | 일치 / 일치 / 일치 | cause_candidate / cause_candidate / cause_candidate | config_default_threshold_20 / config_default_threshold_20 / config_default_threshold_20 | 예 | 예 |
| case-003 | distant_cause | A | 부분 / 불일치 / 불일치 | insufficient_evidence / insufficient_evidence / insufficient_evidence | rollback_missing / rollback_missing / rollback_missing | **아니오** | 예 |
| case-003 | distant_cause | B | 부분 / 부분 / 부분 | insufficient_evidence / insufficient_evidence / insufficient_evidence | rollback_missing_or_rereserve / rollback_missing_or_rereserve / rollback_missing_or_rereserve | 예 | 예 |
| case-004 | insufficient_evidence | A | 일치 / 일치 / 일치 | insufficient_evidence / insufficient_evidence / insufficient_evidence | external_price_data / external_price_data / external_price_data | 예 | 예 |
| case-004 | insufficient_evidence | B | 일치 / 일치 / 일치 | insufficient_evidence / insufficient_evidence / insufficient_evidence | external_price_data / external_price_data / external_price_data | 예 | 예 |
| case-005 | log_clear | A | 일치 / 일치 / 일치 | cause_candidate / cause_candidate / cause_candidate | column_name_typo / column_name_typo / column_name_typo | 예 | 예 |
| case-005 | log_clear | B | 일치 / 일치 / 일치 | cause_candidate / cause_candidate / cause_candidate | column_name_typo / column_name_typo / column_name_typo | 예 | 예 |
| case-006 | log_clear | A | 일치 / 일치 / 일치 | cause_candidate / cause_candidate / cause_candidate | attribute_name_typo / attribute_name_typo / attribute_name_typo | 예 | 예 |
| case-006 | log_clear | B | 일치 / 일치 / 일치 | cause_candidate / cause_candidate / cause_candidate | attribute_name_typo / attribute_name_typo / attribute_name_typo | 예 | 예 |
| case-007 | needs_related_code | A | 부분 / 부분 / 부분 | insufficient_evidence / insufficient_evidence / insufficient_evidence | external_data_taxable / external_data_taxable / external_data_taxable | 예 | 예 |
| case-007 | needs_related_code | B | 일치 / 일치 / 일치 | cause_candidate / cause_candidate / cause_candidate | fixture_milk_not_exempt / fixture_milk_not_exempt / fixture_milk_not_exempt | 예 | 예 |
| case-008 | needs_related_code | A | 부분 / 부분 / 일치 | insufficient_evidence / insufficient_evidence / cause_candidate | boundary_gt / boundary_gt / boundary_gt | **아니오** | 예 |
| case-008 | needs_related_code | B | 부분 / 부분 / 부분 | insufficient_evidence / insufficient_evidence / insufficient_evidence | boundary_gt / boundary_gt / boundary_gt | 예 | 예 |
| case-009 | distant_cause | A | 부분 / 부분 / 부분 | cause_candidate / cause_candidate / cause_candidate | limit_check_late_or_missing / limit_check_after_reserve / limit_check_late_or_missing | 예 | **아니오** |
| case-009 | distant_cause | B | 일치 / 일치 / 일치 | cause_candidate / cause_candidate / cause_candidate | limit_check_len_items / limit_check_len_items / limit_check_len_items | 예 | 예 |
| case-010 | distant_cause | A | 불일치 / 불일치 / 불일치 | insufficient_evidence / insufficient_evidence / insufficient_evidence | external_data_taxable / external_data_taxable / external_data_taxable | 예 | 예 |
| case-010 | distant_cause | B | 부분 / 일치 / 부분 | cause_candidate / cause_candidate / cause_candidate | product_default_or_catalog / product_default_false / product_default_or_catalog | **아니오** | **아니오** |
| case-011 | insufficient_evidence | A | 일치 / 일치 / 일치 | insufficient_evidence / insufficient_evidence / insufficient_evidence | external_data_missing_b200 / external_data_missing_b200 / external_data_missing_b200 | 예 | 예 |
| case-011 | insufficient_evidence | B | 일치 / 일치 / 일치 | insufficient_evidence / insufficient_evidence / insufficient_evidence | external_data_missing_b200 / external_data_missing_b200 / external_data_missing_b200 | 예 | 예 |
| case-012 | out_of_scope | A | 일치 / 일치 / 일치 | out_of_scope / out_of_scope / out_of_scope | - / - / - | 예 | - |
| case-012 | out_of_scope | B | 일치 / 일치 / 일치 | out_of_scope / out_of_scope / out_of_scope | - / - / - | 예 | - |

- 판정 뒤의 `*`는 사람이 검토한 판정이다. 표시가 없으면 1차 채점자의 판정이거나 코드가 정한 판정이다.

- 1순위 후보 열의 이름은 채점자가 붙인 것이다. 같은 사례·방식에서 같은 설명이면 같은 이름이다.
- 추가 실행 44회 호출은 모두 첫 응답에서 형식·인용 검사를 통과했다. 재요청과 잘린 응답은 없었다.
- 추가 실행은 모두 커밋 `3f95387`의 변경 없는 작업 폴더에서 했다. 비용은 4.49달러이고, 장부 누적액은 6.90달러다.

**2. 실행마다 달라진 것**

| 사례·방식 | 달라진 것 | 판정 |
|---|---|---|
| case-002 A | 같은 설명("기준 수량 20이 테스트의 전제와 다르다")인데 위치를 테스트 파일로 적은 실행이 2회, 적지 않은 실행이 1회 | 부분 / 일치 / 부분 |
| case-003 A | 1순위는 3회 모두 롤백 누락(오답). 1회만 낮은 확신의 2순위로 `Inventory` 구현 오류를 덧붙임 | 부분 / 불일치 / 불일치 |
| case-008 A | 추정은 3회 모두 같고 맞다. 결론 유형이 보류 2회, 원인 후보 1회 | 부분 / 부분 / 일치 |
| case-009 A | 판정은 같다. "검사가 예약보다 늦다"와 "늦거나 없다"로 설명이 조금 달랐다 | 부분 / 부분 / 부분 |
| case-010 B | `Product` 기본값만 지목한 실행이 1회, "또는 `Catalog`가 값을 바꾼다"를 붙인 실행이 2회 | 부분 / 일치 / 부분 |

- 결론 유형이 바뀐 것은 72회 중 case-008 A의 1회뿐이다.
- 1순위 후보가 가리키는 방향이 뒤집힌 사례는 없다. 달라진 것은 표현의 범위(대안을 붙였는지, 위치를 적었는지)와 낮은 확신의 추가 후보다.
- 판정이 갈린 4건 중 2건(002 A, 010 B)은 채점 기준의 경계에 걸린 것이다. 기준을 다르게 잡으면 "판정이 같음"의 수가 달라진다.

**3. 1차 채점(D4)과 달라진 판정**

1차 실행 24건을 기준 버전 1로 다시 매기면서 2건이 바뀌었다.

| 실행 | D4 판정 | 지금 판정 | 이유 |
|---|---|---|---|
| case-003 B (1회차) | 불일치 | 부분 | 요약은 롤백 누락이지만 추론에 "해제 경로가 release 대신 reserve를 부를 가능성"이 있다. 기준은 요약과 추론을 함께 읽는다 |
| case-010 B (1회차) | 일치 | 부분 | 서로 다른 대상을 "또는"으로 묶은 후보는 `unspecified`로 본다 |

1차 실행만 보면 A는 일치 6 / 부분 5 / 불일치 1 그대로이고, B는 일치 10 / 부분 1 / 불일치 1에서 일치 9 / 부분 3 / 불일치 0이 된다.

**4. 보인 것 (미검토)**

- 확신 high로 틀린 후보는 66회 호출에서 한 번도 없었다.
- B는 불일치가 없다. A의 불일치 5회는 모두 원인이 드러난 곳과 떨어져 있는 사례(003, 010)에서 나왔다.
- B가 일치에 못 미친 8회는 모두 원인 파일을 받지 못한 사례(003, 008, 010)다. 원인 파일을 받은 5건은 15회 모두 일치다.
- "맞는 추정 + 보류"는 5회이고 모두 case-008이다. 코드를 보지 못하면 추정이 맞아도 보류로 결론 내는 경향이 있다.
- A는 로그에 드러난 줄 번호만으로 위치를 9회 맞혔다(log_clear 3건 × 3회).

**5. 이 결과의 한계**

- 채점자가 분석을 만든 쪽이고, 사람이 검토한 판정이 아직 없다. 검토 요청 자료는 [dev_grading_review.md](./dev_grading_review.md)다.
- 3회는 변동의 크기를 어림하는 데는 쓸 수 있지만 비율을 주장하기에는 적다.
- dev 12건은 프롬프트를 쓴 쪽이 만든 사례다.
- 근거가 주장을 실제로 뒷받침하는지는 확인하지 않았다.
