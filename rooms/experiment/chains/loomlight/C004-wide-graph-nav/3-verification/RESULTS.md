# 3. 검증 결과 — loomlight/C004 (미니맵)

`./verify.sh`(이 폴더)를 `rooms/deployment/ariadne-spec`에서 실행하면 아래를 재현한다.
환경: Python 3.9.6, Go 1.26.5 darwin/arm64, Chrome 헤드리스.

## 측정값

| # | 측정 | 기준 | 결과 |
|---|---|---|---|
| 1 | parity 기본 출력(`gil web`) 참조↔Go `cmp` | 바이트 동일 | **BYTE-IDENTICAL** (1,367,385 B 동일) |
| 2 | parity `--flat` 참조↔Go `cmp` | 바이트 동일 | **BYTE-IDENTICAL** |
| 3 | conformance 참조 | 회귀 0 | **90/90 PASS** |
| 4 | conformance Go | 회귀 0 | **83/83 PASS** |
| 5 | 미니맵이 붙은 체인 수 | 넓은 체인만 | **1개(loom, 깊이 53 ≥ 12)**. genesis(3)·loomlight(4)·gateway(1)·tapestry(1) 미출력 |
| 6 | 좁은 체인 hbody 개선 전/후 `cmp` | 바이트 동일 | genesis·weft·selvage **IDENTICAL**. loomlight는 라이브 상대시각(“활동 N분 전”) 1곳만 차이 = 벽시계 경과분, 구조 변화 0 |
| 7 | 미니맵 노드 href 집합 == 본 그래프 노드 href 집합 | 동일 | **69==69, 집합 일치**. 각 href가 실제 `id="cycdoc-loom-*"`와 매칭 |
| 8 | 자기완결 | 외부 리소스 0·JS 0 | 유지(WEB-SELFCONTAINED PASS 포함) |

## 산출물

- `verify.sh` — 위 1~5를 재현하는 스크립트.
- `rendered-default.html` — 개선 후 기본 출력(참조).
- `minimap-loom.png` — loom 아코디언 펼침 스크린샷: 미니맵(폭맞춤, 전체 69노드 + C003 형제 갈래가
  아래로 살짝 내려간 것까지)이 본 그래프 위에 얹히고, 본 그래프는 자연 크기로 스크롤됨.

## 상호작용(클릭 → 문서) 검증 방식

미니맵 노드 클릭 = `<a href="#cycdoc-loom-*">` 이동 → C067의 `.cycdoc:target{display:block}`(내가
건드리지 않은 기존 기제)이 그 문서를 드러낸다. 측정 #7로 **미니맵 69노드의 href 집합이 본 그래프
69노드와 완전히 일치**하고 각 href가 실제 존재하는 `id`와 매칭됨을 확인 — 즉 미니맵 클릭은 본 그래프
클릭과 동일한 문서를 :target으로 연다. (헤드리스 스크린샷은 매우 긴 페이지에서 프래그먼트 스크롤
위치가 뷰포트를 벗어나는 캡처 아티팩트가 있어, 구조적 링크 증명으로 대체 — 기제 자체는 C067에서 검증됨.)
