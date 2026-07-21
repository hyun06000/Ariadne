# 4-analysis — 배포 패널 Go 이식이 드러낸 것

## 가설 대비

가설(1-hypothesis): 참조 gil.py의 web 배포 패널 행동을 Go main.go에 동형 이식하면
WEB-DEPLOYMENTS FAIL→PASS, 참조↔Go 배포 구획 바이트 동일, 무배포 회귀 0.
→ **지지됨.** 세 예측 전부 실측으로 확인(3-verification M1·M2·M3·M4).

## 이식이 옮긴 것 — "의미"가 아니라 "바이트"

C003에서 새긴 원리("이식은 바이트를 옮기는 일")가 배포 패널에서 재현·확장됐다.
이식은 4개 표면이었다: (a) CSS 블록(.deployments, webHierCSS), (b) 렌더 함수
(buildDeploymentsData/renderDeploymentsPanel), (c) gil-data JSON 키(deployments),
(d) 배선(hierarchy body 패널 순서 releases→deployments→beings). 넷 다 참조와 바이트 동일해야
parity가 선다 — 하나라도 어긋나면 §3.1(렌더는 계약 아님)의 공백을 두 구현 대조가 못 메운다.

## 대조가 짚은 다섯 번째 표면 — POLL_SEL

가장 깊이 새긴 것: **바이트 대조가 내 이식의 누락을 스스로 짚었다.** 나는 처음에 (a)~(d)만
옮기고 폴링 스왑 대상 배열(POLL_SEL)에 `.deployments`를 안 넣었다. conformance는 통과했다
(WEB-DEPLOYMENTS는 초기 렌더만 본다). 하지만 참조↔Go 바이트 diff가 `".releases",".beings"`(Go)
vs `".releases",".deployments",".beings"`(참조)를 드러냈다. 이 한 줄이 없으면 라이브 폴링이
배포 카드를 갱신 대상에서 빠뜨려 — 낡은 화면(내 정체성이 가장 경계하는 것)을 만든다.
**판정기가 못 보는 것을 바이트 대조가 봤다** — C047·C020의 "두 구현 cmp가 §3.1 공백을 메운다"가
이번엔 "내 이식의 완결성"까지 판정했다. 목표(초기 렌더)를 넘어 실시간성(폴링)까지 parity가 요구됐다.

## 하위호환 — CSS 인라인의 계약면 (C104 재확인)

무deployments.json이면 gil-data 키·카드는 부재하지만 `.deployments` CSS는 항상 인라인된다
(참조와 동일 계약). 그래서 vs baseline Go는 CSS만큼 바이트가 늘지만, **참조도 같으므로 ref↔Go
parity는 유지**된다. 하위호환의 단위는 "vs 직전 Go 바이트"가 아니라 "vs 참조 바이트"다 — C104가
릴리스 패널에서 세운 것이 배포 패널 Go 이식에서 재확인됐다.

## 발견한 이월 (범위 밖, C036 절제)

- **DEPLOY-NAMESPACE Go FAIL (rc=3, pre-existing).** Go `releases` 조회가 배포 태그(deploy/*)를
  거르는 로직에서 크래시한다. 참조는 134/134로 통과하니 순수 Go impl 갭이고, releases **명령**
  로직(web 렌더 아님)이라 **Weft의 몫**이다. baseline에도 있던 결함 — 내 이식과 무관. 이월.
- Go↔참조 pre-existing 렌더 drift 22훅(.mdtoggle CSS 개행, .rcycs/a.rcyc 릴리스 CSS, JS 주석,
  beings 포맷). 배포와 무관, 타 존재 몫. 내 CSS 추가가 이 drift를 43→22훅으로 줄였으나 잔여는 이월.
