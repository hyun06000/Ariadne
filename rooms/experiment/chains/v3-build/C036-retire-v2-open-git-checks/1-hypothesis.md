# 1. 가설 수립

## 이전 사이클의 교훈

부모: **v3-build/C035** (셋업 open을 공용 헬퍼로 — 게이트 없이 40→75).

C035가 안전 증명한 것: 셋업 open(전제 구축)은 write_cycle+git 헬퍼로 교체해도 판정 의미 불변. 검사 open(계약 판정)은 헬퍼 교체 불가(테스트 삭제). 현 crash: line 1342(stepgate).

## 상현님 방향 (설계 컨펌)

**"v2 open 검사 항목 제거."** open --git·--push·NO-REMOTE·PATH-SYMLINK는 v2 open 전용 계약(사이클-간 커밋 구조·번호 재번호)이라 v3에 대응물 없음(C033 매핑: 사이클-간 정보는 v3에서 cycle.yaml/notes 층). "완전 폐기"대로 제거 — C034 전진 삭제 패턴.

## 코드 실측으로 좁힌 진실 (C036 s1)

1300~1750 범위의 open 관련 항목을 전수 분류(라벨+성격):

**부류 A — open 자체 검사 (v2 전용, 제거 대상):**
- OPEN-GIT (1320) — open --git이 새 사이클 경로만 커밋
- OPEN-NEWCHAIN-COMMIT (1364) — open --new-chain --git이 chain.md도 커밋
- OPEN-PUSH-RENUMBER (1398) — open --push 번호 재번호
- NO-REMOTE-GRACEFUL (1698) — open --push 원격 없을 때 우아화
- PATH-SYMLINK-GIT (1727) — open --git 심링크 경로 우아화

**부류 B — open을 셋업으로 (헬퍼 교체 대상):**
- STEP-GATE (1346) — step-by-step 강제 검사. 셋업으로 open(1331, --git 없음). **현 crash원.**
- WITHDRAW-RETRACTS·REJECTS-CLOSED·ATOMIC (1561·1579·1589) — withdraw 검사, 셋업 open.

**핵심**: 현 crash원(stepgate)은 부류 B다 → 부류 A 제거만으론 crash가 안 사라진다. 게이트 없이 전진하려면 **부류 A 제거 + 현 crash원 STEP-GATE 셋업 헬퍼 교체를 함께** 해야 한다. 상현님 "검사 항목 제거"(부류 A)에 crash 해소를 위한 셋업 교체(부류 B, C035 패턴)를 더한다.

## 문제 분할

C036이 정복할 조각:
- **부류 A 5항목 제거** (OPEN-GIT·NEWCHAIN-COMMIT·PUSH-RENUMBER·NO-REMOTE-GRACEFUL·PATH-SYMLINK-GIT) — v2 open 전용 계약, v3 대응 없음.
- **STEP-GATE 셋업 open을 헬퍼로 교체** (1331) — 현 crash원 해소, C035 패턴. STEP-GATE는 step 검사지 open 검사가 아니므로 셋업 교체가 판정 불변.
- WITHDRAW 셋업 교체는 crash 지나면 드러나니 다음 카브로(순차).

## 가설

> **가설**: 부류 A(open 검사 5항목)를 제거하고 현 crash원 STEP-GATE의 셋업 open을 write_cycle+git 헬퍼로 교체하면 — crash가 stepgate(1342)를 넘어 판정기 더 뒤로 밀리고, 게이트 없이 통과 항목이 75에서 늘어난다. 부류 A 제거는 순감(회계 명시), STEP-GATE 교체는 판정 불변(step 검사, open 셋업).

## 기각 조건

1. 부류 A 제거 + STEP-GATE 교체 후에도 crash가 stepgate(1342) 근처에 머묾 → STEP-GATE 외 다른 원인(재조정).
2. STEP-GATE 셋업을 헬퍼로 바꾸니 step-by-step 검사 결과가 달라짐(게이트 상속 시 FAIL) → open이 STEP-GATE의 검사 일부였음(셋업 아님, 재분류).
3. 부류 A 제거로 게이트 상속 총 초록이 설명 못 할 만큼 감소(127 − 5 ≠ 실측) → 회계 오류.
4. 부류 A 중 일부가 실은 v3 대응물이 있어 제거가 아니라 재작성해야 함 → 제거 경계 오판.
