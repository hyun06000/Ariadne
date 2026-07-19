# 2. 실험 설계

## 정답 먼저: 기대 행동 (계약 항목)

| # | 항목 | 계약(gil-data 자기보고) | 기대 |
|---|---|---|---|
| T1 | **WEB-CYCLE-RELEASE** | 위계 gil-data chains.cycles[cid]에 `released_in` (배포된 사이클만) | 릴리스 태그가 포함하는 사이클 = 그 사이클의 최소 버전. 미배포/열림 = 키 부재. 지어냄 0. |
| T2 | **회귀 가드** | 기존 WEB-JSON·BEINGS·RELEASES·DOCS·HIERARCHY | 전부 PASS. flat은 released_in 무영향(cycles 메타는 flat도 씀 — 주의). 무릴리스면 released_in 전무. |

**flat 주의**: released_in은 `chains.cycles[cid]` 메타에 들어가는데, 이 메타는 **flat도 gil-data에 씀**(WEB-JSON이 검사). beings/releases는 hierarchy 전용이었지만 released_in은 사이클 메타라 flat에도 나타난다. → **released_in은 hierarchy·flat 공통**으로 담되, 무릴리스(태그 0) 저장소는 키 부재라 기존 산출물 바이트 동일 유지. flat 회귀는 "릴리스 있는 저장소"에서만 바이트가 바뀌는데, 그건 새 진실(배포 상태)의 정당한 추가.

## 설계 결정

### D1. 판정 — 역인덱스 (O(릴리스 수) git 호출)
- `git tag --merged v<X>`는 v<X>의 조상인 태그들(그 릴리스에 포함된 cycle 태그 포함). **낮은 버전부터** 순회하며, 각 릴리스가 포함하는 cycle 태그 중 **아직 배정 안 된 것**에 released_in = 그 버전. → 각 사이클의 "최초 배포 릴리스". git 호출 = 릴리스 수(65)이지 사이클 수(95) 아님.
- 사이클 태그명 = `cycle/<chain>/<id>`. 역인덱스 결과 map[cycle_id] = version.
- git 부재/태그 0이면 빈 map(released_in 전무 — 정직).

### D2. 데이터 — 사이클 메타에 released_in (조건부)
- `_build_web_data`의 cycle entry에 `released_in`을 넣되 **배정된 사이클만**(map에 있을 때만 키). C006 교훈 ②: 관계는 원소 속성.
- released_in 인덱스는 **저장소 전역 1회 계산**(build_web_data 시작 시), cycle마다 조회.

### D3. 렌더 — 노드/마운트 배지
- `_render_cycle_mount`(위계) 헤드에 배포 배지: released_in 있으면 `v2.33.0 배포`(초록), 없으면 닫힌 사이클이면 `미배포`(회색), 열림이면 배지 없음.
- flat `_render_tables`에도 released_in 열? → 최소 침습 위해 위계 마운트에 집중, flat 표는 선택(회귀 최소화). **위계 우선, flat은 gil-data에만**(렌더는 계약 아님).

### D4. parity — Go
- Go `buildWebData`에 released_in 인덱스(`gitReleaseTags` 재사용 + `git tag --merged`). 사이클 메타에 released_in 조립(webJSONPayload). renderCycleMount 배지. 정적이라 parity.
- git 호출 순서·정렬이 참조와 같아야 인덱스 동일 → SemVer 오름차순 순회 고정.

## 절차

1. 참조: `_cycle_release_index(repo, chains_root)` — v태그 SemVer 오름차순, 각 `git tag --merged`의 cycle 태그를 미배정분에 배정. `_build_web_data`에서 1회 호출, cycle entry에 released_in.
2. `_render_cycle_mount`에 배지.
3. Go 동형: releaseIndex, buildWebData 조립, renderCycleMount 배지.
4. conformance WEB-CYCLE-RELEASE 신설(sandbox에 릴리스 태그+사이클 태그 심어 released_in 확인) + 회귀.
5. 실렌더: C082→v2.33.0, C081→v2.32.0, C005→미배포. parity 바이트 동일.

## 측정 방법

- **성공(채택)**: T1 PASS(수정 전 FAIL) + T2 회귀 0 + parity 바이트 동일 + 실렌더 released_in 정확(C082=2.33.0·C081=2.32.0·C005 미배포) + 뷰어 생성 시간 실용적(역인덱스).
- **기각**: 렌더 회귀 / released_in 오판 / parity 불일치 / 느림 / 무태그 미처리 / 왜곡.

## 사용자 컨펌

상현님 발의 축 3, "사이클→배포 연결" 선택. 판정 방법(git tag --contains/merged)은 실측으로 확인.

- [x] 컨펌 받음 (일자: 2026-07-19 — AskUserQuestion "사이클→배포 연결")
