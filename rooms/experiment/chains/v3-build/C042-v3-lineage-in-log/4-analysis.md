# 4. 결과 분석

## 통계적 결과

| 측정 | 기준 | 결과 | 판정 |
|---|---|---|---|
| M1 log v3 계보 | child ← parent | C002-child ← C001-root | PASS |
| M2 그래프 노드 | 계보 반영 | 토폴로지·계보 정확 | PASS |
| M3 author 복원 | record author | clew·weft 복원 | PASS |
| M4 비-git 폴백 | crash 없이 root | rc0, (root) 폴백 | PASS |
| M5 무회귀 | fsck0·conformance121 | 172개·121/121 | PASS |

## 데이터 직접 관찰

**계보 섹션이 정확히 두 곳에서 고쳐졌다.** 수정 전 log: `root: C001-root, C002-child`
(둘 다 root, 틀림) · `C002-child ← (root)`(부모 안 그려짐). 수정 후: `root: C001-root`
(맞음) · `C002-child ← C001-root`(부모 그려짐). `_v3_lineage`가 C002-child 커밋의
`Cycle-Parent: C001-root` trailer를 읽어 record.parents에 넣자, build_graph 토폴로지가
child를 root에서 빼고 C001-root의 자식으로 배치. **trailer(각인)와 log(표현)가
record.parents를 다리로 연결.**

**폴백이 안전하게 동작.** M4에서 .git 제거 후 `git -C log`가 rc≠0이지만 `_v3_lineage`가
`([], None)` 반환 → (root)로 그림, crash 0. try/except + rc 체크 이중 방어. 계보는 커밋
메타라 git 없으면 못 읽는 게 당연 — 없을 때 안 무너지는 게 계약.

## 예상과 달랐던 것

- **C040 v3 record 구조가 계보를 받을 준비가 돼 있었다.** C040에서 v3 record를 v2와 같은
  형태(parents·author 키)로 만들어뒀기에, C042는 빈 값을 **채우기만** 하면 됐다.
  build_graph·log는 record 형태만 보지 v2/v3를 구분 안 하므로, parents가 채워지자 계보
  표현이 공짜로 따라왔다. **C040 "records 통일"의 배당금** — 표현 계층을 안 건드리고 계보
  표현 완성.
- **trailer valueonly·separator 포맷이 여러 부모를 깔끔히 처리.** `%(trailers:key=
  Cycle-Parent,valueonly,separator=%x00)`로 병합 사이클(부모 여럿)도 NUL 분리 파싱. git
  trailer 포맷이 계보 다중성을 직접 지원.

## 판정

**채택 (supported).** 계보가 trailer에서 복원돼 log 그래프에 부모로 그려지고(기각조건 1
불충족 — build_graph에 닿음), 비-git 폴백 안전(기각조건 2 불충족), v2·v3·conformance
무회귀(기각조건 3 불충족). 세 기각조건 모두 회피.

**⭐ 큰 그림**: 도그푸딩 전환의 "눈"이 생겼다. gil log가 v3 사이클을 계보와 함께 그린다
— 관전자가 v3 실사이클을 v2처럼 읽는다.

**정직한 경계**: log 계보 섹션·author는 표현되나, render_graph의 `●` 노드 상태 뱃지는
아직 `[?]`(v3 사이클의 진행/결말을 steps.yaml에서 도출 안 함 — 범위 밖). Cycle-Parent
참조 무결성(존재하는 사이클 가리키는가)도 미검사(C041 이월 유지). 계보 표현은 됐지만
v3 사이클의 "상태 표현"(열림/닫힘·verdict)은 다음.
