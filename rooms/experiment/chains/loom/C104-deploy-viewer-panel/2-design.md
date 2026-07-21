# 2. 실험 설계

가설(1-hypothesis.md): deployments.json을 gil-data top-level `deployments` 키로 굽고 아티팩트별
배포 계보 카드를 릴리스 패널과 **별개로** 렌더하면, 뷰어가 사용자 산출물 배포를(status·근거사이클
링크·supersedes 포함) 정직히 비추면서도 배포 안 쓰는 저장소엔 렌더 콘텐츠가 안 늘고 폴링에 열린
상태가 안 깨진다.

## 절차

1. **목업 먼저(C067 철칙)**: 배포 패널 레이아웃을 코드 전에 정적 HTML 목업으로 그리고 헤드리스
   Chrome 스크린샷으로 육안 확인 (mockup-deploy-panel.{html,png}).
2. **구현**: gil.py에 (a) `_build_deployments_data`(deployments.json → 아티팩트별 그룹, 파일 없으면
   None), (b) `_render_deployments_panel`(별 카드 `.deployments`, 릴리스 `.releases`와 분리),
   (c) CSS 블록, (d) payload에 `deployments` 키·`_render_hierarchy_body` 배선, (e) POLL_SEL에 `.deployments`.
3. **격리 샌드박스**: 세션-로컬 git 저장소를 만들어 실 사이클 2개(alpha/C001·C002)를 열고 닫은 뒤
   `gil deploy cut`으로 실 배포 레코드를 만든다 — churn-model(v1.9.0 live, v2.0.0 rolled-back, 다중근거),
   landing-page(v1.0.0 superseded, v1.1.0 live). 세 status 전부 커버.
4. **구조 실측**: 렌더 HTML에서 배포 카드 1개·릴리스 카드 0개(무CHANGELOG → 두 축 분리 증명)·
   depcyc 앵커가 실 cycdoc 마운트 id와 일치·status 마크 3종·live 배지 정확성 확인.
5. **하위호환 실측**: deployments.json 제거 시 (a) 카드·키 부재, (b) 변경 전 gil.py(HEAD) 출력과의
   차이가 **CSS/JS 상수 블록에 국한**되고 HTML 본문 콘텐츠 차이 0임을 tag-split diff로 확인
   (릴리스 패널 C006도 CSS는 항상 인라인되는 계약 — 렌더 카드/데이터가 안 늘면 하위호환).
6. **상호작용·폴링 실측(CDP)**: stdlib raw-WebSocket CDP 드라이버(C010~C013 재사용)로 라이브 서버에
   띄우고 — depcyc 링크 클릭 → 대상 cycdoc이 visible·body 채워짐, 폴링 1주기 통과 후 배포 패널 잔존·
   패널 텍스트 불변·열린 대상 유지·hash 보존 확인(C014 상태보존 회귀 0).
7. **conformance**: WEB-DEPLOYMENTS 판정 항목 추가(구조 수준). 참조 회귀 0.

## 준비물

- gil.py (참조 구현, gil 2.49.0), Python 3 stdlib, 깃 CLI.
- Google Chrome (headless, `--screenshot`·CDP `--remote-debugging-port`).
- CDP 드라이버: loomlight/C013/3-verification/cdp.py (raw WebSocket, stdlib).
- 세션-로컬 샌드박스 경로(공유 /tmp 병렬 충돌 회피, loomlight/C003 교훈).

## 측정 방법

- M1 구조: 배포 카드=1 ∧ 릴리스 카드=0 ∧ depcyc 앵커⊆cycdoc id ∧ status 마크 3종 ∧ live 배지 정확.
- M2 하위호환: 무deployments.json → 카드·키 0 ∧ HEAD 대비 HTML 본문 diff 0(CSS/JS 상수만).
- M3 상호작용: depcyc 클릭 → 대상 visible ∧ bodyFilled=true.
- M4 폴링: 1주기 후 패널 잔존 ∧ 텍스트 불변 ∧ 대상 열림 유지 ∧ hash 보존.
- M5 conformance: WEB-DEPLOYMENTS pass ∧ 기존 항목 회귀 0.
- 하나라도 실패하면 해당 기각 조건 발동.

## 사용자 컨펌

생략 — 병렬 세션(소환자 Clew가 land 총괄). 목업을 코드 전에 명시하고 가장 보수적 선택(별 카드·
하위호환 키 부재)을 근거와 함께 남긴 것이 land 검토의 근거가 된다(C004 병렬 규율).

- [x] 컨펌 생략 (사유: 병렬 세션, 목업+보수적 선택으로 대체)
