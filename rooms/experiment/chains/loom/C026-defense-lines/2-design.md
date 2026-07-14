# 2. 실험 설계

1. **룰셋 2종** (gh api, 활성): main 브랜치 — deletion·non_fast_forward 금지 (PR 강제는 넣지 않는다 — 존재들의 직접 push가 정상 경로). 태그 `refs/tags/cycle/**`·`refs/tags/v*` — deletion·non_fast_forward 금지, 생성 허용.
2. **CI 게이트** — `.github/workflows/gil-gate.yml`: PR + main push에 fsck → verify → conformance(파이썬) → go build + conformance(Go). fetch-depth 0 (verify가 태그 필요).
3. **T1 파괴 프로브** — 기존 태그의 원격 삭제 push 시도 → 거부 확인 (실패 시 복구 계획: 로컬 태그 재push).
4. **T2 문지기 검증** — 게이트 run 블록을 신선 클론에서 추출 실행(전부 통과) + 위반 주입 클론(유령 parent 사이클)에서 재실행 → 비영 종료.
5. **T3 정상 경로** — 이 사이클 자신의 스텝 push와 close의 태그 생성이 룰셋 아래에서 성공.

## 사용자 컨펌

- [x] 컨펌 받음 (2026-07-15, 박상현: "가자")
