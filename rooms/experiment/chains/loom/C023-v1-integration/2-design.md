# 2. 실험 설계

1. **승격** — C020의 gil-go 소스를 `rooms/deployment/ariadne-spec/go/`로 복사(+ `go/README.md`: 빌드 한 줄 `go build -o gil main.go`, 의존성 0 명시). 원본(닫힌 사이클)은 불가침 — 복사만.
2. **T1 신선 빌드·이중 판정** — 임시 디렉토리에 패키지만 복사 → `go build` → conformance × Go 26/26, conformance × 파이썬 26/26.
3. **T2 불변** — 승격 후 `gil verify` 무변조 (닫힌 사이클 26개).
4. **T3 릴리스** — `gil release 1.0.0` — 단조(1.0.0 > 0.9.3) ✓, gil.py·conformance 무변경이므로 분류는 "문서 릴리스"(소스 동봉은 패키지 확장) — CHANGELOG·태그 확인. SPEC §7에 "두 구현" 항 갱신, RELEASE.md에 v1.0.0 이정표 서술.

## 사용자 컨펌

- [x] 전권 위임으로 갈음 (2026-07-15 — v1.0 통합은 직전 보고들에서 예고된 경로)
