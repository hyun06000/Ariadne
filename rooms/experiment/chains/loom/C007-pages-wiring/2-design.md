# 2. 실험 설계

## 절차

1. **기대 판정 고정** — T1~T4를 `3-verification/fixtures/expected-wiring.md`에 워크플로 작성보다 먼저 기록한다.
2. **워크플로 작성** — `.github/workflows/ariadne-pages.yml`: main push 트리거 → checkout → 빌드(`run:` 블록 하나에 집약: `_site/` 생성 + 배포된 v0.1.0 `ari.py web`) → `upload-pages-artifact` → `deploy-pages`. 빌드 스텝은 표준 러너의 python3만 사용.
3. **검증** — tests.py:
   - T1: `git clone`으로 신선한 클론 생성(체크아웃 시뮬레이션) → **워크플로 파일에서 `run:` 블록을 추출**해 클론 안에서 실행 → `_site/index.html`의 내장 JSON 사이클 집합 = 클론 파일시스템 스캔 결과.
   - T2: 산출물 자기완결(외부 참조 0).
   - T3: 빌드 명령에 설치·네트워크 없음 (pip/npm/curl/wget 부재).
   - T4: 워크플로 구조 — push(main) 트리거, `pages: write`/`id-token: write` 권한, checkout·upload-pages-artifact·deploy-pages 액션.
4. **배선 커밋** — 검증 통과 후 워크플로를 커밋한다. README에 뷰어 한 줄 추가.
5. **닫기** — `ari close --git`.

## 준비물

- 배포된 v0.1.0 도구 (rooms/deployment/ariadne-spec/ari.py — 이미 커밋됨, 클론에 존재)
- git, python3

## 측정 방법

| # | 항목 | 통과 기준 |
|---|---|---|
| 1 | 재현 | T1: 추출된 빌드 스텝이 클론에서 exit 0 + JSON 사이클 집합 = 클론 스캔 |
| 2 | 자기완결 | T2: `_site/index.html` 외부 참조 0 |
| 3 | 무설치 | T3: run 블록에 pip·npm·curl·wget 0회 |
| 4 | 정의 정합 | T4: 트리거·권한·3개 액션 전부 존재 |

전부 통과 → 채택. 원격 끝단(실제 Pages URL)은 한계로 기록하고 사용자 확인 사항으로 남긴다.

## 사용자 컨펌

- [x] 컨펌 받음 (2026-07-14, 박상현: "추천대로 가보자" — C006 보고서의 추천안 (A) 진행 승인)
