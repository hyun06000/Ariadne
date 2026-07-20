# 4. 결과 분석

## 통계적 결과
목표 6항목 전부 PASS, TypeError 해소, STEP-GATE 무회귀. 121/122 (유일 FAIL은 스코프 밖 RELEASE-CYCLE-SOURCE).

## 데이터 직접 관찰
- **한 곳(write_cycle) 수정이 대부분을 풀었다.** 헬퍼가 "step=N 상태"의 파일을 실제로 갖추자, 그 헬퍼를 쓰던 여러 테스트(WEB-AUTO·STEP 계열)가 전이 가드를 자연히 통과. 나머지 3개(OPEN-CREATE·STEP-OK·STEP-SCOPE)만 계약 변화를 직접 반영. 가설대로 "한 곳 + 소수 개별".
- **TypeError의 진짜 원인은 빈 리스트 cond였다.** `cycle_commit and ...`에서 cycle_commit=[]면 파이썬이 []를 반환 → RESULTS에 리스트 → `sum(int들 + list)` 폭발. step 가드가 커밋을 막아 cycle_commit이 비게 된 게 방아쇠였고, 진짜 결함은 "cond가 불리언이 아닐 수 있음"이었다. `bool()`로 방어.
- **가려진 버그가 드러났다.** RELEASE-CYCLE-SOURCE는 C092 전에도 FAIL이었으나 TypeError 크래시가 그 뒤 항목 판정을 통째로 막아 안 보였다. 크래시를 걷어내자 그 아래 있던 별개 버그가 노출 — "한 결함이 다른 결함을 가린다".

## 예상과 달랐던 것
- **로컬 회귀 검사의 맹점.** C090에서 "baseline 5 FAIL 동일"로 통과 판정했으나, 그 baseline은 gil이 PATH에 없어 conformance가 조기 실패한 상태였다 — 진짜 회귀를 못 봤다. **CI(gil 실제 실행)만이 잡았다.** 교훈: 로컬 검증도 gil을 실제 실행하는 경로(/tmp/gilbin 래퍼)로 CI를 재현해야 한다.

## 판정
**채택(supported, 부분).** C090이 깬 회귀를 write_cycle 정합 + 소수 수정으로 해소, gil-gate의 TypeError 크래시 제거. RELEASE-CYCLE-SOURCE는 사전 등록한 대로 스코프 밖(기존 버그)이라 C093 이월 — 부분 진전을 정직하게 표시.
