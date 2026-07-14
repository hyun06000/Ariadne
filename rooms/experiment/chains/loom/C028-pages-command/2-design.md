# 2. 실험 설계

1. **구현(참조·Go)** — `gil pages [--force] [--root]`: `<repo>/.github/workflows/gil-pages.yml` 생성. 저장소 루트는 chains-root에서 `../..`로 유추. 내용: main push 트리거 + workflow_dispatch, pages 권한, 러너에서 `curl <releases>/latest/download/gil-linux-amd64` → `gil web -o _site/index.html` → upload-pages-artifact → deploy-pages. 사용자 저장소명은 어디에도 안 박힘(gil 다운로드 URL만 gil 배포처로 고정 — 정당). 파일 존재 시 거부, --force로 덮기.
2. **T1 생성** — 빈 git 저장소에서 gil pages → yml 존재 + 필수 요소(push/main·pages: write·id-token·upload-pages-artifact·deploy-pages) 전부.
3. **T2 빌드 재현** — 생성된 yml의 build run 블록 추출, curl 라인을 로컬 gil로 치환해 실행(러너 네트워크·아키 제약 회피) → _site/index.html 생성 + gil-data JSON 존재.
4. **T3 이식성** — 생성물에 "hyun06000/Ariadne" 사용자-저장소 참조 0 (gil 릴리스 URL 제외).
5. **T4 덮어쓰기 방어** — 재실행 거부(무변경), --force 덮기.
6. **T5 회귀** — conformance × 참조·Go 각 26/26.
7. **릴리스** — v1.2.0(도구 변경, 양 구현) + 바이너리 4타깃 재배포. QUICKSTART·README에 gil pages 안내. SPEC §5 CLI에 pages 추가.

## 사용자 컨펌

- [x] 추천 위임 (2026-07-15, 박상현: "나는 잘 몰라서 추천받을게" → A안)
