# 2. 실험 설계

가설 하나만 검증한다: 노드 스트림 재설계가 네 요청을 JS 0으로 충족하면서 flat 불변·양 구현 바이트 동일.

## 절차

1. **gil.py `_render_cycle_detail` 재작성** (hierarchy 전용): 반환을 `<li><details class="cyc" name="cyc-<chain>"><summary>● cid·상태·title·⇠lineage칩·↣sup</summary><div class="cbody"><span id="cyc-<chain>-<cid>">메타표+5스텝</div></details></li>`. lineage 칩 `href="#cyc-<ref/→->"`로 원천 점프. dot 색=상태(closed 채움·open 테두리·rejected 빨강).
2. **gil.py `_render_hierarchy_body` 체인 블록**: `<div class="card">SVG</div>`+표 제거 → `<ol class="cycstream">노드들</ol>`. 체인 `<details>`에 `name="hchain"`(배타 아코디언). 미사용 `single` 변수 제거.
3. **CSS(`_WEB_HIER_CSS`)**: `.cycstream`(좌측 레일 border-left) · `.cyc summary`(dot 절대배치 on rail) · `.cdot/.open/.rej` · `.ccid/.cyst/.cytitle` · `a.linchip`(초록, sup은 supersede색) · `.cbody`. `.hbody` gap 0으로.
4. **go/main.go 동형 이식**: `renderCycleDetail`·`renderHierarchyBody` 블록·`webHierCSS` 동일 문자. 정수·문자열뿐이라(좌표 계산 없음) 이식이 곧 바이트 동일.
5. **검증**: Go 빌드 → `diff -q` 기본·`--flat` 바이트 대조 → conformance 양 구현 → 헤드리스 Chrome: `#chainbody-loomlight`(아코디언 열림+스트림+lineage 칩), `#cyc-loomlight-C003-…`(노드 클릭→5스텝 인라인).

## 준비물

- Python 3.9.6, Go 1.26.5 darwin/arm64, Chrome 헤드리스.
- 대상: `rooms/deployment/ariadne-spec/{gil.py, go/main.go}` (hierarchy 렌더 경로만). flat 경로(`_render_svg`·`_render_tables`)는 불변.

## 측정 방법

- **parity**: 기본·`--flat` 각각 `diff -q` 바이트 동일 = 성공.
- **conformance**: 참조 90/90·Go 83/83(회귀 0).
- **상호작용**: 스크린샷에서 (a) 지도 원/아코디언으로 체인 펼침 + lineage 칩 다 보임, (b) 노드 열면 5스텝이 그 아래 인라인.

## 사용자 컨펌

박상현 네 차례 지시로 방향 확정(카드 제거·주루룩 노드·lineage 가시·노드 클릭 5스텝·아코디언). 스크린샷 반복 후 "확정 — 배포 진행" 승인. 초기 SVG-ghost 방향은 "따로 카드 잡지 말고"로 기각되어 노드 스트림으로 선회(정직한 방향 전환).

- [x] 컨펌 받음 (일자: 2026-07-19)
