# 1. 가설 수립 — C090 step 가드가 기존 테스트를 깸 (긴급, gil-gate 적색)

## 이전 사이클의 교훈

부모 **loom/C090**: step-by-step 강제(open 1스텝, step 전이 가드). 회귀 검사에서 "baseline 5 FAIL 동일"이라 통과로 봤으나 — **그 baseline은 gil이 PATH에 없어 conformance가 앞부분에서 실패한 상태**였다. gil이 정상 실행되는 **CI(gil-gate)에서만** 진짜 회귀가 드러났다.

## 문제 진단 (CI 로그)

`gil-gate` 워크플로가 `TypeError: unsupported operand type(s) for +: 'int' and 'list'`로 실패. 범인 = **WEB-AUTO-PURE-COMMIT**의 cond `cycle_commit and all(...) and ...` — `cycle_commit`이 빈 리스트 `[]`면 `[] and X`가 `[]`를 반환해 RESULTS에 리스트가 섞이고 `sum(RESULTS)`가 터진다.

근본 원인: 이 테스트(와 여러 WEB-AUTO·기타)가 `write_cycle(step="1")`로 사이클을 만들고 **1-hypothesis를 실질 작성하지 않은 채 `step 2`를 바로** 친다. C090 가드가 "스텝 1 미완"이라 step을 **거부** → 재굽기·커밋이 안 일어나 cycle_commit이 빈다. 615·622·638·1317·1365·1383·1392·1394 등 광범위.

## 가설

> **가설**: 테스트 헬퍼 `write_cycle(step=N)`이 **스텝 1..N의 파일을 실질 내용으로 생성**하게 하면(스캐폴딩 문구가 아닌 실텍스트), "step=N 상태의 사이클"이라는 헬퍼의 의미가 C090 가드와 정합해져, write_cycle+step을 쓰는 모든 기존 테스트가 새 계약을 자연히 만족하고 gil-gate가 녹색으로 돌아온다. (한 곳 수정으로 광범위 해소.)

## 기각 조건

- 헬퍼 수정으로 안 고쳐지는 테스트가 남으면(개별 대응 필요) 부분 기각.
- WEB-AUTO-PURE-COMMIT의 `[] and` 리스트-cond 자체는 별도 방어(불리언 강제) 필요할 수 있음 — 안 하면 다른 빈-리스트 경로에서 재발.
- 헬퍼 수정이 STEP-GATE 등 C090 신규 테스트를 깨면 기각.

## 스코프 확정 (검증 중 발견)

RELEASE-CYCLE-SOURCE도 전체 실행에서 FAIL이나, **C092 수정 전(write_cycle 원본)에도 이미 FAIL**임을 확인했다 — C090의 TypeError에 가려 안 보였던 **별개의 기존 버그**(release 테스트의 RELEASE.md 상태 간섭). 따라서 C092 스코프는 **"C090 step 가드가 깬 회귀"까지**로 긋고(write_cycle 정합 → OPEN-CREATE·STEP-OK·STEP-SCOPE·sum(RESULTS) TypeError), RELEASE-CYCLE-SOURCE 격리 문제는 후속 사이클로 넘긴다. gil-gate는 그 후속까지 완전 녹색이 되지 않는다(정직한 부분 진전).
