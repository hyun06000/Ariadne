# 3. 가설 검증

산출물: GitHub Release v1.0.0(바이너리 4 + SHA256SUMS), .github/workflows/gil-release.yml, QUICKSTART §0 딸깍 설치, runs/ 3건.

재현: `curl -fsSL -o gil https://github.com/hyun06000/Ariadne/releases/download/v1.0.0/gil-darwin-arm64 && chmod +x gil && ./gil fsck`

실행 기록 (2026-07-15): T1 4타깃 크로스 빌드(zsh 단어 분리 함정 1회 수정) ✓ · T2 산출물 conformance 26/26 ✓ · T3 공개 URL 다운로드 체크섬 일치 + 실행 ✓ · T4 워크플로 추출 실행(신선 클론, dist 4+1 생성) ✓. 미구현 범위(release·open --git)는 릴리스 노트에 정직 고지.
