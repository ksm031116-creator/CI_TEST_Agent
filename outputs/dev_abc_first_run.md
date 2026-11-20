**dev 사례 A/B/C 첫 비교 (방식 C는 사례당 1회)**

실행일: 2026-11-23 · 대상: dev 12건 × 방식 C × 1회, 방식 A/B는 [반복 실행](./dev_ab_repeat_runs.md)의 3회 · 상태: **원인 일치 채점은 미검토**

방식 C(탐색 에이전트)를 dev 사례에 한 번씩 실행해 방식 A/B와 나란히 놓았다. 방식 C의 설계와 한도는 [방식 C 설계](../docs/agent_design.md), 채점은 [채점 기준](../docs/grading_spec.md) 버전 1을 따랐다. holdout 사례는 실행하지 않았다.

**1. 결과: 방식 C는 모델을 호출한 11건 모두 "일치"로 채점됐다. 방식 B가 일치에 못 미쳤던 세 사례(003, 008, 010)에서 원인 파일을 스스로 찾아 읽었다. 실행당 비용은 B의 약 2.3배다.**

| 항목 | A (3회) | B (3회) | C (1회) |
|---|---|---|---|
| 일치한 실행 | 20/36 | 28/36 | 12/12 |
| 모든 실행이 일치한 사례 | 6/12 | 9/12 | 12/12 |
| 결론 유형이 허용 범위 | 25/36 | 30/36 | 12/12 |
| 위치를 정답 줄(2줄 이내)로 적음 | 9/27 | 15/27 | 9/9 |
| 첫 응답이 검사를 통과 | 33/33 | 33/33 | 11/11 |
| 실행당 비용 | 0.097달러 | 0.106달러 | 0.238달러 |
| 실행당 최대 비용 | 0.114달러 | 0.122달러 | 0.386달러 |
| 소요 시간 중앙값 | 21.4초 | 24.2초 | 22.1초 |

- 이 비교는 같은 조건이 아니다. A/B는 사례당 3회, C는 1회다. C의 "12/12"는 한 번씩 실행해 얻은 것이라, 반복하면 달라질 수 있다.
- 12건 중 case-012는 범위 밖 사례라 세 방식 모두 모델을 호출하지 않는다.
- 채점은 분석을 만든 쪽이 했고 사람이 검토하지 않았다.

**2. 방식 C가 B와 달랐던 세 사례**

| 사례 | 정답 | 방식 B (3회) | 방식 C (1회) | C가 읽은 것 |
|---|---|---|---|---|
| case-003 | `Inventory.release`가 예약을 더함 | 부분 3. 규칙이 `inventory.py`를 고르지 못해 "롤백 누락 또는 재예약"으로 추정 | 일치. `inventory.py` 32행의 `+ quantity`를 인용 | 테스트, `orders.py`, `inventory.py` |
| case-008 | 할인 조건이 `>` | 부분 3. 추정은 맞았지만 `pricing.py`를 받지 못해 결론을 보류 | 일치. `pricing.py` 18행을 인용하고 원인 후보로 결론 | 테스트, `pricing.py`, 설정값 검색 |
| case-010 | `Product.taxable` 기본값이 False | 일치 1, 부분 2. `catalog.py`를 받지 못해 "기본값 또는 `Catalog`"로 묶음 | 일치. `catalog.py` 12행을 인용 | `conftest.py`, `catalog.py`, `pricing.py` |

- 세 사례 모두 방식 B의 한계는 규칙이 원인 파일을 고르지 못한 것이었다. 방식 C는 그 파일을 읽었고, 확신도 high로 원인 줄을 지목했다.
- 외부 데이터가 원인인 두 사례(004, 011)에서 방식 C는 코드를 5개, 4개 파일까지 읽은 뒤에도 "판단 보류"를 유지했다. 코드를 볼 수 있게 되었다고 없는 원인을 만들어 내지는 않았다.

**3. 탐색은 한도에 닿지 않았다. 11건 모두 모델이 스스로 탐색을 끝냈다.**

| 항목 | 값 | 한도 |
|---|---|---|
| 실행당 도구 호출 | 1~8회, 평균 4.0회 | 12회 |
| 실행당 모델 호출 | 2~5회, 평균 3.0회 | 8회 |
| 실행당 비용 | 0.149~0.386달러 | 0.60달러 |
| 거부된 도구 호출, 오류로 끝난 도구 호출 | 0 | |
| 정답에 코드 위치가 있는 9건 중 원인 줄을 도구로 본 실행 | 9 | |

- 도구 사용과 보고서 형식 강제는 한 호출에서 함께 동작했다. 보고서를 받는 호출을 따로 둘 필요가 없었다.
- 비용의 대부분은 입력이다. 방식 C의 입력 53만 토큰 가운데 약 34만 토큰(65%)은 같은 실행의 앞선 호출에서 이미 보낸 내용(로그와 그때까지의 대화)이다.
- 소요 시간은 A/B와 비슷하다. 도구를 부르는 응답은 출력이 짧아서 호출 수가 늘어도 시간이 크게 늘지 않았다.

**4. 평가 실행기 출력**

아래는 `scripts/evaluate.py --split dev`의 출력이다. 채점 기록은 `evals/gradings/`에 실행 ID별로 있다.

모델 `claude-opus-5-5` · effort `medium` · 프롬프트 A/B `v0` (`1d7b7066cb90`), C `v0-tools1` (`2d890462d567`) · 분할 `dev` · 실행 84건

**방식별 집계 (실행 단위)**

| 방식 | 실행 | 일치 | 부분 | 불일치 | 미채점 | 맞는 추정+보류 | high 오답 | 결론 유형 허용 | 위치: 줄 / 파일 / 다른 파일 / 없음 | 첫 응답 검사 통과 | 사람 검토 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 36 | 20 | 11 | 5 | 0 | 2 | 0 | 25/36 | 9 / 3 / 2 / 13 (대상 27) | 33/33 | 0/33 |
| B | 36 | 28 | 8 | 0 | 0 | 3 | 0 | 30/36 | 15 / 0 / 0 / 12 (대상 27) | 33/33 | 0/33 |
| C | 12 | 12 | 0 | 0 | 0 | 0 | 0 | 12/12 | 9 / 0 / 0 / 0 (대상 9) | 11/11 | 0/11 |

**방식별 집계 (사례 단위)**

| 방식 | 사례 | 모든 실행이 일치 | 일치가 과반 | 판정이 실행마다 같음 | 결론 유형이 실행마다 같음 | 1순위 후보가 실행마다 같음 |
|---|---|---|---|---|---|---|
| A | 12 | 6 | 6 | 9 | 11 | 9/11 |
| B | 12 | 9 | 9 | 11 | 12 | 10/11 |
| C | 12 | 12 | 12 | 12 | 12 | 11/11 |

**방식별 비용과 소요 시간**

| 방식 | 호출한 실행 | 모델 호출 | 도구 호출 | 입력 토큰 | 출력 토큰 | 비용($) | 실행당 비용($) | 실행당 최대($) | 소요 시간 중앙값(초) | 최대(초) |
|---|---|---|---|---|---|---|---|---|---|---|
| A | 33 | 33 | 0 | 458853 | 68804 | 3.2115 | 0.0973 | 0.1144 | 21.4 | 31.0 |
| B | 33 | 33 | 0 | 506040 | 73504 | 3.4942 | 0.1059 | 0.1223 | 24.2 | 33.0 |
| C | 11 | 33 | 44 | 533238 | 24429 | 2.6215 | 0.2383 | 0.3859 | 22.1 | 33.2 |

- 평균과 중앙값은 모델을 호출한 실행만 센다. 비용은 실행 기록의 값이고, 사용량 장부와 같은 요금표로 계산한 것이다.

**사례별 일치 수 (일치한 실행 / 실행)**

| 사례 | 유형 | A | B | C |
|---|---|---|---|---|
| case-001 | log_clear | 3/3 | 3/3 | 1/1 |
| case-002 | needs_related_code | 1/3 | 3/3 | 1/1 |
| case-003 | distant_cause | 0/3 | 0/3 | 1/1 |
| case-004 | insufficient_evidence | 3/3 | 3/3 | 1/1 |
| case-005 | log_clear | 3/3 | 3/3 | 1/1 |
| case-006 | log_clear | 3/3 | 3/3 | 1/1 |
| case-007 | needs_related_code | 0/3 | 3/3 | 1/1 |
| case-008 | needs_related_code | 1/3 | 0/3 | 1/1 |
| case-009 | distant_cause | 0/3 | 3/3 | 1/1 |
| case-010 | distant_cause | 0/3 | 1/3 | 1/1 |
| case-011 | insufficient_evidence | 3/3 | 3/3 | 1/1 |
| case-012 | out_of_scope | 3/3 | 3/3 | 1/1 |

**사례별 결과**

| 사례 | 유형 | 방식 | 판정 (실행 순) | 결론 (실행 순) | 1순위 후보 (실행 순) | 판정이 같은가 | 1순위 후보가 같은가 |
|---|---|---|---|---|---|---|---|
| case-001 | log_clear | A | 일치 / 일치 / 일치 | cause_candidate / cause_candidate / cause_candidate | price_check_le_zero / price_check_le_zero / price_check_le_zero | 예 | 예 |
| case-001 | log_clear | B | 일치 / 일치 / 일치 | cause_candidate / cause_candidate / cause_candidate | price_check_le_zero / price_check_le_zero / price_check_le_zero | 예 | 예 |
| case-001 | log_clear | C | 일치 | cause_candidate | price_check_le_zero | 예 | 예 |
| case-002 | needs_related_code | A | 부분 / 일치 / 부분 | cause_candidate / cause_candidate / cause_candidate | threshold_20_test_side / threshold_20_neutral / threshold_20_test_side | **아니오** | **아니오** |
| case-002 | needs_related_code | B | 일치 / 일치 / 일치 | cause_candidate / cause_candidate / cause_candidate | config_default_threshold_20 / config_default_threshold_20 / config_default_threshold_20 | 예 | 예 |
| case-002 | needs_related_code | C | 일치 | cause_candidate | config_default_threshold_20 | 예 | 예 |
| case-003 | distant_cause | A | 부분 / 불일치 / 불일치 | insufficient_evidence / insufficient_evidence / insufficient_evidence | rollback_missing / rollback_missing / rollback_missing | **아니오** | 예 |
| case-003 | distant_cause | B | 부분 / 부분 / 부분 | insufficient_evidence / insufficient_evidence / insufficient_evidence | rollback_missing_or_rereserve / rollback_missing_or_rereserve / rollback_missing_or_rereserve | 예 | 예 |
| case-003 | distant_cause | C | 일치 | cause_candidate | release_sign_error | 예 | 예 |
| case-004 | insufficient_evidence | A | 일치 / 일치 / 일치 | insufficient_evidence / insufficient_evidence / insufficient_evidence | external_price_data / external_price_data / external_price_data | 예 | 예 |
| case-004 | insufficient_evidence | B | 일치 / 일치 / 일치 | insufficient_evidence / insufficient_evidence / insufficient_evidence | external_price_data / external_price_data / external_price_data | 예 | 예 |
| case-004 | insufficient_evidence | C | 일치 | insufficient_evidence | external_price_data | 예 | 예 |
| case-005 | log_clear | A | 일치 / 일치 / 일치 | cause_candidate / cause_candidate / cause_candidate | column_name_typo / column_name_typo / column_name_typo | 예 | 예 |
| case-005 | log_clear | B | 일치 / 일치 / 일치 | cause_candidate / cause_candidate / cause_candidate | column_name_typo / column_name_typo / column_name_typo | 예 | 예 |
| case-005 | log_clear | C | 일치 | cause_candidate | column_name_typo | 예 | 예 |
| case-006 | log_clear | A | 일치 / 일치 / 일치 | cause_candidate / cause_candidate / cause_candidate | attribute_name_typo / attribute_name_typo / attribute_name_typo | 예 | 예 |
| case-006 | log_clear | B | 일치 / 일치 / 일치 | cause_candidate / cause_candidate / cause_candidate | attribute_name_typo / attribute_name_typo / attribute_name_typo | 예 | 예 |
| case-006 | log_clear | C | 일치 | cause_candidate | attribute_name_typo | 예 | 예 |
| case-007 | needs_related_code | A | 부분 / 부분 / 부분 | insufficient_evidence / insufficient_evidence / insufficient_evidence | external_data_taxable / external_data_taxable / external_data_taxable | 예 | 예 |
| case-007 | needs_related_code | B | 일치 / 일치 / 일치 | cause_candidate / cause_candidate / cause_candidate | fixture_milk_not_exempt / fixture_milk_not_exempt / fixture_milk_not_exempt | 예 | 예 |
| case-007 | needs_related_code | C | 일치 | cause_candidate | fixture_milk_not_exempt | 예 | 예 |
| case-008 | needs_related_code | A | 부분 / 부분 / 일치 | insufficient_evidence / insufficient_evidence / cause_candidate | boundary_gt / boundary_gt / boundary_gt | **아니오** | 예 |
| case-008 | needs_related_code | B | 부분 / 부분 / 부분 | insufficient_evidence / insufficient_evidence / insufficient_evidence | boundary_gt / boundary_gt / boundary_gt | 예 | 예 |
| case-008 | needs_related_code | C | 일치 | cause_candidate | boundary_gt | 예 | 예 |
| case-009 | distant_cause | A | 부분 / 부분 / 부분 | cause_candidate / cause_candidate / cause_candidate | limit_check_late_or_missing / limit_check_after_reserve / limit_check_late_or_missing | 예 | **아니오** |
| case-009 | distant_cause | B | 일치 / 일치 / 일치 | cause_candidate / cause_candidate / cause_candidate | limit_check_len_items / limit_check_len_items / limit_check_len_items | 예 | 예 |
| case-009 | distant_cause | C | 일치 | cause_candidate | limit_check_len_items | 예 | 예 |
| case-010 | distant_cause | A | 불일치 / 불일치 / 불일치 | insufficient_evidence / insufficient_evidence / insufficient_evidence | external_data_taxable / external_data_taxable / external_data_taxable | 예 | 예 |
| case-010 | distant_cause | B | 부분 / 일치 / 부분 | cause_candidate / cause_candidate / cause_candidate | product_default_or_catalog / product_default_false / product_default_or_catalog | **아니오** | **아니오** |
| case-010 | distant_cause | C | 일치 | cause_candidate | product_default_false | 예 | 예 |
| case-011 | insufficient_evidence | A | 일치 / 일치 / 일치 | insufficient_evidence / insufficient_evidence / insufficient_evidence | external_data_missing_b200 / external_data_missing_b200 / external_data_missing_b200 | 예 | 예 |
| case-011 | insufficient_evidence | B | 일치 / 일치 / 일치 | insufficient_evidence / insufficient_evidence / insufficient_evidence | external_data_missing_b200 / external_data_missing_b200 / external_data_missing_b200 | 예 | 예 |
| case-011 | insufficient_evidence | C | 일치 | insufficient_evidence | external_data_missing_b200 | 예 | 예 |
| case-012 | out_of_scope | A | 일치 / 일치 / 일치 | out_of_scope / out_of_scope / out_of_scope | - / - / - | 예 | - |
| case-012 | out_of_scope | B | 일치 / 일치 / 일치 | out_of_scope / out_of_scope / out_of_scope | - / - / - | 예 | - |
| case-012 | out_of_scope | C | 일치 | out_of_scope | - | 예 | - |

- 판정 뒤의 `*`는 사람이 검토한 판정이다. 표시가 없으면 1차 채점자의 판정이거나 코드가 정한 판정이다.

**탐색 기록 (도구를 쓰는 방식의 실행)**

| 사례 | 실행 ID | 모델 호출 | 도구 호출 (거부) | 읽은 파일 | 원인 파일을 읽음 | 원인 줄을 봄 | 닿은 한도 | 비용($) | 소요 시간(초) |
|---|---|---|---|---|---|---|---|---|---|
| case-001 | `20261120-153940_C_case-001` | 2 | 2 (0) | 2 | 예 | 예 | - | 0.1535 | 17.2 |
| case-002 | `20261120-153958_C_case-002` | 5 | 8 (0) | 4 | 예 | 예 | - | 0.3859 | 24.9 |
| case-003 | `20261120-154023_C_case-003` | 3 | 4 (0) | 3 | 예 | 예 | - | 0.2343 | 20.7 |
| case-004 | `20261120-154043_C_case-004` | 4 | 7 (0) | 5 | - | - | - | 0.3267 | 33.2 |
| case-005 | `20261120-154117_C_case-005` | 2 | 2 (0) | 2 | 예 | 예 | - | 0.1684 | 16.1 |
| case-006 | `20261120-154133_C_case-006` | 2 | 1 (0) | 1 | 예 | 예 | - | 0.1490 | 14.7 |
| case-007 | `20261120-154148_C_case-007` | 3 | 5 (0) | 4 | 예 | 예 | - | 0.2377 | 21.4 |
| case-008 | `20261120-154209_C_case-008` | 4 | 4 (0) | 3 | 예 | 예 | - | 0.2989 | 22.1 |
| case-009 | `20261120-153901_C_case-009` | 2 | 2 (0) | 2 | 예 | 예 | - | 0.1631 | 22.2 |
| case-010 | `20261120-154231_C_case-010` | 3 | 4 (0) | 3 | 예 | 예 | - | 0.2555 | 23.8 |
| case-011 | `20261120-154255_C_case-011` | 3 | 5 (0) | 4 | - | - | - | 0.2486 | 25.7 |

- 원인 파일과 줄은 정답 레이블의 위치다. 레이블에 코드 위치가 없는 사례는 `-`로 적는다.
- 닿은 한도: `tool_calls`(도구 호출), `model_calls`(모델 호출), `cost`(실행당 비용). `-`는 모델이 스스로 탐색을 끝낸 실행이다.

**5. 이 결과의 한계**

- **방식 C는 사례당 1회다.** A/B는 같은 입력에서도 실행마다 판정이 달라진 사례가 있었다(A 3건, B 1건). C의 변동은 아직 재지 않았다.
- **채점이 미검토다.** 방식 C의 11건도 분석을 만든 쪽이 채점했다. case-002는 경계 판정이다. 보고서가 설정의 기준 수량 20을 원인 위치로 지목했지만 "설정과 테스트 중 어느 쪽이 의도인지는 알 수 없다"고 적었다. 같은 설명을 한 방식 B의 판정(일치)에 맞췄다.
- **dev 저장소가 작다.** 파일이 20~65줄이라 파일 하나를 한 번에 읽을 수 있고, 관련 파일이 서너 개뿐이다. 한도에 닿은 실행이 없었으므로 한도가 실제로 어떻게 작동하는지, 큰 저장소에서 탐색이 얼마나 드는지는 이 결과로 알 수 없다.
- **프롬프트의 문장이 결과에 섞여 있다.** 방식 C의 프롬프트에는 "읽을 수 있는 파일을 읽지 않은 것은 판단 보류의 사유가 아니다"라는 문장이 있다. case-008에서 결론이 보류에서 원인 후보로 바뀐 것이 코드를 읽은 효과인지 이 문장의 효과인지는 가르지 못한다. 다만 004와 011에서는 보류를 유지했다.
- **근거가 주장을 뒷받침하는지는 방식 C에 대해 점검하지 않았다.** 인용한 줄이 존재하고 도구가 보여 준 줄이라는 것만 코드로 확인했다.
- **dev 사례는 방식과 프롬프트를 만드는 동안 본 사례다.** 최종 수치는 holdout에서 낸다.
