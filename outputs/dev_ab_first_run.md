**dev 사례 A/B 1차 실행 결과 (프롬프트 v0)**

실행일: 2026-11-18 · 대상: dev 12건 × 방식 A/B · 상태: **원인 일치 채점은 미검토**

방식 A는 로그만, 방식 B는 로그와 규칙으로 고른 코드를 받는다([분석 방식](../docs/analysis_methods.md)). 프롬프트는 결과를 보기 전에 쓴 v0 그대로다. holdout 사례는 실행하지 않았다.

**1. 코드로 판정한 결과: 22회 호출이 모두 첫 응답에서 형식·인용 검사를 통과했다.**

이 표는 `scripts/summarize_runs.py --split dev`의 출력이다. 실행 ID는 `work/runs/`의 폴더 이름이다.

모델 `claude-opus-5-5` · effort `medium` · 프롬프트 `v0` (`1d7b7066cb90`)

| 사례 | 유형 | 방식 | 상태 | 결론 | 호출 | 형식(1차) | 인용(1차) | 코드 파일 | 입력 토큰 | 출력 토큰 | 비용($) | 실행 ID |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| case-001 | log_clear | A | ok | cause_candidate | 1 | 통과 | 통과 | 0 | 13434 | 1565 | 0.0850 | `20261118-105816_A_case-001` |
| case-001 | log_clear | B | ok | cause_candidate | 1 | 통과 | 통과 | 3 | 14814 | 1909 | 0.0974 | `20261118-105838_B_case-001` |
| case-002 | needs_related_code | A | ok | cause_candidate | 1 | 통과 | 통과 | 0 | 13839 | 2133 | 0.0980 | `20261118-105901_A_case-002` |
| case-002 | needs_related_code | B | ok | cause_candidate | 1 | 통과 | 통과 | 2 | 14787 | 2784 | 0.1148 | `20261118-105920_B_case-002` |
| case-003 | distant_cause | A | ok | insufficient_evidence | 1 | 통과 | 통과 | 0 | 13431 | 2217 | 0.0981 | `20261118-105953_A_case-003` |
| case-003 | distant_cause | B | ok | insufficient_evidence | 1 | 통과 | 통과 | 2 | 14439 | 2414 | 0.1060 | `20261118-110014_B_case-003` |
| case-004 | insufficient_evidence | A | ok | insufficient_evidence | 1 | 통과 | 통과 | 0 | 13571 | 2358 | 0.1014 | `20261118-110036_A_case-004` |
| case-004 | insufficient_evidence | B | ok | insufficient_evidence | 1 | 통과 | 통과 | 2 | 14427 | 2394 | 0.1056 | `20261118-110057_B_case-004` |
| case-005 | log_clear | A | ok | cause_candidate | 1 | 통과 | 통과 | 0 | 15072 | 1537 | 0.0910 | `20261118-110118_A_case-005` |
| case-005 | log_clear | B | ok | cause_candidate | 1 | 통과 | 통과 | 4 | 16689 | 1512 | 0.0970 | `20261118-110132_B_case-005` |
| case-006 | log_clear | A | ok | cause_candidate | 1 | 통과 | 통과 | 0 | 13538 | 1391 | 0.0820 | `20261118-110145_A_case-006` |
| case-006 | log_clear | B | ok | cause_candidate | 1 | 통과 | 통과 | 3 | 15034 | 1439 | 0.0889 | `20261118-110157_B_case-006` |
| case-007 | needs_related_code | A | ok | insufficient_evidence | 1 | 통과 | 통과 | 0 | 13914 | 2183 | 0.0993 | `20261118-110215_A_case-007` |
| case-007 | needs_related_code | B | ok | cause_candidate | 1 | 통과 | 통과 | 2 | 14856 | 2144 | 0.1023 | `20261118-110234_B_case-007` |
| case-008 | needs_related_code | A | ok | insufficient_evidence | 1 | 통과 | 통과 | 0 | 13885 | 2379 | 0.1031 | `20261118-110301_A_case-008` |
| case-008 | needs_related_code | B | ok | insufficient_evidence | 1 | 통과 | 통과 | 2 | 14833 | 2215 | 0.1036 | `20261118-110331_B_case-008` |
| case-009 | distant_cause | A | ok | cause_candidate | 1 | 통과 | 통과 | 0 | 13721 | 2223 | 0.0993 | `20261118-110357_A_case-009` |
| case-009 | distant_cause | B | ok | cause_candidate | 1 | 통과 | 통과 | 4 | 16415 | 2405 | 0.1138 | `20261118-110424_B_case-009` |
| case-010 | distant_cause | A | ok | insufficient_evidence | 1 | 통과 | 통과 | 0 | 14873 | 2569 | 0.1109 | `20261118-110452_A_case-010` |
| case-010 | distant_cause | B | ok | cause_candidate | 1 | 통과 | 통과 | 3 | 16426 | 2600 | 0.1177 | `20261118-110514_B_case-010` |
| case-011 | insufficient_evidence | A | ok | insufficient_evidence | 1 | 통과 | 통과 | 0 | 13673 | 1880 | 0.0923 | `20261118-110539_A_case-011` |
| case-011 | insufficient_evidence | B | ok | insufficient_evidence | 1 | 통과 | 통과 | 4 | 15960 | 2154 | 0.1069 | `20261118-110602_B_case-011` |
| case-012 | out_of_scope | A | ok | out_of_scope (no_junit) | 0 | - | - | - | 0 | 0 | 0.0000 | `20261118-110628_A_case-012` |
| case-012 | out_of_scope | B | ok | out_of_scope (no_junit) | 0 | - | - | - | 0 | 0 | 0.0000 | `20261118-110628_B_case-012` |

모델 호출 22회 · 비용 합계 $2.2146 · 요금 기준일 2026-11-03 · 코드 커밋 14e8ce7, 14e8ce7+dirty

- 재요청은 한 번도 없었다. 출력 상한(8,000 토큰)에서 잘린 응답도 없다. 출력은 호출당 1,391~2,784 토큰이었다.
- 입력은 호출당 13,400~16,700 토큰이다. 계획서의 추정(1만)보다 약 1.4~1.7배 많았고, 중단 기준(2배)은 넘지 않았다.
- 호출당 비용은 평균 약 0.10달러다(계획서 추정 0.12달러).
- 코드 커밋의 `+dirty`는 실행 중 작업 폴더에 아직 커밋하지 않은 `scripts/summarize_runs.py`가 있었기 때문이다. 분석에 쓰이는 코드와 설정은 `14e8ce7`과 같다.
- 이 표에 없는 호출이 2회 있다. 브랜치 이름을 가리기 전에 case-009를 A/B로 한 번씩 실행한 것으로(0.19달러), 입력에 정답 힌트가 들어 있어 결과에서 뺐다. 장부 누적액은 이 2회를 포함해 2.41달러다.

**2. 원인 일치 1차 채점 (미검토)**

분석을 만든 쪽(Claude)이 정답(`evals/labels/`)과 보고서를 대조해 매긴 것이다. 사람이 확인하기 전까지는 결과로 인용하지 않는다.

채점 기준은 이 표를 만들면서 임시로 정했다.

- **일치**: 가장 확신이 높은 후보가 정답의 원인과 같다. 정답이 판단 보류를 허용하는 사례는 허용된 결론과 후보, 확인 방법을 냈다.
- **부분**: 정답 원인이 후보에 있으나 위치나 작동 방식을 특정하지 못했거나, 더 낮은 확신의 후보로만 있다.
- **불일치**: 정답 원인이 후보에 없다.

| 사례 | 유형 | B가 원인 파일을 받았나 | A | B | 메모 |
|---|---|---|---|---|---|
| case-001 | log_clear | 예 | 일치 | 일치 | 둘 다 `catalog.py:24`, 확신 high |
| case-002 | needs_related_code | 아니오 | 부분 | 일치 | A는 기준 수량 불일치를 짚었으나 위치를 테스트 파일로 지정. B는 기본 설정값 20을 원인으로 지목(위치 없음) |
| case-003 | distant_cause | 아니오 | 부분 | 불일치 | 둘 다 보류. A는 `release` 로직 오류를 낮은 확신 후보로 포함. B의 유일한 후보는 정답이 오답으로 정한 "롤백 누락" |
| case-004 | insufficient_evidence | 해당 없음 | 일치 | 일치 | 둘 다 보류하고 외부 `prices.csv` 변경 가능성과 파일 확인을 제시 |
| case-005 | log_clear | 예 | 일치 | 일치 | 둘 다 `loader.py:20` 오타, 확신 high |
| case-006 | log_clear | 예 | 일치 | 일치 | 둘 다 `inventory.py:39` 오타, 확신 high |
| case-007 | needs_related_code | 예 | 부분 | 일치 | A는 보류하고 외부 데이터를 1순위로 의심, fixture는 낮은 확신. B는 `conftest.py:21` |
| case-008 | needs_related_code | 아니오 | 부분 | 부분 | 둘 다 경계 비교 오류(`>`)를 맞게 추정했으나 코드를 못 봐 보류 |
| case-009 | distant_cause | 예 | 부분 | 일치 | A는 `place_order`의 상한 검사 문제까지만. B는 `orders.py:47`의 `len(items)`, 확신 high |
| case-010 | distant_cause | 아니오 | 불일치 | 일치 | A는 외부 데이터를 의심. B는 `Product.taxable` 기본값을 지목(위치 없음) |
| case-011 | insufficient_evidence | 해당 없음 | 일치 | 일치 | 둘 다 보류하고 `prices.csv`에 B200이 없을 가능성과 파일 확인을 제시 |
| case-012 | out_of_scope | 해당 없음 | 일치 | 일치 | 모델 호출 없이 `no_junit` |

| 방식 | 일치 | 부분 | 불일치 |
|---|---|---|---|
| A | 6 | 5 | 1 |
| B | 10 | 1 | 1 |

**3. 1차 채점에서 보인 것 (미검토)**

- 확신 high로 틀린 후보는 없었다. high는 7건이고 모두 정답과 같은 위치다.
- B는 원인 파일을 받지 못한 4건(002, 003, 008, 010)에서 모두 "해당 파일이 입력에 없다"고 한계에 적었다. 그중 2건은 테스트 파일과 fixture만으로 원인을 맞게 추정했고, 1건은 보류하면서 맞는 추정을 냈고, 1건(003)은 틀린 후보만 냈다.
- A는 코드가 없을 때 외부 데이터(`prices.csv`)를 의심하는 쪽으로 기운다(007, 010). 이 저장소의 로그에 데이터 내려받기 단계가 항상 보이기 때문으로 보인다.
- case-008은 두 방식 모두 원인을 맞게 추정하고도 보류로 결론을 냈다. 정답은 `cause_candidate`만 허용하므로, "맞는 추정 + 보류"를 어떻게 채점할지 기준이 필요하다.

**4. 이 결과의 한계**

- 사례당 1회 실행이다. 같은 입력을 다시 실행했을 때 결과가 얼마나 달라지는지는 재지 않았다.
- dev 12건은 프롬프트를 쓴 쪽이 만든 사례다. 사례 수가 적어 방식 간 차이를 수치로 주장할 수 없다.
- 채점자가 분석을 만든 쪽과 같다. "부분"과 "일치"의 경계는 사람이 다시 봐야 한다.
- 근거가 주장을 실제로 뒷받침하는지는 확인하지 않았다. 인용 검사는 인용한 줄이 존재하는지만 본다.
