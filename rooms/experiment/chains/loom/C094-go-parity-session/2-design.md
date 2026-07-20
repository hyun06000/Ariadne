# 2. 실험 설계 — Go 이식 (참조를 정본으로)

## 절차 (독립 4갈래, 순차 — 다 main.go 한 파일이라 워크트리 대신 순차, C074)

### ① C085 refresh 기본 (Go)
- `webDefaultRefresh=5` 상수. web 파싱: `--refresh` 미지정 → 5, 지정(0 포함) → 그 값.
- bake 조건 `refresh > 0` → `>= 0`(0도 기록). meta는 `> 0`(0이면 없음).
- `bakeMeta`: Refresh를 `*int`로(nil=구버전 → 기본 5, 명시 0 존중). 초기값 5.

### ② C090 open 1스텝 + step 가드 (Go)
- `stepScaffold` 맵 + `contentSubstantive`(C092판: 본문 실질 줄이 마크 하나뿐이면 미완) + `stepWritten` + `createStepFile` 헬퍼.
- cmdOpen: 5스텝 스캐폴딩 → `createStepFile(dest,1,template)`.
- cmdStep: 전이 가드(1..N-1 실질작성 검증, 미완이면 무변화 거부) + 다음 스텝 생성 + 안내 출력.

### ③ C088 md 렌더 토글 (Go)
- webAppJS에 `rendered`·`safeUrl`·`inlineMd`·`renderMd`·`stepHtml` 추가(참조 JS와 동일, Go 백틱 이스케이프).
- build/buildBeing를 stepHtml로. 토글 클릭 핸들러 + rebuildOpen.
- 헤더에 mdtoggle 버튼 + gilver(C087도 함께). CSS(.gilver·.mdtoggle·.mdbody 계열) webCSS에.

## 측정 방법
- 각 이식 후 `go build` + `conformance --gil /tmp/gil-go`로 해당 항목 PASS 확인(점진).
- 최종 Go 104/104 "이 구현은 gil이다". 참조 122/122 무회귀.
- gil-gate(CI)가 참조·Go 양쪽 녹색.

## 미이식 (정직, 후속)
- C088 이미지 base64 임베드(Go collectCycleDocs): conformance가 정적 검사라 안 잡음. 실제 이미지 표시 동형을 위해 후속 필요.
- C091(노드 입출력 마커)은 참조에도 아직 — 별도 진행 중.

## 사용자 컨펌
- 상현님 "Go에 이식(정공법)". 4갈래 순차, 각 점진 커밋.
- [x] 컨펌 받음 (일자: 2026-07-20)
