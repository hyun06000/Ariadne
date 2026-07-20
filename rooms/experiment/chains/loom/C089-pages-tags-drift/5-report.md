# 5. 결과 보고 — github.io 뷰어 "CHANGELOG만" 오표시 수정 (발의: 박상현)

## 요약
github.io 뷰어가 전 릴리스를 "⚠ CHANGELOG만" drift로 오표시하던 것을 고쳤다. 원인: CI의 `actions/checkout@v4`가 태그를 안 가져와(shallow) 뷰어가 태그를 못 읽음 → 전부 in_tag=False. 두 층 수정: ① `_PAGES_WORKFLOW`에 `fetch-depth: 0`(근본), ② `_build_releases_data`가 `tags_readable`로 "태그 못 읽음"을 감지해 drift 배지 억제(방어선, CLI git_absent의 뷰어 이식). 진짜 drift(태그 읽힘+특정 버전 없음)는 유지. 회귀 0. **채택(supported).**

## 교훈
1. **같은 진실을 보는 두 표면은 같은 판별을 해야 한다.** CLI는 git_absent를 구별했으나 뷰어는 안 했다 — 그 비대칭이 오표시를 낳았다. 조회의 표면이 여럿이면(CLI·뷰어) 환경 판별도 공유해야 한다(C061 정신 확장).
2. **환경이 진실을 가리면 '모른다'고 표시하라.** 태그 못 읽는 CI에서 "태그 없음=drift"는 거짓. tags_readable=False = "대조 불가"로 오탐 억제 — 지어냄 0의 배포판.
3. **증상이 층을 가리킨다.** "전부 CHANGELOG만"이라는 전역적 증상은 개별 렌더가 아니라 데이터 생성(환경 판별)을 가리켰다. entries의 in_tag가 이미 다 False였다.

## 다음 사이클을 위한 제안
- (A) **Go parity** — 뷰어 3연작(C087·C088)에 이 수정까지, Go 이식 이월 누적.
- (B) fsck/CI에 "배포 후 github.io 뷰어 drift 0" 스모크(선택).
- (C) 기배포된 github.io는 다음 push(이 릴리스 포함) 시 새 워크플로로 재빌드되어 자동 교정 — 확인 필요.

## 사이클 닫기
- [x] fetch-depth:0 + tags_readable 억제, 세 시나리오 통과, 진짜 drift 보존, 회귀 0
- [ ] close --verdict supported / 릴리스 / memory
