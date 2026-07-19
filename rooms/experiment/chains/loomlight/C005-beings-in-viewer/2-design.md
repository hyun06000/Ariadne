# 2. 실험 설계

## 정답 먼저: 기대 행동 (계약 항목)

§7 "렌더는 계약이 아니다 / gil-data 자기보고가 계약". 새 판정:

| # | 항목 | 계약(gil-data 자기보고) | 기대 |
|---|---|---|---|
| T1 | **WEB-BEINGS** | 위계 gil-data top-level `beings` 배열 존재, 각 원소 {name, role, docs{identity,will,memory,relations}} | `rooms/existence/` 명부의 존재 집합과 일치(이름 집합 동일). 없는 존재 지어냄 0. |
| T2 | **WEB-BEINGS-LIGHT** | 초기 HTML(스크립트 밖 DOM)에 memory 전문이 안 뜸 | `<pre>`로 렌더된 memory 텍스트가 초기 DOM에 부재 — 앱이 온디맨드(C075 패턴). |
| T3 | **WEB-BEINGS-ABSENT** (회귀·정직) | 존재 0(또는 existence 디렉토리 부재) | `beings` 키 부재 또는 `[]`, 패널 부재, 크래시 0. 기존 사이클 렌더 바이트 동일. |
| T4 | **회귀 가드** | 기존 WEB-JSON·DOCS-EMBEDDED·HIERARCHY-DEFAULT·PARALLEL-BANNER | 전부 PASS(chains/reservations/docs 불변). flat은 beings 무영향(바이트 동일). |

## 설계 결정

### D1. 데이터 소스 — 명부(요지) + 4문서(전문)
- **요지**: `rooms/existence/README.md`의 거주자 명부 표를 파싱 — `| [이름](dir/identity.md) | 역할 | 입주일 |`. 정규식으로 {name, dir, role, moved_in}. **명부가 정본**(§ "뷰어는 새 진실을 안 만든다" — 명부에 없으면 안 그림).
- **전문**: 각 존재 dir의 identity/will/memory/relations.md 텍스트. C075 관찰(clew memory 172KB)로 **전문은 초기 DOM에 안 그림** — gil-data `beings[].docs`에 담고 앱이 클릭 시 렌더.

### D2. 무게 — C075 원칙 준수
- clew memory 172KB 등 전문을 gil-data JSON에 넣으면 **바이트는 커진다**. 그러나 C075 교훈: 병목은 바이트가 아니라 **초기 렌더 DOM 노드 수**. `<script type=application/json>` 안 텍스트는 브라우저가 파싱·레이아웃 안 함 → 초기 렌더 경량 유지(T2가 이를 계약). 사이클 docs와 동일 전략.
- **flat 뷰어는 beings를 안 담는다**(hierarchy 전용, docs와 동일) → `--flat` 바이트 동일.

### D3. 위치 — gil-data top-level `beings` (chains 밖)
- 존재는 특정 체인 소속이 아니라 저장소 전역 → `json_payload`의 `chains`와 **동급 top-level 키** `beings`. hierarchy일 때만, 존재가 있을 때만(키 조건부 — 무존재 바이트 동일).

### D4. 렌더 — 위계 body 상단 "존재" 패널 + 앱 온디맨드 상세
- `_render_hierarchy_body`에 체인 지도 위(또는 아래)에 `_render_beings_panel(beings)`: 각 존재를 카드/칩(이름·역할, `<a href="#being-<name>">`)으로. 클릭 → `#being-<name>` 해시.
- `_WEB_APP_JS`에 `#being-*` 라우팅 추가: `buildBeing(name)`이 gil-data `beings`에서 그 존재의 4문서를 `<details>`(identity/will/memory/relations)로 그 자리에 그림(사이클 `build` 패턴 재사용). `done` 캐시 공유.

### D5. parity — Go 동형
- Go `buildWebData`(별도 `parseBeings`) + `webJSONPayload`에 `beings` + `renderHierarchyBody`에 패널 + `webAppJS` 상수에 `#being-*` 라우팅. 참조와 `beings` gil-data **바이트 동일** 목표.

## 절차

1. `_parse_beings(repo_root)` 신설 — 명부 표 파싱 + 각 dir 4문서 읽기. repo_root는 chains_root의 `../..`(existence는 rooms/ 아래).
2. `render_web_page`에서 hierarchy면 beings 수집 → `json_payload["beings"]`(조건부).
3. `_render_beings_panel` + `_render_hierarchy_body` 삽입.
4. `_WEB_APP_JS`에 `buildBeing`+`#being-*` activate 분기.
5. Go 동형 이식(parseBeings·webJSONPayload·renderHierarchyBody·webAppJS).
6. conformance T1~T3 신설 + T4 회귀 확인. 참조·Go 각각 100%.
7. 실렌더 확인: `gil web`으로 굽고 (a) 초기 DOM에 memory 전문 부재(T2) (b) beings JSON에 5명(T1) (c) 헤드리스로 존재 클릭→상세 출현. `--flat` 바이트 동일.
8. parity: `diff <(참조 web) <(go web)` beings 포함 바이트 동일.

## 측정 방법

- **성공(채택)**: T1~T3 신설 PASS(수정 전 FAIL로 유효성) + T4 회귀 0 + parity 바이트 동일 + 헤드리스 클릭 상세 출현.
- **기각**(1-hypothesis): 사이클 렌더 회귀 / 초기 DOM 폭증(T2 FAIL) / parity 깨짐 / 무존재 미처리 / 존재 왜곡(명부 밖 지어냄, memory 의미 훼손).

## 사용자 컨펌

상현님 발의 + 3대 결정(세 축 모두·단독 순차, 축당 사이클은 방법론 판단). C005=존재 먼저는 상현님이 "AI 자아"를 첫 번째로 짚음.

- [x] 컨펌 받음 (일자: 2026-07-19 — 발의 + AskUserQuestion 범위 확정)
