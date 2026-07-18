# 2. 실험 설계

가설 하나만 검증한다: 삼각함수 없는(sqrt-only) 체인 지도를 위계 상단에 얹어도 양 구현이 바이트 동일하고, 기존 계약이 보존되며, 클릭 드릴다운이 동작한다.

## 절차

1. **gil.py `_render_chain_map(data)` 신설**: (a) 사이클 lineage를 체인→체인 엣지로 집계(source=교훈 원천, target=인용 체인), (b) 허브(최다 연결, 동률이면 사이클 많은 쪽)를 정렬된 `base` 중앙에 배치해 스포크 대칭화, (c) 반지름 = clamp(12+4.6·√사이클수), (d) 엣지 아치는 위로만(라벨과 안 겹침), 양방향 쌍은 역방향을 바깥으로 겹쳐 구분, (e) **끝점을 아치 정점 방향 원 둘레에 벡터 정규화로 배치**(삼각함수 금지 — sqrt만), (f) 굵기·숫자 라벨 ∝ 건수(후광 처리), (g) 원 색=상태(rejected→빨강, 열림→점선 링), (h) 원 전체가 `<a href="#chainbody-<name>">`.
2. **위계 몸체 배선**: 헤더 다음에 `<div class="card hmap">` 삽입, 각 체인 hbody 앞에 `<span id="chainbody-<name>" class="hanchor">` 추가(프래그먼트 표적), hhint 문구 갱신. CSS(.hmap·.chainnode·.hanchor) 추가.
3. **go/main.go 동형 이식**: `renderChainMap` + 배선 + webHierCSS. 순회 결정성 확보 — 엣지는 `sorted(src,tgt)`, 허브는 정렬 base에서 첫 최대, `math.Sqrt` 사용(참조 `math.sqrt`와 IEEE 비트 동일).
4. **검증**: Go 빌드 → `diff -q`로 무옵션·`--flat` 바이트 대조 → conformance 양 구현 → 헤드리스 Chrome으로 렌더 스크린샷 + `#chainbody-loom` 표적 이동 시 loom `<details>` 열림 확인.

## 준비물

- Python 3.9.6, Go 1.26.5 darwin/arm64, Google Chrome(헤드리스 스크린샷).
- 대상: `rooms/deployment/ariadne-spec/{gil.py, go/main.go}` (+ conformance 회귀 확인).
- 데이터: `rooms/experiment/chains` (5체인: gateway·genesis·loom·loomlight·tapestry, 체인간 lineage 8엣지).

## 측정 방법

- **parity**: `diff -q` 무옵션·`--flat` 각각 바이트 동일 = 성공. 1바이트라도 다르면 기각.
- **conformance**: 참조 90/90·Go 83/83 유지(회귀 0).
- **드릴다운**: `file://…#chainbody-loom` 스크린샷에서 loom 체인이 펼쳐져 사이클 그래프가 보이면 성공.

## 사용자 컨펌

박상현과 반복 확정: 원=체인·크기 ∝ 사이클수·초록 점선 화살표=lineage·클릭 드릴다운. 시각 조정 4건(화살표 겹침 완화·카드 여백 축소·건수 라벨·원 상태색) 헤드리스 스크린샷으로 반복 후 "확정 — 배포 진행" 승인.

- [x] 컨펌 받음 (일자: 2026-07-19)
