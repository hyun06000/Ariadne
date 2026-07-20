# 2. 실험 설계 — 헤더에 gil 버전

## 절차
1. hierarchy 헤더(`_render_hierarchy_body`)와 flat 헤더(render_web_page else)의 통계 `<p>`에 `· <span class="gilver">gil v{_GIL_VERSION}</span>` 추가.
2. `.gilver` CSS를 **`_WEB_CSS`**(flat·hierarchy 공용)에 추가 — `_WEB_HIER_CSS`에 넣으면 flat엔 스타일이 안 붙는다(검증 중 실제로 밟은 함정).

## 준비물
- 정본 gil.py. `_GIL_VERSION` 모듈 전역.

## 측정 방법
- M1: hier·flat 두 몸 모두 헤더에 `gil v<현재버전>` (버전은 version 명령과 일치 = 하드코딩 아님).
- M2: `.gilver{` CSS가 두 몸 HTML에 모두 존재.
- M3: 문법·conformance 회귀 0.

## 사용자 컨펌
- 발의 지시(박상현)가 곧 컨펌. 위치(헤더 통계줄)는 "항상 보이게"의 자연스러운 자리.
- [x] 컨펌 받음 (일자: 2026-07-20)
