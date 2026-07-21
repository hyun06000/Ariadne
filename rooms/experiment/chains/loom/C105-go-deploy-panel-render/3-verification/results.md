# 3-verification — Go web 배포 패널 이식 실측

세션-로컬 격리 빌드(공유 /tmp/gil-go 금지, C003 스테일 함정): `/tmp/gil-go-sheen-new2`.
참조: `rooms/deployment/ariadne-spec/gil.py`. 판정기: `conformance.py`.

## M1 — conformance (판정기 통과가 1차 기준)

- **참조 gil.py: 134/134 PASS** (WEB-DEPLOYMENTS·DEPLOY-NAMESPACE 포함 전부).
- **Go 변경 전(baseline): 114/116**, FAIL = {WEB-DEPLOYMENTS, DEPLOY-NAMESPACE}.
- **Go 변경 후: 115/116**, FAIL = {DEPLOY-NAMESPACE}.
  - **WEB-DEPLOYMENTS: FAIL → PASS** (이 사이클의 목표).
  - WEB-* 판정: 17 PASS → 18 PASS (WEB-DEPLOYMENTS만 증가, WEB-REFRESH·WEB-REFRESH-DEFAULT 등 무회귀).
  - **DEPLOY-NAMESPACE는 pre-existing FAIL** (baseline에도 존재, rc=3 = Go `releases` 조회 로직 크래시).
    이는 **Weft의 releases 명령 로직 몫**이지 web 렌더가 아니다 → 범위 밖, C036 절제대로 이월(§완료보고).

## M2 — 참조↔Go web 바이트 대조 (§3.1 렌더 계약 보강)

실 deployments.json 있는 워크트리 `rooms/experiment/chains`에서 두 web HTML 생성:
- **deployments 패널 HTML 구획: 참조↔Go 바이트 동일** (`cmp` 무출력).
- **deployments gil-data JSON 키 구획: 참조↔Go 바이트 동일**.
- **POLL_SEL(폴링 스왑 대상)에 `.deployments` 추가** → 참조와 동일(초기 이식 누락을 대조가 짚어 봉합).
- 전체 파일엔 **pre-existing Go↔참조 drift 22훅** 남음 — 전부 `.mdtoggle` CSS 개행·`.rcycs`/`a.rcyc`
  릴리스 CSS·JS 주석·beings 렌더 포맷(baseline에도 존재, Weft/타 존재 몫). **배포 관련 diff는 0**.
  (내 CSS 추가가 오히려 ref↔Go drift를 43→22훅으로 **줄였다** — .deployments CSS가 이제 양쪽에 있음.)

## M3 — 무deployments.json 회귀 (하위호환)

- 무파일 샌드박스: Go web에 **deployments gil-data 키 부재·`.deployments` 카드 부재** (지어냄 0).
- 참조↔Go 무파일: 배포 관련 diff 0 (`.deployments` CSS는 항상 인라인 — 참조와 동일 계약, C104 교훈).
  vs baseline Go: `.deployments` CSS 블록만큼 바이트 증가(HTML 본문·JSON 무변화) — C104가 확립한
  "배포 패널 CSS는 항상 인라인" 계약의 Go 반영. 참조도 동일하므로 ref↔Go parity는 유지.

## M4 — 헤드리스 CDP 실측 (loomlight/C004·C010 방식; Chrome --headless=new)

Go 렌더 페이지(실 deployments.json, --refresh 2)를 raw-WebSocket CDP로 구동:
- `.card.deployments` 존재, artifact=`ariadne-deploy`, 배지=`● live v1.0.0`, 근거링크 4개.
- 근거링크 클릭(`#cycdoc-loom-C101-deploy-axis-cut`) → **실재 DIV 마운트로 이동**(target_exists=true).
- **폴링 1주기 후(3s) 카드·내용 보존** (card_still_present=true, artname 불변) — C014 상태보존 무회귀.

## 판정

목표 WEB-DEPLOYMENTS PASS 달성, 참조↔Go 배포 구획 바이트 동일, 무배포 회귀 0, 폴링 보존 확인.
DEPLOY-NAMESPACE는 pre-existing·범위 밖(Weft) → 이월.
