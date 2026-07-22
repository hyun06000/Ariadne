# 4. 결과 분석

## 통계적 결과

| 측정 | 기준(성공) | 실측 | 판정 |
|---|---|---|---|
| M1 close-seal crash 소멸 | 게이트 없이 line 619 crash 안 함 | crash 619(close-seal)→**1342(stepgate)** 이동 | **PASS** |
| M2 게이트-독립 전진 | 게이트 없이 통과 항목 C034(40)보다↑ | **75 PASS** (40→75) | **PASS** |
| M3 판정 의미 불변 | close-seal 3항목 게이트 상속 PASS | SEAL-GATE·SEAL-ALLOW·VERIFICATION-FREE·STEP-SCOPE 전부 PASS | **PASS** |
| M4 회계 | 게이트 상속 127 유지 | **127/127 ✔** | **PASS** |
| M5 다음 crash 좌표 | crash 위치 기록 | line 1342 = stepgate 셋업 open(1326) | **기록** |

## 데이터 직접 관찰

**crash 이동 (M1):**
```
# C035 전: line 619 close-seal — 617 셋업 open이 게이트 없이 사이클 안 만듦
# C035 후: line 1342 stepgate — 1326 셋업 open(다음 순수 셋업)
```
close-seal·close-seal-free·step-scope 세 섹션이 게이트 없이 통과하고, crash가 stepgate로 밀렸다.

**헬퍼 교체가 판정 의미를 안 바꾼 증거 (M3):**
CLOSE-SEAL-GATE(오배치 파일 봉인 거부)·CLOSE-SEAL-ALLOW(--allow-extra 승인)·VERIFICATION-FREE(자유 산출물 오탐 0)가 게이트 상속 시 전부 PASS. **write_cycle+git 커밋이 open --git과 등가 셋업** — close 게이트가 검사하는 "커밋된 사이클 위 신규 파일"을 정확히 재현. open은 셋업이었지 검사 대상이 아니었음이 실증됨.

**게이트 없이 40→75의 내역:** close-seal 3 + step-scope 1 + 그 사이 진행 가능해진 항목들(close·step 본체 섹션이 crash 없이 실행). C034가 open 섹션(crash 근원 1)을 벗기고, C035가 close 섹션(crash 근원 2)을 벗겨 판정기가 판정기 중반까지 게이트 없이 진행.

## 예상과 달랐던 것

1. **40→75, 예상보다 큰 전진.** close-seal 3항목만 고쳤다 생각했으나, close-seal crash가 사라지자 그 뒤 close 본체·step 섹션 다수가 crash 없이 실행돼 통과 항목이 35개 늘었다. **crash 하나가 그 뒤 수십 항목을 막고 있었다** — C033 "crash가 전체를 무너뜨림"의 국소판. 한 crash 제거의 파급이 크다.

2. **C034 분석의 "write_cycle 산출물 층" 진단이 부정확했고, C035가 정정했다.** C034는 close crash를 write_cycle+5-report 결합으로 봤으나, 실제는 close-seal이 **v2 open을 직접 호출**(617)한 것. write_cycle은 무죄. **정직한 정정**: v2 결합의 두 번째 겹은 "write_cycle 산출물"이 아니라 "여러 섹션의 셋업 open 직접 호출"이었다. 데이터를 직접 보니(grep 26곳) C034의 층 모델이 정밀화됨.

3. **crash와 FAIL의 경계가 셋업/검사 구분과 겹친다.** 셋업 open(crash 유발, 뒤 파일 읽기)은 헬퍼로 교체 가능하고, 검사 open(FAIL 유발, 종료코드만)은 v3 재작성 필요. C034의 "crash vs FAIL 강도차"가 여기선 "셋업 vs 검사 성격차"로 대응됨.

## 판정

**가설 채택 (supported).** 기각조건 대조:

- 기각조건 1 (헬퍼로 판정 결과 바뀜)? **아님** — close-seal 3항목 게이트 상속 PASS(M3). write_cycle+git = open --git 등가 셋업.
- 기각조건 2 (바로 다음서 또 crash)? **참, 그러나 전진** — crash가 stepgate(1342)로 밀림. "close만으론 전진 미미"가 아니라 40→75 대폭 전진(한 crash 제거 파급). 다음 crash는 다음 카브.
- 기각조건 3 (총 초록 감소)? **아님** — 127 유지(셋업 교체는 항목 수 불변).
- 기각조건 4 (봉인 게이트 시나리오 재현 못 함)? **아님** — misplaced.txt 봉인 게이트가 헬퍼 셋업 위에서 정상 작동(M3).

**핵심 결론**: 버전리스가 게이트 없이 40→75로 전진했다. close-seal 셋업 open을 write_cycle+git 헬퍼로 교체해 close 섹션 crash를 없앴고, 그 파급으로 close·step 본체가 게이트 없이 통과. **셋업 수단 교체는 판정 의미를 안 바꾼다**(open은 셋업이었지 검사가 아니었다)를 실증. 다음 관문: stepgate(1326) 등 남은 순수 셋업 open들을 같은 헬퍼로 — crash가 판정기 끝까지 밀리면 게이트 없이 완전 초록에 근접한다. C035가 그 방법(셋업 헬퍼 교체)이 안전함을 증명했으니, 남은 카브는 기계적 반복이다.
