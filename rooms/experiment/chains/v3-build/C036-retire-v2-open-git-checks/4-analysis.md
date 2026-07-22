# 4. 결과 분석

## 통계적 결과

| 측정 | 기준(성공) | 실측 | 판정 |
|---|---|---|---|
| M1 STEP-GATE 판정 처리 | 헬퍼 교체 후 PASS 또는 재분류 | STEP-GATE는 open검사+step검사 혼합 → 제거로 재분류 | **PASS(재분류)** |
| M2 crash 전진 | crash가 stepgate 넘어 밀림, 통과↑ | crash 1342→**1476(withdraw)**, **75→84** | **PASS** |
| M3 회계 | 게이트 상속 127−6=121 | **121/121 ✔** | **PASS** |
| M4 무결 | 121 전부 PASS | 전부 PASS | **PASS** |
| M5 다음 crash 좌표 | crash 위치 기록 | line 1476 = withdraw 셋업 open(1563) | **기록** |

## 데이터 직접 관찰

**제거한 6항목과 각각의 v2-전용 이유 (코드 실측):**
| 항목 | 검사 내용 | v3 대응 |
|---|---|---|
| OPEN-GIT | open --git이 새 사이클 경로만 커밋 | 없음(사이클-간 커밋 구조) |
| STEP-GATE | open이 1스텝만 + step 거부/통과 | (1)V3-OPEN-CREATE 중복, (2)(3)STEP-OK 중복 |
| OPEN-NEWCHAIN-COMMIT | open --new-chain --git이 chain.md 커밋 | 없음 |
| OPEN-PUSH-RENUMBER | open --push 번호 경합 재번호 | 없음(사이클-간 번호는 notes/cycle.yaml) |
| NO-REMOTE-GRACEFUL | open --push 원격 부재 우아화 | 없음 |
| PATH-SYMLINK-GIT | open --git 심링크 경로 우아화 | 없음 |

**STEP-GATE 재분류의 정직함:** STEP-GATE는 한 항목에 (1)open 검사 + (2)(3)step 검사가 섞여 있었다. 순수 부류 A도 B도 아닌 **혼합**. 처리: (1)은 V3-OPEN-CREATE가 이미 v3 open의 "루트 하나만 생성"을 검사하니 중복, (2)(3)은 별도 step 섹션의 STEP-OK·STEP-REJECT-RANGE·STEP-REJECT-CLOSED가 담당하니 중복. **둘 다 다른 곳에 커버돼 있어 제거해도 계약 공백 없음** — 재분류가 아니라 중복 제거.

**crash 이동 사슬 (C034~C036):** open 섹션(330) → close-seal(619) → stepgate(1342) → withdraw(1476). 네 번의 벗김으로 crash가 판정기를 따라 뒤로 이동. 각 카브가 한 겹씩.

## 예상과 달랐던 것

1. **STEP-GATE가 순수 부류가 아니라 혼합이었다.** 설계 시 부류 A/B 이분법으로 봤으나, STEP-GATE는 open 검사와 step 검사가 한 check에 묶여 있었다. **이분법이 항목 단위가 아니라 검사 단위에서 성립** — 한 항목이 두 성격을 가질 수 있다. 다행히 두 성격 다 다른 항목에 중복 커버돼 제거가 안전했다. 만약 고유 검사였다면 분해가 필요했을 것.

2. **75→84, C035(40→75, +35)보다 증가폭 작다(+9).** C035는 close-seal crash 하나가 뒤 수십 항목을 막았으나, C036의 stepgate crash는 그 뒤 항목이 상대적으로 적었다(correct·supersede·withdraw 앞부분까지만 진행 후 withdraw에서 다시 crash). **crash 제거의 파급은 그 crash가 막던 항목 수에 비례** — 균일하지 않다.

## 판정

**가설 채택 (supported).** 기각조건 대조:

- 기각조건 1 (crash가 stepgate 근처 머묾)? **아님** — crash 1342→1476(withdraw)로 확실히 전진.
- 기각조건 2 (STEP-GATE 교체로 검사 결과 달라짐)? **회피(재분류)** — STEP-GATE를 헬퍼 교체가 아니라 제거로 처리. open검사·step검사 둘 다 다른 항목에 중복이라 제거가 계약 공백 안 만듦.
- 기각조건 3 (설명 못 할 감소)? **아님** — 127−6=121 정확.
- 기각조건 4 (부류 A에 v3 대응물 있음)? **아님** — 6항목 전부 v2 open 전용(사이클-간 커밋·번호·환경 우아화), C033 매핑상 v3 대응 없음.

**핵심 결론**: 버전리스가 게이트 없이 75→84로 전진. v2 open 전용 검사 6항목을 제거해(전진 삭제) crash를 withdraw로 밀었고, 회계 정확(127→121). STEP-GATE 혼합 항목도 두 검사가 다른 곳에 중복돼 안전 제거. **다음 관문**: withdraw 셋업 open(부류 B, C035 헬퍼 패턴)과 그 뒤 남은 셋업/검사 open들. crash가 판정기 끝까지 밀리면 게이트 없이 완전 초록 → GIL_V2_OPEN 게이트 자체 제거(완전 버전리스). C034~C036 세 카브가 crash를 330→1476까지 밀었으니, 판정기 끝(2020)까지 남은 거리가 좁혀졌다.
