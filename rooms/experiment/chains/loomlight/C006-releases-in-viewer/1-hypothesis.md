# 1. 가설 수립

## 이전 사이클의 교훈

부모 loomlight/C005(존재를 뷰어에)가 **확장 패턴**을 확립했다: 파싱→gil-data top-level 키→위계 body 패널→앱 온디맨드 렌더(C075)→Go 정적 이식(parity)→WEB-* 계약(gil-data 자기보고). 그리고 교훈 ②"데이터 소스 선택이 곧 무결성 계약"(정본을 소스로), ③"관심사 분리가 회귀 0"(top-level 형제 키).

상현님 발의의 **축 2(배포)**: "실험이 끝난 브랜치는 배포가 성공적으로 됐는지, 배포는 어떤 버전으로 되고 있는지 뷰어로 볼 수 있어야." 배포 데이터는 이미 두 몸으로 있다(C061): 깃 태그 `v<semver>` + CHANGELOG `## [X.Y.Z] — 날짜`. `gil releases`가 이 둘을 대조해 조회하고 drift를 드러낸다.

## 문제 분할

C005 골격을 배포에 적용:
1. **파싱**: CHANGELOG 릴리스 이력(version→date·note·tools) + 현재 버전(`_GIL_VERSION`) + drift(태그↔CHANGELOG). 참조엔 `_parse_changelog_releases`·`_git_release_tags`·`_release_drift`가 이미 있다.
2. **데이터**: gil-data top-level `releases` 키 {current, entries[], drift[]}.
3. **렌더**: 위계 body에 "배포" 패널 — 현재 버전 강조 + 릴리스 목록(버전·날짜·노트·도구변경) + drift 경고(있으면). 릴리스 노트는 짧으니 목록에 직접 표시(존재 4문서와 달리 경량 — 앱화 불요).
4. **⚠️ Go 비대칭 (C005가 발견)**: `releases`/`threads`는 **Go에 미이식**(참조 전용, `referenceOnly="release"`). 뷰어 데이터(gil-data)를 Go도 구워야 parity가 유지되므로, **CHANGELOG 파싱 + 태그 조회 + drift를 Go에 이식**해야 한다. releases *명령* 전체가 아니라 뷰어 데이터에 필요한 파싱 로직만.

첫 정복: **1~4를 묶어 배포를 뷰어에.** drift는 gil-data에 담되 태그가 환경마다 다를 수 있으므로(로컬 태그 유무) 계약면 설계에 주의.

## 가설

> **가설**: 참조의 CHANGELOG·태그·drift 로직으로 배포 데이터를 gil-data top-level `releases` 키(current·entries·drift)에 담고 위계 뷰어에 "배포" 패널을 렌더하며, 같은 파싱을 Go에 이식하면, 사람이 뷰어에서 **현재 어떤 버전으로 배포 중인지·릴리스 이력·태그와 CHANGELOG의 drift**를 볼 수 있고, 참조·Go 두 구현이 gil-data `releases`에서 동일하며(태그 의존 부분은 계약면 설계로 결정론 확보), 기존 사이클·존재 렌더는 회귀 0일 것이다.

## 기각 조건

- 배포 파싱이 **사이클/존재 렌더를 회귀**시킨다(기존 WEB-* FAIL).
- 참조와 Go의 `releases` gil-data가 **다르다** — 특히 drift(태그 의존)가 환경 차로 비결정적이면 parity가 깨진다(계약면에서 태그 의존 부분을 어떻게 다룰지 미해결이면 기각).
- **현재 버전이 틀리게** 표시된다(`_GIL_VERSION`과 불일치, 또는 지어냄).
- CHANGELOG가 없거나 릴리스 0인 저장소에서 **패널이 깨지거나** 빈 상태를 정직히 못 다룬다.
- 배포 정보를 **왜곡**한다(CHANGELOG에 없는 릴리스 지어냄, drift 오판).
