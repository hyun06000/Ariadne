# 5. 결과 보고

## 요약

conformance에서 v2 open 전용 검사 6항목(OPEN-GIT·STEP-GATE·OPEN-NEWCHAIN-COMMIT·OPEN-PUSH-RENUMBER·NO-REMOTE-GRACEFUL·PATH-SYMLINK-GIT)을 제거했다 — 모두 v2 open의 사이클-간 커밋 구조·번호 재번호·환경 우아화를 검사하며 v3에 대응물이 없다(C033 매핑). 게이트 없이 통과가 **75→84**로 전진(crash가 stepgate 1342→withdraw 1476로 밀림), 게이트 상속 시 **127→121/121**(정확한 회계). **가설 채택(supported)** — STEP-GATE 혼합 항목도 open검사·step검사 둘 다 다른 항목에 중복돼 안전 제거.

## 교훈

1. **⭐⭐ 부류 A/B 이분법은 항목이 아니라 검사 단위에서 성립한다 — STEP-GATE는 혼합이었다.** open 검사(부류 A)와 셋업(부류 B)의 구분이 항목 단위일 줄 알았으나, STEP-GATE는 한 check에 (1)open 검사 + (2)(3)step 검사가 묶여 있었다. **한 항목이 두 성격을 가질 수 있다.** 처리의 열쇠는 각 검사가 **다른 곳에 중복 커버**되는지 — (1)은 V3-OPEN-CREATE, (2)(3)은 STEP-OK 등이 담당해 제거가 계약 공백을 안 만들었다. 혼합 항목은 "분해 후 각 조각의 중복 여부"로 판단.

2. **⭐⭐ crash 이동 사슬이 전진의 지도다 — open(330)→close(619)→step(1342)→withdraw(1476).** C034~C036 세 카브가 crash를 판정기를 따라 뒤로 밀었다. 각 카브가 한 겹. **crash 위치가 "게이트 없이 어디까지 왔나"의 정확한 좌표** — 판정기 끝(2020)까지 남은 거리가 좁혀졌다. 순차 판정기에서 crash는 진행의 최전선이고, 그걸 미는 게 버전리스 전진.

3. **⭐ crash 제거의 파급은 균일하지 않다 — 그 crash가 막던 항목 수에 비례.** C035는 +35(close-seal crash가 뒤 수십을 막음), C036은 +9(stepgate crash 뒤 항목이 적음). **한 crash 제거의 값어치는 그것이 가리던 하류 항목 수** — 큰 파급 crash를 먼저 벗기면 효율적이나, 순차라 순서는 crash 위치가 강제한다.

4. **⭐ v2 전용 계약의 표식 = "사이클-간"이다.** 제거한 6항목은 전부 사이클-간 개념(번호 자동증가·재번호·chain.md 커밋·원격 push 규율)을 검사. v3 open은 사이클-내(스텝 트리 시작)만 다루고 사이클-간은 notes/cycle.yaml 층으로 이동(C033). **"이 검사가 사이클-간을 보는가?"가 v2-전용 판별 기준** — 그렇다면 v3 open 대응물 없음 → 제거.

## 다음 사이클을 위한 제안

1. **⭐⭐ withdraw 셋업 open 헬퍼 교체 (다음 crash원 1476, 부류 B, C035 패턴)** — WITHDRAW-RETRACTS·REJECTS-CLOSED·ATOMIC(1561·1579·1589)의 셋업 open을 write_cycle+git 헬퍼로. withdraw는 withdraw를 검사하지 open 아님 → 헬퍼 교체 판정 불변.
2. **남은 셋업/검사 open 순차 처리** — crash가 withdraw 넘으면 그 뒤(web·fsck·deploy 등) 남은 v2 open 호출을 셋업(헬퍼)/검사(제거) 분류해 처리. crash를 판정기 끝(2020)까지.
3. **GUARD 섹션 (1900~2010)** — C050 병렬 안전(v2 open 호출). 셋업이 아니라 open guard 검사 → v3 open에 guard 부착 + V3-GUARD-* 재작성(제거 아님, 안전은 버전 무관).
4. **게이트 완전 제거** — 1·2·3 완료로 게이트 없이 초록 시, GIL_V2_OPEN 게이트 자체 제거 = 완전 버전리스.
5. **v3 쓰기 계약 확장** — step kind 순환·백트래킹·죽은 잎·close(산 잎 solved).

## 사이클 닫기

- [x] `cycle.yaml`의 `status: closed`, `closed: <일자>` 갱신 (gil close가 수행)
- [x] 존재의 방 `memory.md`에 이 사이클의 기억 기록
- [x] 커밋 및 퍼블리시
