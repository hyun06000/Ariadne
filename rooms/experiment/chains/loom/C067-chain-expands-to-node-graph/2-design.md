# 2. 실험 설계

가설 하나만 검증: 가로 노드-엣지 그래프 + `:target` 문서가 상현님 스케치를 충족하고 flat 불변·양 구현 바이트 동일.

## 절차

1. **전/후 목업 작도·컨펌**: 다크테마 SVG로 현재(세로 목록) vs 제안(가로 0—o—o—o) 그림 → 헤드리스 Chrome 스크린샷 → 상현님 컨펌(`design-mockup-before-after.png`).
2. **gil.py `_render_cycle_graph_h(name, chain)` 신설**: `_layout_columns`로 (깊이,레인) 계산 → **전치**(x=깊이·`_H_COLW`, y=레인·`_H_ROWH`). parent 실선 곡선, 노드=원(closed 채움·open 테두리·rejected 빨강), C-번호 라벨, 교차-체인 lineage는 노드 아래 초록 `⇠ 첫명+N`. 노드는 `<a href="#cycdoc-name-cid" class="gnode">`.
3. **gil.py `_render_cycle_detail` 재작성**: 반환을 `<div class="cycdoc" id="cycdoc-name-cid">`(head+메타+5스텝). 평소 `display:none`, `:target`이면 표시. lineage 칩 `href="#cycdoc-*"`.
4. **hbody 배선**: `<div class="cyclegraph">{graph}</div><div class="cycdocs">{docs}</div>`. CSS: `.cyclegraph{overflow-x:auto}` · `a.gnode` · `.cycdoc{display:none}` · `.cycdoc:target{display:block}`.
5. **go/main.go 동형 이식**: `renderCycleGraphH`·`renderCycleDetail`·hbody·`webHierCSS`. 정수 좌표라 이식이 곧 바이트 동일.
6. **검증**: Go 빌드 → `diff -q` 기본·`--flat` → conformance 양 구현 → 헤드리스 Chrome: `#chainbody-loomlight`(가로 그래프)·`#cycdoc-loomlight-C001-…`(노드 클릭→문서 :target).

## 준비물

- Python 3.9.6, Go 1.26.5 darwin/arm64, Chrome 헤드리스.
- 대상: `rooms/deployment/ariadne-spec/{gil.py, go/main.go}` (hierarchy 렌더·CSS만). flat 경로 불변.

## 측정 방법

- **parity**: 기본·`--flat` `diff -q` 바이트 동일.
- **conformance**: 참조 90/90·Go 83/83.
- **상호작용**: 스크린샷에서 (a) 가로 그래프 펼침·lineage 초록 ⇠, (b) 노드 클릭 시 그래프 아래 문서 :target.

## 사용자 컨펌

상현님 지시로 **전/후 목업을 먼저 그려 컨펌** 받음: "맞음 — 가로(스케치처럼 0—o—o—o)". 이후 실물 렌더도 "배포 진행" 승인. C065~C066의 세로 목록 방향은 오해였음이 목업으로 드러나 정정.

- [x] 컨펌 받음 (일자: 2026-07-19) — 목업 컨펌 + 실물 컨펌 2단
