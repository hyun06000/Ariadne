# 2. 실험 설계

가설 하나만 검증: 아코디언을 지도 카드 안으로 + 서브카드 제거 → 카드 안 인라인 등장·flat 불변·양 구현 바이트 동일.

## 절차

1. **gil.py `_render_hierarchy_body` 반환**: `<div class="card hmap">{지도}<div class="mapchains">{chains_html}</div></div>` — 아코디언을 카드 안으로. 별도 `{chains_html}` 섹션 삭제. htoc는 카드 아래로. hhint 문구를 "그 자리 카드 안에서 아래로 주르륵"으로.
2. **CSS(`_WEB_HIER_CSS`)**: `.mapchains`(상단 구분선). `.hchain` 배경·테두리·라운드 제거 → `border-bottom` 구분선만. summary 패딩 축소(14/20→11/4), 폰트 15→14. 열린 체인 summary에 옅은 강조(`[open]>summary{background:var(--page)}`). `.hbody` 좌패딩 축소(카드 안이므로).
3. **go/main.go 동형 이식**: `renderHierarchyBody` 반환부(인자 순서 map→chains→toc) + `webHierCSS` 동일 문자.
4. **검증**: Go 빌드 → `diff -q` 기본·`--flat` → conformance 양 구현 → 헤드리스 Chrome: 기본(카드 안 아코디언 접힘)·`#chainbody-loomlight`(카드 안에서 loomlight 노드 스트림 등장).

## 준비물

- Python 3.9.6, Go 1.26.5 darwin/arm64, Chrome 헤드리스.
- 대상: `rooms/deployment/ariadne-spec/{gil.py, go/main.go}` (hierarchy 렌더·CSS만). flat 경로 불변.

## 측정 방법

- **parity**: 기본·`--flat` 각각 `diff -q` 바이트 동일.
- **conformance**: 참조 90/90·Go 83/83(회귀 0).
- **배치**: 스크린샷에서 지도+체인+열린 스트림이 한 카드 안, 서브카드 박스 없음.

## 사용자 컨펌

박상현 정정("체인 노드 누르면 지도 카드 안에서 노드가 주르륵 아래로")으로 방향 확정. 스크린샷 후 "맞음 — 배포 진행" 승인.

- [x] 컨펌 받음 (일자: 2026-07-19)
