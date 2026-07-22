# 1. 가설 수립

## 이전 사이클의 교훈

부모 **C038**(GUARD를 커밋-층/author-경로로 v3화). C038에서 crash가 완전히 소멸하고
판정기가 게이트 없이 처음 완주. 여정의 국면이 "crash 최전선"에서 "게이트 없이 남은 12
병렬 FAIL"로 전환. 그 첫 축이 **예약축**(GUARD-RESERVED-OK·OPEN-PROMOTES-OWNER·
OPEN-SKIPS-RESERVED·OPEN-LAST-RESERVATION-GIT).

상현님이 기다리는 것: **"gil v3 쓸 수 있을 때 불러줘"** — 실사이클을 v3 네이티브로.
현재 실사이클 쓰기는 여전히 v2(`GIL_V2_OPEN=1 gil open`) — 도그푸딩 마찰.

## 문제 분할

예약축 4항목의 성질을 실측 분류했다:

- **RESERVE-\***(NEEDS-FOR·CHAIN·NON-INVASIVE·IN-LOG): reserve 명령 자체 검사, open과
  무관 → 게이트 없이 이미 PASS.
- **OPEN-SKIPS-RESERVED·OPEN-PROMOTES-OWNER·OPEN-LAST-RESERVATION-GIT·GUARD-RESERVED-OK**:
  **v2 open의 번호 승격/선점 동작** 검사 → 게이트 없이 FAIL.

**정점 실측 — 예약은 v2 open의 번호 자동증가와 짝이다.** 여러 존재가 동시에 open하면
번호(C00N) 충돌 → 예약으로 선점. 그런데 **v3 open은 경로가 정체성이라 번호 자동증가가
없다**(실측: `gil v3 open <dir>`는 dir 하나만 받고 번호·예약 미언급). 각 존재가 자기
경로(C0NN-slug)를 정하면 충돌 불가 → **예약이 v3 병렬에서 구조적으로 불필요.**

**정점 실측 2 — 우리 병렬 워크플로가 v2 open에 직접 결합.** `_worktree_add`(gil.py 934)가
워크트리 안에서 **`gil open`(v2)을 self-invoke**한다. 예약은 이 병렬 v2 open들의 번호
충돌 방지용. 그래서 예약축을 정리하려면 worktree self-invoke를 v3로 옮기는 것과 짝이다.

**실현가능성 실측(격리)**: 워크트리 안에서 `gil v3 open <dir> --git`이 완벽 작동 —
steps.yaml·루트 define s1 생성, git 각인(trailer), 그 브랜치에만 커밋. C050 격리 보존.

첫 정복 문제: **worktree add가 v2 open이 아니라 v3 open을 self-invoke하도록 전환** —
이것이 (a) 우리가 gil v3로 실사이클을 열 수 있게 하고(상현님 요청 직결), (b) 예약이
v3 병렬에서 불필요함을 실증하며(번호 충돌 없음), (c) C050 격리(브랜치 커밋)를 v3로 계승.

## 가설

> **가설**: `_worktree_add`가 `gil open`(v2) 대신 `gil v3 open <경로>`를 self-invoke하고
> author·parent를 git 각인 trailer(C010)로 기록하도록 전환하면, 워크트리 안에서 v3
> 사이클이 격리 브랜치에 정상 생성되고(steps.yaml·define s1), 번호 충돌이 원천적으로
> 없어 예약 없이도 병렬 안전하며, C050 격리(메인 오염 불가)가 v3로 계승되어 **우리가
> gil v3로 실사이클을 병렬로 열 수 있게 된다.**

## 기각 조건

1. worktree add를 v3 open으로 바꿨을 때 사이클이 브랜치에 안 생기거나 메인으로 새면 →
   격리 계승 실패(기각).
2. v3 open이 병렬에서 경로 충돌을 일으키면(두 존재가 같은 dir) → 예약 불필요 가정 오류
   (기각). 단 경로 충돌은 slug이 다르면 없으므로, 같은 slug 동시 open만 검증.
3. author·parent가 v3 사이클에서 소실되면(notes/trailer에 안 남으면) → 사이클-간 계보가
   끊김(기각·notes 층 보강 필요).
