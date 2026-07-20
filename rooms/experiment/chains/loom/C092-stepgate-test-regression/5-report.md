# 5. 결과 보고 — C090 step 가드가 깬 기존 테스트 수정 (발의: 긴급, gil-gate)

## 요약
C090(step-by-step 강제)이 기존 conformance 테스트를 깨 gil-gate가 `sum(RESULTS)` TypeError로 실패하던 것을 고쳤다. 근본은 테스트 헬퍼 `write_cycle(step=N)`이 스텝 1..N 파일을 실질 작성하게 정합화(한 곳). 연쇄로 OPEN-CREATE·STEP-OK·STEP-SCOPE를 새 계약(open 1스텝·순차 전이)에 맞추고, WEB-AUTO-PURE-COMMIT의 빈-리스트 cond를 `bool()`로 방어. 목표 6항목 PASS, 121/122. **채택(부분).**

## 교훈
1. **로컬 검증도 CI를 재현해야 한다.** C090의 "회귀 0" 판정은 gil이 PATH에 없어 conformance가 조기 실패한 baseline과 비교한 착시였다. 진짜 회귀는 gil을 실제 실행하는 CI(gil-gate)만 잡았다. → `/tmp/gilbin/gil`(python3 절대경로 래퍼)를 PATH·--gil로 줘 로컬에서 CI를 재현하는 절차를 확립.
2. **계약을 바꾸면 그 계약을 검증하던 테스트도 바뀌어야 한다.** step 가드(생산 코드)를 넣으면 write_cycle+step(테스트 코드)이 새 계약을 만족해야 한다. 테스트 헬퍼가 "상태"를 정직하게 표현하면(step=N → N개 파일) 대부분의 개별 수정이 사라진다.
3. **한 크래시가 다른 결함을 가린다.** TypeError가 그 뒤 판정을 막아 RELEASE-CYCLE-SOURCE(기존 버그)가 안 보였다. 크래시를 걷어야 아래가 드러난다 — 그래서 부분 진전이라도 먼저 크래시를 없애는 게 값지다.

## 다음 사이클을 위한 제안
- **(A) RELEASE-CYCLE-SOURCE 격리 버그 (C093, 다음 1순위)** — 전체 실행 시 release가 "RELEASE.md에 1.1.0 서술 없다"로 rc=1. 격리 통과·전체 실패 = RELEASE-DRIFT-GATE와의 상태 간섭(work 경로·RELEASE.md 공유) 의심. 이걸 고치면 gil-gate 완전 녹색.
- (B) conformance 하네스에 "테스트 간 격리" 점검(각 테스트가 자기 샌드박스만 쓰는지).
- (C) 로컬 verify 스킬에 "gil 실제 실행 CI 재현"을 편입.

## 사이클 닫기
- [x] write_cycle 정합 + OPEN-CREATE·STEP-OK·STEP-SCOPE·WEB-AUTO-PURE-COMMIT 수정, TypeError 해소, 목표 6 PASS
- [ ] close --verdict supported / 배포(conformance만 변경 — 도구 무변) / memory
