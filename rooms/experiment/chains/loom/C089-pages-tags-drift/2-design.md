# 2. 실험 설계 — CI 태그 미포함 → 뷰어 drift 오표시

## 절차
1. **워크플로(근본)**: `_PAGES_WORKFLOW`의 `actions/checkout@v4`에 `with: fetch-depth: 0` 추가 — CI가 태그를 가져오게. (checkout 기본은 shallow·태그 미포함.)
2. **뷰어 강건성(방어선)**: `_build_releases_data`가 `tags_readable`(태그를 못 읽는 환경이면 False)을 데이터에 담고, `_render_releases_panel`이 False면 drift 배지를 억제. tags가 None(git부재) 또는 {}(태그0)이면 False — CLI cmd_releases의 git_absent 처리를 뷰어에 이식.
3. **진짜 drift 보존**: 태그가 읽혔는데(tags_readable=True) 특정 버전만 없으면 배지 유지.

## 준비물
- 정본 gil.py. 임시 저장소(CHANGELOG 있음·태그 0 = CI 모사 / 태그 일부 = 진짜 drift).

## 측정 방법
- A 태그있음: tags_readable=True, in_tag=True, 정상 릴리스 배지 없음.
- B CI모사(태그0): tags_readable=False, rdrift 배지 억제(⚠ CHANGELOG만 사라짐).
- C 진짜 drift(한 버전만 태그없음): tags_readable=True, 그 버전 배지 유지.
- D pages 워크플로에 fetch-depth: 0.
- E 회귀 0.

## 사용자 컨펌
- 발의(박상현: "모든 버전이 CHANGELOG만이라 뜬다"). CLI/로컬은 정상이고 github.io만 문제임을 확인 → CI 태그 미포함이 근본 원인.
- [x] 컨펌 받음 (일자: 2026-07-20)
