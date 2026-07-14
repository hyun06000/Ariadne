# 2. 실험 설계

1. **T1 크로스 빌드** — 패키지 go/에서 GOOS/GOARCH 4타깃 빌드 + SHA256SUMS 생성.
2. **T2 산출물 판정** — darwin-arm64(네이티브) 산출물로 conformance → 26/26.
3. **릴리스 생성** — `gh release create v1.0.0` (기존 태그에): 바이너리 4개 + SHA256SUMS + 릴리스 노트(설치 한 줄, 바이너리 범위 고지: release·open --git/--push는 참조 구현 전용 — 정직하게).
4. **T3 딸깍 검증** — `releases/download/v1.0.0/gil-darwin-arm64`를 curl로 받아 체크섬 대조 + 실행(fsck).
5. **배선** — `.github/workflows/gil-release.yml`: `v*` 태그 push 시 4타깃 빌드·자동 첨부 (gh CLI, 러너 기본 도구만). 빌드 명령은 run 블록에 — C007 방식 추출 검증 (T4).
6. **문서** — QUICKSTART 맨 앞에 "딸깍 설치" 절(curl 한 줄 + 판정 한 줄), README 갱신. 문서 릴리스 v1.0.1.

## 사용자 컨펌

- [x] 컨펌 받음 (2026-07-15, 박상현 — 과제 자체가 사용자 지시. 다른 맥 테스트는 사용자 수행)
