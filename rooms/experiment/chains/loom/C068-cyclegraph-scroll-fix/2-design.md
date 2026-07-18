# 2. 실험 설계

가설 하나만: 셀렉터를 직계 자식으로 좁히면 그래프가 자연 크기로 스크롤된다.

## 절차

1. **gil.py `_WEB_HIER_CSS`**: `.gil .hmap svg{...max-width:100%}` → `.gil .card.hmap>svg{...max-width:100%}`.
2. **go/main.go `webHierCSS`**: 동일 문자로 이식.
3. **검증**: Go 빌드 → `diff -q` 기본·`--flat` 바이트 대조 → conformance 양 구현 → 헤드리스 Chrome으로 loom(67노드) 펼쳐 그래프가 자연 크기로 보이고 오른쪽으로 스크롤되는지 스크린샷.

## 준비물

- Python 3.9.6, Go 1.26.5 darwin/arm64, Chrome 헤드리스.
- 대상: `rooms/deployment/ariadne-spec/{gil.py, go/main.go}` CSS 한 줄.

## 측정 방법

- **parity**: 기본·`--flat` `diff -q` 바이트 동일.
- **conformance**: 참조 90/90·Go 83/83.
- **시각**: loom 펼침 스크린샷에서 노드가 읽히는 자연 크기 + 그래프가 뷰포트를 넘겨 스크롤(전부 축소 표시 아님).

## 사용자 컨펌

상현님 지적("스크롤 안 되고 다 작게 보인다")에 대한 수정. 실물 스크린샷으로 자연 크기+스크롤 확인.

- [x] 컨펌 받음 (일자: 2026-07-19) — 수정 지시 + 스크린샷 확인
