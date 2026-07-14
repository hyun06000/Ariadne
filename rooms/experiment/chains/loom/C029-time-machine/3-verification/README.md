# 3. 가설 검증

산출물: gil goto(참조·Go), SPEC §5·README.ai 반영, runs/ 3건. 릴리스 v1.3.0.

재현: `python3 rooms/deployment/ariadne-spec/gil.py goto loom/C005-web-viewer` (조회) / `--checkout`은 격리 저장소에서 (run3 스크립트).

## 실행 기록 (2026-07-15)

- run1: 조회 출력 두 구현 바이트 동일.
- run2: 첫 실행에서 T2b 복귀·T4 분기 FAIL — 조사 결과 **goto 결함이 아니라 픽스처 결함**(git init 기본 브랜치가 master인데 복귀를 "main"으로 하드코딩 → detached 오염). C016 교훈("테스트를 먼저 의심하라") 적중.
- run3: 픽스처 `-b main` 교정 후 3/3 — 체크아웃 왕복(C001 역행→복귀), 미커밋 거부, 분기 재시작(C001에서 wrong·better 두 갈래), 없는 사이클 오류. conformance 26/26.
