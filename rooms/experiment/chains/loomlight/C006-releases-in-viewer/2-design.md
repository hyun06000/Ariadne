# 2. 실험 설계

## 정답 먼저: 기대 행동 (계약 항목)

§7 gil-data 자기보고가 계약. 새 판정:

| # | 항목 | 계약(gil-data 자기보고) | 기대 |
|---|---|---|---|
| T1 | **WEB-RELEASES** | 위계 gil-data top-level `releases` {current, entries[]} 존재 | current = 도구 자기 버전(_GIL_VERSION/gilVersion). entries = CHANGELOG 릴리스(version·date·note·tools). CHANGELOG에 없는 릴리스 지어냄 0. |
| T2 | **WEB-RELEASES-ABSENT** (정직) | CHANGELOG 없는 저장소 | `releases` 키 부재 또는 current만(entries 빈). 패널 부재/최소, 크래시 0. 기존 사이클·존재 렌더 바이트 동일. |
| T3 | **회귀 가드** | 기존 WEB-JSON·BEINGS·DOCS·HIERARCHY·PARALLEL | 전부 PASS. flat은 releases 무영향(바이트 동일). |

drift는 계약면에 넣되(entries에 태그/CHANGELOG 소속 표시), **parity 위험 관리**: 참조·Go가 같은 repo·같은 태그·같은 자기버전을 보므로 결정론적. T1은 같은 저장소에서 참조·Go byte-diff로 확증.

## 설계 결정

### D1. 데이터 소스 — CHANGELOG(원장) + 태그(깃 진실) + 자기버전
- CHANGELOG = `repo_root/rooms/deployment/CHANGELOG.md`(repo_root = chains_root의 `../../..`). 참조 `_parse_changelog_releases` 재사용.
- 현재 버전 = 도구 자기 상수(`_GIL_VERSION`/`gilVersion`) — "지금 이 뷰어를 구운 도구가 어떤 버전인가". **자기보고라 지어냄 불가**.
- 태그 = repo_root git의 `v<semver>`. `_git_release_tags`·`_release_drift` 재사용. git 부재면 drift 없음(정직).

### D2. gil-data 구조 — top-level `releases`
```
"releases": {
  "current": "2.33.0",
  "entries": [ {"version","date","note","tools","in_tag":bool,"in_changelog":bool} ... ],  # 최신 우선
}
```
- entries는 CHANGELOG ∪ 태그를 SemVer 역순. 각 원소가 `in_tag`·`in_changelog`로 drift를 자기표현(둘 중 하나만 true면 drift). 별도 drift 배열 대신 원소에 소속 플래그 — 뷰어가 그 항목을 강조.
- **releases가 있을 때만 키**(current는 항상 있으나, entries 0 + git부재면? current만이라도 유의미 → releases 키는 CHANGELOG 파싱 성공 시 넣음). 무배포 저장소(CHANGELOG 없음)는 키 부재 → 바이트 동일.

### D3. 렌더 — 위계 body "배포" 패널 (경량, 앱화 불요)
- `_render_releases_panel(releases)`: 헤더 "현재 v<current>" + 릴리스 목록. 각 행: 버전·날짜·노트·도구변경, drift면 배지(⚠ 태그만/CHANGELOG만). 노트가 짧아 초기 DOM에 직접(존재 4문서처럼 앱화 안 함 — 무게 문제 없음).
- 위치: 존재 패널 다음, 병렬 배너 앞(header→beings→releases→banner→map). "누가 사는지 → 무엇을 배포했는지 → 지금 뭐가 도는지" 흐름.

### D4. parity — Go 이식 (C005 발견 해소)
- Go에 `parseChangelogReleases`·`gitReleaseTags`·releaseDrift 이식(순수 파싱+git for-each-ref). `webJSONPayload`에 releases 조립(chains 뒤, beings 뒤). `renderHierarchyBody`에 패널. **정적 문자열이라 renderBeingsPanel처럼 parity 공짜**.
- current: Go `gilVersion` ↔ 참조 `_GIL_VERSION` — 배포 시 동기화되므로 같음.

## 절차

1. 참조: `_build_releases_data(chains_root)` 신설(CHANGELOG+태그+drift+current), `render_web_page`에서 hierarchy면 수집→`json_payload["releases"]`, `_render_releases_panel`, hierarchy body 삽입.
2. Go: `parseChangelogReleases`·`gitReleaseTags` 이식, `webJSONPayload` releases 조립, `renderReleasesPanel`, body 삽입.
3. conformance T1·T2 신설, T3 회귀.
4. 실렌더: current=2.33.0, entries에 CHANGELOG 릴리스, drift 표시. `--flat`·무CHANGELOG 바이트 동일.
5. parity: `diff <(참조 web) <(go web)` releases 포함 바이트 동일.

## 측정 방법

- **성공(채택)**: T1·T2 신설 PASS(수정 전 FAIL) + T3 회귀 0 + parity 바이트 동일 + current 정확(2.33.0).
- **기각**(1-hypothesis): 사이클/존재 렌더 회귀 / parity 깨짐(drift 비결정) / current 오류 / 무CHANGELOG 미처리 / 배포 왜곡.

## 사용자 컨펌

상현님 발의 축 2. C005에서 확립한 패턴 적용 + Go 비대칭 해소 방향(파싱만 이식)은 방법론 판단.

- [x] 컨펌 받음 (일자: 2026-07-19 — 발의 + "남은 두 축 이어서" 확정)
