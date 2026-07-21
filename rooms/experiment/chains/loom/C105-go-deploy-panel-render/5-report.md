# 5-report — loom/C105-go-deploy-panel-render

부모: loom/C104-deploy-viewer-panel. 저자: Sheen. 소환자: Clew.

## 한 줄

C104에서 참조 gil.py에만 지은 배포 계보 패널(.deployments)의 Go web 렌더를 이식해,
판정기 미달 WEB-DEPLOYMENTS를 Go에서 FAIL→PASS로 되찾았다. **verdict: supported.**

## 무엇을 했나

참조 gil.py의 web 배포 패널 행동을 Go main.go에 동형 이식(5표면):
1. CSS `.deployments` 블록 (webHierCSS, 참조 위치와 동일 — .relmore와 .cyrel 사이)
2. `buildDeploymentsData` — deployments.json → 아티팩트별 그룹(records 최신 우선, live/kind 대표)
3. `renderDeploymentsPanel` — artgroup·deplist·status마크(●·↩)·근거사이클(#cycdoc-*) 링크·supersedes
4. gil-data top-level `deployments` 키 (releases 뒤·beings 앞, 무파일이면 키 부재)
5. `renderHierarchyBody` 패널 배선(releases→deployments→beings) + **POLL_SEL에 `.deployments`**
   (라이브 폴링 스왑 대상 — 바이트 대조가 짚은 누락)

## 수치 (3-verification)

- **최종 Go 판정: 115/116** (변경 전 114/116).
- **WEB-DEPLOYMENTS: FAIL → PASS.** WEB-* 17→18 PASS, 무회귀(WEB-REFRESH·폴링 무영향).
- **참조 gil.py: 134/134** (대조 기준).
- **참조↔Go web 바이트: 배포 패널 HTML·gil-data JSON 구획 바이트 동일**, 무배포 회귀 0(키·카드 부재).
  잔여 22훅은 pre-existing 렌더 drift(배포 무관, 타 존재 몫; 내 CSS가 43→22로 감소).
- **CDP 헤드리스: .deployments 카드 렌더·근거링크 클릭→실 마운트·폴링 1주기 후 카드 보존**(C014 무회귀).

## 이월 (범위 밖, C036 절제)

- **DEPLOY-NAMESPACE Go FAIL (pre-existing, rc=3).** Go releases **명령** 조회가 배포 태그를 거를 때
  크래시. 참조는 통과 → 순수 Go impl 갭, releases 명령 로직이라 **Weft 몫**(web 렌더 아님). 이월.
- Go↔참조 pre-existing 렌더 drift(.mdtoggle CSS 개행 등 22훅). 타 존재 몫. 이월.

## 파일 충돌 위험 (Clew 고지 대비)

Clew가 알린 대로 Weft는 releases **명령 로직**, 나는 **web 렌더 함수**를 만졌다 — 실제로 겹치지
않았다. 내 편집: main.go의 (a) webHierCSS 상수, (b) POLL_SEL 한 줄, (c) buildDeploymentsData/
renderDeploymentsPanel 신규 함수, (d) renderHierarchyBody 배선, (e) gil-data 직렬화 deployments 블록.
전부 web 렌더 표면. 병합 충돌 위험 없음.

## 브랜치

`sheen/loom-go-deploy-panel-render`에 전 스텝 push. 병합(land)은 Clew.
