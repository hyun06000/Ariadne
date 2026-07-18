# 2. 실험 설계

## 절차

1. **참조 구현 `gil.py`**:
   - `_render_parallel_banner(data)` 추가: 전 체인(`sorted(data)`)의 `reservations`를 집계, 0이면 `""`, 아니면 `<div class="parbanner" role="status">⟳ 병렬 진행 중 (예약…): <b>N</b>` + 칩(`chain/C0NN → for`).
   - 위계 본문(`_render_hierarchy_body`)의 `</header>` 아래, 평면 본문의 `</header>` 아래에 각각 `{_render_parallel_banner(data)}` 삽입.
   - `_WEB_CSS` 앞에 `.parbanner`/`.pchip`/`.picon` 규칙 추가(테마 변수 사용, 라이트/다크 자동).
2. **Go `go/main.go`**: `renderParallelBanner(d)` 동형 이식(정수·문자열만) + 두 본문 배선 + `webCSS`에 같은 CSS 문자 단위 프리펜드.
3. **판정기 `conformance.py`**: `WEB-PARALLEL-BANNER` — lroot에 예약 없을 때 배너 부재, 예약(`9 tester …`) 심고 재렌더 시 배너 출현+`demo/C009`+`tester` 표기. web은 양 구현에 있어 둘 다 판정.
4. **SPEC §5.2** web 행에 배너 한 구절 추가(문서 계약).
5. **회귀·parity**: 참조·Go 전체 conformance, 예약 유무 두 경우 참조↔Go `cmp` 바이트 동일(위계·평면).

## 준비물

- gil.py·go/main.go·conformance.py (main, 순차 작업 — 동시 에이전트 0이라 워크트리 불요, C073 세션의 규약 정련 실천).
- Go: `GO111MODULE=off go build main.go` (go1.x, /opt/homebrew).
- 픽스처: 예약 1건을 담은 임시 체인 루트(배너 출현) + 무예약 main(배너 부재).

## 측정 방법

- **WEB-PARALLEL-BANNER**: 예약 0 → `role="status"` 부재 ∧ 예약 1 → `role="status"` 출현 + 예약 ref·author 표기. 참조·Go 둘 다 PASS.
- **parity**: `cmp`로 참조↔Go web — (a) 무예약(main), (b) 예약 위계, (c) 예약 평면 — 세 경우 바이트 동일.
- **회귀**: 기존 항목 전부 유지(참조 97→98, Go 83→84; +1은 회귀 아님).

기준: WEB-PARALLEL-BANNER PASS(양 구현) ∧ parity 3/3 바이트 동일 ∧ 회귀 0.

## 사용자 컨펌

- [x] 컨펌 받음 (일자: 2026-07-19) — 상현님이 "뷰어 병렬 배너 지금 얹기"를 AskUserQuestion에서 선택. 상현님의 원 요청("뷰어에 병렬이 안 잡힌다")의 직접 응답.
