# 3. 가설 검증

산출물: gil.py·go/main.go의 fallback(내장 스캐폴드 + chains-root 자동 생성), runs/ 3건. 릴리스 v1.1.0.

재현: 빈 디렉토리에서 `curl -fsSL -o gil <latest>/gil-darwin-arm64 && chmod +x gil && ./gil open demo x --new-chain --title t && ./gil fsck`

## 실행 기록 (2026-07-15)

- T1: 갓 빌드한 Go 바이너리만 있는 신선 디렉토리에서 README 대문 블록 전부 성공(두 지뢰 순차 발견·수정: ① _template 부재 → 내장 스캐폴드, ② chains-root 부재 → 자동 생성).
- T2: 표식 있는 _template 존재 시 그것을 우선 사용(내장 아님) — 회귀 0.
- T3: conformance × Go·참조 각 26/26.
- run3: **수신자 관점** — 공개 latest URL에서 받은 바이너리로 빈 폴더에서 딸깍 완결.
