# 5. 결과 보고 — 뷰어 헤더에 gil 버전 (발의: 박상현)

## 요약
뷰어 헤더(hierarchy·flat 두 몸) 통계 줄에 `gil v{_GIL_VERSION}`을 추가해, CHANGELOG 유무와 무관하게 이 뷰어를 구운 도구 버전이 항상 보이게 했다. `.gilver` CSS는 공용 _WEB_CSS에. M1~M3 통과, 회귀 0. **채택(supported).**

## 교훈
1. **자기버전은 이미 데이터에 있었다** — C061의 `_GIL_VERSION` 자기보고를 헤더가 재사용. 순수 렌더 추가(새 진실 0).
2. **CSS 두 블록의 경계는 검증으로만 보인다** — 공용(_WEB_CSS)/위계전용(_WEB_HIER_CSS)을 혼동하면 한 몸에만 스타일이 붙는다. 두 몸 각각 확인이 필수.

## 다음 사이클을 위한 제안
- 제안 2(스텝 문서 마크다운 렌더링 토글 + 이미지 임베드) — 별도 사이클(큰 카브, JS 파서 계약 긴장). **다음 1순위.**

## 사이클 닫기
- [x] hier·flat 두 몸 헤더에 gil 버전, .gilver 공용 CSS, 회귀 0
- [ ] close --verdict supported / 릴리스 / memory
