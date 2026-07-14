# 3. 가설 검증

산출물: 패키지 승격(`ariadne-spec/go/` — main.go + 빌드 지침 + 절대 경로 경고), runs/run1-dual-judgment.txt, run2-release.txt.

재현: 패키지만 임시 디렉토리에 복사 → `go build` → conformance × 두 구현 (run1의 스크립트 그대로).

실행 기록 (2026-07-15): T1 신선 빌드 + Go 26/26 + Python 26/26 ✓ · T2 승격 후 verify 26사이클 무변조 ✓ · T3 v1.0.0 각인(단조 ✓, gil.py·conformance 무변경 → 규칙상 유효) ✓. Weft가 C020에서 발견한 --gil 상대 경로 함정을 go/README에 명시.
